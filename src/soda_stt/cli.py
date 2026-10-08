"""Command-line interface: python -m soda_stt ... (or the `soda-stt` command)."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .download import ensure_engine, ensure_language_pack
from .engine import Result, SodaRecognizer


def _fmt_ts(ms: int) -> str:
    s, ms = divmod(int(ms), 1000)
    h, s = divmod(s, 60 * 60)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _emit_srt(segs: list[Result]) -> str:
    lines = []
    for i, seg in enumerate(segs, 1):
        start = seg.words[0].start_ms if seg.words else seg.start_ms
        last_word = seg.words[-1].start_ms if seg.words else seg.start_ms
        # End 2s after the last word, but never past the next cue's start.
        end = last_word + 2000
        if i < len(segs):
            nxt = segs[i]
            nxt_start = nxt.words[0].start_ms if nxt.words else nxt.start_ms
            end = min(end, max(nxt_start - 1, start + 1))
        spk = f"[S{seg.words[0].speaker}] " if seg.words else ""
        lines.append(f"{i}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{spk}{seg.text.strip()}\n")
    return "\n".join(lines)


def _emit_json(segs: list[Result]) -> str:
    out = [
        {
            "start_ms": seg.start_ms,
            "text": seg.text,
            "words": [
                {"text": w.text, "start_ms": w.start_ms, "speaker": w.speaker}
                for w in seg.words
            ],
        }
        for seg in segs
    ]
    return json.dumps(out, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soda-stt",
        description="On-device speech-to-text with Chrome's SODA engine.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tr = sub.add_parser("transcribe", help="transcribe an audio file or URL")
    p_tr.add_argument("source", help="audio file path or URL (any ffmpeg input)")
    p_tr.add_argument("-l", "--locale", default="pt-BR", help="language (default pt-BR)")
    p_tr.add_argument(
        "-f", "--format", choices=["text", "json", "srt"], default="text",
        help="output format (default text)",
    )
    p_tr.add_argument(
        "-o", "--output", help="write to this file instead of stdout",
    )
    p_tr.add_argument(
        "--workers", type=int, default=None, help="parallel workers (default: cores/2)",
    )
    p_tr.add_argument(
        "--max-speakers", type=int, default=0,
        help="enable speaker diarization with up to N speakers (experimental)",
    )
    p_tr.add_argument(
        "--no-fast", action="store_true",
        help="use single-session paced streaming instead of parallel chunking",
    )
    p_tr.add_argument(
        "--realtime-factor", type=float, default=None,
        help="feed pace as a multiple of real time (default: 6 parallel, 8 single-session)",
    )

    p_dl = sub.add_parser(
        "download", help="make sure the engine and a language pack are available locally"
    )
    p_dl.add_argument("-l", "--locale", default="pt-BR")
    p_dl.add_argument(
        "--force", action="store_true",
        help="check the update service even when a bundled or cached copy exists",
    )

    args = parser.parse_args(argv)

    if args.cmd == "download":
        print("Resolving SODA engine...", file=sys.stderr)
        print(f"  engine: {ensure_engine(force=args.force)}", file=sys.stderr)
        print(f"Resolving {args.locale} language pack...", file=sys.stderr)
        print(f"  models: {ensure_language_pack(args.locale, force=args.force)}",
              file=sys.stderr)
        return 0

    if args.cmd == "transcribe":
        rec = SodaRecognizer.for_locale(args.locale, max_speaker_count=args.max_speakers)

        # None → each path's own default (6x parallel, 8x single session);
        # passing None to the engine itself would mean "no pacing at all".
        if args.no_fast:
            kwargs = (
                {} if args.realtime_factor is None
                else {"realtime_factor": args.realtime_factor}
            )
            segs = [r for r in rec.stream(args.source, **kwargs) if r.is_final]
        else:
            kwargs = {"max_workers": args.workers}
            if args.realtime_factor is not None:
                kwargs["realtime_factor"] = args.realtime_factor
            segs = rec.transcribe_detailed(args.source, **kwargs)

        if args.format == "text":
            out = " ".join(s.text for s in segs).strip()
        elif args.format == "srt":
            out = _emit_srt(segs)
        else:
            out = _emit_json(segs)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out + "\n")
            print(f"wrote {args.output}", file=sys.stderr)
        else:
            print(out)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
