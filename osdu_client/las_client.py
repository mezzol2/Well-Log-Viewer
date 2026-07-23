"""
LASFileClient: an OSDUClient implementation backed by a local folder
of LAS files (e.g. downloaded from the Volve open dataset, NLOG, or KGS).

Each LAS file becomes one Wellbore with one WellLog. Files whose WELL
headers normalize to the same name (e.g. "NO_15/9-19_A" and "15/9-19")
share a single Well, since real datasets spell the same well many ways.
Wells are grouped into a "field" using, in order of preference:
  1. the FLD (field) header mnemonic in the LAS file (any file's)
  2. the name of the top-level folder under the scan root
  3. "Unknown Field"

Curve handling:
  - All curves in the file are loaded (not just GR/RHOB/NPHI/RT), except
    the depth index itself.
  - Common mnemonic aliases are normalized so the viewer's display
    config applies (e.g. "GRC", "GR_EDTC" -> GR; "DEN", "RHOZ" -> RHOB).
  - Null values (typically -999.25) are converted to NaN by lasio and
    plotted as gaps.

This is real-world messiness that the mock client never had - LAS files
in the wild have inconsistent mnemonics, units, and missing headers.
The normalization here is deliberately conservative: it renames only
well-known aliases and leaves everything else untouched.
"""

import os
import re
from typing import Optional

import numpy as np
import lasio

from osdu_client.base import OSDUClient
from models.osdu_models import Well, Wellbore, WellLog, LogCurve


# Conservative alias map: variant mnemonic -> canonical mnemonic.
# Matching is done on the mnemonic with trailing numeric suffixes
# stripped (e.g. "GR:1" or "GR_1" -> "GR").
MNEMONIC_ALIASES = {
    "GR": "GR", "GRC": "GR", "SGR": "GR", "CGR": "GR", "GR_EDTC": "GR", "GAMM": "GR",
    "RHOB": "RHOB", "RHOZ": "RHOB", "DEN": "RHOB", "DENS": "RHOB", "ZDEN": "RHOB",
    "NPHI": "NPHI", "TNPH": "NPHI", "NPOR": "NPHI", "CNC": "NPHI", "NEU": "NPHI",
    "RT": "RT", "RDEP": "RT", "ILD": "RT", "LLD": "RT", "RLLD": "RT",
    "AT90": "RT", "RD": "RT", "HDRS": "RT",
}

# Preferred display order; canonical curves first, everything else after.
CANONICAL_ORDER = ["GR", "RHOB", "NPHI", "RT"]

# Norwegian offshore well naming: "NO 15/9-19 A" = quadrant/block 15/9,
# well 19, sidetrack (wellbore) A. LAS files in the wild write this many
# ways ("NO_15/9-19_A", "15/9-19"), and some name the wellbore while
# others name the parent well - so the same physical well shows up under
# several spellings. We normalize to (well, wellbore-suffix) so files
# group correctly. Handles slot names too ("15/9-F-11 B").
_WELL_NAME_RE = re.compile(
    r"^(?:NO\s+)?(?P<base>\d+/\d+(?:-[A-Z])?-\d+)(?:\s+(?P<bore>[A-Z]{1,2}\d{0,2}))?$"
)


def _parse_well_name(raw: str):
    """Return (well_base_name, wellbore_suffix_or_None) from a WELL header.

    Falls back to the cleaned-up string with no suffix when the name
    doesn't look like a Norwegian well - grouping then just requires an
    exact (case/space-insensitive) match, which is the safe default.
    """
    cleaned = re.sub(r"\s+", " ", raw.replace("_", " ").strip().upper())
    m = _WELL_NAME_RE.match(cleaned)
    if m:
        return m.group("base"), m.group("bore")
    return cleaned, None


def _normalize_mnemonic(raw: str) -> str:
    """Strip lasio's duplicate suffixes (GR:1) and common numeric
    suffixes, then map through the alias table if known.

    Also handles vendor/workflow prefixes like "LFP_" (seen in Volve
    petrophysics composites, where every curve is LFP_GR, LFP_RHOB, ...).
    The prefixed form is mapped only when the remainder is an exact
    alias-table hit, so LFP_GRMAX or LFP_RHOB_LOG stay untouched."""
    base = re.sub(r"[:_]\d+$", "", raw.strip().upper())
    if base in MNEMONIC_ALIASES:
        return MNEMONIC_ALIASES[base]
    if base.startswith("LFP_") and base[4:] in MNEMONIC_ALIASES:
        return MNEMONIC_ALIASES[base[4:]]
    return base


class LASFileClient(OSDUClient):

    def __init__(self, las_dir: str):
        self.las_dir = las_dir
        self._wells: list = []
        self._wellbores: list = []
        self._logs_by_wellbore: dict = {}
        self._load_errors: list = []   # (filename, error) - surfaced, not swallowed silently
        # Files describing the same physical well (under varying header
        # spellings) merge into one Well; key is the normalized name.
        self._well_by_name: dict = {}
        self._field_from_header: dict = {}   # well id -> bool
        self._scan()

    # ------------------------------------------------------------------
    # OSDUClient interface
    # ------------------------------------------------------------------

    def search_wells(self, field_name: Optional[str] = None) -> list:
        if field_name:
            return [w for w in self._wells if w.field_name == field_name]
        return list(self._wells)

    def get_wellbores_for_well(self, well_id: str) -> list:
        return [wb for wb in self._wellbores if wb.well_id == well_id]

    def get_well_log(self, wellbore_id: str):
        return self._logs_by_wellbore.get(wellbore_id)

    # ------------------------------------------------------------------
    # Extras (not part of the interface, but useful for the UI/status bar)
    # ------------------------------------------------------------------

    @property
    def load_errors(self) -> list:
        return list(self._load_errors)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self):
        if not os.path.isdir(self.las_dir):
            self._load_errors.append((self.las_dir, "directory does not exist"))
            return

        las_paths = []
        for root, _dirs, files in os.walk(self.las_dir):
            for fname in sorted(files):
                if fname.lower().endswith(".las"):
                    las_paths.append(os.path.join(root, fname))

        for i, path in enumerate(las_paths, start=1):
            try:
                self._load_one(path, index=i)
            except Exception as exc:  # a single bad file must not kill the app
                self._load_errors.append((os.path.basename(path), str(exc)))

    def _header_value(self, las, mnemonic: str, default: str = "") -> str:
        try:
            item = las.well[mnemonic]
            value = str(item.value).strip()
            return value if value else default
        except KeyError:
            return default

    def _load_one(self, path: str, index: int):
        # engine="normal": Volve-era files are frequently wrapped (WRAP. YES),
        # which the default fast numpy engine can't read - it would print a
        # fallback warning per file. Go straight to the engine that works.
        las = lasio.read(path, ignore_header_errors=True, engine="normal")

        fname = os.path.basename(path)
        raw_well = self._header_value(las, "WELL", default=os.path.splitext(fname)[0])
        well_name, bore_suffix = _parse_well_name(raw_well)

        field_name = self._header_value(las, "FLD")
        field_is_from_header = bool(field_name)
        if not field_name:
            # Fall back to the top-level folder under the scan root, not the
            # immediate parent: Volve wells unpack as <well>/<workflow>/file.las,
            # and the immediate parent is a workflow folder ("CPI", "06.LFP")
            # that makes a meaningless field name.
            rel = os.path.relpath(os.path.dirname(path), self.las_dir)
            top = rel.split(os.sep)[0]
            field_name = top if top not in (".", "") else "Unknown Field"

        operator = self._header_value(las, "COMP", default="Unknown Operator")
        country = self._header_value(las, "CTRY", default="")

        # Lat/lon are frequently absent or in odd formats in real LAS
        # files; default to 0.0 rather than failing.
        latitude = self._float_or(self._header_value(las, "LATI"), 0.0)
        longitude = self._float_or(self._header_value(las, "LONG"), 0.0)

        depth = np.asarray(las.index, dtype=float)
        if depth.size == 0:
            raise ValueError("no depth samples")

        curves = []
        for curve in las.curves:
            if curve.mnemonic == las.curves[0].mnemonic:
                continue  # skip the depth index curve itself
            values = np.asarray(curve.data, dtype=float)
            if values.shape != depth.shape:
                continue
            if np.all(np.isnan(values)):
                continue  # entirely-null curve, don't show an empty track
            curves.append(LogCurve(
                mnemonic=_normalize_mnemonic(curve.mnemonic),
                unit=(curve.unit or "").strip(),
                description=(curve.descr or "").strip(),
                depth=depth,
                values=values,
                original_mnemonic=curve.mnemonic.strip(),
                # In some vendor exports the human description is missing
                # (Volve's LFP file has descr="v1" throughout) and the only
                # provenance left is the ~Curve line's value field, e.g.
                # "UNKNOWN : LFP_GR:GeologLFP:rC:NONE".
                source_info=str(curve.value or "").strip(),
            ))

        if not curves:
            raise ValueError("no usable curves")

        # Canonical curves first, in standard order, then the rest.
        def sort_key(c):
            return (CANONICAL_ORDER.index(c.mnemonic) if c.mnemonic in CANONICAL_ORDER
                    else len(CANONICAL_ORDER))
        curves.sort(key=sort_key)

        # One Well per normalized name, shared by every file that names it
        # (directly or via a wellbore suffix). First file creates it; later
        # files upgrade placeholder metadata when they have real headers.
        well = self._well_by_name.get(well_name)
        if well is None:
            well = Well(
                id=f"las:well:{len(self._well_by_name) + 1:04d}",
                name=well_name, field_name=field_name,
                operator=operator, country=country,
                latitude=latitude, longitude=longitude,
            )
            self._well_by_name[well_name] = well
            self._wells.append(well)
            self._field_from_header[well.id] = field_is_from_header
        else:
            if field_is_from_header and not self._field_from_header[well.id]:
                well.field_name = field_name
                self._field_from_header[well.id] = True
            if well.operator == "Unknown Operator" and operator != "Unknown Operator":
                well.operator = operator
            if not well.country and country:
                well.country = country

        wellbore_id = f"las:wellbore:{index:04d}"
        bore_label = f"{well_name} {bore_suffix}" if bore_suffix else well_name
        self._wellbores.append(Wellbore(
            id=wellbore_id, well_id=well.id, name=f"{bore_label} ({fname})",
            wellbore_datum="KB", total_depth_md=float(np.nanmax(depth)),
        ))
        self._logs_by_wellbore[wellbore_id] = WellLog(
            id=f"las:welllog:{index:04d}",
            wellbore_id=wellbore_id,
            name=f"{well_name} - {fname}",
            top_depth=float(np.nanmin(depth)),
            bottom_depth=float(np.nanmax(depth)),
            curves=curves,
        )

    @staticmethod
    def _float_or(text: str, default: float) -> float:
        try:
            return float(text)
        except (TypeError, ValueError):
            return default
