#!/usr/bin/env python3
"""Run deterministic, network-free structural SEO checks on a rendered site."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

_CONFIG_KEYS = {
    "schema_version",
    "site_origin",
    "sitemap_path",
    "robots_path",
    "retained_redirects_path",
    "fragment_exempt_prefixes",
    "noindex_path_patterns",
    "canonical_aliases",
    "hreflang_groups",
    "required_json_ld_types",
    "redirect_aliases",
}
_IGNORED_SCHEMES = {"blob", "data", "javascript", "mailto", "sms", "tel"}
_OG_FIELDS = ("og:title", "og:description", "og:type", "og:url", "og:image")
_JSON_LD_DATE_KEYS = {
    "dateCreated",
    "dateDeleted",
    "dateModified",
    "datePosted",
    "datePublished",
    "endDate",
    "expires",
    "startDate",
    "uploadDate",
    "validFrom",
    "validThrough",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_REFRESH_RE = re.compile(r"^\s*0(?:\.0+)?\s*;\s*url\s*=\s*(.+?)\s*$", re.IGNORECASE)
# Mirrors scorecard_pipeline.agencies.ID_PATTERN at the public route boundary.
_AGENCY_PATH_RE = re.compile(r"^/agency/[a-z0-9][a-z0-9_-]*/$")
_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_FORBIDDEN_TELEMETRY_HOST_SUFFIXES = (
    "google-analytics.com",
    "googletagmanager.com",
)
_FORBIDDEN_TELEMETRY_MARKERS = _FORBIDDEN_TELEMETRY_HOST_SUFFIXES
_FORBIDDEN_TELEMETRY_FILES = {"analytics.js"}


class ConfigError(ValueError):
    """Raised when the SEO configuration is not the strict schema-v1 shape."""


@dataclass(frozen=True)
class Config:
    """Validated site-specific expectations."""

    site_origin: str
    sitemap_path: str
    robots_path: str
    retained_redirects_path: str
    fragment_exempt_prefixes: tuple[str, ...]
    noindex_path_patterns: tuple[str, ...]
    canonical_aliases: dict[str, str]
    hreflang_groups: tuple[dict[str, str], ...]
    required_json_ld_types: dict[str, tuple[str, ...]]
    redirect_aliases: dict[str, str]


@dataclass(frozen=True, order=True)
class Finding:
    """One stable report finding."""

    code: str
    path: str
    message: str


@dataclass(frozen=True)
class Reference:
    """A URL-bearing HTML attribute and its source line."""

    value: str
    line: int


@dataclass(frozen=True)
class Hreflang:
    """One HTML alternate-language declaration."""

    language: str
    href: str
    line: int


@dataclass(frozen=True)
class LocalTarget:
    """A same-site URL split into the parts relevant to structural checks."""

    scheme: str
    path: str
    query: str
    fragment: str


@dataclass
class Page:
    """All SEO-relevant facts collected during one HTML parse."""

    relative_path: str
    public_path: str
    language: str = ""
    titles: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    canonicals: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    robots: list[str] = field(default_factory=list)
    refreshes: list[Reference] = field(default_factory=list)
    links: list[Reference] = field(default_factory=list)
    assets: list[Reference] = field(default_factory=list)
    forms: list[Reference] = field(default_factory=list)
    hreflangs: list[Hreflang] = field(default_factory=list)
    json_ld: list[Reference] = field(default_factory=list)
    inline_scripts: list[Reference] = field(default_factory=list)
    misplaced_seo: list[Reference] = field(default_factory=list)
    og: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    ids: Counter[str] = field(default_factory=Counter)
    fragment_names: set[str] = field(default_factory=set)


class PageParser(HTMLParser):
    """Collect a page's structural facts without reparsing its HTML."""

    def __init__(self, relative_path: str, public_path: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page(relative_path=relative_path, public_path=public_path)
        self._title_parts: list[str] | None = None
        self._heading_parts: list[str] | None = None
        self._json_ld_parts: list[str] | None = None
        self._json_ld_line = 0
        self._inline_script_parts: list[str] | None = None
        self._inline_script_line = 0
        self._head_depth = 0
        self._head_seen = False
        self._body_seen = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = {key.casefold(): value or "" for key, value in attrs}
        line, _ = self.getpos()
        self._collect_common(tag, values)
        self._start_text_collection(tag, values, line)
        self._collect_element(tag, values, line)

    def _start_text_collection(self, tag: str, values: dict[str, str], line: int) -> None:
        if tag == "head":
            if not self._head_seen and not self._body_seen:
                self._head_seen = True
                self._head_depth = 1
        elif tag == "body":
            # HTML parsers implicitly close <head> when <body> starts, even if
            # the source omitted a literal </head>.
            self._body_seen = True
            self._head_depth = 0
        elif tag == "html" and not self.page.language:
            self.page.language = values.get("lang", "").strip()
        elif tag == "title" and self._head_depth:
            self._title_parts = []
        elif tag == "h1":
            self._heading_parts = []
        elif tag == "script" and "src" not in values:
            if values.get("type", "").strip().casefold() == "application/ld+json":
                self._json_ld_parts = []
                self._json_ld_line = line
            else:
                self._inline_script_parts = []
                self._inline_script_line = line

    def _collect_element(self, tag: str, values: dict[str, str], line: int) -> None:
        if tag == "meta":
            if self._head_depth:
                self._collect_meta(values, line)
            elif self._is_seo_meta(values):
                self.page.misplaced_seo.append(Reference("meta", line))
        elif tag == "link":
            self._collect_link(values, line, in_head=bool(self._head_depth))
        elif tag in {"a", "area"} and "href" in values:
            self.page.links.append(Reference(values["href"].strip(), line))
        elif tag == "form":
            self.page.forms.append(Reference(values.get("action", "").strip(), line))
        elif tag == "script":
            if "src" in values:
                self.page.assets.append(Reference(values["src"].strip(), line))
        else:
            self._collect_asset(tag, values, line)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title" and self._title_parts is not None:
            self.page.titles.append(_normalize_text("".join(self._title_parts)))
            self._title_parts = None
        elif tag == "h1" and self._heading_parts is not None:
            self.page.headings.append(_normalize_text("".join(self._heading_parts)))
            self._heading_parts = None
        elif tag == "script" and self._json_ld_parts is not None:
            self.page.json_ld.append(
                Reference("".join(self._json_ld_parts).strip(), self._json_ld_line)
            )
            self._json_ld_parts = None
        elif tag == "script" and self._inline_script_parts is not None:
            self.page.inline_scripts.append(
                Reference("".join(self._inline_script_parts).strip(), self._inline_script_line)
            )
            self._inline_script_parts = None
        elif tag == "head" and self._head_depth:
            self._head_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._title_parts is not None:
            self._title_parts.append(data)
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)
        if self._inline_script_parts is not None:
            self._inline_script_parts.append(data)

    def _collect_common(self, tag: str, values: dict[str, str]) -> None:
        identifier = values.get("id", "").strip()
        if identifier:
            self.page.ids[identifier] += 1
            self.page.fragment_names.add(identifier)
        name = values.get("name", "").strip()
        if tag == "a" and name:
            self.page.fragment_names.add(name)

    def _collect_meta(self, values: dict[str, str], line: int) -> None:
        name = values.get("name", "").strip().casefold()
        property_name = values.get("property", "").strip().casefold()
        content = values.get("content", "").strip()
        if name == "description":
            self.page.descriptions.append(content)
        elif name == "robots":
            self.page.robots.append(content)
        if property_name.startswith("og:"):
            self.page.og[property_name].append(content)
        if values.get("http-equiv", "").strip().casefold() == "refresh":
            self.page.refreshes.append(Reference(content, line))

    @staticmethod
    def _is_seo_meta(values: dict[str, str]) -> bool:
        name = values.get("name", "").strip().casefold()
        property_name = values.get("property", "").strip().casefold()
        http_equiv = values.get("http-equiv", "").strip().casefold()
        return (
            name in {"description", "robots"}
            or property_name.startswith("og:")
            or http_equiv == "refresh"
        )

    def _collect_link(self, values: dict[str, str], line: int, *, in_head: bool) -> None:
        if "href" not in values:
            return
        href = values["href"].strip()
        rels = set(values.get("rel", "").casefold().split())
        is_canonical = "canonical" in rels
        is_hreflang = "alternate" in rels and bool(values.get("hreflang", "").strip())
        if in_head and is_canonical:
            self.page.canonicals.append(href)
        elif in_head and is_hreflang:
            self.page.hreflangs.append(Hreflang(values["hreflang"].strip(), href, line))
        elif not in_head and (is_canonical or is_hreflang):
            self.page.misplaced_seo.append(Reference("link", line))
        elif not is_canonical and not is_hreflang:
            self.page.assets.append(Reference(href, line))

    def _collect_asset(self, tag: str, values: dict[str, str], line: int) -> None:
        attributes: tuple[str, ...] = ()
        if tag in {"audio", "embed", "iframe", "img", "input", "source", "video"}:
            attributes = ("src",)
        elif tag == "object":
            attributes = ("data",)
        elif tag == "use":
            attributes = ("href", "xlink:href")
        for attribute in attributes:
            if attribute in values:
                self.page.assets.append(Reference(values[attribute].strip(), line))
        if tag == "video" and "poster" in values:
            self.page.assets.append(Reference(values["poster"].strip(), line))
        if tag in {"img", "source"} and "srcset" in values:
            for candidate in _srcset_urls(values["srcset"]):
                self.page.assets.append(Reference(candidate, line))


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _srcset_urls(value: str) -> list[str]:
    """Return non-data URL tokens using the HTML srcset candidate algorithm."""
    urls: list[str] = []
    position = 0
    whitespace = " \t\n\f\r"
    while position < len(value):
        while position < len(value) and value[position] in f"{whitespace},":
            position += 1
        if position >= len(value):
            break

        start = position
        while position < len(value) and value[position] not in whitespace:
            position += 1
        url = value[start:position]

        if url.endswith(","):
            url = url.rstrip(",")
        else:
            while position < len(value) and value[position] != ",":
                position += 1
            if position < len(value):
                position += 1

        if url and not url.casefold().startswith("data:"):
            urls.append(url)
    return urls


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ConfigError(f"non-standard JSON constant is not allowed: {value}")


def _string_list(config: dict[str, Any], key: str) -> tuple[str, ...]:
    raw = config[key]
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{key!r} must be a non-empty array")
    if any(not isinstance(value, str) or not value for value in raw):
        raise ConfigError(f"{key!r} must contain non-empty strings")
    if len(set(raw)) != len(raw):
        raise ConfigError(f"{key!r} must not contain duplicates")
    return tuple(raw)


def _safe_file_path(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ConfigError(f"{key!r} must be a non-empty POSIX file path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(char in value for char in "*?[]#"):
        raise ConfigError(f"{key!r} must stay inside the site root")
    return value


def _public_path(value: str, key: str, *, allow_fragment: bool, allow_query: bool = False) -> None:
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ConfigError(f"{key!r} contains an invalid site path: {value!r}") from exc
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parts.scheme
        or parts.netloc
        or (parts.query and not allow_query)
        or "\\" in value
        or ".." in PurePosixPath(parts.path).parts
    ):
        raise ConfigError(f"{key!r} contains an invalid site path: {value!r}")
    if parts.fragment and not allow_fragment:
        raise ConfigError(f"{key!r} must not contain a fragment: {value!r}")


def _path_mapping(config: dict[str, Any], key: str, *, allow_fragment: bool) -> dict[str, str]:
    raw = config[key]
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(f"{key!r} must be a non-empty object")
    result: dict[str, str] = {}
    for source, target in raw.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise ConfigError(f"{key!r} keys and values must be strings")
        _public_path(source, key, allow_fragment=False)
        _public_path(
            target,
            key,
            allow_fragment=allow_fragment,
            allow_query=allow_fragment,
        )
        result[source] = target
    return result


def _read_config_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ConfigError) as exc:
        raise ConfigError(f"could not read configuration: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration must be a JSON object")
    return raw


def _validate_config_keys(raw: dict[str, Any]) -> None:
    missing = sorted(_CONFIG_KEYS - raw.keys())
    unknown = sorted(raw.keys() - _CONFIG_KEYS)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown keys: {', '.join(unknown)}")
        raise ConfigError("; ".join(details))
    if (
        not isinstance(raw["schema_version"], int)
        or isinstance(raw["schema_version"], bool)
        or raw["schema_version"] != 1
    ):
        raise ConfigError("schema_version must be 1")


def _site_origin(raw: dict[str, Any]) -> str:
    origin = raw["site_origin"]
    if not isinstance(origin, str):
        raise ConfigError("'site_origin' must be a string")
    try:
        origin_parts = urlsplit(origin)
        hostname = origin_parts.hostname
        # Accessing .port performs urllib's numeric and range validation.
        _ = origin_parts.port
    except ValueError as exc:
        raise ConfigError("'site_origin' must be an HTTPS origin without a trailing slash") from exc
    if (
        origin_parts.scheme != "https"
        or not origin_parts.netloc
        or hostname is None
        or not _valid_hostname(hostname)
        or origin_parts.username is not None
        or origin_parts.password is not None
        or origin_parts.path
        or origin_parts.query
        or origin_parts.fragment
        or origin.endswith("/")
    ):
        raise ConfigError("'site_origin' must be an HTTPS origin without a trailing slash")
    return origin


def _valid_hostname(hostname: str) -> bool:
    """Accept an IP literal or a well-formed IDNA hostname."""
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if hostname.endswith("."):
        return False
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if len(ascii_hostname) > 253:
        return False
    return all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) is not None
        for label in ascii_hostname.split(".")
    )


def _config_path_lists(
    raw: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fragment_prefixes = _string_list(raw, "fragment_exempt_prefixes")
    noindex_patterns = _string_list(raw, "noindex_path_patterns")
    for value in fragment_prefixes:
        _public_path(value, "fragment_exempt_prefixes", allow_fragment=False)
        if not value.endswith("/") or "*" in value:
            raise ConfigError(
                f"'fragment_exempt_prefixes' values must be literal directory paths: {value!r}"
            )
    for pattern in noindex_patterns:
        _validate_path_pattern(pattern, "noindex_path_patterns")
    return fragment_prefixes, noindex_patterns


def _validate_path_pattern(pattern: str, key: str) -> None:
    _public_path(pattern, key, allow_fragment=False)
    parts = pattern.strip("/").split("/")
    if (
        not pattern.endswith("/")
        or any(part != "*" and "*" in part for part in parts)
        or any(char in pattern for char in "[]?")
    ):
        raise ConfigError(f"invalid path pattern in {key!r}: {pattern!r}")


def _matches_path_pattern(public_path: str, pattern: str) -> bool:
    path_parts = public_path.strip("/").split("/")
    pattern_parts = pattern.strip("/").split("/")
    return len(path_parts) == len(pattern_parts) and all(
        expected == "*" or expected == actual
        for actual, expected in zip(path_parts, pattern_parts, strict=True)
    )


def _hreflang_groups(raw: dict[str, Any]) -> tuple[dict[str, str], ...]:
    groups = raw["hreflang_groups"]
    if not isinstance(groups, list) or not groups:
        raise ConfigError("'hreflang_groups' must be a non-empty array")
    result: list[dict[str, str]] = []
    used_paths: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or len(group) < 2:
            raise ConfigError("each hreflang group must map at least two languages")
        checked: dict[str, str] = {}
        for language, public_path in group.items():
            if (
                not isinstance(language, str)
                or not re.fullmatch(
                    r"(?:[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)*)|x-default",
                    language,
                )
                or not isinstance(public_path, str)
            ):
                raise ConfigError("hreflang groups must map valid language tags to paths")
            _public_path(public_path, "hreflang_groups", allow_fragment=False)
            if public_path in used_paths:
                raise ConfigError(f"hreflang path appears in multiple groups: {public_path!r}")
            used_paths.add(public_path)
            folded_language = language.casefold()
            if folded_language in checked:
                raise ConfigError(f"hreflang group contains a duplicate language tag: {language!r}")
            checked[folded_language] = public_path
        if len(checked) < 2:
            raise ConfigError("each hreflang group must map at least two distinct languages")
        if len(set(checked.values())) != len(checked):
            raise ConfigError("hreflang group paths must be unique")
        result.append(checked)
    return tuple(result)


def _required_json_ld_types(raw: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    requirements = raw["required_json_ld_types"]
    if not isinstance(requirements, dict) or not requirements:
        raise ConfigError("'required_json_ld_types' must be a non-empty object")
    result: dict[str, tuple[str, ...]] = {}
    for pattern, type_names in requirements.items():
        if not isinstance(pattern, str):
            raise ConfigError("'required_json_ld_types' keys must be strings")
        _validate_path_pattern(pattern, "required_json_ld_types")
        if (
            not isinstance(type_names, list)
            or not type_names
            or any(not isinstance(item, str) or not item for item in type_names)
            or len(set(type_names)) != len(type_names)
        ):
            raise ConfigError("required JSON-LD types must be unique non-empty strings")
        result[pattern] = tuple(type_names)
    return result


def _validate_terminal_aliases(
    canonical_aliases: dict[str, str],
    redirect_aliases: dict[str, str],
    noindex_patterns: tuple[str, ...],
) -> None:
    sources = canonical_aliases.keys() | redirect_aliases.keys()
    for source, target in (*canonical_aliases.items(), *redirect_aliases.items()):
        target_path = urlsplit(target).path
        if target_path in sources:
            raise ConfigError(f"alias target must be terminal, not another alias: {source!r}")
        if any(_matches_path_pattern(target_path, pattern) for pattern in noindex_patterns):
            raise ConfigError(f"alias target must not be a configured noindex page: {source!r}")


def load_config(path: Path) -> Config:
    """Read and strictly validate schema-v1 configuration."""
    raw = _read_config_object(path)
    _validate_config_keys(raw)
    origin = _site_origin(raw)
    fragment_prefixes, noindex_patterns = _config_path_lists(raw)

    canonical_aliases = _path_mapping(raw, "canonical_aliases", allow_fragment=False)
    redirect_aliases = _path_mapping(raw, "redirect_aliases", allow_fragment=True)
    overlap = sorted(canonical_aliases.keys() & redirect_aliases.keys())
    if overlap:
        raise ConfigError(f"alias source paths overlap: {', '.join(overlap)}")
    _validate_terminal_aliases(canonical_aliases, redirect_aliases, noindex_patterns)
    return Config(
        site_origin=origin,
        sitemap_path=_safe_file_path(raw["sitemap_path"], "sitemap_path"),
        robots_path=_safe_file_path(raw["robots_path"], "robots_path"),
        retained_redirects_path=_safe_file_path(
            raw["retained_redirects_path"], "retained_redirects_path"
        ),
        fragment_exempt_prefixes=fragment_prefixes,
        noindex_path_patterns=noindex_patterns,
        canonical_aliases=canonical_aliases,
        hreflang_groups=_hreflang_groups(raw),
        required_json_ld_types=_required_json_ld_types(raw),
        redirect_aliases=redirect_aliases,
    )


def _public_path_for(relative_path: str) -> str:
    if relative_path == "index.html":
        return "/"
    if relative_path.endswith("/index.html"):
        return f"/{relative_path[: -len('index.html')]}"
    return f"/{relative_path}"


def _scan_pages(site_root: Path) -> tuple[dict[str, Page], set[str]]:
    files = sorted(
        path.relative_to(site_root).as_posix() for path in site_root.rglob("*") if path.is_file()
    )
    pages: dict[str, Page] = {}
    for relative_path in files:
        if not relative_path.casefold().endswith(".html"):
            continue
        path = site_root / relative_path
        parser = PageParser(relative_path, _public_path_for(relative_path))
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        pages[relative_path] = parser.page
    return pages, set(files)


def _is_noindex_path(public_path: str, config: Config) -> bool:
    return any(
        _matches_path_pattern(public_path, pattern) for pattern in config.noindex_path_patterns
    )


def _intended_canonical_path(page: Page, config: Config) -> str:
    return config.canonical_aliases.get(page.public_path, page.public_path)


def _absolute(config: Config, public_path: str) -> str:
    return f"{config.site_origin}{public_path}"


def _local_target(raw: str, page: Page, config: Config) -> LocalTarget | None:
    stripped = raw.strip()
    scheme = urlsplit(stripped).scheme.casefold()
    if scheme in _IGNORED_SCHEMES:
        return None
    joined = urlsplit(urljoin(_absolute(config, page.public_path), stripped))
    origin = urlsplit(config.site_origin)
    if joined.scheme not in {"http", "https"}:
        return None
    joined_hostname = (joined.hostname or "").casefold()
    origin_hostname = (origin.hostname or "").casefold()
    if joined_hostname != origin_hostname:
        return None
    if joined.scheme == "https":
        joined_port = joined.port or 443
        origin_port = origin.port or 443
        if joined_port != origin_port:
            return None
    elif not joined_hostname:
        return None
    return LocalTarget(
        scheme=joined.scheme.casefold(),
        path=unquote(joined.path or "/"),
        query=joined.query,
        fragment=unquote(joined.fragment),
    )


def _resolve_file(path: str, files: set[str]) -> str | None:
    if "\\" in path or not path.startswith("/"):
        return None
    relative = path.lstrip("/")
    candidates = [relative]
    if not relative:
        candidates = ["index.html"]
    elif path.endswith("/"):
        candidates = [f"{relative}index.html"]
    else:
        candidates.append(f"{relative}/index.html")
    return next((candidate for candidate in candidates if candidate in files), None)


def _single(
    page: Page,
    values: list[str],
    label: str,
    findings: list[Finding],
    *,
    prefix: str = "metadata",
) -> str | None:
    if not values:
        findings.append(
            Finding(f"{prefix}.{label}_missing", page.relative_path, f"missing {label}")
        )
        return None
    if len(values) > 1:
        findings.append(
            Finding(
                f"{prefix}.{label}_multiple",
                page.relative_path,
                f"found {len(values)} {label} values; expected one",
            )
        )
        return None
    if not values[0].strip():
        findings.append(Finding(f"{prefix}.{label}_empty", page.relative_path, f"{label} is empty"))
        return None
    return values[0].strip()


def _validate_reference(
    page: Page,
    reference: Reference,
    kind: str,
    config: Config,
    pages: dict[str, Page],
    files: set[str],
    findings: list[Finding],
) -> None:
    try:
        target = _local_target(reference.value, page, config)
    except ValueError:
        findings.append(
            Finding(
                f"{kind}.malformed_url",
                page.relative_path,
                f"line {reference.line}: malformed URL {reference.value!r}",
            )
        )
        return
    if target is None:
        return
    if target.scheme != "https":
        findings.append(
            Finding(
                f"{kind}.insecure_same_site",
                page.relative_path,
                f"line {reference.line}: same-site URL must use HTTPS: {reference.value!r}",
            )
        )
    relative = _resolve_file(target.path, files)
    if relative is None:
        findings.append(
            Finding(
                f"{kind}.missing_target",
                page.relative_path,
                f"line {reference.line}: local target does not exist: {reference.value!r}",
            )
        )
        return
    if (
        kind in {"link", "form", "redirect"}
        and target.fragment
        and relative in pages
        and not any(target.path.startswith(prefix) for prefix in config.fragment_exempt_prefixes)
        and target.fragment not in pages[relative].fragment_names
    ):
        findings.append(
            Finding(
                "fragment.missing",
                page.relative_path,
                f"line {reference.line}: fragment #{target.fragment} is missing in {relative}",
            )
        )


def _is_forbidden_telemetry_reference(value: str, page: Page, config: Config) -> bool:
    try:
        resolved = urlsplit(urljoin(_absolute(config, page.public_path), value.strip()))
        hostname = (resolved.hostname or "").casefold()
    except ValueError:
        return False
    if any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _FORBIDDEN_TELEMETRY_HOST_SUFFIXES
    ):
        return True
    origin = urlsplit(config.site_origin)
    return (
        resolved.netloc.casefold() == origin.netloc.casefold()
        and PurePosixPath(unquote(resolved.path)).name in _FORBIDDEN_TELEMETRY_FILES
    )


def _contains_forbidden_telemetry_marker(value: str) -> bool:
    folded = value.casefold()
    return any(marker in folded for marker in _FORBIDDEN_TELEMETRY_MARKERS)


def _validate_no_tracking(
    site_root: Path,
    pages: dict[str, Page],
    files: set[str],
    config: Config,
    findings: list[Finding],
) -> None:
    for page in pages.values():
        for reference in page.assets:
            if _is_forbidden_telemetry_reference(reference.value, page, config):
                findings.append(
                    Finding(
                        "privacy.telemetry_asset",
                        page.relative_path,
                        (
                            f"line {reference.line}: tracking/analytics asset is forbidden: "
                            f"{reference.value!r}"
                        ),
                    )
                )
        for script in page.inline_scripts:
            if _contains_forbidden_telemetry_marker(script.value):
                findings.append(
                    Finding(
                        "privacy.telemetry_script",
                        page.relative_path,
                        f"line {script.line}: inline tracking/analytics loader is forbidden",
                    )
                )

    for relative_path in sorted(files):
        path = PurePosixPath(relative_path)
        if path.name in _FORBIDDEN_TELEMETRY_FILES:
            findings.append(
                Finding(
                    "privacy.telemetry_file",
                    relative_path,
                    "tracking/analytics loader file is forbidden by the public privacy policy",
                )
            )
        if path.suffix.casefold() != ".js":
            continue
        # A distinct name: `script` above this loop is a Reference, and reusing
        # it for the file's text made a strict-mode type error inside the
        # privacy gate that nothing was checking.
        script_source = (site_root / relative_path).read_text(encoding="utf-8")
        if _contains_forbidden_telemetry_marker(script_source):
            findings.append(
                Finding(
                    "privacy.telemetry_script",
                    relative_path,
                    "JavaScript contains a forbidden tracking/analytics host",
                )
            )


def _validate_metadata(
    page: Page,
    config: Config,
    findings: list[Finding],
    *,
    require_h1: bool = True,
) -> None:
    _single(page, page.titles, "title", findings)
    _single(page, page.descriptions, "description", findings)
    canonical = _single(page, page.canonicals, "canonical", findings)
    if require_h1:
        _single(page, page.headings, "h1", findings)
    for field_name in _OG_FIELDS:
        _single(page, page.og.get(field_name, []), field_name.replace(":", "_"), findings)

    expected = _absolute(config, _intended_canonical_path(page, config))
    if canonical is not None and canonical != expected:
        findings.append(
            Finding(
                "metadata.canonical_mismatch",
                page.relative_path,
                f"canonical must be {expected!r}, found {canonical!r}",
            )
        )
    og_url = page.og.get("og:url", [])
    if len(og_url) == 1 and og_url[0] != expected:
        findings.append(
            Finding(
                "metadata.og_url_mismatch",
                page.relative_path,
                f"og:url must be {expected!r}, found {og_url[0]!r}",
            )
        )


def _refresh_target(value: str) -> str | None:
    match = _REFRESH_RE.fullmatch(value)
    if match is None:
        return None
    return match.group(1).strip().strip("\"'")


def _load_retained_redirects(
    site_root: Path, config: Config, findings: list[Finding]
) -> dict[str, str]:
    """Load the renderer-owned registry alias manifest, failing closed."""
    relative_path = config.retained_redirects_path
    path = site_root / relative_path
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ConfigError) as exc:
        findings.append(
            Finding(
                "redirect.manifest_unreadable",
                relative_path,
                f"could not read retained redirect manifest: {exc}",
            )
        )
        return {}
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "redirects"}
        or not isinstance(payload.get("schema_version"), int)
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("redirects"), dict)
    ):
        findings.append(
            Finding(
                "redirect.manifest_invalid",
                relative_path,
                "manifest must contain only schema_version 1 and a redirects object",
            )
        )
        return {}
    raw_redirects = payload["redirects"]
    redirects: dict[str, str] = {}
    invalid = False
    for source, target in raw_redirects.items():
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or _AGENCY_PATH_RE.fullmatch(source) is None
            or _AGENCY_PATH_RE.fullmatch(target) is None
            or source == target
        ):
            invalid = True
            continue
        redirects[source] = target
    alias_sources = (
        config.canonical_aliases.keys() | config.redirect_aliases.keys() | redirects.keys()
    )
    if (
        invalid
        or len(redirects) != len(raw_redirects)
        or any(source in config.canonical_aliases for source in redirects)
        or any(source in config.redirect_aliases for source in redirects)
        or any(target in alias_sources for target in redirects.values())
    ):
        findings.append(
            Finding(
                "redirect.manifest_invalid",
                relative_path,
                "retained redirects must be distinct terminal agency paths without alias overlap",
            )
        )
        return {}
    return redirects


def _validate_redirect(
    page: Page,
    expected_target: str,
    config: Config,
    pages: dict[str, Page],
    files: set[str],
    findings: list[Finding],
) -> None:
    _single(page, page.titles, "title", findings, prefix="redirect")
    _single(page, page.headings, "h1", findings, prefix="redirect")
    refresh = _single(
        page,
        [item.value for item in page.refreshes],
        "refresh",
        findings,
        prefix="redirect",
    )
    if refresh is not None and _refresh_target(refresh) != expected_target:
        findings.append(
            Finding(
                "redirect.refresh_target",
                page.relative_path,
                f"refresh must keep full target {expected_target!r}",
            )
        )
    fallback = [link for link in page.links if link.value == expected_target]
    if not fallback:
        findings.append(
            Finding(
                "redirect.fallback_target",
                page.relative_path,
                f"fallback link must keep full target {expected_target!r}",
            )
        )
    expected_canonical = _absolute(config, expected_target.partition("#")[0])
    canonical = _single(page, page.canonicals, "canonical", findings, prefix="redirect")
    if canonical is not None and canonical != expected_canonical:
        findings.append(
            Finding(
                "redirect.canonical_target",
                page.relative_path,
                f"canonical must omit the redirect fragment: {expected_canonical!r}",
            )
        )
    if page.robots:
        findings.append(
            Finding(
                "redirect.unexpected_noindex",
                page.relative_path,
                "redirect alias has robots meta",
            )
        )
    if page.refreshes:
        _validate_reference(
            page,
            Reference(expected_target, page.refreshes[0].line),
            "redirect",
            config,
            pages,
            files,
            findings,
        )


def _validate_noindex(page: Page, config: Config, findings: list[Finding]) -> None:
    expected = _is_noindex_path(page.public_path, config)
    if len(page.robots) > 1:
        findings.append(
            Finding(
                "noindex.multiple",
                page.relative_path,
                f"found {len(page.robots)} robots meta values; expected at most one",
            )
        )
        return
    if expected and not page.robots:
        findings.append(
            Finding("noindex.missing", page.relative_path, "configured noindex page is indexable")
        )
        return
    if not expected and page.robots:
        findings.append(
            Finding("noindex.unexpected", page.relative_path, "unconfigured robots meta is present")
        )
        return
    if expected:
        directives = {item for item in re.split(r"[\s,]+", page.robots[0].casefold()) if item}
        if directives != {"follow", "noindex"}:
            findings.append(
                Finding(
                    "noindex.directives",
                    page.relative_path,
                    "configured noindex page must use exactly 'noindex,follow'",
                )
            )


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        if _DATE_RE.fullmatch(value):
            date.fromisoformat(value)
            return True
        if _DATETIME_RE.fullmatch(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
    except ValueError:
        return False
    return False


def _json_ld_dates(value: Any, location: str = "$") -> list[tuple[str, Any]]:
    dates: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key in _JSON_LD_DATE_KEYS:
                dates.append((child_location, child))
            dates.extend(_json_ld_dates(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            dates.extend(_json_ld_dates(child, f"{location}[{index}]"))
    return dates


def _json_ld_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        nodes.append(value)
        for child in value.values():
            nodes.extend(_json_ld_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_json_ld_nodes(child))
    return nodes


def _validate_json_ld(page: Page, findings: list[Finding]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for block in page.json_ld:
        try:
            value = json.loads(
                block.value,
                object_pairs_hook=_strict_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ConfigError) as exc:
            message = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
            findings.append(
                Finding(
                    "jsonld.malformed",
                    page.relative_path,
                    f"line {block.line}: malformed JSON-LD: {message}",
                )
            )
            continue
        if not isinstance(value, (dict, list)):
            findings.append(
                Finding(
                    "jsonld.top_level",
                    page.relative_path,
                    f"line {block.line}: JSON-LD must be an object or array",
                )
            )
            continue
        nodes.extend(_json_ld_nodes(value))
        for location, date_value in _json_ld_dates(value):
            if not _valid_iso_date(date_value):
                findings.append(
                    Finding(
                        "jsonld.invalid_date",
                        page.relative_path,
                        f"line {block.line}: {location} is not a valid ISO 8601 date",
                    )
                )
    return nodes


def _node_has_type(node: dict[str, Any], type_name: str) -> bool:
    raw_type = node.get("@type")
    return raw_type == type_name or (isinstance(raw_type, list) and type_name in raw_type)


def _validate_required_json_ld(
    page: Page,
    nodes: list[dict[str, Any]],
    config: Config,
    findings: list[Finding],
) -> None:
    for pattern, required_types in config.required_json_ld_types.items():
        if not _matches_path_pattern(page.public_path, pattern):
            continue
        for type_name in required_types:
            matching = [node for node in nodes if _node_has_type(node, type_name)]
            if not matching:
                findings.append(
                    Finding(
                        "jsonld.required_type_missing",
                        page.relative_path,
                        f"configured page pattern requires JSON-LD @type {type_name!r}",
                    )
                )
                continue
            expected_url = _absolute(config, _intended_canonical_path(page, config))
            for node in matching:
                context = node.get("@context")
                if not isinstance(context, str) or context.rstrip("/") != "https://schema.org":
                    findings.append(
                        Finding(
                            "jsonld.required_context",
                            page.relative_path,
                            f"JSON-LD @type {type_name!r} requires schema.org @context",
                        )
                    )
                if node.get("url") != expected_url:
                    findings.append(
                        Finding(
                            "jsonld.required_url",
                            page.relative_path,
                            (f"JSON-LD @type {type_name!r} url must equal {expected_url!r}"),
                        )
                    )


def _validate_duplicate_metadata(
    pages: dict[str, Page],
    config: Config,
    redirect_aliases: dict[str, str],
    findings: list[Finding],
) -> None:
    getters: tuple[tuple[str, Callable[[Page], list[str]]], ...] = (
        ("title", lambda page: page.titles),
        ("description", lambda page: page.descriptions),
    )
    for label, getter in getters:
        groups: dict[str, list[Page]] = defaultdict(list)
        for page in pages.values():
            if (
                page.public_path in redirect_aliases
                or page.public_path in config.canonical_aliases
                or _is_noindex_path(page.public_path, config)
            ):
                continue
            values = getter(page)
            if len(values) == 1 and values[0]:
                groups[_normalize_text(values[0]).casefold()].append(page)
        for duplicates in groups.values():
            if len(duplicates) < 2:
                continue
            paths = sorted(page.relative_path for page in duplicates)
            findings.append(
                Finding(
                    f"metadata.duplicate_{label}",
                    paths[0],
                    f"duplicate {label} across: {', '.join(paths)}",
                )
            )


def _validate_alias_configuration(
    pages: dict[str, Page],
    files: set[str],
    config: Config,
    redirect_aliases: dict[str, str],
    findings: list[Finding],
) -> None:
    pages_by_public = {page.public_path: page for page in pages.values()}
    for source, target in (*config.canonical_aliases.items(), *redirect_aliases.items()):
        if source not in pages_by_public:
            findings.append(
                Finding("alias.missing_source", source, "configured alias page is missing")
            )
        target_path = urlsplit(target).path
        relative = _resolve_file(target_path, files)
        if relative not in pages:
            findings.append(
                Finding(
                    "alias.missing_target",
                    source,
                    f"configured target is missing: {target_path}",
                )
            )
            continue
        target_page = pages[relative]
        if target_page.public_path != target_path:
            findings.append(
                Finding(
                    "alias.target_noncanonical_path",
                    source,
                    (
                        f"alias target must use the rendered page's exact public path "
                        f"{target_page.public_path!r}, not {target_path!r}"
                    ),
                )
            )
        if target_page.refreshes:
            findings.append(
                Finding(
                    "alias.target_redirect",
                    source,
                    f"alias target must be terminal: {target_path}",
                )
            )
        directives = {
            item
            for value in target_page.robots
            for item in re.split(r"[\s,]+", value.casefold())
            if item
        }
        if _is_noindex_path(target_page.public_path, config) or directives & {
            "noindex",
            "none",
        }:
            findings.append(
                Finding(
                    "alias.target_noindex",
                    source,
                    f"alias target must be indexable: {target_path}",
                )
            )

    actual_refresh = {page.public_path for page in pages.values() if page.refreshes}
    configured_refresh = set(redirect_aliases)
    for source in sorted(actual_refresh - configured_refresh):
        findings.append(
            Finding("redirect.unconfigured", source, "meta-refresh alias is not configured")
        )
    for source in sorted(configured_refresh - actual_refresh):
        findings.append(
            Finding("redirect.refresh_missing", source, "configured redirect has no meta refresh")
        )


def _hreflang_map(page: Page) -> dict[str, list[Hreflang]]:
    result: dict[str, list[Hreflang]] = defaultdict(list)
    for alternate in page.hreflangs:
        result[alternate.language.casefold()].append(alternate)
    return result


def _is_exact_canonical_href(href: str, expected_path: str, config: Config) -> bool:
    return href.strip() == _absolute(config, expected_path)


def _validate_hreflang_groups(
    pages: dict[str, Page], config: Config, findings: list[Finding]
) -> None:
    pages_by_public = {page.public_path: page for page in pages.values()}
    for group in config.hreflang_groups:
        for source_language, source_path in group.items():
            page = pages_by_public.get(source_path)
            if page is None:
                findings.append(
                    Finding(
                        "hreflang.required_page_missing",
                        source_path,
                        "configured hreflang page is missing",
                    )
                )
                continue
            if source_language != "x-default" and page.language.casefold() != source_language:
                findings.append(
                    Finding(
                        "hreflang.source_language",
                        page.relative_path,
                        f"html lang must be {source_language!r}",
                    )
                )
            alternates = _hreflang_map(page)
            unexpected_languages = sorted(set(alternates) - set(group))
            for language in unexpected_languages:
                findings.append(
                    Finding(
                        "hreflang.unexpected_alternate",
                        page.relative_path,
                        f"configured hreflang group does not include {language!r}",
                    )
                )
            for target_language, target_path in group.items():
                entries = alternates.get(target_language, [])
                matches = [
                    alternate
                    for alternate in entries
                    if _is_exact_canonical_href(alternate.href, target_path, config)
                ]
                if len(entries) != 1 or len(matches) != 1:
                    findings.append(
                        Finding(
                            "hreflang.required_alternate",
                            page.relative_path,
                            (f"expected one {target_language!r} alternate to {target_path!r}"),
                        )
                    )


def _validate_hreflang(
    pages: dict[str, Page], files: set[str], config: Config, findings: list[Finding]
) -> None:
    _validate_hreflang_groups(pages, config, findings)
    for page in pages.values():
        if not page.hreflangs:
            continue
        alternates = _hreflang_map(page)
        for language, values in alternates.items():
            if len(values) > 1:
                findings.append(
                    Finding(
                        "hreflang.duplicate",
                        page.relative_path,
                        f"hreflang {language!r} appears {len(values)} times",
                    )
                )
        source_language = page.language.casefold()
        source_path = _intended_canonical_path(page, config)
        if not source_language or not any(
            _is_exact_canonical_href(item.href, source_path, config)
            for item in alternates.get(source_language, [])
        ):
            findings.append(
                Finding(
                    "hreflang.self_missing",
                    page.relative_path,
                    "alternate-language set must contain a canonical self-reference",
                )
            )
        for alternate in page.hreflangs:
            _validate_hreflang_alternate(page, alternate, pages, files, config, findings)


def _validate_hreflang_alternate(
    page: Page,
    alternate: Hreflang,
    pages: dict[str, Page],
    files: set[str],
    config: Config,
    findings: list[Finding],
) -> None:
    try:
        target = _local_target(alternate.href, page, config)
    except ValueError:
        target = None
    if target is None:
        return
    expected_href = _absolute(config, target.path)
    if target.query or target.fragment or alternate.href.strip() != expected_href:
        findings.append(
            Finding(
                "hreflang.noncanonical_url",
                page.relative_path,
                (
                    f"line {alternate.line}: hreflang URL must be the exact "
                    f"absolute HTTPS canonical {expected_href!r}"
                ),
            )
        )
        return
    relative = _resolve_file(target.path, files)
    if relative is None or relative not in pages:
        findings.append(
            Finding(
                "hreflang.missing_target",
                page.relative_path,
                f"line {alternate.line}: local hreflang target is missing",
            )
        )
        return
    target_page = pages[relative]
    if (
        alternate.language.casefold() != "x-default"
        and target_page.language.casefold() != alternate.language.casefold()
    ):
        findings.append(
            Finding(
                "hreflang.language_mismatch",
                page.relative_path,
                f"line {alternate.line}: hreflang does not match target html lang",
            )
        )
    source_language = page.language.casefold()
    source_path = _intended_canonical_path(page, config)
    reciprocal = _hreflang_map(target_page).get(source_language, [])
    if not any(_is_exact_canonical_href(item.href, source_path, config) for item in reciprocal):
        findings.append(
            Finding(
                "hreflang.not_reciprocal",
                page.relative_path,
                f"line {alternate.line}: target does not link back for {source_language!r}",
            )
        )


def _sitemap_tag(local_name: str) -> str:
    return f"{{{_SITEMAP_NAMESPACE}}}{local_name}"


def _expected_sitemap_urls(
    pages: dict[str, Page], config: Config, redirect_aliases: dict[str, str]
) -> set[str]:
    return {
        _absolute(config, _intended_canonical_path(page, config))
        for page in pages.values()
        if page.public_path not in redirect_aliases
        and not _is_noindex_path(page.public_path, config)
    }


def _parse_sitemap(path: Path, relative_path: str, findings: list[Finding]) -> Element | None:
    if not path.is_file():
        findings.append(Finding("sitemap.missing", relative_path, "sitemap file is missing"))
        return None
    try:
        root = DefusedET.parse(path).getroot()
    except (DefusedXmlException, ParseError, OSError) as exc:
        findings.append(
            Finding("sitemap.malformed", relative_path, f"could not parse sitemap: {exc}")
        )
        return None
    if root.tag != _sitemap_tag("urlset"):
        findings.append(
            Finding(
                "sitemap.root",
                relative_path,
                (
                    "sitemap root must be urlset in the sitemap protocol namespace "
                    f"{_SITEMAP_NAMESPACE!r}"
                ),
            )
        )
        return None
    return cast("Element", root)


def _sitemap_locations(root: Element, relative_path: str, findings: list[Finding]) -> list[str]:
    locations: list[str] = []
    for url_node in root:
        if url_node.tag != _sitemap_tag("url"):
            findings.append(
                Finding(
                    "sitemap.element",
                    relative_path,
                    "urlset contains an element outside the sitemap protocol namespace",
                )
            )
            continue
        loc_nodes = [child for child in url_node if child.tag == _sitemap_tag("loc")]
        if len(loc_nodes) != 1 or not (loc_nodes[0].text or "").strip():
            findings.append(
                Finding("sitemap.loc", relative_path, "each url must contain one non-empty loc")
            )
            continue
        location = (loc_nodes[0].text or "").strip()
        locations.append(location)
        for lastmod in (child for child in url_node if child.tag == _sitemap_tag("lastmod")):
            if not _valid_iso_date((lastmod.text or "").strip()):
                findings.append(
                    Finding(
                        "sitemap.invalid_lastmod",
                        relative_path,
                        f"invalid lastmod for {location!r}",
                    )
                )
    return locations


def _validate_sitemap(
    site_root: Path,
    pages: dict[str, Page],
    config: Config,
    redirect_aliases: dict[str, str],
    findings: list[Finding],
) -> None:
    relative_path = config.sitemap_path
    root = _parse_sitemap(site_root / relative_path, relative_path, findings)
    if root is None:
        return
    locations = _sitemap_locations(root, relative_path, findings)
    for location, count in sorted(Counter(locations).items()):
        if count > 1:
            findings.append(
                Finding(
                    "sitemap.duplicate_url",
                    relative_path,
                    f"URL appears {count} times: {location}",
                )
            )
    actual = set(locations)
    expected = _expected_sitemap_urls(pages, config, redirect_aliases)
    for location in sorted(expected - actual):
        findings.append(
            Finding("sitemap.missing_url", relative_path, f"missing canonical URL: {location}")
        )
    for location in sorted(actual - expected):
        findings.append(
            Finding("sitemap.unexpected_url", relative_path, f"unexpected URL: {location}")
        )


def _validate_robots(site_root: Path, config: Config, findings: list[Finding]) -> None:
    relative_path = config.robots_path
    path = site_root / relative_path
    if not path.is_file():
        findings.append(Finding("robots.missing", relative_path, "robots file is missing"))
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        findings.append(
            Finding("robots.unreadable", relative_path, f"could not read robots file: {exc}")
        )
        return
    pointers = []
    for line in lines:
        directive, separator, value = line.partition(":")
        if separator and directive.strip().casefold() == "sitemap":
            pointers.append(value.strip())
    expected = _absolute(config, f"/{config.sitemap_path}")
    if pointers != [expected]:
        findings.append(
            Finding(
                "robots.sitemap_pointer",
                relative_path,
                f"expected exactly one sitemap pointer to {expected!r}",
            )
        )
    if _robots_blocks_site(lines):
        findings.append(
            Finding(
                "robots.disallow_all",
                relative_path,
                "robots.txt globally disallows the rendered site",
            )
        )


def _robots_blocks_site(lines: list[str]) -> bool:
    """Return whether effective wildcard-agent rules block the site root."""
    groups: list[tuple[set[str], list[tuple[bool, str]]]] = []
    agents: set[str] = set()
    rules: list[tuple[bool, str]] = []
    for raw_line in lines:
        line = raw_line.partition("#")[0].strip()
        directive, separator, value = line.partition(":")
        if not separator:
            continue
        directive = directive.strip().casefold()
        value = value.strip()
        if directive == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents = set()
                rules = []
            agents.add(value.casefold())
            continue
        if directive in {"allow", "disallow"} and agents and value:
            rules.append((directive == "allow", value))
    if agents or rules:
        groups.append((agents, rules))

    wildcard_rules = [
        rule for group_agents, group_rules in groups if "*" in group_agents for rule in group_rules
    ]
    matches = [
        (_robots_rule_specificity(pattern), is_allow)
        for is_allow, pattern in wildcard_rules
        if _robots_rule_matches(pattern, "/")
    ]
    if not matches:
        return False
    most_specific = max(score for score, _ in matches)
    # At equal specificity, the less restrictive Allow rule wins.
    return not any(is_allow for score, is_allow in matches if score == most_specific)


def _robots_rule_matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    core = pattern[:-1] if anchored else pattern
    expression = "^" + re.escape(core).replace(r"\*", ".*")
    if anchored:
        expression += "$"
    return re.search(expression, path) is not None


def _robots_rule_specificity(pattern: str) -> int:
    core = pattern[:-1] if pattern.endswith("$") else pattern
    return len(core.replace("*", ""))


def _validate_page(
    page: Page,
    pages: dict[str, Page],
    files: set[str],
    config: Config,
    redirect_aliases: dict[str, str],
    findings: list[Finding],
) -> None:
    is_redirect = page.public_path in redirect_aliases
    if is_redirect:
        _validate_redirect(
            page,
            redirect_aliases[page.public_path],
            config,
            pages,
            files,
            findings,
        )
    else:
        _validate_metadata(
            page,
            config,
            findings,
            require_h1=page.public_path not in config.canonical_aliases,
        )
    _validate_noindex(page, config, findings)
    json_ld_nodes = _validate_json_ld(page, findings)
    if not is_redirect:
        _validate_required_json_ld(page, json_ld_nodes, config, findings)
    for reference in page.misplaced_seo:
        findings.append(
            Finding(
                "html.seo_outside_head",
                page.relative_path,
                f"line {reference.line}: SEO {reference.value} element must be inside <head>",
            )
        )
    for identifier, count in sorted(page.ids.items()):
        if count > 1:
            findings.append(
                Finding(
                    "html.duplicate_id",
                    page.relative_path,
                    f"id {identifier!r} appears {count} times",
                )
            )
    for kind, references in (
        ("link", page.links),
        ("asset", page.assets),
        ("form", page.forms),
    ):
        for reference in references:
            _validate_reference(page, reference, kind, config, pages, files, findings)
    og_images = page.og.get("og:image", [])
    if len(og_images) == 1:
        _validate_reference(
            page, Reference(og_images[0], 0), "asset", config, pages, files, findings
        )


def _validate_noindex_patterns(
    pages: dict[str, Page], config: Config, findings: list[Finding]
) -> None:
    for pattern in config.noindex_path_patterns:
        if any(_matches_path_pattern(page.public_path, pattern) for page in pages.values()):
            continue
        findings.append(
            Finding(
                "noindex.pattern_unmatched",
                pattern,
                "configured noindex pattern matched no HTML pages",
            )
        )


def _validate_required_json_ld_patterns(
    pages: dict[str, Page], config: Config, findings: list[Finding]
) -> None:
    for pattern in config.required_json_ld_types:
        if any(_matches_path_pattern(page.public_path, pattern) for page in pages.values()):
            continue
        findings.append(
            Finding(
                "jsonld.pattern_unmatched",
                pattern,
                "configured required JSON-LD pattern matched no HTML pages",
            )
        )


def audit(site_root: Path, config: Config) -> tuple[list[Finding], dict[str, int]]:
    """Parse the rendered site once and return deterministic structural findings."""
    pages, files = _scan_pages(site_root)
    findings: list[Finding] = []
    if not pages:
        findings.append(Finding("site.no_html", ".", "site root contains no HTML files"))

    redirect_aliases = {
        **config.redirect_aliases,
        **_load_retained_redirects(site_root, config, findings),
    }
    _validate_alias_configuration(pages, files, config, redirect_aliases, findings)
    for page in pages.values():
        _validate_page(page, pages, files, config, redirect_aliases, findings)

    _validate_no_tracking(site_root, pages, files, config, findings)
    _validate_noindex_patterns(pages, config, findings)
    _validate_required_json_ld_patterns(pages, config, findings)
    _validate_duplicate_metadata(pages, config, redirect_aliases, findings)
    _validate_hreflang(pages, files, config, findings)
    _validate_sitemap(site_root, pages, config, redirect_aliases, findings)
    _validate_robots(site_root, config, findings)

    sorted_findings = sorted(set(findings))
    noindex_pages = sum(_is_noindex_path(page.public_path, config) for page in pages.values())
    canonical_aliases = sum(page.public_path in config.canonical_aliases for page in pages.values())
    redirect_alias_count = sum(page.public_path in redirect_aliases for page in pages.values())
    stats = {
        "canonical_aliases": canonical_aliases,
        "html_files": len(pages),
        "indexable_pages": (len(pages) - noindex_pages - redirect_alias_count - canonical_aliases),
        "noindex_pages": noindex_pages,
        "redirect_aliases": sum(bool(page.refreshes) for page in pages.values()),
    }
    return sorted_findings, stats


def _report(
    status: str,
    findings: list[Finding],
    errors: list[dict[str, str]],
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    counts = stats or {
        "canonical_aliases": 0,
        "html_files": 0,
        "indexable_pages": 0,
        "noindex_pages": 0,
        "redirect_aliases": 0,
    }
    return {
        "errors": errors,
        "findings": [
            {"code": item.code, "message": item.message, "path": item.path} for item in findings
        ],
        "schema_version": 1,
        "status": status,
        "summary": {
            **counts,
            "errors": len(errors),
            "findings": len(findings),
        },
    }


def _write_report(path: Path, report: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Could not write SEO report: {exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        report = _report("error", [], [{"code": "config.invalid", "message": str(exc)}])
        _write_report(args.report, report)
        print(f"SEO configuration error: {exc}", file=sys.stderr)
        return 2

    if not args.site_root.is_dir():
        message = f"site root does not exist or is not a directory: {args.site_root}"
        report = _report("error", [], [{"code": "site.invalid_root", "message": message}])
        _write_report(args.report, report)
        print(f"SEO site-root error: {message}", file=sys.stderr)
        return 2

    try:
        findings, stats = audit(args.site_root, config)
    except (OSError, UnicodeError) as exc:
        report = _report("error", [], [{"code": "site.unreadable", "message": str(exc)}])
        _write_report(args.report, report)
        print(f"SEO site-root error: {exc}", file=sys.stderr)
        return 2

    status = "fail" if findings else "pass"
    report = _report(status, findings, [], stats)
    if not _write_report(args.report, report):
        return 2
    if findings:
        print(f"Structural SEO checks failed ({len(findings)} findings).")
        return 1
    print(f"Structural SEO checks passed ({stats['html_files']} HTML files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
