# How soda-stt drives Chrome's SODA engine

This documents the reverse engineering behind the library: what the engine is,
where the files come from, the C ABI, and the "called by Chrome" gate that makes
the engine refuse to transcribe for a naive caller.

## The engine

Chrome's on-device speech recognition (Live Caption, ChromeOS dictation) is
Google's **SODA** — Speech On-Device API — shipped as a native library,
`libsoda.so` on Linux. Chrome does not bundle it in the browser binary; it
fetches it, and per-language model packs, through the **component updater**.

The open-source Chromium tree documents the integration, which is how the ABI
was recovered without guessing:

- `chrome/services/speech/soda/soda_async_impl.h` — the C ABI (structs + entry points)
- `chrome/services/speech/soda/soda_api.proto` — the config and event protobufs
- `chrome/services/speech/soda/soda_client_impl.cc` — how Chrome loads and calls it
- `chrome/browser/component_updater/soda_component_installer.cc` — the component's public key
- `components/soda/constants.{h,cc}` — the per-language pack ids

## Getting the files (no Chrome needed)

Components are served publicly by Google's Omaha update service. Each is a CRX3
archive (a header followed by a zip; `zipfile`/`unzip` read it directly).

- POST an Omaha v3.1 JSON request to
  `https://update.googleapis.com/service/update2/json`
  (the response has an anti-XSSI prefix like `)]}'` to strip).
- SODA library component id: `icnkogojpkfjeajonkmlplionaamopkf`
  (derived from its SubjectPublicKeyInfo SHA-256 via the CRX id algorithm).
- pt-BR language pack component id: `anfcoadblmjplmkgmahlkhgnngkhoben`.

`soda_stt/download.py` implements this. Extracted, you get
`SODAFiles/libsoda.so` and, for the pack, a `SODAModels/` directory of TFLite
models, FSTs, and configs.

## The C ABI

From `soda_async_impl.h`. Audio is 16 kHz mono signed-16-bit little-endian PCM.

```c
void* CreateExtendedSodaAsync(SerializedSodaConfig config);
void  ExtendedSodaStart(void* handle);
void  ExtendedAddAudio(void* handle, const char* buf, int len);
void  ExtendedSodaMarkDone(void* handle);
void  DeleteExtendedSodaAsync(void* handle);
```

`SerializedSodaConfig` carries a serialized `ExtendedSodaConfigMsg` protobuf and
a callback. The callback receives serialized `SodaResponse` protobufs
(`RECOGNITION`, `ENDPOINT`, `AUDIO_LEVEL`, `START`, `STOP`, `SHUTDOWN`, ...).
Recognition results come as growing `PARTIAL` hypotheses, committed as `FINAL`.

## The "called by Chrome" gate

A naive caller that satisfies the ABI gets only empty results and this log line:

```
incremental_result.cc: UNKNOWN: Result lattice is not set. SpeechError(-73542)
```

`CreateExtendedSodaAsync` runs a caller-verification routine and stores a
trusted flag; recognition stays dormant unless **all** of these hold:

1. **Module path** — a loaded module's path contains `SODAFiles/libsoda.so`
   (or `third_party/soda/resources/libsoda.so`). Natural when loaded by path.
2. **Command line** — `argv[0]` (the command line as one string) contains both
   `--utility-sub-type=media.mojom.SpeechRecognitionService` and
   `--service-sandbox-type=speech_recognition`. These are the real switches
   Chrome's sandboxed speech utility process runs with.
3. **Sandbox probe** — `tmpfile()` must **fail** (return NULL). In Chrome's
   speech utility sandbox, temp files can't be created; the engine uses that as
   a signal that it's running where it expects to.
4. **API key** — `SHA-1(api_key)` must equal a digest embedded in the binary
   (`1358f559…4dccfbdd`). Satisfied by the SODA key Chrome ships for this
   purpose, `ce04d119-129f-404e-b4fe-6b913fffb6cb`
   (`google_apis::GetSodaAPIKey()`).

These were located by disassembling `CreateExtendedSodaAsync` (it calls a
verifier doing `strstr` over module paths, a `tmpfile()` check, and an
SHA-1/`pcmpeqb` digest comparison) and confirmed with `gdb` and `strace`.

### How the library satisfies the gate, cleanly

`soda_stt` does not patch the binary. Instead:

- The native helper (`soda_helper.c`) defines its own `tmpfile()` returning
  NULL. Built as the main executable with `-rdynamic`, its symbol **interposes**
  the engine's `tmpfile@plt` — so the sandbox probe sees a failure, in this
  process only. (Condition 3.)
- Python launches the helper with `subprocess.Popen(args=[argv0], executable=…)`
  where `argv0` is the helper path plus the two flags, so the command line
  carries them. (Condition 2.)
- The library loads `libsoda.so` by its real path (condition 1) and sends the
  API key in the config (condition 4).

## Why pacing matters

SODA assumes audio arrives at ~real time. Fed a whole file at once, it processes
the start, finalizes at the first pause, and abandons the backlog. The helper
reads audio from stdin; the Python feeder paces writes to a configurable
multiple of real time (`realtime_factor`, default 6). Around 4–6× the transcript
converges to a stable, complete result on a typical desktop CPU.

## Word timestamps and speaker labels (undeclared proto field)

`SodaRecognitionResult.hypothesis_part[]` gives per-word data. Chromium's copy of
the proto declares only `text` (1) and `alignment_ms` (2), but scanning the raw
bytes `libsoda.so` emits revealed an **undeclared field 5** (varint) on every
part. Testing showed it is a **1-indexed speaker label**: constant (`1`) on
single-speaker audio and taking values `{0,1,…}` across speakers when
`SPEAKER_LABEL_DETECTION` is set. `soda_api.proto` here adds it back as
`speaker_label = 5`. Combined with `alignment_ms` (offset from the result's
`timing_metrics.audio_start_time_usec`) this yields word-level timestamps and
diarization. Diarization accuracy is model-dependent and modest; the labels are
only consistent within one engine session.

## Fast parallel transcription

Because the engine finalizes once per bulk-fed stream, throughput of a single
paced session is bounded (~6× real time). Measured behaviour: a silence-bounded
clip up to ~30 s transcribes essentially completely, and the engine runs about
8× real time per stream. So the library splits long audio at silences (ffmpeg
`silencedetect`, one pass that also yields the PCM) into ≤28 s chunks and
transcribes them concurrently, each still paced for completeness, then stitches
the segments with corrected timestamps. This reaches ~37× real time on 8 cores.
Over-parallelising hurts: when the paced processing bursts collide the engine
falls behind its real-time assumption and drops words, so the default worker
count is half the cores.

## Architecture

```
Python (SodaRecognizer)
  ├─ download.py       resolve engine + model packs: bundled → cache → Omaha/CRX3
  ├─ audio.py          ffmpeg -> 16 kHz mono s16le PCM (file/URL/stream)
  ├─ _config.py        build ExtendedSodaConfigMsg, hold key + flags
  └─ engine.py         spawn helper, pace stdin, parse SodaResponse stream
         │  argv0 = "<helper> --utility-sub-type=… --service-sandbox-type=…"
         ▼
  native/soda_helper.c  interpose tmpfile(); dlopen libsoda; stream audio;
                        emit length-prefixed SodaResponse protobufs on stdout
         ▼
  libsoda.so (SODA)     on-device recognition
```
