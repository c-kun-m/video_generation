from temporalio import activity
from temporalio.exceptions import ApplicationError

from video_generation.application.simulation import SimulationService
from video_generation.config import Settings
from video_generation.domain.errors import DomainError
from video_generation.orchestration.messages import StepRequest, StepResponse
from video_generation.workers.faults import crash_if_selected


class ProductionActivities:
    def __init__(self, sessions, settings: Settings | None = None):
        self.service = SimulationService(sessions)
        self.settings = settings or Settings()

    @activity.defn(name="simulation_transition_v1")
    async def transition(self, request: StepRequest) -> StepResponse:
        try:
            result = await self.service.transition(request)
            crash_if_selected(self.settings, "activity_after_commit", request.operation_id)
            return result
        except DomainError as exc:
            raise ApplicationError(str(exc), type=exc.detail.code, non_retryable=True) from exc
