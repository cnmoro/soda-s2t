"""Resolve the SODA engine and language packs, downloading only if needed.

Resolution is offline-first: a bundled copy (shipped inside the package by
scripts/bundle.py) wins, then whatever a previous download left in the cache,
and only then the component updater. When artifacts are bundled the network is
never touched; see docs/MODEL.md.

The download path needs no Chrome installation: the components are served
publicly by Google's Omaha update service and are plain CRX3 archives
(a signed-zip).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import urllib.request
import zipfile
from pathlib import Path

from ._config import LANGUAGE_PACK_IDS, SODA_COMPONENT_ID

OMAHA_URL = "https://update.googleapis.com/service/update2/json"
# A recent Chrome version string; the service keys responses off this.
PRODVERSION = "141.0.7390.54"

_BUNDLE_NAME = "_bundle"
_BUNDLE_MANIFEST = "bundle.json"


def _default_root() -> Path:
    base = os.environ.get("SODA_STT_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache", "soda-stt"
    )
    return Path(base)


def _bundle_root() -> Path:
    return Path(__file__).resolve().parent / _BUNDLE_NAME


# -- bundled artifacts ------------------------------------------------------


def bundle_info() -> dict:
    """Manifest of the artifacts shipped inside the package ({} if none)."""
    path = _bundle_root() / _BUNDLE_MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bundled_engine() -> Path | None:
    """Path to the bundled libsoda.so, or None if the package has no bundle."""
    lib = _bundle_root() / "SODAFiles" / "libsoda.so"
    return lib if lib.is_file() else None


def bundled_language_pack(locale: str) -> Path | None:
    """Path to a bundled language pack's SODAModels directory, or None."""
    models = _bundle_root() / locale / "SODAModels"
    return models if models.is_dir() else None


# -- downloaded artifacts already on disk -----------------------------------


def _version_key(version: str) -> tuple[int, ...]:
    key = []
    for piece in version.split("."):
        key.append(int(piece) if piece.isdigit() else 0)
    return tuple(key)


def _newest(base: Path, required: tuple[str, ...]) -> Path | None:
    """Newest version directory under `base` containing every path in `required`."""
    if not base.is_dir():
        return None
    best: Path | None = None
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        if not all((entry / rel).exists() for rel in required):
            continue
        if best is None or _version_key(entry.name) > _version_key(best.name):
            best = entry
    return best


def cached_engine(root: Path | None = None) -> Path | None:
    """Newest previously downloaded engine, or None."""
    root = root or _default_root()
    entry = _newest(root / "engine", ("SODAFiles/libsoda.so",))
    return entry / "SODAFiles" / "libsoda.so" if entry else None


def cached_language_pack(locale: str, root: Path | None = None) -> Path | None:
    """Newest previously downloaded language pack, or None."""
    root = root or _default_root()
    entry = _newest(root / "langpacks" / locale, ("SODAModels",))
    return entry / "SODAModels" if entry else None


def _query(app_id: str) -> dict:
    req = {
        "request": {
            "@os": "linux", "@updater": "chrome", "acceptformat": "crx3",
            "arch": "x86_64", "prodversion": PRODVERSION, "protocol": "3.1",
            "updaterversion": PRODVERSION,
            "os": {"arch": "x86_64", "platform": "Linux", "version": "6.8.0"},
            "app": [{"appid": app_id, "version": "0.0.0.0", "updatecheck": {}}],
        }
    }
    data = json.dumps(req).encode()
    with urllib.request.urlopen(
        urllib.request.Request(data=data, url=OMAHA_URL,
                               headers={"Content-Type": "application/json"})
    ) as resp:
        body = resp.read().decode()
    # Responses are prefixed with an anti-XSSI guard like ")]}'".
    body = body[body.index("{"):]
    uc = json.loads(body)["response"]["app"][0]["updatecheck"]
    if uc.get("status") != "ok":
        raise RuntimeError(f"update service returned status {uc.get('status')!r}")
    pkg = uc["manifest"]["packages"]["package"][0]
    codebase = next(
        u["codebase"] for u in uc["urls"]["url"]
        if u["codebase"].startswith("https")
    )
    return {
        "version": uc["manifest"]["version"],
        "url": codebase + pkg["name"],
        "sha256": pkg["hash_sha256"],
    }


def _download_crx(url: str, sha256: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise RuntimeError(f"hash mismatch for {url}: {got} != {sha256}")
    dest.write_bytes(data)


def _extract_crx(crx: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # A CRX3 is a header followed by a zip; zipfile locates the central
    # directory at the end, so it reads the embedded archive directly.
    with zipfile.ZipFile(crx) as zf:
        zf.extractall(out_dir)


def _require_supported_platform() -> None:
    """The engine ships as a glibc Linux x86-64 ELF; fail loudly anywhere else.

    A source install can land anywhere, and without this the first use would
    either dlopen a foreign ELF or download components that cannot run here.
    """
    machine = platform.machine().lower()
    if sys.platform != "linux" or machine not in ("x86_64", "amd64"):
        raise RuntimeError(
            "soda-stt needs glibc Linux x86-64 (libsoda.so is a Linux x86-64 "
            f"ELF); this platform is {sys.platform}/{platform.machine()}."
        )


def ensure_engine(root: Path | None = None, *, force: bool = False) -> Path:
    """Return the path to libsoda.so, without hitting the network if possible.

    Order: bundled copy, then the local cache, then a component-updater
    download. `force=True` skips the local copies and checks for a newer build.
    """
    _require_supported_platform()
    root = root or _default_root()
    if not force:
        local = bundled_engine() or cached_engine(root)
        if local is not None:
            return local
    try:
        info = _query(SODA_COMPONENT_ID)
    except Exception as exc:
        local = bundled_engine() or cached_engine(root)
        if local is not None:
            return local
        raise RuntimeError(
            "no bundled or cached SODA engine, and the component update "
            "service is unreachable. Build a bundled wheel "
            "(uv run python scripts/bundle.py && uv build --wheel) or run `soda-stt download` "
            "on a machine with network access."
        ) from exc
    dest = root / "engine" / info["version"]
    lib = dest / "SODAFiles" / "libsoda.so"
    if lib.exists() and not force:
        return lib
    crx = root / "cache" / f"soda-{info['version']}.crx3"
    if not crx.exists() or force:
        _download_crx(info["url"], info["sha256"], crx)
    _extract_crx(crx, dest)
    if not lib.exists():
        raise RuntimeError(f"libsoda.so not found after extracting to {dest}")
    return lib


def ensure_language_pack(
    locale: str, root: Path | None = None, *, force: bool = False
) -> Path:
    """Return the SODAModels directory for `locale`, network only as needed.

    Same offline-first order as ensure_engine(): bundled copy, local cache,
    component-updater download.
    """
    _require_supported_platform()
    root = root or _default_root()
    if locale not in LANGUAGE_PACK_IDS:
        raise ValueError(
            f"unknown locale {locale!r}; known: {sorted(LANGUAGE_PACK_IDS)}"
        )
    if not force:
        local = bundled_language_pack(locale) or cached_language_pack(locale, root)
        if local is not None:
            return local
    try:
        info = _query(LANGUAGE_PACK_IDS[locale])
    except Exception as exc:
        local = bundled_language_pack(locale) or cached_language_pack(locale, root)
        if local is not None:
            return local
        raise RuntimeError(
            f"no bundled or cached {locale} language pack, and the component "
            "update service is unreachable. Build a bundled wheel "
            "(uv run python scripts/bundle.py && uv build --wheel) or run `soda-stt download` "
            "on a machine with network access."
        ) from exc
    dest = root / "langpacks" / locale / info["version"]
    models = dest / "SODAModels"
    if models.exists() and not force:
        return models
    crx = root / "cache" / f"{locale}-{info['version']}.crx3"
    if not crx.exists() or force:
        _download_crx(info["url"], info["sha256"], crx)
    _extract_crx(crx, dest)
    if not models.exists():
        raise RuntimeError(f"SODAModels not found after extracting to {dest}")
    return models
