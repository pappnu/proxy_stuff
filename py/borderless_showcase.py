from functools import cached_property
from typing import Any, Callable, Literal

from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from plugins.proxy_stuff.py.planeswalker import LAYER_NAMES
from src import CFG
from src.enums.adobe import Dimensions
from src.enums.layers import LAYERS
from src.helpers.bounds import get_layer_dimensions
from src.helpers.colors import get_rgb
from src.helpers.effects import apply_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.helpers.masks import apply_mask, copy_layer_mask
from src.schema.adobe import EffectStroke
from src.templates.normal import BorderlessVectorTemplate
from src.templates.planeswalker import PlaneswalkerMod
from src.templates.transform import TransformMod
from src.utils.adobe import LayerObjectTypes, ReferenceLayer


class BorderlessShowcase(BorderlessVectorTemplate, PlaneswalkerMod):
    """
    * Settings
    """

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

    """
    * Checks
    """

    @cached_property
    def is_planeswalker(self) -> bool:
        return hasattr(self.layout, "pw_size")

    """
    * Frame Details
    """

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

    """
    * Colors
    """

    @cached_property
    def pt_colors(self) -> list[int] | list[dict[str, Any]]:
        return self.pinlines_colors

    """
    * Groups
    """

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

    """
    * Reference layers
    """

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

    """
    * Shapes
    """

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
                "Flipside PT Arrow", [self.pinlines_group, LAYERS.SHAPE, LAYERS.TEXTBOX]
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

        # Name
        if layer := getLayerSet(
            LAYERS.TRANSFORM
            if self.is_transform
            else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
            [_shape_group, LAYERS.NAME],
        ):
            layers.append(layer)

        if self.is_planeswalker:
            if layer := getLayerSet(self.size, _shape_group):
                layers.append(layer)
            return layers

        # Typeline
        if not self.is_textless and (
            layer := getLayer(
                self.size,
                [_shape_group, LAYERS.TYPE_LINE],
            )
        ):
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

    @cached_property
    def enabled_shapes(self) -> list[ArtLayer | LayerSet | None]:
        return [
            *super().enabled_shapes,
            *self.pt_box_shape,
            self.flipside_pt_arrow,
            self.bottom_border_shape,
            self.bottom_pinline_shape,
        ]

    """
    * Masks
    """

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

    """
    * Text
    """

    def stroke_collector_symbol(self) -> None:
        if self.expansion_symbol_layer:
            apply_fx(
                self.expansion_symbol_layer,
                [EffectStroke(weight=7, style="out")],
            )

    def format_nickname_text(self) -> None:
        pass

    def textbox_positioning(self) -> None:
        # Get the delta between the highest box and the target box
        if (ref := self.textbox_reference) and (
            shape := get_reference_layer(
                LAYERS.TALL,
                getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group),
            )
        ):
            dims_ref = get_layer_dimensions(ref)
            dims_obj = get_layer_dimensions(shape)
            delta = dims_ref[Dimensions.Top] - dims_obj[Dimensions.Top]
            self.text_layer_type.translate(0, delta)

            # Shift expansion symbol
            if CFG.symbol_enabled and self.expansion_symbol_layer:
                self.expansion_symbol_layer.translate(0, delta)

            # Shift indicator
            if self.is_type_shifted:
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
        if self.is_token:
            methods.remove(self.token_adjustments)
        if not self.is_planeswalker:
            methods.remove(self.pw_layer_positioning)
        return [
            *methods,
            self.stroke_collector_symbol,
            self.pw_enable_loyalty_graphics,
        ]

    """
    * Transform Methods
    """

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

    """
    * MDFC Methods
    """

    def text_layers_mdfc_front(self) -> None:
        pass
