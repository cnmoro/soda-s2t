"""Silence-aware chunking for fast parallel transcription.

SODA transcribes a silence-bounded clip of up to ~30 s completely when fed in
bulk. Splitting a long recording at silences into such clips lets us transcribe
them in parallel, each at full speed, then stitch the results back together with
corrected timestamps. This is far faster than feeding one long paced stream.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from ._config import CHANNELS, SAMPLE_RATE

_BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * 2
_SILENCE_RE = re.compile(
    r"silence_(start|end):\s*([0-9.]+)"
)


@dataclass
class Chunk:
    index: int
    start_s: float
    end_s: float

    @property
    def start_ms(self) -> int:
        return int(self.start_s * 1000)


def decode_with_silences(
    source: str,
    *,
    noise_db: float = -30.0,
    min_silence_s: float = 0.4,
) -> tuple[bytes, list[tuple[float, float]]]:
    """Decode to 16 kHz mono s16le PCM and detect silences in one ffmpeg pass.

    Returns (pcm_bytes, silences) where silences is a list of (start_s, end_s).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH; required for chunking.")
    cmd = [
        ffmpeg, "-nostdin", "-i", source,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_s}",
        "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-f", "s16le", "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed on {source!r}: "
            f"{proc.stderr.decode(errors='replace').strip()[:500]}"
        )
    pcm = proc.stdout
    silences: list[tuple[float, float]] = []
    cur_start: float | None = None
    for m in _SILENCE_RE.finditer(proc.stderr.decode(errors="replace")):
        kind, value = m.group(1), float(m.group(2))
        if kind == "start":
            cur_start = value
        elif kind == "end" and cur_start is not None:
            silences.append((cur_start, value))
            cur_start = None
    return pcm, silences


def plan_chunks(
    duration_s: float,
    silences: list[tuple[float, float]],
    *,
    max_chunk_s: float = 28.0,
    min_chunk_s: float = 5.0,
) -> list[Chunk]:
    """Cut [0, duration] into chunks no longer than max_chunk_s, breaking at the
    midpoint of a silence whenever possible so no word is split.
    """
    # Candidate cut points: the midpoint of each silence interval.
    cuts = [(s + e) / 2.0 for s, e in silences]
    chunks: list[Chunk] = []
    start = 0.0
    idx = 0
    while duration_s - start > max_chunk_s + 1e-6:
        window_lo = start + min_chunk_s
        window_hi = start + max_chunk_s
        # Prefer the latest silence midpoint within [lo, hi] (longest valid chunk).
        candidates = [c for c in cuts if window_lo <= c <= window_hi]
        cut = max(candidates) if candidates else window_hi
        chunks.append(Chunk(idx, start, cut))
        start = cut
        idx += 1
    chunks.append(Chunk(idx, start, duration_s))
    return chunks


def slice_pcm(pcm: bytes, chunk: Chunk) -> bytes:
    """Byte-exact slice of the decoded PCM for a chunk."""
    lo = int(chunk.start_s * _BYTES_PER_SECOND) & ~1  # keep sample alignment
    hi = int(chunk.end_s * _BYTES_PER_SECOND) & ~1
    return pcm[lo:hi]
