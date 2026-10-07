"""soda-stt: Chrome's on-device speech-to-text engine as a Python library.

Quick start:
    from soda_stt import SodaRecognizer
    rec = SodaRecognizer.for_locale("pt-BR")
    print(rec.transcribe("audio.mp3"))
"""

from ._config import MODE_CAPTION, MODE_IME, SODA_API_KEY
from .download import ensure_engine, ensure_language_pack
from .engine import Result, SodaRecognizer

__all__ = [
    "SodaRecognizer",
    "Result",
    "ensure_engine",
    "ensure_language_pack",
    "MODE_CAPTION",
    "MODE_IME",
    "SODA_API_KEY",
]

__version__ = "0.1.0"
