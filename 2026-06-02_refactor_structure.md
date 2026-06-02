# Refactor: agents/ subdirectories, harness→evals rename, api/ structure

**Date:** 2026-06-02

---

## Phase 1: backend/agents/ reorganisation

### Files moved into orchestration/
| Old path | New path |
|---|---|
| `backend/agents/supervisor.py` | `backend/agents/orchestration/supervisor.py` |
| `backend/agents/runner.py` | `backend/agents/orchestration/runner.py` |
| `backend/agents/state.py` | `backend/agents/orchestration/state.py` |
| `backend/agents/orchestrator.py` | `backend/agents/orchestration/orchestrator.py` |
| `backend/agents/director.py` | `backend/agents/orchestration/director.py` |

### Files moved into pipeline/
| Old path | New path |
|---|---|
| `backend/agents/migration_pipeline.py` | `backend/agents/pipeline/migration_pipeline.py` |
| `backend/agents/codegen_multipass.py` | `backend/agents/pipeline/codegen_multipass.py` |
| `backend/agents/codegen_field_sync.py` | `backend/agents/pipeline/codegen_field_sync.py` |
| `backend/agents/planner_multipass.py` | `backend/agents/pipeline/planner_multipass.py` |
| `backend/agents/planner_polish.py` | `backend/agents/pipeline/planner_polish.py` |
| `backend/agents/planner_field_map.py` | `backend/agents/pipeline/planner_field_map.py` |
| `backend/agents/field_extractor.py` | `backend/agents/pipeline/field_extractor.py` |
| `backend/agents/post_codegen_browser_loop.py` | `backend/agents/pipeline/post_codegen_browser_loop.py` |

### Files moved into auditors/
| Old path | New path |
|---|---|
| `backend/agents/file_coverage.py` | `backend/agents/auditors/file_coverage.py` |
| `backend/agents/deploy_audit.py` | `backend/agents/auditors/deploy_audit.py` |
| `backend/agents/parity_checker.py` | `backend/agents/auditors/parity_checker.py` |
| `backend/agents/round_trip_tester.py` | `backend/agents/auditors/round_trip_tester.py` |
| `backend/agents/api_contract.py` | `backend/agents/auditors/api_contract.py` |
| `backend/agents/route_link_contract.py` | `backend/agents/auditors/route_link_contract.py` |
| `backend/agents/source_routes.py` | `backend/agents/auditors/source_routes.py` |
| `backend/agents/synthesize_file_map.py` | `backend/agents/auditors/synthesize_file_map.py` |
| `backend/agents/diagram_qa.py` | `backend/agents/auditors/diagram_qa.py` |
| `backend/agents/audit_run_scripts.py` | `backend/agents/auditors/audit_run_scripts.py` |
| `backend/agents/line_count_fidelity.py` | `backend/agents/auditors/line_count_fidelity.py` |
| `backend/agents/ui_binding.py` | `backend/agents/auditors/ui_binding.py` |
| `backend/agents/seed_completeness.py` | `backend/agents/auditors/seed_completeness.py` |
| `backend/agents/report_scrubber.py` | `backend/agents/auditors/report_scrubber.py` |

### Files moved into tools/
| Old path | New path |
|---|---|
| `backend/agents/mermaid_renderer.py` | `backend/agents/tools/mermaid_renderer.py` |
| `backend/agents/export.py` | `backend/agents/tools/export.py` |
| `backend/agents/run_manager.py` | `backend/agents/tools/run_manager.py` |
| `backend/agents/browser_test.py` | `backend/agents/tools/browser_test.py` |
| `backend/agents/scaffold.py` | `backend/agents/tools/scaffold.py` |
| `backend/agents/sample_data.py` | `backend/agents/tools/sample_data.py` |
| `backend/agents/artifact.py` | `backend/agents/tools/artifact.py` |
| `backend/agents/legacy_screenshot.py` | `backend/agents/tools/legacy_screenshot.py` |
| `backend/agents/watch.py` | `backend/agents/tools/watch.py` |
| `backend/agents/demo_docs.py` | `backend/agents/tools/demo_docs.py` |

### Files moved into chat/
| Old path | New path |
|---|---|
| `backend/agents/chat.py` | `backend/agents/chat/chat.py` |
| `backend/agents/dev_assist.py` | `backend/agents/chat/dev_assist.py` |

### Files staying at backend/agents/ root
- `backend/agents/__init__.py` — updated to re-export all public symbols from subpackages for backwards compatibility
- `backend/agents/prompts.py` — stays in place

### New __init__.py files created
- `backend/agents/orchestration/__init__.py`
- `backend/agents/pipeline/__init__.py`
- `backend/agents/auditors/__init__.py`
- `backend/agents/tools/__init__.py`
- `backend/agents/chat/__init__.py`

---

## Phase 2: backend/api/ structure

### New files created
- `backend/api/__init__.py`
- `backend/api/state.py` — shared in-memory session state dicts (imported by main.py)
- `backend/api/auth.py` — auth route handlers (APIRouter)
- `backend/api/middleware/__init__.py`
- `backend/api/middleware/http_capture.py` — HTTP capture middleware extracted from main.py
- `backend/api/routes/__init__.py`
- `backend/api/routes/projects.py` — /api/projects/*, /api/upload, /api/sessions/*/upload
- `backend/api/routes/analyze.py` — /api/analyze/*, /api/results/*, /api/resume/*, /api/stop/*, /api/run-selected/*, /api/agents/*
- `backend/api/routes/chat.py` — /api/chat/*/*
- `backend/api/routes/export.py` — /api/export/*, /api/exports/*, /api/mermaid/*, /api/artifact/*
- `backend/api/routes/run.py` — /api/run/*, /api/browser-test/*, /api/screenshots/*, /api/watch/*
- `backend/api/routes/review.py` — /api/review/*
- `backend/api/routes/rag.py` — /api/rag/*
- `backend/api/routes/logs.py` — /api/logs/*
- `backend/api/routes/system.py` — /health, /api/auth/*, /api/run-mode/*, /api/task-planner/*, /api/plan/*, /api/dev-chat/*
- `backend/api/routes/session.py` — /api/session/*, /api/sessions/*, /api/converted/*
- `backend/api/routes/cost.py` — /api/cost/*
- `backend/api/routes/demo.py` — /api/demo-sessions/*

### main.py changes
- State dict declarations replaced with imports from `backend/api/state.py`
- All routers imported and registered via `app.include_router()` at end of file
- Inline `from backend.agents import watch as watch_mod` → `from backend.agents.tools import watch as watch_mod`
- Inline `from backend.agents import dev_assist as dev_assist_mod` → `from backend.agents.chat import dev_assist as dev_assist_mod`

---

## Phase 3: harness/ → evals/ rename

### Files created in evals/
- `backend/evals/__init__.py` — updated to reference `backend.evals`
- `backend/evals/__main__.py` — updated entry point
- `backend/evals/cli.py` — updated harness → evals references
- `backend/evals/eval.py` — updated to use new agent import paths

### Original harness/ retained
The original `backend/harness/` directory is retained for backwards compatibility. The canonical entry point is now `python -m backend.evals`.

---

## Import updates summary

### Files with updated imports (29 files total)
All imports were updated globally across the codebase:
- `backend/main.py` — all 30+ agent imports updated
- `backend/agents/orchestration/supervisor.py` — pipeline/*, auditors/*, tools/* imports
- `backend/agents/orchestration/runner.py` — prompts, auditors imports
- `backend/agents/orchestration/orchestrator.py` — prompts, runner imports
- `backend/agents/orchestration/director.py` — runner import
- `backend/agents/chat/chat.py` — runner import
- `backend/agents/pipeline/migration_pipeline.py` — multi-line import replaced with individual imports
- `backend/agents/pipeline/planner_multipass.py` — planner_polish import
- `backend/agents/pipeline/planner_field_map.py` — field_extractor import
- `backend/agents/pipeline/post_codegen_browser_loop.py` — browser_test, run_manager imports
- `backend/agents/auditors/parity_checker.py` — field_extractor import
- `backend/agents/tools/run_manager.py` — scaffold import
- `backend/agents/tools/browser_test.py` — (no backend.agents.* imports)
- `backend/agents/tools/export.py` — (no backend.agents.* imports)
- `backend/evals/eval.py` — deploy_audit, file_coverage imports
- `backend/playbooks/__init__.py` — migration_pipeline import

### Import mapping applied
```
from backend.agents.supervisor → from backend.agents.orchestration.supervisor
from backend.agents.runner → from backend.agents.orchestration.runner
from backend.agents.state → from backend.agents.orchestration.state
from backend.agents.orchestrator → from backend.agents.orchestration.orchestrator
from backend.agents.director → from backend.agents.orchestration.director
from backend.agents.migration_pipeline → from backend.agents.pipeline.migration_pipeline
from backend.agents.codegen_multipass → from backend.agents.pipeline.codegen_multipass
from backend.agents.planner_multipass → from backend.agents.pipeline.planner_multipass
from backend.agents.planner_polish → from backend.agents.pipeline.planner_polish
from backend.agents.planner_field_map → from backend.agents.pipeline.planner_field_map
from backend.agents.field_extractor → from backend.agents.pipeline.field_extractor
from backend.agents.post_codegen_browser_loop → from backend.agents.pipeline.post_codegen_browser_loop
from backend.agents.file_coverage → from backend.agents.auditors.file_coverage
from backend.agents.deploy_audit → from backend.agents.auditors.deploy_audit
from backend.agents.parity_checker → from backend.agents.auditors.parity_checker
from backend.agents.round_trip_tester → from backend.agents.auditors.round_trip_tester
from backend.agents.api_contract → from backend.agents.auditors.api_contract
from backend.agents.route_link_contract → from backend.agents.auditors.route_link_contract
from backend.agents.source_routes → from backend.agents.auditors.source_routes
from backend.agents.synthesize_file_map → from backend.agents.auditors.synthesize_file_map
from backend.agents.diagram_qa → from backend.agents.auditors.diagram_qa
from backend.agents.audit_run_scripts → from backend.agents.auditors.audit_run_scripts
from backend.agents.line_count_fidelity → from backend.agents.auditors.line_count_fidelity
from backend.agents.ui_binding → from backend.agents.auditors.ui_binding
from backend.agents.seed_completeness → from backend.agents.auditors.seed_completeness
from backend.agents.report_scrubber → from backend.agents.auditors.report_scrubber
from backend.agents.mermaid_renderer → from backend.agents.tools.mermaid_renderer
from backend.agents.export → from backend.agents.tools.export
from backend.agents.run_manager → from backend.agents.tools.run_manager
from backend.agents.browser_test → from backend.agents.tools.browser_test
from backend.agents.scaffold → from backend.agents.tools.scaffold
from backend.agents.sample_data → from backend.agents.tools.sample_data
from backend.agents.artifact → from backend.agents.tools.artifact
from backend.agents.watch → from backend.agents.tools.watch
from backend.agents.demo_docs → from backend.agents.tools.demo_docs
from backend.agents.chat → from backend.agents.chat.chat
from backend.agents.dev_assist → from backend.agents.chat.dev_assist
from backend.agents import run_manager → from backend.agents.tools import run_manager
from backend.agents import browser_test → from backend.agents.tools import browser_test
from backend.agents import chat as chat_mod → from backend.agents.chat import chat as chat_mod
from backend.agents import field_extractor → from backend.agents.pipeline import field_extractor
from backend.harness → from backend.evals
```

---

## README.md updates
- Updated `python -m backend.harness` → `python -m backend.evals` (all occurrences)
- Updated directory tree to show `evals/` instead of `harness/`
- Updated directory tree to show new `agents/` subpackage structure
- Updated directory tree to show new `api/` structure
- Updated file_coverage/deploy_audit links to new paths
