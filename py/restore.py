import os
import re
from collections.abc import Callable
from logging import getLogger
from re import Pattern

from photoshop.api._artlayer import ArtLayer
from photoshop.api._document import Document
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ChannelType, ElementPlacement

from src._state import PATH
from src.gui.qml.models.file_dialog_model import FileMode
from src.templates import BaseTemplate
from src.utils.asynchronic import async_to_sync

_logger = getLogger()


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
    for layer in layer_sets.artLayers:
        if condition(layer):
            return layer
    for layer_set in layer_sets.layerSets:
        found = find_layer(layer_set, condition)
        if found:
            return found
    return None


def find_art_layers_and_their_preceding_layers_names(
    layer_sets: Document | LayerSet, condition: Callable[[ArtLayer | LayerSet], bool]
) -> list[tuple[ArtLayer, str | None]]:
    found: list[tuple[ArtLayer, str | None]] = []
    for art_layer in layer_sets.artLayers:
        if condition(art_layer):
            prev_layer: ArtLayer | LayerSet | None = None
            for layer in layer_sets.layers:
                if layer.name == art_layer.name:
                    found.append((art_layer, prev_layer.name if prev_layer else None))
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
    template_doc = instance.app.activeDocument

    directory_path = PATH.CWD / "backup"
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

    if instance.file_dialog and (
        file := async_to_sync(
            instance.file_dialog.select_files(
                title="Select backup",
                initial_dir=directory_path,
                file_mode=FileMode.OpenFile,
                # Suggest backups with same card name by default
                filters=[
                    *(
                        (
                            f"Card ({instance.layout.name.strip().lower().replace(' ', '*')}*.psd)",
                        )
                        if initialfile
                        else tuple()
                    ),
                    instance.file_dialog.PSD_FILTER,
                    instance.file_dialog.ALL_FILTER,
                ],
                dialog_id="backup_document_selector",
            )
        )
    ):

        def is_art_layer(art_layer: ArtLayer | LayerSet):
            return bool(re.match(r"^(Generative )?Layer [0-9]+", art_layer.name))

        default_preceding_layer = template_doc.layers[-2]

        if instance.art_layer and instance.art_layer.name != "Layer 1":
            _logger.warning(
                f"The existing art layer isn't as expected. Found '{instance.art_layer.name}' instead of 'Layer 1'"
            )
        elif instance.art_layer:
            instance.art_layer.remove()

        backup_doc = instance.app.open(file[0].toLocalFile())
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
            _logger.info(f"Copying layer '{layer.name}' after '{preceding_layer.name}'")
            layer.duplicate(default_preceding_layer, ElementPlacement.PlaceAfter)

        copy_selection_channels(backup_doc, template_doc)

        backup_doc.close()
        return True

    return False


def load_backup_artwork(obj: BaseTemplate) -> bool:
    old = False
    if obj.config.get_setting(
        section="OTHER", key="Copy.Art", default=False, is_bool=True
    ):
        old = load_old_artwork(obj)
    return old
