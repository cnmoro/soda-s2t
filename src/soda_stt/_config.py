"""Constants and config-message construction for the SODA engine.

Values are what Chrome itself uses to invoke the bundled on-device speech
engine; see docs/REVERSE_ENGINEERING.md for how they were derived.
"""

from __future__ import annotations

from . import soda_api_pb2 as pb

# The SODA library verifies that its caller is Chrome. One condition is that the
# API key's SHA-1 matches a digest embedded in libsoda.so; this is the value
# Chrome ships for that purpose (google_apis::GetSodaAPIKey()).
SODA_API_KEY = "ce04d119-129f-404e-b4fe-6b913fffb6cb"

# Another condition: these flags must appear in the process command line
# (argv[0]). They are the real switches Chrome's speech utility process runs
# with. The launcher places them in argv[0].
CHROME_SPEECH_FLAGS = (
    "--utility-sub-type=media.mojom.SpeechRecognitionService "
    "--service-sandbox-type=speech_recognition"
)

# Component-updater identifiers (CRX ids) for fetching the engine + models.
SODA_COMPONENT_ID = "icnkogojpkfjeajonkmlplionaamopkf"
LANGUAGE_PACK_IDS = {
    "pt-BR": "anfcoadblmjplmkgmahlkhgnngkhoben",
    "en-US": "lmcclrhogkmnmaeklogimcdgcolcmkjk",
}

# RecognitionMode: IME is tuned for short dictation, CAPTION for streaming a
# continuous audio feed. CAPTION is the better general default.
MODE_IME = pb.ExtendedSodaConfigMsg.IME
MODE_CAPTION = pb.ExtendedSodaConfigMsg.CAPTION

SAMPLE_RATE = 16000
CHANNELS = 1


def build_config(
    language_pack_directory: str,
    *,
    sample_rate: int = SAMPLE_RATE,
    channel_count: int = CHANNELS,
    recognition_mode: int = MODE_CAPTION,
    enable_formatting: bool = True,
    mask_offensive_words: bool = False,
    max_speaker_count: int = 0,
) -> bytes:
    """Serialize an ExtendedSodaConfigMsg for the given language pack."""
    cfg = pb.ExtendedSodaConfigMsg(
        channel_count=channel_count,
        sample_rate=sample_rate,
        api_key=SODA_API_KEY,
        language_pack_directory=language_pack_directory,
        recognition_mode=recognition_mode,
        enable_formatting=enable_formatting,
        mask_offensive_words=mask_offensive_words,
        simulate_realtime_testonly=False,
    )
    if max_speaker_count > 0:
        cfg.speaker_diarization_mode = (
            pb.ExtendedSodaConfigMsg.SPEAKER_LABEL_DETECTION
        )
        cfg.max_speaker_count = max_speaker_count
    return cfg.SerializeToString()
