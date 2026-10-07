"""Command-line interface: python -m soda_stt ..."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .download import ensure_engine, ensure_language_pack
from .engine import DEFAULT_REALTIME_FACTOR, SodaRecognizer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soda_stt",
        description="On-device speech-to-text with Chrome's SODA engine.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tr = sub.add_parser("transcribe", help="transcribe an audio file or URL")
    p_tr.add_argument("source", help="audio file path or URL (any ffmpeg input)")
    p_tr.add_argument("-l", "--locale", default="pt-BR", help="language (default pt-BR)")
    p_tr.add_argument(
        "--realtime-factor", type=float, default=DEFAULT_REALTIME_FACTOR,
        help="feed pace as a multiple of real time (0 = as fast as possible)",
    )
    p_tr.add_argument(
        "--partials", action="store_true", help="print partial results live to stderr",
    )

    p_dl = sub.add_parser("download", help="pre-fetch the engine and a language pack")
    p_dl.add_argument("-l", "--locale", default="pt-BR")

    args = parser.parse_args(argv)

    if args.cmd == "download":
        print("Fetching SODA engine...", file=sys.stderr)
        lib = ensure_engine()
        print(f"  engine: {lib}", file=sys.stderr)
        print(f"Fetching {args.locale} language pack...", file=sys.stderr)
        models = ensure_language_pack(args.locale)
        print(f"  models: {models}", file=sys.stderr)
        return 0

    if args.cmd == "transcribe":
        rec = SodaRecognizer.for_locale(args.locale)
        factor = args.realtime_factor or None
        if args.partials:
            finals = []
            for r in rec.stream(args.source, realtime_factor=factor):
                if r.is_final:
                    finals.append(r.text)
                else:
                    print(f"\r… {r.text[-100:]}", end="", file=sys.stderr, flush=True)
            print("", file=sys.stderr)
            print(" ".join(finals).strip())
        else:
            print(rec.transcribe(args.source, realtime_factor=factor))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
