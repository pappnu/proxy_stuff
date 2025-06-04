from typing import Any, Iterable

from photoshop.api import ActionDescriptor, ActionReference, DialogModes
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import APP
from src.helpers.bounds import LayerBounds, LayerDimensions, get_dimensions_from_bounds
from src.helpers.colors import get_color, rgb_black
from src.helpers.layers import select_layer, select_layers
from src.schema.colors import ColorObject

from ..uxp.path import PathPointConf, create_path

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID


def get_layer_path(layer: ArtLayer) -> tuple[Any, bool]:
    visible_state = bool(layer.visible)
    # The path can't be accessed if it's not visible and selected
    select_layer(layer, make_visible=True)

    layer_path: Any = None
    fallback: Any = None
    paths: Iterable[Any] = APP.activeDocument.pathItems
    for path in paths:
        if (
            path.name == f"{layer.name} Shape Path"
            or path.name == f"{layer.name} Type Path"
        ):
            layer_path = path
            break
        fallback = path

    # Seems that the paths are somewhat cached(?), so if a path earlier in the list is
    # same as a path later in the list they get same values even though Photoshop GUI
    # shows different values. The path we want seems to be usually the last one, so
    # this isn't that big of a problem hopefully.
    if not layer_path:
        print(
            f"Warning: Path selection failed for '{layer.name}'. Defaulting to the last path."
        )
        if not fallback:
            raise ValueError("No paths found")
        layer_path = fallback
    return layer_path, visible_state


def get_bounds_from_shape(layer: ArtLayer) -> LayerBounds:
    layer_path, visible_state = get_layer_path(layer)

    x_points: list[int] = []
    y_points: list[int] = []
    for sub_path in layer_path.subPathItems:
        for point in sub_path.pathPoints:
            x_points.append(point.anchor[0])
            y_points.append(point.anchor[1])
    layer.visible = visible_state
    return (min(*x_points), min(*y_points), max(*x_points), max(*y_points))


def get_shape_dimensions(layer: ArtLayer) -> LayerDimensions:
    """
    Layer.bounds can return incorrect bounds under unknown conditions
    when used with path layers and path points can give coordinates that are off by 1px,
    so here's a workaround that creates a selection from the shape and uses the selection's
    bounds to calculate the dimensions."""
    layer_path, visible_state = get_layer_path(layer)
    layer_path.makeSelection()
    doc = APP.activeDocument
    dims = get_dimensions_from_bounds(doc.selection.bounds)
    doc.selection.deselect()
    layer.visible = visible_state
    return dims


def create_shape_layer(
    points: Iterable[PathPointConf],
    name: str = "",
    relative_layer: ArtLayer | LayerSet | None = None,
    placement: ElementPlacement = ElementPlacement.PlaceAfter,
    hide: bool = False,
    color: ColorObject | None = None,
) -> ArtLayer:
    solid_color = get_color(color) if color else rgb_black()
    docref = APP.activeDocument

    create_path(points)

    # Convert path to a layer
    ref1 = ActionReference()
    desc1 = ActionDescriptor()
    desc2 = ActionDescriptor()
    desc3 = ActionDescriptor()
    desc4 = ActionDescriptor()
    ref1.putClass(sID("contentLayer"))
    desc1.putReference(sID("target"), ref1)
    desc4.putDouble(sID("red"), solid_color.rgb.red)
    desc4.putDouble(sID("green"), solid_color.rgb.green)
    desc4.putDouble(sID("blue"), solid_color.rgb.blue)
    desc3.putObject(sID("color"), sID("RGBColor"), desc4)
    desc2.putObject(sID("type"), sID("solidColorLayer"), desc3)
    desc1.putObject(sID("using"), sID("contentLayer"), desc2)
    APP.executeAction(sID("make"), desc1, DialogModes.DisplayNoDialogs)

    layer: ArtLayer = docref.activeLayer
    if name:
        layer.name = name
    if hide:
        layer.visible = False
    if relative_layer:
        layer.move(relative_layer, placement)

    return layer


def subtract_front_shape(shape_1: ArtLayer, shape_2: ArtLayer) -> ArtLayer:
    """
    Subtracts the front shape from the bottom shape. The layers are merged together in the process.
    The merged shape will have the name of the front shape.

    Returns:
        The merged layer.
    """
    select_layers([shape_1, shape_2])

    desc = ActionDescriptor()
    desc.putEnumerated(sID("shapeOperation"), sID("shapeOperation"), cID("Sbtr"))
    APP.executeAction(cID("Mrg2"), desc, DialogModes.DisplayNoDialogs)

    return APP.activeDocument.activeLayer
