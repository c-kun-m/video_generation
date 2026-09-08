from dataclasses import dataclass

from video_generation.contracts.models import Identity
from video_generation.domain.errors import DomainError


@dataclass(frozen=True)
class ActorContext:
    tenant_id: str
    actor_id: str
    session_id: str
    role: str
    identity: Identity

    def require_editor(self) -> None:
        if self.role not in {"owner", "editor"}:
            raise DomainError("FORBIDDEN", "当前身份没有编辑项目的权限。", 403)

    def require_reviewer(self) -> None:
        if self.role not in {"owner", "reviewer"}:
            raise DomainError("FORBIDDEN", "当前身份没有审批内容的权限。", 403)
