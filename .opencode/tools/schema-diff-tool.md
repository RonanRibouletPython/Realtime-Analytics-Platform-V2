---
description: >
    Fetches the latest schema version from the [SCHEMA_REGISTRY_TYPE],
    diffs it against the user's local schema file, and returns a structured
    list of breaking vs non-breaking changes. Used by the Schema Sentinel.
name: [FORMAT] Schema Diff Tool
type: tool
---

# Schema Diff Tool

Compares a local [SERIALIZATION_FORMAT] schema file (e.g. JSON Schema, Protobuf, AVRO) against 
the latest registered version in the [SCHEMA_REGISTRY] and classifies each change as 
COMPATIBLE or BREAKING according to BACKWARD compatibility rules.

## Inputs

| Parameter    | Type   | Required | Description                                                  |
|--------------|--------|----------|--------------------------------------------------------------|
| `subject`    | string | yes      | Schema Registry subject/namespace (e.g. `[SCHEMA_SUBJECT]`)  |
| `local_path` | string | yes      | Path to the local `.[SCHEMA_EXTENSION]` file to compare      |
| `registry`   | string | no       | Registry base URL. Default: `[DEFAULT_REGISTRY_URL]`         |

## Output

```json
{
  "subject": "[SCHEMA_SUBJECT]",
  "registered_version": 3,
  "local_schema_path": "schemas/[SCHEMA_FILE].[EXTENSION]",
  "compatibility_mode": "BACKWARD",
  "summary": "COMPATIBLE | BREAKING",
  "changes":[
    {
      "field": "[FIELD_NAME]",
      "change_type": "added",
      "compatible": true,
      "reason": "Field added with default value — existing consumers unaffected."
    },
    {
      "field": "[FIELD_NAME]",
      "change_type": "removed",
      "compatible": false,
      "reason": "Required field removed with no default — consumers expecting it will fail."
    }
  ]
}