from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="RollupReconciliation")


@_attrs_define
class RollupReconciliation:
    """How this program's feed records line up with an external agency directory published by a transport authority.
    Present only for programs with a mapped directory. Never a grade input.

        Attributes:
            directory_source (str):
            directory_month (str):
            directory_agencies (int):
            reconciled_records (int):
            matched_records (int):
            uncertain_records (int):
            absent_records (int):
            organizations_matched (int):
            directory_retrieved_on (str | Unset):
            unreconciled_records (int | Unset):
            directory_only_agencies (int | Unset):
    """

    directory_source: str
    directory_month: str
    directory_agencies: int
    reconciled_records: int
    matched_records: int
    uncertain_records: int
    absent_records: int
    organizations_matched: int
    directory_retrieved_on: str | Unset = UNSET
    unreconciled_records: int | Unset = UNSET
    directory_only_agencies: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        directory_source = self.directory_source

        directory_month = self.directory_month

        directory_agencies = self.directory_agencies

        reconciled_records = self.reconciled_records

        matched_records = self.matched_records

        uncertain_records = self.uncertain_records

        absent_records = self.absent_records

        organizations_matched = self.organizations_matched

        directory_retrieved_on = self.directory_retrieved_on

        unreconciled_records = self.unreconciled_records

        directory_only_agencies = self.directory_only_agencies

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "directory_source": directory_source,
                "directory_month": directory_month,
                "directory_agencies": directory_agencies,
                "reconciled_records": reconciled_records,
                "matched_records": matched_records,
                "uncertain_records": uncertain_records,
                "absent_records": absent_records,
                "organizations_matched": organizations_matched,
            }
        )
        if directory_retrieved_on is not UNSET:
            field_dict["directory_retrieved_on"] = directory_retrieved_on
        if unreconciled_records is not UNSET:
            field_dict["unreconciled_records"] = unreconciled_records
        if directory_only_agencies is not UNSET:
            field_dict["directory_only_agencies"] = directory_only_agencies

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        directory_source = _d.pop("directory_source")

        directory_month = _d.pop("directory_month")

        directory_agencies = _d.pop("directory_agencies")

        reconciled_records = _d.pop("reconciled_records")

        matched_records = _d.pop("matched_records")

        uncertain_records = _d.pop("uncertain_records")

        absent_records = _d.pop("absent_records")

        organizations_matched = _d.pop("organizations_matched")

        directory_retrieved_on = _d.pop("directory_retrieved_on", UNSET)

        unreconciled_records = _d.pop("unreconciled_records", UNSET)

        directory_only_agencies = _d.pop("directory_only_agencies", UNSET)

        rollup_reconciliation = cls(
            directory_source=directory_source,
            directory_month=directory_month,
            directory_agencies=directory_agencies,
            reconciled_records=reconciled_records,
            matched_records=matched_records,
            uncertain_records=uncertain_records,
            absent_records=absent_records,
            organizations_matched=organizations_matched,
            directory_retrieved_on=directory_retrieved_on,
            unreconciled_records=unreconciled_records,
            directory_only_agencies=directory_only_agencies,
        )

        return rollup_reconciliation
