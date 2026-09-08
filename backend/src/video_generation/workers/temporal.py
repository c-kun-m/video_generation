import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from video_generation.config import Settings
from video_generation.infrastructure.persistence.database import create_database
from video_generation.infrastructure.persistence.models import new_id
from video_generation.infrastructure.persistence.outbox import heartbeat
from video_generation.orchestration.activities import ProductionActivities
from video_generation.orchestration.production import SimulationProductionWorkflow

log = logging.getLogger("video.worker")


async def run_worker(settings=None):
    settings = settings or Settings()
    engine, sessions = create_database(settings)
    instance_id = new_id()

    async def report_presence(client):
        while True:
            try:
                await client.service_client.check_health()
                await heartbeat(sessions, "worker", instance_id)
            except Exception as exc:
                log.warning("worker_health_failed reason=%s", type(exc).__name__)
            await asyncio.sleep(10)

    presence = None
    try:
        while True:
            try:
                client = await Client.connect(
                    settings.temporal_address, namespace=settings.temporal_namespace
                )
                break
            except (RuntimeError, OSError) as exc:
                log.warning("worker_connection_retry reason=%s", type(exc).__name__)
                await asyncio.sleep(5)
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[SimulationProductionWorkflow],
            activities=[ProductionActivities(sessions, settings).transition],
            max_concurrent_activities=10,
            max_concurrent_workflow_tasks=10,
            graceful_shutdown_timeout=timedelta(seconds=10),
        )
        presence = asyncio.create_task(report_presence(client))
        await worker.run()
    finally:
        if presence:
            presence.cancel()
            with suppress(asyncio.CancelledError):
                await presence
        await engine.dispose()
