from collections.abc import Callable
from functools import cached_property

from photoshop.api.enumerations import BlendMode, ElementPlacement

from src.helpers.adjustments import create_color_layer
from src.helpers.colors import rgb_black
from src.schema.colors import ColorObject
from src.templates._core import BaseTemplate


class HideTransparencyMod(BaseTemplate):
    """A modifier that ensures that the render output doesn't have transparent parts."""

    @cached_property
    def should_hide_transparencies(self) -> bool:
        return True

    @cached_property
    def transparency_fill_color(self) -> ColorObject:
        return rgb_black()

    @cached_property
    def hooks(self) -> list[Callable[[], None]]:
        hooks = super().hooks
        hooks.append(self._hide_transparencies)
        return hooks

    def _hide_transparencies(self) -> None:
        if self.should_hide_transparencies and self.art_layer:
            # Create a black layer behind everything else in order
            # to ensure that there's no transparency in the final image.
            layer = self.docref.artLayers.add()
            layer.move(self.art_layer, ElementPlacement.PlaceAfter)
            create_color_layer(
                self.transparency_fill_color,
                layer,
                self.docref,
                blend_mode=BlendMode.NormalBlend,
            )
