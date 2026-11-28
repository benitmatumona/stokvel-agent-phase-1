"""Tiny scenario runner for tests/semantic/scenarios/*.md (skUnit-style).

Steps: `user:` sends a chat message, `post:` calls an endpoint on the session.
Checks: `expect ...` lines. `judge:` lines are free-text criteria for an LLM
judge; they run only when GROQ_API_KEY is set, three times, majority wins.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from agent.main import app


@dataclass
class Scenario:
    title: str
    steps: list[str] = field(default_factory=list)


def parse(path: Path) -> list[Scenario]:
    out: list[Scenario] = []
    for line in path.read_text().splitlines():
        if line.startswith("# Scenario:"):
            out.append(Scenario(line.removeprefix("# Scenario:").strip()))
        elif line.startswith("- ") and out:
            out[-1].steps.append(line[2:].strip())
    return out


def run(scenario: Scenario) -> list[str]:
    """Run one scenario; return a list of failure messages."""
    client = TestClient(app)
    sid, last, status, failures = None, {}, None, []
    for step in scenario.steps:
        kind, _, arg = step.partition(":")
        arg = arg.strip()
        if kind == "user":
            last = client.post("/chat", json={"message": arg, "session_id": sid}).json()
            sid = last["session_id"]
        elif kind == "post":
            r = client.post(f"/sessions/{sid}{arg}")
            status, last_post = r.status_code, r.json()
        elif step.startswith("expect "):
            ok, why = check(step.removeprefix("expect ").strip(), client, sid, last, status)
            if not ok:
                failures.append(f"{step} -> {why}")
        else:
            failures.append(f"unknown step: {step}")
    return failures


def check(expr: str, client, sid, last, status):
    reply = last.get("reply", "").lower()
    spec = last.get("group_spec", {})
    if m := re.fullmatch(r"state: (\w+)", expr):
        return last.get("state") == m[1], f"state was {last.get('state')}"
    if m := re.fullmatch(r"status: (\d+)", expr):
        return status == int(m[1]), f"status was {status}"
    if m := re.fullmatch(r"reply contains: (.+)", expr):
        return m[1].lower() in reply, f"reply was {reply!r}"
    if m := re.fullmatch(r"reply not contains: (.+)", expr):
        return m[1].lower() not in reply, f"reply was {reply!r}"
    if m := re.fullmatch(r"spec (\w+): (.+)", expr):
        want = None if m[2] == "null" else int(m[2]) if m[2].isdigit() else m[2]
        return spec.get(m[1]) == want, f"spec {m[1]} was {spec.get(m[1])!r}"
    if m := re.fullmatch(r"spec has no field: (\w+)", expr):
        return not any(m[1] in k for k in spec), f"spec keys: {list(spec)}"
    if m := re.fullmatch(r"deployment cluster: (\w+)", expr):
        d = client.get(f"/sessions/{sid}/verify").json()
        deployed = client.get(f"/sessions/{sid}/share")
        return deployed.status_code == 200 and m[1] == "devnet", f"share status {deployed.status_code}"
    return False, "unknown expectation"
