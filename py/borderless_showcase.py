from functools import cached_property
from math import ceil
from typing import Any, Callable, Iterable, Literal, Sequence

from photoshop.api import SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import APP, CFG
from src.enums.adobe import Dimensions
from src.enums.layers import LAYERS
from src.enums.mtg import Rarity
from src.helpers.bounds import get_layer_dimensions
from src.helpers.colors import get_pinline_gradient, get_rgb
from src.helpers.effects import apply_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.helpers.masks import apply_mask, copy_layer_mask
from src.schema.adobe import EffectGradientOverlay, EffectStroke, LayerEffects
from src.schema.colors import ColorObject, GradientColor
from src.templates.planeswalker import PlaneswalkerMod
from src.templates.saga import SagaMod
from src.templates.transform import TransformMod
from src.utils.adobe import LayerObjectTypes, ReferenceLayer

from .backup import BackupAndRestore
from .helpers import (
    LAYER_NAMES,
    ExpansionSymbolOverrideMode,
    FlipDirection,
    copy_color,
    flip_layer,
    get_numeric_setting,
    is_color_identity,
    parse_hex_color_list,
)
from .vertical_mod import VerticalMod


class BorderlessShowcase(VerticalMod, PlaneswalkerMod, BackupAndRestore):
    # region settings

    @cached_property
    def color_limit(self) -> int:
        setting = CFG.get_setting(
            section="COLORS", key="Max.Colors", default="2", is_bool=False
        )
        if isinstance(setting, str):
            return int(setting) + 1
        raise ValueError(f"Received invalid value for color limit: {setting}")

    @cached_property
    def front_face_colors(self) -> bool:
        """Returns True if lighter color map should be used on front face DFC cards."""
        return bool(
            CFG.get_setting(section="COLORS", key="Front.Face.Colors", default=True)
        )

    @cached_property
    def multicolor_pinlines(self) -> bool:
        """Returns True if Pinlines for multicolored cards should use blended colors."""
        return bool(
            CFG.get_setting(section="COLORS", key="Multicolor.Pinlines", default=True)
        )

    @cached_property
    def pt_box_and_bottom_pinline_type(self) -> Literal["Full", "Partial", "Split"]:
        setting = CFG.get_setting(
            section="SHAPES", key="PT.Box.And.Pinline", default="Full", is_bool=False
        )
        if setting in ("Full", "Partial", "Split"):
            return setting
        raise ValueError(
            f"Received invalid value for PT box and bottom pinline type: {setting}"
        )

    @cached_property
    def bottom_border_type(self) -> Literal["Full", "Fade", "Shadow"] | None:
        setting = CFG.get_setting(
            section="SHAPES", key="Bottom.Border", default="Full", is_bool=False
        )
        if setting in ("Full", "Fade", "Shadow"):
            return setting
        if setting == "None":
            return None
        raise ValueError(f"Received invalid value for bottom border type: {setting}")

    @cached_property
    def flip_twins(self) -> bool:
        return bool(CFG.get_setting(section="SHAPES", key="Flip.Twins", default=False))

    @cached_property
    def pinlines_color_override(self) -> list[SolidColor]:
        if (
            setting := CFG.get_setting(
                section="COLORS", key="Pinlines.Override", default=None, is_bool=False
            )
        ) and isinstance(setting, str):
            return parse_hex_color_list(setting, self.console)
        return []

    @cached_property
    def expansion_symbol_color_override(self) -> ExpansionSymbolOverrideMode:
        if (
            setting := CFG.get_setting(
                section="COLORS",
                key="Expansion.Symbol.Override",
                default=None,
                is_bool=False,
            )
        ) and isinstance(setting, str):
            if setting == "Identity":
                return ExpansionSymbolOverrideMode.Identity
            if setting == "Pinlines override":
                return ExpansionSymbolOverrideMode.Pinlines
            if setting == "Custom":
                return ExpansionSymbolOverrideMode.Custom
        return ExpansionSymbolOverrideMode.Off

    @cached_property
    def expansion_symbol_custom_colors(self) -> list[SolidColor]:
        if (
            setting := CFG.get_setting(
                section="COLORS",
                key="Expansion.Symbol.Custom",
                default=None,
                is_bool=False,
            )
        ) and isinstance(setting, str):
            return parse_hex_color_list(setting, self.console)
        return []

    @cached_property
    def darken_exnapsion_symbol_gradient_endpoints(self) -> float:
        return get_numeric_setting(
            CFG, "COLORS", "Expansion.Symbol.Darken", 0, (0, 100)
        )

    @cached_property
    def expansion_symbol_gradient_angle(self) -> float:
        return get_numeric_setting(
            CFG, "COLORS", "Expansion.Symbol.Angle", 0, (-360, 360)
        )

    @cached_property
    def expansion_symbol_gradient_scale(self) -> float:
        return get_numeric_setting(
            CFG, "COLORS", "Expansion.Symbol.Scale", 70, (10, 150)
        )

    @cached_property
    def expansion_symbol_gradient_method(self) -> str:
        if (
            setting := CFG.get_setting(
                section="COLORS",
                key="Expansion.Symbol.Method",
                default=None,
                is_bool=False,
            )
        ) and isinstance(setting, str):
            return setting
        return "linear"

    # endregion settings

    # region Checks

    @cached_property
    def is_planeswalker(self) -> bool:
        return hasattr(self.layout, "pw_size")

    @cached_property
    def is_pt_enabled(self) -> bool:
        return self.is_creature

    # endregion Checks

    # region Frame Details

    @property
    def art_frame_vertical(self) -> str:
        if self.bottom_border_type == "Full":
            return "Full Art Frame Alt"
        return super().art_frame_vertical

    @cached_property
    def size(self) -> str:
        if self.is_planeswalker:
            if self.layout.pw_size > 3:
                return LAYER_NAMES.PW4
            return LAYER_NAMES.PW3
        return super().size

    def override_set_symbol(self) -> None:
        if self.expansion_symbol_color_override is not ExpansionSymbolOverrideMode.Off:
            # Common symbol is used since it can be inverted to get
            # a white symbol with black lines, which is easy to tint with other colors
            self.layout.rarity_letter = Rarity.C[0].upper()

    @property
    def pre_render_methods(self) -> list[Callable[[], None]]:
        return [*super().pre_render_methods, self.override_set_symbol]

    # endregion Frame Details

    # region Backup

    @cached_property
    def layers_to_seek_masks_from(self) -> Iterable[ArtLayer | LayerSet | None]:
        return (self.pinlines_group,)

    # endregion Backup

    # region Colors

    @cached_property
    def pt_colors(self) -> list[int] | list[dict[str, Any]]:
        return self.pinlines_colors

    _gradient_start_location: float = 0.05

    @cached_property
    def pinlines_colors(self) -> list[int] | list[dict[str, Any]]:
        if override := self.pinlines_color_override:
            colors = ""
            color_map: dict[str, SolidColor] = {}
            for idx, color in enumerate(override):
                i = str(idx)
                colors += i
                color_map[i] = color

            location_map: dict[int, list[int | float]] | None = None
            if (steps := len(colors)) > 5:
                gradient_end_location = 1 - self._gradient_start_location
                locations: list[int | float] = [self._gradient_start_location]
                steps_between = (steps - 2) * 2 + 1
                step = (gradient_end_location - self._gradient_start_location) / (
                    (steps - 2) * 2 + 1
                )
                for i in range(steps_between - 1):
                    locations.append(locations[i] + step)
                locations.append(gradient_end_location)
                location_map = {steps: locations}

            return get_pinline_gradient(
                colors=colors, color_map=color_map, location_map=location_map
            )
        return super().pinlines_colors

    # endregion Colors

    # region Groups

    @cached_property
    def pt_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.PT_BOX)

    @cached_property
    def crown_group(self) -> LayerSet | None:
        return None

    @cached_property
    def textbox_group(self) -> LayerSet | None:
        return None

    @cached_property
    def border_group(self) -> LayerSet:
        if layer := getLayerSet(LAYERS.BORDER):
            return layer
        raise Exception("Couldn't get border group.")

    @cached_property
    def text_group(self) -> LayerSet:
        if layer := getLayerSet(LAYERS.TEXT_AND_ICONS):
            return layer
        raise Exception("Couldn't get text group.")

    # endregion Groups

    # region Reference Layers

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_planeswalker:
            ref = get_reference_layer(
                self.size,
                getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group),
            )
            if (
                ref
                and self.is_mdfc
                and (
                    mdfc_mask := getLayer(
                        LAYERS.MDFC, [self.mask_group, LAYERS.TEXTBOX_REFERENCE]
                    )
                )
            ):
                copy_layer_mask(layer_from=mdfc_mask, layer_to=ref)
                apply_mask(ref)
                ref.visible = False
            return ref
        return super().textbox_reference

    # endregion Reference Layers

    # region Shapes

    @cached_property
    def pt_box_shape(self) -> list[ArtLayer | None]:
        if not self.is_pt_enabled:
            return [None]

        if self.bottom_border_type == "Full":
            pt_name = "Full"
        elif self.bottom_border_type == "Fade":
            pt_name = "Partial"
        else:
            pt_name = self.pt_box_and_bottom_pinline_type
        return [
            getLayer(pt_name, [self.pt_group, LAYERS.SHAPE]),
            getLayer(
                "Fill" if pt_name in ("Full", "Partial") else "Fill Split",
                self.pt_group,
            ),
        ]

    @cached_property
    def flipside_pt_arrow(self) -> ArtLayer | None:
        if self.is_front and self.is_flipside_creature:
            return getLayer(
                "Flipside PT Arrow",
                [
                    self.pinlines_group,
                    LAYERS.SHAPE,
                    LAYERS.SAGA if self.is_layout_saga else LAYERS.TEXTBOX,
                ],
            )
        return None

    @cached_property
    def bottom_pinline_shape(self) -> ArtLayer | None:
        if self.is_pt_enabled:
            return None
        return getLayer(
            "Partial"
            if self.pt_box_and_bottom_pinline_type != "Full"
            else self.pt_box_and_bottom_pinline_type,
            [self.pinlines_group, LAYERS.SHAPE, LAYERS.BOTTOM],
        )

    @cached_property
    def bottom_border_shape(self) -> ArtLayer | None:
        if not self.bottom_border_type:
            return None
        return getLayer(self.bottom_border_type, LAYERS.BORDER)

    @cached_property
    def pinlines_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        _shape_group = getLayerSet(LAYERS.SHAPE, self.pinlines_group)

        layers: list[LayerObjectTypes] = []
        delta: int | float = 0

        # Name
        if (
            self.flip_twins
            and not (self.is_transform or self.is_mdfc)
            and (
                layer_set := getLayerSet(
                    LAYERS.NORMAL,
                    [_shape_group, LAYERS.NAME],
                )
            )
            and (layer := getLayer(LAYERS.NORMAL, layer_set))
        ):
            dims = get_layer_dimensions(layer)
            delta = APP.activeDocument.width - 2 * dims[Dimensions.CenterX]
            layer.translate(delta, 0)
            flip_layer(layer, FlipDirection.Horizontal)
            layers.append(layer_set)
        elif layer := getLayerSet(
            LAYERS.TRANSFORM
            if self.is_transform
            else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
            [_shape_group, LAYERS.NAME],
        ):
            layers.append(layer)

        # Add nickname pinlines if required
        if self.is_nickname:
            layers.append(getLayerSet(LAYERS.NICKNAME, _shape_group))

        if self.is_planeswalker:
            if layer_set := getLayerSet(self.size, _shape_group):
                if self.flip_twins and (layer := getLayer(LAYERS.RIGHT, layer_set)):
                    layer.visible = False
                layers.append(layer_set)
            return layers

        # Typeline
        if not self.is_textless and (
            layer := getLayer(
                self.size,
                [_shape_group, LAYERS.TYPE_LINE],
            )
        ):
            if self.flip_twins:
                layer.translate(-delta, 0)
                flip_layer(layer, FlipDirection.Horizontal)
            layers.append(layer)

        return layers

    @cached_property
    def textbox_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        return None

    @cached_property
    def twins_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        return None

    @cached_property
    def crown_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        return None

    def enable_crown(self) -> None:
        pass

    @cached_property
    def enabled_shapes(self) -> list[ArtLayer | LayerSet | None]:
        return [
            *super().enabled_shapes,
            *self.pt_box_shape,
            self.flipside_pt_arrow,
            self.bottom_border_shape,
            self.bottom_pinline_shape,
        ]

    # endregion Shapes

    # region Masks

    def pw_mask_bottom(self):
        if (
            self.is_planeswalker
            and self.pt_box_and_bottom_pinline_type in ("Partial", "Split")
            and self.bottom_pinline_shape
            and (mask := getLayer(LAYERS.BOTTOM, [self.mask_group, LAYER_NAMES.PW]))
        ):
            return {"mask": mask, "layer": self.bottom_pinline_shape}

    @cached_property
    def enabled_masks(
        self,
    ) -> list[dict[str, Any] | list[Any] | ArtLayer | LayerSet | None]:
        return [self.pw_mask_bottom()]

    # endregion Masks

    # region Text

    @cached_property
    def text_layer_ability(self) -> ArtLayer:
        if self.is_planeswalker:
            return super(SagaMod, self).text_layer_ability
        return super().text_layer_ability

    @cached_property
    def text_layer_flipside_pt(self) -> ArtLayer | None:
        if self.is_layout_saga:
            return getLayer(LAYERS.FLIPSIDE_POWER_TOUGHNESS, self.saga_group)
        return getLayer(LAYERS.FLIPSIDE_POWER_TOUGHNESS, self.text_group)

    def expansion_symbol_handler(self) -> None:
        if self.expansion_symbol_layer:
            if self.size == LAYERS.TEXTLESS and self.is_pt_enabled:
                self.expansion_symbol_layer.visible = False
                return None

            effects: list[LayerEffects] = [EffectStroke(weight=7, style="out")]

            # Expansion symbol color gradient override
            if (
                mode := self.expansion_symbol_color_override
            ) is not ExpansionSymbolOverrideMode.Off:
                self.expansion_symbol_layer.invert()

                step: int | float
                colors: list[ColorObject]

                if mode is ExpansionSymbolOverrideMode.Identity:
                    if (len_identity := len(self.identity)) > 1 and is_color_identity(
                        self.identity
                    ):
                        # For some reason the gradient locations are specified on
                        # a scale of 0-4096 even though in the UI they are specified as 0-100
                        step = 4096 / ((len_identity - 1) or 1)
                        colors = [
                            self.pinlines_color_map[color] for color in self.identity
                        ]

                    else:
                        step = 2048
                        colors = [self.pinlines_color_map[self.identity]] * 3
                elif mode is ExpansionSymbolOverrideMode.Pinlines:
                    step = 4096 / ((len(self.pinlines_color_override) - 1) or 1)
                    colors = [*self.pinlines_color_override]
                else:
                    step = 4096 / ((len(self.expansion_symbol_custom_colors) - 1) or 1)
                    colors = [*self.expansion_symbol_custom_colors]

                if colors:
                    # Optional darken
                    if self.darken_exnapsion_symbol_gradient_endpoints:
                        if len(colors) == 1:
                            step = 2048
                            colors = colors * 3

                        for accessor in (0, -1):
                            color = copy_color(colors[accessor])
                            color.hsb.brightness -= (
                                self.darken_exnapsion_symbol_gradient_endpoints
                            )
                            colors[accessor] = color

                    effects.append(
                        EffectGradientOverlay(
                            colors=[
                                GradientColor(
                                    color=color,
                                    location=ceil(idx * step),
                                )
                                for idx, color in enumerate(colors)
                            ],
                            blend_mode="multiply",
                            dither=True,
                            rotation=self.expansion_symbol_gradient_angle,
                            opacity=100,
                            scale=self.expansion_symbol_gradient_scale,
                            # TODO fix typing once pull request is accepted
                            method=self.expansion_symbol_gradient_method,
                        )
                    )

            apply_fx(
                self.expansion_symbol_layer,
                effects,
            )

    def format_nickname_text(self) -> None:
        pass

    def textbox_positioning(self) -> None:
        # Get the delta between the highest box and the target box
        ref_group = getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group)
        ref = (
            get_reference_layer(LAYERS.TEXTLESS, ref_group)
            if self.is_vertical_layout
            else self.textbox_reference
        )
        if ref and (
            shape := get_reference_layer(
                LAYERS.TALL,
                ref_group,
            )
        ):
            dims_ref = get_layer_dimensions(ref)
            dims_obj = get_layer_dimensions(shape)
            delta = dims_ref[Dimensions.Top] - dims_obj[Dimensions.Top]

            # Shift typeline text
            if self.text_layer_type:
                self.text_layer_type.translate(0, delta)

            # Shift expansion symbol
            if CFG.symbol_enabled and self.expansion_symbol_layer:
                self.expansion_symbol_layer.translate(0, delta)

            # Shift indicator
            if self.is_type_shifted and self.indicator_group:
                self.indicator_group.parent.translate(0, delta)

    def pw_enable_loyalty_graphics(self) -> None:
        if self.is_planeswalker:
            self.loyalty_group.visible = True

    @cached_property
    def text_layer_methods(self) -> list[Callable[[None], None]]:
        methods = super().text_layer_methods
        if not self.is_planeswalker:
            methods.remove(self.pw_text_layers)
        return methods

    @property
    def post_text_methods(self) -> list[Callable[[None], None]]:
        methods = super().post_text_methods.copy()
        methods.remove(self.pw_ability_mask)
        if self.is_textless:
            methods.remove(self.textless_adjustments)
        if self.is_token:
            methods.remove(self.token_adjustments)
        if not self.is_planeswalker:
            methods.remove(self.pw_layer_positioning)
        return [
            *methods,
            self.expansion_symbol_handler,
            self.pw_enable_loyalty_graphics,
        ]

    # endregion Text

    # region Transform Methods

    def text_layers_transform_front(self) -> None:
        """Switch font colors on 'Authentic' front face cards."""
        TransformMod.text_layers_transform_front(self)

        # Switch flipside PT to light gray
        if (
            not self.is_authentic_front
            and self.is_flipside_creature
            and self.text_layer_flipside_pt
        ):
            self.text_layer_flipside_pt.textItem.color = get_rgb(*[186, 186, 186])

    # endregion Transform Methods

    # region MDFC Methods

    def text_layers_mdfc_front(self) -> None:
        pass

    # endregion MDFC Methods

    # region Vertical Right

    def frame_layers_vertical_right(self) -> None:
        if layer := getLayerSet(
            f"{LAYER_NAMES.VERTICAL} {LAYERS.RIGHT}",
            [self.pinlines_group, LAYERS.SHAPE],
        ):
            layer.visible = True

    def frame_layers_case(self) -> None:
        self.frame_layers_vertical_right()
        return super().frame_layers_case()

    def frame_layers_classes(self) -> None:
        self.frame_layers_vertical_right()
        return super().frame_layers_classes()

    # endregion Vertical Right

    # region Saga

    def frame_layers_saga(self):
        if layer := getLayerSet(LAYERS.SAGA, [self.pinlines_group, LAYERS.SHAPE]):
            layer.visible = True
        return super().frame_layers_saga()

    # endregion Saga
