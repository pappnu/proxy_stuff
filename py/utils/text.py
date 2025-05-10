from typing import Literal

from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src.helpers.bounds import get_layer_dimensions
from src.utils.adobe import LayerDimensions, ReferenceLayer


def align_dimension(
    layer: ArtLayer | LayerSet,
    reference_dimensions: LayerDimensions | ArtLayer | LayerSet,
    alignment_dimension: Literal[
        "top", "bottom", "left", "right", "center_y", "center_x"
    ],
    layer_dimensions: LayerDimensions | None = None,
    offset: float | int = 0,
) -> None:
    """Aligns layers given dimension to the reference's equivalent one."""
    if isinstance(layer, ReferenceLayer):
        layer_dimensions = layer.dims

    if not layer_dimensions:
        layer_dimensions = get_layer_dimensions(layer)

    if isinstance(reference_dimensions, ReferenceLayer):
        reference_dimensions = reference_dimensions.dims
    elif isinstance(reference_dimensions, (ArtLayer, LayerSet)):
        reference_dimensions = get_layer_dimensions(reference_dimensions)

    delta = (
        reference_dimensions[alignment_dimension]
        - layer_dimensions[alignment_dimension]
    )

    if alignment_dimension in ("top", "bottom", "center_y"):
        # Vertical
        layer.translate(0, delta + offset)
    else:
        # Horizontal
        layer.translate(delta + offset, 0)
