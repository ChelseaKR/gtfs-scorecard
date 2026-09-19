from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.artifact_agency import ArtifactAgency
    from ..models.artifact_autofix import ArtifactAutofix
    from ..models.artifact_categories import ArtifactCategories
    from ..models.artifact_confidence import ArtifactConfidence
    from ..models.artifact_conformance import ArtifactConformance
    from ..models.artifact_export_diff import ArtifactExportDiff
    from ..models.artifact_feed import ArtifactFeed
    from ..models.artifact_ferry_profile import ArtifactFerryProfile
    from ..models.artifact_fetch import ArtifactFetch
    from ..models.artifact_finding import ArtifactFinding
    from ..models.artifact_geo import ArtifactGeo
    from ..models.artifact_mode_profile import ArtifactModeProfile
    from ..models.artifact_ntd_id_alignment import ArtifactNtdIdAlignment
    from ..models.artifact_ntd_readiness import ArtifactNtdReadiness
    from ..models.artifact_overall import ArtifactOverall
    from ..models.artifact_recompute import ArtifactRecompute
    from ..models.artifact_routability import ArtifactRoutability
    from ..models.artifact_route_map import ArtifactRouteMap
    from ..models.artifact_scoring_profile import ArtifactScoringProfile
    from ..models.artifact_shapes_readiness import ArtifactShapesReadiness


T = TypeVar("T", bound="Artifact")


@_attrs_define
class Artifact:
    """One agency's complete scored result for one snapshot (latest.json and <date>.json). The core contract is
    publish.build_artifact; the optional blocks are attached by the collect run. The top level is closed: adding a key
    requires updating this schema, which is the enforcement point.

        Attributes:
            schema_version (str):
            rubric_version (str):
            validator_version (None | str): MobilityData gtfs-validator release that produced the correctness notices; null
                when correctness was not measured.
            agency (ArtifactAgency):
            generated_at (str): ISO 8601 timestamp derived from the snapshot date, so re-running a day is byte-identical.
            snapshot_date (str):
            feed (ArtifactFeed):
            overall (ArtifactOverall):
            categories (ArtifactCategories):
            top_fixes (list[ArtifactFinding]):
            scoring_profile (ArtifactScoringProfile | Unset): Identity and provenance of the scoring contract that produced
                the unchanged score fields. This is not a jurisdiction overlay or compliance determination.
            fetch (ArtifactFetch | Unset):
            confidence (ArtifactConfidence | Unset): Measurement-confidence read (EXP-01): how much of this grade the
                pipeline could measure this run and from what source. A legibility layer on the one grade, never a second grade;
                absent on artifacts published before schema 1.5.
            recommendations (list[Any] | Unset): Beyond-the-grade opportunities (Fares v2, Flex, accessibility); zero-
                deduction.
            conformance (ArtifactConformance | Unset): Conformance-mark credential over the scores (conformance.assess). The
                independent version changes when derived machine-readable guidance must be refreshed.
            geo (ArtifactGeo | Unset): Median stop point + bbox for the national map; absent when the feed has no located
                stops.
            route_map (ArtifactRouteMap | Unset): Compact route/stop geometry summary; the drawable GeoJSON lives in
                geometry.geojson.
            mode_profile (ArtifactModeProfile | Unset): Descriptive, ungraded service modes derived from routes.txt and
                weighted by trips.txt.
            ferry_profile (ArtifactFerryProfile | Unset): Descriptive, ungraded capability measurements for the ferry routes
                and trips in a feed. Fare and realtime facts are explicitly whole-feed scope.
            routability (ArtifactRoutability | Unset): Zero-deduction routing usability checks (single-stop trips, orphan
                stops).
            export_diff (ArtifactExportDiff | Unset): What changed in the feed content since the previous export (EXP-18);
                present only on the run that first scored a changed export with structural differences.
            ntd_id_alignment (ArtifactNtdIdAlignment | Unset): RY2026 agency_id presence plus optional equality comparison
                with the NTD ID; US agencies only (ADR 0016/0026).
            ntd_readiness (ArtifactNtdReadiness | Unset): NTD certification readiness (published / valid / current /
                agency_id present); US agencies only.
            shapes_readiness (ArtifactShapesReadiness | Unset): shapes.txt trip coverage for FTA's July 2025 NTD shapes
                requirement (Full Reporters RY2025; Reduced, Rural, and Tribal Reporters RY2026); present only where the check
                ran.
            autofix (ArtifactAutofix | Unset): Corrected-feed offer: what the safe deterministic fixes changed, and where
                the patched zip lives.
            recompute (ArtifactRecompute | Unset): Freshness-sweep provenance: when and why the artifact was reswept without
                a refetch.
    """

    schema_version: str
    rubric_version: str
    validator_version: None | str
    agency: ArtifactAgency
    generated_at: str
    snapshot_date: str
    feed: ArtifactFeed
    overall: ArtifactOverall
    categories: ArtifactCategories
    top_fixes: list[ArtifactFinding]
    scoring_profile: ArtifactScoringProfile | Unset = UNSET
    fetch: ArtifactFetch | Unset = UNSET
    confidence: ArtifactConfidence | Unset = UNSET
    recommendations: list[Any] | Unset = UNSET
    conformance: ArtifactConformance | Unset = UNSET
    geo: ArtifactGeo | Unset = UNSET
    route_map: ArtifactRouteMap | Unset = UNSET
    mode_profile: ArtifactModeProfile | Unset = UNSET
    ferry_profile: ArtifactFerryProfile | Unset = UNSET
    routability: ArtifactRoutability | Unset = UNSET
    export_diff: ArtifactExportDiff | Unset = UNSET
    ntd_id_alignment: ArtifactNtdIdAlignment | Unset = UNSET
    ntd_readiness: ArtifactNtdReadiness | Unset = UNSET
    shapes_readiness: ArtifactShapesReadiness | Unset = UNSET
    autofix: ArtifactAutofix | Unset = UNSET
    recompute: ArtifactRecompute | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        rubric_version = self.rubric_version

        validator_version: None | str
        validator_version = self.validator_version

        agency = self.agency.to_dict()

        generated_at = self.generated_at

        snapshot_date = self.snapshot_date

        feed = self.feed.to_dict()

        overall = self.overall.to_dict()

        categories = self.categories.to_dict()

        top_fixes = []
        for top_fixes_item_data in self.top_fixes:
            top_fixes_item = top_fixes_item_data.to_dict()
            top_fixes.append(top_fixes_item)

        scoring_profile: dict[str, Any] | Unset = UNSET
        if not isinstance(self.scoring_profile, Unset):
            scoring_profile = self.scoring_profile.to_dict()

        fetch: dict[str, Any] | Unset = UNSET
        if not isinstance(self.fetch, Unset):
            fetch = self.fetch.to_dict()

        confidence: dict[str, Any] | Unset = UNSET
        if not isinstance(self.confidence, Unset):
            confidence = self.confidence.to_dict()

        recommendations: list[Any] | Unset = UNSET
        if not isinstance(self.recommendations, Unset):
            recommendations = self.recommendations

        conformance: dict[str, Any] | Unset = UNSET
        if not isinstance(self.conformance, Unset):
            conformance = self.conformance.to_dict()

        geo: dict[str, Any] | Unset = UNSET
        if not isinstance(self.geo, Unset):
            geo = self.geo.to_dict()

        route_map: dict[str, Any] | Unset = UNSET
        if not isinstance(self.route_map, Unset):
            route_map = self.route_map.to_dict()

        mode_profile: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mode_profile, Unset):
            mode_profile = self.mode_profile.to_dict()

        ferry_profile: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ferry_profile, Unset):
            ferry_profile = self.ferry_profile.to_dict()

        routability: dict[str, Any] | Unset = UNSET
        if not isinstance(self.routability, Unset):
            routability = self.routability.to_dict()

        export_diff: dict[str, Any] | Unset = UNSET
        if not isinstance(self.export_diff, Unset):
            export_diff = self.export_diff.to_dict()

        ntd_id_alignment: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ntd_id_alignment, Unset):
            ntd_id_alignment = self.ntd_id_alignment.to_dict()

        ntd_readiness: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ntd_readiness, Unset):
            ntd_readiness = self.ntd_readiness.to_dict()

        shapes_readiness: dict[str, Any] | Unset = UNSET
        if not isinstance(self.shapes_readiness, Unset):
            shapes_readiness = self.shapes_readiness.to_dict()

        autofix: dict[str, Any] | Unset = UNSET
        if not isinstance(self.autofix, Unset):
            autofix = self.autofix.to_dict()

        recompute: dict[str, Any] | Unset = UNSET
        if not isinstance(self.recompute, Unset):
            recompute = self.recompute.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "schema_version": schema_version,
                "rubric_version": rubric_version,
                "validator_version": validator_version,
                "agency": agency,
                "generated_at": generated_at,
                "snapshot_date": snapshot_date,
                "feed": feed,
                "overall": overall,
                "categories": categories,
                "top_fixes": top_fixes,
            }
        )
        if scoring_profile is not UNSET:
            field_dict["scoring_profile"] = scoring_profile
        if fetch is not UNSET:
            field_dict["fetch"] = fetch
        if confidence is not UNSET:
            field_dict["confidence"] = confidence
        if recommendations is not UNSET:
            field_dict["recommendations"] = recommendations
        if conformance is not UNSET:
            field_dict["conformance"] = conformance
        if geo is not UNSET:
            field_dict["geo"] = geo
        if route_map is not UNSET:
            field_dict["route_map"] = route_map
        if mode_profile is not UNSET:
            field_dict["mode_profile"] = mode_profile
        if ferry_profile is not UNSET:
            field_dict["ferry_profile"] = ferry_profile
        if routability is not UNSET:
            field_dict["routability"] = routability
        if export_diff is not UNSET:
            field_dict["export_diff"] = export_diff
        if ntd_id_alignment is not UNSET:
            field_dict["ntd_id_alignment"] = ntd_id_alignment
        if ntd_readiness is not UNSET:
            field_dict["ntd_readiness"] = ntd_readiness
        if shapes_readiness is not UNSET:
            field_dict["shapes_readiness"] = shapes_readiness
        if autofix is not UNSET:
            field_dict["autofix"] = autofix
        if recompute is not UNSET:
            field_dict["recompute"] = recompute

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.artifact_agency import ArtifactAgency
        from ..models.artifact_autofix import ArtifactAutofix
        from ..models.artifact_categories import ArtifactCategories
        from ..models.artifact_confidence import ArtifactConfidence
        from ..models.artifact_conformance import ArtifactConformance
        from ..models.artifact_export_diff import ArtifactExportDiff
        from ..models.artifact_feed import ArtifactFeed
        from ..models.artifact_ferry_profile import (
            ArtifactFerryProfile,
        )
        from ..models.artifact_fetch import ArtifactFetch
        from ..models.artifact_finding import ArtifactFinding
        from ..models.artifact_geo import ArtifactGeo
        from ..models.artifact_mode_profile import ArtifactModeProfile
        from ..models.artifact_ntd_id_alignment import (
            ArtifactNtdIdAlignment,
        )
        from ..models.artifact_ntd_readiness import (
            ArtifactNtdReadiness,
        )
        from ..models.artifact_overall import ArtifactOverall
        from ..models.artifact_recompute import ArtifactRecompute
        from ..models.artifact_routability import ArtifactRoutability
        from ..models.artifact_route_map import ArtifactRouteMap
        from ..models.artifact_scoring_profile import (
            ArtifactScoringProfile,
        )
        from ..models.artifact_shapes_readiness import (
            ArtifactShapesReadiness,
        )

        _d = dict(src_dict)
        schema_version = _d.pop("schema_version")

        rubric_version = _d.pop("rubric_version")

        def _parse_validator_version(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        validator_version = _parse_validator_version(_d.pop("validator_version"))

        agency = ArtifactAgency.from_dict(_d.pop("agency"))

        generated_at = _d.pop("generated_at")

        snapshot_date = _d.pop("snapshot_date")

        feed = ArtifactFeed.from_dict(_d.pop("feed"))

        overall = ArtifactOverall.from_dict(_d.pop("overall"))

        categories = ArtifactCategories.from_dict(_d.pop("categories"))

        top_fixes = []
        _top_fixes = _d.pop("top_fixes")
        for top_fixes_item_data in _top_fixes:
            top_fixes_item = ArtifactFinding.from_dict(top_fixes_item_data)

            top_fixes.append(top_fixes_item)

        _scoring_profile = _d.pop("scoring_profile", UNSET)
        scoring_profile: ArtifactScoringProfile | Unset
        if isinstance(_scoring_profile, Unset):
            scoring_profile = UNSET
        else:
            scoring_profile = ArtifactScoringProfile.from_dict(_scoring_profile)

        _fetch = _d.pop("fetch", UNSET)
        fetch: ArtifactFetch | Unset
        if isinstance(_fetch, Unset):
            fetch = UNSET
        else:
            fetch = ArtifactFetch.from_dict(_fetch)

        _confidence = _d.pop("confidence", UNSET)
        confidence: ArtifactConfidence | Unset
        if isinstance(_confidence, Unset):
            confidence = UNSET
        else:
            confidence = ArtifactConfidence.from_dict(_confidence)

        recommendations = cast(list[Any], _d.pop("recommendations", UNSET))

        _conformance = _d.pop("conformance", UNSET)
        conformance: ArtifactConformance | Unset
        if isinstance(_conformance, Unset):
            conformance = UNSET
        else:
            conformance = ArtifactConformance.from_dict(_conformance)

        _geo = _d.pop("geo", UNSET)
        geo: ArtifactGeo | Unset
        if isinstance(_geo, Unset):
            geo = UNSET
        else:
            geo = ArtifactGeo.from_dict(_geo)

        _route_map = _d.pop("route_map", UNSET)
        route_map: ArtifactRouteMap | Unset
        if isinstance(_route_map, Unset):
            route_map = UNSET
        else:
            route_map = ArtifactRouteMap.from_dict(_route_map)

        _mode_profile = _d.pop("mode_profile", UNSET)
        mode_profile: ArtifactModeProfile | Unset
        if isinstance(_mode_profile, Unset):
            mode_profile = UNSET
        else:
            mode_profile = ArtifactModeProfile.from_dict(_mode_profile)

        _ferry_profile = _d.pop("ferry_profile", UNSET)
        ferry_profile: ArtifactFerryProfile | Unset
        if isinstance(_ferry_profile, Unset):
            ferry_profile = UNSET
        else:
            ferry_profile = ArtifactFerryProfile.from_dict(_ferry_profile)

        _routability = _d.pop("routability", UNSET)
        routability: ArtifactRoutability | Unset
        if isinstance(_routability, Unset):
            routability = UNSET
        else:
            routability = ArtifactRoutability.from_dict(_routability)

        _export_diff = _d.pop("export_diff", UNSET)
        export_diff: ArtifactExportDiff | Unset
        if isinstance(_export_diff, Unset):
            export_diff = UNSET
        else:
            export_diff = ArtifactExportDiff.from_dict(_export_diff)

        _ntd_id_alignment = _d.pop("ntd_id_alignment", UNSET)
        ntd_id_alignment: ArtifactNtdIdAlignment | Unset
        if isinstance(_ntd_id_alignment, Unset):
            ntd_id_alignment = UNSET
        else:
            ntd_id_alignment = ArtifactNtdIdAlignment.from_dict(_ntd_id_alignment)

        _ntd_readiness = _d.pop("ntd_readiness", UNSET)
        ntd_readiness: ArtifactNtdReadiness | Unset
        if isinstance(_ntd_readiness, Unset):
            ntd_readiness = UNSET
        else:
            ntd_readiness = ArtifactNtdReadiness.from_dict(_ntd_readiness)

        _shapes_readiness = _d.pop("shapes_readiness", UNSET)
        shapes_readiness: ArtifactShapesReadiness | Unset
        if isinstance(_shapes_readiness, Unset):
            shapes_readiness = UNSET
        else:
            shapes_readiness = ArtifactShapesReadiness.from_dict(_shapes_readiness)

        _autofix = _d.pop("autofix", UNSET)
        autofix: ArtifactAutofix | Unset
        if isinstance(_autofix, Unset):
            autofix = UNSET
        else:
            autofix = ArtifactAutofix.from_dict(_autofix)

        _recompute = _d.pop("recompute", UNSET)
        recompute: ArtifactRecompute | Unset
        if isinstance(_recompute, Unset):
            recompute = UNSET
        else:
            recompute = ArtifactRecompute.from_dict(_recompute)

        artifact = cls(
            schema_version=schema_version,
            rubric_version=rubric_version,
            validator_version=validator_version,
            agency=agency,
            generated_at=generated_at,
            snapshot_date=snapshot_date,
            feed=feed,
            overall=overall,
            categories=categories,
            top_fixes=top_fixes,
            scoring_profile=scoring_profile,
            fetch=fetch,
            confidence=confidence,
            recommendations=recommendations,
            conformance=conformance,
            geo=geo,
            route_map=route_map,
            mode_profile=mode_profile,
            ferry_profile=ferry_profile,
            routability=routability,
            export_diff=export_diff,
            ntd_id_alignment=ntd_id_alignment,
            ntd_readiness=ntd_readiness,
            shapes_readiness=shapes_readiness,
            autofix=autofix,
            recompute=recompute,
        )

        return artifact
