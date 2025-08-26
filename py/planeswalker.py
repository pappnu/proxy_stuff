from collections.abc import Sequence
from functools import cached_property

from photoshop.api import (
    ActionDescriptor,
    ActionReference,
    DialogModes,
    ElementPlacement,
    SolidColor,
)
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

import src.helpers as psd
from src import APP, CFG
from src.enums.layers import LAYERS
from src.frame_logic import contains_frame_colors
from src.layouts import PlaneswalkerLayout
from src.schema.colors import ColorObject, GradientConfig
from src.templates import (
    PlaneswalkerBorderlessTemplate,
    VectorBorderlessMod,
    VectorTemplate,
)
from src.templates._vector import MaskAction
from src.templates.mdfc import VectorMDFCMod
from src.templates.transform import VectorTransformMod
from src.utils.adobe import ReferenceLayer

from .helpers import LAYER_NAMES, create_vector_mask_from_shape
from .utils.path import subtract_front_shape

sID = APP.stringIDToTypeID


class PlaneswalkerBorderlessVector(
    VectorBorderlessMod,
    VectorMDFCMod,
    VectorTransformMod,
    VectorTemplate,
    PlaneswalkerBorderlessTemplate,
):
    """
    SETTINGS
    """

    @cached_property
    def color_limit(self) -> int:
        return (
            int(
                CFG.get_setting(
                    section="COLORS", key="Max.Colors", default="2", is_bool=False
                )
            )
            + 1
        )

    @cached_property
    def colored_textbox(self) -> bool:
        """Returns True if Textbox should be colored."""
        return CFG.get_bool_setting(section="COLORS", key="Color.Textbox", default=True)

    @cached_property
    def multicolor_textbox(self) -> bool:
        """Returns True if Textbox for multicolored cards should use blended colors."""
        return CFG.get_bool_setting(
            section="COLORS", key="Multicolor.Textbox", default=True
        )

    @cached_property
    def multicolor_pinlines(self) -> bool:
        """Returns True if Pinlines and Crown for multicolored cards should use blended colors."""
        return CFG.get_bool_setting(
            section="COLORS", key="Multicolor.Pinlines", default=True
        )

    @cached_property
    def multicolor_twins(self) -> bool:
        """Returns True if Twins for multicolored cards should use blended colors."""
        return CFG.get_bool_setting(
            section="COLORS", key="Multicolor.Twins", default=True
        )

    @cached_property
    def hybrid_colored(self) -> bool:
        """Returns True if Twins and PT should be colored on Hybrid cards."""
        return CFG.get_bool_setting(
            section="COLORS", key="Hybrid.Colored", default=True
        )

    @cached_property
    def front_face_colors(self) -> bool:
        """Returns True if lighter color map should be used on front face DFC cards."""
        return CFG.get_bool_setting(
            section="COLORS", key="Front.Face.Colors", default=True
        )

    @cached_property
    def drop_shadow_enabled(self) -> bool:
        """Returns True if Drop Shadow text setting is enabled."""
        return CFG.get_bool_setting(section="SHADOWS", key="Drop.Shadow", default=True)

    @cached_property
    def bottom_shadow_enabled(self) -> bool:
        """Returns True if Bottom Shadow setting is enabled."""
        return CFG.get_bool_setting(
            section="SHADOWS", key="Bottom.Shadow", default=True
        )

    """
    DETAILS
    """

    @cached_property
    def is_content_aware_enabled(self) -> bool:
        return True

    @cached_property
    def textbox_size(self) -> str:
        if isinstance(self.layout, PlaneswalkerLayout) and self.layout.pw_size > 3:
            return LAYER_NAMES.PW4
        return LAYER_NAMES.PW3

    """
    BOOL
    """

    @cached_property
    def is_multicolor(self) -> bool:
        """Whether the card is multicolor and within the color limit range."""
        return bool(1 <= len(self.identity) < self.color_limit)

    @cached_property
    def is_drop_shadow(self) -> bool:
        """Return True if drop shadow setting is enabled."""
        return bool(
            self.drop_shadow_enabled
            and not (
                (self.is_mdfc or self.is_transform)
                and self.is_front
                and self.front_face_colors
            )
        )

    @cached_property
    def is_authentic_front(self) -> bool:
        """Return True if rendering a front face DFC card with authentic lighter colors."""
        return bool(
            (self.is_mdfc or self.is_transform)
            and self.is_front
            and self.front_face_colors
        )

    """
    COLOR MAPS
    """

    @cached_property
    def dark_color_map(self) -> dict[str, str]:
        return {
            "W": "#958676",
            "U": "#045482",
            "B": "#282523",
            "R": "#93362a",
            "G": "#134f23",
            "Gold": "#9a883f",
            "Hybrid": "#a79c8e",
            "Colorless": "#74726b",
        }

    @cached_property
    def light_color_map(self) -> dict[str, str]:
        return {
            "W": "#faf8f2",
            "U": "#d2edfa",
            "B": "#c9c2be",
            "R": "#f8c7b0",
            "G": "#dbfadc",
            "Gold": "#f5e5a4",
            "Hybrid": "#f0ddce",
            "Colorless": "#e2d8d4",
        }

    @cached_property
    def gradient_location_map(self) -> dict[int, list[float]]:
        return {
            2: [0.40, 0.60],
            3: [0.29, 0.40, 0.60, 0.71],
            4: [0.20, 0.30, 0.45, 0.55, 0.70, 0.80],
            5: [0.20, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.80],
        }

    """
    COLORS
    """

    @cached_property
    def twins_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        # Default to twins
        colors = self.twins

        # Color enabled hybrid OR color enabled multicolor
        if (self.is_hybrid and self.hybrid_colored) or (
            self.is_multicolor and self.multicolor_twins
        ):
            colors = self.identity
        # Color disabled hybrid cards
        elif self.is_hybrid:
            colors = LAYERS.HYBRID

        # Return Solid Color or Gradient notation
        return psd.get_pinline_gradient(
            colors=colors,
            color_map=self.light_color_map
            if self.is_authentic_front
            else self.dark_color_map,
            location_map=self.gradient_location_map,
        )

    @cached_property
    def textbox_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        # Non-colored textbox
        if not (
            self.colored_textbox
            and (self.is_hybrid or (self.is_multicolor and self.multicolor_textbox))
        ):
            return []

        # Hybrid OR color enabled multicolor
        return psd.get_pinline_gradient(
            colors=self.identity,
            color_map=self.light_color_map
            if self.is_authentic_front
            else self.dark_color_map,
            location_map=self.gradient_location_map,
        )

    @cached_property
    def pinlines_colors(
        self,
    ) -> ColorObject | Sequence[ColorObject] | Sequence[GradientConfig]:
        # Use alternate gradient location map
        return psd.get_pinline_gradient(
            # Use identity for hybrid OR color enabled multicolor
            self.identity
            if self.is_hybrid or (self.is_multicolor and self.multicolor_pinlines)
            # Use pinlines if not a color code
            else (
                self.pinlines
                if not contains_frame_colors(self.pinlines)
                else LAYERS.GOLD
            ),
            color_map=self.pinlines_color_map,
            location_map=self.gradient_location_map,
        )

    """
    GROUPS
    """

    @cached_property
    def pinlines_size_group(self) -> LayerSet | None:
        return psd.getLayerSet(
            self.textbox_size,
            [self.pinlines_group, LAYERS.SHAPE],
        )

    @cached_property
    def text_group(self) -> LayerSet | None:
        return psd.getLayerSet(self.textbox_size, LAYERS.TEXT_AND_ICONS)

    @cached_property
    def textbox_root_group(self) -> LayerSet | None:
        return psd.getLayerSet(LAYERS.TEXTBOX)

    @cached_property
    def textbox_size_group(self) -> LayerSet | None:
        return psd.getLayerSet(self.textbox_size, [LAYERS.TEXTBOX, LAYERS.SHAPE])

    @cached_property
    def textbox_group(self) -> LayerSet | None:
        """Group to populate with ragged lines divider mask."""
        return psd.getLayerSet(
            "Ragged Lines",
            [
                LAYERS.TEXTBOX,
                LAYERS.SHAPE,
                self.textbox_size,
                LAYER_NAMES.ABILITY_DIVIDERS,
            ],
        )

    @cached_property
    def dfc_group(self) -> LayerSet | None:
        layer_name = None
        layer_path: list[str] = [LAYERS.TEXT_AND_ICONS]
        if self.is_mdfc:
            layer_name = LAYERS.MDFC_FRONT if self.is_front else LAYERS.MDFC_BACK
        elif self.is_transform:
            layer_path.append(LAYERS.TRANSFORM)
            layer_name = LAYERS.FRONT if self.is_front else LAYERS.BACK
        if layer_name:
            return psd.getLayerSet(
                layer_name,
                layer_path,
            )

    """
    BASIC LAYERS
    """

    @cached_property
    def bottom_shadow_layer(self) -> ArtLayer | None:
        return psd.getLayer(LAYER_NAMES.SHADOW)

    """
    TEXT LAYERS
    """

    @cached_property
    def text_layer_name(self) -> ArtLayer | None:
        if self.is_name_shifted:
            if layer := psd.getLayer(LAYERS.NAME, LAYERS.TEXT_AND_ICONS):
                layer.visible = False
            if name := psd.getLayer(LAYERS.NAME_SHIFT, LAYERS.TEXT_AND_ICONS):
                name.visible = True
                return name
        return psd.getLayer(LAYERS.NAME, LAYERS.TEXT_AND_ICONS)

    @cached_property
    def text_layer_mana(self) -> ArtLayer | None:
        return psd.getLayer(LAYERS.MANA_COST, LAYERS.TEXT_AND_ICONS)

    """
    REFERENCE LAYERS
    """

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        return psd.get_reference_layer(
            LAYERS.TEXTBOX_REFERENCE + " MDFC"
            if self.is_mdfc
            else LAYERS.TEXTBOX_REFERENCE,
            self.text_group,
        )

    """
    VECTOR SHAPES
    """

    @cached_property
    def pinlines_card_name_shape(self) -> LayerSet | None:
        """Vector shape representing the card name pinlines."""
        return psd.getLayerSet(
            LAYERS.MDFC
            if self.is_mdfc
            else LAYERS.TRANSFORM
            if self.is_transform
            else LAYERS.NORMAL,
            [self.pinlines_group, LAYERS.SHAPE, LAYERS.NAME],
        )

    @cached_property
    def pinlines_textbox_shape(self) -> ArtLayer | None:
        """Vector shape representing the inner textbox pinlines."""
        return psd.getLayer(
            LAYERS.NORMAL,
            [self.pinlines_group, LAYERS.TEXTBOX, self.textbox_size],
        )

    @cached_property
    def textbox_shape(self) -> ArtLayer | None:
        """Vector shape representing the card textbox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_front and self.is_transform else LAYERS.TEXTBOX,
            self.textbox_size_group,
        )

    @cached_property
    def textbox_shape_other(self) -> ArtLayer | None:
        """Vector shape representing the less opaque card textbox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_front and self.is_transform else LAYERS.TEXTBOX,
            [self.textbox_size_group, LAYER_NAMES.ABILITY_DIVIDERS],
        )

    @cached_property
    def namebox_shape(self) -> ArtLayer | None:
        """Vector shape representing the card namebox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_transform or self.is_mdfc else LAYERS.NORMAL,
            [self.twins_group, LAYERS.SHAPE, LAYERS.NAME],
        )

    @cached_property
    def typebox_shape(self) -> ArtLayer | None:
        """Vector shape representing the card typebox."""
        return psd.getLayer(
            self.textbox_size,
            [self.twins_group, LAYERS.SHAPE, LAYERS.TYPE_LINE],
        )

    @cached_property
    def enabled_shapes(self) -> list[ArtLayer | LayerSet | None]:
        """Vector shapes that should be enabled during the enable_shape_layers step."""
        return [
            self.border_shape,
            self.namebox_shape,
            self.typebox_shape,
            self.pinlines_size_group,
            self.pinlines_card_name_shape,
            self.pinlines_textbox_shape,
            self.textbox_shape,
            self.textbox_shape_other,
        ]

    """
    MASKS
    """

    @cached_property
    def pinlines_vector_mask(self) -> MaskAction | None:
        """This mask hides undesired layer effects."""
        if (
            self.mask_group
            and self.namebox_shape
            and self.typebox_shape
            and self.pinlines_arrow
            and (target := psd.getLayerSet(LAYERS.SHAPE, self.pinlines_group))
            and (base_shape := psd.getLayer("Base", self.mask_group))
            and (layer := psd.getLayer(LAYERS.TEXTBOX, self.textbox_size_group))
        ):
            # Build the shape
            namebox = self.namebox_shape.duplicate(
                base_shape, ElementPlacement.PlaceBefore
            )
            typeline = self.typebox_shape.duplicate(
                base_shape, ElementPlacement.PlaceBefore
            )
            textbox = layer.duplicate(base_shape, ElementPlacement.PlaceBefore)
            parts: list[ArtLayer] = [namebox, typeline, textbox]
            if self.is_transform and self.is_front:
                parts.append(
                    self.pinlines_arrow.duplicate(
                        base_shape, ElementPlacement.PlaceBefore
                    )
                )
            # The shapes have to be subtracted in bottom up order
            for layer in reversed(parts):
                base_shape = subtract_front_shape(base_shape, layer)

            # Create vector mask fails if the layer isn't visible
            self.mask_group.visible = True
            mask = create_vector_mask_from_shape(
                psd.create_new_layer("Pinlines"), base_shape
            )
            self.mask_group.visible = False

            # Cleanup
            base_shape.remove()

            return {
                "mask": mask,
                "vector": True,
                "layer": target,
                "funcs": [apply_vector_mask_to_layer_fx],
            }

    @cached_property
    def mdfc_pinlines_mask(self) -> MaskAction | None:
        """This mask hides pinlines below the MDFC bottom box."""
        if (mask := psd.getLayer("MDFC Bottom", self.mask_group)) and (
            target := psd.getLayerSet(
                self.textbox_size, [self.pinlines_group, LAYERS.SHAPE]
            )
        ):
            return {
                "mask": mask,
                "vector": True,
                "layer": target,
            }

    @cached_property
    def transform_arrow_textbox_pinlines_mask(self) -> MaskAction | None:
        """This mask hides the textbox stroke from where the transform arrow is."""
        if (mask := psd.getLayer(LAYER_NAMES.ARROW, self.mask_group)) and (
            target := psd.getLayerSet(
                self.textbox_size, [self.pinlines_group, LAYERS.TEXTBOX]
            )
        ):
            return {
                "mask": mask,
                "vector": True,
                "layer": target,
            }

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
        masks: list[
            MaskAction
            | tuple[ArtLayer | LayerSet, ArtLayer | LayerSet]
            | ArtLayer
            | LayerSet
            | None
        ] = [self.pinlines_vector_mask]
        if self.is_mdfc:
            masks.append(self.mdfc_pinlines_mask)
        if self.is_transform and self.is_front:
            masks.append(self.transform_arrow_textbox_pinlines_mask)
        return masks

    """
    FRAME DETAILS
    """

    @cached_property
    def twins_action(self):
        """Function to call to generate twins colors. Can differ from pinlines_action."""
        return (
            psd.create_color_layer
            if isinstance(self.twins_colors, SolidColor)
            else psd.create_gradient_layer
        )

    @cached_property
    def textbox_action(self):
        """Function to call to generate textbox colors. Can differ from pinlines_action."""
        return (
            psd.create_color_layer
            if isinstance(self.textbox_colors, SolidColor)
            else psd.create_gradient_layer
        )

    """
    RENDER CHAIN
    """

    def enable_frame_layers(self) -> None:
        # VectorTemplate and PlaneswalkerBorderlessTemplate have conflicting textbox_group usage
        # super().enable_frame_layers()

        # Sahdow
        if self.bottom_shadow_enabled and self.bottom_shadow_layer:
            self.bottom_shadow_layer.visible = True

        # Enable text and icons
        if self.text_group:
            self.text_group.visible = True

        # Enable vector shapes
        self.enable_shape_layers()

        # Enable layer masks
        self.enable_layer_masks()

        # Color Indicator
        if self.is_type_shifted and self.indicator_group:
            self.generate_layer(
                group=self.indicator_group,
                colors=self.indicator_colors,
                masks=self.indicator_masks,
            )

        # Pinlines
        for group in [g for g in self.pinlines_groups if g]:
            group.visible = True
            self.generate_layer(
                group=group, colors=self.pinlines_colors, masks=self.pinlines_masks
            )

        # Twins
        if self.twins_group:
            self.generate_layer(
                group=self.twins_group,
                colors=self.twins_colors,
                masks=self.twins_masks,
            )

        # Textbox
        if self.textbox_colors and self.textbox_root_group:
            self.generate_layer(
                group=self.textbox_root_group,
                colors=self.textbox_colors,
                masks=self.textbox_masks,
            )

    def pw_text_layers(self) -> None:
        # Add drop shadow if enabled and allowed
        if self.colored_textbox and self.is_drop_shadow:
            for layer in [
                self.text_layer_ability,
                self.text_layer_static,
                self.text_layer_colon,
            ]:
                psd.enable_layer_fx(layer)

        if self.colored_textbox and not (
            (self.is_mdfc or self.is_transform) and self.is_authentic_front
        ):
            for layer in [
                self.text_layer_ability,
                self.text_layer_static,
                self.text_layer_colon,
            ]:
                if layer:
                    self.set_font_color(layer, self.RGB_WHITE)

        super().pw_text_layers()

        if self.text_layer_ability:
            self.text_layer_ability.visible = False
        if self.text_layer_static:
            self.text_layer_static.visible = False
        if self.text_layer_colon:
            self.text_layer_colon.visible = False

    def post_text_layers(self) -> None:
        # Add drop shadow if enabled and allowed
        if self.is_drop_shadow:
            # Name and Typeline
            psd.enable_layer_fx(self.text_layer_name)
            psd.enable_layer_fx(self.text_layer_type)

        # Align color indicator
        if (
            self.textbox_size != LAYER_NAMES.PW3
            and self.is_transform
            and not self.is_front
            and self.indicator_group
            and isinstance((parent := self.indicator_group.parent), LayerSet)
        ):
            base_shape = psd.getLayer(
                LAYERS.TYPE_LINE, [LAYERS.PINLINES, LAYERS.SHAPE, LAYER_NAMES.PW3]
            )
            target_shape = psd.getLayer(LAYERS.TYPE_LINE, self.pinlines_size_group)
            if base_shape and target_shape:
                delta = (
                    psd.get_layer_dimensions(target_shape)["center_y"]
                    - psd.get_layer_dimensions(base_shape)["center_y"]
                )
                parent.translate(0, delta)

    def rules_text_and_pt_layers(self) -> None:
        pass

    """
    TRANSFORM
    """

    @cached_property
    def pinlines_arrow(self) -> ArtLayer | None:
        return psd.getLayer(
            LAYER_NAMES.ARROW,
            [self.pinlines_group, LAYERS.SHAPE],
        )

    @cached_property
    def textbox_pinlines_arrow(self) -> ArtLayer | None:
        return psd.getLayer(
            LAYER_NAMES.ARROW,
            [self.pinlines_group, LAYERS.TEXTBOX],
        )

    def enable_transform_layers_front(self) -> None:
        super().enable_transform_layers_front()

        for layer in [self.pinlines_arrow, self.textbox_pinlines_arrow]:
            if layer:
                layer.visible = True

    def text_layers_transform_front(self) -> None:
        super().text_layers_transform_front()

        # Use black text
        if self.is_authentic_front:
            for layer in [self.text_layer_name, self.text_layer_type]:
                if layer:
                    self.set_font_color(layer, self.RGB_BLACK)

    def text_layers_transform_back(self):
        # No back side changes
        pass

    """
    MDFC
    """

    def text_layers_mdfc_front(self) -> None:
        super().text_layers_mdfc_front()

        # Use black text
        if self.is_authentic_front:
            for layer in [self.text_layer_name, self.text_layer_type]:
                if layer:
                    self.set_font_color(layer, self.RGB_BLACK)

    """
    UTIL METODS
    """

    def set_font_color(self, layer: ArtLayer, color: SolidColor) -> None:
        """
        Set the font color of a text layer.
        @param color: SolidColor object.
        """
        layer.textItem.color = color


# TODO integrate into Proxyshop (maybe as an option for src.helpers.mask.apply_mask_to_layer_fx)
def apply_vector_mask_to_layer_fx(layer: ArtLayer | LayerSet | None = None) -> None:
    if not layer:
        layer = APP.activeDocument.activeLayer
    ref = ActionReference()
    ref.putIdentifier(sID("layer"), layer.id)
    desc = APP.executeActionGet(ref)
    layer_fx = desc.getObjectValue(sID("layerEffects"))
    layer_fx.putBoolean(sID("vectorMaskAsGlobalMask"), True)
    desc = ActionDescriptor()
    desc.putReference(sID("target"), ref)
    desc.putObject(sID("to"), sID("layer"), layer_fx)
    APP.executeAction(sID("set"), desc, DialogModes.DisplayNoDialogs)
