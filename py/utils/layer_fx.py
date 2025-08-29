from typing import TypedDict

from photoshop.api import ActionDescriptor, ActionReference
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src import APP


class StrokeDetails(TypedDict):
    size: int


def get_stroke_details(layer: ArtLayer | LayerSet) -> StrokeDetails | None:
    APP.instance.activeDocument.activeLayer = layer

    ref = ActionReference()
    ref.putEnumerated(
        APP.instance.cID("Lyr "), APP.instance.cID("Ordn"), APP.instance.cID("Trgt")
    )
    desc: ActionDescriptor = APP.instance.executeActionGet(ref)

    layer_effects_id = APP.instance.sID("layerEffects")
    if not desc.hasKey(layer_effects_id):
        return

    layer_effects: ActionDescriptor = desc.getObjectValue(layer_effects_id)

    frame_fx_id = APP.instance.sID("frameFX")
    if not layer_effects.hasKey(frame_fx_id):
        return

    frame_fx: ActionDescriptor = layer_effects.getObjectValue(frame_fx_id)

    return {"size": frame_fx.getInteger(APP.instance.sID("size"))}
