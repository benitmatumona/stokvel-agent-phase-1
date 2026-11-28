import hashlib
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class GroupSpec(BaseModel):
    group_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    group_name: str | None = None
    contribution_lamports: int | None = None
    max_members: int | None = None
    currency: Literal["SOL"] = "SOL"
    payout_order: Literal["fixed"] = "fixed"

    @model_validator(mode="after")
    def validate_group(self):
        if self.contribution_lamports is not None:
            if self.contribution_lamports <= 0:
                raise ValueError("Contribution must be greater than zero")

        if self.max_members is not None:
            if not 2 <= self.max_members <= 20:
                raise ValueError("Group size must be between 2 and 20")

        return self

    @property
    def is_complete(self) -> bool:
        return (
            self.contribution_lamports is not None
            and self.max_members is not None
        )

    def rules_hash(self) -> str:
        """SHA-256 fingerprint of the agreed rules (what gets recorded on-chain)."""
        rules = {
            "group_id": self.group_id,
            "contribution_lamports": self.contribution_lamports,
            "max_members": self.max_members,
            "currency": self.currency,
            "payout_order": self.payout_order,
        }
        canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def summary(self) -> str:
        """Plain-language description generated only from the spec fields."""
        if not self.is_complete:
            return "This group is not fully described yet."
        sol = f"{self.contribution_lamports / 1_000_000_000:g} SOL"
        pool = f"{self.contribution_lamports * self.max_members / 1_000_000_000:g} SOL"
        name = self.group_name or "This stokvel"
        return (
            f"{name} has {self.max_members} members. Each member pays {sol} "
            f"every round. When everyone has paid, one member receives the whole "
            f"pool of {pool}, in a fixed order, until every member has been paid "
            f"once. The organiser cannot withdraw the money, and the rules cannot "
            f"be changed after the group is created."
        )
