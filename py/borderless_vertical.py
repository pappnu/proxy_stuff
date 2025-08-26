from collections.abc import Callable
from functools import cached_property

from photoshop.api import SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import CFG
from src.enums.layers import LAYERS
from src.helpers.colors import get_rgb
from src.helpers.effects import enable_layer_fx
from src.helpers.layers import getLayer, getLayerSet
from src.helpers.masks import apply_mask_to_layer_fx
from src.templates._vector import MaskAction
from src.templates.normal import BorderlessVectorTemplate
from src.utils.adobe import LayerObjectTypes

from .helpers import LAYER_NAMES, create_clipping_mask, find_art_layer
from .vertical_mod import VerticalMod


class BorderlessVertical(VerticalMod):
    # region Settings

    @cached_property
    def color_typeline(self) -> bool:
        return CFG.get_bool_setting(
            section="COLORS", key="Color.Typeline", default=False
        )

    @cached_property
    def color_textbox(self) -> bool:
        return CFG.get_bool_setting(
            section="COLORS", key="Color.Textbox", default=False
        )

    # endregion Settings

    # region Groups

    @cached_property
    def pt_group(self) -> LayerSet | None:
        if self.is_vertical_layout:
            return getLayerSet(LAYERS.PT_BOX)
        return super().pt_group

    # endregion Groups

    # region Shapes

    @cached_property
    def twins_shapes(self) -> list[ArtLayer | LayerSet | None]:
        if self.is_vertical_layout:
            _shape_group = getLayerSet(LAYERS.SHAPE, self.twins_group)
            return [
                getLayer(
                    LAYERS.TRANSFORM
                    if self.is_transform or self.is_mdfc
                    else LAYERS.NORMAL,
                    [_shape_group, LAYERS.NAME],
                ),
                getLayer(
                    LAYERS.TALL if self.has_extra_textbox else LAYER_NAMES.VERTICAL,
                    [_shape_group, LAYERS.TYPE_LINE],
                ),
            ]
        return super().twins_shapes

    @cached_property
    def textbox_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        if self.is_vertical_layout:
            return getLayer(
                self.vertical_mode_layer_name,
                [self.textbox_group, LAYERS.SHAPE],
            )
        return super().textbox_shape

    @cached_property
    def pt_shape(self) -> ArtLayer | None:
        if self.is_creature:
            return getLayer(
                LAYER_NAMES.PT_OUTER
                + (
                    f" {LAYER_NAMES.VERTICAL}"
                    if self.is_vertical_creature and not self.has_extra_textbox
                    else ""
                ),
                [self.pt_group, LAYERS.SHAPE],
            )

    @cached_property
    def pt_inner_shape(self) -> ArtLayer | None:
        if self.is_creature:
            return getLayer(
                LAYER_NAMES.PT_INNER
                + (
                    f" {LAYER_NAMES.VERTICAL}"
                    if self.is_vertical_creature and not self.has_extra_textbox
                    else ""
                ),
                [self.pt_group, LAYERS.SHAPE],
            )

    @cached_property
    def bottom_curve_shape(self) -> ArtLayer | None:
        if self.is_vertical_layout and not self.has_extra_textbox:
            return getLayer(
                "Curved Fill",
                self.border_group if isinstance(self.border_group, LayerSet) else None,
            )

    @cached_property
    def enabled_shapes(self) -> list[ArtLayer | LayerSet | None]:
        return [*super().enabled_shapes, self.pt_shape, self.bottom_curve_shape]

    # endregion Shapes

    # region Masks

    @cached_property
    def border_mask(
        self,
    ) -> (
        MaskAction
        | tuple[ArtLayer | LayerSet, ArtLayer | LayerSet]
        | ArtLayer
        | LayerSet
        | None
    ):
        if self.is_vertical_layout:
            if self.border_group and (
                layer := getLayer(
                    LAYER_NAMES.VERTICAL, [self.mask_group, LAYERS.BORDER]
                )
            ):
                return {
                    "mask": layer,
                    "layer": self.border_group,
                    "vector": True,
                }
            return None
        return super().border_mask

    @cached_property
    def pinlines_mask(
        self,
    ) -> (
        MaskAction
        | tuple[ArtLayer | LayerSet, ArtLayer | LayerSet]
        | ArtLayer
        | LayerSet
        | None
    ):
        if self.is_vertical_layout:
            if (
                not self.has_extra_textbox
                and self.pinlines_group
                and (
                    layer := getLayer(
                        f"{LAYER_NAMES.VERTICAL}{f' {LAYERS.TRANSFORM}' if self.is_transform else ''}",
                        [self.mask_group, LAYERS.PINLINES],
                    )
                )
            ):
                return {
                    "mask": layer,
                    "layer": self.pinlines_group,
                    "funcs": [apply_mask_to_layer_fx],
                }
            return None
        return super().pinlines_mask

    @cached_property
    def crown_mask(
        self,
    ) -> (
        MaskAction
        | tuple[ArtLayer | LayerSet, ArtLayer | LayerSet]
        | ArtLayer
        | LayerSet
        | None
    ):
        if self.is_vertical_creature and self.is_transform:
            return None
        return super().crown_mask

    # endregion Masks

    # region Colors

    def enable_frame_layers(self) -> None:
        super().enable_frame_layers()

        if self.is_creature and self.pt_group:
            layer: ArtLayer
            # Remove unwanted group wide color fill
            for layer in self.pt_group.artLayers:
                if " Fill " in layer.name:
                    layer.visible = False
                    break

            # The inner and outer parts of the PT box require different colors
            if self.pt_shape:
                self.generate_layer(group=self.pt_shape, colors=self.pinlines_colors)
            if self.pt_inner_shape:
                self.generate_layer(
                    group=self.pt_inner_shape, colors=self.pt_inner_colors
                )

    # endregion Colors

    # region Text

    def set_layer_font_color(
        self, layer: ArtLayer, color: SolidColor | None = None
    ) -> None:
        color = color or self.RGB_BLACK
        layer.textItem.color = color

    def handle_authentic_front_text_coloring(self) -> None:
        if self.is_authentic_front and self.text_layer_name:
            self.set_layer_font_color(self.text_layer_name)

        if self.is_authentic_front and self.color_typeline and self.text_layer_type:
            self.set_layer_font_color(self.text_layer_type)

        if (
            self.color_textbox
            and self.show_vertical_reminder_text
            and self.text_layer_reminder
        ):
            self.set_layer_font_color(self.text_layer_reminder)

    @cached_property
    def text_layer_pt(self) -> ArtLayer | None:
        if self.is_vertical_creature and not self.has_extra_textbox:
            return getLayer(
                f"{LAYERS.POWER_TOUGHNESS} {LAYER_NAMES.VERTICAL}", [self.text_group]
            )
        return super().text_layer_pt

    # endregion Text

    # region Hooks

    def disable_colors(self) -> None:
        if (
            not self.color_textbox
            and self.textbox_group
            and (
                layer := find_art_layer(
                    self.textbox_group,
                    lambda layer: " Fill " in layer.name,
                )
            )
        ):
            layer.remove()
        if (
            not self.color_typeline
            and self.twins_group
            and (
                layer := find_art_layer(
                    self.twins_group, lambda layer: " Fill " in layer.name
                )
            )
            and (
                ref := getLayerSet(
                    LAYER_NAMES.CARD_NAME, [self.twins_group, LAYERS.SHAPE]
                )
            )
        ):
            layer.move(
                ref,
                ElementPlacement.PlaceBefore,
            )
            create_clipping_mask(layer)

    @cached_property
    def hooks(self) -> list[Callable[[], None]]:
        return [*super().hooks, self.disable_colors]

    # endregion Hooks

    # region Saga

    def text_layers_saga(self):
        if self.has_extra_textbox:
            self.show_vertical_reminder_text = False

        if self.color_textbox and self.is_authentic_front and self.text_layer_ability:
            self.set_layer_font_color(self.text_layer_ability)

        if self.is_drop_shadow:
            enable_layer_fx(self.text_layer_ability)

        return super().text_layers_saga()

    # endregion Saga

    # region MDFC

    def text_layers_mdfc_front(self) -> None:
        self.handle_authentic_front_text_coloring()

    # endregion MDFC

    # region Transform

    def text_layers_transform_front(self) -> None:
        self.handle_authentic_front_text_coloring()

        if (
            self.color_textbox
            and self.is_authentic_front
            and self.is_flipside_creature
            and self.text_layer_flipside_pt
        ):
            self.text_layer_flipside_pt.textItem.color = get_rgb(45, 45, 45)

        super(BorderlessVectorTemplate, self).text_layers_transform_front()

    # endregion Transform
