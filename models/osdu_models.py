"""
Data models that mirror OSDU's record schema shape.

OSDU records always follow a common envelope:
  - id, kind, version, acl, legal, data {...}, meta [...]

We don't implement the full envelope (acl/legal/meta are about
entitlements and legal tags - important in real OSDU, irrelevant
to a mock), but we keep `data` shaped like the real
osdu:wks:master-data--Well, Wellbore, and WellLog schemas so the
UI and parsing code we write now will still work against a real
OSDU instance later with minimal changes.

Real-world reference kinds this approximates:
  - osdu:wks:master-data--Well:1.x
  - osdu:wks:master-data--Wellbore:1.x
  - osdu:wks:work-product-component--WellLog:1.x
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class Well:
    id: str                     # OSDU id, e.g. "osdu:master-data--Well:12345"
    name: str
    field_name: str
    operator: str
    country: str
    latitude: float
    longitude: float


@dataclass
class Wellbore:
    id: str
    well_id: str                # FK -> Well.id
    name: str
    wellbore_datum: str = "KB"   # Kelly Bushing, common reference datum
    total_depth_md: float = 0.0  # measured depth, meters


@dataclass
class LogCurve:
    """A single curve (e.g. GR, RHOB) within a WellLog."""
    mnemonic: str                # e.g. "GR", "RHOB", "NPHI", "RT"
    unit: str                    # e.g. "GAPI", "G/C3", "V/V", "OHMM"
    description: str
    depth: np.ndarray             # measured depth samples, meters
    values: np.ndarray            # curve values, same length as depth

    # Provenance. `mnemonic` above may have been renamed by an alias table
    # (LFP_GR -> GR), which is a domain guess the user should be able to
    # audit - so keep what the source file actually said.
    original_mnemonic: str = ""   # mnemonic exactly as written in the file
    source_info: str = ""         # raw ~Curve "value" field, if any


@dataclass
class WellLog:
    id: str
    wellbore_id: str             # FK -> Wellbore.id
    name: str
    top_depth: float
    bottom_depth: float
    curves: list = field(default_factory=list)   # list[LogCurve]
