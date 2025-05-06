from functools import cached_property
from math import ceil
from typing import Any, Callable, Iterable, Literal, Sequence

from photoshop.api import SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import APP, CFG
from src.enums.layers import LAYERS
from src.enums.mtg import Rarity
from src.enums.settings import BorderlessTextbox
from src.helpers.bounds import get_layer_dimensions
from src.helpers.colors import get_pinline_gradient, get_rgb
from src.helpers.effects import apply_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.helpers.text import get_font_size, get_line_count, set_text_size_and_leading
from src.layouts import AdventureLayout, PlaneswalkerLayout
from src.schema.adobe import EffectGradientOverlay, EffectStroke, LayerEffects
from src.schema.colors import ColorObject, GradientColor
from src.templates.adventure import AdventureMod
from src.templates.planeswalker import PlaneswalkerMod
from src.templates.saga import SagaMod
from src.templates.transform import TransformMod
from src.text_layers import FormattedTextArea, TextField
from src.utils.adobe import LayerObjectTypes, ReferenceLayer

from .backup import BackupAndRestore
from .helpers import (
    LAYER_NAMES,
    ExpansionSymbolOverrideMode,
    FlipDirection,
    copy_color,
    create_shape_layer,
    flip_layer,
    get_numeric_setting,
    is_color_identity,
    parse_hex_color_list,
)
from .utils.text import align_dimension
from .uxp.shape import ShapeOperation, merge_shapes
from .uxp.text import create_text_layer_with_path
from .vertical_mod import VerticalMod


class BorderlessShowcase(VerticalMod, PlaneswalkerMod, AdventureMod, BackupAndRestore):
    # region Constants

    @cached_property
    def predefined_textbox_heights(self) -> dict[str, int]:
        return {
            BorderlessTextbox.Tall: 1230,
            BorderlessTextbox.Normal: 1046,
            BorderlessTextbox.Medium: 866,
            BorderlessTextbox.Short: 661,
        }

    # region Constants

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
    def textbox_height(self) -> float | int:
        return max(get_numeric_setting(CFG, "TEXT", "Textbox.Height", 0), 0)

    @cached_property
    def rules_text_font_size(self) -> float | int:
        return max(get_numeric_setting(CFG, "TEXT", "Rules.Text.Font.Size", 0), 0)

    @cached_property
    def rules_text_padding(self) -> float | int:
        return get_numeric_setting(CFG, "TEXT", "Rules.Text.Padding", 64)

    # endregion settings

    # region Checks

    @cached_property
    def is_adventure(self) -> bool:
        return isinstance(self.layout, AdventureLayout)

    @cached_property
    def is_planeswalker(self) -> bool:
        return isinstance(self.layout, PlaneswalkerLayout)

    @cached_property
    def is_pt_enabled(self) -> bool:
        return self.is_creature

    @cached_property
    def has_flipside_pt(self) -> bool:
        return self.is_transform and self.is_flipside_creature

    @cached_property
    def requires_text_shaping(self) -> bool:
        return self.is_pt_enabled or self.has_flipside_pt or self.is_mdfc

    @cached_property
    def supports_dynamic_textbox_height(self) -> bool:
        return not self.is_vertical_layout and not self.is_planeswalker

    # endregion Checks

    # region Frame Details

    @property
    def art_frame_vertical(self) -> str:
        if self.bottom_border_type == "Full":
            return "Full Art Frame Alt"
        return super().art_frame_vertical

    @cached_property
    def size(self) -> str:
        if self.supports_dynamic_textbox_height and (
            self.textbox_height or self.rules_text_font_size
        ):
            # Return something else than Tall to trigger textbox_positioning
            return BorderlessTextbox.Automatic

        if self.is_adventure:
            # Get the user's preferred setting
            size = str(
                CFG.get_option(
                    section="FRAME",
                    key="Textbox.Size",
                    enum_class=BorderlessTextbox,
                    default=BorderlessTextbox.Automatic,
                )
            )

            # Determine the automatic size
            if size == BorderlessTextbox.Automatic:
                size_map: dict[int, BorderlessTextbox] = {
                    1: BorderlessTextbox.Short,
                    2: BorderlessTextbox.Medium,
                    3: BorderlessTextbox.Normal,
                    4: BorderlessTextbox.Tall,
                }

                # Determine size for left textbox
                test_layer = self.text_layer_rules_adventure
                test_text = self.layout.oracle_text_adventure
                if self.layout.flavor_text_adventure:
                    test_text += f"\r{self.layout.flavor_text_adventure}"
                test_layer.textItem.contents = test_text.replace("\n", "\r")

                num = get_line_count(test_layer, self.docref)
                if self.layout.flavor_text:
                    num += 1

                if num < 4:
                    size_left = 1
                elif num < 6:
                    size_left = 2
                elif num < 8:
                    size_left = 3
                else:
                    size_left = 4

                # Determine size for right textbox
                test_layer = self.text_layer_rules_base
                test_text = self.layout.oracle_text
                if self.layout.flavor_text:
                    test_text += f"\r{self.layout.flavor_text}"
                test_layer.textItem.contents = test_text.replace("\n", "\r")

                num = get_line_count(test_layer, self.docref)
                if self.layout.flavor_text:
                    num += 1

                if num < 12:
                    size_right = 1
                elif num < 14:
                    size_right = 2
                elif num < 16:
                    size_right = 3
                else:
                    size_right = 4

                # Final size is the biggest required
                size = size_map[max(size_left, size_right)]
            return size
        if self.is_planeswalker:
            if self.layout.pw_size > 3:
                return LAYER_NAMES.PW4
            return LAYER_NAMES.PW3
        return super().size

    @cached_property
    def ability_text_spacing(self) -> float | int:
        return self.rules_text_padding

    @cached_property
    def ability_text_scaling_step_sizes(self) -> Sequence[float] | None:
        return (0.4, 0.1, 0.05)

    def process_layout_data(self) -> None:
        if self.is_vertical_creature:
            CFG.symbol_enabled = False
        return super().process_layout_data()

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

    @cached_property
    def rules_text_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.TALL, self.text_group)

    @cached_property
    def textbox_reference_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group)

    @cached_property
    def adventure_pinlines_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.ADVENTURE, self.pinlines_group)

    @cached_property
    def pinlines_shape_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.SHAPE, self.pinlines_group)

    # endregion Groups

    # region Reference Layers

    @cached_property
    def type_reference(self) -> ReferenceLayer | ArtLayer | None:
        if self.size == BorderlessTextbox.Textless and self.is_pt_enabled:
            return self.pt_reference
        return super().type_reference

    @cached_property
    def pt_text_reference(self) -> ReferenceLayer | None:
        """Offsets PT box and flipside PT text."""
        layer_name: str | None = None
        if self.is_creature:
            layer_name = (
                f"{LAYERS.PT_REFERENCE}{' - Flipside' if self.has_flipside_pt else ''}"
            )
        elif self.has_flipside_pt:
            layer_name = f"{LAYERS.PT_REFERENCE} - Noncreature Flipside"
        if layer_name:
            return get_reference_layer(
                layer_name,
                self.text_group,
            )

    @cached_property
    def textbox_reference_base(self) -> ReferenceLayer | None:
        """
        Top edge should touch the bottom edge of pinline shape.
        Bottom edge should thouch the bottom edge of allowed text area.
        Left and right edges should delimit the horizontal centering of text.
        """
        return get_reference_layer(
            f"{LAYER_NAMES.REFERENCE}{f' - {LAYERS.ADVENTURE} {LAYERS.RIGHT}' if self.is_adventure else ''}",
            self.textbox_reference_group,
        )

    @cached_property
    def textbox_overflow_reference(self) -> ReferenceLayer | None:
        """Text is not allowed to go below the top dimension of this shape."""
        ref = getLayer(LAYER_NAMES.OVERFLOW_REFERENCE, self.textbox_reference_group)
        if self.is_mdfc and ref and self.mdfc_front_bottom_shape:
            dims_mdfc = get_layer_dimensions(self.mdfc_front_bottom_shape)
            dims_ref = get_layer_dimensions(ref)
            ref.translate(0, dims_mdfc["top"] - dims_ref["top"])
            ref.visible = False
        return ReferenceLayer(ref)

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        ref: ArtLayer | None = None

        if self.is_planeswalker:
            ref = get_reference_layer(
                self.size,
                self.textbox_reference_group,
            )
        elif (
            self.supports_dynamic_textbox_height
            and self.rules_text_font_size
            and self.text_layer_rules_base
            and self.textbox_reference_base
            and self.text_wrap_reference_base
        ):
            # Adjust textbox to fit rules text of fixed font size
            if right_adjustment := self.adjust_textbox_for_font_size(
                self.text_layer_rules_base,
                self.textbox_reference_base,
                self.text_wrap_reference_base,
                divider_layer=self.divider_layer,
                oracle_text=self.layout.oracle_text,
                flavor_text=self.layout.flavor_text,
            ):
                rules_text, textbox_ref = right_adjustment

                if (
                    self.is_adventure
                    and self.text_layer_rules_adventure
                    and self.textbox_reference_adventure_base
                    and self.text_wrap_reference_adventure_base
                ):
                    # With Adventure cards we need to make sure that
                    # both left and right rules texts fit
                    height_delta = self.textbox_reference_adventure_base.dims["height"]

                    if left_adjustment := self.adjust_textbox_for_font_size(
                        self.text_layer_rules_adventure,
                        self.textbox_reference_adventure_base,
                        self.text_wrap_reference_adventure_base,
                        divider_layer=self.divider_layer,
                        oracle_text=self.layout.oracle_text_adventure,
                        flavor_text=self.layout.flavor_text_adventure,
                        min_top=textbox_ref.dims["top"] + height_delta,
                    ):
                        rules_text_left, textbox_ref_left = left_adjustment
                        left_height = textbox_ref_left.dims["height"] + height_delta

                        if left_height > textbox_ref.dims["height"]:
                            # We need to make the right textbox higher
                            rules_text.remove()
                            textbox_ref.remove()
                            if right_adjustment := self.adjust_textbox_for_font_size(
                                self.text_layer_rules_base,
                                self.textbox_reference_base,
                                self.text_wrap_reference_base,
                                divider_layer=self.divider_layer,
                                oracle_text=self.layout.oracle_text,
                                flavor_text=self.layout.flavor_text,
                                min_top=textbox_ref_left.dims["top"] - height_delta,
                            ):
                                rules_text, textbox_ref = right_adjustment

                            # Some unknown interaction causes textbox_ref_left to turn visible
                            # during the recreation of the right textbox
                            textbox_ref_left.visible = False

                        self.text_layer_rules_adventure = rules_text_left
                        self.textbox_reference_adventure = textbox_ref_left

                self.text_layer_rules = rules_text
                ref = textbox_ref
        elif (
            not self.is_textless
            and self.supports_dynamic_textbox_height
            and self.textbox_reference_base
        ):
            dims = self.textbox_reference_base.dims
            textbox_height = (
                self.textbox_height or self.predefined_textbox_heights[self.size]
            )
            ref_top: float | int = dims["bottom"] - textbox_height
            ref = create_shape_layer(
                [
                    {"x": dims["left"], "y": ref_top},
                    {"x": dims["right"], "y": ref_top},
                    {"x": dims["right"], "y": dims["bottom"]},
                    {"x": dims["left"], "y": dims["bottom"]},
                ],
                hide=True,
            )

        if ref:
            if (
                self.is_mdfc
                # and (
                #     mdfc_mask := getLayer(
                #         LAYERS.MDFC, [self.mask_group, LAYERS.TEXTBOX_REFERENCE]
                #     )
                # )
            ):
                # copy_layer_mask(layer_from=mdfc_mask, layer_to=ref)
                # try:
                #     apply_mask(ref)
                # except COMError as err:
                #     print("Failed to apply MDFC mask", err)
                # ref.visible = False
                duplicate = self.textbox_overflow_reference.duplicate(
                    ref, ElementPlacement.PlaceBefore
                )
                ref = merge_shapes(
                    duplicate, ref, operation=ShapeOperation.SubtractFront
                )
                ref.visible = False
            # Make sure that outdated dimensions aren't cached
            return ReferenceLayer(ref)

        return super().textbox_reference

    @cached_property
    def textbox_reference_adventure_base(self) -> ReferenceLayer | None:
        """
        Bottom edge should thouch the bottom edge of allowed text area.
        Height should indicate how much shorter the left textbox of an Adventure card is
        in comparison to its right textbox, i.e. how much space Adventure name and typeline take.
        Left and right edges should delimit the horizontal centering of text.
        """
        return get_reference_layer(
            f"{LAYER_NAMES.REFERENCE} - {LAYERS.ADVENTURE} {LAYERS.LEFT}",
            self.textbox_reference_group,
        )

    @cached_property
    def textbox_reference_adventure(self) -> ArtLayer | None:
        if self.textbox_reference and self.textbox_reference_adventure_base:
            dims_textbox_ref = self.textbox_reference.dims
            dims_base_ref = self.textbox_reference_adventure_base.dims
            top = dims_textbox_ref["top"] + dims_base_ref["height"]
            return ReferenceLayer(
                create_shape_layer(
                    (
                        {"x": dims_base_ref["left"], "y": top},
                        {"x": dims_base_ref["right"], "y": top},
                        {"x": dims_base_ref["right"], "y": dims_textbox_ref["bottom"]},
                        {"x": dims_base_ref["left"], "y": dims_textbox_ref["bottom"]},
                    ),
                    hide=True,
                )
            )

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
    def name_normal_pinline_shape(self) -> ArtLayer | None:
        if layer_set := getLayerSet(
            LAYERS.NORMAL,
            [self.pinlines_shape_group, LAYERS.NAME],
        ):
            return getLayer(LAYERS.NORMAL, layer_set)

    @cached_property
    def twins_horizontal_delta(self) -> float | int:
        if self.name_normal_pinline_shape:
            dims = get_layer_dimensions(self.name_normal_pinline_shape)
            return APP.activeDocument.width - 2 * dims["center_x"]
        return 0

    @cached_property
    def typeline_pinline_shape(self) -> ArtLayer | None:
        if (
            not self.is_textless
            and not self.is_vertical_layout
            and not self.is_planeswalker
            and (
                layer := getLayer(
                    LAYERS.TALL,
                    [self.pinlines_shape_group, LAYERS.TYPE_LINE],
                )
            )
        ):
            if self.flip_twins:
                # Flip horizontally
                layer.translate(-self.twins_horizontal_delta, 0)
                flip_layer(layer, FlipDirection.Horizontal)
            return layer

    @cached_property
    def pinlines_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        _shape_group = self.pinlines_shape_group

        layers: list[LayerObjectTypes] = []

        # Name
        if self.flip_twins and self.name_normal_pinline_shape:
            # Flip horizontally
            if not (self.is_transform or self.is_mdfc):
                self.name_normal_pinline_shape.translate(self.twins_horizontal_delta, 0)
                flip_layer(self.name_normal_pinline_shape, FlipDirection.Horizontal)
                layers.append(self.name_normal_pinline_shape)
        if (self.is_transform or self.is_mdfc) and (
            layer := getLayerSet(
                LAYERS.TRANSFORM
                if self.is_transform
                else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
                [_shape_group, LAYERS.NAME],
            )
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
        elif not self.is_textless and self.typeline_pinline_shape:
            layers.append(self.typeline_pinline_shape)

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
    def mdfc_front_bottom_shape(self) -> ArtLayer | None:
        return getLayer(
            LAYERS.SHAPE,
            [self.text_group, f"{LAYERS.MDFC} {LAYERS.FRONT}", LAYERS.BOTTOM],
        )

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

    # region Frame

    @cached_property
    def frame_layer_methods(self) -> list[Callable[[], None]]:
        methods = super().frame_layer_methods
        if self.is_adventure:
            methods.append(self.enable_adventure_layers)
        return methods

    # endregion Frame

    # region Text

    @cached_property
    def text_layer_ability(self) -> ArtLayer | None:
        if self.is_planeswalker:
            return super(SagaMod, self).text_layer_ability
        return super().text_layer_ability

    @cached_property
    def text_layer_rules_name(self) -> str:
        return f"{LAYERS.RULES_TEXT}{f' - {LAYERS.ADVENTURE} {LAYERS.RIGHT}' if self.is_adventure else ''}"

    @cached_property
    def text_wrap_reference_base(self) -> ReferenceLayer | None:
        return get_reference_layer(
            f"{LAYER_NAMES.TEXT_REFERENCE}{f' - {LAYERS.ADVENTURE} {LAYERS.RIGHT}' if self.is_adventure else ''}",
            self.rules_text_group,
        )

    @cached_property
    def text_wrap_reference_adventure_base(self) -> ReferenceLayer | None:
        return get_reference_layer(
            f"{LAYER_NAMES.TEXT_REFERENCE}{f' - {LAYERS.ADVENTURE} {LAYERS.LEFT}' if self.is_adventure else ''}",
            self.rules_text_group,
        )

    @cached_property
    def text_wrap_reference(self) -> ReferenceLayer | None:
        if self.textbox_reference and (self.text_wrap_reference_base):
            dims_textbox_ref = self.textbox_reference.dims
            dims_base = self.text_wrap_reference_base.dims
            return ReferenceLayer(
                create_shape_layer(
                    [
                        {"x": dims_base["left"], "y": dims_textbox_ref["top"]},
                        {"x": dims_base["right"], "y": dims_textbox_ref["top"]},
                        {"x": dims_base["right"], "y": dims_textbox_ref["bottom"]},
                        {"x": dims_base["left"], "y": dims_textbox_ref["bottom"]},
                    ],
                    relative_layer=self.text_wrap_reference_base,
                    placement=ElementPlacement.PlaceBefore,
                    hide=True,
                )
            )

    @cached_property
    def text_layer_rules_base(self) -> ArtLayer | None:
        return getLayer(
            self.text_layer_rules_name,
            self.rules_text_group,
        )

    @cached_property
    def text_layer_rules(self) -> ArtLayer | None:
        if self.is_planeswalker:
            return None

        if self.is_vertical_layout:
            return super().text_layer_rules

        if self.supports_dynamic_textbox_height and self.rules_text_font_size:
            raise NotImplementedError("Accessing text layer rules too early.")

        layer = self.text_layer_rules_base
        if (
            self.size != LAYERS.TEXTLESS
            and (self.is_creature or self.has_flipside_pt)
            and layer
            and self.pt_text_reference
            and self.text_wrap_reference
        ):
            pt_ref_copy = self.pt_text_reference.duplicate(
                self.text_wrap_reference, ElementPlacement.PlaceBefore
            )
            textbox_ref_shape = merge_shapes(
                pt_ref_copy,
                self.text_wrap_reference,
                operation=ShapeOperation.SubtractFront,
            )
            layer = create_text_layer_with_path(textbox_ref_shape, layer)
        return layer

    @cached_property
    def text_layer_flipside_pt(self) -> ArtLayer | None:
        if self.is_layout_saga:
            return getLayer(LAYERS.FLIPSIDE_POWER_TOUGHNESS, self.saga_group)
        return getLayer(LAYERS.FLIPSIDE_POWER_TOUGHNESS, self.text_group)

    @cached_property
    def text_layer_name_adventure(self) -> ArtLayer | None:
        return getLayer(LAYERS.NAME_ADVENTURE, self.rules_text_group)

    @cached_property
    def text_layer_mana_adventure(self) -> ArtLayer | None:
        return getLayer(LAYERS.MANA_COST_ADVENTURE, self.rules_text_group)

    @cached_property
    def text_layer_type_adventure(self) -> ArtLayer | None:
        return getLayer(LAYERS.TYPE_LINE_ADVENTURE, self.rules_text_group)

    @cached_property
    def text_layer_rules_adventure(self) -> ArtLayer | None:
        return getLayer(LAYERS.RULES_TEXT_ADVENTURE, self.rules_text_group)

    @cached_property
    def divider_layer_adventure(self) -> ArtLayer | None:
        return None

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

    def format_temp_rules_text(
        self,
        layer: ArtLayer,
        divider_layer: ArtLayer | None,
        oracle_text: str,
        flavor_text: str | None,
    ) -> None:
        set_text_size_and_leading(
            layer, self.rules_text_font_size, self.rules_text_font_size
        )
        text_field = TextField(
            layer=layer,
            contents=oracle_text,
            flavor=flavor_text,
            divider=divider_layer,
        )
        if not text_field.validate():
            raise ValueError("Rules text layer is invalid.")
        text_field.execute()

    def adjust_textbox_for_font_size(
        self,
        base_text_layer: ArtLayer,
        base_textbox_reference: ReferenceLayer,
        base_text_wrap_reference: ReferenceLayer,
        divider_layer: ArtLayer | None,
        oracle_text: str,
        flavor_text: str | None,
        min_top: float | int | None = None,
    ) -> tuple[ArtLayer, ReferenceLayer] | None:
        """Calculates the required size for rules textbox when the rules text has a fixed font size."""
        doc_height: float | int = APP.activeDocument.height
        min_top = min_top if min_top is not None else doc_height

        # Set and format rules text
        self.format_temp_rules_text(
            base_text_layer, divider_layer, oracle_text, flavor_text
        )

        # Move text layer just above the point where text is allowed to be
        dims_textbox_ref = base_textbox_reference.dims
        align_dimension(
            base_text_layer,
            reference_dimensions=dims_textbox_ref,
            alignment_dimension="bottom",
        )

        # Apply shape to the text that offsets PT elements but allows overflow at bottom
        dims_wrap_ref = base_text_wrap_reference.dims
        min_pt_top = self.pt_reference.dims["top"] if self.pt_reference else doc_height
        dims_rules_text = get_layer_dimensions(base_text_layer)
        top = min(
            dims_rules_text["top"] - self.rules_text_padding,
            min_pt_top,
            min_top,
        )
        bottom = doc_height + 500
        text_ref_shape = create_shape_layer(
            (
                {"x": dims_wrap_ref["left"], "y": top},
                {"x": dims_wrap_ref["right"], "y": top},
                {"x": dims_wrap_ref["right"], "y": bottom},
                {"x": dims_wrap_ref["left"], "y": bottom},
            ),
            hide=True,
        )
        if self.requires_text_shaping and self.pt_text_reference:
            pt_ref_copy = self.pt_text_reference.duplicate(
                text_ref_shape, ElementPlacement.PlaceBefore
            )
            text_ref_shape = merge_shapes(
                pt_ref_copy, text_ref_shape, operation=ShapeOperation.SubtractFront
            )
        shaped_text = create_text_layer_with_path(text_ref_shape, base_text_layer)
        self.format_temp_rules_text(
            shaped_text, divider_layer, oracle_text, flavor_text
        )

        # Check for overflow after offsetting PT elements
        # and reserve more space for text if necessary.
        if (
            self.requires_text_shaping
            and self.textbox_overflow_reference
            and (dims_shaped_text := get_layer_dimensions(shaped_text))
            and (
                delta := self.textbox_overflow_reference.dims["top"]
                - dims_shaped_text["bottom"]
            )
            < 0
        ):
            for layer in (text_ref_shape, shaped_text):
                layer.remove()

            top += delta - self.rules_text_padding
            text_ref_shape = create_shape_layer(
                (
                    {"x": dims_wrap_ref["left"], "y": top},
                    {"x": dims_wrap_ref["right"], "y": top},
                    {"x": dims_wrap_ref["right"], "y": bottom},
                    {"x": dims_wrap_ref["left"], "y": bottom},
                ),
                hide=True,
            )

            if self.pt_text_reference:
                pt_ref_copy = self.pt_text_reference.duplicate(
                    text_ref_shape, ElementPlacement.PlaceBefore
                )
                text_ref_shape = merge_shapes(
                    pt_ref_copy, text_ref_shape, operation=ShapeOperation.SubtractFront
                )

            shaped_text = create_text_layer_with_path(text_ref_shape, base_text_layer)

        base_text_layer.visible = False
        dims_text_ref_shape = get_layer_dimensions(text_ref_shape)
        return (
            shaped_text,
            ReferenceLayer(
                create_shape_layer(
                    (
                        {
                            "x": dims_textbox_ref["left"],
                            "y": dims_text_ref_shape["top"],
                        },
                        {
                            "x": dims_textbox_ref["right"],
                            "y": dims_text_ref_shape["top"],
                        },
                        {
                            "x": dims_textbox_ref["right"],
                            "y": dims_textbox_ref["bottom"],
                        },
                        {
                            "x": dims_textbox_ref["left"],
                            "y": dims_textbox_ref["bottom"],
                        },
                    ),
                    hide=True,
                )
            ),
        )

    def rules_text_and_pt_layers(self) -> None:
        if self.is_planeswalker:
            if self.text_layer_rules_base:
                self.text_layer_rules_base.visible = False
            return

        super().rules_text_and_pt_layers()

        if (
            self.supports_dynamic_textbox_height
            and self.rules_text_font_size
            and self.text_layer_rules
        ):
            # Ensure that rules text font size won't be adjusted
            for entry in self.text:
                if (
                    isinstance(entry, FormattedTextArea)
                    and entry.layer is self.text_layer_rules
                ):
                    set_text_size_and_leading(
                        self.text_layer_rules,
                        self.rules_text_font_size,
                        self.rules_text_font_size,
                    )
                    entry.kwargs.update(
                        {
                            "scale_height": False,
                            "scale_width": False,
                            "fix_overflow_height": False,
                            "fix_overflow_width": False,
                        }
                    )
                    break

    def textbox_positioning(self) -> None:
        # Get the delta between the highest box and the target box
        ref_group = getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group)
        ref = (
            get_reference_layer(LAYERS.TEXTLESS, ref_group)
            if self.is_vertical_layout
            else self.textbox_reference
        )
        if ref and self.textbox_reference_base:
            delta = ref.dims["top"] - self.textbox_reference_base.dims["top"]

            # Shift typeline text
            if self.text_layer_type:
                self.text_layer_type.translate(0, delta)

            # Shift typeline pinline
            if self.typeline_pinline_shape:
                self.typeline_pinline_shape.translate(0, delta)

            # Shift expansion symbol
            if CFG.symbol_enabled and self.expansion_symbol_layer:
                self.expansion_symbol_layer.translate(0, delta)

            # Shift indicator
            if self.is_type_shifted and self.indicator_group:
                self.indicator_group.parent.translate(0, delta)

            # Shift relevant Adventure layers
            if self.is_adventure:
                for layer in (
                    self.text_layer_name_adventure,
                    self.text_layer_mana_adventure,
                    self.text_layer_type_adventure,
                    self.adventure_pinlines_group,
                ):
                    if layer:
                        layer.translate(0, delta)

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
        methods = super().post_text_methods
        methods.remove(self.pw_ability_mask)
        if self.is_textless:
            methods.remove(self.textless_adjustments)
        if self.is_token:
            methods.remove(self.token_adjustments)
        if not self.is_planeswalker:
            methods.remove(self.pw_layer_positioning)
        if self.is_adventure and not self.rules_text_font_size:
            methods.append(self.match_adventure_font_sizes)
        return [
            *methods,
            self.expansion_symbol_handler,
            self.pw_enable_loyalty_graphics,
        ]

    # endregion Text

    # region Transform

    def text_layers_transform_front(self) -> None:
        TransformMod.text_layers_transform_front(self)

        # Switch flipside PT to light gray
        if (
            not self.is_authentic_front
            and self.is_flipside_creature
            and self.text_layer_flipside_pt
        ):
            self.text_layer_flipside_pt.textItem.color = get_rgb(*[186, 186, 186])

    # endregion Transform

    # region MDFC

    def text_layers_mdfc_front(self) -> None:
        pass

    # endregion MDFC

    # region Adventure

    def enable_adventure_layers(self) -> None:
        if self.adventure_pinlines_group:
            self.adventure_pinlines_group.visible = True
            self.generate_layer(
                group=self.adventure_pinlines_group,
                colors=self.pinlines_color_map.get(
                    "".join(self.layout.color_identity_adventure)
                ),
            )

    def text_layers_adventure(self) -> None:
        super().text_layers_adventure()

        if self.rules_text_font_size and self.text_layer_rules_adventure:
            # Ensure that rules text font size won't be adjusted
            for entry in self.text:
                if (
                    isinstance(entry, FormattedTextArea)
                    and entry.layer is self.text_layer_rules_adventure
                ):
                    set_text_size_and_leading(
                        self.text_layer_rules_adventure,
                        self.rules_text_font_size,
                        self.rules_text_font_size,
                    )
                    entry.kwargs.update(
                        {
                            "scale_height": False,
                            "scale_width": False,
                            "fix_overflow_height": False,
                            "fix_overflow_width": False,
                        }
                    )
                    break

    def match_adventure_font_sizes(self) -> None:
        """Sets the same font size for both Adventure rules texts."""
        if self.text_layer_rules_adventure and self.text_layer_rules:
            if get_font_size(self.text_layer_rules_adventure) == get_font_size(
                self.text_layer_rules
            ):
                return

            rules_text_layers = [self.text_layer_rules_adventure, self.text_layer_rules]
            rules_text_layers.sort(key=lambda layer: get_font_size(layer))
            layer_to_adjust = rules_text_layers[1]

            for entry in self.text:
                if (
                    isinstance(entry, FormattedTextArea)
                    and entry.layer is layer_to_adjust
                ):
                    smaller_font_size: float | int = get_font_size(rules_text_layers[0])
                    set_text_size_and_leading(
                        layer_to_adjust, smaller_font_size, smaller_font_size
                    )
                    text_area = FormattedTextArea(
                        layer_to_adjust,
                        contents=entry.contents,
                        **{
                            **entry.kwargs,
                            "scale_height": False,
                            "scale_width": False,
                            "fix_overflow_height": False,
                            "fix_overflow_width": False,
                        },
                    )
                    if text_area.validate():
                        text_area.execute()

    # endregion Adventure

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
