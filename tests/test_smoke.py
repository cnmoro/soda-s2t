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


def test_plan_chunks_breaks_at_silence_and_caps_length():
    from soda_stt import chunking as ck
    # 100s audio, silences around 25s, 50s, 75s.
    silences = [(24.5, 25.5), (49.0, 50.0), (74.0, 75.0)]
    plan = ck.plan_chunks(100.0, silences, max_chunk_s=28.0, min_chunk_s=5.0)
    # All chunks within the cap (with a tiny epsilon).
    assert all(c.end_s - c.start_s <= 28.0 + 0.6 for c in plan)
    # Chunks are contiguous and cover the whole duration.
    assert plan[0].start_s == 0.0
    assert abs(plan[-1].end_s - 100.0) < 1e-6
    for a, b in zip(plan, plan[1:]):
        assert abs(a.end_s - b.start_s) < 1e-6
    # A break should land at a silence midpoint when one is in range.
    cuts = {round(c.start_s, 1) for c in plan[1:]}
    assert 25.0 in cuts  # midpoint of (24.5, 25.5)


def test_plan_chunks_hard_splits_without_silence():
    from soda_stt import chunking as ck
    plan = ck.plan_chunks(90.0, [], max_chunk_s=28.0)
    assert all(c.end_s - c.start_s <= 28.0 + 1e-6 for c in plan)
    assert len(plan) >= 3


def test_speaker_label_field_present_in_proto():
    from soda_stt import soda_api_pb2 as pb
    names = [f.name for f in pb.HypothesisPart.DESCRIPTOR.fields]
    assert "speaker_label" in names
