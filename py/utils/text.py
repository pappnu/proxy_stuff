from enum import Enum, StrEnum
from typing import Literal

from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from photoshop.api._artlayer import ArtLayer
from photoshop.api._layerSet import LayerSet

from src.utils.adobe import LayerDimensions, ReferenceLayer
from src.utils.fonts import FONT_CACHE

from .layer import get_layer_dimensions_via_rasterization


class Language(Enum):
    JAPANESE = 1
    KOREAN = 2
    CHINESE = 3
    CJK = 4


class ExtraPostScriptFontName(StrEnum):
    ARTIST_JP = "NotoSansJP-SemiBold"
    ARTIST_KO = "NotoSansKR-SemiBold"
    ARTIST_CN = "NotoSansSC-SemiBold"


class ExtraFontFileName(StrEnum):
    NOTO_JP = "NotoSansJP"
    NOTO_KO = "NotoSansKO"
    NOTO_SC = "NotoSansSC"


LANGUAGE_TO_FONT: dict[Language, ExtraPostScriptFontName] = {
    Language.JAPANESE: ExtraPostScriptFontName.ARTIST_JP,
    Language.KOREAN: ExtraPostScriptFontName.ARTIST_KO,
    Language.CHINESE: ExtraPostScriptFontName.ARTIST_CN,
}

FONT_TO_FILE: dict[ExtraPostScriptFontName, ExtraFontFileName] = {
    ExtraPostScriptFontName.ARTIST_JP: ExtraFontFileName.NOTO_JP,
    ExtraPostScriptFontName.ARTIST_KO: ExtraFontFileName.NOTO_KO,
    ExtraPostScriptFontName.ARTIST_CN: ExtraFontFileName.NOTO_SC,
}


class _FontDataCache:
    _font_objs: dict[ExtraPostScriptFontName, TTFont] = {}

    def get_font_obj(self, font: ExtraPostScriptFontName) -> TTFont | None:
        if obj := self._font_objs.get(font):
            return obj

        font_filename_prefix = FONT_TO_FILE[font]
        for font_path in FONT_CACHE.user_font_files:
            if font_path.name.startswith(font_filename_prefix):
                obj = TTFont(font_path)
                self._font_objs[font] = obj
                return obj


_font_data_cache = _FontDataCache()


def is_code_point_in_font(code_point: int, font: TTFont) -> bool:
    for cmap_table in font["cmap"].tables:  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        if cmap_table.isUnicode() and code_point in cmap_table.cmap:  # pyright: ignore[reportUnknownMemberType]
            return True
    return False


def _guess_cjk_language_of_char(code_point: int) -> Language | None:
    """Tries to determine the CJK language, if any, of the given character.

    - Japanese detection is based on the presence of *Hiragana* or *Katakana*.
    - Korean detection looks for Hangul symbols.
    - Chinese is assumed based on CJK Unified Ideographs Extensions G and J
    - Japanese is used as a fallback for all other CJK ideographs and radicals

    Returns `None` when the string contains no identifiable CJK characters."""
    # Code point ranges are based on Unicode 17.0
    # Hiragana, katakana, full-width roman characters and half-width katakana (Japanese)
    if 0x3040 <= code_point <= 0x309F or 0x30A0 <= code_point <= 0x30FF:
        return Language.JAPANESE
    # Hangul ranges (Korean)
    if (
        0x1100 <= code_point <= 0x11FF
        or 0xA960 <= code_point <= 0xA97F
        or 0xD7B0 <= code_point <= 0xD7FF
        or 0x3130 <= code_point <= 0x318F
        or 0xFF00 <= code_point <= 0xFFEF
        or 0xAC00 <= code_point <= 0xD7AF
    ):
        return Language.KOREAN
    # Chinese exclusive ranges (CJK Unified Ideographs Extensions G and J)?
    if 0x30000 <= code_point <= 0x3134A or 0x323B0 <= code_point <= 0x33479:
        return Language.CHINESE
    # CJK Unified Ideographs and Radicals
    if (
        0x4E00 <= code_point <= 0x9FFF
        or 0x3400 <= code_point <= 0x4DBF
        or 0x20000 <= code_point <= 0x2A6DF
        or 0x2A700 <= code_point <= 0x2B73F
        or 0x2B740 <= code_point <= 0x2B81D
        or 0x2B820 <= code_point <= 0x2CEAD
        or 0x2CEB0 <= code_point <= 0x2EBE0
        or 0x31350 <= code_point <= 0x323AF
        or 0x2EBF0 <= code_point <= 0x2EE5D
        or 0xF900 <= code_point <= 0xFAFF
        or 0x2F800 <= code_point <= 0x2FA1F
        or 0x2F00 <= code_point <= 0x2FDF
        or 0x2E80 <= code_point <= 0x2EFF
        or 0x31C0 <= code_point <= 0x31EF
        or 0x2FF0 <= code_point <= 0x2FFF
    ):
        return Language.CJK
    return None


def guess_cjk_language(text: str) -> Language | None:
    """Tries to determine the CJK language, if any, of the given text."""
    lang: Language | None = None
    for ch in text:
        code_point = ord(ch)
        result = _guess_cjk_language_of_char(code_point)

        if not result:
            continue

        lang = result

        if not (font_obj := _font_data_cache.get_font_obj(ExtraPostScriptFontName.ARTIST_JP)):
            return

        if lang == Language.CJK and not is_code_point_in_font(code_point, font_obj):
            # Assume Chinese if the code point is not present in the Japanese font
            return Language.CHINESE
        else:
            # Assume Japanese if uncertain
            lang = Language.JAPANESE

    return lang


def find_cjk_sequences(text: str) -> list[tuple[int, int]]:
    """Locate all continuous runs of CJK characters.

    The return value is a list of `(start, end)` index tuples, where
    `start` is inclusive and `end` is exclusive.

    Examples:
        ```
        find_cjk_sequences("helloこんにちはworld한글!")
        # [(5, 10), (15, 17)]
        ```
    """
    sequences: list[tuple[int, int]] = []
    current_start: int | None = None

    for idx, ch in enumerate(text):
        if _guess_cjk_language_of_char(ord(ch)) is not None:
            if current_start is None:
                current_start = idx
        else:
            if current_start is not None:
                sequences.append((current_start, idx))
                current_start = None

    # If string ended while we were in a sequence, close it.
    if current_start is not None:
        sequences.append((current_start, len(text)))

    return sequences


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
        layer_dimensions = get_layer_dimensions_via_rasterization(layer)

    if isinstance(reference_dimensions, ReferenceLayer):
        reference_dimensions = reference_dimensions.dims
    elif isinstance(reference_dimensions, ArtLayer | LayerSet):
        reference_dimensions = get_layer_dimensions_via_rasterization(
            reference_dimensions
        )

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
