#!/usr/bin/env bash
# Build the two release artifacts into dist/:
#   - a manylinux wheel (PyPI rejects the plain `linux_x86_64` tag)
#   - the self-contained sdist, which pip builds from when no wheel matches
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python scripts/bundle.py
rm -f dist/*.whl dist/*.tar.gz

# Builds the sdist first, then the wheel from it, so both carry the bundle.
uv build -o dist

wheel=$(ls dist/*-linux_x86_64.whl)
# `--with patchelf`: auditwheel needs it to rewrite the wheel's tags in place.
uvx --with patchelf auditwheel repair --wheel-dir dist "$wheel"
rm -f "$wheel"

uvx twine check dist/*
ls -la dist
