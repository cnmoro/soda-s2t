"""High-level API around the SODA on-device speech engine."""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from . import audio as _audio
from . import soda_api_pb2 as pb
from . import _config
from .download import ensure_engine, ensure_language_pack

_HELPER_NAME = "soda_helper"

# SODA assumes a roughly real-time feed: dumping a whole file at once makes its
# endpointer finalize once and abandon the rest. Feeding at a bounded multiple
# of real time keeps it producing complete, accurate results. ~6x converges to
# the same output as slower rates while staying fast; configurable per call.
DEFAULT_REALTIME_FACTOR = 6.0
_BYTES_PER_SECOND = _config.SAMPLE_RATE * _config.CHANNELS * 2


def _compile_helper(src: Path, out: Path) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    cc = os.environ.get("CC", "cc")
    subprocess.run(
        [cc, "-O2", "-rdynamic", "-o", str(out), str(src), "-ldl", "-lpthread"],
        check=True,
    )
    return str(out)


def _find_helper() -> str:
    """Locate the compiled helper, building it from bundled source if needed.

    The helper must be built with -rdynamic so its tmpfile() interposes the
    engine's. We never ship a prebuilt binary; we compile the bundled .c into
    the user cache on first use.
    """
    env = os.environ.get("SODA_HELPER")
    if env and os.path.exists(env):
        return env

    pkg_dir = Path(__file__).resolve().parent
    prebuilt = [
        pkg_dir / _HELPER_NAME,                          # already built here
        pkg_dir.parents[1] / "native" / _HELPER_NAME,    # dev checkout
    ]
    for c in prebuilt:
        if c.exists():
            return str(c)

    cache_bin = Path(
        os.environ.get("SODA_STT_HOME")
        or os.path.join(os.path.expanduser("~"), ".cache", "soda-stt")
    ) / "bin" / _HELPER_NAME
    if cache_bin.exists():
        return str(cache_bin)

    # Build from the bundled source (shipped as package data) or dev tree.
    for src in (pkg_dir / "soda_helper.c",
                pkg_dir.parents[1] / "native" / "soda_helper.c"):
        if src.exists():
            return _compile_helper(src, cache_bin)
    raise RuntimeError(
        "soda_helper source not found and no binary available; "
        "set SODA_HELPER to a compiled helper path."
    )


@dataclass
class Result:
    """One recognition result from the engine."""

    text: str
    is_final: bool
    hypotheses: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.text


def _iter_responses(stream) -> Iterator[pb.SodaResponse]:
    """Yield SodaResponse messages from the helper's length-prefixed stdout."""
    while True:
        header = stream.read(4)
        if len(header) < 4:
            return
        (length,) = struct.unpack("<I", header)
        payload = stream.read(length)
        if len(payload) < length:
            return
        yield pb.SodaResponse.FromString(payload)


class SodaRecognizer:
    """Transcribe audio with Chrome's on-device SODA engine.

    Example:
        rec = SodaRecognizer.for_locale("pt-BR")
        print(rec.transcribe("meeting.mp3"))
    """

    def __init__(
        self,
        language_pack_directory: str,
        *,
        libsoda_path: str | None = None,
        recognition_mode: int = _config.MODE_CAPTION,
        enable_formatting: bool = True,
        mask_offensive_words: bool = False,
        max_speaker_count: int = 0,
    ) -> None:
        self.language_pack_directory = str(language_pack_directory)
        self.libsoda_path = libsoda_path or str(ensure_engine())
        self._helper = _find_helper()
        self._config_bytes = _config.build_config(
            self.language_pack_directory,
            recognition_mode=recognition_mode,
            enable_formatting=enable_formatting,
            mask_offensive_words=mask_offensive_words,
            max_speaker_count=max_speaker_count,
        )

    @classmethod
    def for_locale(cls, locale: str = "pt-BR", **kwargs) -> "SodaRecognizer":
        """Build a recognizer, downloading engine + language pack if needed."""
        models = ensure_language_pack(locale)
        return cls(str(models), **kwargs)

    # -- low-level: feed raw PCM, get a stream of Results -------------------

    def stream_pcm(
        self,
        pcm_chunks: Iterable[bytes],
        *,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> Iterator[Result]:
        """Feed s16le mono 16 kHz PCM chunks; yield partial + final Results.

        realtime_factor paces the feed to that multiple of real time (6.0 =
        six times faster than playback). Pass None to feed as fast as possible;
        that is correct only for short clips or when the caller already paces
        the audio (e.g. a live microphone).
        """
        with tempfile.NamedTemporaryFile(suffix=".cfg", delete=False) as tf:
            tf.write(self._config_bytes)
            cfg_path = tf.name
        # argv[0] must carry the Chrome speech flags for the engine to run.
        argv0 = f"{self._helper} {_config.CHROME_SPEECH_FLAGS}"
        proc = subprocess.Popen(
            args=[argv0, self.libsoda_path, cfg_path],
            executable=self._helper,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert proc.stdin is not None and proc.stdout is not None

        def _feed() -> None:
            try:
                for chunk in pcm_chunks:
                    proc.stdin.write(chunk)
                    proc.stdin.flush()
                    if realtime_factor and realtime_factor > 0:
                        time.sleep(len(chunk) / _BYTES_PER_SECOND / realtime_factor)
            except BrokenPipeError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        feeder = threading.Thread(target=_feed, daemon=True)
        feeder.start()
        try:
            for resp in _iter_responses(proc.stdout):
                if resp.soda_type != pb.SodaResponse.RECOGNITION:
                    continue
                rr = resp.recognition_result
                if not rr.hypothesis:
                    continue
                yield Result(
                    text=rr.hypothesis[0],
                    is_final=(rr.result_type == pb.SodaRecognitionResult.FINAL),
                    hypotheses=list(rr.hypothesis),
                )
        finally:
            feeder.join(timeout=5)
            proc.wait()
            try:
                os.unlink(cfg_path)
            except OSError:
                pass

    # -- convenience wrappers ---------------------------------------------

    def stream(
        self,
        source: str,
        *,
        chunk_ms: int = 100,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> Iterator[Result]:
        """Transcribe a file/URL, yielding Results as they arrive."""
        return self.stream_pcm(
            _audio.stream_pcm(source, chunk_ms=chunk_ms),
            realtime_factor=realtime_factor,
        )

    def transcribe_pcm(
        self, pcm: bytes, *, realtime_factor: float | None = DEFAULT_REALTIME_FACTOR
    ) -> str:
        """Transcribe raw PCM, returning the concatenated final text."""
        # Split into chunks so pacing applies; one giant write defeats it.
        step = int(_BYTES_PER_SECOND * 0.1)
        chunks = [pcm[i:i + step] for i in range(0, len(pcm), step)]
        finals = [
            r.text
            for r in self.stream_pcm(chunks, realtime_factor=realtime_factor)
            if r.is_final
        ]
        return " ".join(finals).strip()

    def transcribe(
        self, source: str, *, realtime_factor: float | None = DEFAULT_REALTIME_FACTOR
    ) -> str:
        """Transcribe a file/URL, returning the concatenated final text."""
        finals = [
            r.text
            for r in self.stream(source, realtime_factor=realtime_factor)
            if r.is_final
        ]
        return " ".join(finals).strip()
