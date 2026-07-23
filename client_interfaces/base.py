"""
Defines the contract the rest of the app codes against.

Method names/shapes are deliberately modeled on real OSDU service
calls so that writing a RealOSDUClient later is a matter of
implementing this interface against actual HTTP endpoints, not
restructuring the app:

  - search_wells()        ~ OSDU Search Service  (POST /search/v2/query)
  - get_wellbores_for_well() ~ OSDU Search Service, kind=Wellbore filtered by well id
  - get_well_log()         ~ OSDU Wellbore DDMS   (GET /welllogs/{id})
                             + Storage Service for the actual curve data records

A real client would also need to handle:
  - OAuth2 bearer token acquisition/refresh (entitlements)
  - data-partition-id header (OSDU is multi-tenant per partition)
  - pagination on search results
  - ACL / legal-tag checks (you only see data you're entitled to)

None of that applies to the mock, but it's worth knowing it's there
when discussing security/IP considerations.
"""

from abc import ABC, abstractmethod
from typing import Optional
from models.osdu_models import Well, Wellbore, WellLog


class OSDUClient(ABC):

    @abstractmethod
    def search_wells(self, field_name: Optional[str] = None) -> list:
        """Return list[Well], optionally filtered by field name."""
        ...

    @abstractmethod
    def get_wellbores_for_well(self, well_id: str) -> list:
        """Return list[Wellbore] belonging to a given well."""
        ...

    @abstractmethod
    def get_well_log(self, wellbore_id: str) -> Optional[WellLog]:
        """Return the composite WellLog for a wellbore, or None."""
        ...
