from typing import Iterable

from photoshop.api import ElementPlacement, RasterizeType
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import APP
from src.helpers.adjustments import create_color_layer
from src.helpers.colors import rgb_white
from src.helpers.layers import merge_layers
from src.helpers.masks import create_mask, enter_mask_channel, enter_rgb_channel
from src.helpers.selection import select_canvas

from ..helpers import copy, paste


# TODO fix the original function in Proxyshop
def copy_to_mask(
    target: ArtLayer | LayerSet,
    source: ArtLayer | LayerSet | None = None,
):
    docref = APP.activeDocument
    if source:
        docref.activeLayer = source
    docsel = docref.selection
    select_canvas(docref)
    copy()
    docsel.deselect()

    docref.activeLayer = target
    create_mask()
    enter_mask_channel()
    # The pasting threw an error in the original function for some reason
    # even though the operation succeeded in Photoshop
    paste()
    enter_rgb_channel()


def create_mask_from(apply_to: Iterable[ArtLayer | LayerSet], layers: Iterable[ArtLayer]) -> None:
    background = create_color_layer(rgb_white(), clipped=False)
    layers_to_merge: list[ArtLayer] = [background]
    for layer in layers:
        duplicate = layer.duplicate(background, ElementPlacement.PlaceBefore)
        duplicate.visible = True
        layers_to_merge.append(duplicate)
    merged = merge_layers(layers_to_merge)
    merged.rasterize(RasterizeType.EntireLayer)
    for layer in apply_to:
        copy_to_mask(layer, merged)
    merged.remove()
