"""The provenance atom: every number in the tree knows how much it can be trusted."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Provenance(str, Enum):
    """How a value came to be — and therefore how far we can trust it."""

    MEASURED = "measured"          # tape / laser; trustworthy within tolerance
    INFERRED = "inferred"          # from a photo or estimate; rough, design-only
    DESIGN_TARGET = "design-target"  # a value we chose, not yet a measured constraint


class Quantity(BaseModel):
    """A scalar (mm, or degrees for angles) carrying its provenance.

    `tolerance_mm` is the *known or required* tolerance. For a measured value it is
    how tight the measurement is; for a fit-critical input it is how tight it must be
    before we are willing to cut.
    """

    value: float
    provenance: Provenance
    tolerance_mm: float | None = None
    source: str | None = None  # "tape" | "laser" | photo id | how it was derived
    note: str | None = None

    @property
    def is_measured(self) -> bool:
        return self.provenance is Provenance.MEASURED

    def trusted_within(self, required_tolerance_mm: float | None) -> bool:
        """True iff this value is measured and tight enough to build against."""
        if not self.is_measured:
            return False
        if required_tolerance_mm is None:
            return True
        if self.tolerance_mm is None:
            return False
        return self.tolerance_mm <= required_tolerance_mm


def measured(value: float, tolerance_mm: float, source: str = "tape") -> Quantity:
    return Quantity(value=value, provenance=Provenance.MEASURED,
                    tolerance_mm=tolerance_mm, source=source)


def inferred(value: float, source: str = "photo") -> Quantity:
    return Quantity(value=value, provenance=Provenance.INFERRED, source=source)


def design_target(value: float) -> Quantity:
    return Quantity(value=value, provenance=Provenance.DESIGN_TARGET)
