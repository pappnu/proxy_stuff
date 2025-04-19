import os
import re
from typing import Callable, Pattern

from photoshop.api._artlayer import ArtLayer
from photoshop.api._document import Document
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ChannelType, ElementPlacement

from src import APP, CFG, CONSOLE
from src.templates import BaseTemplate

from .gui import open_ask_file_dialog


def find_file_in_directory(
    directory_path: str | os.PathLike[str], pattern: str | Pattern[str]
):
    files = os.listdir(directory_path)
    for file in files:
        if re.search(pattern, file, flags=re.IGNORECASE):
            return file
    return None


def find_layer(
    layer_sets: Document | LayerSet, condition: Callable[[ArtLayer], bool]
) -> ArtLayer | None:
    for layer in layer_sets.layers:
        if condition(layer):
            return layer
    for layer_set in layer_sets.layerSets:
        found = find_layer(layer_set, condition)
        if found:
            return found
    return None


def find_art_layers_and_their_preceding_layers_names(
    layer_sets: Document | LayerSet, condition: Callable[[ArtLayer], bool]
) -> list[tuple[ArtLayer, str | None]]:
    found: list[tuple[ArtLayer, str | None]] = []
    for art_layer in layer_sets.artLayers:
        if condition(art_layer):
            for index, layer in enumerate(layer_sets.layers):
                if layer.name == art_layer.name:
                    if index > 0:
                        found.append((art_layer, prev_layer.name))
                    else:
                        found.append((art_layer, None))
                if not condition(layer):
                    prev_layer = layer
    for layer_set in layer_sets.layerSets:
        found += find_art_layers_and_their_preceding_layers_names(layer_set, condition)
    return found


def copy_selection_channels(source: Document, target: Document):
    for channel in source.channels:
        if (
            channel.kind == ChannelType.MaskedAreaAlphaChannel
            or channel.kind == ChannelType.SelectedAreaAlphaChannel
        ) and channel.name != "fade effect":
            channel.duplicate(target)


def load_old_artwork(instance: BaseTemplate):
    template_doc = APP.activeDocument

    directory_path = "backup\\"
    initialfile = find_file_in_directory(
        directory_path,
        instance.layout.name,
    )
    filetypes: list[tuple[str, str | list[str] | tuple[str, ...]]] = [("PSD", ".psd")]
    if initialfile:
        filetypes.insert(
            0,
            (
                "Card",
                f"{instance.layout.name.strip().lower().replace(' ', '*')}*",
            ),
        )

    if file := open_ask_file_dialog(initialdir=directory_path, filetypes=filetypes):

        def is_art_layer(art_layer: ArtLayer):
            return bool(re.match(r"^(Generative )?Layer [0-9]+", art_layer.name))

        default_preceding_layer = template_doc.layers[-2]
        print(default_preceding_layer.name)

        if instance.art_layer.name != "Layer 1":
            CONSOLE.update(
                f"WARNING: The existing art layer isn't as expected. Found '{instance.art_layer.name}' instead of 'Layer 1'"
            )
        else:
            instance.art_layer.remove()

        backup_doc = APP.open(file)
        for (
            layer,
            preceding,
        ) in reversed(
            find_art_layers_and_their_preceding_layers_names(backup_doc, is_art_layer)
        ):
            preceding_layer = None
            if preceding:
                preceding_layer = find_layer(
                    template_doc, lambda art_layer: art_layer.name == preceding
                )
            if not preceding_layer:
                preceding_layer = default_preceding_layer
            CONSOLE.update(f"Copy layer '{layer.name}' after '{preceding_layer.name}'")
            layer.duplicate(default_preceding_layer, ElementPlacement.PlaceAfter)

        copy_selection_channels(backup_doc, template_doc)

        backup_doc.close()
        return True

    return False


def load_backup_artwork(obj: BaseTemplate) -> bool:
    old = False
    if CFG.get_setting(section="OTHER", key="Copy.Art", default=False, is_bool=True):
        old = load_old_artwork(obj)
    return old
