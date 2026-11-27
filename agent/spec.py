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
