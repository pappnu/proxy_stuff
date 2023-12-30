from photoshop.api import ActionDescriptor, ActionReference, DialogModes
from photoshop.api._artlayer import ArtLayer

import src.helpers as psd
from src import APP

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID
NO_DIALOG = DialogModes.DisplayNoDialogs


def copy():
    """Same as pressing Ctrl-C in Photoshop."""
    APP.executeAction(cID("copy"), None, NO_DIALOG)


def paste():
    """Same as pressing Ctrl-V in Photoshop."""
    APP.executeAction(cID("past"), None, NO_DIALOG)


def subtract_front_shape(shape_1: ArtLayer, shape_2: ArtLayer) -> ArtLayer:
    """
    Subtracts the front shape from the bottom shape. The layers are merged together in the process.
    The merged shape will have the name of the front shape.

    Returns:
        The merged layer.
    """
    psd.select_layers([shape_1, shape_2])

    desc = ActionDescriptor()
    desc.putEnumerated(sID("shapeOperation"), sID("shapeOperation"), cID("Sbtr"))
    APP.executeAction(cID("Mrg2"), desc, NO_DIALOG)

    return APP.activeDocument.activeLayer


def select_path_component_select_tool():
    """
    Selects the path component selection tool in Photoshop.
    """
    desc = ActionDescriptor()
    ref = ActionReference()
    ref.putClass(sID("pathComponentSelectTool"))
    desc.putReference(cID("null"), ref)
    desc.putBoolean(sID("dontRecord"), True)
    APP.executeAction(cID("slct"), desc, NO_DIALOG)


def create_vector_mask_from_shape(layer: ArtLayer, shape: ArtLayer):
    """
    Adds the given shape as a vector mask to layer.
    WARNING:
    The layer has to be visible or else the shape is duplicated instead of being placed as a mask.

    Returns:
        The layer that the mask was applied to.
    """
    psd.select_layer(shape)
    select_path_component_select_tool()
    copy()
    psd.select_layer(layer)
    paste()
    return layer
