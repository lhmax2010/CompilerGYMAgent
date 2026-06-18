# 7.0-contracts Fail-open Fix Review Notes

Review focus:

- Verify `canonicalize_candidate()` has no catch-all bool flag path.
- Verify `-fstrict-aliasing` / `-fno-strict-aliasing` reject in both orders.
- Verify `StatisticalResult.provenance_complete` defaults to `False`.
- Verify `can_accept()` rejects a significant result whose provenance was omitted.
- Verify `_records_have_complete_provenance()` rejects mismatched
  `measurement_plan_id` across baseline/candidate records.
- Verify 08a verdict and pair_quality rules are unchanged.
