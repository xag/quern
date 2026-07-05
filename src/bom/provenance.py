"""The provenance atom: every number in the tree knows how much it can be trusted.

Unit-agnostic: `unit` is a field ("mm", "EUR", "%", "°", …), never part of a name.
The four provenance categories are epistemics, not domain semantics, and they are
the one fixed vocabulary of the substrate: measured, inferred, design-target,
derived. Domains map their own words onto them ("declared" is a design-target,
"from-feed" is a measurement whose source is the feed).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, model_validator


class Provenance(str, Enum):
    """How a value came to be — and therefore how far we can trust it."""

    MEASURED = "measured"          # an instrument said so; trustworthy within tolerance
    INFERRED = "inferred"          # estimated (photo, judgement); rough, design-only
    DESIGN_TARGET = "design-target"  # a value we chose, not yet a measured constraint
    DERIVED = "derived"            # computed by a solver from other values; only as
    #                                trustworthy as its inputs — never counts as measured


class Quantity(BaseModel):
    """A scalar carrying its unit and its provenance.

    `tolerance` (same unit as `value`) is the *known or required* tolerance: for a
    measured value, how tight the measurement is; for a fit-critical input, how
    tight it must be before we are willing to act on it.
    """

    value: float
    unit: str = "mm"
    provenance: Provenance
    tolerance: float | None = None
    source: str | None = None  # instrument | photo id | feed | how it was derived
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_tolerance_mm(cls, data: Any) -> Any:
        """Pre-unit-agnostic records spelled it `tolerance_mm`; keep them loading."""
        if isinstance(data, dict) and "tolerance_mm" in data:
            data = dict(data)
            tol = data.pop("tolerance_mm")
            data.setdefault("tolerance", tol)
            data.setdefault("unit", "mm")
        return data

    @property
    def tolerance_mm(self) -> float | None:
        """Legacy spelling, kept for callers that predate unit-agnosticism."""
        return self.tolerance

    @tolerance_mm.setter
    def tolerance_mm(self, value: float | None) -> None:
        self.tolerance = value

    @property
    def is_measured(self) -> bool:
        return self.provenance is Provenance.MEASURED

    def trusted_within(self, required_tolerance: float | None) -> bool:
        """True iff this value is measured and tight enough to act on."""
        if not self.is_measured:
            return False
        if required_tolerance is None:
            return True
        if self.tolerance is None:
            return False
        return self.tolerance <= required_tolerance


def measured(value: float, tolerance: float, source: str = "tape",
             unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.MEASURED,
                    tolerance=tolerance, source=source)


def inferred(value: float, source: str = "photo", unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.INFERRED,
                    source=source)


def design_target(value: float, unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.DESIGN_TARGET)
