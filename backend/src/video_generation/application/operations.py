from sqlalchemy import func, select

from video_generation.contracts.content import OutboxStatus
from video_generation.infrastructure.persistence.models import OutboxRow, ServiceHeartbeatRow


async def execution_status(sessions, actor):
    async with sessions() as session:
        counts = dict(
            (
                await session.execute(
                    select(OutboxRow.status, func.count())
                    .where(
                        OutboxRow.tenant_id == actor.tenant_id,
                    )
                    .group_by(OutboxRow.status)
                )
            ).all()
        )

        async def latest(service):
            value = await session.scalar(
                select(func.max(ServiceHeartbeatRow.seen_at)).where(
                    ServiceHeartbeatRow.service == service,
                )
            )
            return value.isoformat() if value else None

        return OutboxStatus(
            pending=counts.get("PENDING", 0),
            dead_letters=counts.get("DEAD", 0),
            last_worker_seen_at=await latest("worker"),
            last_dispatcher_seen_at=await latest("dispatcher"),
        )
