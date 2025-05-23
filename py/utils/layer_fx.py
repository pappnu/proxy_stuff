from typing import TypedDict

from photoshop.api import ActionDescriptor, ActionReference
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import APP

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID


class StrokeDetails(TypedDict):
    size: int


def get_stroke_details(layer: ArtLayer | LayerSet) -> StrokeDetails | None:
    APP.activeDocument.activeLayer = layer

    ref = ActionReference()
    ref.putEnumerated(cID("Lyr "), cID("Ordn"), cID("Trgt"))
    desc: ActionDescriptor = APP.executeActionGet(ref)

    layer_effects_id = sID("layerEffects")
    if not desc.hasKey(layer_effects_id):
        return

    layer_effects: ActionDescriptor = desc.getObjectValue(layer_effects_id)

    frame_fx_id = sID("frameFX")
    if not layer_effects.hasKey(frame_fx_id):
        return

    frame_fx: ActionDescriptor = layer_effects.getObjectValue(frame_fx_id)

    return {"size": frame_fx.getInteger(sID("size"))}
