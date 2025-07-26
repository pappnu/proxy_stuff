import re
from enum import Enum, StrEnum
from functools import cached_property
from typing import Callable, TypeVar

from photoshop.api import ActionDescriptor, ActionReference, DialogModes, SolidColor
from photoshop.api._artlayer import ArtLayer
from photoshop.api._document import Document
from photoshop.api._layerSet import LayerSet
from photoshop.api.enumerations import ElementPlacement

from src import APP
from src._config import AppConfig
from src.console import TerminalConsole
from src.gui.console import GUIConsole
from src.helpers.colors import get_color, get_rgb_from_hex
from src.helpers.layers import select_layer
from src.schema.colors import ColorObject

L = TypeVar("L", bound=ArtLayer | LayerSet)

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID
NO_DIALOG = DialogModes.DisplayNoDialogs


class LAYER_NAMES(StrEnum):
    ARROW = "Arrow"
    ABILITY_DIVIDERS = "Ability Dividers"
    BATTLE = "Battle"
    CARD_NAME = "Card Name"
    ICON = "Icon"
    SHADOW = "Shadow"
    PT_INNER = "PT Box Inner"
    PT_OUTER = "PT Box Outer"
    PW = "pw"
    PW3 = "pw-3"
    PW4 = "pw-4"
    VERTICAL = "Vertical"
    REFERENCE = "Reference"
    REFERENCES = "References"
    TEXT_REFERENCE = "Text Reference"
    TEXT_REFERENCE_CREATURE = "Text Reference - Creature"
    OVERFLOW_REFERENCE = "Overflow Reference"
    UNIFIED = "Unified"
    FUSE = "Fuse"
    PROTOTYPE = "Prototype"
    MANABOX = "Manabox"


class ExpansionSymbolOverrideMode(Enum):
    Off = 0
    Identity = 1
    Pinlines = 2
    Custom = 3


class _LazyValues:
    @cached_property
    def hex_color_regex(self):
        return re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")

    @cached_property
    def color_identity_regex(self):
        return re.compile(r"^[WUBRG]+$")


lazy_values = _LazyValues()


def is_hex_color(value: str) -> re.Match[str] | None:
    return lazy_values.hex_color_regex.match(value)


def parse_hex_color_list(
    value: str, console: GUIConsole | TerminalConsole
) -> list[SolidColor]:
    colors: list[SolidColor] = []
    parts = value.split(",")
    for part in parts:
        if is_hex_color(part):
            colors.append(get_rgb_from_hex(part))
        else:
            console.update(f"WARNING: Encountered non-hexadecimal color: {part}")
    return colors


def clamp(value: int | float, lower: int | float, upper: int | float):
    return lower if value < lower else upper if value > upper else value


def is_color_identity(identity: str):
    return lazy_values.color_identity_regex.match(identity)


def get_numeric_setting(
    cfg: AppConfig,
    section: str,
    key: str,
    default: float,
    min_max: tuple[int | float, int | float] | None = None,
) -> float:
    if (
        setting := cfg.get_setting(
            section=section,
            key=key,
            default=None,
            is_bool=False,
        )
    ) and isinstance(setting, str):
        try:
            value = float(setting)
            if min_max:
                return clamp(value, *min_max)
            else:
                return value
        except ValueError:
            pass
    return default


def copy_color(color: ColorObject):
    if isinstance(color, SolidColor):
        color_copy = SolidColor()
        color_copy.rgb.red = color.rgb.red
        color_copy.rgb.green = color.rgb.green
        color_copy.rgb.blue = color.rgb.blue
        return color_copy
    return get_color(color)


def find_art_layer(
    root: Document | LayerSet, condition: Callable[[ArtLayer], bool]
) -> ArtLayer | None:
    for layer in root.layers:
        if condition(layer):
            return layer
    for layer_set in root.layerSets:
        found = find_art_layer(layer_set, condition)
        if found:
            return found
    return None


def copy():
    """Same as pressing Ctrl-C in Photoshop."""
    APP.executeAction(cID("copy"), None, NO_DIALOG)


def paste():
    """Same as pressing Ctrl-V in Photoshop."""
    APP.executeAction(cID("past"), None, NO_DIALOG)


def delete():
    """Same as pressing Del in Photoshop."""
    APP.executeAction(cID("Dlt "), None, NO_DIALOG)


def create_art_layer(
    name: str | None = None,
    relative_layer: ArtLayer | LayerSet | None = None,
    insertion_location: ElementPlacement = ElementPlacement.PlaceBefore,
) -> ArtLayer:
    new_layer = APP.activeDocument.artLayers.add()
    if name is not None:
        new_layer.name = name
    if relative_layer:
        new_layer.move(relative_layer, insertion_location)
    return new_layer


def copy_layer(
    layer_to_copy: L,
    name: str | None = None,
    relative_layer: ArtLayer | LayerSet | Document | None = None,
    insertion_location: ElementPlacement = ElementPlacement.PlaceBefore,
) -> L:
    new_layer: L = layer_to_copy.duplicate(relative_layer, insertion_location)
    if name is not None:
        new_layer.name = name
    return new_layer


class FlipDirection(StrEnum):
    Horizontal = "Hrzn"
    Vertical = "Vrtc"


def flip_layer(layer: ArtLayer | LayerSet, direction: FlipDirection):
    layer.visible = True
    select_layer(layer)
    desc = ActionDescriptor()
    desc.putEnumerated(cID("Axis"), cID("Ornt"), cID(direction))
    APP.executeAction(cID("Flip"), desc, NO_DIALOG)


# https://community.adobe.com/t5/photoshop-ecosystem-discussions/check-if-layer-has-mask/m-p/3702981
def has_layer_mask(layer: ArtLayer | LayerSet) -> bool:
    ref = ActionReference()
    ref.putName(cID("Lyr "), layer.name)
    return APP.executeActionGet(ref).getBoolean(sID("hasUserMask"))


def create_clipping_mask(layer: ArtLayer):
    select_layer(layer)
    desc1 = ActionDescriptor()
    ref1 = ActionReference()
    ref1.putEnumerated(cID("Lyr "), cID("Ordn"), cID("Trgt"))
    desc1.putReference(cID("null"), ref1)
    APP.executeAction(sID("groupEvent"), desc1, NO_DIALOG)


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
    select_layer(shape)
    select_path_component_select_tool()
    copy()
    select_layer(layer)
    paste()
    return layer


def deselect_all_layers() -> None:
    desc = ActionDescriptor()
    ref = ActionReference()
    ref.putEnumerated(cID("Lyr "), cID("Ordn"), cID("Trgt"))
    desc.putReference(cID("null"), ref)
    APP.executeAction(sID("selectNoLayers"), desc, NO_DIALOG)


def rasterize_layer_style(layer: ArtLayer | LayerSet) -> None:
    select_layer(layer)
    idrasterizeLayer = sID("rasterizeLayer")
    desc = ActionDescriptor()
    ref = ActionReference()
    ref.putEnumerated(cID("Lyr "), cID("Ordn"), cID("Trgt"))
    desc.putReference(cID("null"), ref)
    desc.putEnumerated(cID("What"), sID("rasterizeItem"), sID("layerStyle"))
    APP.executeAction(idrasterizeLayer, desc, NO_DIALOG)
