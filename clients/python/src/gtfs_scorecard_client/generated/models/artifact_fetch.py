from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.artifact_fetch_auth_kind import ArtifactFetchAuthKind
from ..models.artifact_fetch_reader_archive_profile import (
    ArtifactFetchReaderArchiveProfile,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="ArtifactFetch")


@_attrs_define
class ArtifactFetch:
    """
    Attributes:
        source (str):
        final_url (str):
        user_agent (str):
        max_attempts (int | Unset):
        origin_error (str | Unset):
        auth (Literal['env-ref'] | Unset): Present only when the feed URL required a credential (issue #371). The
            credential was supplied by reference from the pipeline's environment; the artifact never carries the credential
            or the name of the variable holding it.
        auth_kind (ArtifactFetchAuthKind | Unset): How the credential was presented: as a request header, a URL query
            parameter, or HTTP basic authentication.
        reader_archive_normalized (bool | Unset):
        reader_archive_profile (ArtifactFetchReaderArchiveProfile | Unset):
    """

    source: str
    final_url: str
    user_agent: str
    max_attempts: int | Unset = UNSET
    origin_error: str | Unset = UNSET
    auth: Literal["env-ref"] | Unset = UNSET
    auth_kind: ArtifactFetchAuthKind | Unset = UNSET
    reader_archive_normalized: bool | Unset = UNSET
    reader_archive_profile: ArtifactFetchReaderArchiveProfile | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        source = self.source

        final_url = self.final_url

        user_agent = self.user_agent

        max_attempts = self.max_attempts

        origin_error = self.origin_error

        auth = self.auth

        auth_kind: str | Unset = UNSET
        if not isinstance(self.auth_kind, Unset):
            auth_kind = self.auth_kind.value

        reader_archive_normalized = self.reader_archive_normalized

        reader_archive_profile: str | Unset = UNSET
        if not isinstance(self.reader_archive_profile, Unset):
            reader_archive_profile = self.reader_archive_profile.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "source": source,
                "final_url": final_url,
                "user_agent": user_agent,
            }
        )
        if max_attempts is not UNSET:
            field_dict["max_attempts"] = max_attempts
        if origin_error is not UNSET:
            field_dict["origin_error"] = origin_error
        if auth is not UNSET:
            field_dict["auth"] = auth
        if auth_kind is not UNSET:
            field_dict["auth_kind"] = auth_kind
        if reader_archive_normalized is not UNSET:
            field_dict["reader_archive_normalized"] = reader_archive_normalized
        if reader_archive_profile is not UNSET:
            field_dict["reader_archive_profile"] = reader_archive_profile

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        _d = dict(src_dict)
        source = _d.pop("source")

        final_url = _d.pop("final_url")

        user_agent = _d.pop("user_agent")

        max_attempts = _d.pop("max_attempts", UNSET)

        origin_error = _d.pop("origin_error", UNSET)

        auth = cast(Literal["env-ref"] | Unset, _d.pop("auth", UNSET))
        if auth != "env-ref" and not isinstance(auth, Unset):
            raise ValueError(f"auth must match const 'env-ref', got '{auth}'")

        _auth_kind = _d.pop("auth_kind", UNSET)
        auth_kind: ArtifactFetchAuthKind | Unset
        if isinstance(_auth_kind, Unset):
            auth_kind = UNSET
        else:
            auth_kind = ArtifactFetchAuthKind(_auth_kind)

        reader_archive_normalized = _d.pop("reader_archive_normalized", UNSET)

        _reader_archive_profile = _d.pop("reader_archive_profile", UNSET)
        reader_archive_profile: ArtifactFetchReaderArchiveProfile | Unset
        if isinstance(_reader_archive_profile, Unset):
            reader_archive_profile = UNSET
        else:
            reader_archive_profile = ArtifactFetchReaderArchiveProfile(
                _reader_archive_profile
            )

        artifact_fetch = cls(
            source=source,
            final_url=final_url,
            user_agent=user_agent,
            max_attempts=max_attempts,
            origin_error=origin_error,
            auth=auth,
            auth_kind=auth_kind,
            reader_archive_normalized=reader_archive_normalized,
            reader_archive_profile=reader_archive_profile,
        )

        return artifact_fetch
