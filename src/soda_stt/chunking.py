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


def _parse_silences(stderr_text: str) -> list[tuple[float, float]]:
    silences: list[tuple[float, float]] = []
    cur_start: float | None = None
    for m in _SILENCE_RE.finditer(stderr_text):
        kind, value = m.group(1), float(m.group(2))
        if kind == "start":
            cur_start = value
        elif kind == "end" and cur_start is not None:
            silences.append((cur_start, value))
            cur_start = None
    return silences


def _ffmpeg_cmd(source: str, out: str, noise_db: float, min_silence_s: float) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH; required for chunking.")
    return [
        ffmpeg, "-nostdin", "-y", "-i", source,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_s}",
        "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-f", "s16le", out,
    ]


def decode_to_file(
    source: str,
    out_path: str,
    *,
    noise_db: float = -30.0,
    min_silence_s: float = 0.4,
) -> tuple[float, list[tuple[float, float]]]:
    """Decode to a 16 kHz mono s16le PCM file and detect silences in one pass.

    Writes the PCM straight to out_path (never holding it in memory) and returns
    (duration_s, silences). Workers then read only their byte range via
    read_chunk(), keeping RAM independent of the recording's length.
    """
    import os

    cmd = _ffmpeg_cmd(source, out_path, noise_db, min_silence_s)
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed on {source!r}: "
            f"{proc.stderr.decode(errors='replace').strip()[:500]}"
        )
    silences = _parse_silences(proc.stderr.decode(errors="replace"))
    duration_s = os.path.getsize(out_path) / _BYTES_PER_SECOND
    return duration_s, silences


def decode_with_silences(
    source: str,
    *,
    noise_db: float = -30.0,
    min_silence_s: float = 0.4,
) -> tuple[bytes, list[tuple[float, float]]]:
    """Decode to in-memory PCM and detect silences in one pass.

    Convenience for short inputs; for long audio prefer decode_to_file(), which
    does not buffer the whole stream.
    """
    cmd = _ffmpeg_cmd(source, "-", noise_db, min_silence_s)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed on {source!r}: "
            f"{proc.stderr.decode(errors='replace').strip()[:500]}"
        )
    return proc.stdout, _parse_silences(proc.stderr.decode(errors="replace"))


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


def _byte_range(chunk: Chunk) -> tuple[int, int]:
    lo = int(chunk.start_s * _BYTES_PER_SECOND) & ~1  # keep sample alignment
    hi = int(chunk.end_s * _BYTES_PER_SECOND) & ~1
    return lo, hi


def feed_plan(
    chunk: Chunk,
    silences: list[tuple[float, float]],
    *,
    pad_s: float = 0.15,
    min_skip_s: float = 0.05,
    max_skip_s: float | None = 1.0,
) -> list[tuple[float, float]]:
    """Time ranges (absolute seconds) of a chunk worth feeding to the engine.

    The encoder costs the same for every frame, so feeding detected silence is
    pure waste: drop it and keep only `pad_s` before speech resumes (enough
    context for the endpointer and for word onsets). Timestamps are recovered
    afterwards via the time map built from these ranges (see engine.py).

    Pauses longer than max_skip_s are fed whole: SODA's endpointer needs them
    to cut segments, and keeping them also lets the decoder restart instead of
    rescoring an ever-longer context — measured fastest on a 55-minute file
    (85.6 s vs 86.2 s skipping everything vs 91.3 s feeding everything), with
    segment boundaries preserved for pauses people actually hear.
    """
    feed_from = chunk.start_s
    segments: list[tuple[float, float]] = []
    for start, end in silences:
        skip_from = max(start, feed_from)
        skip_to = min(end - pad_s, chunk.end_s)
        if skip_from >= chunk.end_s:
            break
        if end - start > (max_skip_s if max_skip_s is not None else float("inf")):
            continue  # keep this pause: the endpointer needs it
        if skip_to - skip_from >= min_skip_s:
            if skip_from > feed_from + 1e-6:
                segments.append((feed_from, skip_from))
            feed_from = skip_to
    if feed_from < chunk.end_s - 1e-6:
        segments.append((feed_from, chunk.end_s))
    return [(a, b) for a, b in segments if b - a > 0.02]


def slice_pcm(pcm: bytes, chunk: Chunk) -> bytes:
    """Byte-exact slice of in-memory PCM for a chunk."""
    lo, hi = _byte_range(chunk)
    return pcm[lo:hi]


def read_chunk(path: str, chunk: Chunk) -> bytes:
    """Read only a chunk's byte range from a PCM file (seek + bounded read)."""
    lo, hi = _byte_range(chunk)
    with open(path, "rb") as f:
        f.seek(lo)
        return f.read(hi - lo)


def read_segments(
    path: str, chunk: Chunk, plan: list[tuple[float, float]]
) -> list[bytes]:
    """Read a chunk's feed-plan ranges (skipped silence is never read).

    Returns one entry per plan range, in order — pairing with plan is exact.
    """
    bps = _BYTES_PER_SECOND
    out: list[bytes] = []
    with open(path, "rb") as f:
        for start, end in plan:
            lo = int(start * bps) & ~1
            hi = int(end * bps) & ~1
            f.seek(lo)
            out.append(f.read(hi - lo))
    return out
