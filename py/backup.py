from functools import cached_property
from pathlib import Path
from typing import Callable, Iterable

from photoshop.api._artlayer import ArtLayer
from photoshop.api._document import Document
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import APP, CFG
from src._state import PATH
from src.helpers.document import save_document_psd
from src.helpers.layers import getLayer
from src.helpers.masks import apply_mask_to_layer_fx, copy_layer_mask
from src.templates._core import BaseTemplate
from src.utils.adobe import ReferenceLayer

from .gui import ask_for_confirmation, open_ask_file_dialog
from .helpers import copy_layer, has_layer_mask
from .restore import find_file_in_directory


class BackupAndRestore(BaseTemplate):
    # region Settings

    @cached_property
    def save_backup(self) -> bool:
        return bool(CFG.get_setting(section="BACKUP", key="Save", default=False))

    @cached_property
    def load_backup(self) -> bool:
        return bool(CFG.get_setting(section="BACKUP", key="Load", default=False))

    @cached_property
    def backup_directory(self) -> Path:
        if (
            (
                setting := (
                    CFG.get_setting(
                        section="BACKUP", key="Directory", default=None, is_bool=False
                    )
                )
            )
            and setting
            and isinstance(setting, str)
        ):
            return Path(setting)
        return PATH.OUT / "backup"

    @cached_property
    def prompt_for_art_backup(self) -> bool:
        return bool(CFG.get_setting(section="BACKUP", key="Art.Prompt", default=True))

    # endregion Settings

    # region Backup Properties

    @cached_property
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
                default(path, docref=docref)

            return save
        return super().save_mode

    # endregion Execution

    # region Backup logic

    def make_backup(self) -> bool:
        if self.layers_to_seek_masks_from or self.layers_to_copy:
            template_doc = APP.activeDocument
            backup_doc = APP.documents.add(
                width=template_doc.width, height=template_doc.height
            )

            default_backup_doc_layer = backup_doc.artLayers[0]

            for layer in self.layers_to_copy:
                if layer:
                    if (
                        layer.name == self.art_layer.name
                        and self.prompt_for_art_backup
                        and not ask_for_confirmation(
                            "Backup art layer?",
                            "Do you want to copy the art layer to the backup?",
                        )
                    ):
                        continue
                    APP.activeDocument = template_doc
                    copy_layer(layer, relative_layer=default_backup_doc_layer)

            for layer in self.layers_to_seek_masks_from:
                APP.activeDocument = template_doc
                if layer and has_layer_mask(layer):
                    temp_layer = template_doc.artLayers.add()
                    temp_layer.name = layer.name
                    copy_layer_mask(layer, temp_layer)
                    bak_layer = copy_layer(
                        temp_layer, relative_layer=default_backup_doc_layer
                    )
                    temp_layer.remove()
                    # APP.activeDocument = backup_doc
                    # bak_layer.name = layer.name

            if len(backup_doc.layers) > 1:
                APP.activeDocument = backup_doc
                default_backup_doc_layer.isBackgroundLayer = False
                default_backup_doc_layer.remove()

                self.backup_directory.mkdir(exist_ok=True)
                save_document_psd(
                    self.backup_directory / self.output_file_name.name, backup_doc
                )

            backup_doc.close()
            APP.activeDocument = template_doc

            return True
        return False

    def restore_backup(self) -> bool:
        initialfile = find_file_in_directory(
            self.backup_directory,
            self.layout.name,
        )
        filetypes: list[tuple[str, str | list[str] | tuple[str, ...]]] = [
            ("PSD", ".psd")
        ]
        if initialfile:
            filetypes.insert(
                0,
                (
                    # Suggest backups with same card name by default
                    "Card",
                    f"{self.layout.name.strip().lower().replace(' ', '*')}*",
                ),
            )

        # Ask which backup to use
        if file := open_ask_file_dialog(
            initialdir=self.backup_directory,
            filetypes=filetypes,
        ):
            template_doc = APP.activeDocument
            backup_doc = APP.open(file)

            was_art_restored = False

            # Copy layers from backup
            for layer in self.layers_to_copy:
                if layer:
                    APP.activeDocument = backup_doc
                    if bak_layer := getLayer(layer.name):
                        layer_copy = copy_layer(
                            bak_layer,
                            relative_layer=layer,
                            insertion_location=ElementPlacement.PlaceBefore,
                        )
                        APP.activeDocument = template_doc
                        layer_copy.name = layer.name
                        was_art_restored = layer.name == self.art_layer.name
                        # Merge is used here to work around the fact that we can't just
                        # delete the old layer and copy a new one in its place
                        # because it might be cached in a property.
                        layer_copy.merge()

            # Copy masks from backup
            for layer in self.layers_to_seek_masks_from:
                if layer:
                    APP.activeDocument = backup_doc
                    if (bak_layer := getLayer(layer.name)) and has_layer_mask(
                        bak_layer
                    ):
                        temp_layer = copy_layer(bak_layer, relative_layer=layer)
                        APP.activeDocument = template_doc
                        copy_layer_mask(temp_layer, layer)
                        temp_layer.remove()
                        apply_mask_to_layer_fx(layer)

            backup_doc.close()
            APP.activeDocument = template_doc

            return was_art_restored
        return False

    # endregion Backup logic
