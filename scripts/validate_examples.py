from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "reposkop" / "schemas"
schema_paths = sorted(SCHEMAS.glob("*.json"))

for path in schema_paths:
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)

config = json.loads((ROOT / "examples" / "inventory-config.json").read_text(encoding="utf-8"))
schema = json.loads((SCHEMAS / "inventory-config.v1.schema.json").read_text(encoding="utf-8"))
Draft202012Validator(schema).validate(config)

evidence = json.loads((ROOT / "examples" / "lifecycle-evidence.json").read_text(encoding="utf-8"))
schema = json.loads((SCHEMAS / "lifecycle-evidence.v1.schema.json").read_text(encoding="utf-8"))
Draft202012Validator(schema).validate(evidence)

print(f"validated {len(schema_paths)} schemas and 2 examples")
