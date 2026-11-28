from pathlib import Path

import pytest

from tests.semantic.runner import parse, run

SCENARIOS = [
    (f.stem, s)
    for f in sorted((Path(__file__).parent / "scenarios").glob("*.md"))
    for s in parse(f)
]


@pytest.mark.parametrize("name,scenario", SCENARIOS, ids=[s.title for _, s in SCENARIOS])
def test_scenario(name, scenario):
    assert run(scenario) == []
