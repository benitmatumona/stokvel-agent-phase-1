from enum import Enum

from pydantic import BaseModel, Field

from agent.spec import GroupSpec


class SessionState(str, Enum):
    DRAFTING = "drafting"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    DEPLOYED = "deployed"


class AgentSession(BaseModel):
    session_id: str
    state: SessionState = SessionState.DRAFTING
    spec: GroupSpec = Field(default_factory=GroupSpec)
    explicit_approval: bool = False
    tests_passed: bool = False
    test_report: dict | None = None
    deployment: dict | None = None

    @property
    def can_deploy(self) -> bool:
        return (
            self.state == SessionState.APPROVED
            and self.deployment is None
            and self.explicit_approval
            and self.tests_passed
            and self.spec.is_complete
        )
