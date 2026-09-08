from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from video_generation.infrastructure.persistence.models import (
    OutboxRow,
    ServiceHeartbeatRow,
    new_id,
    utcnow,
)


class OutboxRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    async def claim(self, run_id=None):
        async with self.sessions() as session, session.begin():
            now = utcnow()
            query = select(OutboxRow).where(
                OutboxRow.status == "PENDING",
                OutboxRow.available_at <= now,
                or_(OutboxRow.lease_until.is_(None), OutboxRow.lease_until <= now),
            )
            if run_id:
                query = query.where(OutboxRow.run_id == run_id)
            row = await session.scalar(
                query.order_by(OutboxRow.created_at, OutboxRow.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.lease_token = new_id()
            row.lease_until = now + timedelta(seconds=30)
            row.attempts += 1
            await session.flush()
            return row

    async def finish(self, claimed, error=None):
        async with self.sessions() as session, session.begin():
            row = await session.get(
                OutboxRow, (claimed.tenant_id, claimed.id), with_for_update=True
            )
            if row is None or row.lease_token != claimed.lease_token:
                return
            now = utcnow()
            row.lease_token = None
            row.lease_until = None
            if error is None:
                row.status = "SENT"
                row.delivered_at = now
                row.error = None
            else:
                row.error = error[:2000]
                row.available_at = now + timedelta(seconds=min(60, 2 ** min(row.attempts, 6)))
                if now - row.created_at >= timedelta(hours=24):
                    row.status = "DEAD"


async def heartbeat(sessions, service, instance_id):
    async with sessions() as session, session.begin():
        statement = insert(ServiceHeartbeatRow).values(
            service=service, instance_id=instance_id, seen_at=utcnow()
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[ServiceHeartbeatRow.service, ServiceHeartbeatRow.instance_id],
                set_={"seen_at": statement.excluded.seen_at},
            )
        )
