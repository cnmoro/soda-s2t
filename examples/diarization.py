"""Speaker diarization (experimental).

SODA tags each recognized word with a speaker label (Word.speaker). Enable label
detection by constructing the recognizer with max_speaker_count > 0.

Important: this uses a SINGLE paced session, not the fast parallel path. Speaker
numbering is only consistent within one session, so chunked/parallel transcription
would renumber speakers per chunk. Diarization is therefore slower than plain
transcription and quality is model-dependent (best with clear turns and little
overlap); on clean single-speaker audio everything is speaker 1.

Usage:
    python examples/diarization.py meeting.mp3 --max-speakers 4
"""

from __future__ import annotations

import argparse

from soda_stt import SodaRecognizer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="audio file or URL")
    ap.add_argument("-l", "--locale", default="pt-BR")
    ap.add_argument("--max-speakers", type=int, default=4)
    args = ap.parse_args()

    rec = SodaRecognizer.for_locale(args.locale, max_speaker_count=args.max_speakers)

    # Single session keeps speaker IDs consistent across the whole recording.
    current = None
    buf: list[str] = []

    def flush():
        if buf:
            print(f"[Speaker {current}] {' '.join(buf)}")

    for seg in rec.stream(args.source):
        if not seg.is_final:
            continue
        for w in seg.words:
            if w.speaker != current:
                flush()
                buf.clear()
                current = w.speaker
            buf.append(w.text)
    flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
