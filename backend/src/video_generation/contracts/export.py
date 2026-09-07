"""Export checked-in wire contracts without starting the server or connecting to PostgreSQL."""

import json

from video_generation.api.app import create_app
from video_generation.config import REPO_ROOT
from video_generation.contracts import models


def main():
    target = REPO_ROOT / "contracts"
    target.mkdir(exist_ok=True)
    documents = {"openapi.json": create_app().openapi()}
    for name in dir(models):
        model = getattr(models, name)
        if (
            isinstance(model, type)
            and issubclass(model, models.Contract)
            and model != models.Contract
        ):
            schema = model.model_json_schema()
            schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
            documents[f"schemas/{name}.json"] = schema
    for name, data in documents.items():
        path = target / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
