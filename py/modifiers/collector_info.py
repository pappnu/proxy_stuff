from collections.abc import Callable
from functools import cached_property

from photoshop.api._artlayer import ArtLayer

from src.helpers.layers import getLayer
from src.helpers.position import RefSide, check_reference_overlap
from src.templates._core import BaseTemplate


class ExtraCollectorInfoMod(BaseTemplate):
    @cached_property
    def extra_collector_info_format(self) -> str:
        return self.config.get_setting("TEXT", "Collector.Line.Extra", default="")

    @cached_property
    def text_layer_extra_collector_info(self) -> ArtLayer | None:
        return getLayer("Extra", self.legal_group)

    def format_extra_collector_info(self) -> None:
        if self.extra_collector_info_format and self.text_layer_extra_collector_info:
            self.text_layer_extra_collector_info.visible = True
            self.format_collector_info_line_custom(
                self.text_layer_extra_collector_info, self.extra_collector_info_format
            )

            if self.text_layer_collector_second:
                extra_bounds = self.text_layer_extra_collector_info.bounds
                ref_bounds = self.text_layer_collector_second.bounds
                delta_y = 0

                if (
                    self.is_creature
                    and self.pt_reference
                    and check_reference_overlap(
                        self.text_layer_extra_collector_info,
                        self.pt_reference,
                        ref_side=RefSide.BOTTOM,
                    )
                    > 0
                ):
                    # Vertically avoid PT box
                    delta_y = ref_bounds[3] - extra_bounds[3]

                # Precisely mirror offset from card edge with set layer
                self.text_layer_extra_collector_info.translate(
                    self.docref.width - ref_bounds[0] - extra_bounds[2], delta_y
                )

    @cached_property
    def text_layer_methods(self) -> list[Callable[[], None]]:
        methods = super().text_layer_methods
        methods.append(self.format_extra_collector_info)
        return methods
