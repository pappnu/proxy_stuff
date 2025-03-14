from functools import cached_property
import re
from photoshop.api import ActionDescriptor, ActionReference, DialogModes, SolidColor
from photoshop.api._artlayer import ArtLayer

from src._config import AppConfig
from src.console import TerminalConsole
from src.gui.console import GUIConsole
import src.helpers as psd
from src import APP
from src.helpers.colors import get_color, get_rgb_from_hex
from src.schema.colors import ColorObject

sID, cID = APP.stringIDToTypeID, APP.charIDToTypeID
NO_DIALOG = DialogModes.DisplayNoDialogs


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
