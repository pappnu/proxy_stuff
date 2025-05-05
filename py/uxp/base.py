from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Any

from photoshop.api import ActionDescriptor, DialogModes

from src import APP
from src._state import PATH

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID


def replace_last(string: str, old: str, new: str) -> str:
    old_idx = string.rfind(old)
    if old_idx > -1:
        return string[:old_idx] + new + string[old_idx + len(old) :]
    return string


def open_in_photoshop(path: Path | str):
    desc = ActionDescriptor()
    desc.putPath(cID("null"), str(path))
    APP.executeAction(sID("open"), desc, DialogModes.DisplayNoDialogs)


class _UXPAccess:
    @cached_property
    def scripts_dir(self) -> Path:
        return PATH.PLUGINS / "proxy_stuff" / "dist"

    @cached_property
    def path_temp_script(self) -> Path:
        return self.scripts_dir / "_temp.psjs"

    @cached_property
    def path_temp_script_absolute(self) -> str:
        return str(self.path_temp_script.resolve()).replace("\\", "/")

    def read_script(self, name: str) -> str:
        with open(self.scripts_dir / name, "r", encoding="utf-8") as f:
            script_str = f.read()

        # TypeScript won't allow using await on top level with CommonJS modules,
        # which Photoshop expects, but the scripts can terminate too early
        # if await isn't used at top level, so we have to add it programmatically.
        # This will break if tsc decides to use a different name for the photoshop import
        # or if the script doesn't use executeAsModal as its last operation to wait.
        return replace_last(
            script_str,
            "photoshop_1.core.executeAsModal",
            "await photoshop_1.core.executeAsModal",
        )

    def construct_script(self, script: str, data: Any) -> None:
        script_str = script.replace(
            "data = []", f"data = {dumps(data, ensure_ascii=False)}"
        )
        with open(self.path_temp_script, "w", encoding="utf-8") as f:
            f.write(script_str)

    def run_script(self, script: str, data: Any) -> None:
        """Runs an UXP script in Photoshop."""
        self.construct_script(script, data)
        open_in_photoshop(self.path_temp_script_absolute)
        # try:
        #    APP.open(self.path_temp_script_absolute)
        # except COMError as err:
        #     # The open script operation errors even if the script executes successfully
        #     if "-2147213504," not in str(err):
        #         print("Batch play failed for script:", script)
        #         raise err


uxp = _UXPAccess()
