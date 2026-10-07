"""Live microphone transcription.

Captures audio from the default input device with ffmpeg and streams it into
SODA in real time, printing partial results as you speak and final lines when a
phrase settles.

Because a microphone already produces audio in real time, we feed with
realtime_factor=None (no extra pacing).

Usage:
    python examples/microphone.py [--locale pt-BR]

Capture backend: tries PulseAudio, then ALSA. Override with --device / --format,
e.g.  --format alsa --device hw:0
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from soda_stt import SodaRecognizer
from soda_stt._config import CHANNELS, SAMPLE_RATE


def mic_chunks(fmt: str, device: str, chunk_ms: int = 100):
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", fmt, "-i", device,
        "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = int(SAMPLE_RATE * CHANNELS * 2 * chunk_ms / 1000)
    try:
        while True:
            chunk = proc.stdout.read(n)
            if not chunk:
                break
            yield chunk
    finally:
        proc.terminate()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-l", "--locale", default="pt-BR")
    ap.add_argument("--format", default="pulse", help="ffmpeg input format (pulse/alsa)")
    ap.add_argument("--device", default="default", help="ffmpeg input device")
    args = ap.parse_args()

    print(f"Loading {args.locale} model...", file=sys.stderr)
    rec = SodaRecognizer.for_locale(args.locale)
    print("Speak now (Ctrl-C to stop).\n", file=sys.stderr)

    try:
        # realtime_factor=None: the mic already arrives in real time.
        for r in rec.stream_pcm(
            mic_chunks(args.format, args.device), realtime_factor=None
        ):
            if r.is_final:
                print(f"\r{r.text}")
            else:
                print(f"\r… {r.text[-100:]}", end="", flush=True)
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
