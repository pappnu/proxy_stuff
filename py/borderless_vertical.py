from functools import cached_property
from typing import Any, Callable

from photoshop.api import SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import CFG
from src.enums.layers import LAYERS
from src.helpers.colors import get_rgb, rgb_white
from src.helpers.effects import enable_layer_fx
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.helpers.masks import apply_mask_to_layer_fx
from src.layouts import SagaLayout
from src.templates.classes import ClassMod
from src.templates.normal import BorderlessVectorTemplate
from src.templates.saga import SagaMod
from src.text_layers import FormattedTextArea, FormattedTextField, TextField
from src.utils.adobe import LayerObjectTypes, ReferenceLayer

from .helpers import LAYER_NAMES, create_clipping_mask, find_art_layer


class BorderlessVertical(BorderlessVectorTemplate, ClassMod, SagaMod):
    # region Settings

    @cached_property
    def show_vertical_reminder_text(self) -> bool:
        return bool(
            CFG.get_setting(section="TEXT", key="Vertical.Reminder", default=False)
        )

    @cached_property
    def color_typeline(self) -> bool:
        return bool(
            CFG.get_setting(section="COLORS", key="Color.Typeline", default=False)
        )

    @cached_property
    def color_textbox(self) -> bool:
        return bool(
            CFG.get_setting(section="COLORS", key="Color.Textbox", default=False)
        )

    # endregion Settings

    # region Checks

    # TODO remove this once is_layout_saga has been marked as property on Proxyshop's side
    @cached_property
    def is_layout_saga(self) -> bool:
        return isinstance(self.layout, SagaLayout)

    @cached_property
    def is_vertical_layout(self) -> bool:
        return self.is_layout_saga or self.is_class_layout

    # endregion Checks

    # region Frame details

    @cached_property
    def layout_keyword(self) -> str:
        if self.is_layout_saga:
            return LAYERS.SAGA
        if self.is_class_layout:
            return LAYERS.CLASS
        raise NotImplementedError("Unsupported layout")

    @cached_property
    def size(self) -> str:
        if self.is_vertical_layout:
            return LAYERS.TEXTLESS
        return super().size

    @cached_property
    def frame_type(self) -> str:
        if self.is_vertical_layout and self.is_transform:
            return f"{LAYERS.TEXTLESS} {LAYERS.TRANSFORM}"
        return super().frame_type

    @cached_property
    def vertical_mode_layer_name(self) -> str:
        return f"{self.layout_keyword}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}"

    # endregion Frame details

    # region Groups

    @cached_property
    def vertical_group(self) -> LayerSet | None:
        if self.is_layout_saga:
            return self.saga_group
        if self.is_class_layout:
            return self.class_group
        raise NotImplementedError("Unsupported layout")

    # endregion Groups

    # region Shapes

    @cached_property
    def pinlines_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        if self.is_vertical_layout:
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

            # Add nickname pinlines if required
            if self.is_nickname:
                layers.append(getLayerSet(LAYERS.NICKNAME, _shape_group))

            # Typeline
            if layer := getLayer(
                LAYER_NAMES.VERTICAL,
                [_shape_group, LAYERS.TYPE_LINE],
            ):
                layers.append(layer)

            # Textbox
            if layer := getLayer(
                self.vertical_mode_layer_name, [_shape_group, LAYERS.TEXTBOX]
            ):
                layers.append(layer)

            return layers
        return super().pinlines_shape

    @cached_property
    def twins_shape(self) -> LayerObjectTypes | list[LayerObjectTypes | None] | None:
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
                    LAYER_NAMES.VERTICAL,
                    [_shape_group, LAYERS.TYPE_LINE],
                ),
            ]
        return super().twins_shape

    @cached_property
    def textbox_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        if self.is_vertical_layout:
            return getLayer(
                self.vertical_mode_layer_name,
                [self.textbox_group, LAYERS.SHAPE],
            )
        return super().textbox_shape

    # endregion Shapes

    # region Masks

    @cached_property
    def border_mask(self) -> list[ArtLayer] | dict[str, Any] | None:
        if self.is_vertical_layout:
            return {
                "mask": getLayer(
                    LAYER_NAMES.VERTICAL, [self.mask_group, LAYERS.BORDER]
                ),
                "layer": self.border_group,
                "vector": True,
            }
        return super().border_mask

    @cached_property
    def pinlines_mask(self) -> dict[str, Any]:
        if self.is_vertical_layout:
            return {
                "mask": getLayer(
                    f"{LAYER_NAMES.VERTICAL}{f' {LAYERS.TRANSFORM}' if self.is_transform else ''}",
                    [self.mask_group, LAYERS.PINLINES],
                ),
                "layer": self.pinlines_group,
                "funcs": [apply_mask_to_layer_fx],
            }
        return super().pinlines_mask

    # endregion Masks

    # region Reference layers

    @cached_property
    def art_reference(self) -> ReferenceLayer:
        return super(SagaMod, self).art_reference

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_vertical_layout:
            return get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE}{'' if self.show_vertical_reminder_text else ' Full'}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}",
                self.vertical_group,
            )
        return super().textbox_reference

    # endregion Reference layers

    # region Text

    def swap_layer_font_color(
        self, layer: ArtLayer, color: SolidColor | None = None
    ) -> None:
        color = color or self.RGB_BLACK
        layer.textItem.color = color

    @cached_property
    def text_layer_ability(self) -> ArtLayer | None:
        return getLayer(LAYERS.TEXT, self.vertical_group)

    @cached_property
    def text_layer_reminder(self) -> ArtLayer | None:
        return getLayer("Reminder Text", self.vertical_group)

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

    # endregion Text

    # region Hooks

    def disable_colors(self) -> None:
        if (
            not self.color_textbox
            and self.textbox_group
            and (
                layer := find_art_layer(
                    self.textbox_group,
                    lambda layer: layer.name.startswith("Color Fill"),
                )
            )
        ):
            layer.remove()
        if (
            not self.color_typeline
            and self.twins_group
            and (
                layer := find_art_layer(
                    self.twins_group, lambda layer: layer.name.startswith("Color Fill")
                )
            )
        ):
            layer.move(
                getLayerSet(LAYER_NAMES.CARD_NAME, [self.twins_group, LAYERS.SHAPE]),
                ElementPlacement.PlaceBefore,
            )
            create_clipping_mask(layer)

    @property
    def hooks(self) -> list[Callable[[], None]]:
        return [*super().hooks, self.disable_colors]

    # endregion Hooks

    # region Class

    def frame_layers_classes(self) -> None:
        if self.class_group:
            self.class_group.visible = True
        if (
            not self.show_vertical_reminder_text
            and self.text_layer_reminder
            and self.reminder_divider_layer
        ):
            self.text_layer_reminder.visible = False
            self.reminder_divider_layer.visible = False

    # TODO find out a way to set the cost colon as white that doesn't involve lots of copy paste
    def text_layers_classes(self) -> None:
        # Add first static line
        self.line_layers.append(self.text_layer_ability)
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
            self.line_layers.append(line_layer)

            # Use existing stage divider or create new one
            stage = self.stage_group if i == 0 else self.stage_group.duplicate()
            cost, level = [*stage.artLayers][:2]
            self.stage_layers.append(stage)

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

    # TODO submit reminder and icon improvements to Proxyshop
    def text_layers_saga(self):
        # Handle reminder text
        if self.show_vertical_reminder_text:
            self.text.append(
                FormattedTextArea(
                    layer=self.text_layer_reminder,
                    contents=self.layout.saga_description,
                    reference=self.reminder_reference,
                )
            )
        else:
            self.text_layer_reminder.visible = False

        if self.color_textbox and self.is_authentic_front:
            self.swap_layer_font_color(self.text_layer_ability)

        if self.is_drop_shadow:
            enable_layer_fx(self.text_layer_ability)

        # Iterate through each saga stage and add line to text layers
        for i, line in enumerate(self.layout.saga_lines):
            # Generate icon layers for this ability
            icon_ref = getLayerSet(LAYER_NAMES.ICON, self.saga_group)
            if icon_ref:
                icons: list[LayerSet] = []
                if text_ref := getLayer(LAYERS.TEXT, [icon_ref]):
                    for n in line["icons"]:
                        text_ref.textItem.contents = n
                        duplicate = icon_ref.duplicate()
                        icons.append(duplicate)
                self.icon_layers.append(icons)

            # Add ability text for this ability
            layer = (
                self.text_layer_ability
                if i == 0
                else self.text_layer_ability.duplicate()
            )
            self.ability_layers.append(layer)
            self.text.append(FormattedTextField(layer=layer, contents=line["text"]))

    # endregion Saga

    # region Transform

    def text_layers_transform_front(self) -> None:
        if self.is_layout_saga:
            if self.is_authentic_front and self.text_layer_name:
                self.swap_layer_font_color(self.text_layer_name)

            if self.is_authentic_front and self.color_typeline and self.text_layer_type:
                self.swap_layer_font_color(self.text_layer_type)

            if self.color_textbox and self.show_vertical_reminder_text:
                self.swap_layer_font_color(self.text_layer_reminder)

            if (
                self.color_textbox
                and not self.is_authentic_front
                and self.is_flipside_creature
                and self.text_layer_flipside_pt
            ):
                self.text_layer_flipside_pt.textItem.color = get_rgb(*[186, 186, 186])

            super(BorderlessVectorTemplate, self).text_layers_transform_front()
        else:
            super().text_layers_transform_front()

    # endregion Transform
