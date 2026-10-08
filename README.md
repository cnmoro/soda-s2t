# soda-stt

> **For education and testing purposes.** This project exists to study and
> exercise the on-device speech engine Chrome ships; see
> [Legal note](#legal-note) below.

Chrome's on-device (offline) speech-to-text engine — the one behind Live Caption
and ChromeOS dictation — as a Python library. Runs fully offline. First-class
support for Brazilian Portuguese (`pt-BR`).

The engine is Google's **SODA** (Speech On-Device API), shipped as `libsoda.so`.
This library can ship with the engine and language models **bundled inside the
package**, so inference never touches the network; when they are not bundled, it
downloads them once from Chrome's public component-update service and caches
them. Either way it drives the engine through a small native helper.

- [docs/MODEL.md](docs/MODEL.md) — how Google publishes the model, how it's
  downloaded, bundled, and integrated here.

## Requirements

- Linux x86-64 on glibc. `libsoda.so` is a glibc Linux x86-64 ELF, so the
  published wheel is tagged `manylinux_2_34_x86_64` (glibc ≥ 2.34: Ubuntu
  22.04+, Debian 12+, Fedora 36+). Older glibc distros build from the source
  distribution instead — `pip` does that automatically. macOS, Windows and
  other architectures are unsupported and get a clear error, not a crash.
- Python 3.12+
- `ffmpeg` on `PATH` (used to decode any audio/video input)
- A C compiler (`cc`) — only for a build made *without* a bundle; both
  published artifacts ship the compiled helper

## Install

```bash
pip install soda-stt      # or: uv add soda-stt
```

Two artifacts are published, both self-contained (engine, pt-BR pack and
helper included, ~92 MB each):

| artifact | pip uses it when |
|----------|------------------|
| `soda_stt-…-py3-none-manylinux_2_34_x86_64.whl` | the platform matches (glibc ≥ 2.34) — installed directly |
| `soda_stt-<version>.tar.gz` (source) | no wheel matches (older glibc) — **built during install**, same bundle inside |

### Building the artifacts yourself

```bash
uv run python scripts/bundle.py   # stage engine + pt-BR from artifacts/ into the package
scripts/build_release.sh          # manylinux wheel + sdist into dist/
pip install dist/*.whl
```

`scripts/bundle.py --pack LOCALE=PATH.crx3` stages further locales; an artifact
built *without* a bundle falls back to downloading components on first use.

## Use

```python
from soda_stt import SodaRecognizer

rec = SodaRecognizer.for_locale("pt-BR")   # bundled, else cached, else downloaded once

# Whole-file transcription (any ffmpeg-readable file or URL).
# Fast by default: splits on silence and transcribes chunks in parallel.
text = rec.transcribe("entrevista.mp3")
print(text)
```

On an 8-core desktop a 55-minute recording transcribes in about 86 seconds
(~38x real time), complete and correctly punctuated.

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
soda-stt download --locale pt-BR               # make engine + models available locally
soda-stt download --locale pt-BR --force       # ...and check the update service for newer ones
soda-stt transcribe entrevista.mp3             # plain text (fast parallel)
soda-stt transcribe entrevista.mp3 -f srt -o out.srt   # subtitles with timecodes
soda-stt transcribe entrevista.mp3 -f json     # segments + word timestamps + speakers
soda-stt transcribe call.wav --max-speakers 4  # experimental diarization
soda-stt transcribe long.mp3 --workers 4       # tune parallelism
soda-stt transcribe odd.aac --no-fast          # single-session paced streaming
```

## How it's fast, and the pacing knob

SODA assumes audio arrives at roughly real time: fed a whole file at once it
finalizes once and drops the rest. Its encoder also costs the same for silent
frames as for speech. Both shape the design:

- **Parallel path (default).** The audio is split at silences into ~28-second
  chunks that are transcribed concurrently. Each chunk is still fed at a bounded
  multiple of real time (`realtime_factor`, default `6`) so none of its content
  is dropped; the speed comes from running many chunks at once. Worker count
  defaults to half your cores — raising it too high makes the engine fall behind
  during processing bursts and lose words, so more workers is not always better.

- **Silent audio is never fed.** Inside a chunk, pauses ffmpeg flags (≥0.4 s
  below −30 dB) are dropped before the engine sees them and word timestamps are
  mapped back onto the original timeline (median error ~13 ms). Pauses longer
  than 1 s are kept: SODA's endpointer needs them to cut segments. Worth ~6% on
  the whole pipeline — and because there is less audio to process under
  contention, slightly *more* words come back, not fewer.

- **Single-session path** (`stream()`, or `transcribe(..., fast=False)`). One
  paced session, results strictly in order, with the CPU to itself — so it is
  fed faster (`realtime_factor`, default `8`). Best for live display and for
  inputs ffmpeg can't probe. A 60-minute file takes about 7½ minutes at the
  default pace.

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
added in `soda_stt/_config.py` (`LANGUAGE_PACK_IDS`). Locales that aren't
bundled or cached are fetched from the update service on first use; to bundle
one too, stage it with `scripts/bundle.py --pack <locale>=<crx3>` before
building the artifacts.

## Legal note

**This project is published for education and testing purposes.** It downloads,
bundles and runs Google's SODA engine and language models, which are Google's
property and carry their own terms. It is an interoperability / research tool
for the on-device speech engine you already receive with Chrome. Review Chrome's
and Google's terms before relying on it beyond education and testing.
