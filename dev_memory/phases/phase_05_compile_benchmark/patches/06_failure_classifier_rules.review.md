# Self Review - Phase 05 / Subtask 5.5b

## Scope

This subtask adds the Phase 05 classifier-rule layer on top of the 5.5a failure/result schema.

## Checks

- Compile and benchmark skills consume a shared classifier module.
- Classifier output is always a 5.5a FailureClassification.
- invalid_option maps to option_related and extracts affected_options.
- option_conflict maps to option_related and can write failed_combos only at HIGH confidence.
- Environment-related classifications never write failed_combos.
- Disk full, OOM, timeout, network, and permission patterns route to environment_related.
- High-confidence environment evidence overrides option matches.
- Unknown/unmatched failures default to unknown/LOW/write_failed_combos=False.
- matched_rule_id and classifier_version are populated.
- score_parse_failed remains a first-class benchmark failure.
- Classifier tests cover conservative routing and affected option extraction.
- Targeted, adjacent, and full tests pass.

## Result

No known findings. The rules layer now supplies structured classifications while preserving the model-level failed-combo write gate from 5.5a.
