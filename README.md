# soda-stt

Chrome's on-device (offline) speech-to-text engine — the one behind Live Caption
and ChromeOS dictation — as a Python library. Runs fully offline after a
one-time model download. No Chrome installation or network needed at inference
time. First-class support for Brazilian Portuguese (`pt-BR`).

The engine is Google's **SODA** (Speech On-Device API), shipped as `libsoda.so`.
This library downloads the engine and language models straight from Chrome's
public component-update service, then drives the engine through a small native
helper. See [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) for how
it works and how it was figured out.

## Requirements

- Linux x86-64 (the published SODA binary's platform)
- Python 3.12+
- `ffmpeg` on `PATH` (used to decode any audio/video input)
- A C compiler (`cc`) available once, to build the bundled helper on first use

## Install

```bash
pip install soda-stt      # or: uv add soda-stt
```

## Use

```python
from soda_stt import SodaRecognizer

rec = SodaRecognizer.for_locale("pt-BR")   # downloads engine + models once

# Whole-file transcription (any ffmpeg-readable file or URL):
text = rec.transcribe("entrevista.mp3")
print(text)

# Streaming results as they arrive:
for r in rec.stream("entrevista.mp3"):
    print("FINAL" if r.is_final else "partial", r.text)
```

Raw PCM (16 kHz, mono, s16le) if you already have samples:

```python
text = rec.transcribe_pcm(pcm_bytes)
```

### Command line

```bash
soda-stt download --locale pt-BR          # pre-fetch engine + models
soda-stt transcribe entrevista.mp3        # prints the transcript
soda-stt transcribe call.wav --partials   # show live partials on stderr
```

## Pacing (`realtime_factor`)

SODA expects audio at roughly real-time speed. If you dump a long file at once,
its endpointer finalizes once and drops the rest. The library therefore paces
the feed at a multiple of real time (default `6.0`, i.e. a 60-minute file takes
about 10 minutes). Raise it on a fast machine, lower it for maximum accuracy:

```python
rec.transcribe("long.mp3", realtime_factor=8)   # faster
rec.transcribe("hard.mp3", realtime_factor=4)   # more accurate
rec.transcribe("short.wav", realtime_factor=0)  # no pacing (short clips only)
```

For a live microphone you already produce audio in real time, so pass
`realtime_factor=None` to `stream_pcm` and feed chunks as they arrive.

## Languages

`pt-BR` and `en-US` are wired up by CRX id. Other locales SODA supports can be
added in `soda_stt/_config.py` (`LANGUAGE_PACK_IDS`).

## Legal note

This project downloads and runs Google's SODA engine and language models, which
are Google's property and carry their own terms. It is an interoperability /
research tool for running the on-device engine you already receive with Chrome.
Review Chrome's and Google's terms before relying on it beyond that.
