#!/usr/bin/env python3
"""No retirement publishes until a person has signed off on the risky ones.

A retirement (`alias_of` plus `feed_status: deprecated`) stops one record
publishing a current grade and sends its readers to another record's page. Most
of them come from the Mobility Database's own `redirect.id`, in batches of a
hundred and more, and the catalog cannot tell "this agency renamed itself" from
"these two records look alike". When it gets that wrong the site publishes one
agency's grade under another agency's name and in another agency's state, and
every other check still passes: both records are well-formed and the alias
chain resolves.

This gate re-derives the flags from the registry itself and fails while any
flagged retirement has no decision recorded in `supersession-review.yaml`, so
the class cannot ship by nobody noticing. It also fails when a decision no
longer matches the registry: a pairing that changed, a record kept separate but
retired anyway, or an entry left behind after the retirement went away.

Offline and deterministic; the catalog is not fetched. Run from the repo root
or anywhere:

    python3 pipeline/scripts/check_supersession_review.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "src"))

from scorecard_pipeline.agencies import read_agencies  # noqa: E402
from scorecard_pipeline.supersession_review import (  # noqa: E402
    REVIEW_FILENAME,
    read_review,
    recorded_retirements,
    review_problems,
)


def main() -> int:
    agencies = read_agencies()
    reviewed = read_review(REPO_ROOT)
    problems = review_problems(agencies, reviewed)
    if problems:
        print(f"Retirements that still need a decision in {REVIEW_FILENAME}:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nEach one sends readers from one agency's page to another's. Read the "
            "pair, then record the decision; do not clear this by removing the flag."
        )
        return 1
    retirements = len(recorded_retirements(agencies))
    print(
        f"{retirements} recorded retirements; {len(reviewed)} carry a decision in "
        f"{REVIEW_FILENAME}, and none is missing one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
