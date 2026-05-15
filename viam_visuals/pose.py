"""Pose — position + orientation vector + theta.

The Viam world-state-store wire format encodes each entity's pose as
``(x, y, z)`` in millimeters plus an orientation specified by an
orientation vector ``(ox, oy, oz)`` and a rotation ``theta`` (in
degrees) around that vector.

The :class:`Pose` dataclass is the typed surface for this. Identity
is ``OZ=1``, everything else zero — the entity's local +Z aligns
with world +Z. Use :meth:`Pose.at` for the common case of setting
position with the orientation defaulting to identity, or construct
fields explicitly when the orientation matters.

Position is in millimeters, in keeping with the rest of the Viam
convention (the renderer treats file coordinates as meters and
multiplies by 1000; this surface stays in mm so callers don't have
to remember the unit boundary).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union


__all__ = ["Pose", "PoseLike"]


@dataclass
class Pose:
    """Position + orientation in the parent frame.

    The orientation vector ``(ox, oy, oz)`` defaults to ``(0, 0, 1)``
    (identity — local +Z aligned with world +Z). ``theta`` is rotation
    around the orientation vector in degrees.
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    ox: float = 0.0
    oy: float = 0.0
    oz: float = 1.0
    theta: float = 0.0

    @classmethod
    def identity(cls) -> "Pose":
        """The identity pose: origin, OZ=1, theta=0."""
        return cls()

    @classmethod
    def at(
        cls,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        ox: float = 0.0,
        oy: float = 0.0,
        oz: float = 1.0,
        theta: float = 0.0,
    ) -> "Pose":
        """Build a pose with positional defaults — handy when only
        the position matters and orientation should stay identity.

        Example::

            Pose.at(x=500, y=-200, z=100)
        """
        return cls(x=x, y=y, z=z, ox=ox, oy=oy, oz=oz, theta=theta)

    def to_dict(self) -> Mapping[str, float]:
        """Serialize to the wire-format dict the service consumes."""
        return {
            "x": self.x, "y": self.y, "z": self.z,
            "ox": self.ox, "oy": self.oy, "oz": self.oz,
            "theta": self.theta,
        }


# Accepted by every Visual constructor: a Pose, a partial dict (missing
# keys filled with identity defaults), or None (→ identity).
PoseLike = Union[None, Pose, Mapping[str, float]]


def normalize_pose(p: PoseLike) -> Mapping[str, float]:
    """Coerce a PoseLike into the full dict the wire format expects.

    None → identity. Mapping → fill missing keys from identity. Pose
    → to_dict(). Anything else raises ``TypeError``.
    """
    if p is None:
        return Pose.identity().to_dict()
    if isinstance(p, Pose):
        return p.to_dict()
    if isinstance(p, Mapping):
        out = dict(Pose.identity().to_dict())
        out.update({k: float(v) for k, v in p.items()})
        return out
    raise TypeError(f"pose must be None | Pose | dict; got {type(p).__name__}")
