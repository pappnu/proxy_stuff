from photoshop.api import ElementPlacement, RasterizeType
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src.helpers.bounds import (
    LayerDimensions,
    get_group_dimensions,
    get_layer_dimensions,
)

from ..helpers import rasterize_layer_style


def get_layer_dimensions_via_rasterization(
    layer: ArtLayer | LayerSet,
) -> LayerDimensions:
    if isinstance(layer, LayerSet):
        return get_group_dimensions(layer)

    layer_copy = layer.duplicate(layer, ElementPlacement.PlaceBefore)
    layer_copy.visible = True
    layer_copy.rasterize(RasterizeType.EntireLayer)
    rasterize_layer_style(layer_copy)
    dims = get_layer_dimensions(layer_copy)
    layer_copy.remove()
    return dims
