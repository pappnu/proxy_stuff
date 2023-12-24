from typing import Any, Optional

from photoshop.api import ActionDescriptor, ActionReference, DialogModes, SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

import src.helpers as psd
from src import APP, CFG
from src.enums.adobe import Dimensions
from src.enums.layers import LAYERS
from src.frame_logic import contains_frame_colors
from src.templates import (
    PlaneswalkerExtendedTemplate,
    VectorBorderlessMod,
    VectorTemplate,
)
from src.templates.mdfc import VectorMDFCMod
from src.templates.transform import VectorTransformMod
from src.utils.properties import auto_prop_cached
from src.utils.strings import StrEnum

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID
NO_DIALOG = DialogModes.DisplayNoDialogs


class LAYER_NAMES(StrEnum):
    ARROW = "Arrow"
    ABILITY_DIVIDERS = "Ability Dividers"
    SHADOW = "Shadow"
    PW3 = "pw-3"
    PW4 = "pw-4"


class PlaneswalkerBorderlessVector(
    VectorBorderlessMod,
    VectorMDFCMod,
    VectorTransformMod,
    VectorTemplate,
    PlaneswalkerExtendedTemplate,
):
    """
    SETTINGS
    """

    @auto_prop_cached
    def color_limit(self) -> int:
        return (
            int(
                CFG.get_setting(
                    section="COLORS", key="Max.Colors", default="2", is_bool=False
                )
            )
            + 1
        )

    @auto_prop_cached
    def colored_textbox(self) -> bool:
        """Returns True if Textbox should be colored."""
        return bool(
            CFG.get_setting(section="COLORS", key="Color.Textbox", default=True)
        )

    @auto_prop_cached
    def multicolor_textbox(self) -> bool:
        """Returns True if Textbox for multicolored cards should use blended colors."""
        return bool(
            CFG.get_setting(section="COLORS", key="Multicolor.Textbox", default=True)
        )

    @auto_prop_cached
    def multicolor_pinlines(self) -> bool:
        """Returns True if Pinlines and Crown for multicolored cards should use blended colors."""
        return bool(
            CFG.get_setting(section="COLORS", key="Multicolor.Pinlines", default=True)
        )

    @auto_prop_cached
    def multicolor_twins(self) -> bool:
        """Returns True if Twins for multicolored cards should use blended colors."""
        return bool(
            CFG.get_setting(section="COLORS", key="Multicolor.Twins", default=True)
        )

    @auto_prop_cached
    def hybrid_colored(self) -> bool:
        """Returns True if Twins and PT should be colored on Hybrid cards."""
        return bool(
            CFG.get_setting(section="COLORS", key="Hybrid.Colored", default=True)
        )

    @auto_prop_cached
    def front_face_colors(self) -> bool:
        """Returns True if lighter color map should be used on front face DFC cards."""
        return bool(
            CFG.get_setting(section="COLORS", key="Front.Face.Colors", default=True)
        )

    @auto_prop_cached
    def drop_shadow_enabled(self) -> bool:
        """Returns True if Drop Shadow text setting is enabled."""
        return bool(CFG.get_setting(section="SHADOWS", key="Drop.Shadow", default=True))

    @auto_prop_cached
    def bottom_shadow_enabled(self) -> bool:
        """Returns True if Bottom Shadow setting is enabled."""
        return bool(
            CFG.get_setting(section="SHADOWS", key="Bottom.Shadow", default=True)
        )

    """
    DETAILS
    """

    @auto_prop_cached
    def is_content_aware_enabled(self) -> bool:
        return True

    @auto_prop_cached
    def textbox_size(self) -> str:
        if self.layout.pw_size > 3:
            return LAYER_NAMES.PW4
        return LAYER_NAMES.PW3

    """
    BOOL
    """

    @auto_prop_cached
    def is_multicolor(self) -> bool:
        """Whether the card is multicolor and within the color limit range."""
        return bool(1 <= len(self.identity) < self.color_limit)

    @auto_prop_cached
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

    @auto_prop_cached
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

    @auto_prop_cached
    def dark_color_map(self) -> dict[str, str]:
        return {
            "W": "958676",
            "U": "045482",
            "B": "282523",
            "R": "93362a",
            "G": "134f23",
            "Gold": "9a883f",
            "Hybrid": "a79c8e",
            "Colorless": "74726b",
        }

    @auto_prop_cached
    def light_color_map(self) -> dict[str, str]:
        return {
            "W": "faf8f2",
            "U": "d2edfa",
            "B": "c9c2be",
            "R": "f8c7b0",
            "G": "dbfadc",
            "Gold": "f5e5a4",
            "Hybrid": "f0ddce",
            "Colorless": "e2d8d4",
        }

    @auto_prop_cached
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

    @auto_prop_cached
    def twins_colors(self) -> SolidColor | list[dict[str, Any]]:
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

    @auto_prop_cached
    def textbox_colors(self) -> SolidColor | list[dict[str, Any]]:
        # Default to twins
        colors = self.twins

        # Hybrid OR color enabled multicolor
        if self.is_hybrid or (self.is_multicolor and self.multicolor_textbox):
            colors = self.identity

        # Return Solid Color or Gradient notation
        return psd.get_pinline_gradient(
            colors=colors,
            color_map=self.light_color_map
            if self.is_authentic_front
            else self.dark_color_map,
            location_map=self.gradient_location_map,
        )

    @auto_prop_cached
    def pinlines_colors(self) -> SolidColor | list[dict[str, Any]]:
        # Use alternate gradient location map
        return psd.get_pinline_gradient(
            # Use identity for hybrid OR color enabled multicolor
            self.identity
            if self.is_hybrid or (self.is_multicolor and self.multicolor_pinlines)
            else (
                # Use pinlines if not a color code
                self.pinlines
                if not contains_frame_colors(self.pinlines)
                else LAYERS.GOLD
            ),
            color_map=self.pinline_color_map,
            location_map=self.gradient_location_map,
        )

    """
    GROUPS
    """

    @auto_prop_cached
    def text_group(self) -> Optional[LayerSet]:
        return psd.getLayerSet(self.textbox_size, LAYERS.TEXT_AND_ICONS)

    @auto_prop_cached
    def textbox_root_group(self) -> Optional[LayerSet]:
        return psd.getLayerSet(LAYERS.TEXTBOX)

    @auto_prop_cached
    def textbox_size_group(self) -> Optional[LayerSet]:
        return psd.getLayerSet(self.textbox_size, [LAYERS.TEXTBOX, LAYERS.SHAPE])

    @auto_prop_cached
    def textbox_group(self) -> Optional[LayerSet]:
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

    """
    BASIC LAYERS
    """

    @auto_prop_cached
    def bottom_shadow_layer(self) -> Optional[ArtLayer]:
        return psd.getLayer(LAYER_NAMES.SHADOW)

    """
    TEXT LAYERS
    """

    @auto_prop_cached
    def text_layer_name(self) -> Optional[ArtLayer]:
        if self.is_name_shifted:
            psd.getLayer(LAYERS.NAME, LAYERS.TEXT_AND_ICONS).visible = False
            name = psd.getLayer(LAYERS.NAME_SHIFT, LAYERS.TEXT_AND_ICONS)
            name.visible = True
            return name
        return psd.getLayer(LAYERS.NAME, LAYERS.TEXT_AND_ICONS)

    @auto_prop_cached
    def text_layer_mana(self) -> Optional[ArtLayer]:
        return psd.getLayer(LAYERS.MANA_COST, LAYERS.TEXT_AND_ICONS)

    """
    REFERENCE LAYERS
    """

    @auto_prop_cached
    def textbox_reference(self) -> Optional[ArtLayer]:
        return psd.getLayer(
            LAYERS.TEXTBOX_REFERENCE + " MDFC"
            if self.is_mdfc
            else LAYERS.TEXTBOX_REFERENCE,
            self.text_group,
        )

    """
    VECTOR SHAPES
    """

    @auto_prop_cached
    def pinlines_shape(self) -> Optional[LayerSet]:
        """Vector shape representing the outer textbox pinlines."""
        return psd.getLayerSet(
            self.textbox_size,
            [self.pinlines_group, LAYERS.SHAPE],
        )

    @auto_prop_cached
    def pinlines_card_name_shape(self) -> Optional[LayerSet]:
        """Vector shape representing the card name pinlines."""
        return psd.getLayerSet(
            LAYERS.MDFC
            if self.is_mdfc
            else LAYERS.TRANSFORM
            if self.is_transform
            else LAYERS.NORMAL,
            [self.pinlines_group, LAYERS.SHAPE, LAYERS.NAME],
        )

    @auto_prop_cached
    def pinlines_textbox_shape(self) -> Optional[ArtLayer]:
        """Vector shape representing the inner textbox pinlines."""
        return psd.getLayer(
            LAYERS.NORMAL,
            [self.pinlines_group, LAYERS.TEXTBOX, self.textbox_size],
        )

    @auto_prop_cached
    def textbox_shape(self) -> Optional[ArtLayer]:
        """Vector shape representing the card textbox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_front and self.is_transform else LAYERS.TEXTBOX,
            self.textbox_size_group,
        )

    @auto_prop_cached
    def textbox_shape_other(self) -> Optional[ArtLayer]:
        """Vector shape representing the less opaque card textbox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_front and self.is_transform else LAYERS.TEXTBOX,
            [self.textbox_size_group, LAYER_NAMES.ABILITY_DIVIDERS],
        )

    @auto_prop_cached
    def namebox_shape(self) -> Optional[ArtLayer]:
        """Vector shape representing the card namebox."""
        return psd.getLayer(
            LAYERS.TRANSFORM if self.is_transform or self.is_mdfc else LAYERS.NORMAL,
            [self.twins_group, LAYERS.SHAPE, LAYERS.NAME],
        )

    @auto_prop_cached
    def typebox_shape(self) -> Optional[ArtLayer]:
        """Vector shape representing the card typebox."""
        return psd.getLayer(
            self.textbox_size,
            [self.twins_group, LAYERS.SHAPE, LAYERS.TYPE_LINE],
        )

    @auto_prop_cached
    def enabled_shapes(self) -> list[ArtLayer | LayerSet | None]:
        """Vector shapes that should be enabled during the enable_shape_layers step."""
        return [
            self.border_shape,
            self.namebox_shape,
            self.typebox_shape,
            self.pinlines_shape,
            self.pinlines_card_name_shape,
            self.pinlines_textbox_shape,
            self.textbox_shape,
            self.textbox_shape_other,
        ]

    """
    MASKS
    """

    @auto_prop_cached
    def pinlines_vector_mask(self) -> dict[str, Any]:
        """This mask hides undesired layer effects."""
        return {
            "vector": psd.getLayer(
                LAYERS.TRANSFORM_FRONT
                if self.is_transform and self.is_front
                else LAYERS.TRANSFORM
                if self.is_mdfc or self.is_transform
                else LAYERS.NORMAL,
                [self.mask_group, self.textbox_size],
            ),
            "layer": psd.getLayerSet(LAYERS.SHAPE, self.pinlines_group),
            "funcs": [apply_vector_mask_to_layer_fx],
        }

    @auto_prop_cached
    def mdfc_pinlines_mask(self) -> dict[str, Any]:
        """This mask hides pinlines below the MDFC bottom box."""
        return {
            "vector": psd.getLayer("MDFC Bottom", self.mask_group),
            "layer": psd.getLayerSet(
                self.textbox_size, [self.pinlines_group, LAYERS.SHAPE]
            ),
        }

    @auto_prop_cached
    def transform_arrow_textbox_pinlines_mask(self) -> dict[str, Any]:
        """This mask hides the textbox stroke from where the transform arrow is."""
        return {
            "vector": psd.getLayer(LAYER_NAMES.ARROW, self.mask_group),
            "layer": psd.getLayerSet(
                self.textbox_size, [self.pinlines_group, LAYERS.TEXTBOX]
            ),
        }

    @auto_prop_cached
    def enabled_masks(
        self,
    ) -> list[dict[str, Any] | list[ArtLayer | LayerSet] | ArtLayer | LayerSet | None]:
        masks: list[
            dict[str, Any] | list[ArtLayer | LayerSet] | ArtLayer | LayerSet | None
        ] = [self.pinlines_vector_mask]
        if self.is_mdfc:
            masks.append(self.mdfc_pinlines_mask)
        if self.is_transform and self.is_front:
            masks.append(self.transform_arrow_textbox_pinlines_mask)
        return masks

    """
    FRAME DETAILS
    """

    @auto_prop_cached
    def twins_action(self):
        """Function to call to generate twins colors. Can differ from pinlines_action."""
        return (
            psd.create_color_layer
            if isinstance(self.twins_colors, SolidColor)
            else psd.create_gradient_layer
        )

    @auto_prop_cached
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
        """Build the card frame by enabling and/or creating various layer."""

        # Enable vector shapes
        self.enable_shape_layers()

        # Enable layer masks
        self.enable_layer_masks()

        # Sahdow
        if self.bottom_shadow_enabled:
            self.bottom_shadow_layer.visible = True

        # Enable text and icons
        self.text_group.visible = True

        # Color Indicator -> Blended solid color layers
        if self.is_type_shifted and self.indicator_group:
            self.create_blended_solid_color(
                group=self.indicator_group,
                colors=self.indicator_colors,
                masks=self.indicator_masks,
            )

        # Pinlines -> Solid color or gradient layers
        for group in [g for g in self.pinlines_groups if g]:
            group.visible = True
            self.pinlines_action(self.pinlines_colors, layer=group)

        # Twins -> Solid color or gradient layer
        if self.twins_group:
            self.twins_action(self.twins_colors, layer=self.twins_group)

        # Textbox -> Solid color or gradient layer
        if self.colored_textbox and self.textbox_group:
            self.textbox_action(self.textbox_colors, layer=self.textbox_root_group)

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
                self.set_font_color(layer, self.RGB_WHITE)

        super().pw_text_layers()

        self.text_layer_ability.visible = False
        self.text_layer_static.visible = False
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
        ):
            base_shape = psd.getLayer(
                LAYERS.TYPE_LINE, [LAYERS.PINLINES, LAYERS.SHAPE, LAYER_NAMES.PW3]
            )
            target_shape = psd.getLayer(LAYERS.TYPE_LINE, self.pinlines_shape)
            delta = (
                psd.get_layer_dimensions(target_shape)[Dimensions.CenterY]
                - psd.get_layer_dimensions(base_shape)[Dimensions.CenterY]
            )
            self.indicator_group.parent.translate(0, delta)

    def rules_text_and_pt_layers(self) -> None:
        pass

    """
    TRANSFORM
    """

    @auto_prop_cached
    def transform_circle_layer(self) -> Optional[LayerSet]:
        return psd.getLayerSet(LAYERS.TRANSFORM, LAYERS.TEXT_AND_ICONS)

    @auto_prop_cached
    def pinlines_arrow(self) -> Optional[ArtLayer]:
        return psd.getLayer(
            LAYER_NAMES.ARROW,
            [self.pinlines_group, LAYERS.SHAPE],
        )

    @auto_prop_cached
    def textbox_pinlines_arrow(self) -> Optional[ArtLayer]:
        return psd.getLayer(
            LAYER_NAMES.ARROW,
            [self.pinlines_group, LAYERS.TEXTBOX],
        )

    def enable_transform_layers_front(self) -> None:
        super().enable_transform_layers_front()

        for layer in [self.pinlines_arrow, self.textbox_pinlines_arrow]:
            layer.visible = True

    def text_layers_transform_front(self) -> None:
        super().text_layers_transform_front()

        # Use black text
        if self.is_authentic_front:
            for layer in [self.text_layer_name, self.text_layer_type]:
                self.set_font_color(layer, self.RGB_BLACK)

    def text_layers_transform_back(self):
        # No back side changes
        pass

    """
    MDFC
    """

    @auto_prop_cached
    def dfc_group(self) -> Optional[LayerSet]:
        if self.face_type:
            return psd.getLayerSet(self.face_type, LAYERS.TEXT_AND_ICONS)

    def text_layers_mdfc_front(self) -> None:
        super().text_layers_mdfc_front()

        # Use black text
        if self.is_authentic_front:
            for layer in [self.text_layer_name, self.text_layer_type]:
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
    APP.executeAction(sID("set"), desc, NO_DIALOG)
