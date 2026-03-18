# Engine shim cleanup (v17)

This pass keeps `openai_story_engine.py` as a compatibility and orchestration surface while moving more domain helpers to their owning modules.

## What changed

- Imported bootstrap helper functions instead of redefining them in the monolithic engine.
- Imported selection helper functions instead of keeping duplicate local copies.
- Replaced local summary/title implementations with thin wrappers that inject the monolithic engine's runtime hooks into `openai_story_engine_summary.py`.

## Why this matters

- Fewer duplicate definitions inside the monolithic engine.
- Lower maintenance cost when changing selection/bootstrap helper behavior.
- Existing tests that monkeypatch `openai_story_engine.call_json_response` / `call_text_response` keep working because wrappers still inject those callables.

## Result

`openai_story_engine.py` becomes closer to a stable shim/orchestrator layer instead of a second home for domain logic.
