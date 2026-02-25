from collections.abc import Callable, Iterable, Sequence
from functools import cached_property
from logging import getLogger
from math import ceil
from typing import Literal, NotRequired, TypedDict

from photoshop.api import SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api._selection import Selection
from photoshop.api.enumerations import BlendMode, ElementPlacement, SelectionType

from src.cards import strip_reminder_text
from src.enums.layers import LAYERS
from src.enums.mtg import Rarity
from src.enums.settings import BorderlessTextbox
from src.helpers.adjustments import create_color_layer
from src.helpers.bounds import (
    LayerDimensions,
    get_group_dimensions,
    get_layer_dimensions,
)
from src.helpers.colors import get_pinline_gradient, get_rgb, rgb_black
from src.helpers.effects import apply_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet, select_layer
from src.helpers.masks import apply_mask_to_layer_fx
from src.helpers.text import (
    get_font_size,
    get_line_count,
    set_text_size_and_leading,
)
from src.layouts import (
    AdventureLayout,
    BattleLayout,
    LevelerLayout,
    MutateLayout,
    PlaneswalkerLayout,
    PrototypeLayout,
    SplitLayout,
    StationLayout,
)
from src.schema.adobe import (
    EffectGradientOverlay,
    EffectStroke,
    GradientMethod,
    LayerEffects,
)
from src.schema.colors import ColorObject, GradientColor, GradientConfig
from src.templates._vector import MaskAction
from src.templates.adventure import AdventureMod
from src.templates.leveler import LevelerMod
from src.templates.normal import BorderlessVectorTemplate
from src.templates.planeswalker import PlaneswalkerMod
from src.templates.saga import SagaMod
from src.templates.split import SplitMod
from src.templates.station import StationMod
from src.templates.transform import TransformMod
from src.text_layers import FormattedTextArea, FormattedTextField, TextField
from src.utils.adobe import LayerObjectTypes, ReferenceLayer

from .backup import BackupAndRestore
from .helpers import (
    LAYER_NAMES,
    ExpansionSymbolOverrideMode,
    FlipDirection,
    copy_color,
    create_clipping_mask,
    flip_layer,
    get_numeric_setting,
    is_color_identity,
    parse_hex_color_list,
)
from .utils.colors import (
    create_gradient_config,
    create_gradient_location_map,
)
from .utils.layer import TemporaryLayerCopy, get_layer_dimensions_via_rasterization
from .utils.layer_fx import get_stroke_details
from .utils.path import check_layer_overlap_with_shape, create_shape_layer
from .utils.text import align_dimension
from .uxp.path import PathPointConf
from .uxp.shape import ShapeOperation, merge_shapes
from .uxp.text import CreateTextLayerWithPathOptions, create_text_layer_with_path
from .vertical_mod import VerticalMod

_logger = getLogger(__name__)


class TextboxSizingArgs(TypedDict):
    base_text_layer: ArtLayer
    base_textbox_reference: ReferenceLayer
    base_text_wrap_reference: ReferenceLayer
    divider_layer: ArtLayer | LayerSet | None
    oracle_text: str
    flavor_text: str | None
    min_top: NotRequired[float | int | None]
    height_padding: NotRequired[float | int | None]


class BorderlessShowcase(
    SplitMod,
    VerticalMod,
    PlaneswalkerMod,
    AdventureMod,
    LevelerMod,
    StationMod,
    BackupAndRestore,
):
    # region Constants

    @cached_property
    def gradient_location_map(self) -> dict[int, list[float | int]]:
        return (
            {
                2: [0.48, 0.52],
                3: [0.25, 0.30, 0.70, 0.75],
                4: [0.25, 0.30, 0.48, 0.52, 0.70, 0.75],
                5: [0.20, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.80],
            }
            if self.is_split
            else super().gradient_location_map
        )

    @cached_property
    def predefined_textbox_heights(self) -> dict[str, int]:
        return {
            BorderlessTextbox.Tall: 1230,
            BorderlessTextbox.Normal: 1046,
            BorderlessTextbox.Medium: 866,
            BorderlessTextbox.Short: 661,
        }

    @cached_property
    def rules_text_default_options(self) -> CreateTextLayerWithPathOptions:
        return {"size": 9, "leading": 9}

    # region Constants

    # region Settings

    @cached_property
    def is_content_aware_enabled(self) -> bool:
        return self.config.get_bool_setting(
            section="ART", key="Content.Aware.Fill", default=True
        )

    @cached_property
    def color_limit(self) -> int:
        return (
            self.config.get_int_setting(section="COLORS", key="Max.Colors", default=2)
            + 1
        )

    @cached_property
    def front_face_colors(self) -> bool:
        """Returns True if lighter color map should be used on front face DFC cards."""
        return self.config.get_bool_setting(
            section="COLORS", key="Front.Face.Colors", default=True
        )

    @cached_property
    def multicolor_pinlines(self) -> bool:
        """Returns True if Pinlines for multicolored cards should use blended colors."""
        return self.config.get_bool_setting(
            section="COLORS", key="Multicolor.Pinlines", default=True
        )

    @cached_property
    def pinlines_color_override(self) -> list[SolidColor]:
        if setting := self.config.get_setting(
            section="COLORS", key="Pinlines.Override", default=None
        ):
            return parse_hex_color_list(setting, _logger)
        return []

    @cached_property
    def expansion_symbol_color_override(self) -> ExpansionSymbolOverrideMode:
        if setting := self.config.get_setting(
            section="COLORS",
            key="Expansion.Symbol.Override",
            default=None,
            is_bool=False,
        ):
            if setting == "Identity":
                return ExpansionSymbolOverrideMode.Identity
            if setting == "Pinlines override":
                return ExpansionSymbolOverrideMode.Pinlines
            if setting == "Custom":
                return ExpansionSymbolOverrideMode.Custom
        return ExpansionSymbolOverrideMode.Off

    @cached_property
    def expansion_symbol_custom_colors(self) -> list[SolidColor]:
        if setting := self.config.get_setting(
            section="COLORS",
            key="Expansion.Symbol.Custom",
            default=None,
            is_bool=False,
        ):
            return parse_hex_color_list(setting, _logger)
        return []

    @cached_property
    def darken_exnapsion_symbol_gradient_endpoints(self) -> float:
        return get_numeric_setting(
            self.config, "COLORS", "Expansion.Symbol.Darken", 0, (0, 100)
        )

    @cached_property
    def expansion_symbol_gradient_angle(self) -> float:
        return get_numeric_setting(
            self.config, "COLORS", "Expansion.Symbol.Angle", 0, (-360, 360)
        )

    @cached_property
    def expansion_symbol_gradient_scale(self) -> float:
        return get_numeric_setting(
            self.config, "COLORS", "Expansion.Symbol.Scale", 70, (10, 150)
        )

    @cached_property
    def expansion_symbol_gradient_method(self) -> GradientMethod:
        if (
            setting := self.config.get_setting(
                section="COLORS",
                key="Expansion.Symbol.Method",
                default=None,
                is_bool=False,
            )
        ) and setting in ("perceptual", "linear", "classic", "smooth", "stripes"):
            return setting
        return "linear"

    @cached_property
    def pt_box_and_bottom_pinline_type(self) -> Literal["Full", "Partial", "Split"]:
        setting = self.config.get_setting(
            section="SHAPES", key="PT.Box.And.Pinline", default="Full", is_bool=False
        )
        if setting in ("Full", "Partial", "Split"):
            return setting
        raise ValueError(
            f"Received invalid value for PT box and bottom pinline type: {setting}"
        )

    @cached_property
    def bottom_border_type(self) -> Literal["Full", "Fade", "Shadow"] | None:
        setting = self.config.get_setting(
            section="SHAPES", key="Bottom.Border", default="Full", is_bool=False
        )
        if setting in ("Full", "Fade", "Shadow"):
            return setting
        if setting == "None":
            return None
        raise ValueError(f"Received invalid value for bottom border type: {setting}")

    @cached_property
    def flip_twins(self) -> bool:
        return self.config.get_bool_setting(
            section="SHAPES", key="Flip.Twins", default=False
        )

    @cached_property
    def textbox_height(self) -> float | int:
        if self.is_vertical_creature:
            # There's no support for an extra textbox for Saga creatures
            return 0
        return super().textbox_height

    @cached_property
    def rules_text_font_size(self) -> float | int:
        return max(
            get_numeric_setting(self.config, "TEXT", "Rules.Text.Font.Size", 0), 0
        )

    @cached_property
    def rules_text_padding(self) -> float | int:
        return get_numeric_setting(self.config, "TEXT", "Rules.Text.Padding", 64)

    @cached_property
    def drop_shadow_enabled(self) -> bool:
        return False

    # endregion Settings

    # region Checks

    @cached_property
    def is_creature(self) -> bool:
        return self.is_battle or super().is_creature

    @cached_property
    def is_adventure(self) -> bool:
        return isinstance(self.layout, AdventureLayout)

    @cached_property
    def is_battle(self) -> bool:
        return isinstance(self.layout, BattleLayout)

    @cached_property
    def is_planeswalker(self) -> bool:
        return isinstance(self.layout, PlaneswalkerLayout)

    @cached_property
    def is_leveler(self) -> bool:
        return isinstance(self.layout, LevelerLayout)

    @cached_property
    def is_prototype(self) -> bool:
        return isinstance(self.layout, PrototypeLayout)

    @cached_property
    def is_pt_enabled(self) -> bool:
        return self.is_creature

    @cached_property
    def is_textless(self) -> bool:
        return not any((self.layout.oracle_text, self.layout.flavor_text))

    @cached_property
    def has_displaced_pt_box(self) -> bool:
        return self.is_leveler or self.is_station

    @cached_property
    def has_flipside_pt(self) -> bool:
        return self.is_transform and self.is_front and self.is_flipside_creature

    @cached_property
    def requires_text_shaping(self) -> bool:
        return (
            (self.is_pt_enabled and not isinstance(self.layout, StationLayout))
            or self.has_flipside_pt
            or self.is_mdfc
        )

    @cached_property
    def supports_dynamic_textbox_height(self) -> bool:
        return (
            not self.is_vertical_layout
            and not self.is_planeswalker
            and not self.is_leveler
        )

    @cached_property
    def is_centered(self) -> bool:
        if self.is_station:
            return False
        return super().is_centered

    # endregion Checks

    # region Frame Details

    @cached_property
    def doc_height(self) -> int | float:
        assert self.docref
        return self.docref.height

    @cached_property
    def doc_width(self) -> int | float:
        assert self.docref
        return self.docref.width

    @cached_property
    def art_frame_vertical(self) -> str:
        if self.bottom_border_type == "Full":
            return "Full Art Frame Alt"
        return super().art_frame_vertical

    @cached_property
    def size(self) -> str:
        if self.is_textless:
            return BorderlessTextbox.Textless
        elif self.supports_dynamic_textbox_height and (
            self.textbox_height or self.rules_text_font_size
        ):
            # Return something else than Tall to trigger textbox_positioning
            return BorderlessTextbox.Automatic
        elif self.is_split or self.is_leveler or self.is_station:
            # Disables textbox_positioning
            return BorderlessTextbox.Tall

        if isinstance(self.layout, AdventureLayout):
            # Get the user's preferred setting
            size = str(
                self.config.get_option(
                    section="FRAME",
                    key="Textbox.Size",
                    enum_class=BorderlessTextbox,
                    default=BorderlessTextbox.Automatic,
                )
            )

            # Determine the automatic size
            if size == BorderlessTextbox.Automatic:
                if self.text_layer_rules_adventure and self.text_layer_rules_base:
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
                else:
                    return BorderlessTextbox.Tall
            return size
        if isinstance(self.layout, PlaneswalkerLayout):
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
            self.config.symbol_enabled = False

        super().process_layout_data()

        if isinstance(self.layout, MutateLayout):
            # Render mutate text like any other rules text
            self.layout.oracle_text = (
                strip_reminder_text(self.layout.mutate_text)
                if self.config.remove_reminder
                else self.layout.mutate_text
            ) + f"\n{self.layout.oracle_text}"

    def override_set_symbol(self) -> None:
        if self.expansion_symbol_color_override is not ExpansionSymbolOverrideMode.Off:
            # Common symbol is used since it can be inverted to get
            # a white symbol with black lines, which is easy to tint with other colors
            self.layout.rarity_letter = Rarity.C[0].upper()

    @cached_property
    def pre_render_methods(self) -> list[Callable[[], None]]:
        return [*super().pre_render_methods, self.override_set_symbol]

    # endregion Frame Details

    # region Artwork

    @cached_property
    def art_fill_selection_hook(
        self,
    ) -> Callable[[ArtLayer, Selection], None] | None:
        if (
            self.bottom_border_type == "Full"
            and self.art_reference
            and self.art_reference.name.startswith("Full")
            and (overflow_ref := self.textbox_overflow_reference_base)
        ):
            bounds = overflow_ref.bounds

            def hook(art_layer: ArtLayer, selection: Selection) -> None:
                # Avoid unnecessary filling at edges if the image reaches that far
                selection.expand(1)
                selection.contract(1)

                bounds_art_layer = art_layer.bounds
                top_padded = bounds[1] - 2
                area = (
                    (bounds_art_layer[0], top_padded),
                    (bounds_art_layer[2], top_padded),
                    (bounds_art_layer[2], bounds[3]),
                    (bounds_art_layer[0], bounds[3]),
                    (bounds_art_layer[0], top_padded),
                )
                selection.select(area, selection_type=SelectionType.ExtendSelection)

            return hook

    # endregion Artwork

    # region Backup

    @property
    def layers_to_seek_masks_from(self) -> Iterable[ArtLayer | LayerSet | None]:
        if self.docref:
            return (*self.docref.layerSets, *self.docref.artLayers)
        return []

    @property
    def layers_to_copy(self) -> Iterable[ArtLayer | LayerSet | None]:
        return [*super().layers_to_copy, getLayer("Remove tool edits")]

    # endregion Backup

    # region Colors

    @cached_property
    def pinlines_color_map_override(self) -> dict[str, ColorObject]:
        if override := self.pinlines_color_override:
            color_map: dict[str, ColorObject] = {}
            for idx, color in enumerate(override):
                color_map[str(idx)] = color
            return color_map
        return self.pinlines_color_map

    @cached_property
    def pinlines_color_identity_override(self) -> str:
        if self.pinlines_color_override:
            return "".join(self.pinlines_color_map_override.keys())
        return self.identity

    @cached_property
    def pt_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        return self.pinlines_colors

    _gradient_start_location: float = 0.05

    @cached_property
    def pinlines_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        if self.pinlines_color_override:
            location_map: dict[int, list[int | float]] | None = (
                create_gradient_location_map(
                    steps,
                    self._gradient_start_location,
                    1 - self._gradient_start_location,
                )
                if (steps := len(self.pinlines_color_identity_override)) > 5
                else None
            )
            return get_pinline_gradient(
                colors=self.pinlines_color_identity_override,
                color_map=self.pinlines_color_map_override,
                location_map=location_map,
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

    @cached_property
    def mdfc_front_bottom_group(self) -> LayerSet | None:
        return getLayerSet(
            LAYERS.BOTTOM, [self.text_group, f"{LAYERS.MDFC} {LAYERS.FRONT}"]
        )

    # endregion Groups

    # region Reference Layers

    @cached_property
    def type_reference(self) -> ReferenceLayer | ArtLayer | None:
        if self.size == BorderlessTextbox.Textless and self.is_pt_enabled:
            return self.pt_reference
        return super().type_reference

    @cached_property
    def pt_reference_base(self) -> ReferenceLayer | None:
        return super().pt_reference

    @cached_property
    def pt_reference(self) -> ReferenceLayer | None:
        if self.is_battle:
            return get_reference_layer(
                f"{LAYERS.PT_REFERENCE} - {LAYER_NAMES.BATTLE}", self.text_group
            )

        refs: list[ArtLayer] = []

        if self.is_creature and self.pt_reference_base:
            duplicate = self.pt_reference_base.duplicate(
                self.pt_reference_base, ElementPlacement.PlaceAfter
            )
            duplicate.visible = False
            refs.append(duplicate)

        if self.has_flipside_pt and (
            layer := getLayer(f"{LAYERS.PT_REFERENCE} - Flipside", self.text_group)
        ):
            refs.append(layer)

            # Reserve space for flipide PT text
            if self.text_layer_flipside_pt:
                # Format flipside PT text
                for idx, txt in enumerate(reversed(self.text)):
                    if txt.layer is self.text_layer_flipside_pt:
                        self.text.pop(idx)
                        if txt.validate():
                            txt.execute()

                # Create a shape that encompasses flipside PT text
                flipside_ref_dims = get_layer_dimensions(layer)
                flipside_pt_dims = get_layer_dimensions_via_rasterization(
                    self.text_layer_flipside_pt
                )
                rules_stroke_size = (
                    (get_stroke_details(self.text_layer_rules_base) or {}).get(
                        "size", 0
                    )
                    if self.text_layer_rules_base
                    else 0
                )
                padded_left = flipside_pt_dims["left"] - rules_stroke_size
                padded_top = flipside_pt_dims["top"] - rules_stroke_size
                refs.append(
                    create_shape_layer(
                        (
                            {
                                "x": padded_left,
                                "y": padded_top,
                            },
                            {"x": flipside_ref_dims["right"], "y": padded_top},
                            {
                                "x": flipside_ref_dims["right"],
                                "y": flipside_ref_dims["bottom"],
                            },
                            {
                                "x": padded_left,
                                "y": flipside_ref_dims["bottom"],
                            },
                        ),
                        relative_layer=layer,
                        placement=ElementPlacement.PlaceAfter,
                    )
                )

        if refs:
            if len(refs) > 1:
                merged = merge_shapes(*refs, operation=ShapeOperation.Unite)
                merged.visible = False
                return ReferenceLayer(merged)
            return ReferenceLayer(refs[0])

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
    def textbox_overflow_reference_base(self) -> ArtLayer | None:
        return getLayer(LAYER_NAMES.OVERFLOW_REFERENCE, self.textbox_reference_group)

    @cached_property
    def textbox_overflow_reference(self) -> ReferenceLayer | None:
        """Text is not allowed to go below the top dimension of this shape."""
        ref = self.textbox_overflow_reference_base
        if self.is_mdfc and ref and self.mdfc_front_bottom_group:
            dims_mdfc = get_layer_dimensions_via_rasterization(
                self.mdfc_front_bottom_group
            )
            dims_ref = get_layer_dimensions(ref)
            ref.translate(0, dims_mdfc["top"] - dims_ref["top"])
            ref.visible = False
        elif self.is_fuse and ref and self.fuse_reference:
            dims_fuse = self.fuse_reference.dims
            dims_ref = get_layer_dimensions(ref)
            ref.translate(0, dims_fuse["top"] - dims_ref["top"])
            ref.visible = False
        return ReferenceLayer(ref)

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_leveler:
            return get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE} - Level Text", self.leveler_group
            )

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
        ):
            if isinstance(self.layout, StationLayout):
                if self.station_group:
                    self.station_group.visible = True

                textbox_ref = self.station_levels_base_text_references[0]
                stations_len = len(self.layout.stations)

                adjusted_text_layers: list[ArtLayer] = []

                # Adjust Station levels
                for i in reversed(range(stations_len)):
                    details = self.layout.stations[i]
                    level_group = self.station_level_groups[i]
                    level_text = self.station_level_text_layers[i]
                    level_text_ref = self.station_levels_base_text_references[i]
                    requirement_group = self.station_requirement_groups[i]
                    pt_group = self.station_pt_groups[i]

                    dims_req_group = get_group_dimensions(requirement_group)

                    sized = self.adjust_textbox_for_font_size(
                        base_text_layer=level_text,
                        base_textbox_reference=textbox_ref,
                        base_text_wrap_reference=level_text_ref,
                        divider_layer=None,
                        oracle_text=details["ability"],
                        flavor_text=None,
                        min_top=textbox_ref.dims["bottom"]
                        - dims_req_group["height"]
                        - self.rules_text_padding,
                        alignment_dimension=None,
                        vertical_padding=(0, self.rules_text_padding / 2),
                    )

                    if sized:
                        text_layer = sized[0]

                        self.align_center_ys(requirement_group, text_layer)
                        if "pt" in details:
                            self.align_center_ys(pt_group, text_layer)

                        adjusted_text_layers.insert(0, text_layer)

                        text_ref = sized[1]
                        dims_req_group = get_group_dimensions(requirement_group)
                        next_bottom = min(text_ref.dims["top"], dims_req_group["top"])
                        next_ref = (
                            self.textbox_reference_base.duplicate(
                                self.textbox_reference_base,
                                ElementPlacement.PlaceBefore,
                            )
                            if i == 0
                            else self.station_levels_base_text_references[i - 1]
                        )
                        temp_shape = create_shape_layer(
                            (
                                {"x": 0, "y": next_bottom},
                                {"x": self.doc_width, "y": next_bottom},
                                {"x": self.doc_width, "y": self.doc_height},
                                {"x": 0, "y": self.doc_height},
                            ),
                            relative_layer=next_ref,
                            placement=ElementPlacement.PlaceBefore,
                        )

                        # Next rules text section needs to be placed on top of this one,
                        # so we have to adjust it's text reference.
                        textbox_ref = ReferenceLayer(
                            merge_shapes(
                                temp_shape,
                                next_ref,
                                operation=ShapeOperation.SubtractFront,
                            )
                        )
                        textbox_ref.visible = False
                    else:
                        raise ValueError(
                            f"Station textbox sizing failed for {level_group.name}"
                        )

                self.station_level_text_layers = adjusted_text_layers

                # Adjust normal rules text
                if sized := self.adjust_textbox_for_font_size(
                    base_text_layer=self.text_layer_rules_base,
                    base_textbox_reference=textbox_ref,
                    base_text_wrap_reference=textbox_ref,
                    divider_layer=None,
                    oracle_text=self.layout.oracle_text,
                    flavor_text=None,
                ):
                    rules_text, textbox_ref = sized
                    self.text_layer_rules = rules_text
                    ref = textbox_ref
                else:
                    raise ValueError(
                        "Station textbox sizing failed for normal rules text"
                    )
            else:
                textboxes_to_adjust: list[TextboxSizingArgs] = [
                    {
                        "base_text_layer": self.text_layer_rules_base,
                        "base_textbox_reference": self.textbox_reference_base,
                        "base_text_wrap_reference": self.textbox_reference_base,
                        "divider_layer": self.divider_layer,
                        "oracle_text": self.layout.oracle_text,
                        "flavor_text": self.layout.flavor_text,
                    }
                ]

                if (
                    isinstance(self.layout, AdventureLayout)
                    and self.text_layer_rules_adventure
                    and self.textbox_reference_adventure_base
                ):
                    # With Adventure cards we need to make sure that
                    # both left and right rules texts fit
                    height_delta = self.textbox_reference_adventure_base.dims["height"]
                    textboxes_to_adjust.append(
                        {
                            "base_text_layer": self.text_layer_rules_adventure,
                            "base_textbox_reference": self.textbox_reference_adventure_base,
                            "base_text_wrap_reference": self.textbox_reference_adventure_base,
                            "divider_layer": self.divider_layer,
                            "oracle_text": self.layout.oracle_text_adventure,
                            "flavor_text": self.layout.flavor_text_adventure,
                            "height_padding": height_delta,
                        }
                    )

                # Adjust textboxes to fit rules text of fixed font size
                sized_boxes = self.adjust_textboxes_for_font_size(
                    self.rules_text_font_size, textboxes_to_adjust
                )

                rules_text, textbox_ref = sized_boxes[0]
                self.text_layer_rules = rules_text
                ref = textbox_ref

                if self.is_adventure:
                    rules_text_left, textbox_ref_left = sized_boxes[1]

                    self.text_layer_rules_adventure = rules_text_left
                    self.textbox_reference_adventure = textbox_ref_left
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
                relative_layer=self.textbox_reference_group,
                placement=ElementPlacement.PlaceInside,
            )

        if ref:
            if (
                self.is_mdfc and self.textbox_overflow_reference
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

    @cached_property
    def textless_bottom_reference_layer(self) -> ReferenceLayer | None:
        return get_reference_layer(LAYERS.TEXTLESS, self.textbox_reference_group)

    # endregion Reference Layers

    # region Shapes

    @cached_property
    def pt_box_shape(self) -> list[ArtLayer | None]:
        if not self.is_pt_enabled or self.has_displaced_pt_box:
            return [None]

        if self.bottom_border_type == "Full":
            pt_name = "Full"
        elif self.bottom_border_type == "Fade":
            pt_name = "Partial"
        else:
            pt_name = self.pt_box_and_bottom_pinline_type

        # Battle does not support split defense box
        if self.is_battle and pt_name == "Split":
            pt_name = "Partial"

        return [
            getLayer(
                f"{f'{LAYER_NAMES.BATTLE} ' if self.is_battle else ''}{pt_name}",
                [self.pt_group, LAYERS.SHAPE],
            ),
            getLayer(
                (f"{LAYER_NAMES.BATTLE} " if self.is_battle else "")
                + ("Fill" if pt_name in ("Full", "Partial") else "Fill Split"),
                self.pt_group,
            ),
        ]

    @cached_property
    def flipside_pt_arrow(self) -> ArtLayer | None:
        if self.has_flipside_pt:
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
        if self.is_pt_enabled and not self.has_displaced_pt_box:
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
        return getLayer(
            LAYERS.NORMAL, (self.pinlines_shape_group, LAYERS.NAME, LAYERS.NORMAL)
        )

    @cached_property
    def twins_horizontal_delta(self) -> float | int:
        if self.name_normal_pinline_shape:
            dims = get_layer_dimensions(self.name_normal_pinline_shape)
            return self.doc_width - 2 * dims["center_x"]
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
    def pinlines_shapes(self) -> list[ArtLayer | LayerSet | None]:
        _shape_group = self.pinlines_shape_group

        layers: list[ArtLayer | LayerSet | None] = []

        # Name
        if (self.is_transform or self.is_mdfc) and (
            layer := getLayerSet(
                LAYERS.TRANSFORM
                if self.is_transform
                else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
                [_shape_group, LAYERS.NAME],
            )
        ):
            layers.append(layer)
        elif self.name_normal_pinline_shape:
            # Flip horizontally
            if (
                self.flip_twins
                and not (self.is_transform or self.is_mdfc)
                and self.layout.mana_cost
            ):
                self.name_normal_pinline_shape.translate(self.twins_horizontal_delta, 0)
                flip_layer(self.name_normal_pinline_shape, FlipDirection.Horizontal)
            layers.append(self.name_normal_pinline_shape)

        # Add nickname pinlines if required
        if self.is_nickname and (
            layer_set := getLayerSet(LAYERS.NICKNAME, _shape_group)
        ):
            layers.append(layer_set)

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
    def twins_shapes(self) -> list[ArtLayer | LayerSet | None]:
        return []

    @cached_property
    def crown_shape(self) -> ArtLayer | None:
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

    def pw_mask_bottom(self) -> MaskAction | None:
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
    ) -> list[
        MaskAction
        | tuple[ArtLayer | LayerSet, ArtLayer | LayerSet]
        | ArtLayer
        | LayerSet
        | None
    ]:
        return [self.pw_mask_bottom()]

    # endregion Masks

    # region Frame

    @cached_property
    def frame_layer_methods(self) -> list[Callable[[], None]]:
        methods = super().frame_layer_methods
        if self.is_adventure:
            methods.append(self.enable_adventure_layers)
        if self.is_leveler:
            methods.append(self.frame_layers_leveler)
        if self.is_prototype:
            methods.append(self.frame_layers_prototype)
        return methods

    # endregion Frame

    # region Text

    @cached_property
    def text_layer_pt(self) -> ArtLayer | None:
        if self.is_station:
            return
        return super().text_layer_pt

    @cached_property
    def text_layer_ability(self) -> ArtLayer | None:
        if self.is_planeswalker:
            return super(SagaMod, self).text_layer_ability
        return super().text_layer_ability

    @cached_property
    def text_layer_rules_name(self) -> str:
        return f"{LAYERS.RULES_TEXT}{f' - {LAYERS.ADVENTURE} {LAYERS.RIGHT}' if self.is_adventure else ''}"

    @cached_property
    def text_layer_rules_base(self) -> ArtLayer | None:
        return getLayer(
            self.text_layer_rules_name,
            self.rules_text_group,
        )

    @cached_property
    def text_layer_rules(self) -> ArtLayer | None:
        if self.is_leveler:
            return getLayer("Rules Text - Level Up", self.leveler_group)

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
            and self.pt_reference
            and self.textbox_reference
        ):
            base_dims = get_layer_dimensions(self.textbox_reference)
            textbox_ref_shape = create_shape_layer(
                (
                    {"x": base_dims["left"], "y": base_dims["top"]},
                    {"x": base_dims["right"], "y": base_dims["top"]},
                    {"x": base_dims["right"], "y": self.doc_height},
                    {"x": base_dims["left"], "y": self.doc_height},
                ),
                relative_layer=self.textbox_reference,
                placement=ElementPlacement.PlaceBefore,
            )
            textbox_ref_shape = merge_shapes(
                self.pt_reference.duplicate(
                    textbox_ref_shape, ElementPlacement.PlaceBefore
                ),
                textbox_ref_shape,
                operation=ShapeOperation.SubtractFront,
            )
            # The Photoshop API can give incorrect text size when accessed initially (?),
            # though assigning a new size works as expected, e.g., actual size is 9 PT,
            # API returns 5.9, but assigning 11 makes the size 11 PT.
            layer = create_text_layer_with_path(
                textbox_ref_shape, layer, **self.rules_text_default_options
            )
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
        divider_layer: ArtLayer | LayerSet | None,
        oracle_text: str,
        flavor_text: str | None,
    ) -> None:
        set_text_size_and_leading(
            layer, self.rules_text_font_size, self.rules_text_font_size
        )
        text_field = FormattedTextField(
            layer=layer,
            contents=oracle_text,
            flavor=flavor_text,
            divider=divider_layer,
        )
        if not text_field.validate():
            raise ValueError("Rules text layer is invalid.")
        text_field.execute()

    def create_offset_text_shape(
        self,
        points: Iterable[PathPointConf],
        base_text_layer: ArtLayer,
        color: SolidColor,
        offset_shape: ArtLayer | None = None,
    ) -> ArtLayer:
        offset_shape = offset_shape or self.pt_reference

        text_ref_shape = create_shape_layer(
            points,
            hide=True,
        )

        if offset_shape:
            offset_copy = offset_shape.duplicate(
                text_ref_shape, ElementPlacement.PlaceBefore
            )
            text_ref_shape = merge_shapes(
                offset_copy, text_ref_shape, operation=ShapeOperation.SubtractFront
            )

        return create_text_layer_with_path(text_ref_shape, base_text_layer, color=color)

    def adjust_textbox_for_font_size(
        self,
        base_text_layer: ArtLayer,
        base_textbox_reference: ReferenceLayer,
        base_text_wrap_reference: ReferenceLayer,
        divider_layer: ArtLayer | LayerSet | None,
        oracle_text: str,
        flavor_text: str | None,
        min_top: float | int | None = None,
        align_to: float | int | None = None,
        alignment_dimension: Literal[
            "top", "bottom", "left", "right", "center_y", "center_x"
        ]
        | None = "center_y",
        vertical_padding: tuple[float | int, float | int] | None = None,
    ) -> tuple[ArtLayer, ReferenceLayer] | None:
        """Calculates the required size for rules textbox when the rules text has a fixed font size."""
        min_top = min_top if min_top is not None else self.doc_height
        vertical_padding = (
            vertical_padding
            if vertical_padding is not None
            else (self.rules_text_padding / 2, self.rules_text_padding / 2)
        )
        stroke_size = (
            stroke_details["size"]
            if (stroke_details := get_stroke_details(base_text_layer))
            else 0
        )
        # Text formatting might mess with the text's color value,
        # so the original has to be noted here
        color = base_text_layer.textItem.color

        if align_to is not None:
            top = min_top
        else:
            # Set and format rules text
            self.format_temp_rules_text(
                base_text_layer, divider_layer, oracle_text, flavor_text
            )
            dims_rules_text = get_layer_dimensions_via_rasterization(base_text_layer)
            top = min(dims_rules_text["top"], min_top)

        dims_wrap_ref = base_text_wrap_reference.dims
        bottom = self.doc_height + 500
        text_ref_shape = create_shape_layer(
            (
                {"x": dims_wrap_ref["left"], "y": top + stroke_size},
                {"x": dims_wrap_ref["right"], "y": top + stroke_size},
                {"x": dims_wrap_ref["right"], "y": bottom},
                {"x": dims_wrap_ref["left"], "y": bottom},
            ),
            hide=True,
            relative_layer=base_text_layer,
            placement=ElementPlacement.PlaceBefore,
        )

        # Assign the text to a shape to make sure that the text wraps consistently
        shaped_text = create_text_layer_with_path(
            text_ref_shape, base_text_layer, color=color
        )
        self.format_temp_rules_text(
            shaped_text, divider_layer, oracle_text, flavor_text
        )

        # Move text layer just above the point where text is allowed to be
        dims_textbox_ref = base_textbox_reference.dims
        align_dimension(
            shaped_text,
            reference_dimensions=dims_textbox_ref,
            alignment_dimension="bottom",
            offset=-vertical_padding[1],
        )

        dims_shaped_text = get_layer_dimensions_via_rasterization(shaped_text)
        if (
            align_to is None
            and (delta := min_top + vertical_padding[0] - dims_shaped_text["top"]) < 0
        ):
            shaped_text.translate(0, delta)
            alignment_dimension = "center_y"

        # Apply shape to the text that offsets PT elements but allows overflow at bottom
        if self.requires_text_shaping and self.pt_reference:
            dims_initial_shape = get_layer_dimensions_via_rasterization(shaped_text)
            min_pt_top = (
                self.pt_reference_base.dims["top"]
                if self.pt_reference_base
                else self.doc_height
            )
            top = min(
                dims_initial_shape["top"],
                min_pt_top,
                min_top,
            )

            shaped_text.remove()
            shaped_text = self.create_offset_text_shape(
                (
                    {"x": dims_wrap_ref["left"], "y": top + stroke_size},
                    {"x": dims_wrap_ref["right"], "y": top + stroke_size},
                    {"x": dims_wrap_ref["right"], "y": bottom},
                    {"x": dims_wrap_ref["left"], "y": bottom},
                ),
                base_text_layer,
                color,
            )

            self.format_temp_rules_text(
                shaped_text, divider_layer, oracle_text, flavor_text
            )

        # Check for overflow after offsetting PT elements
        # and reserve more space for text if necessary.
        if self.requires_text_shaping and self.textbox_overflow_reference:
            if (
                (
                    dims_shaped_text := get_layer_dimensions_via_rasterization(
                        shaped_text
                    )
                )
                and (
                    delta := self.textbox_overflow_reference.dims["top"]
                    - dims_shaped_text["bottom"]
                )
                # and (
                #     delta := check_reference_overlap(
                #         shaped_text,
                #         self.textbox_overflow_reference.bounds,
                #         docsel=self.docref.selection,
                #     )
                # )
                < 0
            ):
                top = dims_shaped_text["top"] + delta - vertical_padding[1]

                shaped_text.remove()
                shaped_text = self.create_offset_text_shape(
                    (
                        {"x": dims_wrap_ref["left"], "y": top + stroke_size},
                        {"x": dims_wrap_ref["right"], "y": top + stroke_size},
                        {"x": dims_wrap_ref["right"], "y": bottom},
                        {"x": dims_wrap_ref["left"], "y": bottom},
                    ),
                    base_text_layer,
                    color,
                )
                self.format_temp_rules_text(
                    shaped_text, divider_layer, oracle_text, flavor_text
                )

                dims_text_ref_shape = get_layer_dimensions_via_rasterization(
                    shaped_text
                )
                align_bottom = ceil(
                    min(
                        self.textbox_overflow_reference.dims["top"],
                        dims_textbox_ref["bottom"],
                    )
                    - vertical_padding[1]
                )

                mock_dims: LayerDimensions = {
                    **dims_textbox_ref,
                    "bottom": align_bottom,
                }
                # Align text vertically
                align_dimension(
                    shaped_text,
                    reference_dimensions=mock_dims,
                    alignment_dimension="bottom",
                )

                # Text might overlap with the PT box after alignment
                if (
                    self.pt_reference
                    and (
                        delta := check_layer_overlap_with_shape(
                            shaped_text, self.pt_reference
                        )
                    )
                    < 0
                ):
                    dims_text_ref_shape = get_layer_dimensions_via_rasterization(
                        shaped_text
                    )

                    top = dims_text_ref_shape["top"] + delta - vertical_padding[1]

                    shaped_text.remove()
                    shaped_text = self.create_offset_text_shape(
                        (
                            {"x": dims_wrap_ref["left"], "y": top + stroke_size},
                            {"x": dims_wrap_ref["right"], "y": top + stroke_size},
                            {"x": dims_wrap_ref["right"], "y": bottom},
                            {"x": dims_wrap_ref["left"], "y": bottom},
                        ),
                        base_text_layer,
                        color,
                    )
                    self.format_temp_rules_text(
                        shaped_text, divider_layer, oracle_text, flavor_text
                    )

                # Further alignment is unnecessary, unless a specific alignment point has been given
                alignment_dimension = None

        dims_text_ref_shape = get_layer_dimensions_via_rasterization(shaped_text)
        # Take padding into account when centering text
        chosen_top = (
            dims_text_ref_shape["top"]
            if dims_text_ref_shape["top"] < min_top
            else min_top
        )
        align_y = ceil(
            align_to
            if align_to is not None
            else chosen_top
            + (
                (
                    dims_textbox_ref["bottom"]
                    - (
                        # If there's plenty of space, ignore padding
                        vertical_padding[1]
                        if dims_text_ref_shape["height"] + sum(vertical_padding)
                        > dims_textbox_ref["bottom"] - min_top
                        else 0
                    )
                    - chosen_top
                )
                / 2
            )
        )

        if align_to is not None or alignment_dimension:
            mock_dims: LayerDimensions = {
                **dims_textbox_ref,
                "center_y": align_y,
            }
            # Align text
            align_dimension(
                shaped_text,
                reference_dimensions=mock_dims,
                alignment_dimension=alignment_dimension or "center_y",
            )

        base_text_layer.visible = False
        top_ref = (
            min_top
            if align_to is not None
            else get_layer_dimensions_via_rasterization(shaped_text)["top"]
            - vertical_padding[0]
        )
        return (
            shaped_text,
            ReferenceLayer(
                create_shape_layer(
                    (
                        {
                            "x": dims_textbox_ref["left"],
                            "y": top_ref,
                        },
                        {
                            "x": dims_textbox_ref["right"],
                            "y": top_ref,
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

    def adjust_textboxes_for_font_size(
        self, font_size: int | float, textbox_args: list[TextboxSizingArgs]
    ) -> list[tuple[ArtLayer, ReferenceLayer]]:
        """
        Adjusts multiple textboxes, whose bottom edges are aligned horizontally,
        to font size so that all the textboxes will end up with the same height.
        """

        # Size the textboxes starting from the one with most characters in its text
        # in the hope that we avoid resizing textboxes that way.
        textbox_args_sorted = textbox_args.copy()
        textbox_args_sorted.sort(
            key=lambda args: len(args["oracle_text"]) + len(args["flavor_text"] or ""),
            reverse=True,
        )

        sizes: list[tuple[ArtLayer, ReferenceLayer]] = []
        tallest_top: float | int = self.doc_height
        tallest_height: float | int = 0
        tallest_idx: int = -1
        # First pass of sizing
        for idx, arg in enumerate(textbox_args_sorted):
            height_padding = arg.get("height_padding", 0) or 0

            if not arg["oracle_text"] and arg["flavor_text"]:
                sized = (
                    arg["base_text_layer"],
                    self.textless_bottom_reference_layer
                    or arg["base_textbox_reference"],
                )
            else:
                with TemporaryLayerCopy(arg["base_text_layer"]) as base_text_layer_copy:
                    sized = self.adjust_textbox_for_font_size(
                        base_text_layer=base_text_layer_copy,
                        base_textbox_reference=arg["base_textbox_reference"],
                        base_text_wrap_reference=arg["base_text_wrap_reference"],
                        divider_layer=arg["divider_layer"],
                        oracle_text=arg["oracle_text"],
                        flavor_text=arg["flavor_text"],
                        min_top=min(
                            arg.get("min_top", self.doc_height) or self.doc_height,
                            tallest_top + height_padding,
                        )
                        or None,
                    )
                    # Some unknown interaction causes the previous reference layer
                    # to turn visible when starting a new sizing loop. Selecting some
                    # other layer seems to fix it without causing side effects.
                    if self.art_layer:
                        select_layer(self.art_layer)
            arg["base_text_layer"].visible = False
            if sized:
                sizes.append(sized)
                if (
                    height := sized[1].dims["height"] + height_padding
                ) > tallest_height:
                    tallest_top = sized[1].dims["top"] - height_padding
                    tallest_height = height
                    tallest_idx = idx
            else:
                raise ValueError(
                    f"Textbox sizing failed for {arg['base_text_layer'].name}"
                )

        # Resize all shorter layers to match the tallest
        for idx, ((layer, ref), arg) in enumerate(
            zip(sizes.copy(), textbox_args_sorted)
        ):
            orig_idx = textbox_args.index(arg)
            height_padding = arg.get("height_padding", 0) or 0

            if (
                idx == tallest_idx
                # If height already matches, there's no need to recreate the layer
                or ref.dims["height"] + height_padding == tallest_height
            ):
                sizes[orig_idx] = sizes[idx]
                continue

            layer.remove()
            ref.remove()
            min_top = tallest_top + height_padding
            with TemporaryLayerCopy(arg["base_text_layer"]) as base_text_layer_copy:
                sized = self.adjust_textbox_for_font_size(
                    base_text_layer=base_text_layer_copy,
                    base_textbox_reference=arg["base_textbox_reference"],
                    base_text_wrap_reference=arg["base_text_wrap_reference"],
                    divider_layer=arg["divider_layer"],
                    oracle_text=arg["oracle_text"],
                    flavor_text=arg["flavor_text"],
                    min_top=min_top,
                    align_to=min_top + (tallest_height - height_padding) / 2,
                )
                # Same reference layer turning visible bug as above.
                if self.art_layer:
                    select_layer(self.art_layer)
            if sized:
                sizes[orig_idx] = sized
            else:
                raise ValueError(
                    f"Textbox resizing failed for {arg['base_text_layer'].name}"
                )

        return sizes

    def disable_text_area_scaling(self, text_area: FormattedTextArea) -> None:
        text_area.scale_height = False
        text_area.scale_width = False
        text_area.fix_overflow_height = False
        text_area.fix_overflow_width = False

    def rules_text_and_pt_layers(self) -> None:
        if self.is_split:
            if self.rules_text_font_size:
                # Split cards don't have PT text and rules text is already adjusted elsewhere
                return
            return super().rules_text_and_pt_layers()

        if self.is_planeswalker:
            if self.text_layer_rules_base:
                self.text_layer_rules_base.visible = False
            return

        # Ensure that sizing logic associated with fixed font size runs before
        # accessing the rules text layer
        self.textbox_reference
        super(BorderlessVectorTemplate, self).rules_text_and_pt_layers()

        if self.supports_dynamic_textbox_height:
            if self.rules_text_font_size:
                # Filter out rules text formatting as it has been done already
                self.text = [
                    entry
                    for entry in self.text
                    if entry and entry.layer is not self.text_layer_rules
                ]
            else:
                for entry in self.text:
                    if (
                        isinstance(entry, FormattedTextArea)
                        and entry.layer is self.text_layer_rules
                    ):
                        # The text element already has a proper width
                        # This can also create an undesirable interaction
                        # where the text is scaled to be minimal.
                        entry.scale_width = False
                        if entry.reference_dims and (
                            stroke_details := get_stroke_details(entry.layer)
                        ):
                            # Add enough padding to offset stroke
                            # TODO Figure out a cleaner way to do this. Possibly by extending FormattedTextArea?
                            entry.reference_dims = {
                                **entry.reference_dims,
                                "height": entry.reference_dims["height"]
                                - stroke_details["size"],
                            }

                        # The text element already has a shape that offsets PT box and other extras.
                        entry.pt_reference = None
                        break

        if isinstance(self.layout, BattleLayout):
            for entry in self.text:
                if entry and entry.layer == self.text_layer_pt:
                    entry.contents = self.layout.defense

    def textbox_positioning(self) -> None:
        if self.is_split:
            ref = self.textbox_references[0]
            ref_base = get_reference_layer(
                f"{LAYER_NAMES.REFERENCE} {LAYERS.LEFT}", self.textbox_reference_group
            )
            if ref and ref_base:
                delta = ref.dims["top"] - ref_base.dims["top"]

                layers: list[ArtLayer | LayerSet | None] = [
                    *self.text_layers_type,
                    *self.typeline_pinlines_layers,
                    *self.expansion_symbols,
                ]
                for layer in layers:
                    if layer:
                        layer.translate(0, delta)
        else:
            if self.is_prototype:
                ref = ReferenceLayer(self.prototype_manabox_shape)
                ref.dims["top"] -= self.rules_text_padding / 2
            else:
                ref = (
                    self.textless_bottom_reference_layer
                    if self.is_vertical_layout or self.is_textless
                    else self.textbox_reference
                )
            if ref and self.textbox_reference_base:
                # Get the delta between the highest box and the target box
                delta = ref.dims["top"] - self.textbox_reference_base.dims["top"]

                # Shift typeline text
                if self.text_layer_type:
                    self.text_layer_type.translate(0, delta)

                # Shift typeline pinline
                if self.typeline_pinline_shape:
                    self.typeline_pinline_shape.translate(0, delta)

                # Shift expansion symbol
                if self.config.symbol_enabled and self.expansion_symbol_layer:
                    self.expansion_symbol_layer.translate(0, delta)

                # Shift indicator
                if (
                    self.is_type_shifted
                    and self.indicator_group
                    and isinstance((parent := self.indicator_group.parent), LayerSet)
                ):
                    parent.translate(0, delta)

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
        if self.is_planeswalker and self.loyalty_group:
            self.loyalty_group.visible = True

    @cached_property
    def text_layer_methods(self) -> list[Callable[[], None]]:
        methods = super().text_layer_methods
        if not self.is_planeswalker:
            methods.remove(self.pw_text_layers)
        if self.is_prototype:
            methods.append(self.text_layers_prototype)
        methods.insert(0, self.adjust_split_textboxes_to_font_size)
        return methods

    @cached_property
    def post_text_methods(self) -> list[Callable[[], None]]:
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
        if self.is_prototype:
            methods.insert(0, self.post_text_layers_prototype)
            if self.textbox_positioning not in methods:
                methods.append(self.textbox_positioning)
        return [
            *methods,
            self.expansion_symbol_handler,
            self.pw_enable_loyalty_graphics,
        ]

    # endregion Text

    # region Hooks

    @cached_property
    def hooks(self) -> list[Callable[[], None]]:
        hooks = super().hooks
        hooks.append(self.hide_layer_effects_with_pinlines_mask)
        hooks.append(self.hide_transparencies)
        return hooks

    def hide_layer_effects_with_pinlines_mask(self) -> None:
        if self.config.exit_early and self.pinlines_group:
            # Set layer effects to be hidden by pinlines mask
            # in order to ease creating pop-out effects.
            apply_mask_to_layer_fx(self.pinlines_group)

    def hide_transparencies(self) -> None:
        if self.bottom_border_type == "Full" and self.art_layer:
            # Create a black layer behind everything else in order
            # to ensure that there's no transparency in the final image.
            layer = self.docref.artLayers.add()
            layer.move(self.art_layer, ElementPlacement.PlaceAfter)
            create_color_layer(
                rgb_black(), layer, self.docref, blend_mode=BlendMode.NormalBlend
            )

    # endregion Hooks

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

    @cached_property
    def adventure_pinlines_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        if isinstance(self.layout, AdventureLayout) and self.adventure_pinlines:
            adventure_pinline_dims = get_layer_dimensions(self.adventure_pinlines)
            proportional_pinlines_width = (
                adventure_pinline_dims["width"] / self.doc_width
            )
            gradient_start_offset = (
                proportional_pinlines_width
                / (len(self.layout.color_identity_adventure) + 1)
                - proportional_pinlines_width * 0.05
            )
            return create_gradient_config(
                "".join(self.layout.color_identity_adventure),
                self.pinlines_color_map,
                adventure_pinline_dims["left"] / self.doc_width + gradient_start_offset,
                adventure_pinline_dims["right"] / self.doc_width
                - gradient_start_offset,
            )
        return (0, 0, 0)

    @cached_property
    def adventure_pinlines(self) -> ArtLayer | None:
        return getLayer(LAYERS.ADVENTURE, self.adventure_pinlines_group)

    def enable_adventure_layers(self) -> None:
        if isinstance(self.layout, AdventureLayout) and self.adventure_pinlines_group:
            self.adventure_pinlines_group.visible = True
            self.generate_layer(
                group=self.adventure_pinlines_group,
                colors=self.adventure_pinlines_colors,
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
                    self.disable_text_area_scaling(entry)
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
                        # It's enough to reposition the text since it's already formatted.
                        # Reformatting actually breaks the styling of the text.
                        text_area.position_within_reference()
                    break

    # endregion Adventure

    # region Leveler

    def frame_layers_leveler(self) -> None:
        if self.leveler_group:
            self.leveler_group.visible = True
        if group := getLayerSet("Leveler Boxes"):
            if (pinlines := getLayerSet(LAYERS.PINLINES, group)) and (
                layer := self.generate_layer(
                    group=pinlines, colors=self.pinlines_colors, clipped=False
                )
            ):
                layer.move(pinlines, ElementPlacement.PlaceBefore)
                create_clipping_mask(layer)
            group.visible = True

    # endregion Leveler

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

    # region Split

    @cached_property
    def fuse_gradient_locations(self) -> dict[int, list[int | float]]:
        return self.gradient_location_map

    @cached_property
    def pinline_gradient_locations(self) -> list[dict[int, list[int | float]]]:
        # At the time of writing there are no split cards with more than 2 colors per side.
        return [
            {**self.gradient_location_map, 2: [0.25, 0.30]},
            {**self.gradient_location_map, 2: [0.70, 0.75]},
        ]

    def frame_layers_split(self):
        if self.is_fuse:
            if self.fuse_pinline:
                self.fuse_pinline.visible = True
            if self.text_layer_fuse:
                self.text_layer_fuse.visible = True
        if self.flip_twins:
            self.name_pinlines_layers
        for layer in self.typeline_pinlines_layers:
            if layer:
                layer.visible = True
        for i in range(len(self.sides)):
            if group := self.pinlines_groups_split[i]:
                # Apply pinlines colors
                self.generate_layer(group=group, colors=self.pinlines_colors_split[i])

    def flip_split_layers(self, layers: list[ArtLayer | None]) -> None:
        if (layer_a := layers[0]) and (layer_b := layers[1]):
            dims_a = get_layer_dimensions(layer_a)
            dims_b = get_layer_dimensions(layer_b)
            half_doc_width: float | int = self.doc_width / 2
            delta = half_doc_width - (dims_b["left"] - half_doc_width) - dims_a["right"]
            for layer in layers:
                if layer:
                    flip_layer(layer, FlipDirection.Horizontal)
                    layer.translate(delta, 0)

    @cached_property
    def name_pinlines_layers(self) -> list[ArtLayer | None]:
        layers = [
            getLayer(
                LAYERS.NORMAL,
                (side, LAYERS.PINLINES, LAYERS.SHAPE, LAYERS.NAME, LAYERS.NORMAL),
            )
            for side in self.card_groups
        ]

        if self.flip_twins:
            self.flip_split_layers(layers)

        return layers

    @cached_property
    def typeline_pinlines_layers(self) -> list[ArtLayer | None]:
        if self.has_unified_typeline:
            if (
                layer := getLayer(
                    LAYER_NAMES.UNIFIED,
                    (self.pinlines_group, LAYERS.SHAPE, LAYERS.TYPE_LINE),
                )
            ) and self.flip_twins:
                flip_layer(layer, FlipDirection.Horizontal)
                dims = get_layer_dimensions(layer)
                layer.translate(self.doc_width - 2 * dims["center_x"], 0)

            return [layer]

        layers = [
            getLayer(
                LAYERS.TYPE_LINE,
                (group, LAYERS.PINLINES, LAYERS.SHAPE, LAYERS.TYPE_LINE),
            )
            for group in self.card_groups
        ]

        if self.flip_twins:
            self.flip_split_layers(layers)

        return layers

    @cached_property
    def fuse_pinline(self) -> ArtLayer | None:
        return getLayer(
            LAYER_NAMES.FUSE, (self.pinlines_group, LAYERS.SHAPE, LAYER_NAMES.FUSE)
        )

    @cached_property
    def textbox_references(self) -> list[ReferenceLayer | None]:
        refs = [
            get_reference_layer(
                f"{LAYER_NAMES.REFERENCE} {side}", self.textbox_reference_group
            )
            for side in self.sides
        ]

        if self.is_fuse and self.fuse_reference:
            for idx, ref in enumerate(refs):
                if ref:
                    name = ref.name
                    fuse_ref_duplicate = self.fuse_reference.duplicate(
                        ref, ElementPlacement.PlaceBefore
                    )
                    new_ref = merge_shapes(
                        fuse_ref_duplicate,
                        ref,
                        operation=ShapeOperation.SubtractFront,
                    )
                    new_ref.name = name
                    new_ref.visible = False
                    refs[idx] = ReferenceLayer(new_ref)

        if self.textbox_height and not self.rules_text_font_size:
            # Create fixed size textbox references
            created_refs: list[ReferenceLayer | None] = []
            for ref in refs:
                if ref:
                    dims = ref.dims
                    top = dims["bottom"] - self.textbox_height
                    created_ref = create_shape_layer(
                        (
                            {"x": dims["left"], "y": top},
                            {"x": dims["right"], "y": top},
                            {"x": dims["right"], "y": dims["bottom"]},
                            {"x": dims["left"], "y": dims["bottom"]},
                        ),
                        relative_layer=ref,
                        placement=ElementPlacement.PlaceBefore,
                        hide=True,
                    )
                    created_refs.append(ReferenceLayer(created_ref))
                else:
                    created_refs.append(None)
            refs = created_refs

        return refs

    @cached_property
    def expansion_references(self) -> list[ReferenceLayer | None]:
        return [
            get_reference_layer(f"{LAYERS.EXPANSION_REFERENCE} {side}", self.text_group)
            for side in self.sides
        ]

    @cached_property
    def fuse_reference(self) -> ReferenceLayer | None:
        return get_reference_layer(
            f"{LAYER_NAMES.FUSE} {LAYER_NAMES.REFERENCE}", self.text_group
        )

    @cached_property
    def text_layers_name(self) -> list[ArtLayer | None]:
        return [
            getLayer(f"{LAYERS.NAME} {side}", self.text_group) for side in self.sides
        ]

    @cached_property
    def text_layers_rules(self) -> list[ArtLayer | None]:
        return [
            getLayer(f"{LAYERS.RULES_TEXT} {side}", self.rules_text_group)
            for side in self.sides
        ]

    @cached_property
    def text_layers_type(self) -> list[ArtLayer | None]:
        layers = [
            getLayer(f"{LAYERS.TYPE_LINE} {side}", self.text_group)
            for side in self.sides
        ]
        if self.has_unified_typeline:
            for idx, layer in enumerate(layers[1:]):
                if layer:
                    layer.visible = False
                    layers[idx + 1] = None

        return layers

    @cached_property
    def text_layers_mana(self) -> list[ArtLayer | None]:
        return [
            getLayer(f"{LAYERS.MANA_COST} {side}", self.text_group)
            for side in self.sides
        ]

    @cached_property
    def text_layer_fuse(self) -> ArtLayer | None:
        return getLayer(f"{LAYER_NAMES.FUSE} {LAYERS.TEXT}", self.text_group)

    def adjust_split_textboxes_to_font_size(self):
        if self.rules_text_font_size and isinstance(self.layout, SplitLayout):
            args: list[TextboxSizingArgs] = []
            for text_layer, textbox_ref, divider, flavor, oracle in zip(
                self.text_layers_rules,
                self.textbox_references,
                self.rules_text_dividers,
                self.layout.flavor_texts,
                self.layout.oracle_texts,
            ):
                if text_layer and textbox_ref:
                    args.append(
                        {
                            "base_text_layer": text_layer,
                            "base_text_wrap_reference": textbox_ref,
                            "base_textbox_reference": textbox_ref,
                            "divider_layer": divider,
                            "flavor_text": flavor,
                            "oracle_text": oracle,
                        }
                    )
            sized_boxes = self.adjust_textboxes_for_font_size(
                self.rules_text_font_size, args
            )

            self.text_layers_rules = [layer for layer, _ in sized_boxes]
            self.textbox_references = [ref for _, ref in sized_boxes]

    # endregion Split

    # region Prototype

    _prototype_manabox_colors: dict[str, ColorObject] = {
        "W": "#afa591",
        "U": "#0c7798",
        "B": "#585757",
        "R": "#a2442e",
        "G": "#305e3a",
        "Gold": "#826b3f",
        "Land": "#82837f",
        "Artifact": "#6c7a84",
        # The ones below were not defined in Proxyshop's Prototype template
        "Colorless": "#e6ecf2",
        "Vehicle": "#4d2d05",
    }

    @cached_property
    def prototype_manabox_colors(
        self,
    ) -> ColorObject | list[ColorObject] | list[GradientConfig] | None:
        if isinstance(self.layout, PrototypeLayout):
            return get_pinline_gradient(
                colors=self.layout.proto_color,
                color_map=self._prototype_manabox_colors,
                location_map=self.gradient_location_map,
            )

    @cached_property
    def prototype_pinlines_colors(
        self,
    ) -> ColorObject | list[ColorObject] | list[GradientConfig] | None:
        if isinstance(self.layout, PrototypeLayout):
            return get_pinline_gradient(
                colors=self.layout.proto_color,
                color_map=self.pinlines_color_map,
                location_map=self.gradient_location_map,
            )

    @cached_property
    def prototype_group(self) -> LayerSet | None:
        return getLayerSet(LAYER_NAMES.PROTOTYPE)

    @cached_property
    def prototype_manabox_group(self) -> LayerSet | None:
        return getLayerSet(LAYER_NAMES.MANABOX, self.prototype_group)

    @cached_property
    def prototype_pt_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.PT_BOX, self.prototype_group)

    @cached_property
    def rules_text_reference_prototype(self) -> ReferenceLayer | None:
        return get_reference_layer(LAYER_NAMES.TEXT_REFERENCE, self.prototype_group)

    @cached_property
    def prototype_manabox_shape(self) -> ArtLayer | None:
        if isinstance(self.layout, PrototypeLayout):
            size = "2" if self.layout.proto_mana_cost.count("{") <= 2 else "3"
            return getLayer(size, self.prototype_manabox_group)

    @cached_property
    def prototype_pt_box_shape(self) -> ArtLayer | None:
        return getLayer(LAYERS.PT_BOX, self.prototype_pt_group)

    @cached_property
    def text_layer_rules_prototype(self) -> ArtLayer | None:
        return getLayer(LAYERS.RULES_TEXT, self.prototype_group)

    @cached_property
    def text_layer_mana_prototype(self) -> ArtLayer | None:
        return getLayer(LAYERS.MANA_COST, self.prototype_group)

    @cached_property
    def text_layer_pt_prototype(self) -> ArtLayer | None:
        return getLayer(LAYERS.POWER_TOUGHNESS, self.prototype_group)

    def frame_layers_prototype(self) -> None:
        if self.prototype_group:
            self.prototype_group.visible = True
        if self.prototype_manabox_shape:
            self.prototype_manabox_shape.visible = True

        # Colors
        if self.prototype_manabox_group and self.prototype_manabox_colors:
            self.generate_layer(
                group=self.prototype_manabox_group, colors=self.prototype_manabox_colors
            )
        if self.prototype_pt_group and self.prototype_pinlines_colors:
            self.generate_layer(
                group=self.prototype_pt_group, colors=self.prototype_pinlines_colors
            )

    def text_layers_prototype(self) -> None:
        if isinstance(self.layout, PrototypeLayout):
            if self.text_layer_mana_prototype:
                self.text.append(
                    FormattedTextField(
                        layer=self.text_layer_mana_prototype,
                        contents=self.layout.proto_mana_cost,
                    )
                )
            if self.text_layer_pt_prototype:
                self.text.append(
                    TextField(
                        layer=self.text_layer_pt_prototype,
                        contents=self.layout.proto_pt,
                    )
                )

    def post_text_layers_prototype(self) -> None:
        if isinstance(self.layout, PrototypeLayout):
            if self.text_layer_rules_prototype and self.text_layer_rules:
                self.text_layer_rules_prototype.textItem.size = (
                    self.text_layer_rules.textItem.size
                )
                text_area = FormattedTextArea(
                    layer=self.text_layer_rules_prototype,
                    contents="Prototype"
                    if self.config.remove_reminder
                    else self.text_layer_rules_prototype.textItem.contents,
                    reference=self.rules_text_reference_prototype,
                )
                self.disable_text_area_scaling(text_area)
                if text_area.validate():
                    text_area.execute()

        # Move Prototype elements on top of normal rules text
        if self.textbox_reference and self.prototype_group and self.prototype_pt_group:
            pt_dims = get_layer_dimensions_via_rasterization(self.prototype_pt_group)
            ref_dims = self.textbox_reference.dims
            delta = ref_dims["top"] - pt_dims["bottom"]
            self.prototype_group.translate(0, delta)

    # endregion Prototype

    # region Station

    @cached_property
    def station_levels_base_text_references(self) -> list[ReferenceLayer]:
        layers: list[ReferenceLayer] = []
        if isinstance(self.layout, StationLayout):
            for details, level_group in zip(
                self.layout.stations, self.station_level_groups
            ):
                if layer := get_reference_layer(
                    LAYER_NAMES.TEXT_REFERENCE_CREATURE
                    if "pt" in details
                    else LAYER_NAMES.TEXT_REFERENCE,
                    level_group,
                ):
                    layers.append(layer)
        return layers

    def text_layers_station(self) -> None:
        if self.rules_text_font_size:
            if isinstance(self.layout, StationLayout):
                for details, requirement, pt in zip(
                    self.layout.stations,
                    self.station_requirement_text_layers,
                    self.station_pt_text_layers,
                ):
                    requirement.textItem.contents = details["requirement"]
                    if "pt" in details:
                        pt.textItem.contents = (
                            f"{details['pt']['power']}/{details['pt']['toughness']}"
                        )
        else:
            return super().text_layers_station()

    def frame_layers_station(self) -> None:
        super().frame_layers_station()

        for group_list in (self.station_requirement_groups, self.station_pt_groups):
            for group in group_list:
                if layer := getLayer(LAYERS.PINLINES, group):
                    self.generate_layer(group=layer, colors=self.pinlines_colors)

    def layer_positioning_station(self) -> None:
        if not self.rules_text_font_size:
            return super().layer_positioning_station()

    # endregion Station
