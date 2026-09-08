import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

from video_generation.orchestration.messages import ProductionInput, StepRequest, StepResponse

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}


@workflow.defn(name="SimulationProductionWorkflowV1")
class SimulationProductionWorkflow:
    def __init__(self):
        self.notifications = 0
        self.cancel_notified = False

    @workflow.signal(name="business_event")
    def business_event(self, event: dict):
        self.notifications += 1
        if event.get("action") == "cancel":
            self.cancel_notified = True

    async def transition(self, execution: ProductionInput, action: str, **kwargs) -> StepResponse:
        return await workflow.execute_activity(
            "simulation_transition_v1",
            StepRequest(execution, action, workflow.info().run_id, **kwargs),
            result_type=StepResponse,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=30)
            ),
        )

    async def checkpoint(self, execution: ProductionInput) -> StepResponse:
        while True:
            observed = self.notifications
            state = await self.transition(execution, "checkpoint")
            if state.status != "PAUSED":
                return state
            try:
                # The timer also repairs missed wake-ups without keeping a DB connection.
                await workflow.wait_condition(
                    lambda observed=observed: self.notifications != observed,
                    timeout=timedelta(seconds=30),
                )
            except TimeoutError:
                pass

    @workflow.run
    async def run(self, execution: ProductionInput) -> str:
        try:
            state = await self.transition(execution, "load")
            for shot_id in state.shot_ids:
                state = await self.checkpoint(execution)
                if state.status in TERMINAL:
                    return state.status
                operation_id = f"{execution.run_id}/shot/{shot_id}"
                if operation_id in state.completed_operations:
                    continue
                state = await self.transition(
                    execution, "begin_step", stage=f"simulate_shot:{shot_id}"
                )
                if state.status in TERMINAL:
                    return state.status
                if state.status == "PAUSED":
                    state = await self.checkpoint(execution)
                    if state.status in TERMINAL:
                        return state.status
                try:
                    await workflow.wait_condition(
                        lambda: self.cancel_notified,
                        timeout=timedelta(seconds=execution.simulation_step_seconds),
                    )
                except TimeoutError:
                    pass
                state = await self.transition(
                    execution,
                    "complete_step",
                    operation_id=operation_id,
                    shot_id=shot_id,
                    stage="shot_collected",
                )
                if state.status in TERMINAL:
                    return state.status
            while True:
                state = await self.checkpoint(execution)
                if state.status in TERMINAL:
                    return state.status
                state = await self.transition(execution, "finish")
                if state.status in TERMINAL:
                    return state.status
        except ActivityError:
            state = await self.transition(
                execution, "fail", error="模拟步骤校验失败，请查看服务日志。"
            )
            return state.status
        except asyncio.CancelledError:
            # User cancellation is a durable domain command, not Temporal termination.
            raise
