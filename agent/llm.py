
import json
import logging
import re
from decimal import Decimal

import httpx

from agent.config import GROQ_API_KEY, GROQ_MODEL, GROQ_URL
from agent.spec import GroupSpec


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
Extract stokvel group details from the user's message.

Return only JSON with these fields:
{
  "group_name": null,
  "contribution_lamports": null,
  "max_members": null
}

Rules:
- Convert SOL to lamports.
- 1 SOL = 1,000,000,000 lamports.
- Never invent missing information.
- max_members must be between 2 and 20.
"""


def fallback_extract(message: str, current: GroupSpec) -> GroupSpec:
    updates = {}

    # Extract the group name from common natural-language patterns.
    name_patterns = [
        r"\b(?:called|named)\s+(.+?)(?=\s+with\s+\d+\s+members?\b|[,.;]|$)",
        r"\b(?:group\s+name|name)\s+is\s+(.+?)(?=\s+with\s+\d+\s+members?\b|[,.;]|$)",
    ]

    for pattern in name_patterns:
        name_match = re.search(pattern, message, re.IGNORECASE)

        if name_match:
            group_name = name_match.group(1).strip().strip(chr(34) + chr(39))

            if group_name:
                updates["group_name"] = group_name
                break

    member_match = re.search(
        r"\b(\d+)\s+members?\b",
        message,
        re.IGNORECASE,
    )

    if member_match:
        updates["max_members"] = int(member_match.group(1))

    contribution_match = re.search(
        r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*SOL\b",
        message,
        re.IGNORECASE,
    )

    if contribution_match:
        sol_amount = Decimal(contribution_match.group(1))
        lamports = sol_amount * Decimal("1000000000")

        if lamports == lamports.to_integral_value():
            updates["contribution_lamports"] = int(lamports)

    if re.search(r"\bhalf\s+a\s+SOL\b", message, re.IGNORECASE):
        updates["contribution_lamports"] = 500_000_000

    # Accept standalone names, but reject conversational responses.
    if current.group_name is None and "group_name" not in updates:
        is_structured_update = bool(
            re.search(
                r"\b\d+\s+members?\b|"
                r"(?<![\w.])-?\d+(?:\.\d+)?\s*SOL\b|"
                r"\bhalf\s+a\s+SOL\b",
                message,
                re.IGNORECASE,
            )
        )

        candidate = message.strip()
        normalized_candidate = re.sub(
            r"[.!?,]+$",
            "",
            candidate,
        ).strip().casefold()

        ambiguous_responses = {
            "hello",
            "hi",
            "hey",
            "i don't know",
            "i do not know",
            "maybe",
            "not sure",
            "i'm not sure",
            "im not sure",
            "okay",
            "ok",
            "yes",
            "no",
            "thanks",
            "thank you",
        }

        if (
            candidate
            and len(candidate) <= 60
            and not is_structured_update
            and normalized_candidate not in ambiguous_responses
        ):
            updates["group_name"] = candidate

    # Merge existing information with newly extracted information.
    # model_validate ensures that all values are checked.
    return GroupSpec.model_validate({
        **current.model_dump(),
        **updates,
    })


async def extract_group_spec(
    message: str,
    current: GroupSpec,
) -> GroupSpec:

    # No API key? Use local extraction.
    if not GROQ_API_KEY:
        return fallback_extract(message, current)

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GROQ_URL,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        extracted = json.loads(content)

        if not isinstance(extracted, dict):
            raise ValueError("Groq returned an invalid JSON structure")

        allowed_fields = {
            "group_name",
            "contribution_lamports",
            "max_members",
        }

        updates = {
            key: value
            for key, value in extracted.items()
            if key in allowed_fields and value is not None
        }

        # Validate Groq's extracted information.
        return GroupSpec.model_validate({
            **current.model_dump(),
            **updates,
        })

    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:

        # Log the failure without exposing credentials.
        logger.warning(
            "Groq extraction failed (%s). Using local fallback.",
            type(exc).__name__,
        )

        return fallback_extract(message, current)
