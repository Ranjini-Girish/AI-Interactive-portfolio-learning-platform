# Findings Specification

## Finding Types

Findings are generated when computed metrics exceed thresholds defined in `config/thresholds.json`.

### Function-Level Findings

For each function, check:

1. **Cyclomatic Complexity Findings:**
   - CC > `very_high` threshold → finding type `very_high_cyclomatic`
   - CC > `high` threshold → finding type `high_cyclomatic`
   - CC > `moderate` threshold → finding type `moderate_cyclomatic`
   - Only emit the **highest** applicable finding (most severe wins)

2. **Cognitive Complexity Findings:**
   - CogC > `very_high` threshold → finding type `very_high_cognitive`
   - CogC > `high` threshold → finding type `high_cognitive`
   - CogC > `moderate` threshold → finding type `moderate_cognitive`
   - Only emit the **highest** applicable finding

### Module-Level Findings

For each module, check:

3. **Maintainability Index:**
   - MI < `low` threshold → finding type `low_maintainability`
   - MI < `moderate` threshold → finding type `moderate_maintainability`
   - Only emit the **highest** applicable finding (lowest MI wins)

4. **Instability:**
   - Instability > `instability_warning` → finding type `high_instability`

5. **Halstead Difficulty:**
   - Max function difficulty > `high` threshold → finding type `high_halstead_difficulty`
   - Max function difficulty > `moderate` threshold → finding type `moderate_halstead_difficulty`... (not used, only high threshold generates a finding)

Note: For Halstead, only the `high` threshold generates a finding. No moderate/low Halstead findings.

## Risk Score

Each finding has a risk score computed as:

```
risk_score = severity_multiplier × complexity_decay_base ^ normalized_value
```

Where:
- `severity_multiplier` comes from `weights.json → risk_score.severity_multipliers`
- `complexity_decay_base` comes from `weights.json → risk_score.complexity_decay_base`
- `normalized_value` is the metric value that triggered the finding (e.g., the CC value for cyclomatic findings, the CogC value for cognitive findings, the MI value for maintainability findings, the instability value × 100 for instability findings, the Halstead difficulty for Halstead findings)
- Round to `rounding_decimals` decimal places

## Finding Object Structure

```json
{
  "finding_type": "high_cyclomatic",
  "severity": "high",
  "module_name": "data_processor",
  "function_name": "processRecords",
  "metric_value": 15,
  "risk_score": 1.234567,
  "evidence": {
    "metric": "cyclomatic_complexity",
    "value": 15,
    "threshold": 10
  }
}
```

For module-level findings, `function_name` is `null`.

## Sorting

### Per-Module Findings
Sorted by: severity_rank ASC, finding_type ASC, function_name ASC (nulls first)

### Global Findings
Sorted by: severity_rank ASC, risk_score DESC, module_name ASC, function_name ASC (nulls first)
