from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import RegisterNamespaceRequest
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from video_generation.config import Settings


async def initialize_temporal():
    settings = Settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    try:
        await client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace=settings.temporal_namespace,
                workflow_execution_retention_period=Duration(seconds=7 * 86400),
            )
        )
    except RPCError as exc:
        if exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise
    print(f"Temporal namespace ready: {settings.temporal_namespace}")
