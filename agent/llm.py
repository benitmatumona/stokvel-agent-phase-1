
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


NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "a dozen": 12, "dozen": 12,
}
_NUM = r"(\d+|" + "|".join(sorted((re.escape(w) for w in NUMBER_WORDS), key=len, reverse=True)) + r")"
_PEOPLE = r"(?:members?|people|persons?|friends|participants|of us)"
_NAME_END = r"(?=\s+(?:with|for|and|where|that|which|each|every|who)\b|[,.;!?]|$)"
CHATTER = {
    "you", "your", "me", "my", "i", "we", "us", "hear", "know", "hello", "hi",
    "hey", "can", "could", "would", "don't", "dont", "how", "what", "why",
    "let", "please", "thanks", "thank", "yes", "no", "okay", "ok", "maybe",
    "again", "instead", "going", "gonna", "want", "need", "like", "test",
    "testing", "technician",
}


def _to_int(token: str) -> int | None:
    token = token.lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def fallback_extract(message: str, current: GroupSpec) -> GroupSpec:
    updates = {}

    # Explicit naming always wins, even over an earlier name.
    name_patterns = [
        r"\b(?:call|name)\s+(?:it|the\s+(?:group|stokvel))\s+[\"']?(.+?)[\"']?" + _NAME_END,
        r"\b(?:called|named)\s+[\"']?(.+?)[\"']?" + _NAME_END,
        r"\b(?:group\s+name|stokvel\s+name|name)\s+(?:is|should be)\s+[\"']?(.+?)[\"']?" + _NAME_END,
    ]
    for pattern in name_patterns:
        name_match = re.search(pattern, message, re.IGNORECASE)
        if name_match:
            group_name = name_match.group(1).strip().strip(chr(34) + chr(39))
            if group_name:
                updates["group_name"] = group_name
                break

    member_match = re.search(
        r"\b" + _NUM + r"\s+" + _PEOPLE + r"\b", message, re.IGNORECASE
    ) or re.search(
        r"\b(?:for|of)\s+" + _NUM + r"\s+(?:people|persons?|friends)\b",
        message, re.IGNORECASE,
    )
    if member_match:
        count = _to_int(member_match.group(1))
        if count is not None:
            updates["max_members"] = count

    contribution_match = re.search(
        r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*SOL\b",
        message,
        re.IGNORECASE,
    )
    amount = contribution_match.group(1) if contribution_match else None

    if amount is None:
        # Spoken amounts often omit the unit: "each contributing 0.01".
        loose = re.search(
            r"(?:each|per\s+(?:member|person)|contribut\w*|pay\w*|put(?:ting)?\s+in|deposit\w*)"
            r"\D{0,25}?(?<![\w.])(\d+(?:\.\d+)?)(?!\s*(?:members?|people|persons?|friends)\b)",
            message, re.IGNORECASE,
        ) or re.search(
            r"(?<![\w.])(\d+\.\d+|\d+)\s+(?:each|per\s+(?:member|person))\b",
            message, re.IGNORECASE,
        )
        if loose:
            amount = loose.group(1)

    if amount is not None:
        lamports = Decimal(amount) * Decimal("1000000000")
        if lamports == lamports.to_integral_value():
            updates["contribution_lamports"] = int(lamports)

    if re.search(r"\bhalf\s+a\s+SOL\b", message, re.IGNORECASE):
        updates["contribution_lamports"] = 500_000_000

    # Accept standalone names, but reject conversational responses.
    if current.group_name is None and "group_name" not in updates:
        is_structured_update = bool(
            re.search(
                r"\b\d+\s+members?\b|\b" + _NUM + r"\s+" + _PEOPLE + r"\b|"
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

        # A request such as "I want to start a savings group" is not a name.
        looks_like_request = bool(
            re.match(
                r"(i|we|can|could|would|please|help|make|create|start|set|build|"
                r"let's|lets|how|what|why|do|does|is|are|will)\b",
                normalized_candidate,
            )
        )

        words = re.findall(r"[a-z0-9']+", normalized_candidate)
        is_chatter = (
            candidate.endswith("?")
            or len(words) > 5
            or any(w in CHATTER for w in words)
            or "stokvel" in words and len(words) > 3
        )

        if (
            candidate
            and len(candidate) <= 40
            and not is_structured_update
            and not is_chatter
            and not looks_like_request
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
