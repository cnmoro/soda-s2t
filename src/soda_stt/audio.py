"""Audio decoding helpers.

SODA wants 16 kHz, mono, signed-16-bit little-endian PCM. We shell out to
ffmpeg, which accepts essentially any input (wav, mp3, ogg, flac, m4a, video
containers, ...) and can also capture a live device.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Iterator

from ._config import CHANNELS, SAMPLE_RATE


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg not found on PATH; it is required to decode audio input."
        )
    return path


def decode_to_pcm(
    source: str,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> bytes:
    """Decode a file (or URL) fully into s16le PCM bytes."""
    cmd = [
        _ffmpeg(), "-nostdin", "-loglevel", "error",
        "-i", source,
        "-ac", str(channels), "-ar", str(sample_rate),
        "-f", "s16le", "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to decode {source!r}: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    return proc.stdout


def stream_pcm(
    source: str,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    chunk_ms: int = 100,
) -> Iterator[bytes]:
    """Decode incrementally, yielding s16le PCM chunks of ~chunk_ms each.

    Useful for long files so audio need not be fully buffered in memory.
    """
    bytes_per_chunk = int(sample_rate * channels * 2 * chunk_ms / 1000)
    cmd = [
        _ffmpeg(), "-nostdin", "-loglevel", "error",
        "-i", source,
        "-ac", str(channels), "-ar", str(sample_rate),
        "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        while True:
            chunk = proc.stdout.read(bytes_per_chunk)
            if not chunk:
                break
            yield chunk
    finally:
        proc.stdout.close()
        err = proc.stderr.read() if proc.stderr else b""
        if proc.wait() != 0:
            raise RuntimeError(
                f"ffmpeg failed to decode {source!r}: "
                f"{err.decode(errors='replace').strip()}"
            )
