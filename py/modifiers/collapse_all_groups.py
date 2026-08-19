from collections.abc import Callable
from functools import cached_property

from src.templates._core import BaseTemplate

from ..helpers import collapse_all_groups


class CollapseAllGroupsMod(BaseTemplate):
    """Modifier for collapsing all groups in order to make it easier to access
    the layers usually involved in pop-outs."""

    @cached_property
    def hooks(self) -> list[Callable[[], None]]:
        hooks = super().hooks
        hooks.append(collapse_all_groups)
        return hooks
