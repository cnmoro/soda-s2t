# soda-stt

Chrome's on-device (offline) speech-to-text engine — the one behind Live Caption
and ChromeOS dictation — as a Python library. Runs fully offline after a
one-time model download. No Chrome installation or network needed at inference
time. First-class support for Brazilian Portuguese (`pt-BR`).

The engine is Google's **SODA** (Speech On-Device API), shipped as `libsoda.so`.
This library downloads the engine and language models straight from Chrome's
public component-update service, then drives the engine through a small native
helper.

- [docs/MODEL.md](docs/MODEL.md) — how Google publishes the model, how it's
  downloaded, and how it integrates here.
- [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) — the engine ABI,
  the "called by Chrome" gate, timestamps/diarization, and the fast path.

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

# Whole-file transcription (any ffmpeg-readable file or URL).
# Fast by default: splits on silence and transcribes chunks in parallel.
text = rec.transcribe("entrevista.mp3")
print(text)
```

On an 8-core desktop a 55-minute recording transcribes in about 90 seconds
(~37x real time), complete and correctly punctuated.

### Word timestamps and segments

```python
for seg in rec.transcribe_detailed("entrevista.mp3"):
    print(f"[{seg.start_ms/1000:.1f}s] {seg.text}")
    for w in seg.words:
        print(f"    {w.start_ms/1000:6.2f}s  {w.text}  (speaker {w.speaker})")
```

### Live streaming (in order, as it arrives)

```python
for r in rec.stream("entrevista.mp3"):
    print("FINAL" if r.is_final else "partial", r.text)
```

Raw PCM (16 kHz, mono, s16le) if you already have samples:

```python
text = rec.transcribe_pcm(pcm_bytes)
```

See [`examples/`](examples/) for a live **microphone** script and a
**diarization** script.

### Command line

```bash
soda-stt download --locale pt-BR               # pre-fetch engine + models
soda-stt transcribe entrevista.mp3             # plain text (fast parallel)
soda-stt transcribe entrevista.mp3 -f srt -o out.srt   # subtitles with timecodes
soda-stt transcribe entrevista.mp3 -f json     # segments + word timestamps + speakers
soda-stt transcribe call.wav --max-speakers 4  # experimental diarization
soda-stt transcribe long.mp3 --workers 4       # tune parallelism
soda-stt transcribe odd.aac --no-fast          # single-session paced streaming
```

## How it's fast, and the pacing knob

SODA assumes audio arrives at roughly real time: fed a whole file at once it
finalizes once and drops the rest. Two consequences:

- **Parallel path (default).** The audio is split at silences into ~28-second
  chunks that are transcribed concurrently. Each chunk is still fed at a bounded
  multiple of real time (`realtime_factor`, default `6`) so none of its content
  is dropped; the speed comes from running many chunks at once. Worker count
  defaults to half your cores — raising it too high makes the engine fall behind
  during processing bursts and lose words, so more workers is not always better.

- **Single-session path** (`stream()`, or `transcribe(..., fast=False)`). One
  paced session, results strictly in order. Best for live display and for inputs
  ffmpeg can't probe. A 60-minute file takes about 10 minutes at the default
  pace.

For a live microphone you already produce audio in real time, so pass
`realtime_factor=None` to `stream_pcm` and feed chunks as they arrive (see
`examples/microphone.py`).

## Speaker diarization (experimental)

The engine tags each word with a speaker label, exposed as `Word.speaker`
(1-indexed). Enable it with `SodaRecognizer.for_locale(..., max_speaker_count=N)`
and read labels from `transcribe_detailed()` or `stream()`. Speaker numbering is
only consistent within a single session, so use `stream()` (not the parallel
path) when you care about who-said-what across a whole recording. Quality is
model-dependent: clean, turn-taking audio works best; on single-speaker audio
everything is speaker 1.

## Languages

`pt-BR` and `en-US` are wired up by CRX id. Other locales SODA supports can be
added in `soda_stt/_config.py` (`LANGUAGE_PACK_IDS`).

## Legal note

This project downloads and runs Google's SODA engine and language models, which
are Google's property and carry their own terms. It is an interoperability /
research tool for running the on-device engine you already receive with Chrome.
Review Chrome's and Google's terms before relying on it beyond that.
