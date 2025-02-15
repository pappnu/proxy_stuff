from functools import cached_property
from typing import Any, Callable, Literal

from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import CFG
from src.enums.layers import LAYERS
from src.helpers.colors import get_rgb
from src.helpers.effects import apply_fx
from src.helpers.layers import getLayer, getLayerSet
from src.schema.adobe import EffectStroke
from src.templates.normal import BorderlessVectorTemplate
from src.templates.transform import TransformMod
from src.utils.adobe import LayerObjectTypes


class BorderlessShowcase(BorderlessVectorTemplate):
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
    * Frame Details
    """

    @property
    def art_frame_vertical(self) -> str:
        if self.bottom_border_type == "Full":
            return "Full Art Frame Alt"
        return super().art_frame_vertical

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
        if self.bottom_border_type == "None":
            return None
        return getLayer(self.bottom_border_type, LAYERS.BORDER)

    @cached_property
    def pinlines_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        _shape_group = getLayerSet(LAYERS.SHAPE, self.pinlines_group)

        # Name and typeline always included
        layers: list[LayerObjectTypes | None] = [
            getLayerSet(
                LAYERS.TRANSFORM
                if self.is_transform
                else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
                [_shape_group, LAYERS.NAME],
            ),
            getLayer(
                LAYERS.TEXTLESS if self.is_textless else self.size,
                [_shape_group, LAYERS.TYPE_LINE],
            ),
        ]

        # Add nickname pinlines if required
        if self.is_nickname and not self.is_legendary:
            layers.append(getLayerSet(LAYERS.NICKNAME, _shape_group))

        # Skip others for textless
        if self.is_textless:
            return layers

        # Add Transform Front cutout if required
        if self.is_transform and self.is_front:
            layers.append(
                getLayer(LAYERS.TRANSFORM_FRONT, [_shape_group, LAYERS.TEXTBOX])
            )
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
        """Vector shapes that should be enabled during the enable_shape_layers step. Should be
        a list of layer, layer group, or None objects."""
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

    @cached_property
    def enabled_masks(
        self,
    ) -> list[dict[str, Any] | list[Any] | ArtLayer | LayerSet | None]:
        return []

    """
    * Text
    """

    def stroke_collector_symbol(self) -> None:
        if self.expansion_symbol_layer:
            apply_fx(
                self.expansion_symbol_layer,
                [EffectStroke(weight=16, style="out")],
            )

    def format_nickname_text(self) -> None:
        pass

    @property
    def post_text_methods(self) -> list[Callable[[None], None]]:
        return [*super().post_text_methods, self.stroke_collector_symbol]

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
