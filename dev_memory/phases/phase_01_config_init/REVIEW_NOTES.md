# Self Review Notes

No self review has been performed yet.

Required checklist for each subtask:
- Implementation matches referenced requirements.
- Documented failure modes are covered.
- Trace writes are present where required by SoT dual-track rules.
- Atomic YAML writes are used where required.
- No hidden canonical data is stored only in SQLite/cache.
- No unsafe assumption about spec restore or workspace verification.
- `dev_memory` progress is updated.
- Linux/Ubuntu-only behavior is explicit where POSIX features are used.
- No hardcoded paths that should come from config.
- Imported experience text is quote-wrapped in prompts where applicable.
- Hash calculation excludes fields listed in `hash_fields_excluded`.
