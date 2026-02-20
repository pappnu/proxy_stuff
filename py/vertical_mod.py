from functools import cached_property

from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement, RasterizeType

from src.enums.layers import LAYERS
from src.enums.settings import BorderlessColorMode, BorderlessTextbox
from src.helpers.colors import get_pinline_gradient, rgb_white
from src.helpers.effects import disable_layer_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet, select_layer
from src.helpers.masks import (
    apply_mask,
    apply_mask_to_layer_fx,
    copy_layer_mask,
    enable_vector_mask,
)
from src.layouts import ClassLayout, SagaLayout
from src.schema.colors import ColorObject, GradientConfig
from src.templates.case import CaseMod
from src.templates.classes import ClassMod
from src.templates.normal import BorderlessVectorTemplate
from src.templates.saga import SagaMod
from src.text_layers import FormattedTextArea, FormattedTextField, TextField
from src.utils.adobe import ReferenceLayer

from .helpers import LAYER_NAMES, get_numeric_setting
from .utils.layer_fx import get_stroke_details
from .utils.mask import create_mask_from
from .utils.path import create_shape_layer, get_shape_dimensions
from .uxp.shape import ShapeOperation, merge_shapes
from .uxp.text import create_text_layer_with_path


class VerticalMod(BorderlessVectorTemplate, CaseMod, ClassMod, SagaMod):
    # region Settings

    @cached_property
    def textbox_height(self) -> float | int:
        return max(get_numeric_setting(self.config, "TEXT", "Textbox.Height", 0), 0)

    @cached_property
    def show_vertical_reminder_text(self) -> bool:
        return not self.config.remove_reminder and self.config.get_bool_setting(
            section="TEXT", key="Vertical.Reminder", default=False
        )

    # endregion settings

    # region Checks

    @cached_property
    def is_vertical_layout(self) -> bool:
        return self.is_layout_saga or self.is_class_layout or self.is_case_layout

    @cached_property
    def is_vertical_creature(self) -> bool:
        return self.is_vertical_layout and self.is_creature

    @cached_property
    def has_extra_textbox(self) -> bool:
        return bool(self.is_vertical_creature and self.textbox_height)

    @cached_property
    def is_pt_enabled(self) -> bool:
        return self.is_vertical_creature or super().is_pt_enabled

    # endregion Checks

    # region Frame details

    @cached_property
    def layout_keyword(self) -> str:
        if self.is_layout_saga:
            return LAYERS.SAGA
        if self.is_class_layout or self.is_case_layout:
            return f"{LAYER_NAMES.VERTICAL} {LAYERS.RIGHT}"
        raise NotImplementedError("Unsupported layout")

    @cached_property
    def size(self) -> str:
        if self.is_vertical_layout:
            return BorderlessTextbox.Textless
        return super().size

    @cached_property
    def frame_type(self) -> str:
        if self.is_vertical_layout and self.is_transform:
            return f"{LAYERS.TEXTLESS} {LAYERS.TRANSFORM}"
        return super().frame_type

    @cached_property
    def vertical_mode_layer_name(self) -> str:
        return f"{self.layout_keyword}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}"

    def process_layout_data(self) -> None:
        super().process_layout_data()

        if (
            isinstance(self.layout, SagaLayout)
            and self.is_vertical_creature
            and not self.textbox_height
        ):
            self.layout.saga_description = (
                f"{self.layout.ability_text}\n{self.layout.saga_description}"
            )

    def load_expansion_symbol(self) -> None:
        # There's no tailored slot in the execution chain to insert the shape creation
        # so lets just use something that works
        if self.is_vertical_creature and self.textbox_height:
            self.create_shapes_for_vertical_creature()

        return super().load_expansion_symbol()

    # endregion Frame details

    # region Builders

    def create_shapes_for_vertical_creature(self) -> None:
        if ref_textbox := getLayer(LAYERS.TALL, (self.textbox_group, LAYERS.SHAPE)):
            pinlines_stroke = (
                get_stroke_details(self.pinlines_group) if self.pinlines_group else None
            )
            pinlines_stroke_size = pinlines_stroke["size"] if pinlines_stroke else 0
            ref_textbox_dims = get_shape_dimensions(ref_textbox)
            textbox_bottom = ref_textbox_dims["bottom"] - pinlines_stroke_size
            textbox_top = textbox_bottom - self.textbox_height

            # Build bottom textbox
            self.bottom_textbox_shape = create_shape_layer(
                (
                    {
                        "x": ref_textbox_dims["left"] + pinlines_stroke_size,
                        "y": textbox_top,
                    },
                    {
                        "x": ref_textbox_dims["right"] - pinlines_stroke_size,
                        "y": textbox_top,
                    },
                    {
                        "x": ref_textbox_dims["right"] - pinlines_stroke_size,
                        "y": textbox_bottom,
                    },
                    {
                        "x": ref_textbox_dims["left"] + pinlines_stroke_size,
                        "y": textbox_bottom,
                    },
                ),
                relative_layer=ref_textbox,
                placement=ElementPlacement.PlaceAfter,
            )

            if self.text_layer_ability and self.pt_reference:
                # Build bottom text layer
                text_shape = self.bottom_textbox_shape.duplicate()
                pt_reference = self.pt_reference.duplicate(
                    relativeObject=text_shape,
                    insertionLocation=ElementPlacement.PlaceBefore,
                )
                text_shape = merge_shapes(
                    text_shape, pt_reference, operation=ShapeOperation.SubtractFront
                )
                self.text_layer_ability_bottom = create_text_layer_with_path(
                    text_shape, reference_text=self.text_layer_ability
                )
                disable_layer_fx(self.text_layer_ability_bottom)
                self.text_layer_ability_bottom.move(
                    relativeObject=self.text_layer_ability,
                    insertionLocation=ElementPlacement.PlaceAfter,
                )
                text_shape.remove()

            if ref_textbox_pinlines := getLayer(
                LAYERS.TALL, (self.pinlines_group, LAYERS.SHAPE, LAYERS.TEXTBOX)
            ):
                ref_textbox_pinlines_dims = get_shape_dimensions(ref_textbox_pinlines)
                pinlines_top = (
                    ref_textbox_pinlines_dims["bottom"]
                    - self.textbox_height
                    - 2 * pinlines_stroke_size
                    - (ref_textbox_pinlines_dims["height"] - ref_textbox_dims["height"])
                )

                # Build bottom pinlines
                self.bottom_textbox_pinlines_shape = create_shape_layer(
                    (
                        {"x": ref_textbox_pinlines_dims["left"], "y": pinlines_top},
                        {"x": ref_textbox_pinlines_dims["right"], "y": pinlines_top},
                        {
                            "x": ref_textbox_pinlines_dims["right"],
                            "y": ref_textbox_pinlines_dims["bottom"],
                        },
                        {
                            "x": ref_textbox_pinlines_dims["left"],
                            "y": ref_textbox_pinlines_dims["bottom"],
                        },
                    ),
                    relative_layer=ref_textbox_pinlines,
                    placement=ElementPlacement.PlaceAfter,
                )

                if (
                    ref_vertical_textbox := getLayer(
                        self.vertical_mode_layer_name,
                        [self.textbox_group, LAYERS.SHAPE],
                    )
                ) and (
                    ref_typeline := getLayer(LAYERS.TYPE_LINE, self.references_group)
                ):
                    ref_vertical_textbox_dims = get_shape_dimensions(
                        ref_vertical_textbox
                    )
                    ref_typeline_dims = get_shape_dimensions(ref_typeline)
                    vertical_textbox_bottom = pinlines_top - ref_typeline_dims["height"]

                    # Build vertical textbox
                    self.textbox_shape = create_shape_layer(
                        (
                            {
                                "x": ref_vertical_textbox_dims["left"],
                                "y": ref_vertical_textbox_dims["top"],
                            },
                            {
                                "x": ref_vertical_textbox_dims["right"],
                                "y": ref_vertical_textbox_dims["top"],
                            },
                            {
                                "x": ref_vertical_textbox_dims["right"],
                                "y": vertical_textbox_bottom,
                            },
                            {
                                "x": ref_vertical_textbox_dims["left"],
                                "y": vertical_textbox_bottom,
                            },
                        ),
                        relative_layer=ref_vertical_textbox,
                        placement=ElementPlacement.PlaceAfter,
                    )

                    if ref_vertical_pinline := getLayer(
                        self.vertical_mode_layer_name,
                        [self.pinlines_group, LAYERS.SHAPE, LAYERS.TEXTBOX],
                    ):
                        ref_vertical_pinline_dims = get_shape_dimensions(
                            ref_vertical_pinline
                        )
                        pinline_bottom = vertical_textbox_bottom + (
                            ref_vertical_textbox_dims["top"]
                            - ref_vertical_pinline_dims["top"]
                        )

                        # Build vertical pinline
                        self.vertical_pinlines_shape = create_shape_layer(
                            (
                                {
                                    "x": ref_vertical_pinline_dims["left"],
                                    "y": ref_vertical_pinline_dims["top"],
                                },
                                {
                                    "x": ref_vertical_pinline_dims["right"],
                                    "y": ref_vertical_pinline_dims["top"],
                                },
                                {
                                    "x": ref_vertical_pinline_dims["right"],
                                    "y": pinline_bottom,
                                },
                                {
                                    "x": ref_vertical_pinline_dims["left"],
                                    "y": pinline_bottom,
                                },
                            ),
                            relative_layer=ref_vertical_pinline,
                            placement=ElementPlacement.PlaceAfter,
                        )

    # endregion Builders

    # region Groups

    @cached_property
    def legendary_crown_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.LEGENDARY_CROWN)

    @cached_property
    def references_group(self) -> LayerSet | None:
        return getLayerSet(LAYER_NAMES.REFERENCES)

    @cached_property
    def textbox_reference_group(self) -> LayerSet | None:
        return getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group)

    @cached_property
    def vertical_group(self) -> LayerSet | None:
        if self.is_layout_saga:
            return self.saga_group
        if self.is_class_layout or self.is_case_layout:
            return self.vertical_right_group
        raise NotImplementedError("Unsupported layout")

    @cached_property
    def vertical_right_group(self) -> LayerSet | None:
        return getLayerSet(f"{LAYER_NAMES.VERTICAL} {LAYERS.RIGHT}")

    @cached_property
    def pt_group(self) -> LayerSet | None:
        if self.is_vertical_layout:
            return getLayerSet(LAYERS.PT_BOX)
        return super().pt_group

    @cached_property
    def case_group(self) -> LayerSet | None:
        return self.vertical_right_group

    @cached_property
    def class_group(self) -> LayerSet | None:
        return self.vertical_right_group

    # endregion Groups

    # region Reference layers

    @cached_property
    def art_reference(self) -> ReferenceLayer | None:
        return super(SagaMod, self).art_reference

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_vertical_layout:
            if self.has_extra_textbox:
                return ReferenceLayer(self.textbox_shape)

            # If the full height layer doesn't exist, try to fall back to the normal layer
            return get_reference_layer(
                LAYERS.TEXTBOX_REFERENCE
                + (
                    ""
                    if not self.is_case_layout
                    and (
                        self.show_vertical_reminder_text
                        or (
                            self.is_vertical_creature
                            and isinstance(self.layout, SagaLayout)
                            and self.layout.saga_description
                        )
                    )
                    else " Full"
                )
                + (
                    f" {LAYERS.TRANSFORM_FRONT}"
                    if self.is_front and self.is_flipside_creature
                    else ""
                ),
                self.vertical_group,
            ) or get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}",
                self.vertical_group,
            )

        # TODO Build a new reference shape based on MDFC element dimensions
        # instead of relying on a mask.
        ref = get_reference_layer(
            self.size, getLayerSet(LAYERS.TEXTBOX_REFERENCE, self.text_group)
        )
        if (
            self.is_mdfc
            and ref
            and (
                mask_source := getLayer(
                    LAYERS.MDFC, [self.mask_group, LAYERS.TEXTBOX_REFERENCE]
                )
            )
        ):
            copy_layer_mask(layer_from=mask_source, layer_to=ref)
            # The template uses shapes as reference layers, which need to be
            # rasterized before a mask can be applied to them.
            ref.rasterize(RasterizeType.Shape)
            apply_mask(ref)
            ref.visible = False
        return ref

    @cached_property
    def textbox_bottom_reference(self) -> ReferenceLayer | None:
        return ReferenceLayer(self.bottom_textbox_shape)

    @cached_property
    def type_reference(self) -> ArtLayer | None:
        if not self.config.symbol_enabled:
            return getLayer(
                f"{LAYERS.TYPE_LINE} {LAYER_NAMES.OVERFLOW_REFERENCE}", self.text_group
            )
        return super().type_reference

    # endregion Reference layers

    # region Raster layers

    @cached_property
    def nyx_crown_background(self) -> ArtLayer | None:
        return getLayer(self.background, LAYERS.NYX)

    # endregion Raster layers

    # region Shapes

    @cached_property
    def pinlines_shapes(self) -> list[ArtLayer | LayerSet | None]:
        if self.is_vertical_layout:
            _shape_group = getLayerSet(LAYERS.SHAPE, self.pinlines_group)

            layers: list[ArtLayer | LayerSet | None] = []

            # Name
            if layer := getLayerSet(
                LAYERS.TRANSFORM
                if self.is_transform
                else (LAYERS.MDFC if self.is_mdfc else LAYERS.NORMAL),
                [_shape_group, LAYERS.NAME],
            ):
                layers.append(layer)

            # Add nickname pinlines if required
            if self.is_nickname and (
                layer := getLayerSet(LAYERS.NICKNAME, _shape_group)
            ):
                layers.append(layer)

            # Typeline
            if layer := getLayer(
                LAYERS.TALL if self.has_extra_textbox else LAYER_NAMES.VERTICAL,
                [_shape_group, LAYERS.TYPE_LINE],
            ):
                layers.append(layer)

            # Textbox
            if not self.has_extra_textbox and (
                layer := getLayer(
                    self.vertical_mode_layer_name, [_shape_group, LAYERS.TEXTBOX]
                )
            ):
                layers.append(layer)

            return layers
        return super().pinlines_shapes

    @cached_property
    def typeline_pinline_shape(self) -> ArtLayer | None:
        if self.is_vertical_creature:
            return getLayer(
                LAYERS.TALL, (self.pinlines_group, LAYERS.SHAPE, LAYERS.TYPE_LINE)
            )

    @cached_property
    def bottom_textbox_shape(self) -> ArtLayer | None:
        raise ValueError("Bottom textbox shape hasn't been built yet.")

    @cached_property
    def bottom_textbox_pinlines_shape(self) -> ArtLayer | None:
        raise ValueError("Bottom textbox pinlines shape hasn't been built yet.")

    @cached_property
    def vertical_pinlines_shape(self) -> ArtLayer | None:
        raise ValueError("Vertical pinlines shape hasn't been built yet.")

    @cached_property
    def textbox_transform_front_addition_shape(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return None
        return super().textbox_transform_front_addition_shape

    # endregion Shapes

    # region Color Maps

    @cached_property
    def crown_color_map(self) -> dict[str, ColorObject]:
        return {
            **super().crown_color_map,
            "U": "#116cad",
            "Artifact": "#a3b6bf",
        }

    @cached_property
    def dark_color_map(self) -> dict[str, ColorObject]:
        if self.is_creature:
            gold = "#9e7939"
        elif self.is_land:
            gold = "#9e822f"
        else:
            gold = "#94762f"
        if self.is_land and self.is_colorless:
            land = "#8f8c88"
        elif self.land_colorshift:
            land = "#684e30"
        else:
            land = "#a79c8e"
        return {
            "W": "#878377",
            "U": "#0075be",
            "B": "#282523",
            "R": "#b82e1c",
            "G": "#1f593f",
            "Gold": gold,
            "Land": land,
            "Hybrid": "#a79c8e",
            "Artifact": "#4f6b7d",
            "Colorless": "#74726b",
            "Vehicle": "#885a40",
        }

    @cached_property
    def pinlines_color_map(self) -> dict[str, ColorObject]:
        return {
            "W": "#f6f6ef",
            "U": "#0075be",
            "B": "#383630",
            "R": "#ef3827",
            "G": "#0b7446",
            "Gold": "#e9c748",
            "Land": "#a59385",
            "Artifact": "#8a9fad",
            "Colorless": "#e6ecf2",
            "Vehicle": "#4d2d05",
        }

    @cached_property
    def pt_box_inner_color_map(self) -> dict[str, ColorObject]:
        return {
            **self.dark_color_map,
            "W": "#8f8071",
            "U": "#1e5576",
            "B": "#3c342c",
            "R": "#972122",
            "G": "#185231",
            "Gold": "#87693f",
            "Artifact": "#365d6b",
            "Vehicle": "#684333",
        }

    # endregion Color Maps

    # region Colors

    @cached_property
    def pt_inner_colors(self) -> ColorObject | list[ColorObject] | list[GradientConfig]:
        """
        Colors for inner part of PT box.
        Follows the rules of pt_colors, but uses a different color_map.
        """

        # Default to twins, or Vehicle for non-colored vehicle artifacts
        colors = self.twins

        # Color enabled hybrid OR color enabled multicolor
        if (self.is_hybrid and self.hybrid_colored) or (
            self.is_multicolor and self.multicolor_pt
        ):
            colors = self.identity[-1]
        # Use Hybrid color for color-disabled hybrid cards
        elif self.is_hybrid:
            colors = LAYERS.HYBRID

        # Use artifact twins color if artifact mode isn't colored
        if (
            self.is_artifact
            and not self.is_land
            and self.artifact_color_mode
            not in [
                BorderlessColorMode.Twins_And_PT,
                BorderlessColorMode.All,
                BorderlessColorMode.PT,
            ]
        ):
            colors = LAYERS.ARTIFACT

        # Use Vehicle for non-colored artifacts
        if colors == LAYERS.ARTIFACT and self.is_vehicle:
            colors = LAYERS.VEHICLE

        # Return Solid Color or Gradient notation
        return get_pinline_gradient(
            colors=colors,
            color_map=self.pt_box_inner_color_map,
        )

    # endregion Colors

    # region Text

    @cached_property
    def text_layer_ability(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return getLayer(LAYERS.TEXT, self.vertical_group)
        return super().text_layer_ability

    @cached_property
    def text_layer_ability_bottom(self) -> ArtLayer | None:
        raise ValueError("Bottom ability text layer hasn't been built yet.")

    @cached_property
    def text_layer_reminder(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return getLayer("Reminder Text", self.vertical_group)
        return super().text_layer_reminder

    @cached_property
    def text_layer_rules(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return self.text_layer_ability
        return super().text_layer_rules

    @cached_property
    def text_layer_flipside_pt(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return getLayer(
                LAYERS.FLIPSIDE_POWER_TOUGHNESS,
                [self.vertical_group],
            )
        return super().text_layer_flipside_pt

    @cached_property
    def reminder_divider_layer(self) -> ArtLayer | None:
        return getLayer(LAYERS.DIVIDER, self.vertical_group)

    def rules_text_and_pt_layers(self) -> None:
        if self.is_vertical_layout and not self.is_creature:
            return None
        if (
            self.has_extra_textbox
            and self.text_layer_ability_bottom
            and isinstance(self.layout, SagaLayout)
        ):
            self.text += [
                FormattedTextArea(
                    self.text_layer_ability_bottom,
                    contents=self.layout.ability_text,
                    centered=True,
                    reference=self.textbox_bottom_reference,
                )
            ]
        return (
            super() if self.is_token else super(BorderlessVectorTemplate, self)
        ).rules_text_and_pt_layers()

    def textbox_positioning(self) -> None:
        if (
            self.has_extra_textbox
            and (
                ref_textbox_pinlines := getLayer(
                    LAYERS.TALL, (self.pinlines_group, LAYERS.SHAPE, LAYERS.TEXTBOX)
                )
            )
            and self.bottom_textbox_pinlines_shape
        ):
            delta = (
                get_shape_dimensions(self.bottom_textbox_pinlines_shape)["top"]
                - get_shape_dimensions(ref_textbox_pinlines)["top"]
            )

            # Shift typeline text
            if self.text_layer_type:
                self.text_layer_type.translate(0, delta)

            # Shift typeline pinline
            if self.typeline_pinline_shape:
                self.typeline_pinline_shape.translate(0, delta)

            # Shift typeline box
            if isinstance((typeline_box := self.twins_shapes[1]), ArtLayer):
                typeline_box.translate(0, delta)

                # Create mask for pinlines
                if (
                    isinstance((name_box := self.twins_shapes[0]), ArtLayer)
                    and self.bottom_textbox_shape
                    and self.pinlines_group
                ):
                    apply_to: list[LayerSet] = [self.pinlines_group]
                    if self.is_legendary and self.legendary_crown_group:
                        apply_to.append(self.legendary_crown_group)
                    create_mask_from(
                        apply_to,
                        (name_box, typeline_box, self.bottom_textbox_shape),
                    )
                    for layer in apply_to:
                        apply_mask_to_layer_fx(layer)

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

            # For some reason, at this point Photoshop is in a state where
            # even basic actions like removing a layer that is not selected
            # causes the currently selected layer to become visible, so as a
            # precaution let's select some layer that should be visible anyway.
            if self.art_layer:
                select_layer(self.art_layer)
        else:
            super().textbox_positioning()

    # endregion Text

    # region Case

    def frame_layers_case(self) -> None:
        if self.case_group:
            self.case_group.visible = True
        return super().frame_layers_case()

    # endregion Case

    # region Class

    def frame_layers_classes(self) -> None:
        if self.class_group:
            self.class_group.visible = True
        if not self.show_vertical_reminder_text:
            if self.text_layer_reminder:
                self.text_layer_reminder.visible = False
            if self.reminder_divider_layer:
                self.reminder_divider_layer.visible = False
        elif self.text_layer_reminder:
            self.text_layer_reminder.visible = True

    # TODO find out a way to set the cost colon as white that doesn't involve lots of copy paste
    def text_layers_classes(self) -> None:
        if isinstance(self.layout, ClassLayout) and self.text_layer_ability:
            # Add first static line
            self.class_line_layers.append(self.text_layer_ability)
            self.text.append(
                FormattedTextField(
                    layer=self.text_layer_ability,
                    contents=self.layout.class_lines[0]["text"],
                )
            )

            # Add text fields for each line and class stage
            for i, line in enumerate(self.layout.class_lines[1:]):
                # Create a new ability line
                line_layer = self.text_layer_ability.duplicate()
                self.class_line_layers.append(line_layer)

                if self.stage_group:
                    # Use existing stage divider or create new one
                    stage = self.stage_group if i == 0 else self.stage_group.duplicate()
                    cost, level = [*stage.artLayers][:2]
                    self.class_stage_layers.append(stage)

                    # Add text layers to be formatted
                    self.text.extend(
                        [
                            FormattedTextField(layer=line_layer, contents=line["text"]),
                            FormattedTextField(
                                layer=cost,
                                contents=f"{line['cost']}:",
                                # the whole function had to be overridden to set this color kwarg
                                color=rgb_white(),
                            ),
                            TextField(layer=level, contents=f"Level {line['level']}"),
                        ]
                    )

    # endregion Class

    # region Saga

    def frame_layers_saga(self):
        if self.saga_group:
            self.saga_group.visible = True

        if (
            self.is_nyx
            and self.is_legendary
            and self.legendary_crown_group
            and self.nyx_crown_background
        ):
            enable_vector_mask(self.legendary_crown_group)
            self.nyx_crown_background.visible = True

    # TODO submit reminder and icon improvements to Proxyshop
    def text_layers_saga(self):
        if isinstance(self.layout, SagaLayout):
            # Handle reminder text
            if self.text_layer_reminder:
                if self.layout.saga_description and (
                    self.show_vertical_reminder_text
                    or (self.is_vertical_creature and not self.has_extra_textbox)
                ):
                    self.text.append(
                        FormattedTextArea(
                            layer=self.text_layer_reminder,
                            contents=self.layout.saga_description,
                            reference=self.reminder_reference,
                        )
                    )
                    if self.ability_divider_layer:
                        self.ability_divider_layer.visible = True
                else:
                    self.text_layer_reminder.visible = False

            # Iterate through each saga stage and add line to text layers
            if (icon_ref := getLayerSet(LAYER_NAMES.ICON, self.saga_group)) and (
                text_ref := getLayer(LAYERS.TEXT, [icon_ref])
            ):
                for i, line in enumerate(self.layout.saga_lines):
                    # Generate icon layers for this ability
                    icons: list[ArtLayer | LayerSet] = []
                    for n in line["icons"]:
                        text_ref.textItem.contents = n
                        duplicate = icon_ref.duplicate()
                        icons.append(duplicate)
                    self.saga_icon_layers.append(icons)

                    # Add ability text for this ability
                    if self.text_layer_ability:
                        layer = (
                            self.text_layer_ability
                            if i == 0
                            else self.text_layer_ability.duplicate()
                        )
                        self.saga_ability_layers.append(layer)
                        self.text.append(
                            FormattedTextField(layer=layer, contents=line["text"])
                        )

    # endregion Saga
