from _ctypes import COMError
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from src import APP
from src._state import PATH


class ActionTarget(TypedDict):
    _ref: str


class ActionTargetID(ActionTarget):
    _id: int


class ActionTargetName(ActionTarget):
    _name: str


class ActionTargetIndex(ActionTarget):
    _index: int


class ActionTargetEnumeration(ActionTarget):
    _enum: NotRequired[str]
    _value: NotRequired[str]


class ActionTargetProperty(ActionTarget):
    _property: str


class OptionsDescriptor(TypedDict):
    dialogOptions: NotRequired[Literal["silent", "dontDisplay", "display"]]
    suppressProgressBar: NotRequired[bool]


class ActionDescriptor(TypedDict):
    _target: NotRequired[
        list[
            ActionTarget
            | ActionTargetID
            | ActionTargetName
            | ActionTargetIndex
            | ActionTargetEnumeration
            | ActionTargetProperty
        ]
    ]
    _options: NotRequired[OptionsDescriptor]


class _BatchPlayCache:
    @cached_property
    def _path_script_template(self) -> Path:
        return Path("./plugins/proxy_stuff/js/batchPlay.psjs")

    @cached_property
    def path_temp_script(self) -> Path:
        return PATH.CWD / "plugins" / "proxy_stuff" / "js" / "_temp.psjs"

    @cached_property
    def path_temp_script_absolute(self) -> str:
        return str(self.path_temp_script.resolve()).replace("\\", "/")

    @cached_property
    def batch_play_template_script(self) -> str:
        with open(self._path_script_template, "r", encoding="utf-8") as f:
            return f.read()

    def construct_script(self, *descriptors: ActionDescriptor) -> None:
        script_str = self.batch_play_template_script.replace(
            "[{}]", dumps(descriptors, ensure_ascii=False)
        )
        with open(self.path_temp_script, "w", encoding="utf-8") as f:
            f.write(script_str)


_batch_play_cache = _BatchPlayCache()


def batch_play(*descriptors: ActionDescriptor) -> None:
    """Runs an UXP script in Photoshop."""
    _batch_play_cache.construct_script(*descriptors)
    try:
        APP.open(_batch_play_cache.path_temp_script_absolute)
    except COMError as err:
        # The open script operation errors even if the script executes successfully
        if "-2147213504," not in str(err):
            print("Batch play failed for descriptors:", descriptors)
            raise err
