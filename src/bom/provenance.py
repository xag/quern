"""The provenance atom: every number in the tree knows how much it can be trusted.

Unit-agnostic: `unit` is a field ("mm", "EUR", "%", "°", …), never part of a name.

Provenance is a *label a domain names* — "measured", "from-feed", "self-reported",
"preprint", "clinician-confirmed" — so it is **data**, a free string, not a fixed
vocabulary the substrate imposes. What the core fixes is not the label but the one
*verb a consumer branches on*: `grounded` — is this value an observation we may act
on, or is it provisional (a guess, a target, a derivation only as good as its
inputs)? A domain maps its own words onto that single predicate. `Provenance` below
survives only as a set of conventional label constants; nothing in the core is a
closed enum over it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Provenance(str, Enum):
    """Conventional provenance labels — a convenience, **not** a closed set. A
    `Quantity.provenance` is a free string; these are the words the substrate's own
    helpers use, and the ones whose grounding the core knows by default."""

    MEASURED = "measured"          # an instrument said so; grounded, act within tolerance
    INFERRED = "inferred"          # estimated (photo, judgement); provisional, design-only
    DESIGN_TARGET = "design-target"  # a value we chose, not yet a measured constraint
    DERIVED = "derived"            # computed by a solver; only as trustworthy as its inputs


# The one label whose grounding the core assumes by default. Every other label is
# provisional unless the caller says otherwise via `grounded=True`. This is the
# whole of the substrate's fixed opinion about epistemics: one predicate, not four
# nouns.
_GROUNDED_BY_DEFAULT = frozenset({Provenance.MEASURED.value})


class Quantity(BaseModel):
    """A scalar carrying its unit, its provenance label, and its grounding.

    `grounded` is the fixed predicate the substrate reasons with: True iff this is
    an observation trustworthy enough to act on (within `tolerance`). The
    `provenance` label is free data — a domain names its own epistemics — and only
    *seeds* `grounded` when the caller does not state it. `tolerance` (same unit as
    `value`) is the known-or-required tolerance: for a grounded value, how tight the
    observation is; for a fit-critical input, how tight it must be before we act.
    `derived_from` is machine-usable lineage — the refs this value was computed from
    ("path" or "path/param") — so a later change can find and invalidate it.
    """

    value: float
    unit: str = "mm"
    provenance: str = Provenance.MEASURED.value  # free label — DATA, the domain names it
    grounded: bool = True     # the fixed verb: an observation we may act on
    tolerance: float | None = None
    source: str | None = None  # instrument | photo id | feed | how it was derived
    derived_from: list[str] = Field(default_factory=list)  # lineage refs, traversable
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        """Fold legacy spellings and seed `grounded` from the label when unstated:
        `tolerance_mm` → `tolerance`+`unit`; an omitted `grounded` defaults to whether
        the provenance label is one the core grounds by default (`measured`)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "tolerance_mm" in data:
            tol = data.pop("tolerance_mm")
            data.setdefault("tolerance", tol)
            data.setdefault("unit", "mm")
        if "grounded" not in data:
            label = data.get("provenance", Provenance.MEASURED.value)
            data["grounded"] = label in _GROUNDED_BY_DEFAULT
        return data

    @property
    def tolerance_mm(self) -> float | None:
        """Legacy spelling, kept for callers that predate unit-agnosticism."""
        return self.tolerance

    @tolerance_mm.setter
    def tolerance_mm(self, value: float | None) -> None:
        self.tolerance = value

    @property
    def is_grounded(self) -> bool:
        return self.grounded

    @property
    def is_measured(self) -> bool:
        """Deprecated alias for `is_grounded`. The core no longer privileges the
        *word* "measured" — it privileges the grounding predicate. Kept so callers
        that predate the split keep working; for legacy stores the two coincide."""
        return self.grounded

    def trusted_within(self, required_tolerance: float | None) -> bool:
        """True iff this value is grounded and tight enough to act on."""
        if not self.grounded:
            return False
        if required_tolerance is None:
            return True
        if self.tolerance is None:
            return False
        return self.tolerance <= required_tolerance


def measured(value: float, tolerance: float, source: str = "tape",
             unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.MEASURED.value,
                    grounded=True, tolerance=tolerance, source=source)


def inferred(value: float, source: str = "photo", unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.INFERRED.value,
                    grounded=False, source=source)


def design_target(value: float, unit: str = "mm") -> Quantity:
    return Quantity(value=value, unit=unit, provenance=Provenance.DESIGN_TARGET.value,
                    grounded=False)


def derived(value: float, source: str, derived_from: list[str] | None = None,
            unit: str = "mm") -> Quantity:
    """A value a solver computed: never grounded (only as good as its inputs), and
    carrying its lineage so a change upstream can find and invalidate it."""
    return Quantity(value=value, unit=unit, provenance=Provenance.DERIVED.value,
                    grounded=False, source=source,
                    derived_from=list(derived_from or []))
