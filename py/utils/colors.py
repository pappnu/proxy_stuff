from src.helpers.colors import get_pinline_gradient
from src.schema.colors import ColorObject, GradientConfig


def create_gradient_location_map(
    steps: int, start: float, end: float
) -> dict[int, list[int | float]]:
    """Creates evenly divided gradient location map.

    Args:
        steps: I.e. how many different colors
        start: Gradient start position on a scale of 0.0-1.0
        end: Gradient end position on a scale of 0.0-1.0
    """
    locations: list[int | float] = [start]
    steps_between = (steps - 2) * 2 + 1
    step = (end - start) / steps_between
    for i in range(steps_between - 1):
        locations.append(locations[i] + step)
    locations.append(end)
    return {steps: locations}


def create_gradient_config(
    colors: str, color_map: dict[str, ColorObject], start: float, end: float
) -> ColorObject | list[GradientConfig]:
    """Creates a gradient config.

    Args:
        colors: Colors in color identity notation, e.g., 'WU'
        color_map: Identity -> color mapping, e.g, 'W' -> SolidColor object representing white
        start: Gradient start position on a scale of 0.0-1.0
        end: Gradient end position on a scale of 0.0-1.0
    """
    location_map: dict[int, list[int | float]] | None = (
        create_gradient_location_map(steps, start, end)
        if (steps := len(colors)) > 1
        else None
    )
    return get_pinline_gradient(
        colors=colors, color_map=color_map, location_map=location_map
    )
