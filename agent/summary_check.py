"""Checks that the plain-language summary matches the spec before approval.

Deterministic facts are always checked. If a Groq key is set, an LLM judge is
also asked, using conditions generated from the spec. The LLM only judges
wording; it never decides whether money is safe.
"""
import re

import httpx

from agent import config
from agent.spec import GroupSpec


def conditions_from_spec(spec: GroupSpec) -> list[str]:
    sol = f"{spec.contribution_lamports / 1_000_000_000:g}"
    return [
        f"States that the group has {spec.max_members} members",
        f"States that each member pays {sol} SOL per round",
        "Says one member receives the whole pool each round, in a fixed order",
        "Says the organiser cannot withdraw the money",
        "Does not promise interest, profit or returns",
    ]


def deterministic_check(spec: GroupSpec, text: str) -> list[str]:
    """Return a list of problems (empty means the summary matches)."""
    problems = []
    if not spec.is_complete:
        return ["spec is incomplete"]
    numbers = {n for n in re.findall(r"\d+(?:\.\d+)?", text)}
    sol = f"{spec.contribution_lamports / 1_000_000_000:g}"
    pool = f"{spec.contribution_lamports * spec.max_members / 1_000_000_000:g}"
    for label, value in (("members", str(spec.max_members)), ("contribution", sol), ("pool", pool)):
        if value not in numbers:
            problems.append(f"{label} {value} missing from summary")
    if re.search(r"\b(interest|profit|guarantee[sd]?|returns?)\b", text, re.I):
        problems.append("summary promises returns")
    if "cannot withdraw" not in text.lower():
        problems.append("summary omits that the organiser cannot withdraw")
    return problems


async def llm_check(spec: GroupSpec, text: str) -> list[str] | None:
    """Ask the judge each condition. None means no judge is configured/reachable."""
    if not config.GROQ_API_KEY:
        return None
    prompt = (
        "Summary:\n" + text + "\n\nFor each numbered condition answer PASS or FAIL, "
        "one per line, nothing else.\n"
        + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(conditions_from_spec(spec)))
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                config.GROQ_URL,
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                json={"model": config.GROQ_MODEL, "temperature": 0,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            lines = r.json()["choices"][0]["message"]["content"].splitlines()
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    verdicts = [ln for ln in lines if re.search(r"\b(PASS|FAIL)\b", ln)]
    conds = conditions_from_spec(spec)
    return [c for c, v in zip(conds, verdicts) if "FAIL" in v.upper()]
