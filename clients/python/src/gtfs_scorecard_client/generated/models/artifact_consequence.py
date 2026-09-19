from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.artifact_consequence_need_type_0 import ArtifactConsequenceNeedType0
    from ..models.artifact_consequence_need_type_1 import ArtifactConsequenceNeedType1
    from ..models.artifact_consequence_reach_type_0 import ArtifactConsequenceReachType0
    from ..models.artifact_consequence_reach_type_1 import ArtifactConsequenceReachType1
    from ..models.artifact_consequence_ridership_type_0 import (
        ArtifactConsequenceRidershipType0,
    )
    from ..models.artifact_consequence_ridership_type_1 import (
        ArtifactConsequenceRidershipType1,
    )


T = TypeVar("T", bound="ArtifactConsequence")


@_attrs_define
class ArtifactConsequence:
    """Per-finding consequence block (consequence.py). Reach is computed from this artifact. Ridership and served-area need
    are properties of the feed and are null with a reason wherever the writer did not join them; not_joined_here means
    the step that wrote this record does not read that input, not that the data does not exist.

        Attributes:
            code (str):
            reach (ArtifactConsequenceReachType0 | ArtifactConsequenceReachType1): A share with an empty reason, or a null
                share with the reason it is not known. Never both. A finding with basis none has no share. Identifiers and
                labels that do not apply are null, never empty strings.
            ridership (ArtifactConsequenceRidershipType0 | ArtifactConsequenceRidershipType1): Annual rider-trips with an
                empty reason, or null with the reason they are not known. An absence is never published as zero.
            served_area_need (ArtifactConsequenceNeedType0 | ArtifactConsequenceNeedType1): A within-country need tier with
                the scale that produced it, or null with the reason it is not known. Tiers from different scales are not
                comparable.
            line (str):
            absences (list[str]):
    """

    code: str
    reach: ArtifactConsequenceReachType0 | ArtifactConsequenceReachType1
    ridership: ArtifactConsequenceRidershipType0 | ArtifactConsequenceRidershipType1
    served_area_need: ArtifactConsequenceNeedType0 | ArtifactConsequenceNeedType1
    line: str
    absences: list[str]

    def to_dict(self) -> dict[str, Any]:
        from ..models.artifact_consequence_need_type_0 import (
            ArtifactConsequenceNeedType0,
        )
        from ..models.artifact_consequence_reach_type_0 import (
            ArtifactConsequenceReachType0,
        )
        from ..models.artifact_consequence_ridership_type_0 import (
            ArtifactConsequenceRidershipType0,
        )

        code = self.code

        reach: dict[str, Any]
        if isinstance(self.reach, ArtifactConsequenceReachType0):
            reach = self.reach.to_dict()
        else:
            reach = self.reach.to_dict()

        ridership: dict[str, Any]
        if isinstance(self.ridership, ArtifactConsequenceRidershipType0):
            ridership = self.ridership.to_dict()
        else:
            ridership = self.ridership.to_dict()

        served_area_need: dict[str, Any]
        if isinstance(self.served_area_need, ArtifactConsequenceNeedType0):
            served_area_need = self.served_area_need.to_dict()
        else:
            served_area_need = self.served_area_need.to_dict()

        line = self.line

        absences = self.absences

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "reach": reach,
                "ridership": ridership,
                "served_area_need": served_area_need,
                "line": line,
                "absences": absences,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_consequence_need_type_0 import (
            ArtifactConsequenceNeedType0,
        )
        from ..models.artifact_consequence_need_type_1 import (
            ArtifactConsequenceNeedType1,
        )
        from ..models.artifact_consequence_reach_type_0 import (
            ArtifactConsequenceReachType0,
        )
        from ..models.artifact_consequence_reach_type_1 import (
            ArtifactConsequenceReachType1,
        )
        from ..models.artifact_consequence_ridership_type_0 import (
            ArtifactConsequenceRidershipType0,
        )
        from ..models.artifact_consequence_ridership_type_1 import (
            ArtifactConsequenceRidershipType1,
        )

        _d = dict(src_dict)
        code = _d.pop("code")

        def _parse_reach(
            data: object,
        ) -> ArtifactConsequenceReachType0 | ArtifactConsequenceReachType1:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_artifact_consequence_reach_type_0 = (
                    ArtifactConsequenceReachType0.from_dict(data)
                )

                return componentsschemas_artifact_consequence_reach_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            componentsschemas_artifact_consequence_reach_type_1 = (
                ArtifactConsequenceReachType1.from_dict(data)
            )

            return componentsschemas_artifact_consequence_reach_type_1

        reach = _parse_reach(_d.pop("reach"))

        def _parse_ridership(
            data: object,
        ) -> ArtifactConsequenceRidershipType0 | ArtifactConsequenceRidershipType1:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_artifact_consequence_ridership_type_0 = (
                    ArtifactConsequenceRidershipType0.from_dict(data)
                )

                return componentsschemas_artifact_consequence_ridership_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            componentsschemas_artifact_consequence_ridership_type_1 = (
                ArtifactConsequenceRidershipType1.from_dict(data)
            )

            return componentsschemas_artifact_consequence_ridership_type_1

        ridership = _parse_ridership(_d.pop("ridership"))

        def _parse_served_area_need(
            data: object,
        ) -> ArtifactConsequenceNeedType0 | ArtifactConsequenceNeedType1:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_artifact_consequence_need_type_0 = (
                    ArtifactConsequenceNeedType0.from_dict(data)
                )

                return componentsschemas_artifact_consequence_need_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            componentsschemas_artifact_consequence_need_type_1 = (
                ArtifactConsequenceNeedType1.from_dict(data)
            )

            return componentsschemas_artifact_consequence_need_type_1

        served_area_need = _parse_served_area_need(_d.pop("served_area_need"))

        line = _d.pop("line")

        absences = cast(list[str], _d.pop("absences"))

        artifact_consequence = cls(
            code=code,
            reach=reach,
            ridership=ridership,
            served_area_need=served_area_need,
            line=line,
            absences=absences,
        )

        return artifact_consequence
