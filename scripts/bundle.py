#!/usr/bin/env python3
"""Stage the SODA engine and language packs into the package.

Everything copied here lands inside the wheel (uv/hatchling package everything
under `src/soda_stt/`), so an installed `soda-stt` runs without ever contacting
Google's update service. Sources are the local CRX3 files or extracted trees
under `artifacts/`; nothing is downloaded.

    uv run python scripts/bundle.py                    # engine + every pack found
    uv run python scripts/bundle.py --pack en-US=en.crx3
    uv run python scripts/bundle.py --clean

Then `uv build --wheel` produces the self-contained wheel. See docs/MODEL.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from soda_stt._config import LANGUAGE_PACK_IDS, SODA_COMPONENT_ID  # noqa: E402

DEFAULT_ARTIFACTS = REPO / "artifacts"
DEFAULT_OUT = REPO / "src" / "soda_stt" / "_bundle"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _sha256_tree(root: Path) -> tuple[str, int]:
    """Deterministic digest over every file's path, size and content hash."""
    h = hashlib.sha256()
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        h.update(f"{rel}\0{size}\0{_sha256_file(path)}\n".encode())
        total += size
    return h.hexdigest(), total


def _manifest_from_crx(crx: Path) -> dict:
    with zipfile.ZipFile(crx) as zf:
        return json.loads(zf.read("manifest.json"))


def _crx_payload_dir(crx: Path, dest: Path) -> Path:
    """Extract a CRX3 and return the dir holding SODAFiles/ or SODAModels/."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(crx) as zf:  # CRX3 = header + zip; zipfile skips ahead
        zf.extractall(dest)
    return dest


def _packaged(payload: Path) -> Path:
    """Where a component's payload lives: SODAFiles/, SODAModels/, or the root."""
    for name in ("SODAFiles", "SODAModels"):
        if (payload / name).is_dir():
            return payload / name
    return payload


def _manifest_for(source: Path) -> dict:
    """Component manifest for an explicit source: a CRX3 or an extracted tree."""
    if source.name.endswith(".crx3"):
        return _manifest_from_crx(source)
    for candidate in (source / "manifest.json", source.parent / "manifest.json"):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def discover(artifacts: Path) -> dict[str, tuple[Path, dict]]:
    """Find components under `artifacts/`: CRX3 files first, then extracted trees.

    Returns {key: (source_path, manifest)} with key "engine" or a locale.
    """
    found: dict[str, tuple[Path, dict]] = {}

    def key_for(name: str) -> str | None:
        name = name.strip()
        if name == "Chrome SODA":
            return "engine"
        if name.startswith("Chrome SODA "):
            return name.removeprefix("Chrome SODA ").strip()
        return None

    crx_dir = artifacts / "crx"
    for crx in sorted(crx_dir.glob("*.crx3")):
        manifest = _manifest_from_crx(crx)
        key = key_for(manifest.get("name", ""))
        if key:
            found[key] = (crx, manifest)

    for manifest_path in sorted(artifacts.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        key = key_for(manifest.get("name", ""))
        if key and key not in found:
            found[key] = (manifest_path.parent, manifest)
    return found


def stage(source: Path, manifest: dict, key: str, out: Path) -> dict:
    """Copy/extract one component into `out`; return its bundle.json record."""
    if source.suffix == ".crx3":
        payload = _crx_payload_dir(source, out / ".tmp-payload")
    else:
        payload = source

    if key == "engine":
        src = _packaged(payload)  # .../SODAFiles
        dest = out / "SODAFiles"
        shutil.copytree(src, dest, dirs_exist_ok=True)
        lib = dest / "libsoda.so"
        record = {
            "version": manifest.get("version", "unknown"),
            "component_id": SODA_COMPONENT_ID,
            "sha256": _sha256_file(lib),
            "bytes": lib.stat().st_size,
        }
    else:
        src = _packaged(payload)  # .../SODAModels
        dest = out / key / "SODAModels"
        shutil.copytree(src, dest, dirs_exist_ok=True)
        digest, total = _sha256_tree(dest)
        record = {
            "version": manifest.get("version", "unknown"),
            "component_id": LANGUAGE_PACK_IDS.get(key, ""),
            "sha256": digest,
            "bytes": total,
            "files": sum(1 for p in dest.rglob("*") if p.is_file()),
        }
    if payload == out / ".tmp-payload":
        shutil.rmtree(payload, ignore_errors=True)
    return record


def build_helper(out: Path) -> Path | None:
    """Compile the native helper and stage it so the wheel carries a binary."""
    src = REPO / "native" / "soda_helper.c"
    cc = os.environ.get("CC", "cc")
    binary = REPO / "native" / "soda_helper"
    subprocess.run(
        [cc, "-O2", "-rdynamic", "-o", str(binary), str(src), "-ldl", "-lpthread"],
        check=True,
    )
    dest = out.parent / "soda_helper"
    shutil.copy2(binary, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS,
                        help="directory holding CRX3 files and/or extracted components")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="bundle destination inside the package")
    parser.add_argument("--only", action="append", default=[],
                        metavar="KEY", help="stage only this key (engine or locale)")
    parser.add_argument("--engine", type=Path,
                        help="engine CRX3 or extracted dir (default: discover under --artifacts)")
    parser.add_argument("--pack", action="append", default=[], metavar="LOCALE=PATH",
                        help="stage this language pack from a CRX3 or extracted dir")
    parser.add_argument("--no-helper", action="store_true",
                        help="skip compiling the native helper into the package")
    parser.add_argument("--clean", action="store_true",
                        help="remove an existing bundle and exit")
    args = parser.parse_args(argv)

    if args.clean:
        for path in (args.out, args.out.parent / "soda_helper"):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"removed {path}")
            elif path.is_file():
                path.unlink()
                print(f"removed {path}")
        return 0

    found = discover(args.artifacts)
    if args.engine is not None:
        if not args.engine.exists():
            parser.error(f"--engine path not found: {args.engine}")
        found["engine"] = (args.engine, _manifest_for(args.engine))
    for spec in args.pack:
        if "=" not in spec:
            parser.error(f"--pack expects LOCALE=PATH, got {spec!r}")
        locale, path = spec.split("=", 1)
        src = Path(path).expanduser()
        if not src.exists():
            parser.error(f"--pack path not found: {src}")
        found[locale] = (src, _manifest_for(src))

    wanted = args.only or sorted(found)
    missing = [k for k in wanted if k not in found]
    if missing or not found:
        print(
            f"nothing staged; missing {missing or 'any component'} "
            f"(looked for --engine/--pack paths and components under {args.artifacts})",
            file=sys.stderr,
        )
        return 1

    tmp = args.out.with_name(args.out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    records: dict[str, dict] = {}
    for key in wanted:
        source, manifest = found[key]
        records[key] = stage(source, manifest, key, tmp)
        print(f"staged {key} {records[key]['version']} from {source}")

    engine = records.pop("engine", None)
    bundle = {"format": 1, "language_packs": records}
    if engine:
        bundle["engine"] = engine
    (tmp / "bundle.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    shutil.rmtree(args.out, ignore_errors=True)
    os.replace(tmp, args.out)

    if not args.no_helper:
        helper = build_helper(args.out)
        print(f"staged helper {helper}")

    total = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"bundle at {args.out} ({total / 1e6:.0f} MB)")
    print("build the self-contained wheel with: uv build --wheel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
