"""Deterministic, stable athlete identity assignment.

Rules (spec section 3):
  * Trim whitespace and collapse harmless internal whitespace differences.
  * Assign deterministic IDs and retain the original label.
  * Use the same mapping for both sheets.
  * Keep mappings stable across uploads (append-only when an existing map is fed
    back in).
  * NEVER fuzzy-match different labels into one athlete.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional


def normalize_label(raw) -> Optional[str]:
    """Normalize a raw athlete label.

    Only *harmless* formatting is normalized: surrounding whitespace and
    runs of internal whitespace. Casing and spelling are preserved so two
    genuinely different labels are never silently merged.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    s = re.sub(r"\s+", " ", s)
    return s


class IdentityMap:
    """Bidirectional, deterministic athlete-id <-> label map.

    Without a seed map, IDs are assigned by sorted normalized label so the same
    input always yields the same IDs. With a seed map (e.g. persisted from a
    previous upload), existing assignments are preserved and genuinely new
    labels are appended with fresh IDs -- this is what keeps ids stable across
    re-uploads.
    """

    _PREFIX = "A"
    _WIDTH = 3

    def __init__(self, existing: Optional[Dict[str, str]] = None):
        # label (normalized) -> id
        self._label_to_id: Dict[str, str] = {}
        # id -> label
        self._id_to_label: Dict[str, str] = {}
        self._next = 1
        if existing:
            for label, aid in sorted(existing.items(), key=lambda kv: kv[1]):
                self._label_to_id[label] = aid
                self._id_to_label[aid] = label
                n = self._id_number(aid)
                if n is not None:
                    self._next = max(self._next, n + 1)

    @classmethod
    def _id_number(cls, aid: str) -> Optional[int]:
        m = re.fullmatch(rf"{cls._PREFIX}(\d+)", aid or "")
        return int(m.group(1)) if m else None

    def _mint(self) -> str:
        aid = f"{self._PREFIX}{self._next:0{self._WIDTH}d}"
        self._next += 1
        return aid

    def register_all(self, labels: Iterable[str]) -> None:
        """Register a batch of normalized labels, assigning IDs in sorted order.

        Labels already present keep their IDs; new ones are added in
        deterministic (sorted) order.
        """
        new_labels = sorted({l for l in labels if l and l not in self._label_to_id})
        for label in new_labels:
            aid = self._mint()
            self._label_to_id[label] = aid
            self._id_to_label[aid] = label

    def get(self, normalized_label: Optional[str]) -> Optional[str]:
        if normalized_label is None:
            return None
        return self._label_to_id.get(normalized_label)

    def label_for(self, aid: str) -> Optional[str]:
        return self._id_to_label.get(aid)

    def as_dict(self) -> Dict[str, str]:
        """Return label -> id (sorted by id) for persistence / export."""
        return {lbl: aid for lbl, aid in sorted(self._label_to_id.items(), key=lambda kv: kv[1])}

    def athletes(self) -> list:
        """Return [{athlete_id, athlete_label}] sorted by id."""
        return [
            {"athlete_id": aid, "athlete_label": lbl}
            for lbl, aid in sorted(self._label_to_id.items(), key=lambda kv: kv[1])
        ]
