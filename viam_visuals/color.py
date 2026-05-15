"""Color — RGB color helpers.

The wire format encodes color as ``{"r": int, "g": int, "b": int}``
with each channel in ``[0, 255]``. This module accepts the common
input shapes — dict, ``(r, g, b)`` tuple, or ``None`` — and
normalizes them so the rest of the library only ever sees the dict.

Future versions can grow named-color tables, hex parsing, and HSV
conversion here without affecting the wire format.
"""

from __future__ import annotations

from typing import Mapping, Optional, Tuple, Union


__all__ = ["ColorLike", "normalize_color"]


ColorLike = Union[None, Mapping[str, int], Tuple[int, int, int]]


def normalize_color(c: ColorLike) -> Optional[Mapping[str, int]]:
    """Coerce a ColorLike into the wire-format dict.

    Accepts:
      * ``None`` → returns ``None`` (no color override)
      * ``{"r": int, "g": int, "b": int}`` → returned as-is (channel-typed)
      * ``(r, g, b)`` tuple or list → converted to dict

    Raises ``TypeError`` for anything else. Channel values are coerced
    to int but not range-clamped; callers responsible for staying in
    ``[0, 255]``.
    """
    if c is None:
        return None
    if isinstance(c, Mapping):
        return {"r": int(c["r"]), "g": int(c["g"]), "b": int(c["b"])}
    if isinstance(c, (tuple, list)) and len(c) == 3:
        return {"r": int(c[0]), "g": int(c[1]), "b": int(c[2])}
    raise TypeError(
        f"color must be None | dict | (r,g,b) tuple/list; got {type(c).__name__}"
    )
