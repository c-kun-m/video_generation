from dataclasses import dataclass


@dataclass
class ProductionInput:
    tenant_id: str
    project_id: str
    run_id: str
    snapshot_id: str
    start_event_id: str
    simulation_step_seconds: int = 5


@dataclass
class StepRequest:
    execution: ProductionInput
    action: str
    temporal_run_id: str
    operation_id: str = ""
    shot_id: str | None = None
    stage: str = ""
    error: str | None = None


@dataclass
class StepResponse:
    status: str
    pause_requested: bool
    shot_ids: list[str]
    completed_operations: list[str]
    control_seq: int
