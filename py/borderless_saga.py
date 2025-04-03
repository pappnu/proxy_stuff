from functools import cached_property
from typing import Callable

from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import CFG
from src.enums.layers import LAYERS
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.helpers.masks import disable_mask
from src.layouts import SagaLayout
from src.templates.normal import BorderlessVectorTemplate
from src.templates.saga import SagaMod
from src.text_layers import FormattedTextArea, FormattedTextField
from src.utils.adobe import LayerObjectTypes, ReferenceLayer

from .helpers import LAYER_NAMES, create_clipping_mask, find_art_layer


class BorderlessSaga(BorderlessVectorTemplate, SagaMod):
    # region Settings

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

    # endregion Checks

    # region Frame details

    @cached_property
    def layout_keyword(self) -> str:
        if self.is_layout_saga:
            return LAYERS.SAGA
        raise NotImplementedError("Unsupported layout")

    @cached_property
    def size(self) -> str:
        if self.is_layout_saga:
            return LAYERS.TEXTLESS
        return super().size

    # endregion Frame details

    # region Shapes

    @cached_property
    def pinlines_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        if self.is_layout_saga:
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
                LAYERS.SAGA,
                [_shape_group, LAYERS.TYPE_LINE],
            ):
                layers.append(layer)

            # Textbox
            if layer := getLayer(LAYERS.SAGA, [_shape_group, LAYERS.TEXTBOX]):
                layers.append(layer)

            return layers
        return super().pinlines_shape

    @cached_property
    def twins_shape(self) -> LayerObjectTypes | list[LayerObjectTypes | None] | None:
        if self.is_layout_saga:
            _shape_group = getLayerSet(LAYERS.SHAPE, self.twins_group)
            return [
                getLayer(
                    LAYERS.TRANSFORM
                    if self.is_transform or self.is_mdfc
                    else LAYERS.NORMAL,
                    [_shape_group, LAYERS.NAME],
                ),
                getLayer(
                    LAYERS.SAGA,
                    [_shape_group, LAYERS.TYPE_LINE],
                ),
            ]
        return super().twins_shape

    @cached_property
    def textbox_shape(self) -> LayerObjectTypes | list[LayerObjectTypes] | None:
        if self.is_layout_saga:
            return getLayer(LAYERS.SAGA, [self.textbox_group, LAYERS.SHAPE])
        return super().textbox_shape

    # endregion Shapes

    # region Reference layers

    @cached_property
    def art_reference(self) -> ReferenceLayer:
        return super(SagaMod, self).art_reference

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_layout_saga:
            return get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE} {LAYERS.TRANSFORM_FRONT}"
                if self.is_front and self.is_flipside_creature
                else LAYERS.TEXTBOX_REFERENCE,
                self.saga_group,
            )
        return super().textbox_reference

    # endregion Reference layers

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

    # region Saga

    def frame_layers_saga(self):
        if self.saga_group:
            self.saga_group.visible = True
        if layer := getLayerSet(LAYERS.SAGA, [self.pinlines_group, LAYERS.SHAPE]):
            layer.visible = True
        disable_mask(self.pinlines_group)

    # TODO Submit the icon generation officially to Proxyshop to avoid this ugly copy paste
    def text_layers_saga(self):
        # Add description text with reminder
        self.text.append(
            FormattedTextArea(
                layer=self.text_layer_reminder,
                contents=self.layout.saga_description,
                reference=self.reminder_reference,
            )
        )

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
