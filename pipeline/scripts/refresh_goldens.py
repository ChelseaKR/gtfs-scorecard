"""Refresh deterministic static-site goldens from the committed fixture."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    pipeline = Path(__file__).resolve().parents[1]
    fixture = pipeline / "tests" / "fixtures" / "golden_site"
    goldens = pipeline / "tests" / "goldens"
    report_goldens = goldens / "report"

    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = Path(tmpdir) / "golden_site"
        shutil.copytree(fixture, scratch)
        os.environ["SCORECARD_ROOT"] = str(scratch)

        from scorecard_pipeline.render_site import render_site

        liveness = json.loads((scratch / "data" / "liveness.json").read_text())
        checked = [
            dt.datetime.fromisoformat(str(feed["checked_at"]))
            for feed in liveness.get("feeds", {}).values()
            if feed.get("checked_at")
        ]
        now = (max(checked) if checked else dt.datetime.now(dt.UTC)) + dt.timedelta(hours=2)
        written = render_site(now=now)

        preserved_reports: Path | None = None
        if report_goldens.exists():
            preserved_reports = Path(tmpdir) / "report"
            shutil.copytree(report_goldens, preserved_reports)
        shutil.rmtree(goldens)
        goldens.mkdir(parents=True)
        web = scratch / "web"
        for source in written:
            target = goldens / source.relative_to(web)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if preserved_reports is not None:
            shutil.copytree(preserved_reports, report_goldens)

    print(f"refreshed {len(written)} rendered golden files")


if __name__ == "__main__":
    main()
