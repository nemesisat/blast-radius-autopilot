"""Shared test setup.

The only thing here is a containment guard. `plan_mutations()` persists the Impact
Assessment body to disk (B18.3 — the catalog aspect it links from can hold only a URL
and a title, so the document has to live somewhere real). Its default location is the
project's `out/` directory, which also holds the CAPTURED evidence runs. Left alone,
every test that plans a mutation would drop synthetic-fixture assessments in there and
a reader could not tell fixture output from captured evidence.

So: for the whole test session, the default assessment directory points at a temp dir.
Tests that care about the path still pass one explicitly.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_assessment_dir(tmp_path_factory):
    import autopilot.writeback as wb

    original = wb.DEFAULT_ASSESSMENT_DIR
    wb.DEFAULT_ASSESSMENT_DIR = tmp_path_factory.mktemp("assessment-bodies")
    yield
    wb.DEFAULT_ASSESSMENT_DIR = original
