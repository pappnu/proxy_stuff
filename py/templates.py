from pathlib import Path

from photoshop.api._artlayer import ArtLayer

from src.utils.adobe import ReferenceLayer

from .borderless_saga import BorderlessSaga
from .borderless_showcase import BorderlessShowcase
from .planeswalker import PlaneswalkerBorderlessVector
from .restore import load_backup_artwork


class PlaneswalkerBorderlessTemplate(PlaneswalkerBorderlessVector):
    template_suffix = "Planeswalker Borderless"

    def load_artwork(
        self,
        art_file: str | Path | None = None,
        art_layer: ArtLayer | None = None,
        art_reference: ReferenceLayer | None = None,
    ) -> None:
        if not load_backup_artwork(self):
            super().load_artwork(art_file, art_layer, art_reference)


class BorderlessShowcaseTemplate(BorderlessShowcase):
    template_suffix = "Borderless Showcase"

    def load_artwork(
        self,
        art_file: str | Path | None = None,
        art_layer: ArtLayer | None = None,
        art_reference: ReferenceLayer | None = None,
    ) -> None:
        if not load_backup_artwork(self):
            return super().load_artwork(art_file, art_layer, art_reference)


class BorderlessSagaTemplate(BorderlessSaga):
    template_suffix = "Borderless"

    def load_artwork(
        self,
        art_file: str | Path | None = None,
        art_layer: ArtLayer | None = None,
        art_reference: ReferenceLayer | None = None,
    ) -> None:
        if not load_backup_artwork(self):
            return super().load_artwork(art_file, art_layer, art_reference)
