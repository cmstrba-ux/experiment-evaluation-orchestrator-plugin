import json


def validate_required_columns(schema_path: str, required: list[str]) -> None:
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    present = {col["name"] for col in schema}
    missing = [c for c in required if c not in present]
    if missing:
        raise ValueError(f"Missing required columns in {schema_path}: {missing}")
