from _ctypes import COMError
from collections.abc import Callable, Iterable
from functools import cached_property
from logging import getLogger
from pathlib import Path

from photoshop.api._artlayer import ArtLayer
from photoshop.api._document import Document
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement, LayerKind, SaveOptions
from pydantic import BaseModel, ValidationError

from src._state import PATH
from src.gui.qml.models.file_dialog_model import FileMode
from src.helpers.document import save_document_psd
from src.helpers.layers import duplicate_layer, getLayer
from src.helpers.masks import apply_mask_to_layer_fx, copy_layer_mask
from src.templates._core import BaseTemplate
from src.utils.adobe import ReferenceLayer
from src.utils.asynchronic import async_to_sync
from src.utils.data_structures import find_item

from .helpers import copy_layer, has_layer_mask
from .restore import find_file_in_directory

_logger = getLogger(__name__)


class ExtraLayerConfig(BaseModel):
    name: str
    after_layer: str | None
    is_clipping: bool


_adjustment_layer_kinds = (
    LayerKind.BlackAndWhiteLayer,
    LayerKind.BrightnessContrastLayer,
    LayerKind.ChannelMixerLayer,
    LayerKind.ColorBalanceLayer,
    LayerKind.ColorLookup,
    LayerKind.CurvesLayer,
    LayerKind.ExposureLayer,
    LayerKind.HueSaturationLayer,
    LayerKind.InversionLayer,
    LayerKind.LevelsLayer,
    LayerKind.PhotoFilterLayer,
    LayerKind.PosterizeLayer,
    LayerKind.SelectiveColorLayer,
    LayerKind.ThresholdLayer,
    LayerKind.Vibrance,
)


def is_adjustment_layer(layer: ArtLayer):
    return layer.kind in _adjustment_layer_kinds


class BackupAndRestore(BaseTemplate):
    # region Settings

    @cached_property
    def save_backup(self) -> bool:
        return self.config.get_bool_setting(section="BACKUP", key="Save", default=False)

    @cached_property
    def load_backup(self) -> bool:
        return self.config.get_bool_setting(section="BACKUP", key="Load", default=False)

    @cached_property
    def backup_directory(self) -> Path:
        if (
            setting := (
                self.config.get_setting(section="BACKUP", key="Directory", default=None)
            )
        ) and setting:
            return Path(setting)
        return PATH.OUT / "backup"

    @cached_property
    def prompt_for_art_backup(self) -> bool:
        return self.config.get_bool_setting(
            section="BACKUP", key="Art.Prompt", default=True
        )

    @cached_property
    def backup_adjustment_layers(self) -> bool:
        return self.config.get_bool_setting(
            section="BACKUP", key="Backup.Adjustment.Layers", default=True
        )

    # endregion Settings

    # region Backup Properties

    # For some reason using a cached property here leads to an error in make_backup
    # if a backup is first loaded and then made anew
    @property
    def layers_to_seek_masks_from(self) -> Iterable[ArtLayer | LayerSet | None]:
        raise NotImplementedError

    # For some reason using a cached property here leads to an error in make_backup
    # if a backup is first loaded and then made anew
    @property
    def layers_to_copy(self) -> Iterable[ArtLayer | LayerSet | None]:
        return (self.art_layer,)

    # endregion Backup Properties

    # region Execution

    def load_artwork(
        self,
        art_file: str | Path | None = None,
        art_layer: ArtLayer | None = None,
        art_reference: ReferenceLayer | None = None,
    ) -> None:
        art_restored = False
        if self.load_backup:
            art_restored = self.restore_backup()
        if not art_restored:
            super().load_artwork(art_file, art_layer, art_reference)

    @cached_property
    def save_mode(self) -> Callable[[Path, Document | None], None]:
        if self.save_backup:
            default = super().save_mode

            def save(path: Path, docref: Document | None = None) -> None:
                self.make_backup()
                default(path, docref)

            return save
        return super().save_mode

    # endregion Execution

    # region Backup logic

    def make_backup(self) -> bool:
        if self.layers_to_seek_masks_from or self.layers_to_copy:
            template_doc = self.app.activeDocument
            try:
                backup_doc = self.app.documents.add(
                    width=template_doc.width, height=template_doc.height
                )

                default_backup_doc_layer = backup_doc.artLayers[0]
                backed_up_something = False

                art_layer = self.art_layer
                layers_to_copy = self.layers_to_copy
                for layer in layers_to_copy:
                    if layer:
                        if (
                            art_layer
                            and layer.name == art_layer.name
                            and self.prompt_for_art_backup
                            and self.message_dialog
                            and not async_to_sync(
                                self.message_dialog.open_message_dialog_async(
                                    title="Backup art layer?",
                                    text="Do you want to copy the art layer to the backup?",
                                )
                            )
                        ):
                            continue
                        self.app.activeDocument = template_doc
                        copy_layer(layer, relative_layer=default_backup_doc_layer)
                        backed_up_something = True

                layers_to_seek_masks_from = self.layers_to_seek_masks_from
                for layer in layers_to_seek_masks_from:
                    self.app.activeDocument = template_doc
                    if layer and has_layer_mask(layer):
                        temp_layer = template_doc.artLayers.add()
                        temp_layer.name = layer.name
                        copy_layer_mask(layer, temp_layer)
                        copy_layer(temp_layer, relative_layer=default_backup_doc_layer)
                        temp_layer.remove()
                        backed_up_something = True

                if self.backup_adjustment_layers:
                    prev: ArtLayer | LayerSet | None = None
                    for lyr in self.docref.layers:
                        if (
                            not isinstance(lyr, LayerSet)
                            and is_adjustment_layer(lyr)
                            and not find_item(
                                layers_to_copy,
                                lambda item: bool(item) and item.name == lyr.name,
                            )
                            and not find_item(
                                layers_to_seek_masks_from,
                                lambda item: bool(item) and item.name == lyr.name,
                            )
                        ):
                            conf = ExtraLayerConfig(
                                name=lyr.name,
                                after_layer=prev.name if prev else None,
                                is_clipping=lyr.grouped,
                            )
                            duplicate_layer(
                                lyr, name=conf.model_dump_json(), relative_to=backup_doc
                            )
                            backed_up_something = True
                        prev = lyr

                if backed_up_something:
                    self.app.activeDocument = backup_doc
                    default_backup_doc_layer.isBackgroundLayer = False
                    default_backup_doc_layer.remove()

                    self.backup_directory.mkdir(exist_ok=True)
                    save_document_psd(
                        self.backup_directory / self.output_file_name.name, backup_doc
                    )

                backup_doc.close(SaveOptions.DoNotSaveChanges)

                return True
            except Exception as exc:
                _logger.warning(
                    f"Failed to make a backup of <b>{self.layout.display_name}</b>",
                    exc_info=exc,
                )
            finally:
                self.app.activeDocument = template_doc
        return False

    def restore_backup(self) -> bool:
        initialfile = find_file_in_directory(
            self.backup_directory,
            self.layout.name,
        )

        # Ask which backup to use
        if self.file_dialog and (
            file := async_to_sync(
                self.file_dialog.select_files(
                    title="Select backup",
                    initial_dir=self.backup_directory,
                    file_mode=FileMode.OpenFile,
                    # Suggest backups with same card name by default
                    filters=[
                        *(
                            (
                                f"Card ({self.layout.name.strip().lower().replace(' ', '*')}*.psd)",
                            )
                            if initialfile
                            else tuple()
                        ),
                        self.file_dialog.PSD_FILTER,
                        self.file_dialog.ALL_FILTER,
                    ],
                    dialog_id="backup_document_selector",
                )
            )
        ):
            template_doc = self.app.activeDocument
            backup_doc = self.app.open(file[0].toLocalFile())

            was_art_restored = False

            # Copy layers from backup
            art_layer = self.art_layer
            art_layer_name = art_layer.name if art_layer else ""
            for layer in self.layers_to_copy:
                if layer:
                    self.app.activeDocument = backup_doc
                    if bak_layer := getLayer(layer.name):
                        layer_copy = copy_layer(
                            bak_layer,
                            relative_layer=layer,
                            insertion_location=ElementPlacement.PlaceBefore,
                        )
                        self.app.activeDocument = template_doc
                        layer_copy.name = layer.name
                        was_art_restored = layer.name == art_layer_name
                        # Merge is used here to work around the fact that we can't just
                        # delete the old layer and copy a new one in its place
                        # because it might be cached in a property.
                        layer_copy.merge()

            # Copy masks from backup
            for layer in self.layers_to_seek_masks_from:
                if layer:
                    self.app.activeDocument = backup_doc
                    if (bak_layer := getLayer(layer.name)) and has_layer_mask(
                        bak_layer
                    ):
                        temp_layer = copy_layer(bak_layer, relative_layer=layer)
                        self.app.activeDocument = template_doc
                        copy_layer_mask(temp_layer, layer)
                        temp_layer.remove()
                        try:
                            apply_mask_to_layer_fx(layer)
                        except COMError:
                            _logger.warning(
                                f"Couldn't apply backup mask to layer fx for: {layer.name}"
                            )

            template_doc_layers = [*template_doc.layers]
            for layer in backup_doc.artLayers:
                try:
                    conf = ExtraLayerConfig.model_validate_json(layer.name)
                    duplicate = duplicate_layer(
                        layer,
                        name=conf.name,
                        relative_to=find_item(
                            template_doc_layers,
                            lambda item: item.name == conf.after_layer,
                        )
                        if conf.after_layer
                        else None,
                        element_placement=ElementPlacement.PlaceAfter,
                    )
                    if conf.is_clipping:
                        self.app.activeDocument = template_doc
                        duplicate.grouped = True
                except ValidationError:
                    pass

            backup_doc.close()
            self.app.activeDocument = template_doc

            return was_art_restored
        return False

    # endregion Backup logic
