import hashlib
import json

from video_generation.contracts.content import BriefContent, ScriptContent, StoryboardContent
from video_generation.domain.errors import DomainError


def canonical_digest(value: dict) -> str:
    # Wire schemas prohibit floats for timing and extra fields. Array order is meaningful.
    data = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def validate_structure(payload: BriefContent | ScriptContent | StoryboardContent) -> None:
    if isinstance(payload, ScriptContent):
        ids = [segment.segment_id for segment in payload.segments]
        if payload.brief_ref and payload.brief_ref.entity_kind != "brief":
            raise DomainError("VALIDATION_FAILED", "剧本必须引用需求版本。", 422)
    elif isinstance(payload, StoryboardContent):
        ids = [shot.shot_id for shot in payload.shots]
        if payload.script_ref and payload.script_ref.entity_kind != "script":
            raise DomainError("VALIDATION_FAILED", "分镜必须引用剧本版本。", 422)
        if any(len(set(s.segment_ids)) != len(s.segment_ids) for s in payload.shots):
            raise DomainError("VALIDATION_FAILED", "同一镜头不能重复关联剧本段落。", 422)
    else:
        ids = []
    if len(set(ids)) != len(ids):
        raise DomainError("VALIDATION_FAILED", "段落或镜头标识不能重复。", 422)


def validate_complete(
    payload: BriefContent | ScriptContent | StoryboardContent, upstream=None
) -> None:
    validate_structure(payload)
    if isinstance(payload, BriefContent):
        valid = all(
            value.strip()
            for value in (payload.theme, payload.audience, payload.purpose, payload.style)
        )
        message = "审批前请填写主题、受众、目的和风格。"
    elif isinstance(payload, ScriptContent):
        valid = bool(payload.brief_ref and payload.segments) and all(
            s.spoken_text.strip() and s.visual_description.strip() for s in payload.segments
        )
        message = "审批前请关联需求版本，并填写剧本旁白与画面描述。"
    else:
        valid = bool(payload.script_ref) and 3 <= len(payload.shots) <= 8
        valid = valid and 720 <= sum(s.duration_frames for s in payload.shots) <= 1440
        valid = valid and all(
            s.intent.strip() and s.camera.strip() and s.segment_ids for s in payload.shots
        )
        if upstream is not None:
            segments = {s.segment_id for s in upstream.segments}
            used = {i for s in payload.shots for i in s.segment_ids}
            valid = valid and used == segments
        message = "审批前请关联剧本，填写 3–8 个镜头的意图、运镜和段落，覆盖全部旁白；总计划时长需为 30–60 秒（24 fps）。"
    if not valid:
        raise DomainError("VALIDATION_FAILED", message, 422)
