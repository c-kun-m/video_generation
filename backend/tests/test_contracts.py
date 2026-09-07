import json

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from video_generation.config import REPO_ROOT
from video_generation.contracts import models

SAMPLES = json.loads((REPO_ROOT / "contracts/samples.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample["name"])
def test_same_contract_in_pydantic_and_jsonschema(sample):
    model = getattr(models, sample["model"])
    try:
        model.model_validate(sample["data"])
        valid = True
    except ValidationError:
        valid = False
    assert valid == sample["valid"]
    schema = json.loads(
        (REPO_ROOT / f"contracts/schemas/{sample['model']}.json").read_text(encoding="utf-8")
    )
    assert Draft202012Validator(schema).is_valid(sample["data"]) == sample["valid"]
