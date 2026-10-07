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
from . import chunking as _chunking
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
class Word:
    """A single recognized word with timing and speaker label."""

    text: str
    start_ms: int           # start time within the audio, in milliseconds
    speaker: int = 1        # 1-indexed speaker label (SODA default is 1)

    def __str__(self) -> str:  # pragma: no cover
        return self.text


@dataclass
class Result:
    """One recognition result from the engine."""

    text: str
    is_final: bool
    hypotheses: list[str] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    start_ms: int = 0       # segment start time within the audio, in ms

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.text


def _extract_words(rr: pb.SodaRecognitionResult, *, offset_ms: int = 0) -> list[Word]:
    """Build Word list from a recognition result's hypothesis parts.

    alignment_ms is relative to the result's audio_start_time_usec; offset_ms
    shifts everything into a global timeline (used when stitching chunks).
    """
    base_ms = rr.timing_metrics.audio_start_time_usec // 1000 + offset_ms
    words: list[Word] = []
    for part in rr.hypothesis_part:
        if not part.text:
            continue
        # text[0] is the (formatted) token; a second entry is the raw form.
        words.append(
            Word(
                text=part.text[0],
                start_ms=base_ms + part.alignment_ms,
                speaker=part.speaker_label or 1,
            )
        )
    return words


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
        offset_ms: int = 0,
    ) -> Iterator[Result]:
        """Feed s16le mono 16 kHz PCM chunks; yield partial + final Results.

        realtime_factor paces the feed to that multiple of real time (6.0 =
        six times faster than playback). Pass None to feed as fast as possible;
        that is correct only for short clips or when the caller already paces
        the audio (e.g. a live microphone).

        offset_ms shifts reported word/segment timestamps into a global
        timeline (used when stitching parallel chunks).
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
                is_final = rr.result_type == pb.SodaRecognitionResult.FINAL
                # Word-level data is only meaningful on final results.
                words = _extract_words(rr, offset_ms=offset_ms) if is_final else []
                yield Result(
                    text=rr.hypothesis[0],
                    is_final=is_final,
                    hypotheses=list(rr.hypothesis),
                    words=words,
                    start_ms=rr.timing_metrics.audio_start_time_usec // 1000 + offset_ms,
                )
        finally:
            feeder.join(timeout=5)
            proc.wait()
            try:
                os.unlink(cfg_path)
            except OSError:
                pass

    # -- single-blob helper (used by the parallel path) -------------------

    def _transcribe_blob(
        self, pcm: bytes, *, offset_ms: int = 0,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> list[Result]:
        """Transcribe one PCM blob; return its final Results.

        Used for silence-bounded chunks. The feed is paced (realtime_factor) so
        the engine captures every utterance in the chunk, not just the first;
        parallelism across chunks provides the speed. Blocks until finished.
        """
        step = int(_BYTES_PER_SECOND * 0.1)
        chunks = (pcm[i:i + step] for i in range(0, len(pcm), step))
        return [
            r for r in self.stream_pcm(
                chunks, realtime_factor=realtime_factor, offset_ms=offset_ms
            ) if r.is_final
        ]

    # -- fast parallel transcription --------------------------------------

    def transcribe_detailed(
        self,
        source: str,
        *,
        max_workers: int | None = None,
        max_chunk_s: float = 28.0,
        noise_db: float = -30.0,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> list[Result]:
        """Transcribe a file/URL fast, returning ordered final segments.

        Splits the audio at silences into <= max_chunk_s chunks and transcribes
        them in parallel, stitching results into one global timeline. Each
        Result carries text, word timestamps and speaker labels.

        Each chunk's feed is paced (realtime_factor) for completeness; the speed
        comes from running many chunks at once. Paced workers mostly wait, so the
        default worker count oversubscribes the CPU on purpose.
        """
        from concurrent.futures import ThreadPoolExecutor

        # Decode once to a temp PCM file (not memory); each worker reads only its
        # own byte range, so RAM stays independent of the recording's length.
        fd, pcm_path = tempfile.mkstemp(suffix=".pcm")
        os.close(fd)
        try:
            duration_s, silences = _chunking.decode_to_file(
                source, pcm_path, noise_db=noise_db
            )
            plan = _chunking.plan_chunks(duration_s, silences, max_chunk_s=max_chunk_s)
            if max_workers is None:
                # Paced workers mostly wait, but during each chunk's processing
                # bursts too many at once saturate the CPU and make the engine
                # fall behind its real-time assumption (dropping content). Half
                # the cores keeps bursts from colliding while running many at once.
                max_workers = max(2, min(8, (os.cpu_count() or 4) // 2))

            def work(chunk: _chunking.Chunk) -> tuple[int, list[Result]]:
                blob = _chunking.read_chunk(pcm_path, chunk)
                if not blob:
                    return chunk.index, []
                return chunk.index, self._transcribe_blob(
                    blob, offset_ms=chunk.start_ms, realtime_factor=realtime_factor
                )

            if len(plan) == 1 or max_workers == 1:
                results = [work(c) for c in plan]
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    results = list(pool.map(work, plan))
        finally:
            try:
                os.unlink(pcm_path)
            except OSError:
                pass

        ordered: list[Result] = []
        for _, segs in sorted(results, key=lambda t: t[0]):
            ordered.extend(segs)
        return ordered

    # -- convenience wrappers ---------------------------------------------

    def stream(
        self,
        source: str,
        *,
        chunk_ms: int = 100,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> Iterator[Result]:
        """Transcribe a file/URL, yielding Results in order as they arrive.

        Uses paced streaming (one engine session). Good for live display; for
        the fastest whole-file transcription use transcribe()/transcribe_detailed().
        """
        return self.stream_pcm(
            _audio.stream_pcm(source, chunk_ms=chunk_ms),
            realtime_factor=realtime_factor,
        )

    def transcribe_pcm(
        self, pcm: bytes, *, realtime_factor: float | None = DEFAULT_REALTIME_FACTOR
    ) -> str:
        """Transcribe raw PCM, returning the concatenated final text."""
        step = int(_BYTES_PER_SECOND * 0.1)
        chunks = [pcm[i:i + step] for i in range(0, len(pcm), step)]
        finals = [
            r.text
            for r in self.stream_pcm(chunks, realtime_factor=realtime_factor)
            if r.is_final
        ]
        return " ".join(finals).strip()

    def transcribe(
        self,
        source: str,
        *,
        fast: bool = True,
        max_workers: int | None = None,
        realtime_factor: float | None = DEFAULT_REALTIME_FACTOR,
    ) -> str:
        """Transcribe a file/URL, returning the full text.

        By default uses the fast parallel (silence-chunked) path. Set fast=False
        to use single-session paced streaming instead (e.g. for inputs ffmpeg
        cannot seek/duration-probe, or to avoid chunk boundaries entirely).
        """
        if fast:
            segs = self.transcribe_detailed(source, max_workers=max_workers)
            return " ".join(s.text for s in segs).strip()
        finals = [
            r.text
            for r in self.stream(source, realtime_factor=realtime_factor)
            if r.is_final
        ]
        return " ".join(finals).strip()
