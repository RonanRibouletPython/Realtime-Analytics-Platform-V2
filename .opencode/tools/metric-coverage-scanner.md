---
description: >
    Static analysis tool that walks the source tree and reports every
    function missing an expected [OBSERVABILITY_FRAMEWORK] metric registration. Produces
    a structured coverage report consumed by the Observability Auditor.
name: Metric Coverage Scanner
type: tool
---

# Metric Coverage Scanner

Performs static analysis on the source tree to verify that every target function 
defined in the `[SOURCE_ROOT]` directory has the instrumentation expected for its role. 
Produces a machine-readable coverage report for the Observability Auditor.

## Inputs

| Parameter        | Type   | Required | Description                                                       |
|------------------|--------|----------|-------------------------------------------------------------------|
| `source_root`    | string | yes      | Path to scan (e.g. `src/` or `app/`)                              |
| `step`           | string | yes      | Current step slug (used to load the expected metric rules)        |
| `metrics_module` | string | no       | Module where metrics are registered. Default: `[DEFAULT_METRICS_MODULE]` |

## Output

```json
{
  "step": "[STEP_SLUG]",
  "source_root": "[SOURCE_ROOT]",
  "files_scanned": 4,
  "functions_checked": 12,
  "coverage_summary": "PASS | FAIL",
  "missing": [
    {
      "file": "[SOURCE_ROOT]/[FILE_PATH]",
      "function": "[FUNCTION_NAME]",
      "line": 34,
      "missing_metrics": [
        {
          "metric_name": "[EXPECTED_METRIC_NAME]",
          "metric_type": "[METRIC_TYPE]",
          "rule": "[METRIC_RULE_DESCRIPTION]"
        }
      ]
    }
  ],
  "present":[
    {
      "file": "[SOURCE_ROOT]/[FILE_PATH]",
      "function": "[FUNCTION_NAME]",
      "line": 58,
      "metrics_found": ["[EXPECTED_METRIC_NAME]"]
    }
  ]
}