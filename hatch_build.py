"""Build hook: tag the wheel for the platform it can actually run on.

`scripts/bundle.py` stages libsoda.so (a Linux x86-64 ELF) into the package, so
the wheel is not universal: pip must not install it on a Mac. hatchling has no
config key for this, hence the hook. It also warns when a wheel is built without
a bundle, since such a wheel downloads its components on first use.
"""

from __future__ import annotations

import sysconfig
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class PlatformWheelBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        if self.target_name != "wheel":
            return
        platform = sysconfig.get_platform().replace("-", "_").replace(".", "_")
        build_data["tag"] = f"py3-none-{platform}"
        build_data["pure_python"] = False
        if not (Path(self.root) / "src" / "soda_stt" / "_bundle" / "bundle.json").is_file():
            self.app.display_warning(
                "No bundle staged (run: uv run python scripts/bundle.py); this wheel "
                "will download the SODA engine and language packs on first use."
            )
