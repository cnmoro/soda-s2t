# The SODA model: how Google ships it and how this project gets it

This explains where the on-device speech model comes from, the exact mechanism
Google uses to publish and deliver it, and how `soda-stt` fetches, caches, and
feeds it to the engine. For the engine ABI and the "called by Chrome" gate, see
[REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

## What the "model" actually is

SODA (Speech On-Device API) is split into two independently-versioned pieces:

1. **The engine** — `libsoda.so`, a single native library containing the
   inference runtime (TensorFlow Lite with the XNNPACK delegate, FST/WFST
   machinery, the endpointer, text normalization, etc.). It is language-neutral.
2. **A language pack** — a `SODAModels/` directory of weights and data files for
   one locale (e.g. `pt-BR`). The engine loads these at runtime; the path is
   passed to it as `language_pack_directory`.

Keeping them separate is why one ~120 MB engine serves every language and you
only download the ~70 MB pack for the locale(s) you want.

### What's inside a language pack

From the pt-BR pack (`version 1.3071.0`), the notable files:

| File | Size | Role |
|------|------|------|
| `endtoendmodel/medium-encoder.tflite` | ~35 MB | RNN-T **encoder** (acoustic → embeddings) |
| `endtoendmodel/medium-decoder.tflite` | ~6 MB | RNN-T **prediction/decoder** network |
| `endtoendmodel/medium-joint_posterior.tflite` | ~3 MB | RNN-T **joint** network (posterior) |
| `endtoendmodel/medium-joint_prior.tflite` | ~3 MB | RNN-T joint (prior) |
| `endtoendmodel/medium.wpm.portable` | ~160 KB | wordpiece / subword vocabulary |
| `endtoendmodel/medium.syms.compact` | ~21 KB | output symbol table |
| `denorm/lm.pruned.sorted.fst` | ~11 MB | language-model **FST** (rescoring) |
| `denorm/transducer.pruned.fst` | ~2 MB | inverse-text-normalization transducer |
| `denorm/embedded_class_denorm.mfar` | ~320 KB | class-based denormalization (numbers, dates…) |
| `SODA_punctuation_model.tflite` | ~2.3 MB | punctuation / casing model |
| `denorm/PUNCTUATION_LSTM.model.int8.tflite` | ~270 KB | punctuation LSTM (quantized) |
| `langid/ONDEVICE_langid.tflite` | ~2.5 MB | spoken-language identification |
| `acousticmodel/*.endpointer_portable_lstm_model` | ~120–470 KB | endpointers (detect speech start/end) |
| `configs/ONDEVICE_MEDIUM_CONTINUOUS.config` | ~12 KB | pipeline definition (CAPTION mode) |
| `configs/ONDEVICE_MEDIUM_SHORT.config` | ~12 KB | pipeline definition (IME mode) |
| `context_prebuilt/*.fst`, `denorm/*.mfar` | — | context biasing, normalization resources |
| `metadata` | ~3 KB | locale, version, and per-file hashes |

So the recognizer is a **medium-sized RNN-T** (transducer: encoder + prediction +
joint) decoding against a wordpiece vocabulary, with a separate LM FST, an
inverse-text-normalization stage (spoken → written form, e.g. "oito milhões" →
numeric), a punctuation/casing model, endpointers, and a language-id model.
`enable_formatting` in the config turns the normalization + punctuation stages on.

## How Google publishes it: the Component Updater

Chrome does not bundle these files in the browser; it downloads them through the
**Component Updater**, the same background service that delivers the certificate
revocation list, Widevine, etc. The service speaks the **Omaha v3.1** protocol,
and the files are **CRX3** packages. Everything is public — no Chrome, login, or
API key is needed to fetch them.

### Component identity

Each component is identified by a 32-character **CRX id** derived from the
publisher's RSA public key: take SHA-256 of the SubjectPublicKeyInfo, keep the
first 16 bytes, and map each hex nibble `0..f` to the letters `a..p`.

- SODA engine: `icnkogojpkfjeajonkmlplionaamopkf`
  (from the key SHA-256 `82dae6e9fa59409e…`, see Chromium's
  `soda_component_installer.cc`).
- pt-BR language pack: `anfcoadblmjplmkgmahlkhgnngkhoben`
  (per-language keys live in `components/soda/constants.cc`).

### The update check

A JSON POST to

```
https://update.googleapis.com/service/update2/json
```

asks "what is the current version of component X for this platform?". Request
shape (abridged):

```json
{"request": {"@os": "linux", "@updater": "chrome", "acceptformat": "crx3",
  "arch": "x86_64", "prodversion": "141.0.7390.54", "protocol": "3.1",
  "os": {"arch": "x86_64", "platform": "Linux"},
  "app": [{"appid": "icnkogojpkfjeajonkmlplionaamopkf",
           "version": "0.0.0.0", "updatecheck": {}}]}}
```

The response is prefixed with an anti-XSSI guard (`)]}'`) that must be stripped,
then parsed. It gives the current version, one or more CDN URLs, the package file
name, its size, and a SHA-256:

```json
{"response": {"app": [{"updatecheck": {"status": "ok",
  "urls": {"url": [{"codebase": "https://edgedl.me.gvt1.com/edgedl/release2/chrome_component/<hash>_1.3071.0/"}]},
  "manifest": {"version": "1.3071.0", "packages": {"package": [
    {"name": "anfcoadblmjplmkgmahlkhgnngkhoben_1.3071.0_all_<hash>.crx3",
     "size": 71507797,
     "hash_sha256": "e87c00c0…"}]}}}}]}}
```

`targetversionprefix` can be added to the `updatecheck` to request a specific
version line (e.g. `"1.2.0"`), which is how older engine builds can still be
pulled.

### The package format (CRX3)

The file at `<codebase><name>` is a **CRX3**: a small header (magic `Cr24`, a
protobuf of signatures/public key) followed by a standard ZIP. Because the ZIP's
central directory is at the end, standard unzip tools read the embedded archive
directly (ignoring the header bytes). Inside is `manifest.json` (name + version),
the payload (`SODAFiles/libsoda.so`, or the `SODAModels/` tree), and a
`_metadata/verified_contents.json`. Delivery CDNs: `edgedl.me.gvt1.com`,
`dl.google.com`, `www.google.com/dl`.

Integrity: the update response's `hash_sha256` is verified against the downloaded
bytes before extraction. (Chrome additionally verifies the CRX3's cryptographic
signature with the pinned publisher key; this project verifies the SHA-256, which
the update service delivers over HTTPS.)

## How this project integrates it

All of the above lives in [`src/soda_stt/download.py`](../src/soda_stt/download.py).

### Fetch + cache

- `ensure_engine()` → does an update check for the engine component, downloads
  the CRX3 if not already cached, verifies its SHA-256, extracts it, and returns
  the path to `libsoda.so`.
- `ensure_language_pack(locale)` → the same for a language pack, returning the
  `SODAModels/` directory.

Both are idempotent: if the current version is already extracted they return
immediately; pass `force=True` to refresh. Downloaded CRX3s are kept in a cache
so re-extraction is free.

### Cache layout

Root is `~/.cache/soda-stt` (override with `SODA_STT_HOME`):

```
~/.cache/soda-stt/
  cache/                         # downloaded .crx3 files (reused across versions)
  engine/<version>/SODAFiles/libsoda.so
  langpacks/<locale>/<version>/SODAModels/
  bin/soda_helper                # the native helper, compiled on first use
```

Versioning by directory means a newer engine or pack installs side-by-side; the
library resolves to the current version reported by the update service.

### Wiring it to the engine

`SodaRecognizer.for_locale("pt-BR")` calls `ensure_engine()` and
`ensure_language_pack("pt-BR")`, then builds an `ExtendedSodaConfigMsg` whose
`language_pack_directory` points at the resolved `SODAModels/` path (see
[`_config.py`](../src/soda_stt/_config.py)). The engine loads the models from
there at `CreateExtendedSodaAsync` time. Nothing else in the pipeline needs to
know which version is installed.

Adding a locale is just one line: its CRX id in `LANGUAGE_PACK_IDS`
(`_config.py`). The id comes from that language's public-key hash in Chromium's
`components/soda/constants.cc`.

## Legal note

The engine and language packs are Google's property and carry Google's terms.
`soda-stt` fetches and runs the same on-device components Chrome already
downloads to your machine; it is an interoperability/research tool, not a
redistribution of Google's models. Review Chrome's and Google's terms before
relying on it beyond that.
