"""Smoke tests. Network + ffmpeg required; skipped if unavailable."""
import shutil
import wave
import struct
import math
import os
import tempfile

import pytest

from soda_stt import _config, soda_api_pb2 as pb


def test_config_roundtrips():
    raw = _config.build_config("/tmp/models", sample_rate=16000)
    msg = pb.ExtendedSodaConfigMsg.FromString(raw)
    assert msg.sample_rate == 16000
    assert msg.api_key == _config.SODA_API_KEY
    assert msg.language_pack_directory == "/tmp/models"


def test_api_key_matches_embedded_digest():
    import hashlib
    # The engine checks SHA-1(api_key) against a constant; guard the value.
    digest = hashlib.sha1(_config.SODA_API_KEY.encode()).hexdigest()
    assert digest == "1358f5598953e0f596e3fbecf67643f14dccfbdd"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
@pytest.mark.skipif(
    os.environ.get("SODA_STT_ONLINE") != "1",
    reason="set SODA_STT_ONLINE=1 to run the end-to-end download+transcribe test",
)
def test_end_to_end_tone_runs():
    # A pure tone produces no words, but the pipeline must run and finalize.
    from soda_stt import SodaRecognizer
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000)))
            for i in range(16000 * 2)
        )
        w.writeframes(frames)
    rec = SodaRecognizer.for_locale("pt-BR")
    # Should return a string (likely empty) without raising.
    assert isinstance(rec.transcribe(path, realtime_factor=0), str)
