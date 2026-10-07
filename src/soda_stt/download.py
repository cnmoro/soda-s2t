"""Fetch the SODA engine and language packs from Chrome's component updater.

No Chrome installation is required: the components are served publicly by
Google's Omaha update service and are plain CRX3 archives (a signed-zip).
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

from ._config import LANGUAGE_PACK_IDS, SODA_COMPONENT_ID

OMAHA_URL = "https://update.googleapis.com/service/update2/json"
# A recent Chrome version string; the service keys responses off this.
PRODVERSION = "141.0.7390.54"


def _default_root() -> Path:
    base = os.environ.get("SODA_STT_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache", "soda-stt"
    )
    return Path(base)


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


def ensure_engine(root: Path | None = None, *, force: bool = False) -> Path:
    """Download+extract the SODA library. Returns the path to libsoda.so."""
    root = root or _default_root()
    info = _query(SODA_COMPONENT_ID)
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
    """Download+extract a language pack. Returns its SODAModels directory."""
    root = root or _default_root()
    if locale not in LANGUAGE_PACK_IDS:
        raise ValueError(
            f"unknown locale {locale!r}; known: {sorted(LANGUAGE_PACK_IDS)}"
        )
    info = _query(LANGUAGE_PACK_IDS[locale])
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
