from functools import cached_property

from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import CFG
from src.enums.layers import LAYERS
from src.helpers.colors import rgb_white
from src.helpers.layers import get_reference_layer, getLayer, getLayerSet
from src.layouts import SagaLayout
from src.templates.case import CaseMod
from src.templates.classes import ClassMod
from src.templates.normal import BorderlessVectorTemplate
from src.templates.saga import SagaMod
from src.text_layers import FormattedTextArea, FormattedTextField, TextField
from src.utils.adobe import ReferenceLayer

from .helpers import LAYER_NAMES


class VerticalMod(BorderlessVectorTemplate, CaseMod, ClassMod, SagaMod):
    # region Settings

    @cached_property
    def show_vertical_reminder_text(self) -> bool:
        return bool(
            CFG.get_setting(section="TEXT", key="Vertical.Reminder", default=False)
        )

    # endregion settings

    # region Checks

    # TODO remove this once is_layout_saga has been marked as property on Proxyshop's side
    @cached_property
    def is_layout_saga(self) -> bool:
        return isinstance(self.layout, SagaLayout)

    @cached_property
    def is_vertical_layout(self) -> bool:
        return self.is_layout_saga or self.is_class_layout or self.is_case_layout

    @cached_property
    def is_vertical_creature(self) -> bool:
        return self.is_vertical_layout and self.is_creature

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

    def process_layout_data(self) -> None:
        if self.is_vertical_creature:
            CFG.remove_flavor = True
        return super().process_layout_data()

    # endregion Frame details

    # region Groups

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
    def art_reference(self) -> ReferenceLayer:
        return super(SagaMod, self).art_reference

    @cached_property
    def textbox_reference(self) -> ReferenceLayer | None:
        if self.is_vertical_layout:
            # If the full height layer doesn't exist, try to fall back to the normal layer
            return get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE}{'' if not self.is_case_layout and self.show_vertical_reminder_text else ' Full'}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}",
                self.vertical_group,
            ) or get_reference_layer(
                f"{LAYERS.TEXTBOX_REFERENCE}{f' {LAYERS.TRANSFORM_FRONT}' if self.is_front and self.is_flipside_creature else ''}",
                self.vertical_group,
            )
        return super().textbox_reference

    # endregion Reference layers

    # region Text

    @cached_property
    def text_layer_ability(self) -> ArtLayer | None:
        if self.is_vertical_layout:
            return getLayer(LAYERS.TEXT, self.vertical_group)
        return super().text_layer_ability

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
        return super(SagaMod, self).rules_text_and_pt_layers()

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

        # Iterate through each saga stage and add line to text layers
        if (icon_ref := getLayerSet(LAYER_NAMES.ICON, self.saga_group)) and (
            text_ref := getLayer(LAYERS.TEXT, [icon_ref])
        ):
            for i, line in enumerate(self.layout.saga_lines):
                # Generate icon layers for this ability
                icons: list[LayerSet] = []
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
