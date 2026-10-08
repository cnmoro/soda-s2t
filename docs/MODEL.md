# The SODA model: how Google ships it and how this project gets it

This explains where the on-device speech model comes from, the exact mechanism
Google uses to publish and deliver it, and how `soda-stt` fetches, bundles,
caches, and feeds it to the engine. For the engine ABI and the "called by
Chrome" gate, see [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).

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

### Resolution order: offline first

`ensure_engine()` and `ensure_language_pack(locale)` walk three steps and only
reach the network on the last one:

1. **Bundled copy** — the artifacts staged inside the installed package at
   `src/soda_stt/_bundle/` (next section). Used in place, read-only, no cache
   directory involved.
2. **Local cache** — whatever an earlier download left under `SODA_STT_HOME`;
   the newest version directory wins.
3. **Component updater** — update check, CRX3 download, SHA-256 verification,
   extraction, exactly as described above.

So a wheel built from a bundle never opens a socket at inference time —
[`tests/test_offline.py`](../tests/test_offline.py) asserts that with
`socket.connect` and `urllib` patched to raise. Pass `force=True` (or run
`soda-stt download --force`) to skip steps 1–2 and look for a newer version.

Both functions stay idempotent, and downloaded CRX3s are kept in a cache so
re-extraction is free.

### Bundling the artifacts into the wheel

`uv run python scripts/bundle.py` stages the components into the package:

```
src/soda_stt/
  _bundle/
    bundle.json                  # versions, component ids, hashes, sizes
    SODAFiles/libsoda.so         # the engine
    <locale>/SODAModels/…        # one directory per staged locale (pt-BR)
  soda_helper                    # the native helper, compiled by the script
```

Its sources are the local CRX3s under `artifacts/crx/` (preferred, so the bytes
are exactly what Google published) or an already-extracted component tree — the
bundler itself never downloads. `--pack LOCALE=PATH.crx3` stages additional
locales, `--clean` removes the bundle, and `bundle.json` records a SHA-256 (plus
file count and total size for packs) so the staged tree can be verified later.

hatchling packages everything under `src/soda_stt/`, so

```bash
uv run python scripts/bundle.py && uv build
```

produces both a self-contained wheel and sdist (~92 MB compressed each, ~192 MB
installed). A build hook ([`hatch_build.py`](../hatch_build.py)) tags the wheel
`py3-none-<platform>` — the payload is a Linux x86-64 ELF, so the package is
never universal. The bundle is gitignored: the artifacts are the product, not
the git tree; the sdist pulls it back in with `force-include`.

### Publishing

`scripts/build_release.sh` runs the whole flow:

1. `scripts/bundle.py` — stage the components and compile the helper.
2. `uv build` — the sdist first, then a wheel built *from* it, so both carry
   the bundle.
3. `uvx --with patchelf auditwheel repair` — **PyPI rejects plain
   `linux_x86_64`**: its allowlist only takes `any`, Windows, macOS,
   `manylinux_*` and `musllinux_*`, so an upload would fail with HTTP 400.
   auditwheel reads the ELF symbol versions, computes the real glibc floor and
   retags — today `manylinux_2_34_x86_64`. The floor comes from our own
   `soda_helper` (built on glibc 2.39, references `GLIBC_2.34`); `libsoda.so`
   alone needs only `GLIBC_2.27`, so building the helper in a manylinux
   container would drop the floor to `manylinux_2_27_x86_64`.
4. `uvx twine check` — validates the metadata that becomes the PyPI page.

Both artifacts fit PyPI's 100 MB per-file limit with ~12 MB to spare. A Linux
x86-64 user the wheel misses (glibc older than the floor) falls back to the
sdist: pip builds it during install and the result carries the same bundle.
Anything else — macOS, Windows, other architectures — raises a clear error from
`_require_supported_platform()` instead of trying to load a foreign ELF.

### Cache layout

Root is `~/.cache/soda-stt` (override with `SODA_STT_HOME`). A bundled wheel
never creates it — it only exists when something was downloaded:

```
~/.cache/soda-stt/
  cache/                         # downloaded .crx3 files (reused across versions)
  engine/<version>/SODAFiles/libsoda.so
  langpacks/<locale>/<version>/SODAModels/
  bin/soda_helper                # the native helper, compiled on first use
```

Versioning by directory means a newer engine or pack installs side-by-side.
Local copies are picked newest-first; the update service only decides which
version to fetch when nothing is local yet.

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

## Note

The engine and language packs are Google's property and carry Google's terms.
`soda-stt` fetches and runs the same on-device components Chrome already
downloads to your machine; it is an interoperability/research tool for testing purposes.
