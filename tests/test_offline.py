"""The library must run inference without ever contacting Google.

Guard rails for the bundled-artifact path: resolution order, the no-network
guarantee, and end-to-end transcriptions with the sockets closed.
"""

import hashlib
import json
import math
import os
import shutil
import socket
import struct
import tempfile
import wave
from pathlib import Path

import pytest

from soda_stt import download

PKG_DIR = Path(download.__file__).resolve().parent
SPEECH_CLIP = Path(__file__).resolve().parent.parent / "testdata" / "brasil_180s.mp3"


def _needs_bundle():
    return pytest.mark.skipif(
        not download.bundle_info(),
        reason="no bundle staged (run: python scripts/bundle.py)",
    )


def _block_network(monkeypatch):
    def blocked(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("urllib.request.urlopen", blocked)


def _tone_wav(seconds: float = 2.0) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(
            b"".join(
                struct.pack(
                    "<h",
                    int(4000 * math.sin(2 * math.pi * (150 + 40 * i / 16000) * i / 16000)),
                )
                for i in range(int(16000 * seconds))
            )
        )
    return path


# -- bundle layout -----------------------------------------------------------


def test_bundle_manifest_matches_files():
    info = download.bundle_info()
    if not info:
        pytest.skip("no bundle staged (run: python scripts/bundle.py)")

    engine = download.bundled_engine()
    assert engine is not None and engine.is_file()
    record = info["engine"]
    assert hashlib.sha256(engine.read_bytes()).hexdigest() == record["sha256"]
    assert engine.stat().st_size == record["bytes"]

    packs = info["language_packs"]
    assert packs, "bundle carries no language pack"
    for locale, rec in packs.items():
        models = download.bundled_language_pack(locale)
        assert models is not None and models.is_dir()
        files = [p for p in models.rglob("*") if p.is_file()]
        assert len(files) == rec["files"]
        assert sum(p.stat().st_size for p in files) == rec["bytes"]


def test_bundle_manifest_is_valid_json():
    info = download.bundle_info()
    if not info:
        pytest.skip("no bundle staged (run: python scripts/bundle.py)")
    assert set(info) >= {"format", "language_packs"}
    assert info["format"] == 1
    assert json.loads(json.dumps(info)) == info


def test_bundled_helper_is_present():
    if not download.bundle_info():
        pytest.skip("no bundle staged (run: python scripts/bundle.py)")
    assert (PKG_DIR / "soda_helper").is_file(), "bundled helper missing"


# -- resolution order --------------------------------------------------------


def test_bundled_artifacts_win_without_network(monkeypatch, tmp_path):
    if not download.bundle_info():
        pytest.skip("no bundle staged (run: python scripts/bundle.py)")

    def boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("update service must not be contacted")

    monkeypatch.setattr(download, "_query", boom)
    monkeypatch.setenv("SODA_STT_HOME", str(tmp_path))  # empty cache

    assert download.ensure_engine() == download.bundled_engine()
    assert download.ensure_language_pack("pt-BR") == download.bundled_language_pack(
        "pt-BR"
    )


def test_cache_is_used_without_network_when_no_bundle(monkeypatch, tmp_path):
    def boom(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("update service must not be contacted")

    monkeypatch.setattr(download, "_query", boom)
    monkeypatch.setattr(download, "bundled_engine", lambda: None)
    monkeypatch.setattr(download, "bundled_language_pack", lambda locale: None)

    lib = tmp_path / "engine" / "9.9.9" / "SODAFiles" / "libsoda.so"
    lib.parent.mkdir(parents=True)
    lib.write_bytes(b"fake engine")
    models = tmp_path / "langpacks" / "pt-BR" / "9.9.9" / "SODAModels"
    models.mkdir(parents=True)
    (models / "metadata").write_bytes(b"fake pack")

    assert download.ensure_engine(tmp_path) == lib
    assert download.ensure_language_pack("pt-BR", tmp_path) == models


def test_newest_cached_version_is_preferred(monkeypatch, tmp_path):
    monkeypatch.setattr(download, "bundled_engine", lambda: None)

    for version in ("1.2.12", "1.2.5"):
        lib = tmp_path / "engine" / version / "SODAFiles" / "libsoda.so"
        lib.parent.mkdir(parents=True)
        lib.write_bytes(version.encode())

    assert download.ensure_engine(tmp_path).parent.parent.name == "1.2.12"


def test_helpful_error_when_nothing_local(monkeypatch, tmp_path):
    def boom(*args, **kwargs):  # noqa: ARG001
        raise OSError("network down")

    monkeypatch.setattr(download, "_query", boom)
    monkeypatch.setattr(download, "bundled_engine", lambda: None)

    with pytest.raises(RuntimeError, match="bundled or cached"):
        download.ensure_engine(tmp_path)


def test_unsupported_platform_fails_with_clear_error(monkeypatch, tmp_path):
    """A source install on the wrong platform must not dlopen or download."""
    import types

    monkeypatch.setattr(
        download, "platform", types.SimpleNamespace(machine=lambda: "aarch64")
    )
    monkeypatch.setattr(download, "sys", types.SimpleNamespace(platform="linux"))
    with pytest.raises(RuntimeError, match="glibc Linux x86-64"):
        download.ensure_engine(tmp_path)

    monkeypatch.setattr(
        download, "platform", types.SimpleNamespace(machine=lambda: "x86_64")
    )
    monkeypatch.setattr(download, "sys", types.SimpleNamespace(platform="darwin"))
    with pytest.raises(RuntimeError, match="glibc Linux x86-64"):
        download.ensure_language_pack("pt-BR", tmp_path)


# -- end to end, sockets closed ---------------------------------------------


@_needs_bundle()
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_tone_transcribes_with_network_blocked(monkeypatch):
    _block_network(monkeypatch)
    from soda_stt import SodaRecognizer

    path = _tone_wav()
    try:
        rec = SodaRecognizer.for_locale("pt-BR")
        assert isinstance(rec.transcribe(path, realtime_factor=0), str)
    finally:
        os.unlink(path)


@_needs_bundle()
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
@pytest.mark.skipif(not SPEECH_CLIP.exists(), reason="testdata/brasil_180s.mp3 missing")
def test_speech_transcribes_with_network_blocked(monkeypatch):
    _block_network(monkeypatch)
    from soda_stt import SodaRecognizer

    rec = SodaRecognizer.for_locale("pt-BR")
    text = rec.transcribe(str(SPEECH_CLIP))
    assert len(text) > 50
    assert text.lower().startswith("brasil")


# -- speed path: silence skipping + timestamp mapping -----------------------


def test_feed_plan_skips_silence_and_keeps_padding():
    from soda_stt import chunking as ck

    chunk = ck.Chunk(0, 0.0, 10.0)
    silences = [(2.0, 3.0), (5.0, 5.5)]
    plan = ck.feed_plan(chunk, silences, pad_s=0.15)
    # Speech before the first pause, the pause itself dropped (minus pad),
    # speech between pauses, second pause dropped, speech to the end.
    assert plan == [(0.0, 2.0), (3.0 - 0.15, 5.0), (5.5 - 0.15, 10.0)]
    fed = sum(b - a for a, b in plan)
    assert fed < 10.0  # the point: silent frames are not fed
    assert all(b > a for a, b in plan)


def test_feed_plan_keeps_long_pauses_for_the_endpointer():
    from soda_stt import chunking as ck

    chunk = ck.Chunk(0, 0.0, 10.0)
    silences = [(2.0, 3.0), (5.0, 8.0)]  # 1 s pause vs 3 s pause
    plan = ck.feed_plan(chunk, silences, pad_s=0.15, max_skip_s=2.0)
    # Short pause skipped; the long one is fed whole so SODA still cuts segments.
    assert plan == [(0.0, 2.0), (3.0 - 0.15, 10.0)]


def test_feed_plan_without_silence_is_a_contiguous_chunk():
    from soda_stt import chunking as ck

    chunk = ck.Chunk(3, 30.0, 45.0)
    assert ck.feed_plan(chunk, []) == [(30.0, 45.0)]


def test_map_time_reconstructs_the_original_timeline():
    from soda_stt.engine import _map_time

    # Two fed segments: [0..2000ms) at t=0, [4000..6000ms) at session 2000.
    tm = [(0, 4000), (2000, 9000)]
    assert _map_time(None, 123, offset_ms=7) == 130      # plain offset fallback
    assert _map_time(tm, 0) == 4000                      # segment start
    assert _map_time(tm, 1500) == 5500                   # inside segment 1
    assert _map_time(tm, 2000) == 9000                   # segment 2 start
    assert _map_time(tm, 3500) == 10500                  # inside segment 2
    assert _map_time(None, 500) == 500                   # no map: identity
