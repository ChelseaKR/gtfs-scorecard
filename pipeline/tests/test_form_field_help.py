"""Form help and form errors are tied to the fields they are about.

Two things a sighted reader gets from layout and a screen-reader user gets
only from markup (WCAG 1.3.1, 3.3.1, 3.3.2):

- A hint under a field ("A direct link to your GTFS .zip...") is read with
  that field only when the field names it in `aria-describedby`. Otherwise a
  person filling in the form field by field never hears it.
- An error message lives in one status line at the foot of the form. When a
  check fails the script moves focus to the field, and the message has to
  travel with it: the field names the status line in `aria-describedby` until
  the next check.

The first is read from the pages. The second is read from the scripts here
and driven in a browser by `tests/e2e/test_forms.py`.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
FORM_PAGES = ("submit.html", "subscribe.html", "try.html")
FORM_SCRIPTS = ("submit.js", "subscribe.js", "try.js")


class _FormHints(HTMLParser):
    """Collect each form's hint ids and every id a control says describes it."""

    def __init__(self) -> None:
        super().__init__()
        self.in_form = 0
        self.in_label = 0
        self.hints_without_id: list[str] = []
        self.hint_ids: list[str] = []
        self.described_by: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "form":
            self.in_form += 1
        if not self.in_form:
            return
        if tag == "label":
            self.in_label += 1
        if tag in {"input", "select", "textarea", "fieldset"}:
            self.described_by.update((attr.get("aria-describedby") or "").split())
        classes = (attr.get("class") or "").split()
        # A hint inside a <label> is already part of the field's name.
        if "hint" in classes and not self.in_label:
            if attr.get("id"):
                self.hint_ids.append(str(attr["id"]))
            else:
                self.hints_without_id.append(self.get_starttag_text() or tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self.in_label:
            self.in_label -= 1
        if tag == "form" and self.in_form:
            self.in_form -= 1


@pytest.mark.parametrize("page", FORM_PAGES)
def test_every_form_hint_is_named_by_a_field(page: str) -> None:
    parser = _FormHints()
    parser.feed((WEB / page).read_text(encoding="utf-8"))
    assert not parser.hints_without_id, (
        f"{page}: a hint has no id, so no field can point to it: {parser.hints_without_id}"
    )
    orphans = [hint for hint in parser.hint_ids if hint not in parser.described_by]
    assert not orphans, f"{page}: no field's aria-describedby names these hints: {orphans}"


def test_the_submission_form_has_hints_to_tie() -> None:
    # Guards the test above against passing because it found nothing.
    parser = _FormHints()
    parser.feed((WEB / "submit.html").read_text(encoding="utf-8"))
    assert len(parser.hint_ids) >= 4


@pytest.mark.parametrize("script", FORM_SCRIPTS)
def test_an_error_message_travels_with_the_field_it_is_about(script: str) -> None:
    source = (WEB / "src" / script).read_text(encoding="utf-8")
    flag = re.search(r"function flagInvalid\(field\) \{(.*?)\n\}", source, flags=re.S)
    assert flag, f"{script}: no flagInvalid helper"
    body = flag.group(1)
    assert 'setAttribute("aria-invalid", "true")' in body
    assert "status.id" in body and 'setAttribute("aria-describedby"' in body
    # Every place that marks a field invalid goes through the helper, so no
    # error path can mark a field and leave the message behind.
    assert source.count('setAttribute("aria-invalid", "true")') == 1
    clear = re.search(r"function clearInvalid\(\) \{(.*?)\n\}", source, flags=re.S)
    assert clear and "status.id" in clear.group(1), (
        f"{script}: a corrected field must stop pointing at the status line"
    )
