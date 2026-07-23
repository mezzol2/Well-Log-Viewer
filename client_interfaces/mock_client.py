"""
MockClient: serves the synthetic dataset from mock_data/generator.py
through the same interface a real OSDU-backed client would expose.

Swap point for later: implement RealClient(BaseClient) in this
same package, backed by `requests` calls to your OSDU instance's
Search / Storage / Wellbore DDMS endpoints, then change one line in
main.py to instantiate it instead of MockClient.
"""

from typing import Optional
from client_interfaces.base import BaseClient
from mock_data.generator import get_mock_wells


class MockClient(BaseClient):

    def __init__(self):
        self._wells, self._wellbores, self._logs_by_wellbore = get_mock_wells()

    def search_wells(self, field_name: Optional[str] = None) -> list:
        if field_name:
            return [w for w in self._wells if w.field_name == field_name]
        return list(self._wells)

    def get_wellbores_for_well(self, well_id: str) -> list:
        return [wb for wb in self._wellbores if wb.well_id == well_id]

    def get_well_log(self, wellbore_id: str):
        return self._logs_by_wellbore.get(wellbore_id)
