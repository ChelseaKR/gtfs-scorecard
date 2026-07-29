"""Subprocess tests for the deterministic structural SEO gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "pipeline" / "scripts" / "check_site_seo.py"
ORIGIN = "https://example.test"


def _page(
    public_path: str,
    title: str,
    description: str,
    *,
    body: str,
    canonical_path: str | None = None,
    extra_head: str = "",
    h1: str | None = "Page heading",
    language: str = "en",
    noindex: bool = False,
    og_url: str | None = None,
) -> str:
    canonical = f"{ORIGIN}{canonical_path or public_path}"
    social_url = og_url or canonical
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    heading = f"<h1>{h1}</h1>" if h1 is not None else ""
    return f"""<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{social_url}">
  <meta property="og:image" content="{ORIGIN}/og.png">
  {robots}
  {extra_head}
</head>
<body>{heading}{body}</body>
</html>
"""


def _write_text(site: Path, relative: str, content: str) -> None:
    path = site / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "site_origin": ORIGIN,
        "sitemap_path": "sitemap.xml",
        "robots_path": "robots.txt",
        "fragment_exempt_prefixes": ["/app/"],
        "noindex_path_patterns": [
            "/agency/*/board/",
            "/agency/*/brief/",
        ],
        "canonical_aliases": {"/app/": "/agencies/"},
        "hreflang_groups": [{"en": "/", "es": "/es/"}],
        "required_json_ld_types": {"/agency/*/": ["Dataset"]},
        "redirect_aliases": {
            "/old/": "/target/?view=all#section",
        },
    }


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    site = tmp_path / "site"
    en_alternates = (
        f'<link rel="alternate" hreflang="en" href="{ORIGIN}/">'
        f'<link rel="alternate" hreflang="es" href="{ORIGIN}/es/">'
    )
    es_alternates = (
        f'<link rel="alternate" hreflang="en" href="{ORIGIN}/">'
        f'<link rel="alternate" hreflang="es" href="{ORIGIN}/es/">'
    )
    _write_text(
        site,
        "index.html",
        _page(
            "/",
            "Home title",
            "Home description",
            extra_head=(
                en_alternates + '<script type="application/ld+json">'
                '{"@context":"https://schema.org","@type":"WebSite",'
                '"dateModified":"2026-07-29"}</script>'
            ),
            body=(
                '<a href="/target/#section">Target section</a>'
                '<a href="/app/#/agency/demo">SPA route</a>'
                '<form action="/target/?from=form"></form>'
                '<script src="/app.js"></script>'
            ),
        ),
    )
    _write_text(
        site,
        "es/index.html",
        _page(
            "/es/",
            "Inicio",
            "Descripción en español",
            extra_head=es_alternates,
            body='<a href="/">English</a>',
            language="es",
        ),
    )
    _write_text(
        site,
        "agencies/index.html",
        _page(
            "/agencies/",
            "Agency directory",
            "Agency directory description",
            body='<a href="/agency/demo/">Demo agency</a>',
        ),
    )
    _write_text(
        site,
        "app/index.html",
        _page(
            "/app/",
            "Interactive agency search",
            "Interactive search description",
            canonical_path="/agencies/",
            og_url=f"{ORIGIN}/agencies/",
            h1=None,
            body='<a href="/app/#/agency/demo">Open demo</a>',
        ),
    )
    for relative, public_path, noindex in (
        ("agency/demo/index.html", "/agency/demo/", False),
        ("agency/demo/board/index.html", "/agency/demo/board/", True),
        ("agency/demo/brief/index.html", "/agency/demo/brief/", True),
    ):
        _write_text(
            site,
            relative,
            _page(
                public_path,
                "Repeated agency metadata",
                "Repeated agency description",
                noindex=noindex,
                extra_head=(
                    ""
                    if noindex
                    else (
                        '<script type="application/ld+json">'
                        '{"@context":"https://schema.org","@type":"Dataset",'
                        f'"url":"{ORIGIN}/agency/demo/"'
                        "}</script>"
                    )
                ),
                body='<a href="/agencies/">Directory</a>',
            ),
        )
    _write_text(
        site,
        "target/index.html",
        _page(
            "/target/",
            "Target title",
            "Target description",
            body=(
                '<section id="section">Target</section><svg><title>Inline map feature</title></svg>'
            ),
        ),
    )
    redirect_target = "/target/?view=all#section"
    _write_text(
        site,
        "old/index.html",
        f"""<!doctype html>
<html lang="en"><head>
<title>Moved page</title>
<meta http-equiv="refresh" content="0; url={redirect_target}">
<link rel="canonical" href="{ORIGIN}/target/?view=all">
</head><body><h1>Moved</h1><a href="{redirect_target}">Continue</a></body></html>
""",
    )
    (site / "app.js").write_text("/* fixture */\n", encoding="utf-8")
    (site / "og.png").write_bytes(b"png")
    sitemap_urls = (
        "/",
        "/agencies/",
        "/agency/demo/",
        "/es/",
        "/target/",
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(
            f"<url><loc>{ORIGIN}{url}</loc><lastmod>2026-07-29</lastmod></url>"
            for url in sitemap_urls
        )
        + "</urlset>\n"
    )
    (site / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (site / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n",
        encoding="utf-8",
    )
    config = tmp_path / "site-seo.json"
    config.write_text(json.dumps(_config()), encoding="utf-8")
    return site, config


def _run(
    site: Path,
    config: Path,
    report: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-owned paths
        [
            sys.executable,
            str(CHECKER),
            "--site-root",
            str(site),
            "--config",
            str(config),
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _codes(report: Path) -> set[str]:
    payload = json.loads(report.read_text(encoding="utf-8"))
    return {item["code"] for item in payload["findings"]}


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_valid_site_passes_with_deterministic_report_and_canonical_alias(
    tmp_path: Path,
) -> None:
    site, config = _write_fixture(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_result = _run(site, config, first)
    second_result = _run(site, config, second)

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["status"] == "pass"
    assert payload["summary"] == {
        "canonical_aliases": 1,
        "errors": 0,
        "findings": 0,
        "html_files": 9,
        "indexable_pages": 5,
        "noindex_pages": 2,
        "redirect_aliases": 1,
    }


def test_reports_local_references_fragments_and_duplicate_ids(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</body>",
        (
            '<a href="/missing/">Broken link</a>'
            '<a href="/target/#absent">Broken fragment</a>'
            '<form action="/missing-form/"></form>'
            '<script src="/missing.js"></script>'
            '<div id="duplicate"></div><span id="duplicate"></span></body>'
        ),
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {
        "asset.missing_target",
        "form.missing_target",
        "fragment.missing",
        "html.duplicate_id",
        "link.missing_target",
    } <= _codes(report)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/app.js",
        "http://example.test:80/app.js",
    ],
)
def test_same_site_http_asset_is_rejected(tmp_path: Path, url: str) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        '<script src="/app.js"></script>',
        f'<script src="{url}"></script>',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "asset.insecure_same_site" in _codes(report)


def test_non_hreflang_alternate_link_remains_an_asset_check(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</head>",
        '<link rel="alternate" type="application/atom+xml" href="/missing-feed.xml"></head>',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "asset.missing_target" in _codes(report)


def test_srcset_data_url_does_not_create_a_bogus_local_asset(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</body>",
        '<img alt="" srcset="data:image/png;base64,AAAA 1x, /og.png 2x"></body>',
    )
    report = tmp_path / "report.json"

    assert _run(site, config, report).returncode == 0


def test_srcset_still_checks_non_data_candidates(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</body>",
        '<img alt="" srcset="/og.png 1x, /missing.png 2x"></body>',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "asset.missing_target" in _codes(report)


def test_no_tracking_contract_rejects_analytics_loader_asset_and_file(
    tmp_path: Path,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</head>",
        '<script src="/analytics.js"></script></head>',
    )
    _write_text(site, "analytics.js", "/* tracking loader placeholder */\n")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {
        "privacy.telemetry_asset",
        "privacy.telemetry_file",
    } <= _codes(report)


def test_no_tracking_contract_rejects_known_telemetry_hosts(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "index.html",
        "</head>",
        (
            '<script src="https://www.googletagmanager.com/gtag/js?id=G-TEST"></script>'
            "<script>fetch('https://www.google-analytics.com/collect')</script>"
            "</head>"
        ),
    )
    _write_text(
        site,
        "telemetry.js",
        'fetch("https://region1.google-analytics.com/collect");\n',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {
        "privacy.telemetry_asset",
        "privacy.telemetry_script",
    } <= _codes(report)


def test_metadata_noindex_and_duplicate_metadata_findings(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "agencies/index.html",
        "<title>Agency directory</title>",
        "<title>Home title</title>",
    )
    _replace(
        site / "agencies/index.html",
        'content="Agency directory">',
        'content="Home title">',
    )
    _replace(
        site / "agencies/index.html",
        "Agency directory description",
        "Home description",
    )
    _replace(
        site / "agency/demo/board/index.html",
        '<meta name="robots" content="noindex,follow">',
        "",
    )
    _replace(
        site / "app/index.html",
        f'<meta property="og:url" content="{ORIGIN}/agencies/">',
        f'<meta property="og:url" content="{ORIGIN}/app/">',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {
        "metadata.duplicate_description",
        "metadata.duplicate_title",
        "metadata.og_url_mismatch",
        "noindex.missing",
    } <= _codes(report)


@pytest.mark.parametrize("omit_head_close", [False, True])
def test_seo_elements_outside_head_are_rejected(
    tmp_path: Path,
    omit_head_close: bool,
) -> None:
    site, config = _write_fixture(tmp_path)
    misplaced = (
        '<meta http-equiv="refresh" content="0; url=/target/">'
        f'<link rel="canonical" href="{ORIGIN}/target/">'
        '<meta name="robots" content="noindex,follow">'
        f'<link rel="alternate" hreflang="en" href="{ORIGIN}/">'
    )
    if omit_head_close:
        _replace(site / "index.html", "</head>\n<body>", f"<body>{misplaced}")
    else:
        _replace(site / "index.html", "</body>", f"{misplaced}</body>")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "html.seo_outside_head" in _codes(report)


def test_second_head_inside_body_cannot_satisfy_metadata_contract(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    page = site / "index.html"
    content = page.read_text(encoding="utf-8")
    content = content.replace("<head>", "<head></head><body><head>", 1)
    content = content.replace("</head>\n<body>", "</head>", 1)
    page.write_text(content, encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    codes = _codes(report)
    assert "html.seo_outside_head" in codes
    assert "metadata.canonical_missing" in codes
    assert "metadata.description_missing" in codes
    assert "metadata.title_missing" in codes


def test_redirect_canonical_preserves_query_but_drops_fragment(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    passing_report = tmp_path / "passing.json"
    assert _run(site, config, passing_report).returncode == 0

    _replace(
        site / "old/index.html",
        f'<link rel="canonical" href="{ORIGIN}/target/?view=all">',
        f'<link rel="canonical" href="{ORIGIN}/target/">',
    )
    report = tmp_path / "report.json"
    result = _run(site, config, report)

    assert result.returncode == 1
    assert "redirect.canonical_target" in _codes(report)


def test_redirect_refresh_and_fallback_keep_full_target(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "old/index.html",
        'content="0; url=/target/?view=all#section"',
        'content="0; url=/target/?view=all"',
    )
    _replace(
        site / "old/index.html",
        'href="/target/?view=all#section">Continue',
        'href="/target/?view=all">Continue',
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {"redirect.fallback_target", "redirect.refresh_target"} <= _codes(report)


@pytest.mark.parametrize(
    ("relative_path", "old", "new", "expected_code"),
    [
        (
            "index.html",
            "</head>",
            '<script type="application/ld+json">{"value":NaN}</script></head>',
            "jsonld.malformed",
        ),
        (
            "index.html",
            "</head>",
            '<script type="application/ld+json">{not-json}</script></head>',
            "jsonld.malformed",
        ),
        (
            "index.html",
            "</head>",
            ('<script type="application/ld+json">{"dateModified":"2026-02-30"}</script></head>'),
            "jsonld.invalid_date",
        ),
        (
            "sitemap.xml",
            "<lastmod>2026-07-29</lastmod>",
            "<lastmod>2026-02-30</lastmod>",
            "sitemap.invalid_lastmod",
        ),
        (
            "robots.txt",
            f"Sitemap: {ORIGIN}/sitemap.xml",
            f"Sitemap: {ORIGIN}/wrong.xml",
            "robots.sitemap_pointer",
        ),
        (
            "es/index.html",
            f'<link rel="alternate" hreflang="en" href="{ORIGIN}/">',
            "",
            "hreflang.not_reciprocal",
        ),
    ],
)
def test_structured_metadata_and_discovery_failures(
    tmp_path: Path,
    relative_path: str,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / relative_path, old, new)
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert expected_code in _codes(report)


def test_sitemap_requires_exact_indexable_canonical_parity(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(
        site / "sitemap.xml",
        f"<url><loc>{ORIGIN}/target/</loc><lastmod>2026-07-29</lastmod></url>",
        f"<url><loc>{ORIGIN}/old/</loc><lastmod>2026-07-29</lastmod></url>",
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {"sitemap.missing_url", "sitemap.unexpected_url"} <= _codes(report)


@pytest.mark.parametrize(
    "namespace",
    ["", "https://example.test/not-the-sitemap-protocol"],
)
def test_sitemap_requires_protocol_namespace(
    tmp_path: Path,
    namespace: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    declaration = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    replacement = f'xmlns="{namespace}"' if namespace else ""
    _replace(site / "sitemap.xml", declaration, replacement)
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "sitemap.root" in _codes(report)


@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        (
            (
                f'<link rel="alternate" hreflang="en" href="{ORIGIN}/">'
                f'<link rel="alternate" hreflang="es" href="{ORIGIN}/es/">'
            ),
            "",
            "hreflang.required_alternate",
        ),
        (
            "</head>",
            f'<link rel="alternate" hreflang="fr" href="{ORIGIN}/"></head>',
            "hreflang.unexpected_alternate",
        ),
        (
            "</head>",
            f'<link rel="alternate" hreflang="es" href="{ORIGIN}/"></head>',
            "hreflang.required_alternate",
        ),
        (
            f'hreflang="es" href="{ORIGIN}/es/"',
            'hreflang="es" href="/es/"',
            "hreflang.required_alternate",
        ),
        (
            f'hreflang="es" href="{ORIGIN}/es/"',
            'hreflang="es" href="http://example.test/es/"',
            "hreflang.required_alternate",
        ),
    ],
)
def test_configured_hreflang_cluster_is_exact(
    tmp_path: Path,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / "index.html", old, new)
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert expected_code in _codes(report)


@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        (
            (
                '<script type="application/ld+json">'
                '{"@context":"https://schema.org","@type":"Dataset",'
                f'"url":"{ORIGIN}/agency/demo/"'
                "}</script>"
            ),
            "",
            "jsonld.required_type_missing",
        ),
        (
            '"@context":"https://schema.org"',
            '"@context":"https://example.org"',
            "jsonld.required_context",
        ),
        (
            f'"url":"{ORIGIN}/agency/demo/"',
            f'"url":"{ORIGIN}/agency/wrong/"',
            "jsonld.required_url",
        ),
    ],
)
def test_required_agency_dataset_has_schema_identity(
    tmp_path: Path,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / "agency/demo/index.html", old, new)
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert expected_code in _codes(report)


def test_required_json_ld_pattern_must_match_a_page(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["required_json_ld_types"] = {"/agenciez/*/": ["Dataset"]}
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "jsonld.pattern_unmatched" in _codes(report)


def test_indexable_agency_pages_are_checked_for_duplicate_metadata(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _write_text(
        site,
        "agency/twin/index.html",
        _page(
            "/agency/twin/",
            "Repeated agency metadata",
            "Repeated agency description",
            extra_head=(
                '<script type="application/ld+json">'
                '{"@context":"https://schema.org","@type":"Dataset",'
                f'"url":"{ORIGIN}/agency/twin/"'
                "}</script>"
            ),
            body='<a href="/agencies/">Directory</a>',
        ),
    )
    _replace(
        site / "sitemap.xml",
        "</urlset>",
        (f"<url><loc>{ORIGIN}/agency/twin/</loc><lastmod>2026-07-29</lastmod></url></urlset>"),
    )
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert {
        "metadata.duplicate_description",
        "metadata.duplicate_title",
    } <= _codes(report)


@pytest.mark.parametrize("cycle", [False, True], ids=["chain", "cycle"])
def test_alias_targets_must_be_terminal_in_config(tmp_path: Path, cycle: bool) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["canonical_aliases"]["/app/"] = "/old/"
    if cycle:
        payload["redirect_aliases"]["/old/"] = "/app/"
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 2
    error_report = json.loads(report.read_text(encoding="utf-8"))
    assert error_report["errors"][0]["code"] == "config.invalid"


@pytest.mark.parametrize(
    ("insertion", "expected_code"),
    [
        ('<meta name="robots" content="noindex,follow">', "alias.target_noindex"),
        ('<meta http-equiv="refresh" content="0; url=/target/">', "alias.target_redirect"),
    ],
)
def test_alias_target_must_be_indexable_and_terminal_in_rendered_site(
    tmp_path: Path,
    insertion: str,
    expected_code: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / "agencies/index.html", "</head>", f"{insertion}</head>")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert expected_code in _codes(report)


@pytest.mark.parametrize("target", ["/app/index.html", "/agencies"])
def test_alias_target_must_use_exact_rendered_public_path(
    tmp_path: Path,
    target: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["canonical_aliases"]["/app/"] = target
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "alias.target_noncanonical_path" in _codes(report)


@pytest.mark.parametrize("disallow", ["/", "/*", "/*$"])
def test_robots_must_not_disallow_the_whole_site(
    tmp_path: Path,
    disallow: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / "robots.txt", "Allow: /", f"Disallow: {disallow}")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 1
    assert "robots.disallow_all" in _codes(report)


def test_robots_equal_allow_rule_wins(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    _replace(site / "robots.txt", "Allow: /", "Disallow: /\nAllow: /")
    report = tmp_path / "report.json"

    assert _run(site, config, report).returncode == 0


def test_only_ids_and_legacy_anchor_names_define_fragments(tmp_path: Path) -> None:
    bad_site, bad_config = _write_fixture(tmp_path / "bad")
    _replace(
        bad_site / "target/index.html",
        "</body>",
        '<meta name="ghost"><a href="#ghost">Ghost</a></body>',
    )
    bad_report = tmp_path / "bad-report.json"

    bad_result = _run(bad_site, bad_config, bad_report)

    assert bad_result.returncode == 1
    assert "fragment.missing" in _codes(bad_report)

    good_site, good_config = _write_fixture(tmp_path / "good")
    _replace(
        good_site / "target/index.html",
        "</body>",
        '<a name="legacy"></a><a href="#legacy">Legacy</a></body>',
    )
    good_report = tmp_path / "good-report.json"

    assert _run(good_site, good_config, good_report).returncode == 0


def test_strict_config_error_writes_schema_v1_report(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["unknown"] = True
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 2
    error_report = json.loads(report.read_text(encoding="utf-8"))
    assert error_report["schema_version"] == 1
    assert error_report["status"] == "error"
    assert error_report["errors"][0]["code"] == "config.invalid"


def test_hreflang_config_rejects_casefolded_duplicate_languages(tmp_path: Path) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["hreflang_groups"] = [{"en": "/", "EN": "/es/"}]
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 2
    assert json.loads(report.read_text(encoding="utf-8"))["errors"][0]["code"] == "config.invalid"


@pytest.mark.parametrize(
    "origin",
    [
        "https://[",
        "https://example.test:notaport",
        "https://:443",
        "https://bad host.example",
    ],
)
def test_malformed_site_origin_is_a_reported_config_error(
    tmp_path: Path,
    origin: str,
) -> None:
    site, config = _write_fixture(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["site_origin"] = origin
    config.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"

    result = _run(site, config, report)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    error_report = json.loads(report.read_text(encoding="utf-8"))
    assert error_report["errors"][0]["code"] == "config.invalid"


def test_invalid_root_writes_error_report_and_report_write_error_exits_two(
    tmp_path: Path,
) -> None:
    site, config = _write_fixture(tmp_path)
    missing_root_report = tmp_path / "missing-root.json"

    invalid_root = _run(tmp_path / "missing", config, missing_root_report)

    assert invalid_root.returncode == 2
    assert json.loads(missing_root_report.read_text(encoding="utf-8"))["status"] == "error"

    report_directory = tmp_path / "report-directory"
    report_directory.mkdir()
    report_error = _run(site, config, report_directory)
    assert report_error.returncode == 2
    assert "Could not write SEO report" in report_error.stderr


def test_repository_config_keeps_aliases_and_exemptions_narrow() -> None:
    config = json.loads((ROOT / "site-seo.json").read_text(encoding="utf-8"))

    assert "duplicate_metadata_exempt_prefixes" not in config
    assert config["fragment_exempt_prefixes"] == ["/app/"]
    assert config["canonical_aliases"] == {"/app/": "/agencies/"}
    assert config["hreflang_groups"] == [{"en": "/", "es": "/es/"}]
    assert config["required_json_ld_types"] == {"/agency/*/": ["Dataset"]}
    assert config["redirect_aliases"] == {
        "/access/": "/adoption/#access",
        "/changes/": "/pulse/#changes",
        "/concept/": "/how-to-read/",
        "/leaderboard/": "/pulse/#changes",
        "/trends/": "/pulse/#trend",
    }
