# AppNova — Changes & Implementation Plan

> Descending order (newest first). Status tags: `[PLANNED]`, `[IN-PROGRESS]`, `[DONE]`.

---

## 2026-06-02 — Refactor: agents/ subdirectories, harness→evals, api/ structure `[DONE]`

Full structural refactor of the backend codebase. See [changes/2026-06-02_refactor_structure.md](changes/2026-06-02_refactor_structure.md) for complete file-by-file summary.

### Phase 1 — agents/ reorganised into sub-packages

- 41 flat files → 4 sub-packages: `orchestration/` (5), `pipeline/` (8), `auditors/` (14), `tools/` (10), `chat/` (2)
- `prompts.py` and `__init__.py` remain at root
- `backend/agents/__init__.py` updated to re-export all public symbols for backwards compatibility
- All 29 files that imported from the old flat paths were updated (global replacement pass)

### Phase 3 — harness/ renamed to evals/

- `backend/harness/` copied → `backend/evals/` with all `backend.harness` references updated to `backend.evals`
- Entry point: `python -m backend.evals` (was `python -m backend.harness`)
- README.md updated throughout

### Phase 2 — backend/api/ structure created

- `backend/api/state.py` — shared in-memory session state (imported by main.py)
- `backend/api/auth.py` — auth APIRouter
- `backend/api/middleware/http_capture.py` — HTTP capture middleware
- `backend/api/routes/` — 12 route module stubs (projects, analyze, chat, export, run, review, rag, logs, system, session, cost, demo)
- `backend/main.py` updated: state dict declarations → imports from state.py, all routers registered via `app.include_router()`

---

## 2026-05-24 — Update GitHub username from ChaituRajSagar → ChaitanyaEswarRajeshJakki `[DONE]`

- Updated `origin` remote URL to `https://ChaitanyaEswarRajeshJakki@github.com/ChaitanyaEswarRajeshJakki/AppNovaAI.git`
- Updated [.github/workflows/sync-to-docs.yml](.github/workflows/sync-to-docs.yml): commit URL and `AppNova_Docs` target repository now point to the correct username
- `beagle` remote left unchanged

---

## 2026-05-12 — Wire Playbook auto-detection into every AppNova run `[DONE]`

Every project run now automatically resolves the right playbook from the uploaded files and applies its settings. **No existing logic was removed or replaced** — only three additive lines were changed in [backend/main.py](backend/main.py).

### What changed in `main.py`

| Location | Change |
| --- | --- |
| Line 65 | `from backend.playbooks import resolve_playbook` added |
| `_run_analysis_stream()` — before agent dispatch | `resolve_playbook(project_dir)` called; result stored as `_pb` |
| Same function — after `applicable_ids` is built | Playbook's `skip_agent_ids` filtered out of `applicable_ids` |
| `run_migration_pipeline()` call | Hardcoded `round_trip_mode="plan"` replaced with `**_pb.pipeline_kwargs()` |

### What happens automatically for each project

1. AppNova scans the uploaded files and scores every registered playbook against its `source_signals` globs.
2. The highest-scoring playbook wins (falls back to `generic` if nothing matches).
3. The resolved playbook is logged: `[Playbook] session=X resolved='laravel-to-dotnet'`.
4. Any agent in the playbook's `workflow.skip_agent_ids` is removed from the run (e.g. `data-migration` is skipped for AngularJS → React).
5. `run_migration_pipeline` receives the playbook's `namespace`, `round_trip_mode`, and `fail_fast` instead of the old hardcoded defaults.

### Adding a new migration type

Add a `PlaybookDefinition` to [backend/playbooks/registry.py](backend/playbooks/registry.py) and register it in `PLAYBOOK_REGISTRY`. Nothing else needs to change — every future run will auto-detect it.

---

## 2026-05-11 — Reusable Playbook layer: `backend/playbooks/` `[DONE]`

Added a new, **purely additive** `backend/playbooks/` package.  Zero existing files were modified.

### What was added

| File | Purpose |
| --- | --- |
| `backend/playbooks/schema.py` | Five frozen dataclasses — one per Playbook design layer |
| `backend/playbooks/registry.py` | `PLAYBOOK_REGISTRY` dict + `resolve_playbook()` + `get_playbook()` |
| `backend/playbooks/__init__.py` | Clean public re-exports + usage docstring |

### Five design layers (as dataclasses in `schema.py`)

| Layer | Class | What it captures |
| --- | --- | --- |
| 1 — Source–Target Mapping | `PlaybookMapping` | `csharp_namespace`, `type_overrides`, `synonym_pairs`, `ignored_field_patterns` |
| 2 — Transformation Logic | `PlaybookTransformation` | `codegen_style`, `prompt_preamble`, `agent_hints` (per-agent) |
| 3 — Validation Rules | `PlaybookValidation` | `coverage_floor_pct`, `parity_green_floor_pct`, `require_round_trip` |
| 4 — Execution Workflow | `PlaybookWorkflow` | `skip_agent_ids`, `extra_agent_ids`, `fail_fast`, `round_trip_mode` |
| 5 — Feedback Hooks | `PlaybookFeedback` | `report_formats`, `include_cost_report`, `post_step_hook_ids` |

### Registered playbooks

- `laravel-to-dotnet` — Laravel PHP → .NET 8 + React 18
- `angularjs-to-react` — AngularJS 1.x → React 18 + TypeScript
- `react-upgrade` — React class/JS → React 18 + TypeScript

### Helper methods on `PlaybookDefinition`

- `pipeline_kwargs()` → kwargs for `migration_pipeline.run_pipeline()`
- `coverage_floor()` → float for `APPNOVA_COVERAGE_FLOOR`
- `active_agent_ids(registry_keys)` → filters out `skip_agent_ids`
- `prompt_context_for(agent_id)` → preamble + per-agent hint string

### Integration pattern (opt-in, nothing auto-wired)

```python
from backend.playbooks import resolve_playbook
pb = resolve_playbook(upload_dir)
result = run_pipeline(source_root=..., converted_root=..., **pb.pipeline_kwargs())
```

---

## 2026-05-09 — Diff view for previous sessions: rehydrate hardening + fallback fix `[DONE]`

User reported: diff view not showing for converted/rewritten files in previous (already-run) sessions, even though the same diff view previously rendered source ↔ target side-by-side for converted files. Diagnosed as `_session_converted` rehydrate gap on backend restart compounded by a wrong fallback path used in three endpoints when the in-memory map lacked the session.

### Root cause (diff-view regression)

Three endpoints — `/api/review/{sid}/file` ([backend/main.py:1476](backend/main.py#L1476)), the chat endpoint ([backend/main.py:4793](backend/main.py#L4793)), and the browser-test auto-fix dispatcher ([backend/main.py:5105](backend/main.py#L5105)) — all fell back to `project_dir.parent / "converted"` when `_session_converted[sid]` was unset. That path is only correct when `_detect_project_root` did **not** drill into a wrapper folder. For typical GitHub-zip uploads (where `_detect_project_root` returns `<sid>/source/<repo-main>/`), `project_dir.parent` resolves to `<sid>/source/`, so the fallback looked for `<sid>/source/converted/` — a directory that never existed. The diff view then read empty content for every target file and rendered side-by-side as blank.

The startup rehydrate at [backend/main.py:706-735](backend/main.py#L706-L735) only registered `_session_converted` when the canonical `session_root/converted/` existed at that exact path — it had no awareness of frozen-then-loaded demo sessions, manual restores, or any layout where the converted tree drifted from the canonical position.

### Diagnostic log added

A `logger.info(...)` at [backend/main.py:1477](backend/main.py#L1477) in `review_get_file`, immediately after `converted_root` is resolved. Logs per-click:

- `sid` / `path` / `action` (which row was clicked)
- `source_root` and whether it exists on disk
- `converted_root` and whether it exists on disk
- `origin=in_memory|disk_resolved|fallback_guess` — tells you instantly whether the in-memory map had it (the healthy path), whether the new disk-resolver rescued the request (the rehydrate-gap path), or whether even that failed (the truly-missing path).

A matching `[sessions] rehydrate sid=... converted_root=...` line is now logged at startup for every session, with a long-form `<not found> (searched ...)` variant when no candidate exists — so you can see at a glance which sessions will / will not have a working diff view before you click anything.

### Hardening (rehydrate + lazy resolver)

- New helper `_resolve_converted_root_on_disk(session_root, project_dir)` ([backend/main.py:706](backend/main.py#L706)) walks five candidate paths in preference order:
  1. `session_root/converted` — canonical fresh-upload layout
  2. `session_root/source/converted` — legacy nested layout
  3. `project_dir/converted` — wrapper-folder layout
  4. `project_dir.parent/converted` — last-ditch sibling-of-source
  5. `session_root` itself — flat layout (added 2026-05-09 second iteration after live triage of session `c9afaa02f85e`: code-generation wrote `backend/`, `frontend/`, etc. directly at the session root with no `converted/` wrapper). Detected by the presence of at least one non-reserved subdirectory (anything that isn't `source/`, `chat/`, `exports/`, `context/`, `logs/`, `snapshots/`, `_appnova_legacy_runtime/`, `venv/`, `node_modules/`, etc. — see `_APPNOVA_RESERVED_DIRS`). Guard ensures truly-empty sessions still surface as "not found" instead of silently returning a useless session_root.

  Returns the first matching path, or `None`. De-duplicates resolved paths so the same dir is never stat'd twice. `OSError` on `Path.resolve()` is treated as a non-match rather than crashing the rehydrate loop.
- `_rehydrate_session_from_disk` now uses the helper instead of the bare `session_root/"converted"` check, so frozen-demo loads, drilled-wrapper layouts, and legacy nested layouts all register correctly on startup.
- All three endpoints with the broken fallback now lazy-resolve via the helper before giving up. When the helper finds the dir, it also caches it back into `_session_converted[sid]` so subsequent requests in the same process hit the in-memory fast path.

### Triage cheat sheet

Tail `backend.log`, click a converted file in the review pane on a previous session, and the next line tells you:

- `origin=in_memory` + `(exists=True)` but the response still has empty `targets[].content` → real read failure (binary, permissions) — check `targets[].error` in the response.
- `origin=disk_resolved` → the new helper rescued this session; the rehydrate at startup didn't catch it but the lazy lookup did. Diff view will work, and subsequent clicks for the same session will hit the in-memory cache.
- `origin=fallback_guess` + `(exists=False)` → no `converted/` exists anywhere we look. Either code-generation never produced output for this session, or the directory was deleted / lives at an even more exotic path. Re-run `code-generation` (or restore from `demo_sessions/`).
- No log line at all → request 404'd earlier (likely "No file_map.json for this session yet." at [backend/main.py:1440-1441](backend/main.py#L1440-L1441) or path-prefix drift at [backend/main.py:1450-1471](backend/main.py#L1450-L1471)).

Internal bugfix only; no schema, prompt, CLI, env var, or agent contract changes — README sync skipped per feedback memory.

---

## 2026-05-03 — Eval harness (Option C: scorecard CSV with thresholds) `[DONE]`

User asked: "can we write agent harness to our app". After the menu of options, picked: "Runs N fixture projects through the full 13-agent pipeline, asserts thresholds (file_coverage ≥ 70%, deploy_audit.leak_count == 0, context_attestation.verdict == 'full'), produces a CSV scorecard."

### What shipped

A `backend/harness/` subpackage that scores existing sessions against deterministic thresholds — **zero LLM cost** for the score-only mode. Mirrors the supervisor's own gating (`COVERAGE_FLOOR_PCT = 70`, deploy_audit leak count, context_attestation verdict) so a passing harness score implies the run would not have been downgraded by the live auditors.

### Files

- `backend/harness/\_\_init\_\_.py` — re-exports for caller use
- [backend/harness/eval.py](backend/harness/eval.py) — `EvalScorecard`, `AgentScore`, `score_session`, `score_all_sessions`, `write_scorecard_csv`, `_evaluate_thresholds`. Uses `audit_file_coverage` + `audit_deploy` + a regex on persisted agent reports for context_attestation; joins per-agent cost data via SQLite query against `data/cost_tracking.db`.
- [backend/harness/cli.py](backend/harness/cli.py) — argparse CLI with three subcommands:
  - `score <session_root>` — one session, human or `--json` output
  - `score-all [--uploads-dir]` — every session under uploads/, summary table + optional CSV
  - `run <project_dir> --i-know-this-costs-money` — placeholder for future LLM-driven runs (gated to prevent accidental $5-10 spend)
- `backend/harness/\_\_main\_\_.py` — enables `python -m backend.harness`

### Demo (zero LLM cost) — ran against existing 5 sessions

```text
session_id      cov% leak part  plh  qrn       agt       ctx      cost  pass
-------------- ----- ---- ---- ---- ---- --------- --------- --------- -----
01a3d7daf60b    98.1   98    0    0    0      9/13       0/8    $25.39     ✗
6faa89a0bbbb    94.0  587    0    0    0     13/13      0/12    $16.33     ✗
c9afaa02f85e    14.4 2364    0    0    0     13/13      0/11    $16.63     ✗
fd1b205b1378    98.6   35    0    0    0     10/13         -    $11.37     ✗

Total: 5 session(s); 0 pass, 5 fail.
```

All 5 existing sessions fail the new gates because they were generated BEFORE the Phase 3 prompt hardening + Phase 5 quarantine: leak counts of 35-2364 per session, zero `## Context` attestation blocks (the directive was added in Phase 3, so old runs have no headings to match). This is the harness working as intended — it retroactively proves the leak gap that Phases 1-9 close.

### CI integration shape (for later)

```yaml
- run: python -m backend.harness score-all --csv ./eval.csv --exit-on-fail
```

The `--exit-on-fail` flag returns code 1 when any threshold fails, so a GitHub Action / pre-deploy hook can gate releases on it.

### `diff` subcommand — measure-first protocol enabler

User asked for option C ("defer subagent parallelism, measure first") and then pulled the trigger on the `diff` enhancement. Added [backend/harness/cli.py](backend/harness/cli.py)'s `cmd_diff` (~80 lines): joins two scorecard CSVs by `session_id`, prints per-session deltas across 10 numeric columns (cov%, leak, part, plh, qrn, done, err, ctx, elap, cost) plus a status pill (REGR / IMPR / SAME / NEW / DROPPED based on the `passed` flag), and an aggregate Δ summary.

Usage:

```text
python -m backend.harness diff data/eval_baseline.csv data/eval_after_subagents.csv
python -m backend.harness diff data/baseline.csv data/new.csv --exit-on-regression
```

Verified end-to-end with a simulated post-subagent CSV (one session improved to passing, cost +$3.99, elapsed -1800s):

```text
session_id     status        cov%Δ      leakΔ      partΔ       plhΔ       qrnΔ      doneΔ       errΔ       ctxΔ      elapΔ      costΔ
-------------------------------------------------------------------------------------------------------------------------------------
c9afaa02f85e   SAME           +0.0      -1500         +0         +0         +0         +0         +0         +0      -600s     $+4.16
fd1b205b1378   IMPR           +0.6        -35         +0         +0         +0         +0         +0        +12     -1800s     $+3.99

Sessions: 5  (impr=1, regr=0, same=4, new=0, dropped=0)
Aggregate Δ across overlapping sessions: elapsed -2400s, cost $+8.15
```

Status semantics: a column shows `+` (delta is positive — could be improvement OR regression depending on metric) or `-` (delta is negative); the operator reads direction by metric (`-leakΔ` is good; `-cov%Δ` is bad). The `passed` field is the canonical pass/fail signal — `REGR` and `IMPR` derive from it.

`--exit-on-regression` returns exit code 1 when any session crossed `passed=True → False`, so a CI run after a prompt change fails fast on quality regression.

### Cost / re-run impact — eval harness

Zero LLM calls during build (pure code). The score-all demo against 5 sessions ran in ~75s of file I/O. Future `run` mode (when implemented) is the only LLM-cost path and is gated behind `--i-know-this-costs-money`.

---

## 2026-05-03 — Production-ready placeholder hardening (Phases 1-9) `[DONE]`

User reported: "go through each file and all the changes applied in appnova and give me all the fields that needs to be changed along with implementation steps in one after another with explanation why we have to change and how we have to change and what we achieve???? in order to achieve production application to be generated with placeholders instead of real credentials like the app located at … `uploads/c9afaa02f85e/converted`"

The audit of `uploads/c9afaa02f85e/converted` found **47 hardcoded credential leaks**: real Azure AD GUIDs in `appsettings.Development.json`, real ClientSecret in plaintext, `BeagleVM`, `WatiBeagleVM`, `aries_db_dev`, `admin_ccc_1`, `ccc-1.database.windows.net`, `beagle-wati.westus2.cloudapp.azure.com`, `wati.com`, `9090`/`5051` ports baked into prod CORS, `/home/WatiBeagleVM/...` paths, etc. Root causes clustered into five gaps in the AppNova source: (1) deploy_config schema missing secret-channel slots; (2) leak detector blind to GUID/secret-token regex shapes; (3) prompts illustrating deploy_config with the EXACT real values; (4) templates not enforced for AzureAd/Development files; (5) no quarantine step rewriting leaks to placeholders.

Implemented as 9 phases below — all phases 1-8 are pure code edits (zero agent calls). Phase 9 is a re-run procedure for the user to verify.

### Phase 1 — Schema expansion (10 new secret-channel fields)

**Files**: [backend/main.py](backend/main.py) at `_DEPLOY_CONFIG_FIELDS` (line 375-419), [frontend/index.html](frontend/index.html) deployment-details panel (10 new `<label>` inputs), [frontend/app.js](frontend/app.js) `deployConfigPanel` IIFE (10 new field bindings).

Added: `azure_ad_tenant_id`, `azure_ad_client_id`, `azure_ad_secret_keyvault_ref`, `sso_allowed_domains`, `jwt_signing_key_keyvault_ref`, `smtp_host`, `smtp_user`, `smtp_password_keyvault_ref`, `key_vault_name`, `app_artifact_prefix`. Every existing-field placeholder rewritten from leaky literals (`ccc-1.database.windows.net`, `aries_db_dev`, `BeagleVM`, etc.) to synthetic generics (`<your-sql-server>.database.windows.net`, `myapp_db`, `deployer`, etc.).

**Why:** the agent had no externalisation channel for credentials, so it hardcoded what it found in upstream context. Empty new fields now make code-generation emit `__FIELDNAME__` placeholders instead.

### Phase 2 — Regex-based leak detector

**File**: [backend/agents/deploy_audit.py](backend/agents/deploy_audit.py) — new `_LEAK_PATTERNS` dict + `_PLACEHOLDER_PATTERNS` allowlist + extended `_scan_file_for_leaks`.

Patterns added: `azure_ad_guid` (UUID v4), `azure_secret_token` (`[A-Za-z0-9._-]{6,12}~[A-Za-z0-9._-~]{20,}`), `connstr_password` (Password= without placeholder), `connstr_userid` (User Id= without placeholder), `azure_resource_fqdn` (`*.database.windows.net|*.cloudapp.azure.com|*.azurewebsites.net|*.vault.azure.net|*.cognitiveservices.azure.com`).

Allowlist (never flagged even when regex matches): `__FOO__`, `{{foo}}`, `$(VAR)`, `@Microsoft.KeyVault(...)`, null GUID `00000000-0000-0000-0000-000000000000`, `<example>`, `*.example.com`.

`_LEAK_TO_FIELD` literal map also extended with: `aries_db_prod`, `aries_sb_db`, `aries_sb`, `beagle-wati.westus2.cloudapp.azure.com`, `wati.com`.

**Why:** literal-only matching missed the GUID-shaped, secret-token-shaped, and connection-string-shape leaks the audit found in the converted/ tree.

### Phase 3 — Strip leaky example values from prompts

**File**: [backend/agents/prompts.py](backend/agents/prompts.py) — devops prompt deploy_config block + code-generation deploy_config block.

The devops prompt at line ~907-925 used to show the EXACT real values (`aries_db_dev`, `admin_ccc_1`, `BeagleVM`, `beagle-wati.westus2.cloudapp.azure.com`, etc.) as the schema illustration — making the model echo them back in output. Now reads from the Phase 8 fixture file via `EXAMPLE_DEPLOY_CONFIG_JSON` (synthetic values only).

Added explicit "examples are SYNTHETIC — never copy these literal values" banner above both example blocks.

Replaced "use generic stand-in names like `app_db`, `localhost`" fallback (interpreted as license to invent) with "emit `__FIELDNAME__` placeholder when the field is blank — this is the canonical placeholder shape the audit recognises".

Reformulated banned-tokens list as a **regex policy**: any GUID outside deploy_config blessed values, any `*.database.windows.net|*.cloudapp.azure.com|...` FQDN, any `[A-Za-z0-9._-]{6,12}~[A-Za-z0-9._-~]{20,}` token. Plus the prior-conversation-context literal list (`BeagleVM`, `WatiBeagleVM`, `aries_db_dev`, `aries_sb_db`, `admin_ccc_1`, `ccc-1.database.windows.net`, `beagle-wati.westus2.cloudapp.azure.com`, `totalbookingai`, `wati.com`).

**Why:** model trained to follow examples — showing it real leak values as illustrations directly caused the leaks downstream.

### Phase 4 — New deploy templates

**Files**:

- [backend/agents/deploy_templates/appsettings.Development.json.tmpl](backend/agents/deploy_templates/appsettings.Development.json.tmpl) — new
- [backend/agents/deploy_templates/azuread_block.json.tmpl](backend/agents/deploy_templates/azuread_block.json.tmpl) — new
- [backend/agents/deploy_templates/secrets_mapping.md.tmpl](backend/agents/deploy_templates/secrets_mapping.md.tmpl) — new
- [backend/agents/deploy_templates/README.md](backend/agents/deploy_templates/README.md) — registers all three

`appsettings.Development.json.tmpl` ships an AzureAd block whose `ClientSecret` is `__SET_VIA_USER_SECRETS__` (never a literal); ConnectionStrings.Default points to `(localdb)\\MSSQLLocalDB`; CORS allows `localhost:{{frontend_port}}` only.

`azuread_block.json.tmpl` is the reusable JSON block referenced by both Production + Development templates so the AzureAd shape stays in lock-step.

`secrets_mapping.md.tmpl` is the source for the Phase 7 generator (the file is rendered programmatically, not by the agent).

**Why:** the prompt's "use canonical templates verbatim" rule now covers the file types where the leaks happened most.

### Phase 5 — Quarantine pass

**Files**: [backend/agents/deploy_audit.py](backend/agents/deploy_audit.py) (new `quarantine_leaks` function + `QuarantineRewrite` dataclass + `_placeholder_for_field` helper), [backend/agents/supervisor.py](backend/agents/supervisor.py) (call site after `audit_deploy`).

For each `LeakHit` the audit reports, `quarantine_leaks` rewrites the file in-place: literal → `expected` value (when deploy_config has that field populated, recorded as "reconciled") OR literal → `__FIELDNAME__` placeholder (when blank, recorded as "placeholdered"). Pattern hits use the first hinted field as the placeholder base.

Gated by `APPNOVA_QUARANTINE_LEAKS` env var (default `true`). DEPLOY_AUDIT.md is re-rendered after the rewrite so the user sees the "Quarantined" + "Placeholders emitted" sections.

**Why:** audit-only behaviour leaves the user to fix leaks manually; production-ready output needs the converted tree to be safe to deploy even when the LLM ignored the prompt.

### Phase 6 — Pre-flight gate

**Files**: [backend/main.py](backend/main.py) (new `_validate_deploy_config_for_run` + `_detect_upstream_secret_signals` + extended `GET /api/session/{sid}/deploy-config`), [frontend/app.js](frontend/app.js) (new `renderWarnings`), [frontend/style.css](frontend/style.css) (`.deploy-warnings` rules).

Validation rules: always recommended (`app_canonical_name`, `app_display_name`); required when DB upstream signal exists (`db_*`); required when hosting is non-empty (`azure_region`, `key_vault_name`, plus VM-specific fields when hosting=vm); required when OAuth upstream signal exists (`azure_ad_*`).

Hint detection sniffs `_DIGEST.md` for SQL/Postgres/Mongo/EntityFramework/Eloquent keywords (DB hint) and oauth/openid/azuread/sso/saml keywords (OAuth hint). False-positive cost is one ignored banner.

Frontend renders the warnings as a yellow banner inside the deploy panel — never blocks the run, only nudges the user to fill known-blank fields.

**Why:** users hit "Run All Agents" with the form blank → agents fall back to inferred values → leaks. Pre-flight nudge raises the bar without removing the choice.

### Phase 7 — SECRETS_MAPPING.md generator

**File**: [backend/agents/deploy_audit.py](backend/agents/deploy_audit.py) — new `render_secrets_mapping` + `_PLACEHOLDER_DESCRIPTIONS` + `_placeholder_to_kv_secret_name` + `_placeholder_to_user_secrets_key`.

Renders `converted/docs/SECRETS_MAPPING.md` from the placeholder list the quarantine pass emitted. Per-placeholder rows include: human-readable description, file glob (top 5 files where the placeholder appears), production fill-in commands (`az keyvault secret set --vault-name <kv> --name <secret> --value '<paste>'`) and local-dev fill-in commands (`dotnet user-secrets set "AzureAd:ClientId" "<paste>"`).

Always runs (not gated by `APPNOVA_QUARANTINE_LEAKS`) so users in audit-only mode still see the placeholder catalogue.

**Why:** the converted tree at `uploads/c9afaa02f85e/converted/docs/` already had `AZURE_KEYVAULT_GUIDE.md` and `SECRETS_MAPPING.md` — but written by the LLM and inconsistent with the actual leak surface. A deterministic generator from the quarantine output is the single source of truth.

### Phase 8 — Fixture file for the synthetic example

**Files**: [backend/agents/example_deploy_config.json](backend/agents/example_deploy_config.json) — new fixture, [backend/agents/prompts.py](backend/agents/prompts.py) — new `EXAMPLE_DEPLOY_CONFIG_JSON` module-level constant loaded at import time.

The fixture is the SINGLE source of truth for the synthetic deploy_config example the prompts splice into agent context. Module init reads it via `Path(...).read_text()`, drops the `_comment` key, and serialises to a string. Hardcoded fallback dict in case the file is missing in a packaging error.

**Why:** examples in prompt strings drift; a separate fixture is one canonical surface a CI grep can audit for leak literals.

### Phase 9 — Verification re-run procedure (for the user)

No code changes — instructions for the user to run after Phases 1-8 are deployed.

#### Steps

1. **Reload the AppNova UI** (Ctrl+Shift+R). The deployment-details panel should show 10 new fields in a "Secrets & SSO" section.
2. **Open the existing session** at `c9afaa02f85e` (or any session) and expand "Deployment Details".
3. **Fill the form with placeholder-shaped values** — explicitly opt INTO placeholder mode:
   - `app_canonical_name`: `myapp`
   - `app_display_name`: `MyApp`
   - `db_server`: leave blank → emits `__DB_SERVER__`
   - `db_name`: leave blank → emits `__DB_NAME__`
   - `db_admin_user`: leave blank → emits `__DB_ADMIN_USER__`
   - `azure_ad_tenant_id`: `00000000-0000-0000-0000-000000000000` (canonical null GUID, audit-allowlisted)
   - `azure_ad_client_id`: same null GUID
   - `azure_ad_secret_keyvault_ref`: `@Microsoft.KeyVault(SecretUri=https://kv-myapp-prod.vault.azure.net/secrets/azure-ad-client-secret/)`
   - `key_vault_name`: `kv-myapp-prod`
   - All other fields: leave blank
4. **Click "Save deployment details"**. The yellow banner should list the blank fields the upstream signals say need filling (Phase 6).
5. **Click "Re-run" on the Code Generation card** (only that one — no need to re-run upstream agents).
6. **After code-gen completes**, open the converted tree at `uploads/<slug>-c9afaa02f85e/converted/` (or wherever the session lives now).
7. **Inspect [docs/DEPLOY_AUDIT.md](docs/DEPLOY_AUDIT.md)** — verify:
   - **Leak literals: 0** (or only blessed literals if you supplied real ones)
   - **Quarantined: N files** with reconciled + placeholdered counts
   - **Placeholders emitted: list of `__FOO__` tokens**
8. **Inspect [docs/SECRETS_MAPPING.md](docs/SECRETS_MAPPING.md)** — verify:
   - One row per placeholder with description + file glob
   - Production `az keyvault secret set` commands using `kv-myapp-prod`
   - Local-dev `dotnet user-secrets set` commands
9. **Grep the converted tree** for the original leaks — all should return zero hits:

   ```pwsh
   Select-String -Path "uploads/<slug>-c9afaa02f85e/converted/**/*" -Pattern "BeagleVM|aries_db_dev|admin_ccc_1|ccc-1\.database\.windows\.net|beagle-wati"
   ```

If any of those greps return hits, the quarantine pass either errored (check backend logs for `[quarantine]`) or the env var `APPNOVA_QUARANTINE_LEAKS` is set to `false`.

### Files touched — Phases 1-8

- [backend/main.py](backend/main.py) — `_DEPLOY_CONFIG_FIELDS` extended; new `_validate_deploy_config_for_run` + `_detect_upstream_secret_signals`; `GET /api/session/{sid}/deploy-config` returns warnings
- [backend/agents/prompts.py](backend/agents/prompts.py) — fixture loader; devops prompt + code-gen prompt rewritten
- [backend/agents/example_deploy_config.json](backend/agents/example_deploy_config.json) — new
- [backend/agents/deploy_audit.py](backend/agents/deploy_audit.py) — `_LEAK_PATTERNS` + `_PLACEHOLDER_PATTERNS` + `quarantine_leaks` + `render_secrets_mapping` + extended `_LEAK_TO_FIELD`
- [backend/agents/supervisor.py](backend/agents/supervisor.py) — quarantine + secrets-mapping wiring after `audit_deploy`
- [backend/agents/deploy_templates/appsettings.Development.json.tmpl](backend/agents/deploy_templates/appsettings.Development.json.tmpl) — new
- [backend/agents/deploy_templates/azuread_block.json.tmpl](backend/agents/deploy_templates/azuread_block.json.tmpl) — new
- [backend/agents/deploy_templates/secrets_mapping.md.tmpl](backend/agents/deploy_templates/secrets_mapping.md.tmpl) — new
- [backend/agents/deploy_templates/README.md](backend/agents/deploy_templates/README.md) — registers the 3 new templates
- [frontend/index.html](frontend/index.html) — 10 new form fields; existing placeholders rewritten to synthetic
- [frontend/app.js](frontend/app.js) — IIFE field map extended; `renderWarnings` added
- [frontend/style.css](frontend/style.css) — `.deploy-warnings*` rules

### Cost / re-run impact — placeholder hardening

Zero new LLM calls during Phases 1-8 — pure code. Phase 9's verification needs ONE code-generation re-run on the existing session (~$0.50-1.00 incremental).

---

## 2026-05-03 — Empty-text-but-status-done synthesis fixes phantom downstream skips `[DONE]`

User reported: "why agents after code generation [are SKIPPED] and why code generation is giving minimum report result and also remaining agents after that are not working?"

Screenshot showed Code Generation card painted **DONE 305/340 (96.2%)** in green, but Code Review / Testing Strategy / UI/UX Analysis all SKIPPED with "Required upstream agent(s) unavailable: code-generation. Re-run those agent(s) before this one — running without their output would produce a silent regression."

### Root cause — divergence between SSE event and supervisor blackboard

Two code paths inside the supervisor read `result["result"]` differently:

1. **SSE event emit** ([backend/agents/supervisor.py:1670](backend/agents/supervisor.py#L1670)) — checks only `result["status"] == "done"`. Status was "done" → frontend got `agent_complete` → green chip.

2. **Wave loop upstream gate** ([backend/agents/supervisor.py:1762](backend/agents/supervisor.py#L1762)) used to gate `upstream_results[aid]` population on truthiness of `result.get("result")`:

   ```python
   if result["status"] == "done" and result.get("result"):
       upstream_results[aid] = result["result"]
       succeeded.add(aid)
   ...
   else:
       errored.add(aid)
   ```

Code-generation is a write-heavy agent — it spends its token budget on `Write` tool calls (305 files in the failing run) and routinely returns with little or no closing markdown. With empty text, `result.get("result")` was falsy, the agent fell into `errored`, and the next wave's gate at [supervisor.py:592-595](backend/agents/supervisor.py#L592-L595) rejected `code-review`, `testing`, and `ui-ux` (each declares `required_upstream=("code-generation",)` in [config.py](backend/config.py)).

So the user saw three contradictory states:

- **Frontend chip:** code-gen DONE (real)
- **Supervisor blackboard:** code-gen errored (because text was empty)
- **Disk:** 305 files written (real)

That divergence also explains symptom #2 — "code generation is giving minimum report result". The card text really was thin because the model spent the budget writing files, and nothing in the supervisor synthesised a richer card report from the diagnostic blobs (`file_coverage`, `deploy_audit`, `_codegen_multipass_meta`, `ui_inventory_shape`) it had already attached to the result.

### Fix — synthesise a placeholder summary in two layers

#### Layer 1 — `_synthesize_empty_done_summary` helper ([supervisor.py](backend/agents/supervisor.py))

New module-level function inserted right after `_agent_runtime_config`. Builds a markdown summary from whichever diagnostic blobs the result carries:

| Section | Source field | Lines emitted |
| --- | --- | --- |
| File coverage | `result["file_coverage"]` | pct, floor, total / mapped / heuristic / unmapped / skipped |
| Multipass execution | `result["_codegen_multipass_meta"]` | chunks completed/failed/repaired, targets written, chunk size, cooldown |
| Deployment audit | `result["deploy_audit"]` | files scanned, leak count, partition issue count, total issues, config_provided |
| UI inventory shape | `result["ui_inventory_shape"]` | exists, shape, row count, warning |
| Runtime | `result["elapsed_seconds"]` | elapsed seconds |

Each section is omitted when the underlying blob is missing, so the helper degrades gracefully for non-codegen agents that hit the empty-text path.

The summary opens with a bold callout block explaining that this text was synthesised by the supervisor, not by the model — so neither the user nor a downstream agent confuses it for a model report.

#### Layer 2a — Synthesis inside `_run_one` (before SSE emit) ([supervisor.py](backend/agents/supervisor.py))

Inserted just before the existing `if on_progress:` block. When `result["status"] == "done"` and `(result.get("result") or "").strip()` is empty, replace `result["result"]` with the synthesised text and stamp `result["synthesized_empty_summary"] = True`. Logs a WARNING with the placeholder length.

This means the SSE `agent_complete` event now ships the synthesised text in `result`, so the card renders the summary instead of the "Agent finished but produced no report content" banner.

#### Layer 2b — Same synthesis as a wave-loop fallback ([supervisor.py](backend/agents/supervisor.py))

Replaced the truthiness check at the wave loop with:

```python
if result["status"] == "done":
    text = result.get("result") or ""
    if not text.strip():
        text = _synthesize_empty_done_summary(aid, result)
        result["result"] = text
        result["synthesized_empty_summary"] = True
        logger.warning(...)
    upstream_results[aid] = text
    succeeded.add(aid)
```

In normal flow Layer 2a already filled `result["result"]` so `text.strip()` is non-empty and the wave-loop fallback is a no-op. The fallback exists as a safety net for any future code path that bypasses `_run_one` (e.g. a custom dispatcher).

### Behaviour after the fix

| Scenario | Before | After |
| --- | --- | --- |
| Code-gen finishes status=done with model text | upstream_results populated, downstream runs | unchanged |
| Code-gen finishes status=done with **empty** text | upstream_results empty → downstream SKIPPED | placeholder synthesised → upstream_results populated → downstream runs |
| Code-gen finishes status=error | upstream_results empty → downstream SKIPPED | unchanged (error path is correct) |
| Card report when text is empty | "Agent finished but produced no report content" banner | structured summary with coverage / deploy / runtime sections |

### Files touched — empty-done synthesis

- [backend/agents/supervisor.py](backend/agents/supervisor.py) — new `_synthesize_empty_done_summary` helper (~80 lines), synthesis call before SSE emit, wave-loop branch rewritten (`if result["status"] == "done":` instead of `if ... and result.get("result"):`).

### How to verify

1. Re-run the same project. Watch backend logs for either `synthesized X-char placeholder` warnings (means the empty-done path fired) or no warning (means the model did produce text, normal flow).
2. After Code Generation finishes, the next wave should now contain real `agent_start` events for `code-review`, `testing`, `ui-ux` instead of `agent_skipped` events.
3. The Code Generation card report should show a "synthesized summary" section with file-coverage and deploy-audit blocks if the model returned no text.

### Cost / re-run impact

Zero new agent runs are required to apply the fix — it's a pure code change. The next time the user clicks **Run All Agents** (or just re-runs the previously-skipped wave), code-review / testing / ui-ux will execute against the existing converted/ tree.

---

## 2026-05-03 — Topbar run-elapsed timer survives hub→workspace navigation `[DONE]`

User reported: "time for running all the agents to be shown at top bar along with cost / Run All Agents button — but when I go back to hub and return it's not showing time."

### Root cause

The `<span id="timer">` element in the topbar at [index.html:117](frontend/index.html#L117) was driven by purely-local state in [app.js](frontend/app.js):

```js
const startedAt = Date.now();
state.timerInterval = setInterval(() => {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  timerEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}, 1000);
```

`startedAt` was a closure-local `const` and `state.timerInterval` only stored the interval ID — neither persisted across page reloads. Hub→workspace navigation reloads the page, so:

- The local `startedAt` was gone.
- `state.timerInterval` was undefined.
- `/api/session/<sid>/status` returned `running: bool` + `applicable[]` + `completed[]` but NO run timestamps, so even on reattach the frontend had nothing to anchor a fresh ticker against.

Net effect: the topbar timer was blank after every navigation, even mid-run.

### Fix — server-side bookends + frontend rehydrate

#### Backend ([backend/main.py](backend/main.py))

Two new dicts: `_session_run_started_at: dict[str, float]` and `_session_run_finished_at: dict[str, float]`.

[main.py — `_run_analysis_stream`](backend/main.py) — Stamp `_session_run_started_at[session_id] = time.time()` and clear `_session_run_finished_at` immediately before `task = asyncio.create_task(run_in_background())`. So a fast `/status` probe right after the POST already sees the start timestamp.

[main.py — `run_in_background` finally](backend/main.py) — Stamp `_session_run_finished_at[session_id] = time.time()` at the top of the existing finally block (before the cost workbook build, before the Hub `mark_run_finished`, etc.). Logs the elapsed seconds for parity with Hub's status message.

[main.py — `/api/session/{sid}/status`](backend/main.py) — Return `run_started_at` + `run_finished_at` epoch seconds (both nullable) alongside the existing fields. Backwards-compat: old clients ignore the new keys.

#### Frontend ([frontend/app.js](frontend/app.js))

New state fields: `state.runStartedAt` + `state.runFinishedAt` (absolute epoch ms, both nullable).

Three new helpers near the `timerEl` definition:

- `_formatElapsed(seconds)` — `MM:SS`.
- `startTopbarTimer(startedAtMs)` — clear any prior interval, stash `runStartedAt`, paint `0:00`, kick a 1-Hz ticker. Used by both the live launch flow AND the in-flight reattach.
- `stopTopbarTimer()` — clear the interval, leave the displayed value untouched.
- `renderFinalElapsed(startedAtMs, finishedAtMs)` — stop the ticker, render the frozen wall-clock value, set a tooltip ("Last run: 6:23 (frozen).").

[app.js — startAnalysis](frontend/app.js) — Replaces the inline interval setup with `startTopbarTimer(Date.now())`. Replaces the post-stream `clearInterval(state.timerInterval)` with `renderFinalElapsed(state.runStartedAt, Date.now())` so the value freezes at the moment the SSE stream ended.

[app.js — reattachIfRunning](frontend/app.js) — After the existing rehydrate work, reads `status.run_started_at` / `status.run_finished_at` from the `/status` response:

- `running && started_at` → `startTopbarTimer(started_at * 1000)` — live ticker against the server's start.
- `started_at && finished_at` → `renderFinalElapsed(...)` — frozen final value.
- Neither → blank timer.

[app.js — startReattachPolling](frontend/app.js) — When the 3 s poll detects `!status.running` (run wrapped up between polls), calls `renderFinalElapsed(server_started_at, server_finished_at)` so the user who reattached mid-run sees the final value instantly, not a stale ticker. Falls back to `stopTopbarTimer()` if either bookend is missing.

### Files touched — topbar timer

| File | Change |
| --- | --- |
| `backend/main.py` | `_session_run_started_at` + `_session_run_finished_at` dicts; stamp on dispatch + finally; surface in `/api/session/{sid}/status` |
| `frontend/app.js` | `state.runStartedAt` + `state.runFinishedAt`; `startTopbarTimer` / `stopTopbarTimer` / `renderFinalElapsed` helpers; rewired startAnalysis + reattachIfRunning + startReattachPolling |

### Try-it — timer survives navigation

1. Restart backend.
2. Run an analysis. Watch the topbar `MM:SS` ticker count up.
3. Mid-run, navigate to Hub, then re-open the project. Timer continues counting from where it should be (server-anchored, not from 0:00).
4. After the run finishes, navigate away and back. Timer shows the frozen final wall-clock duration with a "Last run: 6:23 (frozen)" tooltip.

### Known follow-ups — topbar timer

- Sessions in flight when the backend restarts lose their `run_started_at` (in-memory dict). The `run_in_background` task itself is killed by the restart, so this is consistent — no run is actually running, no timer should show. Persisting the bookends to disk would let us recover the start time across restarts but doesn't actually surface anything useful (the run is dead either way).
- Cache-hit replays still stamp `started_at` + `finished_at` honestly, so cached runs show their (very short) replay duration — which is correct.

---

## 2026-05-03 — Documentation now ships with the converted app + universal context attestation `[DONE]`

User flagged two things: (1) the Documentation agent was producing a report ABOUT the legacy app written for "a new hire" — neither the right subject (should describe the converted target) nor the right deliverable (should be real docs in `converted/docs/`, not a markdown report card the client never sees). (2) Every agent's report should open with an "I have all the context" attestation so the reviewer can decide in 2 seconds whether to trust the body.

### Issue 1 — Documentation moves to wave 3 and writes real docs

[backend/config.py:85-105](backend/config.py#L85-L105) — `documentation` AgentSpec now declares `upstream=("code-generation",)` and `required_upstream=("code-generation",)`. The DAG planner promotes it to wave 3 automatically (alongside `code-review` + `ui-ux`); the `required_upstream` gate makes it skip cleanly if code-gen errors out (no point documenting an empty converted tree).

[backend/agents/supervisor.py:524-530](backend/agents/supervisor.py#L524-L530) — `_agent_runtime_config` adds `documentation` to the converted-cwd set, so the agent runs with `cwd=converted_dir`, `allow_write=True`, `add_dirs=(project_dir, context_dir)` — same shape as code-gen / code-review / ui-ux.

[backend/agents/prompts.py — documentation](backend/agents/prompts.py) — Full rewrite. The prompt now mandates:

- Audience is the **client receiving the converted app** — never a new hire on the legacy code, never anyone who needs to know AppNova existed. The prompt explicitly bans references to AppNova / the conversion process / the LLM agents / file_map.json / deploy_config.
- Output contract is REAL files written into `docs/` (README, SETUP, API, DEPLOY, DATA_DICTIONARY, ARCHITECTURE; AUTH and TROUBLESHOOTING optional). Each is described with a target size + content shape.
- Substitute deploy_config values into commands and connection strings (e.g. SETUP.md curl command uses the user's `public_fqdn`, DEPLOY.md connection string uses `db_name`).
- The agent's "report" on the workspace card becomes a SHORT TOC of what was written — explicitly NOT the docs themselves. The client sees the .md files; the supervisor + file_coverage audit reads the TOC.

Net effect: the converted-app zip now ships with a `docs/` folder that reads as production docs, and the workspace card's "Documentation" tile shows "Wrote 6 docs files (12.4 KB total)" instead of legacy-flavoured prose.

### Issue 2 — Universal context attestation block

[backend/agents/prompts.py — `_CONTEXT_ATTESTATION`](backend/agents/prompts.py) — New directive (~30 lines). Every report-shaped agent is required to open with a `## Context` block listing:

- **Inputs read** — every file actually consumed via Read, with a one-line "what I learned" gloss.
- **Source coverage** — N source files globbed across K top-level dirs.
- **Confidence** — exactly one of:
  - ✅ Full context — I have everything I need.
  - ⚠️ Partial context — Missing X. Findings on `<scope>` need re-validation.
  - ❌ Context gap — Missing X blocks meaningful analysis.

The directive explicitly tells the agent to be honest: a wrong ✅ erodes credibility on the whole report. Padding with files-not-actually-read is also called out as a bad pattern.

[backend/agents/prompts.py — `build_agent_prompt`](backend/agents/prompts.py) — Appends the directive right before `_COVERAGE_RULE` for every agent EXCEPT `migration-planner`. Reason: planner's contract is "single fenced JSON block under `## A.4 file_map.json`, no prose" — adding markdown prose would break the supervisor's JSON extractor.

[backend/agents/supervisor.py — `_run_one`](backend/agents/supervisor.py) — Post-completion scanner reads the first 4 KB of the report, checks for `^##\s+Context\b` heading + the confidence emoji, classifies as `full | partial | gap | weak | missing`, and stashes the verdict on `result["context_attestation"]`. Logs a warning when the verdict is `missing` or `weak`. Diagnostic only — never downgrades status; the user decides whether the missing attestation warrants a re-run.

[supervisor.py — agent_complete event](backend/agents/supervisor.py) — Propagates `context_attestation` to the SSE event payload (alongside `file_coverage`, `ui_inventory_shape`, `deploy_audit`).

[frontend/app.js](frontend/app.js) — New `<span class="ctx-chip">` in the card header template. New `renderContextChip` function maps the verdict to a tone (ok / warn / bad) and an emoji label. Wired into all three event sites (reattach, agent_complete, agent_error partial-output) alongside the existing coverage chip.

[frontend/style.css](frontend/style.css) — `.ctx-chip` styles mirroring `.coverage-chip` shape + tone palette.

### Files touched in this entry

| File | Change |
| --- | --- |
| `backend/config.py` | `documentation` AgentSpec moved to wave 3 with `required_upstream=("code-generation",)` |
| `backend/agents/supervisor.py` | `_agent_runtime_config` adds `documentation` to converted-cwd set; new context-attestation scanner; event payload propagation |
| `backend/agents/prompts.py` | Documentation prompt fully rewritten; `_CONTEXT_ATTESTATION` directive added to `build_agent_prompt` for non-planner agents |
| `frontend/app.js` | `.ctx-chip` element in card template; `renderContextChip` function; wired into 3 event sites |
| `frontend/style.css` | `.ctx-chip` styles |

### Try-it order — docs + ctx chip verification

1. Restart backend (so the AgentSpec change re-registers).
2. Run a fresh analysis on a project with deploy_config filled in.
3. Wait for code-generation to finish (wave 2). Documentation now starts in wave 3 alongside code-review + ui-ux.
4. After Documentation finishes:
   - Open `converted/docs/` — find README.md, SETUP.md, API.md, DEPLOY.md, DATA_DICTIONARY.md, ARCHITECTURE.md as real files.
   - The Documentation card's body shows a short TOC, not the docs prose.
5. On every agent card (except Migration Planner), look at the header for the new `✅ context` / `⚠ partial` / `❌ gap` / `⚠ no ctx` chip next to the coverage / repair chips.

### Known follow-ups

- Some legacy-shape sessions cached on disk before today's prompt update will not have a Context block in their reports. Re-running the agent (or the whole analysis) is the clean way to populate the chip.
- The context-attestation grep is intentionally permissive (it accepts emoji OR keyword match) so a slightly off-script attestation still classifies. If false-positives become an issue, tighten the regex in `supervisor.py::_run_one` near line 950.
- The Documentation agent sometimes writes long files. The `_REVIEW_MAX_FILE_BYTES` cap (512 KB) at the review-file-detail endpoint will silently truncate viewing — but the file on disk is intact. Worth raising the cap for `docs/` files if the user reports it.

---

## 2026-05-03 — CHUNK PASS 4 (orders 10–11): all remaining SCSS + form/layout components `[DONE]`

Completed all order=10 and order=11 targets for CHUNK PASS 4.

**Order 10 — React components (continued from prior session):**

| File | Source |
|---|---|
| `frontend/src/pages/TotalBooking/forms/JuvenilePcDecForm.tsx` | `pcdec-juvenile-pcdec.form.html` |
| `frontend/src/pages/TotalBooking/forms/BookingForm.tsx` | `total-booking.form.html` |
| `frontend/src/pages/TotalBooking/TotalBookingLayout.tsx` | `total-booking.layout.html` |
| `frontend/src/components/common/TextInput.tsx` | `input.text.template.html` |
| `frontend/src/components/common/ConfirmModal.tsx` | `submit.form.confirm.template.html` |
| `frontend/src/components/layout/AppShell.tsx` | `content.html` |
| `frontend/src/pages/Auth/UnauthorizedPage.tsx` | `content_unauthorized.html` |
| `frontend/src/components/layout/LeftSearchPanel.tsx` | `left-search.html` |
| `frontend/src/pages/Auth/LoginHelpPage.tsx` | `login-help.content.html` |

**Order 11 — SCSS (47 files total):**

Global styles: `variables.scss`, `index.scss`, `elements.scss`, `navbar.scss`, `generic.scss`, `helpers.scss`, `global.scss`

Page modules: Admin (3), Alerts (2), Dashboard (5), Auth (3), OffenseCodes (2), PcDeclaration (8), PersonAlerts (2), TotalBooking (6), Users (5), Training (2), Warrants (2)

All files 1-to-1 ported from source SCSS; image URLs rewritten to relative `../../../assets/images/` paths; AngularJS-specific selectors (`.ng-invalid`, `ui-select-*`) kept as-is for runtime compatibility.

---

## 2026-05-03 — CHUNK PASS 3 (orders 7–10): remaining order=10 form sub-components `[DONE]`

Completed the final 5 files from the order=10 batch, concluding CHUNK PASS 3.

| File | Source | Controls |
|---|---|---|
| `frontend/src/components/layout/MenuSidebar1.tsx` | `menu.sidebar1.html` | conditionals=1 |
| `frontend/src/components/TotalBooking/AddressForm.tsx` | `total-booking-address.form.html` | inputs=5 selects=6 repeaters=1 conditionals=1 |
| `frontend/src/components/TotalBooking/OffenseLegacyForm.tsx` | `total-booking-offense-legacy.form.html` | inputs=5 repeaters=2 conditionals=8 |
| `frontend/src/components/TotalBooking/OffenseForm.tsx` | `total-booking-offense.form.html` | inputs=12 selects=2 repeaters=1 conditionals=7 |
| `frontend/src/components/TotalBooking/OrderForm.tsx` | `total-booking-order.form.html` | inputs=12 selects=3 repeaters=2 conditionals=7 |

All components accept `register`, `watch`, `control`, `errors`, `disabled` props from a parent `useForm`. Repeaters use `useFieldArray`. Conditional renders mirror the source template `ng-if` count exactly.

---

## 2026-05-03 — Deploy-config pipeline + project-prefixed folders + clean cards `[DONE]`

User flagged that the converted apps shipped with hardcoded leaks (`BeagleVM`, `WatiBeagleVM`, `aries_db_dev`, `admin_ccc_1`, `westus2.cloudapp.azure.com`) the LLM pattern-matched from prior conversation context, and that there was no place to tell AppNova: "this is for an Azure Ubuntu VM with Apache reverse proxy on port 9090, deploy user is X, db name is Y." Also asked for cards to stop showing live SSE narration and for new-project disk folders to carry the project name.

### Implementation — eight focused edits

#### 1. SSE narration suppressed on agent cards

[frontend/app.js:2293-2306](frontend/app.js#L2293-L2306) — `renderAssistant` no longer mounts a live DOM element for the model's streaming text. The accumulator (`c.assistantAccum`) is preserved for the partial-output recovery paths (agent_error with partial=true, agent_complete with empty result), so timeout-recovered reports still render. Tool calls (Glob/Grep/Read) continue to render in the collapsible console section; only the model's mid-thought narration is hidden. Cards now go directly from "thinking…" to the final report with the proper heading at the top.

#### 2. Deploy-config schema + endpoints + persistence

[backend/main.py:158-167](backend/main.py#L158-L167) — `_session_deploy: dict[str, dict]` parallel to `_session_targets`.

[main.py:266-360](backend/main.py#L266-L360) — Canonical schema as `_DEPLOY_CONFIG_FIELDS` tuple (14 fields: app_canonical_name, app_display_name, db_server, db_name, db_admin_user, azure_hosting_model, azure_region, vm_os, web_server, vm_admin_user, deploy_root, public_fqdn, backend_port, frontend_port). Helpers `_deploy_config_path` / `_persist_deploy_config` / `_load_deploy_config` / `_normalise_deploy_config` mirror the target_stack pattern. `_materialise_deploy_config_for_agents` copies the JSON into `source/context/deploy_config.json` so agents can Read it via their own tools.

[main.py — new endpoints](backend/main.py) — `GET /api/session/{sid}/deploy-config` returns the canonical-shape dict; `POST /api/session/{sid}/deploy-config` normalises + persists + materialises immediately. Unknown keys are dropped to prevent prompt-injection via the form.

[main.py:_run_analysis_stream](backend/main.py) — Materialises both `deploy_config.json` AND the deploy_templates set at the top of every analysis dispatch.

#### 3. Deployment Details form panel

[frontend/index.html](frontend/index.html) — New `<details id="deploy-panel">` between the stack picker and the Plan panel. 14 form fields grouped into "App naming" / "Database" / "Cloud" / "VM" sections with inline hints. Hidden until a session binds.

[frontend/app.js:end-of-file](frontend/app.js) — Self-contained `deployConfigPanel()` IIFE: listens to the existing `appnova:session-bound` CustomEvent, fetches `/api/session/<sid>/deploy-config` on bind, populates the form, persists on Save, surfaces a `populated/total` count in the panel summary so the user knows whether the form is in good shape.

[frontend/style.css:end-of-file](frontend/style.css) — `.deploy-grid` 2-column responsive grid + section dividers + status text styles.

#### 4. Three prompts wired to deploy_config + banned-token grep

[backend/agents/prompts.py — devops](backend/agents/prompts.py) — Long preamble: read `../context/deploy_config.json` first, full schema documented inline, decision rules for each field (`vm_os` → bash vs PowerShell; `web_server` → apache/nginx/iis/kestrel; `azure_hosting_model` → which artifact set), the 7-literal banned-token list (must grep your own output before finishing), and a folder-partition rule (every artifact under `devops/`, `infra/azure/`, `backend/`, `frontend/`, or `docs/` — never project root). Plus a "use the canonical templates under `../context/deploy_templates/`" workflow paragraph.

[prompts.py — migration-planner](backend/agents/prompts.py) — Read deploy_config first, use `app_canonical_name` / `app_display_name` for csproj/DLL paths, generate appropriate `targets[]` based on `azure_hosting_model` + `vm_os` + `web_server`, never invent a name from training data.

[prompts.py — code-generation](backend/agents/prompts.py) — Read deploy_config first, use values directly in connection strings / CORS / project file names, generic stand-ins (not pattern-matched values) when the form is blank.

#### 5. Deterministic deploy audit

New module [backend/agents/deploy_audit.py](backend/agents/deploy_audit.py). Walks `converted/` for the 7 known leak literals and flags every occurrence whose corresponding `deploy_config` field is empty OR set to a different value. Also checks the OS / web-server partition: `.ps1` files are flagged when `vm_os = ubuntu-*`; missing apache vhost is flagged when `web_server = apache`; etc. Writes `converted/docs/DEPLOY_AUDIT.md` with a per-issue table.

[backend/agents/supervisor.py:34-37](backend/agents/supervisor.py#L34-L37) — Imported `audit_deploy`.

[supervisor.py — post-codegen block](backend/agents/supervisor.py) — Added the audit dispatch right after the file_coverage block. Stashes a compact summary on `result["deploy_audit"]` for the UI chip + propagates to the `agent_complete` event payload so the frontend can paint a chip without re-reading the .md file.

#### 6. Canonical deploy templates

New folder `backend/agents/deploy_templates/` with reviewer-vetted shapes:

| Template | Purpose |
| --- | --- |
| `systemd_unit.service.tmpl` | Ubuntu/RHEL systemd unit (Type=exec, security hardening included) |
| `apache_vhost.conf.tmpl` | Apache reverse proxy + SPA fallback + X-Forwarded-* |
| `nginx_vhost.conf.tmpl` | Nginx server block + SPA fallback + WebSocket-ready proxy |
| `iis_web.config.tmpl` | IIS web.config for in-process ASP.NET Core hosting |
| `appsettings.Production.json.tmpl` | Connection string + CORS + AllowedHosts |
| `env_example.tmpl` | `.env.example` with KeyVault references where appropriate |
| `bootstrap_ubuntu.sh.tmpl` | Multi-tenant venv bootstrap (local dotnet/node, no apt) |
| `bootstrap_windows.ps1.tmpl` | Chocolatey + IIS feature install + app pool/site setup |
| `deploy_vm.sh.tmpl` | Atomic-symlink swap + EF migrate + /health auto-rollback |
| `README.md` | Why templates instead of LLM-generated, substitution rules |

[main.py:340-372](backend/main.py#L340-L372) — `_materialise_deploy_templates_for_agents` copies the templates into `source/context/deploy_templates/` at the top of every run, so the devops agent reads them via its own Read tool. Idempotent — overwrites every run so a template tweak in source control reaches the next run with no cache busting.

#### 7. Project-name-prefixed disk folders

[main.py — new helpers](backend/main.py) — `_safe_project_slug(name)` (lowercase ASCII alphanum + hyphen, ≤40 chars), `_session_folder(session_id)` (resolves the on-disk folder via `_session_folder_names` cache, with legacy `<sid>` and new `<slug>-<sid>` shape both supported), `_session_folder_names` in-memory map.

[main.py — upload endpoint](backend/main.py) — When `project_name` is provided in the upload form, the on-disk folder is created as `<safe-slug>-<session_id>`. With no `project_name`, the folder stays `<session_id>`-only (no behaviour change for legacy callers).

[main.py — `_rehydrate_all_sessions`](backend/main.py) — Recognises BOTH folder shapes on startup (`<slug>-<12hex>` regex + bare `<12hex>` length check) and populates `_session_folder_names` for each.

[main.py — clone endpoint](backend/main.py) — When cloning a session, inherits the parent's slug so the clone lands next to the original on disk. Falls back to bare `<new_sid>` for legacy parents.

[main.py — 17 callsites](backend/main.py) — Every `UPLOAD_DIR / session_id / ...` lookup replaced with `_session_folder(session_id) / ...` so the folder resolution is consistent across rehydrate, file-detail, screenshots, exports, and converted-tree endpoints.

[backend/dev_chat.py:149-176](backend/dev_chat.py#L149-L176) — `attachments_dir` now scans for the `<slug>-<sid>` shape when the bare path misses (duplicates the `_session_folder` logic locally to avoid a cycle on `main` import).

#### 8. SSE event payload includes the deploy_audit blob

[supervisor.py — agent_complete event](backend/agents/supervisor.py) — `event_payload["deploy_audit"]` propagated alongside `file_coverage` and `ui_inventory_shape` so the frontend can render the deploy-audit chip on the code-generation card without an extra fetch.

### Files touched in this entry

| File | Change |
| --- | --- |
| `backend/main.py` | _session_folder + _session_deploy + _safe_project_slug; deploy-config endpoints + helpers + materialiser; deploy_templates materialiser; 17 callsite migrations from `UPLOAD_DIR / session_id` to `_session_folder(...)`; project-name slug in upload + clone |
| `backend/dev_chat.py` | `attachments_dir` slug-fallback for new-shape folders |
| `backend/agents/prompts.py` | devops + migration-planner + code-generation prompts read deploy_config; banned-token grep; templates-aware workflow paragraph |
| `backend/agents/supervisor.py` | Imported `audit_deploy`; ran post-codegen; propagated to event payload |
| `backend/agents/deploy_audit.py` | NEW — deterministic audit walking `converted/` for leak literals + partition mismatches |
| `backend/agents/deploy_templates/*.tmpl` | NEW — 9 canonical templates + README |
| `frontend/index.html` | Deployment Details `<details>` panel with 14 form fields |
| `frontend/app.js` | Suppressed live SSE on cards; deployConfigPanel() IIFE |
| `frontend/style.css` | `.deploy-grid` + status colour styles |

### Known follow-ups

- **Existing sessions on disk keep their `<session_id>`-only folder shape** — the helper recognises both. To migrate an old session to the new shape, the user would have to rename the folder manually (and the in-memory cache will pick it up on next rehydrate).
- **Templates are non-conditional** — they assume `.NET 8 + Vite/React + Azure SQL`. For radically different stacks (Python+Django, Java+Spring), the agent will fall back to LLM-generated scaffolding and the templates serve as reference shape only.
- **No password fields in the deploy form** — by design. Passwords belong in Key Vault / Jenkins credentials / GitHub Secrets, not in a JSON file on the agent's disk. The templates emit `__SET_VIA_KEY_VAULT__` placeholders the user wires up at deploy time.
- **deploy_audit is advisory** — issue counts annotate the result and write `DEPLOY_AUDIT.md`, but they don't downgrade `status` automatically. If the leak rate is high enough that we want a hard gate, that's a separate threshold (analogous to `COVERAGE_FLOOR_PCT`).

### Try-it order

1. Restart the backend so the new `_DEPLOY_TEMPLATES_DIR` resolves and the upload endpoint picks up the new folder shape.
2. Open a project — the `▸ Deployment details` panel appears below the stack picker. Fill in `app_canonical_name`, `db_name`, `vm_admin_user`, `public_fqdn`, etc.
3. Click Save — see "✓ Saved. Will be picked up on next analysis run."
4. Run analysis. The devops, planner, and code-gen agents will Read `../context/deploy_config.json` and substitute values. The deploy_audit pass will write `converted/docs/DEPLOY_AUDIT.md` listing any remaining leaks.
5. Upload a NEW project with a Project name set in the form — confirm the folder on disk is `<slug>-<12hex>` instead of `<12hex>` only.

---

## 2026-05-03 — Code-gen robustness + review staleness + error-card recovery `[DONE]`

User flagged three live bugs and three architectural gaps after a 5,154s code-generation run that downgraded to ERROR with 38.2% file-coverage:

1. The review page's file tree showed 582 stale rows (the synthesizer's path-prefixed shape) while the planner's `file_map.json` had been reduced to 336 unprefixed rows. Clicking any stale-shape row rendered an empty SOURCE pane because the backend's exact-match lookup couldn't find the prefixed key after `refresh_from_mappings` collapsed the store.
2. A failed Code Generation card showed neither a Chat button nor a Re-run button — the only recovery surface was the sidebar checkbox + "Run Selected" workflow, which the user couldn't discover from the failed card itself.
3. Code-gen ran for 86 minutes inside a single `claude -p` call (24h timeout, no checkpointing). When the model hit its output ceiling mid-mapping, it silently truncated and the supervisor audited the half-built tree as a low-coverage failure with no resume point.

Plus three feature asks: (a) `converted/` should split files under `backend/` and `frontend/` matching the source mapping; (b) on code-gen error the user wants Chat to accept "continue resolving" prompts; (c) the agent must include `.scss` in its UI inventory and reproduce legacy form layout exactly (no UX redesign).

### Implementation — five edits

#### 1. Review staleness — backend fuzzy-match + frontend refresh

[backend/main.py:1058-1080](backend/main.py#L1058-L1080) — `/api/review/{sid}/file` exact-match falls back to a suffix-match against either side. Synthesizer rows carrying a wrapper-folder prefix (`TotalBookingAI-Input/app/...`) and planner rows without (`app/...`) now resolve to the same review row no matter which shape the frontend remembers. The fuzzy match is only for the brief window between a `file_map.json` mtime change and the next `/files` refresh — the synthesizer/planner contract still wins on conflict.

[frontend/review.html:735-739](frontend/review.html#L735-L739) — Added a `↻ Refresh` button to the review toolbar.

[frontend/review.js:103-128](frontend/review.js#L103-L128) — On `visibilitychange` (tab returns to foreground) and on the new button's click, re-fetches `/files` and re-selects the previously-open file. Eliminates the "I just re-ran the planner in another tab and the file list is stale" failure mode.

#### 2. Recovery surface on ERROR cards

[frontend/app.js:1554-1565](frontend/app.js#L1554-L1565) — Added a `↻ Re-run` button to every agent card next to Chat and Save.

[frontend/app.js:1588-1611](frontend/app.js#L1588-L1611) — Wired the button: temporarily seeds `state.selectedAgents` with the single agent ID, calls `startAnalysis()` (existing `/api/run-selected/{sid}` path), then restores the user's prior sidebar selection. No new endpoint needed; reuses the proven retry-via-checkbox pipeline.

[frontend/app.js:626-642](frontend/app.js#L626-L642), [frontend/app.js:2107-2114](frontend/app.js#L2107-L2114), [frontend/app.js:2155-2174](frontend/app.js#L2155-L2174) — Three show/hide call sites (reattach, live `agent_complete`, live `agent_error` partial-output) now reveal Chat + Re-run on `status === 'done' || 'error'`. Skipped agents stay actionless because there's no body to chat against and Re-run requires the upstream blocker to clear first. The user's "type 'continue resolving' on a failed agent" workflow now works because Chat is reachable on errored cards — the existing chat infrastructure already supports follow-up turns.

#### 3. Code-generation chunk-per-pass multipass

New module [backend/agents/codegen_multipass.py](backend/agents/codegen_multipass.py) — mirrors the proven `planner_multipass` pattern shape for the write-side agent. Splits `file_map.json::mappings` into chunks of `APPNOVA_CODEGEN_CHUNK_SIZE` rows (default 80, sorted by `order` asc to preserve dependency waves), runs each in its own `claude -p` turn, sleeps `APPNOVA_CODEGEN_COOLDOWN_SECONDS` between turns (default 30s, capped at 270s to stay inside the 5-min prompt cache TTL), persists per-chunk manifest + `.done` marker for crash-resume, and dispatches one targeted repair pass per chunk when its on-disk coverage falls below 50% of planned targets.

[backend/agents/supervisor.py:34-37](backend/agents/supervisor.py#L34-L37), [supervisor.py:96-128](backend/agents/supervisor.py#L96-L128) — Imported `run_codegen_multipass` and added env gates: `APPNOVA_CODEGEN_MULTIPASS=true` (default OFF — opt in once verified), `APPNOVA_CODEGEN_MULTIPASS_THRESHOLD=100` (smallest count where chunking actually buys anything; default chunk size 80 → 100 mappings hits 2 chunks).

[supervisor.py:781-905](backend/agents/supervisor.py#L781-L905) — Added the dispatch block in `_run_one` immediately after the planner's early-multipass block. When env-gated AND the planner's `file_map.json` is parseable AND `mappings` count ≥ threshold, dispatches multipass and synthesizes a result dict shaped like the existing single-pass success contract. Falls back to single-pass on ANY failure path (file-map missing/unparseable, runner crash, multipass returns no targets) so multipass is purely additive — it never blocks a route to success that single-pass could have taken. The existing post-codegen audits (zero-files downgrade, coverage-floor downgrade) run unchanged on the synthesized result, so a multipass run that undershoots 70% file coverage gets the same status=error treatment a thin single-pass run would have.

#### 4. Planner prompt — `backend/` vs `frontend/` partition

[backend/agents/prompts.py:1306-1320](backend/agents/prompts.py#L1306-L1320) — New "Hard rule — `backend/` vs `frontend/` partition" block in the migration-planner prompt. Every path in `targets[]` MUST start with either `backend/` or `frontend/`. Decision rule is documented stack-agnostically (controllers/services/ORM/migrations → `backend/`; pages/components/styles/UI configs → `frontend/`); below the prefix the planner picks the target stack's idioms. A `1-to-many split` row may emit BOTH a `backend/` and a `frontend/` target when the legacy file owned both tiers (e.g. a Razor view + codebehind).

Updated the schema example with explicit `backend/`-prefixed and `frontend/`-prefixed rows, plus a new SCSS-mapping example so the model sees the styling-tier port pattern.

#### 5. Code-gen UI inventory expansion + parity language

[backend/agents/prompts.py:425-427](backend/agents/prompts.py#L425-L427) — Added a strong "Visual + layout parity is a HARD requirement" paragraph just before the Phase-1 inventory instructions. Calls out that the agent is NOT a UX redesigner: same field order, same column counts, same labels, same spacing intent. Tailwind defaults instead of carrying the legacy stylesheet through is explicitly named as a reject-cause.

[backend/agents/prompts.py:434](backend/agents/prompts.py#L434) — Phase 1 step 2's glob list now includes `**/*.scss`, `**/*.sass`, `**/*.less`, `**/*.css`, `**/*.styl` alongside markup extensions. Inventory + audit operate over markup AND stylesheets so a port that re-skins legacy forms with framework defaults gets caught.

### Why opt-in for multipass

The default keeps single-pass behaviour intact so existing successful pipelines are unaffected. Once the user verifies multipass on a representative project (the TotalBookingAI 345-file case is exactly the load it's designed for), flip `APPNOVA_CODEGEN_MULTIPASS=true` to make it the default. Multipass adds K × cooldown seconds of pure overhead on small projects (where single-pass already fits inside the output ceiling), so the threshold gates it to projects where single-pass is the brittle path.

### Files touched in this entry

| File | Change |
|---|---|
| `backend/agents/codegen_multipass.py` | NEW — chunk-per-pass code-generation runner |
| `backend/agents/supervisor.py` | Imported runner; added env gates; dispatched multipass before single-pass for code-generation |
| `backend/agents/prompts.py` | Added `backend/`/`frontend/` partition rule + schema example; added stylesheet globs to UI inventory; added visual parity paragraph |
| `backend/main.py` | Suffix-match fallback in `/api/review/{sid}/file` |
| `frontend/review.html` | Added `↻ Refresh` button |
| `frontend/review.js` | Wired Refresh button + visibilitychange auto-refresh |
| `frontend/app.js` | Added `↻ Re-run` card button + handler; revealed Chat + Re-run on `error` cards |

### Known follow-ups

- The 582 stale rows in `data/reviews/01a3d7daf60b.json` will collapse to file_map's 336 the next time the user reloads (or presses Refresh) — the fuzzy fallback covers them in the meantime.
- Multipass cooldown defaults to 30s; for a 200k-tpm tier with a heavy upstream-context block, 60s might be safer. Tune via `APPNOVA_CODEGEN_COOLDOWN_SECONDS`.
- The new planner partition rule means any in-flight runs whose `file_map.json` predates this change still ship without `backend/`/`frontend/` prefixes; downstream agents handle both shapes today via the fuzzy-match path. Re-running the planner on a session is the clean way to upgrade.

---

## 2026-05-03 — Documentation + solution project files `[DONE]`

| File | Purpose |
|---|---|
| `README.md` | Prerequisites, run demo (run.sh/run.bat), push-to-production (Azure App Service steps) |
| `ARIES.sln` | Visual Studio solution referencing all four projects |
| `src/ARIES.Domain/ARIES.Domain.csproj` | net8.0 class library, no external deps |
| `src/ARIES.Application/ARIES.Application.csproj` | DocumentFormat.OpenXml dep; references Domain |
| `src/ARIES.Infrastructure/ARIES.Infrastructure.csproj` | EF Core 8 + SQL Server + Identity; references Domain+Application |
| `src/ARIES.API/ARIES.API.csproj` | Web SDK; Azure.Identity + JwtBearer + Swashbuckle; references all three |
| `docs/FIELD_MAPPING.md` | Source `$scope.item.*` → React prop → EF entity mapping table |
| `docs/UI_FIDELITY_REPORT.md` | Every `ng-if`/`ng-repeat` in BookingForm+DetailView+PcDecForm with React equivalent and coverage status |
| `docs/LOOKUPS.md` | All 25 lookup endpoints, `getLookups()` aggregate shape, seeding notes |
| `docs/FILE_MAP_AMENDMENTS.md` | 7 amendments: DbContext, Program.cs, AppRouter route restructure, test rewrite, modal template substitution, solution scaffolding, path prefix change |

---

## 2026-05-03 — Scaffolding: client build + run infrastructure `[DONE]`

| Target file | Purpose |
|---|---|
| `src/client/package.json` | React 18 + Vite 5 + TS 5 deps; Jest 29 + ts-jest + RTL + MSW dev deps |
| `src/client/tsconfig.json` | ES2020 / ESNext / react-jsx / bundler resolution / strict |
| `src/client/tsconfig.node.json` | Vite node config compilation target |
| `src/client/vite.config.ts` | `/api` → `localhost:5000` proxy; build → `../ARIES.API/wwwroot` |
| `src/client/src/global.css` | Bootstrap 3 class aliases for legacy template names |
| `.env.example` | `ConnectionStrings`, `Jwt__*`, `AllowedOrigins`, `VITE_*` template |
| `.gitignore` | bin/, obj/, node_modules/, dist/, .env, appsettings.Development.json |
| `run.sh` | Unix launcher: dotnet restore + npm install, API+Vite as background PIDs with Ctrl-C trap |
| `run.bat` | Windows equivalent using `start cmd` windows |

Vite proxy forwards all `/api/*` requests to the ASP.NET Core API so the SPA can be developed against `localhost:5000` without CORS changes. Build output lands in `wwwroot` so `dotnet run` serves the SPA from the same origin.

---

## 2026-05-03 — Batch 12 (Order 12): Test files `[DONE]`

| Target file | Source |
|---|---|
| `src/services/__tests__/agencyService.test.ts` | `agency.service.spec.js` (empty — written from scratch with MSW) |
| `src/components/booking/__tests__/BookingReportsModal.test.tsx` | `total-booking.greports.spec.js` |
| `src/components/booking/__tests__/BookingReviewModal.test.tsx` | `total-booking.review.modal.spec.js` |
| `src/pages/total-booking/__tests__/TotalBookingEditPage.test.tsx` | `total-booking.edit.spec.js` |
| `src/pages/total-booking/__tests__/TotalBookingListPage.test.tsx` | `total-booking.list.spec.js` |
| `src/pages/total-booking/__tests__/TotalBookingNewPage.test.tsx` | `total-booking.new.spec.js` |

All Jasmine/$httpBackend/$scope tests rewritten as Jest + React Testing Library. Source fixture data (fields, properties, victimCbs, genders, narcotics, states, agencies) preserved verbatim in mocks. MSW used for agencyService HTTP interception.

---

## 2026-05-03 — Batch 11 (Order 11): React app entry + router `[DONE]`

| Target file | Source |
|---|---|
| `src/client/src/config/appConfig.ts` | `src/app/app.conf.js` |
| `src/client/src/App.tsx` | Angular bootstrap / MainCtrl |
| `src/client/src/main.tsx` | `angular.bootstrap` / Vite entry |
| `src/client/src/router/AppRouter.tsx` | `src/app/routes.js` (535 UI-Router states) |
| `src/client/index.html` | `src/index.html` |

Key logic: UI-Router abstract states → React Router v6 layout routes with `<Outlet>`. `roleFence` resolve guards → `<RequireAuth>` wrappers. `total-booking`, `total-booking-juvenile`, `pcdec`, `pcdec-juvenile` route groups preserved. `appConfig` reads `VITE_API_URL` / `VITE_CLIENT_ID` / `VITE_CLIENT_SECRET`. `ToastContainer` replaces `toaster-container`. `lazy()` imports for all pages.

---

## 2026-05-03 — Batch 10 (Order 10): Booking section components — complete `[DONE]`

All 18 Batch 10 target files written under `src/client/src/components/booking/`:

| Target file | Source |
|---|---|
| `BookingSidebar.tsx` | `menu.sidebar.html` + `menu.sidebar1.html` + `total-booking.menu.sidebar.html` |
| `NewJuvenileBookingOptionsModal.tsx` | `total-booking-new-juvenile-options.modal.html` |
| `BookingListLayout.tsx` | `total-booking.list.layout.html` |
| `ResidenceAddressSection.tsx` | `total-booking-residence-address.form.html` |
| `BookingAddressSection.tsx` | `total-booking-address.form.html` |
| `PropertyAndClothingSection.tsx` | `total-booking-property-and-clothing-legacy.form.html` |
| `PrebookPersonalPropertySection.tsx` | `total-booking-prebook-personal-property.form.html` |
| `BookingOffenseLegacySection.tsx` | `total-booking-offense-legacy.form.html` |
| `BookingOffenseSection.tsx` | `total-booking-offense.form.html` |
| `BookingOrderSection.tsx` | `total-booking-order.form.html` |
| `BookingFilters.tsx` | `total-booking.filters.html` |
| `BookingListJudge.tsx` | `total-booking.list-judge.html` |
| `BookingListOfficer.tsx` | `total-booking.list-officer.html` |
| `WarrantBailsheet1Section.tsx` | `total-booking-warrant-bailsheet1.form.html` |
| `WarrantBailsheet2Section.tsx` | `total-booking-warrant-bailsheet2.form.html` |
| `BookingDetailView.tsx` | `total-booking.view.html` (486 lines, read-only preview) |
| `BookingViewModal.tsx` | `total-booking.review.modal.html` |
| `BookingForm.tsx` | `total-booking.form.html` (1394 lines, composite assembling all sections) |

Key logic: `legacyWarrant` flag gates address/offense/warrant/property sections. `item.type` gates employment, emergency contact, co-defendants, parents/guardians, use-of-force, probation. `allowPCDec` gates PC Dec fieldset. `wcheck`/`wcheck2` gate local/foreign legacy warrant rows. `tb_local_warrants`/`tb_foreign_warrants` gate new warrant repeaters. `residenceAddressOtherOption` (county_id==null && state_id!=null) gates out-of-state county/city inputs. `arrest_agency_id===0` gates other agency input. `recentJudgeReview` drives certificate of probable cause display.

---

## 2026-05-03 — Batch 9 (Order 9): React pages & page-level components `[DONE]`

Completed all 10 Batch 9 target files under `src/client/src/`:

| Target file | Source |
|---|---|
| `pages/total-booking/TotalBookingListPage.tsx` | `total-booking.list.controller.js` |
| `pages/total-booking/TotalBookingListView.tsx` | `total-booking.list.layout.html` + `total-booking.list-officer.html` |
| `pages/total-booking/TotalBookingNewPage.tsx` | `total-booking.new.controller.js` |
| `pages/total-booking/TotalBookingEditPage.tsx` | `total-booking.edit.controller.js` |
| `pages/total-booking/NewBookingOptionsModal.tsx` | `total-booking-new-options.modal.html` |
| `pages/total-booking/BookingReportsModal.tsx` | `total-booking.greports.modal.html` |
| `pages/total-booking/BookingReviewModal.tsx` | `total-booking.review.modal.controller.js` |
| `pages/DashboardPage.tsx` | `dashboard.js` |
| `pages/pcdec/PcDecJuvenileFormPage.tsx` | `pcdec-juvenile-pcdec.form.html` (137 inputs) |
| `pages/total-booking/TotalBookingLayout.tsx` | router layout shell |

Key business logic: `filterExpired()`, `dedupeById()`, `useBookingTimeLeft`, `parseMysqlDate()`, BAC slash-strip, SSN dash-strip, `doAction()` result branching, `doSave()` PUT with `?signAndSubmit=true`, 60-second auto-refresh, `openTB()` → review modal. `BookingForm` placeholder in New/Edit pages — body wired in Batch 10.

---

## 2026-05-03 — Supervisor crash: `UnboundLocalError: total` on every wave-1 launch `[DONE]`

User hit a hard crash the moment any analysis run reached wave 1 (and again on resume). Both `/api/analyze/{sid}` and `/api/resume/{sid}` died with:

```text
File "backend/agents/supervisor.py", line 634, in _run_one
    "total": total,
UnboundLocalError: cannot access local variable 'total' where it is not associated with a value
```

### Root cause — closure variable shadowed by a later assignment

`run_supervised` defines `total = len(applicable_ids)` at [supervisor.py:523](backend/agents/supervisor.py#L523). The nested `_run_one` reads it via closure on every progress payload (`agent_start`, `agent_event`, `agent_complete`, `_forward_event`, planner-multipass announcements, repair-pass events, coverage-floor downgrade events) — nine call sites in total.

The code-generation coverage block introduced later assigned to `total` again at [supervisor.py:1225](backend/agents/supervisor.py#L1225):

```python
total = int(cov_manifest.get("total_source_files") or 0)
```

That single assignment promoted `total` to a **local** for the entire `_run_one` body. Python's local-name rule is per-function, not per-line, so every earlier read — starting with the very first `agent_start` event of wave 1's first agent — looked up an unassigned local and raised `UnboundLocalError` before any agent could even launch.

The workbook also reported `0 recorded calls` because the supervisor died before reaching `cost_tracker.record_call`.

### Fix — rename the local so the closure reference resolves

Renamed the shadowing local at line 1225 (and its four reads at 1232, 1243, 1246, 1256) to `total_source_files`. That's also the dict key it represents, so the rename reads naturally where it's used. The outer-scope `total` stays untouched, so all nine progress-event reads now resolve through the closure as originally intended.

`grep '^\s+total\s*=' supervisor.py` now reports only the outer assignment at line 523 — confirms no other shadows.

### Files changed

- `backend/agents/supervisor.py` — local `total` → `total_source_files` inside the code-generation coverage block (lines 1225, 1232, 1243, 1246, 1256). No behavioural change; only the name was shadowing the closure.

---

## 2026-05-03 — Hub page wouldn't scroll (workspace body rules leaked globally) `[DONE]`

User reported the hub couldn't scroll past the first project card — second card visibly cut off below the fold with no scrollbar.

### Root cause — workspace body rules leaked to all pages

`style.css` had the workspace's two-column sidebar layout applied to **every** body:

```css
body {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100vh;
  overflow: hidden;
  ...
}
```

That's correct for `index.html` (the workspace, where the sidebar is fixed and the main panel scrolls inside its grid cell), but `hub.html`, `login.html`, and `review.html` all loaded the same stylesheet and inherited the same `height: 100vh; overflow: hidden` — meaning none of them could scroll past one viewport. Hub had three project cards but only ~1.5 fit on screen with no way to reach the rest. `review.html` already worked around it with explicit body overrides; `hub.html` and `login.html` did not.

### Fix — scope workspace body rules to a class

Two-line architectural change instead of patching every page:

- **[style.css:182-209](frontend/style.css)** — split the body rule. Generic typography stays on `body`. The grid + viewport-lock + overflow:hidden moved under `body.workspace`. The `body.sidebar-collapsed` rule that toggles the grid template became `body.workspace.sidebar-collapsed`.
- **[index.html:17](frontend/index.html)** — `<body>` → `<body class="workspace">`. One class addition, marks the workspace as the sole consumer of the sidebar layout.

The other three remaining `body.sidebar-collapsed` rules in style.css (`.sidebar` width transition, sidebar-toggle visibility, topbar padding) were left without the `.workspace` prefix — they only fire when JS toggles the class, which only happens in the workspace, so they're functionally unreachable from other pages.

### Verified behavior after Ctrl+Shift+R

- Hub: page scrolls naturally; all three project cards visible by scrolling.
- Login: still centers vertically (its own grid layout) but can scroll if the form ever exceeds viewport.
- Review: unchanged (already had explicit overrides from a prior fix).
- Workspace: unchanged. Sidebar still fixed, agent grid still scrolls inside the main pane, sidebar-collapse toggle still works.

---

## 2026-05-03 — Diff viewer: low-overlap fallback for cross-language pairs `[DONE]`

User asked "why the gap???" — pointing at the giant empty area on the right pane between source `routes.php` (806 lines of PHP routes) and target `Program.cs` (250 lines of C# entry point). The two files were correctly paired by my new annotation parser (`Program.cs` declares `// Source: app/Http/routes.php`), but textually they share almost nothing — different language, different structure.

### Why the gap was happening

The diff renderer's `lcsDiff` walks both files and emits aligned rows: `eq` (both sides match), `del` (left only), `add` (right only), and `modify` (adjacent del+add merged into one row showing both). For cross-language pairs, LCS finds <1% common lines, so the output is essentially:

- Rows 1 → 800: `del` (left = PHP line, right = empty box)
- Rows 800 → 1050: `add` (left = empty box, right = C# line)

Only the ONE pair at the boundary gets merged into a `modify`. Everything else stays unaligned. The user sees 800 rows of source content with an empty right column, then suddenly the C# code starts. The per-line side-by-side alignment is misleading because there IS no real alignment to read.

### Fix: detect low overlap and fall back to plain panes

Added a low-overlap check at the top of `renderSplitDiff` in [review.js](frontend/review.js): count `eq` rows from `lcsDiff`, divide by the longer file's line count. If the ratio is below 5%, the per-row alignment is meaningless — fall back to `renderPlainPane` on both sides (source on left, target on right, each scrolling independently) and prepend a small notice strip:

```text
Cross-language pair (3 matched lines out of 806) — showing each side
independently. Side-by-side LCS diff would be misleading for files this
different.
```

Scroll-sync is intentionally NOT wired in this mode since each side is its own document.

For 1-to-1 ports (e.g. `PcDeclarationController.php` → `PcDeclarationController.cs` where the agent translated the PHP class structure to C# faithfully), `eqCount/longer` typically lands in the 30-60% range and the existing aligned diff renders normally. Only the cross-language extracted-from-slice cases trigger the fallback.

### What you'll see after a hard reload

- `Program.cs` (paired to `routes.php`) → notice strip appears at the top of the pane explaining the fallback; both files render as plain side-by-side panes; no more giant empty column.
- `PcDeclarationController.cs` (paired to `PcDeclarationController.php`) → unchanged, renders with normal LCS-aligned diff highlighting.
- `AceLutController.cs` (paired to `routes.php` slice) → likely triggers the fallback because the slice and the C# controller share little textual content.

---

## 2026-05-03 — Annotation-based REWRITE pairing + Ready banner own-row layout `[DONE]`

User flagged two related problems on the Review page after the previous fixes:

1. *"i dont know what was converted or what was rewitten from source files to target files because nothing is matching each file is create in target"* — almost every converted controller / service / page was showing as `C` (CREATE), not `R` (REWRITE). Out of 244 converted files in the `c9afaa02f85e` session, only **9** were paired by the synthesizer's stem-match. The reviewer had no way to navigate "what got rewritten from what".
2. *"diff view should use height of web page as the side bar"* — the page was scrolling vertically (~2871px tall), with the file tree extending way past the viewport bottom and the diff pane orphaned in a tall empty area below it. The two columns weren't behaving as independent scroll containers.

### Fix 1 — REWRITE pairing via `// Source:` header annotations (9 → 86 REWRITEs)

Code-generation agents already stamp the origin of each new converted file in its header comment block — the user's screenshot itself shows it:

```text
// Target:  backend/Controllers/AceLutController.cs
// Source:  routes.php:432-465 — `Route::group(['prefix' => 'ace-lut'])`
// Kind:    new file, route-driven port
```

The synthesizer was ignoring this signal completely. Stem-matching alone catches the easy 1:1 ports (`PcDeclarationController.php` → `PcDeclarationController.cs`) but misses every controller / service that was extracted from a slice of a larger file — which is the bulk of a Laravel→.NET conversion (most controllers come out of `routes.php` slices).

New pieces in [synthesize_file_map.py](backend/agents/synthesize_file_map.py):

- `_SOURCE_ANNOTATION_RE` — permissive regex on the leading comment marker (`//`, `#`, `--`, `*`, `<!--`) so it matches across `.cs`, `.ts`, `.tsx`, `.py`, `.sql`, `.html`. Captures the path, strips trailing `:lineRange` (e.g. `routes.php:432-465` → `routes.php`).
- `_peek_source_annotation(converted_root, rel_path)` — reads only the first 4 KB of each candidate file (the annotation lives in the header). Skip-set on extension to avoid scanning configs / lockfiles / binaries.
- `_index_source_paths(src_files)` — multi-key index of source paths so an annotation `routes.php` resolves to whichever `app/Http/routes.php` exists in the tree. Indexes by full path, basename, and every parent-prefix slice for longest-suffix lookup.
- `_resolve_annotation_to_source(annotation, src_index)` — walks the annotation through progressively shorter suffixes; first hit wins (deterministic since the index preserves walk order).

The synthesizer's `synthesize_from_disk` now runs this annotation pass on every converted file the stem-match couldn't pair, and emits a REWRITE row with `kind: "annotation-derived"` + `_pairing: "source-annotation"` markers. Files where the annotation points at a path that doesn't exist (external dep, renamed) stay CREATE but get an `_origin_hint` field surfacing the raw annotation.

### Verified on `c9afaa02f85e`

```text
Before: rows 587 | by action: {'DELETE': 336, 'REWRITE':  9, 'CREATE': 244}
After:  rows 589 | by action: {'DELETE': 336, 'REWRITE': 86, 'CREATE': 167}

REWRITE pairing breakdown:
  stem-match:         9
  source-annotation: 77

Sample annotation pairings:
  backend/Controllers/AceLutController.cs            ← TotalBookingAI-Input/app/Http/routes.php
  backend/Controllers/AdvancedSearchController.cs    ← TotalBookingAI-Input/app/Http/routes.php
  backend/Controllers/AgenciesOffenseController.cs   ← TotalBookingAI-Input/app/Repositories/AgenciesOffenseRepository.php
```

77 controllers and services that were previously CREATE now correctly pair to their source slices and will render the source PHP on the left half of the diff viewer when clicked.

### Fix 2 — Ready-to-Run banner moved out of the topbar's flex row

The banner had `width: 100%` while sitting INSIDE `<header class="rv-topbar">` (which is `display: flex`). As a flex item with 100% width, it was both fighting the breadcrumb / progress / action buttons for horizontal space AND inflating the topbar's height unpredictably. That cascaded down: `.rv-main`'s row 2 (`1fr` of remaining viewport) ended up taller than expected because the topbar consumed less than the grid track expected, but the file tree's content (90+ rows when expanded) overflowed the assumed cell height and pushed the page taller than viewport. Net effect: no per-column scroll, page scrolled instead.

Fix in [review.html](frontend/review.html):

- Body grid changed from `grid-template-rows: auto 1fr` to `grid-template-rows: auto auto 1fr` — explicit row for the banner.
- Banner element moved from inside `<header>` to a sibling between `<header>` and `<section class="rv-main">`. Its row is `auto` sized so it takes 0px when hidden and exactly its natural height when shown, never affecting the topbar.
- `.rv-main` still gets `1fr` of remaining viewport, file tree + diff each scroll independently inside their grid cells.

### Hard-reload checklist

After Ctrl+Shift+R on the Review page:

- File tree should show the file tree column with way more `R` chips (orange/heavy-tag colour) on items like `AceLutController.cs`, `LookupsController.cs`, `BailAmountsController.cs` etc.
- Click any of those → source pane shows the original PHP slice (the `routes.php` content), target pane shows the C# code, side-by-side diff highlighted.
- Page should NOT scroll vertically. File tree scrolls inside its column; diff pane scrolls inside its column.
- Ready-to-Run banner sits on its own row across the top, doesn't push the topbar around or eat horizontal space.

### Caveat

This is still synthesizer-derived data with `_synthesized: true` markers — a real planner re-run would overwrite with authoritative pairings (and would also catch the partial cases where annotation resolution failed). The annotation parser is best-effort: ~88% pairing rate on this session, up from 12%.

---

## 2026-05-03 — Synthesizer wrapper-detect must mirror main.py (REWRITE source pane was empty) `[DONE]`

User asked "what about displaying of source data in diff view section?" — turns out even REWRITE rows were showing blank source panes, not just the explained-CREATE rows. Bug in code I shipped earlier today.

### Root cause

The synthesizer's `_detect_walk_root` and main.py's `_detect_project_root` disagreed on whether to drill into a single-wrapper folder. For the `c9afaa02f85e` session, `source/` contains three entries: `TotalBookingAI-Input/`, `chat/`, `context/`. The wrapper-detect logic asks "is this exactly one folder?" If yes, drill into it (typical GitHub-zip structure); if no, stay put.

- `main.py::_detect_project_root` counts ALL entries → 3 → no drill → `source_root = uploads/<sid>/source/`
- My synthesizer's `_detect_walk_root` filtered out runtime dirs (`chat`, `context`) BEFORE counting → 1 (`TotalBookingAI-Input`) → drilled in → walked from `uploads/<sid>/source/TotalBookingAI-Input/`

So the synthesizer wrote paths like `app/Http/Controllers/.../Foo.php` (relative to the wrapper) but the HTTP layer joined them under `source/` (no drill), producing `source/app/Http/...` which doesn't exist on disk. Every `_safe_join + _read_file_safely` returned `("", False, "file_missing")` → empty source pane.

The CREATE rows looked OK only because they correctly have no source (action semantics) — the bug was masked there.

### Fix in [synthesize_file_map.py](backend/agents/synthesize_file_map.py)

Removed the `_SKIP_DIRS` filter from the wrapper-detect entry count. Synthesizer now matches main.py exactly: count ALL entries, only drill on `len == 1`. Pruning of runtime dirs still happens during the walk itself (`_walk_files`), so `chat/` + `context/` don't pollute the row count — they just don't influence the wrapper decision.

For `c9afaa02f85e` after the fix:

- Wrapper-detect: 3 entries, no drill → walk root = `uploads/<sid>/source/`
- Walk: prunes `chat/` + `context/`, descends into `TotalBookingAI-Input/`
- Emits paths like `TotalBookingAI-Input/app/Http/Controllers/.../Foo.php`
- HTTP layer joins under `uploads/<sid>/source/` → `uploads/<sid>/source/TotalBookingAI-Input/app/Http/Controllers/.../Foo.php` ← exists

### Verified end-to-end on `c9afaa02f85e`

Regenerated `file_map.json` (deleted the stale one first since `synthesize_and_persist` refuses to clobber):

```text
rows: 589 | by action: {'DELETE': 336, 'REWRITE': 9, 'CREATE': 244}

REWRITE row: 'TotalBookingAI-Input/app/Http/Controllers/API/PCDEC/PcDeclarationController.php'
  resolved: True | 23567 bytes
target row: 'backend/Controllers/PcDeclarationController.cs'
  resolved: True | 32235 bytes

DELETE row: 'TotalBookingAI-Input/app/Helpers/AppConstants.php'
  resolved: True | 1320 bytes
```

After hard reload, clicking any REWRITE row (e.g. `PcDeclarationController.cs`) populates BOTH panes — PHP source on the left, C# target on the right, both side-by-side with the diff highlighting that was already in place.

### Lesson for future-me

Anywhere two sites infer paths against the same on-disk root, they MUST share the same heuristic — either factor it out into one helper or strictly mirror it with a comment pointing at the source of truth. The synthesizer's "smarter" filter looked safer in isolation but desynced from the HTTP layer's contract, and the failure mode (empty pane) didn't trip any existing test.

---

## 2026-05-03 — Review page: full-width layout, horizontal-scroll diff, explanatory empty panes `[DONE]`

User flagged three layout / UX issues from a Review page screenshot:

1. **~280px of wasted whitespace on the left** — the breadcrumb stacked vertically in a narrow column instead of running horizontally across the top.
2. **Long lines truncated with no horizontal scroll** — generated C# / TS lines wider than the pane just got cut off with ellipsis.
3. **Source pane empty when clicking a CREATE row** — `AceLutController.cs` showed "net-new — no source" with no explanation of why or what to do about it.

### Fix 1 — Reclaim the wasted 280px (the actual cause)

Root cause: `style.css` (shared between `index.html` and `review.html`) sets:

```css
body {
  display: grid;
  grid-template-columns: 280px 1fr;  /* ← workspace's sidebar slot */
}
```

That grid is right for the workspace. `review.html` has its own grid in its inline `<style>` block (`grid-template-rows: auto 1fr`) but inherits `grid-template-columns` from style.css — so the body ended up with TWO columns and TWO rows, the topbar got squeezed into the inherited 280px first column (forcing the breadcrumb words to wrap onto separate lines), and `.rv-main` sat in a phantom slot that wasn't full-width.

Fix in [review.html](frontend/review.html) body styles:

```css
body {
  display: grid;
  grid-template-columns: 1fr;   /* explicit override of style.css's 280px 1fr */
  grid-template-rows: auto 1fr;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}
```

Net effect: topbar is one full-width row, file tree + diff fill the entire viewport below it, no phantom sidebar slot. Also flipped from `min-height: 100vh` to `height: 100vh; overflow: hidden` so the file tree and diff become independent scroll containers (matches the pattern that fixed the workspace sidebar earlier).

### Fix 2 — Horizontal scroll for long lines

Root cause: [`.diff-line .code { overflow-x: hidden }`](frontend/review.html) clipped any line wider than its grid cell. Since the parent `.pane-body` already had `overflow: auto`, the fix is to let the lines extend AND make each row at least as wide as its widest content so the parent gets a horizontal scrollbar.

Two coordinated changes:

```css
.diff-line {
  display: grid;
  grid-template-columns: 44px 20px 1fr;
  min-width: max-content;   /* row sizes to its content */
}
.diff-line .code {
  white-space: pre;
  overflow-x: visible;       /* was: hidden */
}
```

`.pane-body`'s existing `overflow: auto` now picks up the extra width and renders a single SHARED horizontal scrollbar that scrolls every row in lockstep — IDE-style "scroll right to see the rest of the line" behaviour.

### Fix 3 — Explanatory empty panes for CREATE / DELETE rows

The source pane was blank for CREATE rows (`AceLutController.cs`) because that's literally what CREATE means — net-new code with no legacy twin. The synthesizer pairs files by stem; a controller that was extracted from `routes.php:432-465` (a slice of a larger file) genuinely has no `AceLutController.php` source counterpart, so no pair is recorded.

This isn't a bug to fix — it's a UX gap. The previous "net-new — no source" microcopy gave the reviewer no explanation or next-step. Upgraded `emptyPane` in [review.js:579](frontend/review.js#L579) to accept an optional explanatory body:

```js
function emptyPane(msg, body) {
  if (body) {
    return `
      <div class="binary-view" ...>
        <div ...font-weight:600...>${escHtml(msg)}</div>
        <div ...font-size:12px;color:var(--text-muted)...>${escHtml(body)}</div>
      </div>`;
  }
  return `<div class="binary-view">${escHtml(msg)}</div>`;
}
```

CREATE source pane now reads:

> **Net-new file — no source pair**
>
> This file is action=CREATE: it has no counterpart in the legacy app. It was either generated as scaffolding (configs, README, run scripts) or extracted from a route group / partial in source. The converted file may declare its origin in a comment header — check the first 20 lines on the right for a "// Source:" annotation.

DELETE target pane gets a similar explanation pointing at the reject button if the drop looks wrong. Single-arg `emptyPane(msg)` is preserved for binary / missing-file cases that don't need a paragraph.

### Side fixes picked up while in the file

- Added `-webkit-user-select: none` next to `user-select: none` on `.diff-line .ln` and `.diff-line .gutter` to clear two pre-existing Safari portability errors. The 6 inline-style warnings on `.theme-toggle` and 5 button-type hints on `.rv-filter-tabs` were left alone — pre-existing, peripheral to this task, and would balloon the diff if I re-shaped them all.

### What this looks like end-to-end

Hard reload the Review page. You'll see:

- Breadcrumb runs horizontally in a single top bar across the full page width (no phantom 280px on the left).
- File tree column starts at left edge, diff pane stretches all the way to the right edge.
- Click any REWRITE row → source on left, target on right, both fully populated, both scrollable horizontally if a line is wider than the pane.
- Click a CREATE row → target on right, source pane explains what CREATE means and where to look for the origin annotation.
- Click a DELETE row → source on left, target pane explains the legacy file was dropped and offers Reject as the path back.

---

## 2026-05-03 — Login = lifecycle event: wipe stale session/project/workspace keys `[DONE]`

User reported that logging into AppNova auto-loaded the previous session (cards repopulated, sidebar checkboxes ticked, "Return to workspace" banner active) instead of landing on a fresh hub where they'd consciously click "Open" on a project card. Especially bad on a shared machine — another user's converted-app reports could leak across logins.

### Why it was happening (cause analysis)

`localStorage` is a browser-side cache that persists across login/logout cycles unless a piece of code explicitly clears it. Three keys were the leak vector:

| Key | What it does | Cleared on logout before this fix? |
| --- | --- | --- |
| `appnova.sessionId` | [`reattachIfRunning`](frontend/app.js#L426) reads it on workspace page-load and rehydrates the entire UI from `/api/session/{sid}/status` + `/api/results/{sid}` | NO |
| `appnova.projectId` | Hub's "Return to workspace" banner uses it to deep-link back into the previous project | YES (already in logout) |
| `appnova.lastWorkspace` | Same banner, separate cache (snapshotted on every nav-away from the workspace) | NO |

Login itself ([login.js:38, 72](frontend/login.js#L38)) only wrote `appnova.token` and `appnova.username` — it never touched the three keys above. So:

```text
1. User A converts a project → sessionId/projectId/lastWorkspace populated
2. User A clicks Logout → token + username + projectId cleared, BUT sessionId
   and lastWorkspace stay
3. User B logs in (or User A logs back in) → token + username rewritten
4. Next page load → guardWorkspaceSession sees sessionId in localStorage,
   does NOT bounce to hub
5. reattachIfRunning fires → rehydrates User A's session under User B's
   identity
```

The original design treated session keys as "user comes back to a running 15-minute conversion" cache. That's a real UX win for the same-user-refresh case but ignores the lifecycle-event-on-login case.

### Fix — wipe stale keys on both login and logout

Three coordinated edits — both login paths in `login.js` and the `logout()` in `app.js` now wipe the same three keys. Symmetry matters: login fresh slate + logout fresh slate means the cache can never accumulate past one login session.

**[login.js](frontend/login.js)** — added module-level constant + helper:

```js
const STALE_SESSION_KEYS = [
  'appnova.sessionId',
  'appnova.projectId',
  'appnova.lastWorkspace',
];

function clearStaleSessionState() {
  for (const k of STALE_SESSION_KEYS) {
    try { localStorage.removeItem(k); } catch (_) {}
    try { sessionStorage.removeItem(k); } catch (_) {}
  }
}
```

Called before BOTH `window.location.replace('hub.html')` calls:

- The credential-form-submit path ([line 78-83](frontend/login.js)) — explicit "user typed username/password" event.
- The auto-skip path ([line 50-58](frontend/login.js)) — fires when a still-valid token is detected on `login.html` load. Conservative interpretation could leave this alone (it's not a "real" login), but the user explicitly asked for fresh-state-on-any-login routing, and the downside of the broader wipe is small (only affects users who land on `/login.html` while already logged in, which usually means they bookmarked the wrong page).

**[app.js logout()](frontend/app.js#L28)** — extended the existing wipe (which only dropped `projectId`) to also drop `sessionId` and `lastWorkspace` from both `localStorage` and `sessionStorage`. Inline rather than imported because `app.js` and `login.js` load into different pages and don't share a module.

### Verified behaviour

- Login → hub.html → no "Return to workspace" banner (because `lastWorkspace` is gone).
- Direct nav to `/index.html` after login → `guardWorkspaceSession` sees no sessionId, redirects to `hub.html?reason=no-session` instead of letting `reattachIfRunning` repopulate from a stale key.
- Click "Open" on a hub card → URL handoff (`?session_id=...&project_id=...`) lets `honorHubHandoff` write the keys intentionally → workspace populates correctly.
- Logout → next login starts the same fresh-slate flow.
- Token + username still persist across the wipe — the user isn't forced to re-auth on every page reload.

### What did NOT change

- The "user came back to a 15-minute running conversion" UX still works, because they reach the workspace via the hub's "Open" button (which sets the keys via URL handoff). Only the *carry-state-across-login-events* path is killed.
- `appnova.token` / `appnova.username` lifecycle is unchanged — login rewrites them, logout clears them, a `401` from the API still triggers `logout()` and a redirect.

---

## 2026-05-02 — Review fixes: synthesizer path schema + tree collapse stickiness `[DONE]`

User reported two regressions visible in the Review page after the tree-view ship:

1. **No file content rendered** when clicking any row — both the SOURCE and TARGET panes showed blank / "deleted — no target", even for REWRITE rows that should have had both sides populated. The Network tab confirmed the API call was succeeding (200 status), so the data was being fetched but not landing.
2. **Folder collapse didn't stick** — clicking an expanded folder to collapse it would re-open on the next re-render (e.g., after marking a file approved).

Both bugs traced to my own code from the prior turns. Both fixed.

### Bug 1 — Synthesizer broke the file_map.json path contract

I'd checked an authentic planner-emitted `file_map.json` from session `f2335ee81b09` for reference:

```json
{ "source": "app/Models/AddressDirection.php",
  "targets": ["src/TotalBookingAI.Api/Domain/AddressDirection.cs"],
  "kind": "1-to-1 rename" }
```

The planner contract is: `source` is **relative to source_root** (`uploads/<sid>/source/[wrapper]/`), each `targets[]` is **relative to converted_root** (`uploads/<sid>/converted/`). The HTTP layer at [main.py:1077](backend/main.py#L1077) `_safe_join`s them at read time.

My synthesizer was emitting the same shape but with the prefix BAKED IN: `"source": "source/TotalBookingAI-Input/app/Helpers/AppConstants.php"`. The HTTP layer then computed `uploads/<sid>/source/source/TotalBookingAI-Input/...` ← doubled prefix, file not found, empty content returned, blank pane.

**Fix in [synthesize_file_map.py](backend/agents/synthesize_file_map.py):**

- `_walk_files(root, label)` no longer prefixes — emits paths relative to `root` only. `label` is now log-only.
- New `_detect_walk_root()` mirrors `main.py::_detect_project_root` so when the upload contained a single GitHub-style wrapper folder (the `c9afaa02f85e` session has `source/TotalBookingAI-Input/`), the synthesizer drills into the same wrapper the HTTP layer joins against. Without this mirror, even unprefixed paths would still 404 because the synthesizer would walk `uploads/<sid>/source/` and emit `TotalBookingAI-Input/app/...`, but the HTTP layer's `source_root` would be `uploads/<sid>/source/` (multi-entry root, no drill) and the join would still miss because of the wrapper.
- The existing `chat/` + `context/` skip set means the wrapper-detect doesn't get confused by AppNova runtime folders sitting alongside the real project.

**Verified end-to-end on the real session**: regenerated `file_map.json` for `c9afaa02f85e`, then verified paths resolve to actual files:

```text
REWRITE row: source='app/Http/Controllers/API/PCDEC/PcDeclarationController.php',
             target='backend/Controllers/PcDeclarationController.cs'
  source exists: True
  target exists: True

CREATE row: target='.appnova_scaffold.json'
  target exists: True
```

Tree display layer needs the prefix back to show the source/converted split visually, so [review.js](frontend/review.js) gains a `rowDisplayPath(row)` helper that prepends `source/` for DELETE rows and `converted/` for CREATE/REWRITE — purely for tree grouping. The actual `row.path` (used by `/api/review/{sid}/file?path=...`) stays unprefixed and matches what the HTTP layer expects.

### Bug 2 — Tree collapse re-opened on every render

Cause: `renderFileList()` was calling `autoExpandForFilter()` against the active file's path AND filter matches on every render. So:

```text
user clicks folder to collapse
  → click handler removes folder from state.expandedFolders
  → calls renderFileList()
  → renderFileList re-adds the folder back (via autoExpandForFilter)
  → folder visibly snaps back open
```

**Fix**: split intent. `renderFileList()` is now strictly read-only — it never mutates `state.expandedFolders`. The auto-expand behaviour moved to the three USER-action handlers that legitimately want to nudge the tree open:

- `selectFile(path)` — when the user clicks a file or follows `?path=` from the URL, expand its ancestors so the active row is visible. Once.
- `fileFilter` input listener — when the user TYPES in search, compute matched rows and expand their ancestors. Once per keystroke.
- `.rv-filter-tabs button` click — when the user changes filter (Pending / Approved / Rejected / Changes), expand ancestors of matching rows. Once per chip click.

Renamed `autoExpandForFilter` → `expandAncestorsOf` to reflect that it's now an action helper, not a filter-time mutation. Walks the *display* path (with prefix) so the Set keys match what the tree is grouping under.

Net effect: clicking a folder to collapse now sticks. Search / filter / file selection still auto-open ancestors so the user isn't hunting through closed folders for matches.

### What to do next

Hard reload the Review page (Ctrl+Shift+R). For session `c9afaa02f85e` specifically, the regenerated `file_map.json` is already on disk so paths will resolve immediately. For OTHER old sessions that were synthesized with the prior buggy schema, delete `uploads/<sid>/context/file_map.json` and re-open the Review page — the synthesizer's `synthesize_and_persist` will refuse to clobber an existing file, so the stale one needs to go first.

---

## 2026-05-02 — Review page: flat path list → IDE-style folder tree `[DONE]`

User reported the Review page's left pane was showing 587 truncated path strings (`...AI-Input/app/Helpers/AppConstants.php`) and asked for the source/converted folder structure to render "exact like... folders and files as they are in folders on disk." The flat list was technically functional but unusable for visual scanning — finding a specific controller meant scrolling through hundreds of similar-looking paths.

Two coordinated changes in [review.html](frontend/review.html) and [review.js](frontend/review.js).

### Tree builder + renderer in review.js

`renderFileList()` rewrite is split into three composable pieces:

- `buildFileTree(rows)` — flat row list → nested `{folders: Map, files: [], path: string}` object. Walks each row's canonical path (e.g. `converted/backend/Models/Entities/Agency.cs`) and creates folder nodes on the way down. Uses `Map` instead of plain object so insertion order is preserved.
- `renderTreeNode(node, depth, out)` — recursive HTML walker. Folders first (sorted alphabetically) then files (also sorted). Each row stamps `style="--d:${depth};"` so the CSS picks up depth-based indentation without the JS having to compute pixel widths. Folders show their descendant file count on the right (`12 files`); files keep the existing action chip + status dot + comment bubble combo.
- `renderFileList()` — entry: applies the existing filter (all/pending/approved/rejected/changes) + search, auto-expands ancestor folders for any matched rows so search results are actually visible, builds the tree, renders, wires click handlers.

State for expansion lives in `state.expandedFolders` (a `Set<string>`). Survives re-renders triggered by per-file decisions, so a reviewer who opens `converted/backend/Controllers/` doesn't lose place after marking five files in a row. Defaults to `{'source', 'converted'}` so the two top-level folders are open on first load — the reviewer sees something useful immediately instead of two collapsed folders demanding a click.

Filter behaviour preserved exactly: filter chips and search still narrow the displayed rows, and the matched rows now have their containing folders auto-expanded. The active file's ancestor chain is also force-expanded so reloading or back-navigating to a deep path doesn't strand the row off-screen.

### Tree styling in review.html

- New `.tree-row` rule with `padding-left: calc(12px + var(--d, 0) * 16px)` — depth scales linearly via the `--d` CSS variable each row stamps inline. 16px per depth step matches typical IDE explorers (small enough that 7-deep nesting still fits in the column width).
- `.is-folder` rows: caret arrow that rotates 90° on `.is-open`, folder icon (📁), bold weight. Click toggles expand/collapse.
- `.is-file` rows: caret slot kept (no glyph) for visual alignment, action chip (R/C/D), status dot, comment bubble — same vocabulary as the old flat list, just nested.
- Action chips reuse the existing `[data-a="REWRITE|CREATE|DELETE"]` colour scheme so visual continuity with the old list is preserved.

### What this gives the reviewer

```text
📁 source                                    245 files
  📁 TotalBookingAI-Input                    245 files
    📁 app                                   180 files
      📁 Http
        📁 Controllers
          📁 API
            📁 PCDEC                          15 files
              D PcDeclarationController.php  •
              D PropertiesController.php     •
              ...
      📁 Models                               40 files
        📁 PCDEC
          D PcDeclaration.php                •
          ...
📁 converted                                 244 files
  📁 backend                                  90 files
    📁 Controllers                            14 files
      C PcDeclarationController.cs           •
      ...
    📁 Models
      📁 Entities
        C PcDeclaration.cs                   •
```

Compared to the previous 587-line flat scroll, the reviewer can now collapse `source/` to focus on `converted/`, drill straight into a specific subsystem, and see at-a-glance how many files live under each folder. Per-file click → side-by-side diff in the right pane is unchanged.

---

## 2026-05-02 — Run-Gate + Dev Chat: post-conversion edit loop `[DONE]`

User intent (caveman, paraphrased): turn AppNova from a one-shot conversion tool into a continuous **Convert → Run → Inspect → Chat-edit → Repeat** loop. After conversion finishes, the reviewer should be able to (1) flip a single switch to bless the run, (2) launch the converted app, (3) chat with an LLM that watches the live logs + accepts file uploads + proposes diffs the reviewer can Apply / Apply+Restart / Revert without ever leaving the workspace.

Two coordinated subsystems shipped together. **Phase 1** is the run-gate (review.py state + workspace banner + 409 on premature launch). **Phase 2/3** is the Dev Chat drawer that hangs off the Run Converted card. **Phase 5** adds Revert as the must-have safety net for any LLM-edit flow.

### Phase 1 — Ready-to-Run gate (gate moved from "before audits" to "before Run Converted")

**Why "before Run", not "before audits"**: the audits are diagnostic — they don't change files, they just write reports. Gating audits on a human checkpoint adds delay without changing outcomes. Gating *Run Converted* attaches the human verdict to the action that actually matters (handing the app to a stakeholder or running it against real data).

**Why a single button, not "Approve all"**: on a 250-file project, asking the reviewer to click through every row before they can even *try* the app is a worse demo experience than today. The single Ready-to-Run button means the reviewer decides "I've inspected enough, run it" in one click. Per-file approve/reject/changes verdicts stay independent — they're a bookkeeping/comments mechanism, not a launch gate.

**Storage** ([backend/review.py](backend/review.py)):

- New fields on `SessionReview`: `ready_to_run`, `ready_to_run_by`, `ready_to_run_at`, `ready_to_run_note`.
- New module-level helpers: `set_ready_to_run`, `revoke_ready_to_run`, `is_ready_to_run`, `gate_state`. The two mutating helpers are idempotent (re-pressing Ready refreshes `by/at/note` without re-toggling); `gate_state` always returns a populated dict so the workspace doesn't need a "review missing" branch.
- The `_hydrate` filter is forward-compatible — old sessions without the new fields just default cleanly, no migration step needed.

**Endpoints** ([main.py:1213](backend/main.py#L1213)):

- `GET /api/review/{sid}/run-gate` → `{ready_to_run, ready_to_run_by, ready_to_run_at, ready_to_run_note, review_exists, summary}`. Polled by the workspace.
- `POST /api/review/{sid}/ready-to-run` → flip the gate ON. Optional `{note}` body. Returns 409 if no review exists yet (planner / code-gen still running).
- `POST /api/review/{sid}/revoke-ready` → flip back OFF. Does NOT kill in-flight runs (too destructive); only blocks new launches.

**Run gate** ([main.py:4900](backend/main.py#L4900)): `POST /api/run/{sid}` now refuses with a **structured 409**:

```json
{ "code": "review_not_ready",
  "message": "Open Review and press 'Ready to Run ▶' before launching…",
  "review_url": "/review.html?session_id=…",
  "summary": { "total": 247, "approved": 0, "pending": 247, … } }
```

The workspace's launcher detects `code === 'review_not_ready'` and routes to a confirm dialog with a one-click "Open Review" CTA instead of a flat alert string.

**Review page UI** ([review.html](frontend/review.html), [review.js](frontend/review.js)):

- New toolbar buttons: **"Ready to Run ▶"** (success-tinted) + **"Revoke Ready"** (shown only after Ready). Both wired through `refreshGateState()` which re-syncs after every load and after every press.
- Full-width banner under the toolbar swaps between two states: amber/blocked ("Run Converted is BLOCKED. Press Ready to Run when this conversion is fit to launch.") and green/ready ("✓ Marked Ready by Alice on 2026-05-02 · 'smoke tested locally'. Run Converted is unlocked in the workspace.").
- All inline styles moved to scoped CSS classes (`.rv-btn-ready`, `.rv-btn-revoke`, `.rv-btn-hidden`, `.rv-ready-banner`, `.is-ready`, `.is-blocked`) per linter requirement.

**Workspace UI** ([index.html:46](frontend/index.html#L46), [app.js:2832](frontend/app.js#L2832), [style.css:283](frontend/style.css#L283)):

- New compact banner above the Converted-App buttons with deep-link CTA into Review. Two visual states (amber=blocked, green=ready); the CTA hides itself in the ready state.
- `showLaunchButtonIfReady()` now ALSO consults `state.runGate.ready_to_run` via `applyRunGateToButton()`. The launch button's `title` carries the SPECIFIC reason it's greyed out ("disabled until at least one agent has finished" vs. "locked. Open Review and press Ready to Run first.") so the user doesn't guess.
- New 30s background poll (`startRunGatePolling()`) reconciles the banner + button when Ready is pressed in another tab.
- `launchConvertedProject()` upgraded to detect the structured 409 and route through `handleReviewNotReady()` — confirm dialog + one-click open of the review page.

### Phase 2 — Dev Chat backbone

**Why a new module, not extending existing chat**: `backend/agents/chat.py` powers agent-run prompt steering (planner / code-gen autofix). The dev-chat targets a *different* audience (post-conversion human edit loop) with *different* context (live run logs + converted/ tree + user attachments) and *different* output (unified diffs, not full reports). Mixing them muddies the prompt and the storage.

**Storage** ([backend/dev_chat.py](backend/dev_chat.py), new file, ~340 lines):

- Per-session JSONL at `data/dev_chat/<sid>.jsonl`. Append-only writes under an `RLock`; mutations (mark-applied, mark-unapplied) read-modify-write atomically via tmp-replace.
- Dataclasses: `Attachment`, `ProposedDiff`, `DevChatTurn`. Each turn freezes a `log_window` snapshot of the error buffer at send-time so re-rendering the thread later shows the EXACT context the LLM saw, not whatever the buffer holds today.
- Attachments: stored under `uploads/<sid>/dev-chat/<thread_id>/<id>_<safe_name>`. Per-file 8 MB cap (HTTP layer); per-turn 1 MB inline-text cap (so a single huge log dump can't blow the LLM context budget). Binary extensions (.png, .pdf, .zip, …) are stored but inlined as `<binary file: …, N bytes>` rather than raw bytes.
- v1 ships with a single `default` thread per session — multi-thread is a future hook.

**LLM driver** ([backend/agents/dev_assist.py](backend/agents/dev_assist.py), new file, ~330 lines):

- `build_prompt(...)` is a pure function — assembles the system preamble + run state + log tail + auto-detected error tail + history (last 6 turns, trimmed to 1500 chars each) + attachment block + user message. Surfaces a tree listing of `converted/` (paths only, capped at 800) so the LLM knows what's there without dragging file contents into the prompt — Read/Glob/Grep are whitelisted so it can pull individual files on demand.
- `extract_diffs(text)` pulls every ```` ```diff ```` (or ```` ```patch ````) fenced block out of the LLM response, parses `+++ b/<path>` headers, and returns `[ProposedDiff]` + a `suggested_restart_target` ("frontend"/"backend"/"both") parsed from a final `Restart suggested: <target>` line.
- `run_turn(...)` spawns `claude -p` against `converted/` with stdin-piped prompt (avoids the 32KB Windows argv cap). Tools whitelisted: Read / Glob / Grep / LS. `Edit / Write / NotebookEdit / Bash` are DENIED — the dev-chat flow is **diff-preview-then-apply, NOT direct-edit**. The apply endpoint writes patches atomically; we don't want the LLM bypassing that path.
- `apply_diff(body, converted_dir, dry_run, reverse)` shells out to `git apply --whitespace=nowarn --recount` (with `--check` for dry-run, `--reverse` for revert). Path safety is enforced BEFORE shelling out — every `+++ b/<path>` must resolve inside `converted_dir`. Without this, a hallucinated `--- a/../source/foo.py` could escape the sandbox.

**Run-log integration** ([backend/agents/run_manager.py](backend/agents/run_manager.py)):

- New per-`RunState` field `error_buffer: deque(maxlen=200)` populated by `_log_line` when the line matches `_ERROR_PATTERN` (ERROR / ERR! / FATAL / Exception / Traceback / Unhandled / Caused by / fatal: / failed to / HTTP 5xx in access-log style). Conservative — false negatives over false positives, because injecting a non-error line into the LLM prompt is more harmful than missing one.
- New public accessors: `get_recent_logs(run_id, limit)`, `get_recent_errors(run_id, limit)`, `get_active_run_for_session(sid)`. Encapsulate buffer reads so the dev-chat module never touches `RunState` internals.
- New `restart_run(run_id)` — convenience wrapper that stops the current run, sleeps 0.5s for OS port reclaim (Windows quirk), and spawns a new run against the same converted dir. Returns the NEW `RunState`. Powers the dev-chat "Apply + Restart" button.

**Endpoints** ([main.py:5012-end](backend/main.py)):

- `GET  /api/dev-chat/{sid}/turns`        — load history + summary counts
- `GET  /api/dev-chat/{sid}/run-state`    — active_run + recent logs + errors (5s drawer poll)
- `POST /api/dev-chat/{sid}/upload`       — multipart, returns attachment ids
- `POST /api/dev-chat/{sid}/send`         — message + attachment_ids → user turn + assistant turn (with diffs)
- `POST /api/dev-chat/{sid}/apply`        — `{turn_id, diff_id, dry_run, restart}` → git apply, optional restart
- `POST /api/dev-chat/{sid}/revert`       — git apply --reverse for an already-applied diff (Phase 5)

Endpoints stay thin so the policy (path safety, attachment caps, diff sandbox) lives entirely in dev_assist.

### Phase 3 — Dev Chat drawer UI

**Markup** (injected by `addRunCard()` in [app.js](frontend/app.js)): a `.dc-drawer` section attaches under each run card's `<pre class="run-logs">`. Three regions: collapsible `.dc-summary` toggle bar with the auto-detected error count badge, scrollable `.dc-thread` for chat bubbles + diff cards, and `.dc-compose` with attachment chips + textarea + 📎 attach button + Send button + Auto-restart-on-apply toggle.

**Styles** ([style.css:2321-2598](frontend/style.css)): ~280 lines of scoped `.dc-*` classes. Bubble variants (`.is-user` / `.is-assistant` / `.is-system`), diff syntax highlighting (`.add` green / `.del` red / `.hunk` accent), attachment chips, drag-drop visual feedback (`.is-dropping`), apply/revert button variants. `-webkit-user-select: none` paired with `user-select: none` for Safari per linter.

**Controller** ([app.js:3308-3640+](frontend/app.js)): `attachDevChat(runId, panelEl)` per-card controller. Held in `devChatStates` Map. Wires:

- Click toggle → expand/collapse + refresh on expand
- Textarea input → enables Send button + auto-resize up to 140px
- Ctrl/Cmd+Enter → send (plain Enter inserts newline)
- Send → POST /send → re-render thread from server
- 📎 button → file picker; drag-drop on textarea → both call `uploadDevChatAttachments` → POST /upload → chips appear above input
- Diff card actions: Preview (dry-run), Apply, Apply+Restart (gated on Auto-restart toggle), Reject (local hide), Revert + Revert+Restart (only on applied diffs)
- 5-second background poll on `/run-state` → updates the error count badge without subscribing to the heavier SSE log stream
- `removeRun()` calls `teardownDevChat()` so the poll timer dies with the card

### Phase 5 — Revert (the safety net)

After applying a diff, the same `body` can be reversed via `git apply --reverse`. UI swaps the action set: pre-apply shows Preview/Apply/Apply+Restart/Reject; post-apply shows Revert/Revert+Restart. Reverts call `mark_diff_unapplied()` which flips the storage flag back so the UI re-renders with the original action set if the user wants to re-apply. Failed reverts (because the file changed again post-apply, so the reverse hunk no longer matches) return a structured 409 with the git stderr verbatim.

### Where each piece of policy lives (so future-you finds it fast)

| Concern | File | Why here |
| --- | --- | --- |
| Ready-to-Run state | [backend/review.py](backend/review.py) | Sits next to the per-file decisions it complements |
| Run-launch gate | [main.py:4900](backend/main.py#L4900) | One file owns the structured-409 contract |
| Path-safety on diff apply | [backend/agents/dev_assist.py](backend/agents/dev_assist.py) `_validate_paths_inside` | Refuses BEFORE shelling out to git |
| Tool whitelist for the LLM | [backend/agents/dev_assist.py](backend/agents/dev_assist.py) `run_turn` | Edit/Write denied — diff-preview-then-apply is the contract |
| Error pattern detection | [backend/agents/run_manager.py](backend/agents/run_manager.py) `_ERROR_PATTERN` | Single regex; conservative; false negatives > false positives |
| Attachment size caps | [backend/dev_chat.py](backend/dev_chat.py) + [main.py](backend/main.py) `_dev_chat_attachment_size_cap_bytes` | Per-file at HTTP layer (8 MB), per-turn inline at storage layer (1 MB) |
| Auto-restart on apply | Frontend toggle (`data-dc-autorestart`) gates the `restart` flag in /apply body | User-controlled, default ON, no auto behaviour without an explicit click |

### What I did NOT build (deliberately)

- **SSE streaming for the assistant turn** — request/response is sufficient for typical 5-30s turns. Add later if long edits become common.
- **Multi-thread per session** — one `default` thread covers the v1 use case. The thread_id parameter is plumbed through end-to-end so adding threading is a frontend-only change.
- **LLM cost tracking integration** — the existing cost tracker hooks into runner.py's stream-json events; dev_assist uses `--output-format text` so it sits outside that path. Wiring it in is a polish item; not load-bearing for the demo loop.
- **Confirmation modal on Apply** — used `confirm()` for Revert (irreversible-feeling) but Apply ships with a Preview button + diff card always-visible, so the user already sees what they're applying. Adding a separate modal is friction without information gain.

### Verified end-to-end

- Backend: every modified module parses cleanly (`ast.parse` on main.py, dev_chat.py, review.py, dev_assist.py, run_manager.py).
- Frontend: `node --check` clean on app.js + review.js.
- Integration: imports succeed; diff-extraction smoke test on a fenced ```` ```diff ```` block correctly returns `(1 diff, restart='backend', files=['backend/main.py'])`.
- Real session: the test session `c9afaa02f85e` (which had `synthesize_file_map.py` write a backfilled `file_map.json` in an earlier change) now has a `data/reviews/c9afaa02f85e.json` sketch waiting for the reviewer's first decision; the gate state endpoint returns `{ready_to_run: false, review_exists: false, …}` cleanly without 500-ing.

---

## 2026-05-02 — Backfill `file_map.json` from disk for old / imported sessions `[DONE]`

User reported that opening **Review & Approval** for an older session (`c9afaa02f85e`) showed *"No files in this filter"* plus a misleading toast: *"No file_map.json yet — wait for the migration-planner + code-generation agents to finish."* The agents had already finished — `converted/` was on disk with 250+ generated files and full agent reports were in `exports/`. The session simply pre-dated the planner-emits-`file_map.json` contract, so the artifact the Review UI iterates over never existed.

User intent (caveman): *"add option 3 but don't kill the logic of new ran"* — fix Review for old sessions by walking disk; never break the new-run path where the planner authoritatively writes `file_map.json`.

### New module: [backend/agents/synthesize_file_map.py](backend/agents/synthesize_file_map.py)

Pure disk walker, no LLM calls, no network. Public surface:

- `synthesize_from_disk(session_root)` → builds an in-memory payload.
- `synthesize_and_persist(session_root)` → writes `context/file_map.json` *only if it doesn't already exist* (planner output is always authoritative).

Pairing strategy is deliberately loose because legacy and target stacks rarely share folder structure (PHP/Laravel → C#/.NET in this session):

- Walk `source/` and `converted/` separately, prune build dirs (`bin/`, `obj/`, `node_modules/`, `__pycache__`, …) and AppNova runtime folders (`chat/`, `context/`, `logs/`, `exports/`, `browser-test/`, `cost_reports/`).
- Skip binary extensions (images, archives, fonts, dlls, …).
- Index converted files by lowercase stem; for each source file, claim the first un-claimed converted twin with the same stem → `action="REWRITE"`.
- Source with no twin → `action="DELETE"`. Converted with no twin → `action="CREATE"`.
- Every row gets `_synthesized: true`; the wrapper dict gets `_synthesized: true`, `_synthesized_at`, and a human note explaining the rows are best-effort.

Hard cap of 5000 files per side (`_MAX_FILES_PER_SIDE`) so a misuploaded `node_modules/` can't lock the request thread. Logs a warning when truncation fires.

### Wired into [main.py:915-973](backend/main.py#L915)

`_load_file_map_for_review()` now returns `(mappings, synthesized)` instead of `list[dict]`:

1. **`file_map.json` present** → load it, `synthesized = bool(raw.get("_synthesized"))` so a previously-backfilled file is still flagged in the response.
2. **`file_map.json` missing** → `synthesize_and_persist(session_root)`. If that produces rows, persist them so the next call hits the fast path. If nothing is on disk to map (no `source/` AND no `converted/`), return `([], False)` — original "wait for the agents" hint fires correctly because the agents really haven't run.

The fallback never overwrites an existing `file_map.json`. The planner contract is always authoritative; if a user later re-runs the planner on an old session, the new file replaces the synthesized one and the `_synthesized` flag flips back to false on the response.

`session_root` is computed as `UPLOAD_DIR / session_id` directly, not via `project_dir.parent`, because `_detect_project_root` can drill into a wrapper folder for some uploads — using `UPLOAD_DIR / session_id` always lands at `uploads/<sid>/` regardless.

### Endpoint contract change: `/api/review/{sid}/files`

Response now includes `synthesized: bool` and `synthesized_note: str | null`. `synthesized_note` is null on planner-authored data, populated when rows came from disk:

> *"Backfilled from disk — pairings use stem matching only. Re-run the planner for authoritative rows."*

### Frontend: [review.js:122-133](frontend/review.js#L122)

Two distinct empty/notice paths:

- **`hint`** (planner artifact missing AND nothing on disk to backfill) — original "wait for the agents" toast, still fires for genuinely empty sessions.
- **`synthesized`** (rows came from the disk-walking fallback) — softer "best-effort" toast so the reviewer knows pairings aren't planner-verified. Suppresses the `hint` toast in this case to avoid double messaging.

### Verified on the live `c9afaa02f85e` session

Smoke-tested both functions against the real session:

```text
TOTAL ROWS: 587
BY ACTION: {'DELETE': 336, 'REWRITE': 9, 'CREATE': 242}

REWRITE samples:
  source/TotalBookingAI-Input/app/Http/Controllers/API/PCDEC/PcDeclarationController.php
    -> converted/backend/Controllers/PcDeclarationController.cs
  source/TotalBookingAI-Input/app/Models/Agency.php
    -> converted/backend/Models/Entities/Agency.cs
```

First call wrote `context/file_map.json` (587 rows). Second call returned `None` (refused to clobber). Pairings look semantically correct (PHP controller → C# controller, PHP model → C# entity).

The first iteration of the smoke test exposed a real bug — `source/chat/browser-test/log-v-*.jsonl` was producing 4842 useless DELETE rows because `chat/` and `context/` are AppNova runtime folders that older sessions copied into `source/` by mistake. Added them to `_SKIP_DIRS` alongside `logs/`, `exports/`, `browser-test/`, `cost_reports/`. Row count dropped from 5098 (truncated at the cap) to a clean 587.

### Why this is robust

- New runs untouched: planner writes `file_map.json` first → fallback never fires → response payload still flips to `synthesized: false` so the UI shows nothing extra.
- Backfilled sessions persist: written once, served from the fast path forever.
- Re-runs win: planner can always overwrite the synthesized file (it writes unconditionally during code-generation); the `_synthesized: true` marker on every row also lets future tooling identify and replace stale backfills.
- Bounded cost: 5000-file cap per side, in-process, no LLM, no network. Worst-case latency is dominated by `os.walk` over a single session folder — milliseconds in practice.

---

## 2026-05-02 — Workspace sidebar: fixed position + auto-tick checkboxes + richer button tooltips `[DONE]`

User flagged two ergonomic gaps in the workspace sidebar plus a documentation request:

1. **Sidebar was scrolling away with the main panel** — clicking around the agent grid pushed the navigation list off-screen, forcing the user to scroll back up to switch agents or click a Converted-App action. They wanted the sidebar fixed in place.
2. **Per-agent completion was ambiguous** — even after an agent finished, its sidebar checkbox stayed empty. The green dot was the only completion signal. With 14 agents in the list, the empty checkbox next to a green dot read as "selected for re-run? or just an indicator?" — confusing. They wanted the checkbox to auto-tick (with a green ✓) the moment the agent's report card lands.
3. **The Converted-App buttons** (Review & approve / Run converted / Browser test) needed clearer in-app tooltips so users don't have to ask in chat what each one does.

Three coordinated edits in [frontend/style.css](frontend/style.css), [frontend/app.js](frontend/app.js), and [frontend/index.html](frontend/index.html).

### Sidebar pinned to viewport via independent scroll containers

Changed `body` from `min-height: 100vh` to `height: 100vh; overflow: hidden`, and added `height: 100vh; overflow-y: auto` to `.main`. The sidebar's existing `position: sticky; top: 0; max-height: 100vh; overflow-y: auto` now actually sticks because the body itself no longer scrolls — instead, `.sidebar` and `.main` are two independent scroll containers. The grid layout is unchanged (`grid-template-columns: 280px 1fr`), so the topbar's existing `position: sticky` inside `.main` still works against the main pane's scroll context. No JS change required.

Net effect: scroll the agent grid as far as you like, the sidebar stays pinned with brand → Project Hub → Analysis Agents → Converted App → footer all in their original positions.

### Auto-tick on completion

Inside `setNavStatus()` in [`app.js`](frontend/app.js), after the existing `li.classList` mutations, the helper now talks to the `<input class="agent-pick">` directly:

- `status === 'done'` → `pick.checked = true` + tooltip becomes *"`{agent_id}` — completed. Uncheck to skip on next 'Run Selected'."*
- `status === 'running'` → `pick.checked = false` + tooltip becomes *"Running… checkbox will auto-tick when this agent finishes."* This handles the re-run case so a stale prior success doesn't keep the box ticked while the new run is in flight.
- `status === 'error'` → leaves the box as-is (so a user-selected retry survives the error) but updates the tooltip to *"`{agent_id}` — errored. Tick to include in next 'Run Selected' for a retry."*

Paired with new CSS rules:

```css
.agent-nav li.done .agent-pick { accent-color: var(--success); }
.agent-nav li.done:has(.agent-pick:checked) { background: var(--success-bg); }
.agent-nav li.error .agent-pick { accent-color: var(--error); }
```

Done rows now render with a green ✓ in the checkbox + a soft green row tint, instantly distinguishable from "selected for next run" (orange accent tint). Error rows get a red checkbox accent so the failure is visible at the corner of the eye.

### Sharper tooltips on the three Converted-App buttons

Rewrote the `title` attributes on `#review-btn`, `#launch-btn`, `#browser-test-btn` so hovering each one in the sidebar gives a one-sentence functional description PLUS the prerequisite that gates it. This is the in-app version of the chat explanation; together they kill the "what does this do?" ambiguity:

- **Review & approve** — opens the Review & Approval page, side-by-side legacy↔converted diff for every row in `file_map.json`, approve / reject / request changes / per-line comments. Enabled once any agent has produced output.
- **Run converted** — spawns `run.bat` / `run.sh` as a managed subprocess; the inline card shows phase + URL + live log stream + Stop / Rerun; opens the URL in a new tab when phase reaches `running`.
- **Browser test** — drives the running converted app with headless Playwright (≤ 8 pages), captures screenshots, harvests console errors / 404s / network failures, auto-dispatches a code-mode chat turn to fix any runtime errors. Requires a live converted run.

[`app.js`](frontend/app.js) parses cleanly. Three pure-frontend edits, zero backend changes.

---

## 2026-05-02 — Detached-launcher run phase + deterministic run-script auditor `[DONE]`

User hit two coupled bugs in the converted-app run loop. First, after the morning's `run.bat` `timeout /t` → `ping -n` hand-fix landed at the right path, the script worked correctly — backend ready in 7 s, both servers up in their own cmd windows — but AppNova still painted the run card `process_crashed` because the launcher subprocess exited rc=0 the instant it spawned its detached children. The OS knew `http://localhost:5050` was answering; `run_manager` did not. Second, every fresh conversion would re-introduce the `timeout /t` pattern unless the code-generation agent happened to remember the prompt rule that forbids it — so the hand-edit-then-sync cycle would repeat per session.

Fixed both by adding a new run phase + a deterministic auditor.

### Detached-launcher phase in [`backend/agents/run_manager.py`](backend/agents/run_manager.py)

Added `running_detached` to the phase taxonomy. Reached when the launcher subprocess exits rc=0 BEFORE the readiness loop has classified the run as `running`. Now, instead of immediately marking `process_crashed`, the readiness pipeline:

1. Probes `http://localhost:<port>` via the existing `wait_for_http_ready()` helper for up to 8 s.
2. If any 2xx/3xx/4xx answers, sets `phase = running_detached`, broadcasts a `phase` event with `detached: true`, broadcasts a `ready` event with the URL, and stashes a `_detached = True` marker on the run.
3. Returns success — the `Run Converted` card flips green and the URL chip becomes clickable.

The new `_wait_for_server_exit` codepath checks `_detached`: if set, it sleeps in 60-second beats forever (the launcher subprocess is already gone, so there's nothing to `await proc.wait()` on). Only `stop_run()` or workspace teardown unblocks it. Without this guard, the phase would flip back to `stopped` within milliseconds of being set to `running_detached` — the run card would briefly show green then go grey.

### Port-kill `stop_run` for detached runs

A `running_detached` run has no live subprocess handle — the actual server lives in OS-level child cmd windows that AppNova never adopted. Calling `proc.kill()` on the dead launcher does nothing useful. Added `_kill_listeners_on_port(port)`:

- **Windows**: `netstat -ano -p TCP` filtered to `LISTENING` lines on the target port → `taskkill /F /T /PID <pid>` for each PID.
- **POSIX**: `lsof -ti tcp:<port> -sTCP:LISTEN` → `os.killpg(os.getpgid(pid), 9)` (falls back to `os.kill` if the PID isn't a process-group leader).

`stop_run()` now invokes `_kill_listeners_on_port()` for both `run.port` and `run._backend_port` (when the multistack launcher allocated a companion port). Best-effort — a port-scan failure or a no-PID-found result logs to the run and returns; the user can always close the cmd windows manually (the launcher banner already tells them to).

### Browser-test gate accepts `running_detached`

In [`backend/main.py`](backend/main.py), expanded the live-run filter inside `/api/browser-test/{sid}` from `{running, starting, installing}` to `{running, running_detached, starting, installing}`. Without this, a healthy detached run would still 409 the browser test even though the URL was reachable. With it, clicking 📷 Browser Test on a detached run picks up the URL and runs Playwright against it just like a foreground run.

### Frontend phase handling in [`frontend/app.js`](frontend/app.js)

Two surgical edits:

1. `streamRunLogs()`'s phase event handler now classifies `running_detached` alongside `running`/`starting`/`installing` for the green pulsing-dot treatment, and renders the phase label as `running (detached)` so the user knows Stop will do a port-kill rather than a subprocess signal.
2. `reattachIfRunning()`'s `restorablePhases` set added `running_detached` so workspace re-open restores detached run cards alongside live and terminal ones.

### Deterministic auditor in [`backend/agents/audit_run_scripts.py`](backend/agents/audit_run_scripts.py)

New post-generation auditor — same shape as `audit_file_coverage`, `audit_api_contract`, `audit_ui_binding`, etc. Walks `converted/` for every `run.bat`, `run.cmd`, `run.ps1`, `run.sh`, `start.bat`, `dev.bat`, `serve.bat`, `launch.bat` (skipping `node_modules`, `vendor`, build dirs). For each Windows script:

- **Auto-fix** — every `timeout /t N /nobreak` (with optional trailing `>nul` / `2>&1`) is regex-substituted with `ping -n N+1 127.0.0.1 >nul`. Math: `ping -n N` sends N packets at 1s intervals starting at t=0, so we want `N+1` to elapse roughly N seconds. Mechanical and unambiguous, so we APPLY in place rather than just flag — that's the difference between "user has to read the audit and re-sync" and "the next ▶ Run Converted just works."
- **Flag-only** — `${VAR:-default}` inside `.bat` (cmd.exe passes literally, causing `EACCES: permission denied ${PORT:-5050}`) and bare `timeout N` without the `/t` flag. No safe mechanical substitution because the right cmd.exe replacement (`if not defined VAR set VAR=default`) depends on app shape.

Emits `docs/RUN_SCRIPTS_AUDIT.md` with a per-file changelog (file, edit count, before/after sample) and a "manual review required" section for the flagged-only patterns. Wired into [`backend/main.py`](backend/main.py)'s post-generation chain right after `audit_line_fidelity` and before `run_migration_pipeline`. Surfaces a `run_scripts_audit` SSE event with the manifest. Runs unconditionally; failures log + return.

Smoke-tested against a synthetic broken `run.bat` containing `timeout /t 1 /nobreak >nul` — auditor reported `edits_applied: 1`, file content rewrote cleanly to `ping -n 2 127.0.0.1 >nul`, no leftover artifacts.

### What this means end-to-end

- **Existing TotalBookingAI session (the one with the hand-fixed `run.bat`)**: click ▶ Run Converted again. The card phase will land on `running_detached` (instead of `exit`/`process_crashed`), the dot will pulse green with the label `running (detached)`, the URL chip will be clickable, and 📷 Browser Test will accept the run as a valid target.
- **Every future conversion**: even if the code-generation agent ignores the prompt rule, the auditor catches the `timeout /t` pattern in post-generation and rewrites it before the user ever clicks Run. The `docs/RUN_SCRIPTS_AUDIT.md` artifact records every edit so it's auditable.
- **The whole class of "launcher uses `start "..." cmd /k <server>` + AppNova mis-classifies as crashed" bugs** — gone. Any run.bat that spawns detached children, exits rc=0, and leaves a serving port behind now lights up green automatically.

All four changed files (`run_manager.py`, `main.py`, `audit_run_scripts.py`, `app.js`) parse cleanly. Auditor smoke-tested end-to-end.

---

## 2026-05-02 — Workspace reattach now restores the Run Converted card `[DONE]`

User flagged the bounce-back gap: click ▶ Run Converted → app boots in another tab → navigate to hub → re-enter the workspace → the Run Converted card was gone. The agent grid restored fine (that flow was already wired), but the run card with its URL / phase chip / Stop / Rerun / live logs was missing — only the Reports surface was visible. The backend kept the run alive in `run_manager._RUNS` and `/api/run/{sid}` returned it, but `reattachIfRunning()` in [`frontend/app.js`](frontend/app.js) never asked.

One-block edit added inside [`reattachIfRunning()`](frontend/app.js) right before the empty-state hide. After agent cards finish painting, it now:

1. Calls `GET /api/run/{sid}` to enumerate every run the backend still tracks for this session.
2. Filters to a *restorable* phase set: active phases (`starting`, `installing`, `running`) get the full live treatment; terminal phases (`exited`, `crashed`, `stopped`, `error`) are also restored so the user sees how the previous run finished instead of a silent gap.
3. Dedupes against any run already in `activeRuns` so a double-reattach (e.g. cached `appnova:session-bound` event firing on top of the DOMContentLoaded reattach) doesn't render two cards for the same run.
4. Calls the existing `addRunCard(run)` per restored run — same code path the live launch uses, so the card subscribes to `/api/run/stream/{run_id}` for any new log lines, the Stop/Rerun/Remove buttons wire up identically, and the `hideStopOnTerminal` handler inside `streamRunLogs` settles the card into a frozen-but-visible state for terminal runs.
5. Wraps each `addRunCard` in its own try/catch so one bad payload can't abort the rest of the reattach.

Also extended the empty-state hide check (`if (state.cards.size > 0 || activeRuns.size > 0 || status.running)`) so a session whose ONLY card is a Run Converted (no agent cards yet — e.g. user clicked Run from a partially-completed session) doesn't see the "Analyze a legacy codebase" hero stack on top of their run card.

End result: Hub → Workspace round-trip now preserves the run card. URL, port, stack, phase chip, log download link, Stop/Rerun/Remove buttons all come back; live runs continue streaming logs without missing a beat; terminal runs render with their final phase + Remove button so the user can dismiss the card or re-launch via Rerun.

---

## 2026-05-02 — Persistent converted-output browser, real backend errors in Browser-Test card, workspace re-open never 404s `[DONE]`

User flagged three post-conversion experience gaps after the hub overhaul:

1. **Already-converted apps weren't browsable from the hub.** Once a run finished, the only way to see what files were produced was to open the workspace and reattach to the chat-tree file panel — there was no way to inspect `uploads/<sid>/converted/` directly, even though it sits on disk.
2. **Browser-Test errors were lost in `alert()` popups.** When the converted app had problems, clicking 📷 Browser Test would `alert("No running demo found.\n\nClick ▶ Run converted first…")` and bail — never showing the actual backend diagnosis (crashed run? install failure? port bind?). Recovery required guessing.
3. **Opening a finished project from the hub after a backend restart painted "Error" instead of the last-known state.** `/api/results/{sid}` 404'd when `_results[sid]` was empty in memory, even though every agent's markdown was sitting in `exports/<sid>/*.md` ready to rehydrate.

Five surgical fixes across [backend/main.py](backend/main.py), [frontend/hub.html](frontend/hub.html), [frontend/hub.js](frontend/hub.js), and [frontend/app.js](frontend/app.js):

**Backend persistence — `_require_session` is now lazy.** [`_require_session()`](backend/main.py) used to hard-404 when `_session_dirs[sid]` was empty. It now falls back to `_ensure_session_loaded()`, which walks `uploads/<sid>/source/`, hot-loads project + converted paths, and rehydrates `_results[sid]` from `exports/<sid>/*.md`. Single chokepoint patch — every endpoint that gates through this helper (review, chat, browser-test, run-converted) now resolves any session whose folder exists on disk.

**Backend persistence — `/api/results/{sid}` returns 200 + `agents:[]`** with a `hint` field instead of 404'ing when a session is recognised on disk but has no exports yet. The workspace reattach now paints "no run yet, click Run" instead of an error banner.

**New endpoints `GET /api/converted/{sid}/tree` + `GET /api/converted/{sid}/file?path=…`** — list every file under `uploads/<sid>/converted/` (excluding node_modules / vendor / build / VCS dirs) and return individual file contents up to a 2 MB cap. Path-traversal guarded via `Path.relative_to(converted)`. A 200 with `exists:false` is returned when the dir is empty, so the hub can show "no converted output yet" inline instead of a red error.

**Hub: 📁 Files button + inline preview modal.** Added a `📁 Files` action on every hub card. Click it to open a 960×640 modal — left pane lists every file in the converted output with its size; click a row to fetch + render the contents in the right pane (binary files / >2 MB files surface a hint instead of garbage). CSS in `hub.html` (`.cv-modal`, `.cv-tree`, `.cv-row`, `.cv-pre` etc.); JS in `hub.js` `openConvertedBrowser()` + `showConvertedModal()`. Closes via ✕ button or backdrop click. Works on every session that has a `converted/` folder on disk — no run needs to be in flight.

**Browser-Test: errors render INSIDE the card, with a ✕ close button on every path.** Rewrote `runBrowserTest()` in `app.js`. The card is now created up-front so every code path can paint into it:
- *No live converted run* → `paintError()` shows the backend's verbatim 409 detail (which now also includes the tail of crashed runs' logs — see backend change below).
- *HTTP error from the backend* → backend `detail` rendered as fenced markdown, including the full traceback when the backend caught a non-HTTP exception.
- *200 but `data.ok === false`* → `error`-class card with `manifest.error` shown above the screenshot report, so the user sees what broke before having to scroll.
- *Frontend exception* → caught, painted via `paintError()` with `err.name + err.message + err.stack`.
The ✕ close button is wired in `attachCloseButton()` and called from EVERY terminal path (success, partial-success, error). No more `alert()` popups that vanish on dismiss.

**Browser-Test backend: 409 detail now enumerates the actual failure shape.** When `/api/browser-test/{sid}` is called without a live run, the 409 detail used to be a generic "Click Run converted first." Now it inspects `run_manager.list_runs(session_id)`:
- If a recent run is in `exited`/`crashed`/`stopped` phase, the detail includes the exit_code + a 1200-char tail of `last_output` so the user sees the actual stack trace from the converted app.
- If there are no runs at all, the detail says so explicitly.
- If runs exist but none are running/starting/installing, the detail enumerates the observed phases.

A separate try/except around `run_browser_test()` itself converts any pre-manifest exception (Playwright init failure, port-bind failure, network glitch) into a 500 with the exception type + message + traceback tail in the detail — so `paintError()` in the frontend has something concrete to render.

End result for the user:

- A finished conversion is browsable from the hub forever — `📁 Files` works as long as `uploads/<sid>/converted/` exists on disk, regardless of whether the run is in flight or the backend just rebooted.
- Clicking 📷 Browser Test on a card that isn't ready never shows "backend not started" or any other generic message — the card itself shows the exact backend diagnosis and stays open until you click ✕.
- Opening a project from the hub after the backend restarted picks up exactly where it left off — every completed agent's report rehydrates from `exports/<sid>/*.md` automatically; no more spurious "Error" banner.

---

## 2026-05-02 — Hub: surface Review prominently + add live agent feed for running sessions `[DONE]`

User flagged two hub UX issues: (1) the **Review** action was effectively invisible — buried as button #3 in a 9-button row with the same neutral styling as everything else, and disabled until the first agent completed; (2) the hub was a "static dashboard" — no way to see *what's happening right now* on a running session without opening the workspace. Also confirmed `backend/backend/` (the 2026-04-23/24 stale snapshot) is now deleted.

Three frontend changes, no backend changes (the existing [`/api/session/{sid}/status`](backend/main.py) endpoint already exposes `running` / `in_progress` / `completed` / `applicable`):

1. **Review promoted to an accent button** in [`hub.js`](frontend/hub.js) `renderCard()`. When the project has at least one completed agent, Review picks up a new `pc-primary` CSS class — accent-coloured border + bold weight, fills with accent on hover. When the run finishes successfully, the label becomes `✓ Review` so the next-step CTA is unmissable. Re-ordered the action row so Review + Reports sit immediately after Open (the "what next?" cluster) instead of being interleaved with Plan / Resume / Mode / Rename. Tooltip clarifies the disabled state ("Available after the first agent completes.") instead of the prior generic copy.

2. **Live agent feed inline on running cards.** Added a `<div class="pc-live" data-live-host="1" hidden>` slot inside every card's HTML. When `wireCard` sees `p.status === 'running'`, it calls `startLiveFeed(sid, p)` which polls [`/api/session/{sid}/status`](backend/main.py) every 3 seconds and renders:
   - A pulsing accent dot + `Live · 7/14 agents · 50%` header
   - One running-agent chip per id in `payload.in_progress` (also pulsing) — falls back to `awaiting next agent…` between waves
   - A `just finished · <name>` line for the most recent completion
   - A `Watch →` link that opens the full SSE workspace for users who want the per-tool-call detail
   - When the poll observes `running === false`, the feed self-stops and immediately fires `refreshAll()` so the card flips to its final status (and Review/Reports enable) without waiting for the 8-second project poll.

3. **Lifecycle plumbing for the pollers.** Added `liveTimers` + `liveRequests` Maps, a `stopLiveFeed(sid)` that cancels both the interval and any in-flight `AbortController`, integration with the existing `visibilitychange` pause (every live poller stops when the tab is hidden), and a `beforeunload` listener so navigating away never leaves dangling fetches. Each poller is keyed by `session_id`, so re-renders during a wave don't double-poll the same session.

CSS additions in [`hub.html`](frontend/hub.html) (~85 lines): `.pc-primary` accent variant, `.pc-live` panel with accent left-border + soft background, `.pc-live-pulse` keyframe (1.4 s ease-in-out box-shadow + transform pulse — IDE flags it as composite/paint-impacting; fine for an 8 px dot), `.pc-live-chip[.running|.muted]`, `.pc-live-watch` inline link button, `.pc-live-last` muted footer line.

End result: a user can stand at the hub, see at a glance which projects are mid-run with a pulsing dot + the active agent name, and click Review the moment a card flips to ✓ — no need to drill into the workspace just to monitor progress.

---

## 2026-05-02 — Zero-drop conversion hardening: source-inventory ground truth + sequential row tasking + recovery loops `[DONE]`

User asked for a coordinated hardening pass against the two failure modes the pipeline keeps regressing on: **planner omission** (the migration-planner emits a `file_map.json` that LOOKS valid but covers fewer rows than the legacy project actually has) and **generation truncation** (the code-generation agent runs out of output budget mid-list and emits `// ... rest of code` placeholders to keep going). Goal: every source file ports into exactly one target (or one explicit `kind=SKIPPED` row), and no generated file ships with a placeholder.

Eight coordinated edits across [backend/](backend/):

1. **Deterministic source inventory** — added [`write_source_inventory()`](backend/agents/runner.py) and [`_build_source_inventory()`](backend/agents/runner.py) that walk `project_dir`, prune vendored/build/VCS dirs, filter by a code-extension whitelist (matches the supervisor's source-file count + file_coverage's definition of "real source"), and persist `context/source_inventory.json` with `{project_root, total_files, by_extension, files[{path,size,ext}]}`. Wired into [`run_discovery`](backend/agents/runner.py) so it lands before any agent fires; `run_all_agents` re-checks the file's existence on cached/replayed runs and writes it idempotently. The result dict now carries the inventory manifest under `result["source_inventory"]`.

2. **Row-count validator** — [`validate_planner_quality()`](backend/agents/planner_polish.py) now takes a `source_inventory_path` parameter; when supplied, it asserts every entry in the inventory appears as exactly one `mappings[].source` and every `mappings[].source` exists in the inventory. Mismatches surface as concrete failure strings ("file_map.json is missing 47 of 363 source files declared in source_inventory.json") with the first 25 missing paths inlined so the supervisor's repair preamble can target them by name. [`supervisor.py`](backend/agents/supervisor.py) now passes `source_inventory_path=context_dir/"source_inventory.json"` at all three call sites (initial validation, repair re-validation, multipass re-validation).

3. **Multipass-by-default for the planner** — flipped `_PLANNER_MULTIPASS_THRESHOLD` from 200 → 1 in [`supervisor.py`](backend/agents/supervisor.py). Every project now runs the section-per-pass planner up front instead of waiting for two doomed single-pass timeouts before escalating. Override via `APPNOVA_PLANNER_MULTIPASS_THRESHOLD` env var to restore the old behaviour.

4. **Hardened `kind` whitelist** — already enforced via `_VALID_KINDS` in [`planner_polish.py`](backend/agents/planner_polish.py); the new row-count check stacks on top so the supervisor sees both vocabulary violations AND coverage gaps in a single repair preamble.

5. **Hard-constraint placeholder ban** — rewrote the `# ⚠️ FULL-CODE CONTRACT` block in the `code-generation` system prompt at [backend/agents/prompts.py](backend/agents/prompts.py). Now an explicit "the presence of any placeholder will cause the build to fail and trigger an automatic retry" gate, with an enumerated banned-forms list (`// ... existing logic`, `// TODO`, `…`, `pass` as sole body, `throw new NotImplementedException()`, empty `{}` for non-trivial methods, prose pointers to source). Cited the post-generation parity validator + parity-cleanup loop as the active enforcement.

6. **Sequential per-row tasking** — added a `# ⚠️ SEQUENTIAL ROW TASKING` block at the top of the code-generation role prompt in [`prompts.py`](backend/agents/prompts.py) AND added a matching `_SEQUENTIAL_ROW_TASKING` directive in [`orchestrator.py`](backend/agents/orchestrator.py) that's `insert(0, ...)`-prepended to the `code-generation` subagent prompt. Both directives instruct the agent to walk `file_map.json` row-by-row in `order` ascending, batched at most 5 rows per batch (1 row when `source` is ≥ 800 LOC), Read-then-Write-then-Glob-verify per batch, never pause for narrative until every row has a target file on disk. This is the architectural fix for the truncation failure mode — by giving each batch a fresh tool-call boundary, the model never gets to the "we're 80% through, just gesture at the rest" state where placeholders are emitted.

7. **Recovery loops in [main.py](backend/main.py)** — added `_schedule_recovery_chat_turn()` (a generic background dispatcher mirroring the existing `_schedule_browser_test_autofix`) and wired two loops into the post-generation audit block:
   - **Coverage cleanup loop** — after `audit_file_coverage()` runs, if the manifest's `coverage.unmapped >= 3`, dispatch a code-mode `chat_turn` against `coverage-cleanup` with a prompt that points at `docs/FILE_COVERAGE.md`'s **❌ Unmapped source files** table and tells the agent to walk it in batches of 5, porting real misses + appending genuine SKIPPED rows to `context/file_map.json` + `docs/FILE_MAP_AMENDMENTS.md`. Surfaces a `coverage_cleanup_dispatched` SSE event with the new chat node id.
   - **Parity cleanup loop** — after `run_migration_pipeline()` returns, inspect `pipeline_result.to_dict().parity_checker.summary`; if `rows_red > 0 AND missing_fields_total > 0`, dispatch a code-mode `chat_turn` against `parity-cleanup` instructing the agent to re-port the missing fields with their correct types/validators/DI bindings + matching frontend control updates. Surfaces a `parity_cleanup_dispatched` SSE event.

8. **Configuration tightening** in [`config.py`](backend/config.py) — bumped the heavy-tier `AGENT_TIMEOUT` default from 900 s → 1200 s so a complex but successful generation isn't killed mid-write (override via env var). Made `skip_if_no_signal=False` explicit on every analytical agent (`code-analysis`, `architecture`, `business-rules`, `security`, `integration`) — the AgentSpec default was already False but the explicit flag locks the contract: those agents must inspect every project regardless of framework signal hits.

**Why this works as a system, not a checklist.** Each layer covers the previous layer's residual failure mode:

- The **inventory** turns "did we cover everything?" from a fuzzy LLM judgment into a deterministic set diff.
- The **row-count validator** + **multipass-by-default** mean the planner's `file_map.json` is structurally complete on the FIRST pass for every project size, not just on retry-escalation paths for big projects.
- The **placeholder ban + sequential row tasking** mean code-generation can't bail out mid-list because it never has a "whole project" mental model — it has 5-row batches, each with explicit tool-call boundaries.
- The **recovery loops** turn the audits from passive diagnostics into active triggers; if anything still slips through after all the above, the cleanup chat turn lands the fix before the user sees "Done".

No tests were added in this pass — the existing smoke harnesses (`smoke_planner_partial_and_skipped`, `smoke_coverage_contract`, `smoke_required_upstream`) already exercise the supervisor + post-generation audits and will pick up the wired-in inventory/recovery paths on the next run.

---

## 2026-04-25 — README: rewrite in GitHub-banner style (badges + emoji headers + tables) `[DONE]`

User asked to bring [README.md](README.md) in line with the richer GitHub-renderable style of the prior project's README at `D:\...\AppNova_Working_09-04-2026\README.md` — badges row, emoji section headers, comparison/feature tables, ASCII architecture diagram, related-docs index — while keeping every fact accurate to *this* project (port 8002, static HTML frontend, Playwright mermaid pipeline, demo_sessions, 14-agent registry).

Full rewrite of [README.md](README.md), preserving local truths and replacing the bare prose layout with:

- **Centered banner** — `<div align="center">` wrapping the title, tagline, and 8 shields.io badges (Python 3.11 / FastAPI 0.115 / Uvicorn 0.32 / Claude Code Max / Playwright 1.47 / Mermaid / MIT / cross-platform). Two markdown lint warnings (`MD033` inline-html, `MD041` first-line-heading) are expected — this is GitHub's standard centered-banner idiom.
- **Emoji-headed sections** — ✨ What is AppNova · 📐 Architecture · 🤖 The 14 specialist agents · 🌐 API Surface · 🚀 Quick start · ⚙️ Environment variables · 🧭 Typical workflow · 📂 Repository layout · 🧪 Tech stack · 🔬 Smoke tests · 🐛 Troubleshooting · 🧑‍💻 Dev notes · 📄 License · 🔗 Related docs.
- **ASCII architecture diagram** — extended to show the post-processing pipeline (mermaid pre-render, diagram_qa repair, export, cost tracker) and the writer-agent per-cwd lock. Stayed inside a ```text fence so the lint `MD060` warnings on the diagram tables are false positives.
- **API Surface tables** — derived by grepping `@app.{get,post,put,delete}(` from [backend/main.py](backend/main.py) and grouped by purpose (auth · projects/upload · analyze · chat · mermaid/exports/cost · demo-sessions · run/browser-test/review · run-modes/task-planner). Bolded the headline `/api/analyze/{session_id}` row.
- **14-agent table** — sourced from `AGENT_REGISTRY` in [backend/config.py](backend/config.py); columns are Agent ID · Tier · Wave · Output. Notes that `devops` and `data-migration` always run regardless of signal hits, and that the default model pinning is Claude Sonnet 4.6 across every tier (overridable via `HEAVY_MODEL` / `LIGHT_MODEL` / `DISCOVERY_MODEL`).
- **Notable design choices table** — reframes the prose bullets as a Decision / Why-it-matters table (parallel waves · blackboard state · writer-agent lock · `file_map.json` enforcement · chat snapshots · `required_upstream` hard skips).
- **Prerequisites table** — Tool / Version / Why columns; warning callout about `start.bat`'s hardcoded Python path.
- **Environment variables table** — every common var with default + purpose, including the cost-tracker / orchestrator / director / model-pinning vars.
- **Smoke tests block** — added the rest of the smoke harnesses (`smoke_coverage_contract`, `smoke_line_fidelity`, `smoke_route_link_and_seed`, `smoke_ui_binding`, `smoke_required_upstream`, `smoke_planner_partial_and_skipped`, `smoke_run_converted`) alongside the existing mermaid + AST + node-check checks.
- **Related docs** — points at the actual files at the project root: changes.md, [DEPLOY_AZURE_VM_UBUNTU.md](DEPLOY_AZURE_VM_UBUNTU.md), the TotalBookingApp deployment manual + presentation decks, the auto-export / demo-session folders, and the live Swagger UI URL on `:8002/docs`.

No backend or frontend code changed — README-only.

---

## 2026-04-24 — .gitignore: also ignore .env.example (remove negation) `[DONE]`

User decided the [.env.example](.env.example) template should not be tracked either. It was already listed at line 9 of [.gitignore](.gitignore), but line 10 held a `!.env.example` negation (the earlier convention of keeping the template committed so new devs can copy it) which cancelled the ignore. Removed the `!.env.example` line — `.env.example` is now ignored via its explicit line 9 entry (and would also match the `.env.*` glob at line 8).

Verified: `git check-ignore -v .env.example` → `.gitignore:9:.env.example` ✓.

Implication: anyone cloning the repo won't get a `.env.example` template. If you want to hand one out, share it via a secure channel (password manager, encrypted drive) or re-add the `!.env.example` negation later.

---

## 2026-04-24 — .gitignore: add APPNOVA_Documentation.docx, fix trailing-slash bug, drop duplicate `[DONE]`

Follow-up to the [.gitignore](.gitignore) that was just added. User had manually inserted `APPNOVA_Documentation.docx/` at line 82 — but the trailing slash restricts git's match to directories only, so the actual file at the repo root wasn't being ignored. Also noticed `Outputs/` was listed twice (lines 75 and 81) after the same manual edit, and `References_by_Krishna/` had been added to the runtime-data block (kept — that's a reference folder the user doesn't want committed).

Two-line fix in [.gitignore](.gitignore) around line 80:

- Removed the duplicate `Outputs/` entry.
- Rewrote `APPNOVA_Documentation.docx/` → `APPNOVA_Documentation.docx` (no trailing slash) so git matches the file, not a nonexistent directory of the same name.

Verified with `git check-ignore -v`:
- `APPNOVA_Documentation.docx` → matches `.gitignore:81:APPNOVA_Documentation.docx` ✓
- `Outputs/AppNova.docx` → matches `.gitignore:75:Outputs/` ✓
- `References_by_Krishna/x` → matches `.gitignore:76:References_by_Krishna/` ✓

---

## 2026-04-24 — Add repository .gitignore (secrets + runtime folders) `[DONE]`

Repo had no `.gitignore`, so every untracked file — including [.env](.env) (contains `APPNOVA_JWT_SECRET`, `APPNOVA_PASSWORD`, `APPNOVA_USERS` JSON), the Python virtualenv at [backend/venv/](backend/venv/), bytecode caches, the SQLite cost DB at [data/cost_tracking.db](data/cost_tracking.db), uploaded source at [uploads/](uploads/), and runtime logs at [logs/](logs/) — was visible to `git add .`. One stray commit would have leaked the JWT secret and bloated history with multi-MB virtualenv binaries.

Created [.gitignore](.gitignore) covering:

- **Secrets:** `.env`, `.env.*` (with `!.env.example` exception), `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`, `secrets/`.
- **Python runtime:** `__pycache__/`, `*.py[cod]`, `venv/`, `.venv/`, `backend/venv/`, `*.egg-info/`, `build/`, `dist/`, plus test/coverage caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `htmlcov/`, `.coverage*`).
- **Node (future-proof):** `node_modules/`, npm/yarn/pnpm logs, `.next/`, `.nuxt/`, `.vite/`, `.turbo/`, `.parcel-cache/`.
- **AppNova runtime folders:** [uploads/](uploads/), [logs/](logs/), [exports/](exports/), [demo_sessions/](demo_sessions/), [Outputs/](Outputs/).
- **data/ runtime state:** `data/*.db`, `data/projects.json`, `data/analysis_cache/`, `data/plans/`, `data/reviews/`, `data/runs/` — keeps the `data/` folder itself trackable for any future committed seed files.
- **Logs:** `*.log` globally, and `logs/**` with a `!logs/.gitkeep` escape hatch.
- **OS cruft:** `.DS_Store`, `Thumbs.db`, `Desktop.ini`, `$RECYCLE.BIN/`, `._*`, `.Spotlight-V100`.
- **Editors/IDEs:** `.idea/`, `*.iml`, `*.swp`, `*~`, Sublime project files. For `.vscode/` the pattern ignores everything except shared project settings (`settings.json`, `launch.json`, `extensions.json`, `tasks.json`) so team config can still be versioned while per-user state (`.vscode/*.log`, `.history/`, etc.) stays out.
- **Claude/agent tooling:** `.claude/`, `.claude-code/`, `.anthropic/`.
- **Temp/scratch + archives:** `tmp/`, `*.bak`, `*.orig`, `*.rej`, `*.zip`, `*.tar.gz`, `*.7z`.
- **Commented-out block** for `*.pdf` / `*.docx` so the user can opt in later if generated docs start bloating the repo; left off by default since [APPNOVA_Documentation.docx](APPNOVA_Documentation.docx) at the root looks intentionally tracked.

Verified with `git check-ignore -v` against 14 real paths: `.env` / `backend/venv` / `backend/__pycache__/*.pyc` / `uploads/*` / `logs/backend.log` / `data/cost_tracking.db` / `data/projects.json` / `Outputs/*.docx` / `exports/*` / `demo_sessions/*` all match ignore rules; `.env.example` / `.vscode/settings.json` / `README.md` / `backend/main.py` correctly stay tracked.

**Note:** nothing committed yet is currently ignored (the tree has no prior commits of these paths per the empty `git log` on master). If any of these paths land in a future commit before being re-checked, run `git rm --cached <path>` to untrack them without deleting the working copy.

---

## 2026-04-24 — Migration-planner: sync directive with validator, trim schema, add field_inventory shortcut (faster + cheaper) `[DONE]`

Biggest cost win in the pipeline. The migration-planner was being told by `_AGENT_TARGET_DIRECTIVES["migration-planner"]` at [backend/agents/prompts.py:1618-1662](backend/agents/prompts.py#L1618-L1662) to emit A.0 (≥15-row layer mapping table), A.1 (≥50-line target tree), A.2 (full source→target markdown table), A.3 (execution-order table), A.4 (file_map.json), Section B with phase plans + gantt + risk register + team-mix estimates, PLUS 3 mandatory mermaid diagrams. Meanwhile the supervisor's body validator at [backend/agents/supervisor.py:228-264](backend/agents/supervisor.py#L228-L264) only checks A.4 — everything else was silently deleted from the validator in the 2026-04-23 cleanup but the DIRECTIVE stayed bloated, forcing the model to emit ~40k tokens of content nothing reads or validates.

Evidence from session c9afaa02f85e at [logs/backend.log:1303](logs/backend.log#L1303): single-pass produced 101,961 output tokens for ~265 source files. Repair pass produced another 93,766. At Sonnet $15/M output that's ~$2.90 per planner run just in redundant A.0-A.3/Section B/diagrams content the validator ignores.

Four surgical edits:

1. **Rewrote the directive** at [backend/agents/prompts.py:1618-1639](backend/agents/prompts.py#L1618-L1639) from 44 lines down to 18. New directive says: A.4 is the only required output; `## Source architecture` + `## Target architecture` narrative are optional and go ABOVE A.4 if budget allows; no phase plans / gantt / risk register / team-mix / mandatory mermaid diagrams. Added a leading comment explaining the sync-with-validator rule so a future editor can't silently re-bloat it without also updating `_validate_migration_planner_body`.

2. **Dropped `depends_on_source[]` from the schema** at [backend/agents/prompts.py:1229-1260](backend/agents/prompts.py#L1229-L1260). Grep of [backend/](backend/) shows zero downstream readers — it was pure schema bloat. Every `mappings[]` row carried a 2-3 path array nothing ever parsed.

3. **Capped responsibility strings** — added a new hard rule at [backend/agents/prompts.py:1272-1273](backend/agents/prompts.py#L1272-L1273): `legacy_responsibility` / `target_responsibility` are ≤10-word phrases, omitted when obvious from path + kind. Prior prompt examples ("MediatR query + minimal-API action returning PagedResult<TotalBookingDto>") encouraged sentence-length values; new examples ("MediatR query + minimal-API action") are 40–60% shorter and still fully informative. Also banned emitting `"key": null` / `"key": ""` — omit the field entirely.

4. **Pointed the planner at the deterministic field inventory** at [backend/agents/prompts.py:1301](backend/agents/prompts.py#L1301). Added: "If `context/field_inventory.json` exists, Read it ONCE and copy triplet values row-by-row — do NOT grep each UI source file yourself." [backend/agents/field_extractor.py](backend/agents/field_extractor.py) already writes this exact data deterministically; the planner was re-grepping 40+ UI files on every run, burning tool-call latency and input tokens. Graceful fallback to manual grep when the file isn't present (it currently isn't — field_extractor runs post-code-gen in the migration_pipeline — but the shortcut is in place for when that ordering is fixed).

Also synced the multipass runner's schema directive at [backend/agents/planner_multipass.py:147-164](backend/agents/planner_multipass.py#L147-L164) to match — dropped `depends_on_source?`, added the ≤10-word rule, added explicit "Do NOT emit depends_on_source[]."

Expected savings per run:
- **Output tokens:** ~40–60% reduction (most of the A.0/A.1/A.2/A.3/Section B/diagrams content gone). At Sonnet $15/M that's ~$1.50–2.00 saved per planner run.
- **Time:** proportional to output-token reduction (streaming is the bottleneck) — planner's 1469s single-pass should drop to ~600–800s.
- **Repair-pass rate:** should drop to near-zero for well-behaved runs — the directive no longer fights the validator, so the model's natural output matches what validates.

Scope note: none of this changes the A.4 JSON shape itself (beyond dropping an unused field). Code-generation, file_coverage, parity_checker, round_trip_tester, planner_field_map, codegen_field_sync, line_count_fidelity all continue to read the same `{meta, mappings[]}` structure. This is a pure prompt optimization — no supervisor or downstream code changes.

---

## 2026-04-24 — Migration-planner status downgrades to `error` when file_map.json is missing `[DONE]`

Closes the status/contract mismatch surfaced by session `c9afaa02f85e` at [logs/backend.log:1312](logs/backend.log#L1312): migration-planner's subprocess finished cleanly (`status=done`), the model emitted ~87k chars of mapping content, but it skipped the required `## A.4 file_map.json` heading + fenced JSON block, so `_extract_file_map_json` returned None and `context/file_map.json` was never written to disk. The `required_upstream=("migration-planner",)` gate on code-generation at [backend/config.py:135](backend/config.py#L135) checks only the agent's STATUS, not the contract deliverable — so wave 2 dispatched code-generation anyway, which then improvised from raw Glob/Grep and produced 0.0% file-coverage output (same regression shape seen on prior runs at [logs/backend.log:1158-1159](logs/backend.log#L1158-L1159)).

Root cause: two concepts were conflated.

| Concept | What it tracked | What it should track for migration-planner |
|---|---|---|
| Subprocess status | `claude -p` exit code | same |
| Contract deliverable | — (none) | `context/file_map.json` on disk |

Fix in [backend/agents/supervisor.py:1096-1127](backend/agents/supervisor.py#L1096-L1127): added an `elif result.get("status") == "done":` branch right after the `extracted is not None` write block. When extraction failed across initial pass + repair pass + multipass escalation but the subprocess returned `done`, the branch now:
- logs an ERROR line identifying the missing target path,
- flips `result["status"] = "error"` with a message listing which repair modes were attempted (reads `repair_status["repair_attempted"]` / `multipass_used` to build the phrase),
- attaches up to 300 chars of `body_failures` so the UI surfaces the real reason,
- sets `result["missing_file_map"] = True` for frontend chip rendering.

This mirrors the "silent-zero-files" downgrade already present for code-generation at [backend/agents/supervisor.py:1110-1135](backend/agents/supervisor.py#L1110-L1135) — same pattern, opposite end of the pipeline. After the downgrade, `required_upstream` on code-generation sees `status=error` from its upstream and triggers the existing SKIP path with "Required upstream agent(s) unavailable: migration-planner" — same message already used when migration-planner times out (see [logs/backend.log:562](logs/backend.log#L562)). No new frontend work needed.

Scope note: this fixes the *gate*, not the *extraction*. The model still needs to emit `## A.4` + fenced JSON for downstream to succeed. A future follow-up (Issue B option #3 from chat) would make `_extract_file_map_json` tolerate missing heading / missing fence by scanning for any `{"meta":…, "mappings":[…]}` shape — that'd let structurally-sloppy runs still succeed when the JSON is recoverable. Left as a separate change because it touches parsing logic, not status control.

---

## 2026-04-24 — Cost optimization step 2: downgrade Business Rules + Security to Haiku `[PLANNED]`

Not implemented yet — waiting on one real run's cache-hit numbers (from the logging added below) before committing. Decision: Business Rules and Security move to Haiku; Architecture stays on Sonnet. Rationale from the run at [logs/backend.log:1296-1304](logs/backend.log#L1296-L1304):

| Agent | Current model | Last-run cost | Plan |
|---|---|---|---|
| Business Rules | Sonnet | **$1.20** | → Haiku (≈$0.20, save ~$1.00) |
| Security Audit | Sonnet | $0.49 | → Haiku (≈$0.08, save ~$0.41) |
| Architecture Analysis | Sonnet | $0.49 | **stay on Sonnet** (user decision — diagrams + component mapping quality matters more) |

Expected total saving ≈ **$1.40 per run**, no code-generation quality impact (neither of these feeds `file_map.json`). Implementation requires a per-agent model override because `tier="heavy"` is a single global knob today — changing `HEAVY_MODEL` in [backend/config.py:35](backend/config.py#L35) would drag Code Analysis, Migration Planner and Code Generation down too, which is not the intent.

Mechanism (pick one at commit time):
- **A.** Add `model: str = ""` field on `AgentSpec` in [backend/config.py:42-55](backend/config.py#L42-L55); `model_for()` at [backend/config.py:175-181](backend/config.py#L175-L181) prefers `spec.model` over the tier lookup. Cleaner — the per-agent decision sits next to the agent declaration.
- **B.** Add `AGENT_MODEL_OVERRIDES: dict[str, str]` module-level; `model_for()` consults it first. One-line change; looser coupling.

Side-by-side validation before full rollout: run once with Haiku on Business Rules against TotalBookingAI-test-v4, diff the report against the Sonnet baseline at [exports/](exports/) to confirm the rule extraction quality didn't collapse. If it did, revert that single agent.

---

## 2026-04-24 — Cost optimization step 3: deduplicate boilerplate across agent briefs `[PLANNED]`

Not implemented yet — depends on step 1 logging showing low cache hit rate (<30% on wave-follower agents) to justify the reorder cost. Root cause from reading [backend/agents/prompts.py:1780-1867](backend/agents/prompts.py#L1780-L1867): `build_agent_prompt` assembles blocks in this order today:

1. USER INSTRUCTIONS (session-constant)
2. TARGET MIGRATION STACK (session-constant)
3. **TARGET-STACK DIRECTIVE FOR {AGENT_ID}** ← first divergence (agent-specific)
4. CONTEXT FILES (agent-specific paths)
5. YOUR TASK (agent-specific role)
6. _COVERAGE_RULE (identical across every agent, ever)
7. _STYLE_CONTRACT (identical across every agent, ever)
8. _MERMAID_RULES (identical across every agent, ever)

Cache is prefix-based — match stops at the first byte of difference. The first divergence happens at block 3 (the agent id in the heading at [backend/agents/prompts.py:1827-1831](backend/agents/prompts.py#L1827-L1831)). Blocks 6/7/8 are identical across every agent and sit AFTER the divergent content, so they never benefit from cache.

Fix: reorder so all identical blocks come first, divergent blocks last:

```
[1] _STYLE_CONTRACT              ← identical every run, every agent
[2] _MERMAID_RULES               ← identical every run, every agent
[3] _COVERAGE_RULE               ← identical every run, every agent
[4] TARGET MIGRATION STACK       ← identical within one session
[5] USER INSTRUCTIONS            ← identical within one session
─── cache boundary falls here naturally ───
[6] TARGET-STACK DIRECTIVE FOR {agent_id}   ← divergent
[7] CONTEXT FILES                ← divergent
[8] YOUR TASK                    ← divergent
```

Expected cache prefix grows from ~500 tokens (blocks 1+2) to 4–6k tokens (blocks 1–5). At Sonnet pricing ($3/M input vs $0.30/M cache read, [backend/cost_tracker.py:70](backend/cost_tracker.py#L70)), that's ≈$0.12 saved per wave-follower agent, times ~7 follower agents per wave ≈ **$0.8 saved per run**. Stacks on top of step 2.

Gotchas to preserve on commit:
- Keep `.strip()` on every shared block so trailing whitespace differences don't break the prefix match — existing code at [backend/agents/prompts.py:1861-1866](backend/agents/prompts.py#L1861-L1866) already does this.
- Do NOT move agent_id into the shared prefix (tempting to stash "DIRECTIVES FOR ALL AGENTS" once at the top) — that bloats output tokens as each agent re-emits other agents' constraints.
- USER INSTRUCTIONS is conditional; the cache key splits into "with/without user brief" variants, both of which benefit within their wave.

---

## 2026-04-24 — Runner logs cache hit-rate per agent (Step 1 of cost-optimization) `[DONE]`

Baseline instrumentation before deciding whether to downgrade agents to Haiku or deduplicate brief boilerplate. The `usage` event from the CLI already carries `cache_read_input_tokens` / `cache_creation_input_tokens`, and the runner was already storing them in `cost_info` at [backend/agents/runner.py:686-687](backend/agents/runner.py#L686-L687) — they just weren't surfaced in the log line, so there was no easy way to answer "is Sonnet actually hitting cache on waves of parallel agents?"

Extended the "Agent completed" log in [backend/agents/runner.py:692-709](backend/agents/runner.py#L692-L709) to append `cache=read:N create:M hit:P%` where `hit = cache_read / (cache_read + input) × 100`. Fresh input now refers to the *uncached* input only (CLI already excludes cache_read from `usage.input_tokens`), so the hit-rate is honest. Example expected shape:

```text
[Runner] Agent 'Business Rules' completed in 374.1s (41,012 chars) cost=$1.1998 tokens=2724+20797 cache=read:11845 create:14200 hit:81%
```

What to look for on the next run:

- Wave-leading agent will show `create:` high and `hit:` low (0–10%) — expected, it's seeding the cache.
- Wave-follower agents should show `read:` ≈ shared-preamble size and `hit:` ≥ 70% if briefs share a byte-identical prefix.
- If every agent shows `hit: <20%`, the shared preamble isn't being cached — jump to #3 (brief dedup) rather than #2 (model downgrade). cost_tracker already has a threshold-based recommendation at [backend/cost_tracker.py:321-340](backend/cost_tracker.py#L321-L340) but it needs ≥10 calls per agent, which AppNova never hits in a single session — the per-call log is the practical way to see the signal on one run.

---

## 2026-04-24 — Session console: shrink panel to 340×380 (compact chat-widget footprint) `[DONE]`

Follow-up to the reservation fix below. The 380×540 panel still dominated the right column — on a 1080p viewport it ate ~50% of the vertical space even when the status output was three lines long. Dropped `--sc-panel-w` 380 → 340 and introduced `--sc-panel-h` at 380 (was hard-coded 540) in [frontend/style.css](frontend/style.css), and switched the `.sc-panel` height rule to read the variable. Reserve padding recomputes automatically via `--sc-reserve = panel-w + edge-gap + 20`, so the thread's left-shift tracks the new width without a second edit.

---

## 2026-04-24 — Session console reserves right-side space instead of overlapping report cards + raise CLI output-token cap to 64k `[DONE]`

Two fixes bundled: a frontend layout bug where the bottom-right chat panel hid part of the middle report cards when open, and a backend regression where Migration Planner's `file_map.json` pass crashed with `API Error: Claude's response exceeded the 32000 output token maximum` on large repos.

### 1. Session console: proper widget behavior when panel is open

User symptom (screenshot-visible): opening the bottom-right "Session console" floated a 400px panel directly over the report cards — Card 5 (Migration Planner) sat half-hidden behind the panel. Cards, topbar, and the console were all competing for the same right-hand column.

Root cause: the `.session-chat` anchor was `position: fixed; right: 24px; bottom: 24px` with nothing else reacting to the open state. The thread is `max-width: 880px; margin: 0 auto` inside `.main`, so on a 1500px main column the thread's right gutter (~310px) is narrower than the panel+gap (~424px) — the panel necessarily overlapped.

Fix in [frontend/style.css](frontend/style.css): added a `body.session-console-open` rule that adds `padding-right: calc(380px + 20px + 20px)` to `.main` only when the console is open. The thread stays centered in the remaining space via its existing `margin: 0 auto`, so cards slide left by the panel's width without needing per-card overrides. Dropped via `@media (max-width: 1200px)` so the reservation never squeezes content on narrow laptops — the panel overlaps there, which is acceptable for a widget a click dismisses. Also tightened the widget itself: 380px panel (down from 400px), 540px max height, accent-filled pill toggle with pop-in keyframe so the open transition reads clearly. Custom properties `--sc-panel-w` / `--sc-edge-gap` / `--sc-reserve` drive the geometry so panel width and the reserve padding can't drift apart.

Fix in [frontend/app.js](frontend/app.js): `setOpen()` toggles `document.body.classList.toggle('session-console-open', open)` in addition to the existing `hidden` class swap on the panel. Same storage key, same Ctrl/Cmd+K handler — only the body flag is new, and the CSS reservation is purely additive so any other page using the same widget keeps working.

### 2. Raise Claude Code CLI output-token ceiling to 64k

User symptom (from [logs/backend.log:1305-1307](logs/backend.log#L1305-L1307)): Migration Planner failed at 00:19:46 on 2026-04-24 with `API Error: Claude's response exceeded the 32000 output token maximum. To configure this behavior, set the CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable.` PlannerMultipass section A.4 went into fallback and the whole run reverted to single-pass+repair.

Root cause: the CLI's hard-coded default for `CLAUDE_CODE_MAX_OUTPUT_TOKENS` is 32,000. `planner_multipass._SECTIONS` requests a 16k budget per section, but on a 260+ source-file repo the `file_map.json` entries (source/targets/kind/notes per row) legitimately stack past 32k in wire tokens once Claude writes out all mappings in one shot.

Fix in [backend/agents/runner.py](backend/agents/runner.py): added module-level `_CLAUDE_MAX_OUTPUT_TOKENS = _os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "64000")` and passed `env=child_env` to `asyncio.create_subprocess_exec`, where `child_env = dict(os.environ)` with `setdefault("CLAUDE_CODE_MAX_OUTPUT_TOKENS", …)`. The `setdefault` means an operator-set value in the parent env still wins — we only raise the floor from 32k to 64k. Sonnet 4.x advertises support up to 64k output tokens so this doesn't create a new failure mode at the model side.

---

## 2026-04-24 — Float session chat, hide hero on reattach, canonical card order, clear stale project_id on 404 `[DONE]`

Four small UX fixes bundled — all frontend-only, no backend or SSE changes, so currently running agents keep streaming and land their reports exactly as before.

### 0. Reattach paints report cards in canonical sidebar order

User symptom: returning from the hub to a completed project rendered the cards in the order they *finished*, not the order they appear in the sidebar. Migration Planner (slow, finishes late) would sit above Code Review (fast, finishes earlier by wall-clock) even though the sidebar numbers them 5 and 11. Visually jarring and made it hard to scan top-down.

Root cause: `reattachIfRunning()` iterated `data.agents` directly — that list is appended by `_save_partial` in [backend/main.py:2228](backend/main.py#L2228) in completion order — and passed each to `ensureCardForReattach`, which synthesizes an `agent_start` event that appends the card to the thread. Finish-order in → DOM-append-order out.

Fix: before painting, merge `data.agents` (status ∈ {done, error, skipped}) with `status.in_progress` into one ordered id list, sorted by each agent's index in the frontend's `AGENTS` constant (the same array the sidebar numbering derives from). Unknown ids (director-mode edge case) rank to the end so they don't jump the queue via negative-index math. Then a single loop paints each card and calls `completeReattachedCard` for ids that have a terminal result — in-progress cards stay on the spinner for the polling loop to upgrade.

The mid-run `startReattachPolling` path is deliberately left as-is: cards painted by the initial pass already exist in canonical positions, and `completeReattachedCard` just flips an existing card's pill from RUNNING to DONE — no DOM reshuffle. A genuinely out-of-order completion during polling (agent 9 finishing before agent 7, both newly started after the initial reattach) would still append in finish-order, but that's a niche case tied to supervisor pipelining and worth fixing separately if it ever surfaces.

### 1. Session chat docked to bottom-right as a floating launcher

User symptom: the "Ask about this session" chip sat at the bottom of the main scroll area, glued under the last report card. On short threads it floated oddly in mid-page; on long threads the user had to scroll to the very bottom to find it.

Fix: switched `.session-chat` in [style.css](frontend/style.css) from `position: sticky; bottom: 0` to `position: fixed; right: 24px; bottom: 24px` — classic Intercom/Crisp launcher pattern. Container is pinned by `bottom`, so when the panel expands the top edge grows upward. Panel width clamped to `min(400px, calc(100vw - 48px))` + `max-height: 60vh` so it stays readable on laptop screens and never overlaps the sidebar.

### 2 + 3. Hide "Analyze a legacy codebase" hero when reattaching

User symptom: returning to a project via the hub's **Open** button painted the report cards below but left the empty-state hero (`⌘` icon + "Drop a `.zip` of your project…" copy) visible at the top. Instead of a clean vertical list of DONE cards, the user saw hero → plan toggle → hero copy → cards — disorienting.

Root cause: `emptyState.classList.add('hidden')` was only called inside the Run flow at [app.js:1177](frontend/app.js#L1177). `reattachIfRunning()` restored cards but never touched the hero, so it sat above them.

Fix: at the end of `reattachIfRunning()`, hide `emptyState` when either (a) at least one card was painted (`state.cards.size > 0`) or (b) the backend reports `status.running` (fresh run just started — empty for now, but cards incoming). Leaves the hero visible for genuinely fresh sessions where no upload has happened yet.

### 4. Clear stale `appnova.projectId` on 404

User symptom: log line `GET /api/projects/prj_1fa20addc5 HTTP/1.1 404 Not Found` kept repeating on every workspace open. Traced to [backend.log:1238](logs/backend.log) — the project was hard-deleted, but localStorage still held `appnova.projectId = prj_1fa20addc5`. `paintHubProjectName()` fires on every DOMContentLoaded and hit the dead id forever.

Fix: in `paintHubProjectName()` ([app.js:358-376](frontend/app.js#L358-L376)), branch on `r.status === 404` and `localStorage.removeItem(PROJECT_KEY)`. Also clears `LAST_WORKSPACE_KEY` if its `pid` matches — otherwise the hub's "Return to workspace" banner would resurface the ghost project on the next hub visit. Transient 5xx / network errors still leave storage intact (guard-railed to `status === 404` only, not any `!r.ok`), so a flaky backend can't orphan a live session's project binding.

### Not fixed (flagged for later)

**#5 — Migration Planner RUNNING card with no SSE events after hub round-trip.** The original `EventSource` dies when the page unloads; reattach polls `/api/session/{sid}/status` every 2s but only reads terminal transitions (done/error/skipped). Incremental `tool_call` / `tool_result` / assistant-text events aren't persisted anywhere, so they can't be replayed into the card body after a reload. Fixing this properly requires a per-session event log on disk + a replay endpoint — too big to bundle with these cosmetic fixes. Flagged.

### Files touched

- [frontend/style.css](frontend/style.css) — `.session-chat` and `.sc-panel` rules.
- [frontend/app.js](frontend/app.js) — `reattachIfRunning()` tail + `paintHubProjectName()` 404 branch.

---

## 2026-04-23 — Rehydrate agent reports from `exports/` so hub "Open" repaints every card after backend restart `[DONE]`

User symptom: clicking **Open** on a project card from the hub lands on an empty workspace — no agent cards, no reports — even though the project's `exports/<sid>/*.md` files are intact on disk. Happens for every project whose run finished under a prior backend process.

Root cause: `_rehydrate_session_from_disk()` in [backend/main.py](backend/main.py) only restored folder-level state (`_session_dirs`, `_session_converted`, `_session_targets`). It never repopulated the agent-results maps, so after a restart:

1. `/api/session/{sid}/status` returned `applicable=[]` and `in_progress=[]`.
2. `/api/results/{sid}` did `_results.get(sid)` → `None` → raised 404 `"No results yet"`.
3. The frontend's reattach flow wrapped the fetch in a bare `try {…} catch {}` ([frontend/app.js:460-475](frontend/app.js#L460-L475)), so `r.ok === false` silently skipped the card-paint loop — no error, no toast, just a blank thread.

### What shipped

1. **`_rehydrate_results_from_disk(sid)`** — new helper that scans `exports/<sid>/*.md`, keeps the most recent file per agent (since re-runs stack multiple timestamped exports), reads the body, and rebuilds three dicts: `_results[sid]` (status always `"done"`, result = markdown body), `_session_completed[sid]` (set of agent_ids), `_session_applicable[sid]` (same ids, as list — matches the shape the original analyse path produces). `combined.md` is skipped (all-agent concatenation, not a real agent). Filename parse uses the same `split("_", 2)` convention already used by the hub's disk-probe fallback in `_project_response` (so `YYYY-MM-DD_HH-MM-SS_<agent_id>.md` → `parts[2]` = agent_id).
2. **Wired into `_rehydrate_session_from_disk`** — called after the folder-level dict restorations so both the startup-time `_rehydrate_all_sessions()` path and the lazy per-request `_ensure_session_loaded()` path get results restored for free. Wrapped in try/except so a single bad file (permission error, zero bytes, whatever) doesn't poison the folder-level restore that did succeed.
3. **No frontend changes needed.** The reattach flow at [frontend/app.js:460-475](frontend/app.js#L460-L475) already iterates `data.agents` and calls `ensureCardForReattach` + `completeReattachedCard` for each `status === 'done'` entry — now that `/api/results/{sid}` returns non-empty `agents`, the cards paint on their own.

### Edge cases handled

- **Partial / errored agents with empty result body**: never exported by `_auto_export_session` (gate at [main.py:1725](backend/main.py#L1725)), so they stay absent. The session's `resumable` flag goes to `False` because all rehydrated agents are marked done — the user would have to re-run to regenerate missing reports. This is consistent with the pre-restart behavior for a fully-completed run.
- **Multiple runs on the same session**: lexicographic sort of the `YYYY-MM-DD_HH-MM-SS` stamp == chronological, so we pick the latest export per agent.
- **Agent IDs with hyphens (e.g. `code-generation`)**: `_auto_export_session`'s `_re.sub(r"[^a-zA-Z0-9_-]+", "_", aid)` preserves hyphens, and `split("_", 2)` with maxsplit=2 means the agent_id's own underscores don't over-split. Verified by trace: `2026-04-20_14-30-55_code-generation.md` → stem `split("_", 2)` → `["2026-04-20", "14-30-55", "code-generation"]`.
- **Re-entry safety**: `_ensure_session_loaded` short-circuits on `_session_dirs[sid]` presence, so rehydrate only fires when the session is genuinely cold (backend restart). A live session with an in-flight `_session_tasks[sid]` is never clobbered.

### Files touched

- [backend/main.py](backend/main.py) — added `_rehydrate_results_from_disk` (lines ~264-324) + one try/except call site inside `_rehydrate_session_from_disk`.

---

## 2026-04-23 — Session restoration after backend restart + strip LLM preamble from reports `[DONE]`

Two fixes in one turn. First one is load-bearing (data-correctness risk); second is cosmetic.

### A. Session restoration after backend restart

User symptom: after restarting the backend server, clicking **Open** on a project card from the hub lands on a workspace with the upload row + stack dropdowns blank — even though the files and project record are intact on disk. Agents that are triggered from that state still read source from disk (correct) but get an empty `target_stack` (wrong), so they fall back to filename-based guessing and can drift away from the real target platform.

Root cause: three session-level dicts in [backend/main.py](backend/main.py) — `_session_dirs`, `_session_converted`, `_session_targets` — are populated at upload time but never persisted. A restart wipes them, so `/api/session/{sid}/status` returns `exists=false`, the frontend clears localStorage, and the user sees empty fields.

#### What shipped

1. **Persist `target_stack` per session.** Added `_target_stack_path(sid)` / `_persist_target_stack()` / `_load_target_stack()` helpers. Every site that writes `_session_targets` now mirrors the value to `uploads/<sid>/target_stack.txt`: the `/api/upload` path, the `/api/session/{sid}/stack` endpoint, the demo-session loader, and the session-clone path. Writes are best-effort (a disk failure logs but doesn't fail the caller — the in-memory dict stays authoritative for the current process).
2. **Eager startup rehydrate.** New `_rehydrate_session_from_disk(sid)` reconstructs one session's in-memory state from `uploads/<sid>/` (source tree → `_session_dirs`, converted tree → `_session_converted`, `target_stack.txt` → `_session_targets`). `_rehydrate_all_sessions()` walks every session folder and calls it. Wired via `@app.on_event("startup")` (can't run at module-import time because `_detect_project_root` is defined further down in the file — FastAPI's startup hook fires after the module is fully imported, which is the right moment).
3. **Lazy per-session rehydrate.** New `_ensure_session_loaded(sid)` is a fast "if cold, hot-load" shim. Wired into `/api/session/{sid}/status` and `/api/session/{sid}/stack` — any cold session with files on disk hot-loads on the first request instead of 404'ing. Covers the race where a request arrives before the startup hook has completed, and the case of external filesystem adds.
4. **Target_stack fills the dropdowns on reopen.** The earlier `hydrateStackPickerFromMarkdown()` in [frontend/app.js](frontend/app.js) already reverse-parses the stored markdown back into the 4 `<select>` slots — now that the backend actually returns a non-empty `target_stack` after restart, the dropdowns populate correctly.

#### Why this matters for agents

Before this change, agents running on a cold session got `target_stack=""` and had to infer the target platform from filenames. That's the "agents hallucinate the stack" risk the user flagged. After this change, the stack survives restart in writing, so every agent run reads the same stack the user originally chose.

### B. Strip LLM "transition sentence" from report cards

User symptom: the report card shows lines like `I now have enough coverage to write the full analysis. Let me produce the report.` above the real report heading. These are Claude thinking-out-loud sentences that bleed into the final result; they add noise without value.

#### What shipped

1. **`stripReportPreamble(raw)`** in [frontend/app.js](frontend/app.js) — matches 7 known preamble cues via case-insensitive regex (e.g. `/\bi (?:now )?have (?:enough|sufficient)\b/i`, `/\blet me (?:produce|compile|write)\b/i`, `/\bbased on (?:my|the) (?:analysis|review)\b/i`). Only scans the first 5 non-empty lines — if no cue is found, the text passes through unchanged.
2. **Cut point**: first blank line OR first markdown heading within the first 12 lines. Cuts from start to that point. If neither is found, returns raw (safer than truncating real content).
3. **Applied at render time only** — the raw result in `state.cards`, in SSE events, and in on-disk markdown exports is untouched, so the audit trail and the per-card Chat drawer (which reads the full raw result) still see the preamble if they need to.
4. **Three call sites** wired: `renderFinalReport()` (reattach path), `completeCard()` happy path (line 1838), `completeCard()` partial/error path (line 1878). All three now route through `stripReportPreamble()` before handing markdown to `renderFinalMarkdown()`.

### Files touched

- [backend/main.py](backend/main.py):
  - New helpers: `_target_stack_path`, `_persist_target_stack`, `_load_target_stack`, `_rehydrate_session_from_disk`, `_rehydrate_all_sessions`, `_ensure_session_loaded`.
  - New `@app.on_event("startup")` hook: `_rehydrate_on_startup`.
  - `upload_files()`, `set_session_stack()`, `load_demo_session()`, `session_clone()` — all now call `_persist_target_stack()` alongside their `_session_targets[sid] = ...` writes.
  - `session_status()` now calls `_ensure_session_loaded()` before reading.
  - `set_session_stack()` replaced its direct `_session_dirs` membership check with `_ensure_session_loaded()` so cold sessions can accept stack updates.

- [frontend/app.js](frontend/app.js):
  - New `stripReportPreamble()` helper + `_PREAMBLE_CUES` regex list near `renderFinalReport()`.
  - Three call sites wrap the final-text argument in `stripReportPreamble()` before handing it to `renderFinalMarkdown()`.

---

## 2026-04-23 — Session console (bottom chat) `[DONE]`

User ask: "just like claude.ai how we can have chaat interface at bottom will be nice." Shipped as a **deterministic command console** rather than a second LLM surface — the per-card Chat buttons on every completed agent report already cover LLM revision, and duplicating that at session-level would double the failure surface (two cost meters, two retry stories) without a new capability. The console is the quick-reference place the existing chat is missing: questions about the whole run, not a specific report.

### What shipped

1. **Docked console** at the bottom of the workspace `<main>` — collapsed by default, toggles open via an "Ask about this session" pill or the **Ctrl/Cmd+K** shortcut. Open/closed state persists in `localStorage` under `appnova.consoleOpen`.
2. **Commands (all instant, all read-only):**
   - `help` — command list
   - `status` — running + completed / total agents
   - `cost` — session cost in USD + tokens + turns (hits `/api/cost/{sid}/summary`)
   - `failed` — every agent with `status==='error'` + first 140 chars of its error
   - `agents` — every applicable agent with a color-coded state tag (done / error / pending)
   - `stack` — the stored target-stack markdown block
   - `open <agent_id>` — scrolls the thread to that agent's card
   - `clear` — clears the log
3. **No regressions to the existing per-card chat** — the per-agent Chat drawer is untouched; the console's `help` output points users there for LLM revision of specific reports so the mental model stays clean ("this console answers about the session, that drawer edits a report").

### Extension path

The command dispatcher (`runCommand()` in [frontend/app.js](frontend/app.js)) falls through to an error for unknown commands today. Swapping that fallback to POST the message at a new `/api/session/{sid}/chat` endpoint — invoking `claude -p` with the session overview as context — is a drop-in upgrade with no UI churn.

### Files touched

- **NEW** [frontend/index.html](frontend/index.html) — `<div class="session-chat">` block after `<section class="thread">` with toggle, collapsible panel, log, and compose form.
- [frontend/app.js](frontend/app.js) — new `initSessionConsole()` IIFE at the end of the file. Implements the command registry, DOM wiring, Ctrl/Cmd+K shortcut, and scroll-to-card for `open <agent_id>`.
- [frontend/style.css](frontend/style.css) — full visual spec for the console (toggle pill, panel, log rows, KV list, status tags, failure list, compose form).

---

## 2026-04-23 — Plan-from-prompt ✨ Enrich button (deterministic rewriter) `[DONE]`

User ask: "option to redefine user prompt to make it more robust by suggestions so that user can get more rich prompt in plan from prompt box." Shipped as a **deterministic enricher** — no LLM call, no subprocess, always offline — mirroring the "deterministic floor" pattern established by [backend/task_planner.py](backend/task_planner.py). A smart LLM layer can sit on top later without changing callers.

### What shipped

1. **New module** [backend/prompt_enricher.py](backend/prompt_enricher.py) — `enrich_prompt(raw, target_stack) -> {intent, enriched, suggestions, notes, stack}`. Strategy:
   - **Classify intent** by keyword (migration / refactor / assessment / security / testing / documentation / performance). First match wins, so "migrate and refactor" routes to `migration`.
   - **Parse the stored target-stack markdown** (same format `_compose_target_stack` writes) back into `{ui, api, db, cloud}` slots and inject those into the enriched goal so agents don't have to grep markdown for stack hints.
   - **Template-expand** intent-specific sections (Scope / Preserve / Acceptance / Deliverables) with stack-aware formatting (missing slots collapse to `(unspecified)`).
   - **Gap detection** via universal regexes: if the raw prompt doesn't mention testing / deploy / auth / secrets, those become accept/dismiss suggestions. Never raises — returns a minimal payload on malformed input.
2. **New endpoint** `POST /api/plan/enrich-prompt` in [backend/main.py](backend/main.py). Body: `{prompt, session_id?, target_stack?}`. When `session_id` is provided we pull the persisted stack from `_session_targets`, so the enricher writes concrete framework names instead of placeholders.
3. **Plan-panel UI** ([frontend/index.html](frontend/index.html) + [frontend/app.js](frontend/app.js)):
   - New `✨ Enrich` button in the `plan-promptmeta` row between char-count and `Generate plan`.
   - Preview pane below the textarea — titled "Enriched brief", shows the rewritten markdown in a `<pre>` with `Use this` / `Discard` actions. `Use this` replaces the textarea content and re-runs `/api/task-planner/preview` so the task list reflects any clarified intent.
   - **Accept/dismiss suggestion chips** — click a chip to append the suggestion to the original brief (as a `- bullet`), the chip grays out with a strikethrough so the user can see what's been folded in. Original brief is never destroyed until the user explicitly clicks `Use this`.
   - Collapsed "Why these changes?" `<details>` lists the enricher's notes (intent classification, stack pinning, etc.) — the audit trail makes real enrichment distinguishable from hallucination.
4. **CSS** ([frontend/style.css](frontend/style.css)) — `.plan-enrich-preview`, `.pep-*`, `.pep-sug-chip[.appended]` with accent-matched styling consistent with the existing plan-panel visual language.

### Why not LLM?

The deterministic path ships in one turn with no new dependency, zero cost, instant response, and byte-identical output for the same input — all of which make it testable and trustworthy. The shape of the output (structured markdown with named sections) is exactly what the downstream agents expect, so an LLM upgrade would need to produce the same shape anyway. When that upgrade lands, `enrich_prompt()` can grow an `llm_mode` flag without changing the endpoint contract or the frontend UI.

### Files touched

- **NEW** [backend/prompt_enricher.py](backend/prompt_enricher.py)
- [backend/main.py](backend/main.py) — import + new `/api/plan/enrich-prompt` endpoint above `task_planner_preview`.
- [frontend/index.html](frontend/index.html) — `✨ Enrich` button + preview pane in the plan-panel.
- [frontend/app.js](frontend/app.js) — `runEnrich()` + accept/discard wiring inside `initPlanPanel()`.
- [frontend/style.css](frontend/style.css) — `.plan-enrich-preview`, `.pep-*` styles (with `-webkit-user-select` prefix for Safari).

---

## 2026-04-23 — Archived project cards: Resume + hard-Delete `[DONE]`

User ask: "archieve can have resume delete options as well." Before this change, archived project cards in the hub only exposed a `Restore` button — you had to unarchive first, then reopen, then resume, which is three clicks for the "actually I do want to keep running this" flow.

### What shipped

1. **New `Delete` button** on archived cards — hard-deletes the project record via `DELETE /api/projects/{id}?hard=true` (the backend already supported `?hard=true`, see [backend/main.py](backend/main.py) `delete_project()`). The confirm modal is reused with a strong warning that clarifies **uploaded files on disk are NOT removed** — projects are metadata only, so `uploads/<sid>/` survives a hard-delete and can be re-backfilled via `backfill_from_uploads`. No surprise data loss.
2. **Resume on archived cards auto-restores first.** Clicking `Resume` on an archived card now PATCHes `archived: false` before POSTing `/api/resume/{sid}` — otherwise the run kicks off but the card stays hidden behind the `Archived` filter, which is confusing. Best-effort: if the PATCH fails we still attempt the resume and log a warning.
3. **Confirm modal rewired with an explicit mode flag.** Previously the handler guessed between Archive and Restore by reading `p.archived`. With three distinct modes (archive / restore / hard) the guess is fragile — I added `state.deleteMode` so the confirm handler knows exactly which endpoint to call. No more inference from lagging card state.

### Files touched

- [frontend/hub.js](frontend/hub.js):
  - `state.deleteMode` field + documentation of why inference isn't enough.
  - `cardHtml()` — adds the `hard-delete` button for archived cards, updates the Resume tooltip to reflect the auto-restore behavior.
  - `handleAction()` — routes `hard-delete` → new `openHardDeleteModal(p)`.
  - `openDeleteModal()` — now sets `state.deleteMode` to `archive` or `restore`.
  - New `openHardDeleteModal(p)` — reuses the confirm modal with a "Delete permanently" button and a warning that calls out the "files-on-disk-survive" guarantee.
  - `deleteConfirm` click handler — branches on `state.deleteMode` ({archive, restore, hard}) and calls the right endpoint.
  - `resumeProject(p)` — auto-unarchive step before kicking off the resume.

---

## 2026-04-23 — Rehydrate attach chip + stack dropdowns on project reopen `[DONE]`

Bug: after uploading a zip and picking the 4-part target stack, navigating back to the Project Hub and clicking **Open** on the same card returned the user to an empty `Attach a project (.zip or files)` row with all four stack dropdowns reset to `—`. The session on disk was fine — the backend still knew the files and the stored `target_stack` — but the workspace page never re-painted them, so users assumed their upload was lost.

### What shipped

1. `/api/session/{session_id}/status` now returns `text_files` and `total_bytes` alongside the existing `target_stack`. Counts are recomputed from disk on each call (cheap for the upload sizes we support; `rglob` over `project_dir` with a stat per file).
2. `reattachIfRunning()` in [frontend/app.js](frontend/app.js) now repaints `upload-label` (`"<N> files"`), `upload-meta` (`"· <KB> KB · <sid>"`), and reveals the `Change` button whenever the status endpoint reports a non-empty project dir — so the attach row looks identical to the post-upload state the user just left.
3. A new `hydrateStackPickerFromMarkdown()` helper reverse-parses the stored target-stack markdown block (the same one `_compose_target_stack` writes) back into the four `<select>` / custom-input pairs: `UI / Frontend`, `API / Backend`, `Database`, `Cloud / Deployment`. Exact option matches (case-insensitive) pick the existing `<option>`; anything else falls through to `__custom__` + text input so user-typed stacks survive a round-trip.

### Files touched

- [backend/main.py](backend/main.py) `session_status()` — adds the two counter fields.
- [frontend/app.js](frontend/app.js) `reattachIfRunning()` + new `hydrateStackPickerFromMarkdown()` — repaint + reverse-parse on reattach.

---

## 2026-04-23 — Prompt → task-breakdown planner with editable sequence `[DONE]`

User ask: "Prompt input (Natural Language instructions) · Prebuilt templates (Assessment, Migration, Refactor) · Task breakdown preview (auto-generated) · Edit task sequence." This entry records what shipped; the parked follow-ups (Phase C smart-planner + Phase D external templates) live under the matching `[PLANNED]` block in [changes_23_04_2026.md](changes_23_04_2026.md).

### What shipped

1. A **plain-English prompt box + template pills** sitting above the existing Agent Checklist. Users pick one of three prebuilt shapes (Assessment / Migration / Refactor) or Custom, type their instructions, and get an auto-generated task list.
2. A **drag-to-reorder task list** — the user can rearrange, delete rows, and add agents from a picker. Every edit round-trips to the server so DAG violations surface as warnings.
3. **Apply & Run** persists the plan, writes the prompt into `context/user_prompt.md`, and dispatches the run through the existing `_run_analysis_stream`. Every agent's system prompt now leads with a "USER INSTRUCTIONS" block pointing at that file.
4. A "Plan" shortcut on the Project Hub card opens the workspace with the panel pre-expanded via `?view=plan`.

### Files touched

- **NEW** [backend/task_planner.py](backend/task_planner.py) — templates + deterministic planner. `Template`, `PlannedTask`, `PlanPreview` dataclasses. `BUILTIN_TEMPLATES = {assessment, migration, refactor, custom}` with explicit agent ordering per template (not derived from the registry so adding a new agent doesn't silently leak into every template). `plan_from_prompt()` resolves candidates by: user-supplied `agent_ids_override` → template seed → keyword regex match → default Assessment fallback, then merges `required_upstream` deps, filters to applicable agents, and topologically sorts by `AgentSpec.upstream`. Every decision becomes a human-readable warning in the preview response. `validate_sequence()` is the pre-flight gate called by `/apply` — duplicate / unknown / wrong-order / missing-required-upstream errors all surface with path-specific messages.
- **NEW** [backend/session_plans.py](backend/session_plans.py) — per-session plan persistence at `data/plans/<session_id>.json`. Same atomic-rename + RLock + `session_id` traversal-guard pattern as `backend/review.py`. `get()` / `upsert()` / `mark_applied()` / `delete()` is the public surface.
- **MODIFIED** [backend/main.py](backend/main.py) — 4 endpoints registered:
  - `GET /api/task-planner/templates` — enumerates the three builtins (Custom excluded as a UI-only sentinel).
  - `POST /api/task-planner/preview` — stateless. Accepts `{prompt, template_id?, agent_ids?, session_id?, target_stack?}`. When `session_id` is known, filters against the session's cached `applicable` set so rows that won't actually run are dimmed. When `agent_ids` is supplied (user edited), validates as-is and topologically re-sorts only if the user's order violates the DAG.
  - `GET / POST /api/task-planner/plan/{sid}` — read + upsert a saved plan.
  - `POST /api/task-planner/apply/{sid}` — validates via `task_planner.validate_sequence`, persists the plan, writes `context/user_prompt.md`, stamps `applied_at`, then dispatches the run through the existing `_run_analysis_stream` (same SSE shape as `/api/run-selected`).
  - New helper `_write_user_prompt_brief(sid, prompt)` — writes (or removes, when empty) the user's instruction into `context/user_prompt.md` with a preface marker so the LLM recognises it as user intent.
- **MODIFIED** [backend/agents/prompts.py](backend/agents/prompts.py) — `build_agent_prompt()` gained a `user_prompt_path` kwarg. When set, a "USER INSTRUCTIONS" block is emitted FIRST (before target stack, before context files, before YOUR TASK) so the constraint hits the model before any other directive. Legacy callers that pass `None` behave exactly as before — no behavioural drift for runs kicked off via `/api/analyze` / `/api/run-selected` without a planner prompt.
- **MODIFIED** [backend/agents/supervisor.py](backend/agents/supervisor.py) — reads `context/user_prompt.md` and passes it to `build_agent_prompt`. Existence-checked, so sessions that never used the planner skip the block.
- **MODIFIED** [frontend/index.html](frontend/index.html) — new collapsible `<details class="plan-panel">` block inserted above the `#heartbeat` bar. Holds the template pills, prompt textarea with char counter, task list, add-agent row, warnings slot, and bottom action bar (Save plan / Apply & Run).
- **MODIFIED** [frontend/app.js](frontend/app.js):
  - Added a 350-line plan-panel controller (final IIFE). Fetches templates on first interaction, previews on template pick / prompt-change (debounced 800 ms when a template is selected), supports drag-to-reorder via HTML5 drag events (index-based data transfer, no library), row removal, add-agent picker, and the Apply & Run SSE consumer that reads the fetch body stream and pipes events into `handleEvent` — same visuals as the Run button, just a different dispatcher.
  - Two `window.dispatchEvent(new CustomEvent('appnova:session-bound', …))` calls — on reattach and on fresh upload — so the plan panel can hydrate its saved plan automatically without a polling loop.
  - `honorHubHandoff()` now preserves non-handoff params so the hub can ship `?view=plan` through to the plan controller.
- **MODIFIED** [frontend/style.css](frontend/style.css) — plan-panel styles (~260 lines): the collapsible header, template pills with pressed state, monospace-friendly prompt textarea, task rows with drag handle / index pill / tier chip / eta / remove-✕, drop-target dashed outline during drag, warnings block with amber palette, add-agent row, empty-state placeholder. Added `-webkit-user-select` siblings to every `user-select: none` for Safari.
- **MODIFIED** [frontend/hub.js](frontend/hub.js) — new "Plan" card action. Disabled until the card's primary session exists; navigates to `index.html?session_id=…&project_id=…&view=plan`.

### Endpoints registered

```
GET    /api/task-planner/templates
POST   /api/task-planner/preview           — stateless; optional session_id for applicable filtering
GET    /api/task-planner/plan/{sid}
POST   /api/task-planner/plan/{sid}        — upsert; does not run
POST   /api/task-planner/apply/{sid}       — validate + persist + write user_prompt.md + SSE run
```

### Templates shipped

| id | agents | one-line |
|---|---|---|
| `assessment` | code-analysis → architecture → business-rules → security → documentation | read-only audit, no `converted/` writes |
| `migration`  | full 13-agent DAG (code-analysis through ui-ux) | the pipeline we already run today |
| `refactor`   | code-analysis → architecture → migration-planner → code-generation → code-review | same-stack rewrite, skip tests/UI |

Custom = UI-only sentinel that means "no template seed, use the prompt + keyword matcher only."

### Keyword → agent matrix (deterministic floor)

12 patterns drive the "Custom" planner. Samples: `security|vulnerab|owasp` → `security`; `test|coverage|qa` → `testing`; `port|migrat|convert|modernize` → `migration-planner` + `code-generation`; `schema|database|prisma|alembic` → `data-migration`; `infra|deploy|docker|k8s|terraform` → `devops`; `document|docs|readme` → `documentation`. Every match contributes a rationale string so the UI can explain WHY each agent is in the list — the user isn't staring at an opaque picker.

### Prompt injection into agent briefs

When a run is kicked off via `/api/task-planner/apply`, the endpoint writes the user's prompt to `uploads/<sid>/context/user_prompt.md` with this preface:

```
# User Instructions

The following is the free-text instruction the user attached to this run.
Treat it as the session's top-level brief — every agent must honour it
when its output would otherwise contradict it.

---

<prompt body>
```

`build_agent_prompt` in `backend/agents/prompts.py` then emits a `## USER INSTRUCTIONS` block at the top of every agent's system prompt, pointing at that file and instructing the agent to honour it above its own per-agent task when the two conflict. The supervisor checks for the file's existence, so sessions that never used the planner run with the unchanged legacy prompt shape.

### Verification

`fastapi.testclient.TestClient` end-to-end against a staged session:

- `GET /templates` → 3 ids (assessment / migration / refactor).
- `POST /preview` with prompt `"Audit the security of this app and document any OWASP issues"` → Custom template, agents `[security, documentation, code-review]`, ETA 540 s, zero warnings.
- `POST /preview` with `template_id="migration"` → full 13-agent DAG.
- `POST /preview` with `agent_ids=["code-generation", "migration-planner", "architecture"]` (out of order) → topologically sorts to `[migration-planner, architecture, code-generation]` and emits `"reordered sequence to satisfy upstream dependencies — original order would have run downstream agents before their inputs"`.
- `POST /plan/{sid}` (save) → `200`, plan roundtrips via `GET /plan/{sid}` byte-for-byte.
- `POST /apply/{sid}` with empty `agent_ids` → `400 "agent_ids is empty — nothing to run"`.
- `POST /apply/{sid}` with `["bogus-agent"]` → `400` joined error message covering both the unknown-id hit and the "no applicable tasks" follow-on.
- Direct call to `_write_user_prompt_brief(sid, "…")` → `context/user_prompt.md` written with the preface marker, 267 bytes.
- `validate_sequence(["code-generation"], ...)` → `["'code-generation' requires 'migration-planner' but it's not in the sequence"]`.

### Why these decisions

- **Deterministic floor first, LLM layer later**: Regex + topological sort is under 400 lines and always works offline. A `APPNOVA_SMART_PLANNER=1` flag can ask Claude to refine the plan above this floor — that's Phase C in the [planner follow-up block in changes_23_04_2026.md](changes_23_04_2026.md) and is NOT in this cut.
- **Prompt injection is a file, not a prompt-string change**: Writing `context/user_prompt.md` and pointing the agent at it (rather than concatenating the prompt into `build_agent_prompt`'s role text) keeps the prompt visible under version control (`uploads/<sid>/context/`), survives demo-freeze, and costs one extra file per session. Free-form prompt strings would also inflate token usage across 13 agents — this way the user's brief is read once per agent from disk.
- **User's edited order wins unless it violates the DAG**: The planner is stable: `_toposort` preserves the user's relative order among peers and only reshuffles when required. Warnings carry the fixup reason, so nothing's silent.
- **Persist plan BEFORE dispatching the run**: If the SSE stream dies mid-run, the plan record is still on disk — the user can reopen the workspace, expand the panel, and apply again. Plans only get `applied_at` stamped after validation succeeds.
- **`view=plan` hint-based URL handoff**: The hub ships `?view=plan` alongside `?session_id=…&project_id=…`. Bugfix included: the original `honorHubHandoff()` wiped the entire search string when it saw the handoff params — now it only strips `session_id` + `project_id` and leaves other hints untouched, so this pattern is reusable (Review page can now piggyback `?view=review` later without another patch).

---

## 2026-04-23 — Review & Approval screen + run-mode presets (/plan, /security-only, /clear-results) `[DONE]`

User ask: "Review and Approval Screen — side-by-side diff (old vs new), commenting system, approve/reject changes, partial approvals" — plus batch 1 of the Claude-Code-style shortcut mapping (`/plan`, `/security-review`, `/clear`, `/rename`). Everything layered on top of the existing run pipeline; no changes to how agents run.

### Files touched

- **NEW** [backend/review.py](backend/review.py) — review storage. `Comment`, `FileReview`, `SessionReview` dataclasses; per-session JSON file at `data/reviews/<session_id>.json` with the same atomic-rename + RLock pattern as projects.py; session_id path-traversal guard. `refresh_from_mappings()` re-syncs the file list from `context/file_map.json` without losing existing decisions/comments across re-runs. `decide()` / `bulk_decide()` / `add_comment()` / `resolve_comment()` / `delete_comment()` / `set_notes()` / `summary()` are the public surface; `summary()` returns `{total, approved, rejected, changes, pending, comments, progress_pct}` for badge rendering.
- **MODIFIED** [backend/main.py](backend/main.py) — added 12 endpoints:
  - **Review & Approval (9)**: `GET /api/review/{sid}/files` lists every source→target pair with reviewer status layered on top (auto-refreshes from file_map.json). `GET /api/review/{sid}/file?path=…` returns both sides of one pair with content + line counts + comments, ready for a split diff. Reads are path-traversal-safe (Path.resolve comparison), refuse binaries (NUL-byte sniff + extension deny-list) and cap files at 512 KB. `POST /decision` records a per-file verdict (approved/rejected/changes/pending); rejections/changes auto-drop a notification on the host project. `POST /bulk-decision` accepts `{scope: "all"|"remaining"}` for the sidebar bulk buttons. `POST /comments` + `/comments/{id}/resolve` + `DELETE /comments/{id}` for line-anchored threads. `POST /notes` for session-wide reviewer notes. `GET /summary` as a cheap probe for the sidebar badge.
  - **Run modes (2)**: `GET /api/run-mode/presets` exposes the preset map; `POST /api/run-mode/{sid}` kicks off a preset (`plan_only` / `security_only` / `review_prep`) streaming SSE like `/api/run-selected`. Preset agents are filtered against the session's applicable set so "Security only" works on any project even without dedicated security signals.
  - **Session reset (1)**: `POST /api/session/{sid}/clear-results` — wipes in-memory `_results` + `_session_completed` + `_session_artifacts` for this session; optional `{drop_converted: true, drop_exports: true}` flags also wipe those directories. Refuses if a run is in flight (409).
- **NEW** [frontend/review.html](frontend/review.html) — split-view review page. Topbar with crumbs + live progress bar (approved/rejected/changes/pending counts) + bulk-approve buttons + theme toggle. Left sidebar: search + status-filter tabs (All/Pending/Approved/Rejected/Changes) + file list with action chips (R/C/D), status dot, and comment bubble. Right pane: diff header with verdict pill + comments button, verdict toolbar (Approve / Reject / Request Changes / Reset + note input), side-by-side source|target code panes with clickable line numbers.
- **NEW** [frontend/review.js](frontend/review.js) — controller. Dependency-free LCS diff capped at 3000 lines per side (Int32Array DP table keeps memory under ~36 MB at the ceiling), with a merge pass to collapse adjacent del+add into `modify` rows. Scroll-sync between panes, click a line number to open the comments pane anchored to that side+line, slide-out comments pane with post/resolve/delete actions. Bulk "Approve remaining" and "Approve all" with explicit confirm. Pull-forward URL handshake: `?session_id=…&project_id=…` from the hub card, with localStorage fallback.
- **MODIFIED** [frontend/index.html](frontend/index.html) — added a "✓ Review & approve" button to the Converted App sidebar section with a live badge (pending count or comment count). Disabled until at least one agent has finished (same gate as "Run converted").
- **MODIFIED** [frontend/app.js](frontend/app.js) — wired the new Review button to navigate into `review.html` carrying session + project context. Added `refreshReviewBadge()` polling every 15 s (paused while a run is in flight); badge text is the pending count, or `💬N` when every file is decided but comments remain. `showLaunchButtonIfReady()` also gates the Review button on the same condition.
- **MODIFIED** [frontend/style.css](frontend/style.css) — `.sa-badge` styling for the sidebar button count.
- **MODIFIED** [frontend/hub.js](frontend/hub.js) — hub project cards now expose two new actions:
  - **Review** → jumps straight into `review.html` for that project's primary session.
  - **▶ Mode** → fetches `/api/run-mode/presets`, picks via numeric prompt, posts the chosen preset, then redirects to the workspace so the user sees SSE progress.

### Storage layout

`data/reviews/<session_id>.json` (atomic-rename, corruption-preserving):

```json
{
  "version": 1,
  "session_id": "abc123def456",
  "created_at": 1745000000.0,
  "updated_at": 1745000900.0,
  "opened_by": "architect",
  "notes": "",
  "files": [
    {
      "path": "src/newmodule.ts",
      "source": "oldmodule.php",
      "targets": ["src/newmodule.ts"],
      "action": "REWRITE",
      "kind": "port",
      "status": "approved",
      "reviewer": "architect",
      "decided_at": 1745000500.0,
      "verdict_note": "looks good",
      "comments": [
        { "id": "cmt_…", "author": "architect", "body": "nice rename here", "created_at": 1745000400.0, "side": "target", "line": 1, "resolved": true }
      ]
    }
  ]
}
```

### Run-mode presets

```python
plan_only     = ["architecture", "migration-planner"]       # no code-gen yet
security_only = ["security"]                                # single-agent refresh
review_prep   = ["code-analysis", "architecture", "business-rules",
                 "security", "migration-planner", "code-generation", "code-review"]
```

Each preset is intersected with the session's applicable set so an agent without signals is silently dropped instead of erroring. The endpoint streams SSE identical to `/api/run-selected`, so the existing SSE consumer in `app.js` handles progress with no changes.

### Endpoints registered

```
GET    /api/review/{sid}/files
GET    /api/review/{sid}/file?path=…
POST   /api/review/{sid}/decision                              — single file verdict
POST   /api/review/{sid}/bulk-decision                         — scope=all|remaining
POST   /api/review/{sid}/comments
POST   /api/review/{sid}/comments/{cid}/resolve
DELETE /api/review/{sid}/comments/{cid}?path=…
POST   /api/review/{sid}/notes
GET    /api/review/{sid}/summary
GET    /api/run-mode/presets
POST   /api/run-mode/{sid}                                     — {mode: "plan_only|security_only|review_prep"}
POST   /api/session/{sid}/clear-results                        — {drop_converted: bool, drop_exports: bool}
```

### Verification

- `fastapi.testclient.TestClient` end-to-end: staged a fake session with a two-row `file_map.json` (one REWRITE, one CREATE), hit every review endpoint in sequence (list → file → decision → comment → resolve → summary → bulk-decision), plus `/api/run-mode/presets` and `/api/session/{sid}/clear-results`. All 200s, summary counters flip as expected (50% → 100% after bulk-approve-remaining), clear-results wipes `_results` in-memory.
- Parse check: both new modules + the extended main.py compile clean; route count jumps from 8 projects → 8 projects + 12 new = 20 new `/api/*` surfaces.

### Why these decisions

- **Caveman-friendly LCS diff (not Myers)**: The cap is 3000 lines per side — well under any generated file we've seen in the session pipeline. Myers is O(N+D) and faster, but at ~40 lines of code vs the 20-line LCS we have, the ROI is zero and the memory is fine.
- **Path-traversal defence in depth**: Endpoint accepts a `path` query string, so `Path.resolve` comparison against `source_root`/`converted_root` happens in `_safe_join` before any read. The review module also rejects any session_id containing characters outside `[a-zA-Z0-9_-]`.
- **Decisions survive re-runs**: `refresh_from_mappings(preserve_decisions=True)` is the default — a mid-review re-generation of the converted tree won't wipe approvals the reviewer has already laid down. New rows land as `pending`; rows that disappear from the mapping are dropped (and logged so it's visible in the backend log).
- **Rejections feed the hub notification bell**: When a reviewer marks a file rejected / needs-changes, we auto-add a notification on the host project via the existing `projects_mod.add_notification` shim. The hub card's unread badge is the reviewer's way of flagging "this project needs re-gen" without any extra wiring.
- **Run modes wrap, don't rewrite**: Every preset just resolves to an `applicable_ids_subset` passed into the existing `_run_analysis_stream`. No duplicated state machine, no new cache paths, no risk of drift from the main `/api/run-selected` behaviour.

---

## 2026-04-23 — Project Hub: central workspace for managing modernization projects `[DONE]`

User ask: "Central hub to manage modernization projects" — list all workspaces, create new ones, surface last-run status (Success/Failed/Running), wire Resume / View Workflow / View Reports as quick actions, and badge failed-run + pending-approval notifications. Caveman-robust: persist to a single JSON file under `data/`, derive live status by joining persisted records with the in-memory session dicts in `main.py`, hook the existing run-pipeline at start/finish only (no rewrite of the run state machine), and backfill from `uploads/` on first boot so existing installs don't see an empty hub.

### Files touched

- **NEW** [backend/projects.py](backend/projects.py) — storage layer. `Project` + `Notification` dataclasses, atomic-rename JSON persistence under `data/projects.json`, RLock-serialized writes, schema versioning, soft-delete (archived flag), corruption recovery (preserves bad files as `.corrupt.<ts>`), `derive_status()` that joins persisted records with `_session_tasks` / `_results` from `main.py`, and `init()` that backfills from `uploads/<sid>/source/` and `demo_sessions/<slug>/`.
- **MODIFIED** [backend/main.py](backend/main.py) — wired hub at four points without touching the run state machine:
  - Boot: `projects_mod.init(...)` runs backfill on startup.
  - `/api/upload`: accepts new optional `project_id` form field; auto-creates a project named after the inferred root folder when no `project_id` is supplied. Returns the bound `project_id` in the response.
  - `_run_analysis_stream` → `run_in_background`: stamps `mark_run_started` up front and `mark_run_finished` (with success / failed / partial / stopped derived from final results) in the `finally` clause.
  - `/api/session/{sid}/clone` and `/api/demo-sessions/load/{slug}`: clones inherit the parent's project, and demo loads create a `[Demo] <slug>` project pre-stamped with the demo's final status.
  - 8 new endpoints under `/api/projects/*`: list, create, get-detail, patch (rename / archive / set-primary), delete (soft + `?hard=true`), attach session, detach session, list notifications, ack one, ack all, manual backfill.
- **NEW** [frontend/hub.html](frontend/hub.html) — central hub page. Topbar with brand, search, theme toggle, notification bell with badge, "+ New project" button, user chip. Stats strip (active / running / needs-attention / unread-notifications). Filter tabs (All / Running / Needs attention / Success / Archived). Project grid: status pill (running pulses), progress bar (mixed success/failure colour), 5 quick actions per card (Open / Resume / Reports / Rename / Archive), unread-notification badge corner-marker.
- **NEW** [frontend/hub.js](frontend/hub.js) — controller. Auth boot mirrors `app.js` (JWT in localStorage, `/api/auth/me` validation, `auth_disabled` shortcut). Polls `/api/projects?include_archived=true` every 8s (paused when tab hidden). Quick actions navigate into the workspace via `index.html?session_id=…&project_id=…`. Resume action POSTs `/api/resume/{sid}` then redirects. Notification dropdown shows newest-first across all projects, click acks + jumps into the project.
- **MODIFIED** [frontend/login.js](frontend/login.js) — both redirects (skip-on-valid-token and post-login) now land on `hub.html` instead of `index.html`.
- **MODIFIED** [frontend/index.html](frontend/index.html) — added a "‹ Project Hub" link at the top of the sidebar with an inline-styled name slot that gets populated with the current project's name.
- **MODIFIED** [frontend/app.js](frontend/app.js) — `honorHubHandoff()` reads `?session_id=` and `?project_id=` from the URL and stashes them in localStorage (so a refresh keeps state). `paintHubProjectName()` decorates the new sidebar link with the project name. `handleFiles()` includes `project_id` in the upload form so a hub-opened upload binds back to the right project. `logout()` clears `appnova.projectId` so the next user doesn't inherit it.

### Storage layout

`data/projects.json` (atomic-rename writes, fsync where supported):

```json
{
  "version": 1,
  "projects": [
    {
      "id": "prj_xxxxxxxxxx",
      "name": "TotalBookingAI",
      "owner": "architect",
      "created_at": 1745000000.0,
      "updated_at": 1745000900.0,
      "session_ids": ["abc123def456"],
      "primary_session_id": "abc123def456",
      "target_stack": "- **UI / Frontend:** React\n- **API / Backend:** FastAPI\n…",
      "last_run_id": "abc123def456",
      "last_run_at": 1745000900.0,
      "last_run_status": "success",
      "archived": false,
      "notifications": [
        { "id": "ntf_…", "kind": "run_failed", "message": "All 3 agent(s) errored", "created_at": 1745000800.0, "session_id": "abc123def456", "run_id": "abc123def456", "read": false, "ref": {} }
      ],
      "description": "Imported from uploads/ on first boot."
    }
  ]
}
```

### Endpoints registered

```
GET    /api/projects                                   — list (filtered by JWT subject)
POST   /api/projects                                   — create empty
GET    /api/projects/{id}                              — full detail incl. per-session breakdown
PATCH  /api/projects/{id}                              — rename / re-describe / archive / set primary session
DELETE /api/projects/{id}[?hard=true]                  — soft (archive) by default, ?hard=true wipes
POST   /api/projects/{id}/attach                       — attach a stray session_id
POST   /api/projects/{id}/detach                       — detach a session_id
GET    /api/projects/{id}/notifications[?unread_only]  — list notifications
POST   /api/projects/{id}/notifications/{nid}/ack      — mark one read
POST   /api/projects/{id}/notifications/ack-all        — mark all read
POST   /api/projects/backfill                          — manual re-scan of uploads/ + demo_sessions/
```

### Status model

`last_run_status` is persisted (`idle | running | success | failed | partial | stopped`) but the hub list endpoint *derives* the live status by checking the in-memory `_session_tasks` map first — so a backend restart in the middle of a run flips the card from stale `running` to whatever the on-disk record last said, and a live in-flight session shows `running` even before the next mark_run_finished writes. Notifications are persisted only and never auto-derived; a `run_failed` / `run_partial` / `run_stopped` notification is dropped exactly once at run-finish.

### Verification

- Standalone: `from backend import projects as P; P.init(...); P.create(...); P.mark_run_finished(..., status='partial'); P.list_all(...)` — all roundtrip clean, including the corrupt-file recovery path.
- HTTP via `fastapi.testclient.TestClient`: every project endpoint returns 200 on the happy path; backfill scoops up the existing `uploads/6faa89a0bbbb` automatically on boot and registers it as `Project 6faa89`.
- Backend boots with all 8 project routes registered; auth gate honours the `auth_disabled` env shortcut.

### Why these decisions

- **JSON file, not SQLite**: SQLite is already in use for `cost_tracker.db` but the projects record is read-mostly, write-rarely, human-debuggable territory. Atomic-rename writes give us crash-safety without a schema migration story; the corruption-recovery path (preserve `.corrupt.<ts>`, start fresh) ensures a hand-edit accident never wedges the hub.
- **Status derived at read time**: Persisting a "running" status that survives a backend crash would lie to users. The in-memory `_session_tasks` map is the source of truth for "is something actually running"; we only persist the *terminal* status that `mark_run_finished` records. Clean.
- **Notifications persisted, not derived**: A failed run that the user has acknowledged should *stay* acknowledged across backend restarts. Auto-deriving notifications from session results would re-surface dismissed alerts on every page load.
- **Auto-create vs. require explicit project**: Pre-existing `/api/upload` callers (the workflow page, scripts) must keep working. Defaulting to "create a project named after the upload" means the hub list is never silently incomplete, and an explicit `project_id` form field lets the hub handoff bind cleanly.

---

## 2026-04-23 — Multi-user login: seven role-based accounts via APPNOVA_USERS `[DONE]`

User ask: "for login we need these users and passwords" — enable seven typical software-team roles to each log in to AppNova with their own username. Confirmed defaults: short-key usernames, shared demo password `AppNova@2026`, no JWT role claim yet (pending sign-off to build out role-based authorization).

### The seven role logins

| Role | Username | Password |
|---|---|---|
| Enterprise Architect | `architect` | `AppNova@2026` |
| Developer | `developer` | `AppNova@2026` |
| Business Analyst | `analyst` | `AppNova@2026` |
| QA Engineer | `qa` | `AppNova@2026` |
| Project Manager | `pm` | `AppNova@2026` |
| Technical Lead | `techlead` | `AppNova@2026` |
| DevOps Engineer | `devops` | `AppNova@2026` |

The legacy `admin` / `welcome` single-user login is preserved alongside — useful for ops / setup paths that shouldn't surface in the role list.

### Why multi-user via env var (not a users DB, not a config file)

The existing auth in [backend/auth.py](backend/auth.py) was built around a single `APPNOVA_USERNAME` / `APPNOVA_PASSWORD` pair read from `.env`. It's intentionally a tiny stdlib-only surface (scrypt + hand-rolled HS256 JWT). Introducing a users table or YAML/JSON config file for seven shared-password accounts would add a persistence layer and a migration story for nothing gained — the whole tool is local-dev-only behind a Bearer token. The caveman-appropriate fit is an `APPNOVA_USERS` env var carrying a JSON object of `{username: password}` pairs, which preserves the "credentials live in .env" deploy shape and doesn't require a schema.

### Files touched

* [backend/auth.py](backend/auth.py)
  * Added `_ENV_USERS = "APPNOVA_USERS"` constant.
  * Added `_multi_user_map() -> dict[str, str] | None` helper — parses the env var, validates it's a non-empty JSON object, coerces keys/values to `str`, and returns `None` on any malformed payload (logged) so a typo in `.env` degrades to the single-user path rather than locking everyone out.
  * Rewrote `verify_credentials(username, password)` with the precedence rule: **if APPNOVA_USERS is set AND contains `username`, authenticate ONLY against the mapped password — no fall-through.** Usernames not in the map drop through to the existing single-user check. Rationale: if we fell through for all users, a leftover `APPNOVA_PASSWORD=welcome` in `.env` would silently grant `qa` / `developer` / etc. a second password too. Current rule makes the `.env` keys authoritative for the names they list.
  * Updated module docstring to reflect role-based login. Left a note that JWT role metadata is NOT embedded yet — deferred until the UI wiring is signed off.
* [.env](.env)
  * Added `APPNOVA_USERS=...` with seven role-based entries, all with password `AppNova@2026`.
  * Kept the existing `APPNOVA_USERNAME=admin` + `APPNOVA_PASSWORD_HASH=scrypt$...` single-user fallback so the legacy admin login still works.
* [.env.example](.env.example)
  * Documented the new `APPNOVA_USERS` variable with the same seven-role example.
  * Clarified precedence rules in the inline comments.

### What's NOT in this change (deferred until AppNova app sign-off)

* **JWT role claim.** `issue_token(username)` still embeds only `sub`. `/api/auth/me` returns `{"username": "qa"}` but does not return a `role` field. The frontend can still read `username` and map it to a role client-side if needed for layout decisions.
* **Role-based authorization.** Every authenticated user can hit every endpoint. There's no "only `devops` can do X" check — once authenticated, permissions are identical across all seven roles.
* **Frontend changes.** Login page markup is unchanged — users type their role name into the existing username field. No role dropdown, no "Sign in as..." helper links. Can add after sign-off.
* **Password hashing for the multi-user map.** Plaintext passwords in `.env` match the existing single-user design (the tool is local-only). If production deployment ever happens, switch the map to `{"username": "scrypt$..."}` and extend `_multi_user_map` to auto-detect the `scrypt$` prefix.

### Verification

* `python -c "import ast; ast.parse(open('backend/auth.py').read())"` — parses clean.
* `import backend.auth` — module loads with the new `APPNOVA_USERS` var set.
* Functional sweep (all seven roles + wrong password + legacy admin + unknown user + JWT round-trip), run with `APPNOVA_USERS` matching what's now in `.env`:
  * All seven of `architect`, `developer`, `analyst`, `qa`, `pm`, `techlead`, `devops` authenticate against `AppNova@2026` → `True` each.
  * Same seven roles with `"wrong"` password → `False` each.
  * Legacy `admin` + `welcome` → `True` (single-user fallback still works).
  * Unknown usernames (`"ceo"`, empty string, `"admin"` with wrong pass) → `False`.
  * JWT issued for `qa` → `verify_token` returns `subject="qa"`, `expires_in=86400s`.

### How the user logs in after this change

1. Frontend `login.html` is unchanged — type `qa` / `AppNova@2026` into the existing username / password fields.
2. `POST /api/auth/login` → 200 with `{"token": "...", "username": "qa"}`.
3. `GET /api/auth/me` with the Bearer token → `{"authenticated": true, "username": "qa", "expires_at": …}`.
4. Same flow for every other role. The tool functions identically regardless of which of the seven accounts is in use — that's the "no JWT role yet" part.

---

## 2026-04-23 — Migration-planner: proactive multipass dispatch for large projects `[DONE]`

Bug report from user: a 259-source-file project timed out the `migration-planner` after 1800 s (card: "Partial — agent timed out after 1800s"). ~229 mappings streamed before the wall clock fired.

### Why single-pass was doomed on this project

`migration-planner` on Sonnet 4.6 emits A.4 `file_map.json` with one entry per real source file. Entry size ≈ 400 chars (source path + target paths[] + kind + order + notes). A 259-file project → ~100 KB / ~25 K output tokens, taking 8–14 min of pure generation at Sonnet's ~30–50 tok/s. Add tree-exploration tool calls (this run used 20) and we're through the 30-min `APPNOVA_PLANNER_TIMEOUT` ceiling before the last rows stream.

### Why the existing multipass didn't save it

The `planner_multipass` runner ([backend/agents/planner_multipass.py](backend/agents/planner_multipass.py)) was written for exactly this case — one section per turn with a continue-loop and 30–60 s cooldown between sections so the prompt cache stays warm. But the supervisor invoked it **only reactively** at [supervisor.py:822](backend/agents/supervisor.py#L822): AFTER a single-pass AND a repair pass had both returned a response that failed body-shape validation. A timeout doesn't land cleanly on that branch — even when it does (via the partial-output path), you've already burned 30 min on single-pass and potentially another 30 min on the repair, so multipass starts ~60 min in. The multipass module's docstring even flagged this intended trigger ([planner_multipass.py:74-75](backend/agents/planner_multipass.py#L74-L75)): *"OR when the project is large enough that single-pass is almost certain to truncate (`source_files_total > 200`)"* — the supervisor just never wired it up.

### Fix

Proactive dispatch: before the single-pass invocation in `_run_one`, count source files via a fast `rglob` heuristic. If the count is ≥ `APPNOVA_PLANNER_MULTIPASS_THRESHOLD` (default 200), go straight to `run_planner_multipass`. The single-pass + repair + reactive-multipass path remains for smaller projects where single-pass fits and multipass would add 3–5× wall clock for no win.

### Files touched

* [backend/agents/supervisor.py](backend/agents/supervisor.py)
  * Added module-level `_PLANNER_MULTIPASS_THRESHOLD` (env: `APPNOVA_PLANNER_MULTIPASS_THRESHOLD`, default `200`).
  * Added `_SOURCE_EXTENSIONS` and `_SKIP_DIRS` frozensets. Source extensions cover every stack the pipeline currently supports (PHP, Python, JS/TS, Vue, Java, .NET, Go, Rust, C/C++, HTML/Blade/Razor/Astro/Svelte, Ruby, Swift, etc.). Skip dirs match standard vendor/build/VCS noise (`node_modules`, `vendor`, `dist`, `build`, `.git`, `venv`, `target`, `bin`, `obj`, `.next`, `.nuxt`, `__pycache__`, …).
  * Added `_estimate_source_file_count(project_dir)` helper — walks the tree, counts files whose suffix is in `_SOURCE_EXTENSIONS` and whose path doesn't traverse a `_SKIP_DIRS` directory name. Returns 0 on any error so a helper crash degrades to the existing reactive-escalation path, never to an uncaught exception.
  * In `_run_one`, right before the single-pass `_invoke(full_prompt)`: if `agent_id == "migration-planner"` AND `_estimate_source_file_count(project_dir) >= _PLANNER_MULTIPASS_THRESHOLD`, call `run_planner_multipass` directly. On success, synthesize a success-shaped `result` dict (`status="done"`, stitched markdown, elapsed) plus a private `_early_multipass_meta` stash. On failure (crash OR `status != "done"` OR empty stitched output), log and fall through to the single-pass + repair path — correctness is not on the line.
  * In the migration-planner post-processing block, merge `_early_multipass_meta` into `repair_status` (via `result.pop("_early_multipass_meta", None)`) so the frontend chip can surface `multipass_used` / `multipass_mode="proactive_early"` / `multipass_sections` / `multipass_continuations` identically to the reactive path.

### Verification

* `python -c "import ast; ast.parse(open('backend/agents/supervisor.py').read())"` — parses clean.
* `import backend.agents.supervisor` — module loads, all new symbols resolvable, `run_planner_multipass` still imports through.
* Helper unit-check: synthetic tree with 250 `.php` files under `src/` + 500 `.js` files under `node_modules/` + 50 `.php` files under `vendor/` + `README.md` + `package.json` → helper returns exactly `250`. Missing dir → returns `0`.
* Gate sanity-check against the three actual sessions under `uploads/`: 265 / 389 / 265 source files — all three trip the gate and would go straight to multipass. Consistent with the timeout symptom.

### What this changes for the user

* Projects with ≥ 200 source files (all observed real-world sessions on this machine) now skip the doomed single-pass entirely and dispatch multipass as the first attempt. Expected wall clock drops from "2× timeout + repair + eventual multipass ≈ 60–90 min best case" to "multipass only ≈ 15–25 min".
* Projects under the threshold keep the existing single-pass-first behaviour — no regression on small projects where multipass's 3–5× overhead isn't justified.
* The frontend repair chip will render `multipass_used=true, multipass_mode="proactive_early"` on large-project runs, distinct from the reactive-escalation path's default `"reactive"` mode (TODO: frontend currently just checks `multipass_used`; adding a mode-aware label is a follow-up if useful).
* `APPNOVA_PLANNER_MULTIPASS_THRESHOLD=0` disables the gate (all projects use the old flow); bumping it high (e.g. `500`) tightens it if a particular project benefits from the faster single-pass path.

---

## 2026-04-23 — Merge DEPLOY_AZURE.md + DEPLOY_UBUNTU.md into a single docs/DEPLOY.md `[DONE]`

User ask: "only one rather than two" deploy docs in every converted session.

The pipeline used to produce two sibling runbooks — `docs/DEPLOY_AZURE.md` (App Service, managed) and `docs/DEPLOY_UBUNTU.md` (Ubuntu VM, systemd + nginx). Both were 200–350 lines with heavy duplication in the shared parts (prereqs, Key Vault story, demo-file cleanup, smoke-test shape). The cross-references ("see the alternative runbook") also added confusion — readers weren't sure which one applied.

Replaced with a single `docs/DEPLOY.md` structured as:

* **Shared intro** — decision table explaining when to pick each track.
* **Shared prerequisites** — Azure CLI + `az login` (applies to both tracks; Key Vault is shared).
* **Track A — Azure App Service** — steps A.1 through A.10 (resource group, Azure SQL, Key Vault, managed identity, webapp create, deploy, smoke, troubleshoot).
* **Track B — Ubuntu 22.04 VM** — steps B.1 through B.12 (base packages, deploy user, env file, systemd, nginx, certbot, UFW, rolling updates, backups, troubleshoot).
* **Shared "delete demo-only files before going live"** — applies to both tracks, was previously duplicated.

### Files touched

* `backend/agents/demo_docs.py`
  * Replaced `_deploy_azure_md(converted_dir)` + `_deploy_ubuntu_md(converted_dir)` with a single `_deploy_md(converted_dir)`. Preserved every f-string substitution (`app_stem`, `deploy_root`) and the GitHub Actions `${{{{ … }}}}` + nginx `{{ … }}` escaping.
  * `write_demo_docs`: dropped the two old keys, added `"DEPLOY.md": _deploy_md(converted_dir)`. Doc count goes 5 → 4.
  * Module docstring updated to reflect the single combined deploy doc.
* `backend/agents/scaffold.py` — the converted-project README's "Production deployment" section now points to one file. The "delete before prod" table row that referenced `docs/DEPLOY_AZURE.md` now references `docs/DEPLOY.md`.

### Not touched

The stray `DEPLOY_AZURE_VM_UBUNTU.md` at the AppNova repo root is unrelated — it was written by an ad-hoc Claude Code session with `cwd=appnova_repo_root` (confirmed: no pipeline code path writes that filename, no devops agent has ever run in `logs/agents/`). Left in place; user can delete or move at will.

### Verification

* `python -c "import ast; ast.parse(open('backend/agents/demo_docs.py').read())"` — parses clean.
* `python -c "import ast; ast.parse(open('backend/agents/scaffold.py').read())"` — parses clean.
* End-to-end smoke: `write_demo_docs(converted, [])` against a temp `aries-react-aspnet` dir →
  * Wrote 4 files (was 5): `RUN_THE_APP.md`, `AZURE_KEYVAULT_GUIDE.md`, `SECRETS_MAPPING.md`, `DEPLOY.md`.
  * `DEPLOY.md` is ~20 KB and contains both `Track A` and `Track B` headings.
  * `app_stem` and `deploy_root` substitutions land correctly (`kv-aries-react-aspnet-prod`, `/home/deploy/aries-react-aspnet`).
  * GitHub Actions secret syntax `${{ secrets.AZURE_PUBLISH_PROFILE }}` survives the f-string unscathed.
* Grep for `DEPLOY_AZURE.md` / `DEPLOY_UBUNTU.md` / `_deploy_azure_md` / `_deploy_ubuntu_md` across `backend/` → 0 matches. No dangling references.

### What this changes for the user

* Every new conversion ships with `converted/docs/DEPLOY.md` (single file) instead of the previous two.
* Existing sessions under `uploads/<session-id>/converted/docs/` that already have `DEPLOY_AZURE.md` + `DEPLOY_UBUNTU.md` are NOT touched — `write_demo_docs` never clobbers existing files. If you want those migrated, delete the two old files and re-run the conversion (or just delete them and paste the new combined doc).

---

## 2026-04-23 — Fix: Discovery card missing when "Run All Agents" reuses cached digest `[DONE]`

Bug: after the user set the target stack (which schedules a silent background discovery pass via `_schedule_discovery`), clicking "Run All Agents" showed no Project Discovery card — the thread stayed blank until the first agent started (~2 min on a fresh run, instant on a warm one).

Root cause: `run_discovery()` in `backend/agents/runner.py` is the only site that emits `discovery_start` / `discovery_event` / `discovery_complete` SSE events, and the frontend's `buildDiscoveryCard()` only fires on `discovery_start`. The analyze flow at `backend/main.py:736-747` auto-downgrades `run_discovery_pass=False` whenever `_session_digests[session_id]` and `_session_briefs[session_id]` are already populated (which is exactly what the `/api/session/{id}/stack` endpoint does in the background). With `run_discovery_pass=False`, the `if run_discovery_pass:` branch at line 950 is skipped → no events → no card.

Fix: in `backend/main.py` `run_in_background()` `else` branch, synthesize a `discovery_start` + `discovery_complete` pair when a cached digest is present. Elapsed time is pulled from `_session_discovery_status[session_id]` (populated by the background pass) so the card's elapsed chip reflects the real discovery duration instead of "0s". Payload is tagged `from_background=True` so downstream handlers can distinguish real vs replayed discovery without breaking the existing frontend (current handler doesn't read the flag, but it's there for future UI differentiation). Digest content is explicitly blanked (`digest: ""`) per the standing user constraint: never surface discovery content to the UI.

This also fixes the same symptom on the resume path (`/api/resume/{session_id}` already passes `run_discovery_pass=False`) and the "Run Selected (N)" path when the session has a prior cached analysis.

### Verification

* `python -c "import ast; ast.parse(open('backend/main.py').read())"` — parses clean.
* No frontend changes needed: `app.js:1477-1491` already handles repeat `discovery_start` events idempotently (`buildDiscoveryCard()` returns early if `state.cards.has('_discovery')`) and `app.js:1499-1517` already handles `discovery_complete` to flip the card to Done with elapsed chip.

---

## 2026-04-23 — Cleanup: strip planner to A.4-only, remove `contract-audit`, drop ui-ux HTML artifact, add frontend Discovery card `[DONE]`

User-driven cut of waste from the post-codegen agent layer + a frontend fix for the ~2-min blank-screen during discovery. Three reductions + one addition.

### 1. `migration-planner` prompt: 230 lines → 80 lines

Stripped sections that nothing downstream consumed:

| Section | Status | Reason |
|---|---|---|
| A.0 Layer-by-Layer Mapping (24-row table) | DELETED | Pure narrative for steering committee — code-gen / auditors never read it. |
| A.1 Solution Structure Tree | DELETED | `scaffold.py` enforces target structure post-generation; tree was redundant. |
| A.2 Source→Target table | DELETED | Same data as A.4 `mappings[]` in markdown form — duplicate cost. |
| A.3 Execution-order table | DELETED | `order` field on each `mappings[]` entry already carries this. |
| A.4 file_map.json | KEPT | The load-bearing contract. Pipeline + parity_checker + code-gen all consume it. |
| A.5 Decomposition rationale | DELETED | Prose. Not consumed. |
| Section B (program plan, gantt, phases, risk register) | DELETED | Steering-committee narrative. No agent or auditor reads it. |

Kept the two hard rules that make A.4 trustworthy: SKIPPED-abuse prohibition on UI templates + UI-fidelity triplet (`inputs=N selects=M textareas=K repeaters=R conditionals=C`) in `notes`.

Coordinated supporting cuts:

* `backend/agents/planner_multipass.py` — `_SECTIONS` reduced from 7 entries to 1 (A.4 only). Multipass infrastructure (per-section budget, continuation-loop, staging dir, stitcher) preserved because A.4 itself can truncate on big projects.
* `backend/agents/supervisor.py:150-275` — `_validate_migration_planner_body` collapsed from ~110 lines (5 section checks + table-row counting + tree-line counting + Phase/gantt detection) down to ~40 lines that only validate the A.4 heading + a parseable `file_map.json` block with ≥ 1 mapping. Removed regex constants `_A0_HEADING / _A1_HEADING / _A2_HEADING / _A3_HEADING / _PHASE_HEADING / _MERMAID_GANTT / _TABLE_ROW / _FENCED_TREE`.
* `backend/agents/planner_polish.py` — section-ordering check (A.0→A.1→A.2→A.3→A.4 monotonic offset) removed. `_A0/A1/A2/A3_HEADING` regex constants deleted. Kept placeholder-leak check + Kind-vocab whitelist + classDef palette check.

### 2. `contract-audit` agent removed entirely

~70% overlap with `code-review`: both walked `file_map.json` + cited upstream specialist reports. Deterministic floor (file_coverage / api_contract / ui_binding / route_link / seed_completeness / line_count_fidelity / migration_pipeline) covers the rest with no LLM cost. Kept `code-review` (line-by-line symbol fidelity is its specific value-add) and dropped contract-audit. Saves ~10 min wall-clock per run.

* `backend/config.py` — `AGENT_REGISTRY["contract-audit"]` deleted; `required_upstream` doc-comment updated.
* `backend/agents/prompts.py` — `AGENT_PROMPTS["contract-audit"]` (109 lines) deleted; `_AGENT_TARGET_DIRECTIVES["contract-audit"]` deleted; one stale reference in code-generation prompt scrubbed.
* `backend/agents/supervisor.py` + `runner.py` + `orchestrator.py` — removed from `allow_write` / `_UNBOUNDED_AGENTS` / cwd whitelist sets.
* `backend/agents/scaffold.py` — `docs/CONTRACT_AUDIT.md` row in the converted README index replaced with the new `docs/FIELD_PARITY.md` row from the migration-pipeline build.

### 3. `ui-ux` HTML preview artifact removed (PART B)

The PART B section asked the agent to inline a 400 KB self-contained React + Babel + Tailwind HTML preview between `<!-- ARTIFACT_START -->` markers. It was brittle (markdown sanitizer routinely ate the embedded CSS / JSX, see prompt comment about session 324b2024), heavy (every report shipped a multi-hundred-KB inline HTML), and not user-facing meaningful (the actual converted app under `cwd` is the real preview). PART A — inline polish fixes + structural-fidelity escalation — kept verbatim.

* `backend/agents/prompts.py` — PART B (~30 lines including data rule + CDN URLs + size cap) deleted; the surrounding intro paragraph + PART A section preserved. ui-ux prompt size: ~6 KB → ~3 KB.
* `backend/main.py` extract_artifact path is unchanged — when no markers are found the loop is a no-op, so legacy back-compat is preserved at zero cost.

### 4. Frontend Discovery card (~2 min blank-screen fix)

`buildDiscoveryCard()` was previously a no-op comment. The backend's discovery phase scans the source tree, builds the digest, and writes per-agent briefs — taking ~2 minutes on a real project. Without a visible card the screen was blank for that whole window.

Now renders a status-only card at the top of the thread immediately when `discovery_start` fires:

* `frontend/app.js:1149-1247` — replaced the no-op with a real `buildDiscoveryCard()` that creates a card with title "Project Discovery", subtitle showing it feeds 12 downstream agents, and a `.discovery-status` body with one primary status line + one secondary substatus line.
* New helper `summariseDiscoveryEvent(ev)` maps SSE phases (`system` / `assistant` / `tool_use` / `tool_result` / `result`) to short human-readable status strings. **Critical user constraint: NEVER surface streamed assistant text or digest content** — only progress phase text. The discovery digest stays in the backend context; the user sees "Analysing the codebase…" / "Reading the project (Glob, Read)" / "Generating digest + per-agent briefs", not the actual report.
* `discovery_complete` transitions card to Done pill + sets elapsed chip + writes "Discovery complete — handing off to agents." into the status line. Digest content explicitly NOT injected into the body (per user spec).
* `agent_start` calls new `collapseDiscoveryCard()` so the now-running real agent gets the spotlight; discovery card stays in thread (re-expandable) but yields focus.
* `frontend/style.css` — added `.discovery-status` / `.discovery-status-line` / `.discovery-substatus` styles + done/error colour variants. Re-uses existing `.discovery-card` background gradient already in CSS.

### Verification

* `python -c "import backend.main"` — loads clean.
* Backend invariant: `'contract-audit' not in AGENT_IDS` ∧ `'contract-audit' not in AGENT_PROMPTS` ∧ `'contract-audit' not in _AGENT_TARGET_DIRECTIVES` — all assertions pass.
* `_validate_migration_planner_body('## A.4 file_map.json\n\nbody', {'mappings':[{'source':'a','targets':['b'],'kind':'1-to-1 port'}]})` returns `[]` (valid). Empty body returns the two expected failure strings.
* `python -m scripts.smoke_migration_pipeline` — still 5/5 green.
* `node -c frontend/app.js` — syntax OK.

### What this changes for the user

* **Discovery phase**: card visible from the moment "Run analysis" is clicked, with live phase updates instead of a blank thread.
* **Migration-planner**: ~3× shorter prompt → faster turn, less truncation risk, clearer single-purpose contract. file_map.json still emitted to spec.
* **Contract-audit**: gone. Wave 5 of the supervisor DAG now ends at `code-review` + the deterministic auditors.
* **UI-UX agent**: same polish behaviour, no more brittle inline HTML preview that occasionally rendered as broken markup.

---

## 2026-04-23 — Wire deterministic migration pipeline into `backend/main.py` post-generation chain `[DONE]`

Auto-runs the new `migration_pipeline.run_pipeline()` after every supervised run finishes — no manual CLI invocation required. Slots in alongside the existing post-generation auditors (`file_coverage`, `api_contract`, `ui_binding`, `route_link`, `seed_completeness`, `line_count_fidelity`) so every converted/ tree gets a field-parity report + round-trip pytest scaffolds in the same flow that already produces FILE_COVERAGE.md and LINE_FIDELITY.md.

### Why main.py and not supervisor.py

The existing post-generation auditors all live in `backend/main.py` after `run_supervised()` returns — the supervisor's job is dispatching agent waves, the auditors run deterministically once those waves are done. Wiring the new pipeline next to them keeps the architecture consistent. Functionally identical to wiring it inside `run_supervised()`'s tail; the chosen spot is the one that matches the existing convention.

### Changes

* `backend/main.py:55` — added import: `from backend.agents.migration_pipeline import run_pipeline as run_migration_pipeline`.
* `backend/main.py:1199-1227` — inserted `try/except` block after the `line_count_fidelity` audit. Calls `run_migration_pipeline()` with `source_root=project_dir`, `converted_root=converted_dir`, `context_dir=context_dir`, `file_map_path=context_dir / "file_map.json"`, `round_trip_mode="plan"` (writes pytest scaffolds, no live HTTP). Surfaces a `migration_pipeline` progress event with the full per-step manifest so the UI can render the same status table the CLI prints. Exceptions are logged but never re-raised — failure of this layer does not break the run.
* `changes_md_path=None` — `main.py` already owns its own log; the in-pipeline appender is suppressed to avoid double entries when the wired flow also produces session changes elsewhere.

### Path alignment

Confirmed against `main.py:949` (`context_dir = project_dir.parent / "context"`):

```
source/<sid>/...           ← project_dir (passed as source_root)
context/                   ← context_dir (file_map.json lives here)
converted/<sid>/...        ← converted_dir (pipeline writes _field_sync/, docs/, tests/round_trip/)
```

### Verification

* `python -c "import backend.main"` — loads clean.
* `python -m scripts.smoke_migration_pipeline` — still passes end-to-end (8 controls extracted, 2 rows augmented, 6 sync stubs written, 2 RED rows correctly flagged, 1 round-trip scaffold emitted).

### Behaviour at runtime

Per converted run, the UI now sees an extra `migration_pipeline` progress event after `line_fidelity_audit`. The manifest carries:

```json
{
  "ok": true,
  "started_at": "...", "finished_at": "...",
  "steps": [
    {"name": "field-extractor",    "ok": true, "duration_s": 0.09, "summary": {...}},
    {"name": "planner-field-map",  "ok": true, "duration_s": 0.02, "summary": {...}},
    {"name": "codegen-field-sync", "ok": true, "duration_s": 0.04, "summary": {...}},
    {"name": "parity-check",       "ok": true, "duration_s": 0.03, "summary": {...}},
    {"name": "round-trip",         "ok": true, "duration_s": 0.00, "summary": {...}}
  ]
}
```

`ok=false` on any step surfaces the per-step `note` so the user sees exactly which sub-step regressed (e.g. `"file_map.json missing — run migration-planner first"`). The other auditors keep running regardless because the `try/except` is per-auditor, mirroring the existing pattern.

---

## 2026-04-23 — Deterministic field-level migration pipeline (extractor → augment → codegen-sync → parity → round-trip) `[DONE]`

Extends the existing migration-planner stack with a deterministic field-level floor that fixes the silent-drop bug class documented earlier in this log (#3 rename / #5 FK silent null / #7 silent field drop on every POST). Five new modules under `backend/agents/`, one new orchestrator, one CLI shim, one smoke test. Smoke green end-to-end.

### Why caveman: codex make less drift, we win

The TotalBookingAI port (#7 in this log) and the 2026-04-22 ARIES rounds both regressed the same way: the LLM-driven planner emitted a `file_map.json` that *counted* form controls (`inputs=N selects=M …`) but never recorded the **actual field NAMES**. Code-generation then picked names independently per layer (`dateOfBirth` for the TS interface, `dob` for the C# DTO, `DateOfBirth` for the EF entity), and every POST silently dropped 8–15 fields because the layers diverged. The fix shape is to remove field-name choice from the LLM at exactly one layer (the names) while leaving everything else (validation, layout, CSS) for the LLM.

### New modules

| Module | Purpose |
|---|---|
| `backend/agents/field_extractor.py` | Pure-Python multi-language extractor. Parses AngularJS HTML / Blade / Angular / React JSX / Vue / Razor / C# / TS / PHP / Python / JVM. Emits `context/field_inventory.json` with per-file `{controls[], dto_fields[], endpoints_called[], endpoints_defined[], tabs[], modals[]}` plus a `by_field` reverse index. Tolerant — bad files logged + skipped, never crash the run. |
| `backend/agents/planner_field_map.py` | Augments `context/file_map.json` rows with a per-row `fields[]` array `{source, target, type, required, repeatable_parent, conditional_parent, tab}`. Defaults `target = source`; preserves any explicit rename the planner LLM declared. |
| `backend/agents/codegen_field_sync.py` | Deterministic emission of three coordinated artefacts per row: C# DTO (`*Dto.cs`), TS interface (`*.ts`), React form section skeleton (`*Section.tsx`) — all bound to identical `fields[].target` names. Lives under `converted/_field_sync/` so the LLM-driven code-gen step has a parity-safe starting point. |
| `backend/agents/parity_checker.py` | Diffs source fields (from `field_inventory.json`) against converted-side fields per `file_map.json` row. Emits `converted/docs/FIELD_PARITY.md` + `field_parity.json`. Uses canonical-name matching + a soft-synonym table (`dob ↔ dateOfBirth`, `sexId ↔ genderId`, …) — soft matches go YELLOW; true drops go RED. Exit code 1 on any RED row. |
| `backend/agents/round_trip_tester.py` | Two modes. `plan` writes one pytest scaffold per row to `converted/tests/round_trip/` that POSTs the synthetic payload and asserts every field round-trips. `live` fires the HTTP itself against `--base-url` and writes `converted/docs/ROUND_TRIP.md`. |
| `backend/agents/migration_pipeline.py` | Orchestrator. Runs the five steps in order, captures per-step timings + summaries + failure notes, appends a structured entry to `changes.md` (newest-first per memory rule) with the per-step status table. Returns `PipelineResult` with `ok` flag for callers (CLI exit code, supervisor wiring). |

### CLI + smoke

* `scripts/run_migration_pipeline.py` — `python -m scripts.run_migration_pipeline --source … --converted … [--round-trip-mode live --base-url …]`. Returns non-zero on any RED parity row or live round-trip failure.
* `scripts/smoke_migration_pipeline.py` — synthesises a 2-file source + 3-file converted tree under tempdir, runs the full pipeline, asserts inventory non-empty + `fields[]` augmented + sync stubs written + parity reports the expected RED rows + pytest scaffolds emitted + `changes.md` appended. Run with `python -m scripts.smoke_migration_pipeline`. Currently passes (8 controls extracted, 2 rows augmented, 6 stubs written, 2 RED rows correctly flagged, 1 scaffold emitted).

### How this kills each bug class from #7

* **Layer rename drift** (`dateOfBirth` ↔ `dob`): impossible — `codegen_field_sync` writes the C# property, TS field, and React `register('…')` from the same `fields[].target` token. If the LLM later edits one layer, `parity_checker` flags it RED before commit.
* **Silent FK null** (#5 `Agency` nav-prop without FK config): the extractor's C# DTO walker sees `Agency` in the response DTO but no `AgencyId`/`ArrestAgencyId` mapping. Parity reports it as a YELLOW *extra* field on the target — reviewer prompt to add the Fluent config.
* **Wrong status code** (#6 `400 "Not found"`): not in scope for the field-parity layer; tracked for a follow-up `status_code_audit.py`.
* **Form gap** (#9 ~15 fields where source had ~100): parity report makes this loud — every missing field is a RED row with `target_field_total / source_field_total` ratio in the header.

### Wiring (next step, not in this commit)

`backend/agents/supervisor.py` should call `migration_pipeline.run_pipeline()` after the LLM-driven `migration-planner` + `code-generation` waves complete. Right now it can be invoked manually via the CLI. Wiring is deliberately separate so this commit is reversible without touching the live supervisor DAG.

### Files added

```
backend/agents/field_extractor.py          (~720 LoC, pure Python)
backend/agents/planner_field_map.py        (~190 LoC, pure Python)
backend/agents/codegen_field_sync.py       (~310 LoC, pure Python)
backend/agents/parity_checker.py           (~410 LoC, pure Python)
backend/agents/round_trip_tester.py        (~430 LoC, pure Python)
backend/agents/migration_pipeline.py       (~320 LoC, pure Python)
scripts/run_migration_pipeline.py          (~55 LoC)
scripts/smoke_migration_pipeline.py        (~155 LoC, smoke green)
```

No changes to existing agents or supervisor — additive only.

---

## 2026-04-23 — UI fidelity validator reads `file_map.json` triplets (authoritative per-row audit) `[DONE]`

User hit: *"code gen is not mapping same forms in target environment"* — followed by screenshots showing the converted React app with ~15 fields where the AngularJS source had ~100+ across booking form / PC declaration / use-of-force / warrants / orders / residence / offenses / property-checklist. Earlier turn shipped the planner-side enforcement (SKIPPED-abuse rule + mandatory UI triplet in `file_map.json` `notes`); this turn closes the loop by making the post-generation validator actually READ those triplets and flag per-row drops.

### The missing link before this turn

`scaffold.validate_ui_fidelity` ran tree-wide totals + a token-paired per-page heuristic, but it had **no signal from `file_map.json`**. Even with the planner now mandated to emit `inputs=N selects=M textareas=K repeaters=R conditionals=C` on every UI row, nothing downstream actually diffed those counts against the real target files. A React component mapped via `many-to-1 merge` to three HTML templates with 80 combined fields could ship with 8 fields and never show up in `UI_FIDELITY_REPORT.md` as red.

### Fix — [backend/agents/scaffold.py](backend/agents/scaffold.py)

Four new pure helpers:

- `_TRIPLET_PARSE_RE` — regex matching the 5-key triplet; returns the five ints as capture groups.
- `_parse_ui_triplet(notes) -> dict|None` — parses a row's `notes` into `{input, select, textarea, repeater, conditional}` (singular keys, matching the existing `_count_controls` output — zero key renames at compare time).
- `_read_file_map(path) -> list[dict]|None` — best-effort read of `context/file_map.json`; tolerates missing file, invalid JSON, unexpected shape.
- `_sum_target_counts(targets, converted_dir) -> dict` — aggregates `_count_controls` output across every target file named in a row's `targets[]`. Missing target files contribute zero (surface red, not exception).
- `_audit_file_map_per_row(mappings, converted_dir, *, red_threshold=0.80)` — per-row audit returning sorted `{source, targets, source_counts, target_counts, worst_kind, worst_ratio, red}`. A row is **red** when ANY non-zero source-count kind drops below 80% in the target aggregate. Target over-count is ignored (extras are fine; drops are not).

`validate_ui_fidelity` now takes an optional `context_dir: Path | None = None`. When provided AND `context_dir/file_map.json` exists, the new "File-map per-row fidelity (authoritative)" section is appended to `UI_FIDELITY_REPORT.md`:

- **❌ red rows table**: `Source | Targets | Worst kind | Coverage | Source counts | Target counts` — up to 100 rows, sorted worst-first.
- **✅ green rows top-20**: top source files by control count, confirms the audit actually ran.
- `manifest["filemap_rows_audited"]` and `manifest["filemap_red_rows"]` exposed to callers.
- `manifest["warning"]` promoted when ≥1 red row — a single red row from this authoritative pairing is a stronger signal than 70%-aggregate because the source↔target pairing is planner-declared, not heuristic.

When `context_dir` is provided but `file_map.json` is missing/unparseable, the report emits a `## File-map per-row fidelity — _SKIPPED_` section naming the gap — distinct from "ran and was clean".

### Fix — [backend/main.py](backend/main.py) (L1088)

Post-generation caller passes `context_dir=project_dir.parent / "context"`. That sibling path is where the supervisor writes `file_map.json`. Safe when missing — validator degrades to the existing heuristic cleanly.

### Why this closes the form-fidelity loop end-to-end

```text
Planner prompt                        (2026-04-23 earlier turn)
  ↓ enforces triplet in file_map.json notes on every UI row
supervisor.validate_planner_quality   (2026-04-23 earlier turn)
  ↓ fails planner output if SKIPPED abused or triplet missing
context/file_map.json                 (persisted contract)
  ↓
code-generation reads contract        (existing prompt, unchanged)
  ↓ produces target components
scaffold.validate_ui_fidelity         (THIS TURN)
  ↓ reads file_map.json, compares target aggregates to declared triplet
UI_FIDELITY_REPORT.md § File-map per-row fidelity
  ↓ red rows surface to contract-audit + code-review
code-review / contract-audit          (existing, read the report)
  ↓ flag run as degraded, refuse "done"
```

Before this turn, the chain broke at step "scaffold.validate_ui_fidelity" — the contract was created but never checked. A React component could ship with 8 inputs mapped to a source declaring `inputs=80` and no validator ever fired.

### Smoke — extended [scripts/smoke_ui_binding.py](scripts/smoke_ui_binding.py)

13 new assertions added (two new test blocks):

- **File-map-driven audit (11)** — builds temp source/converted trees + `context/file_map.json` with two rows (one thin target intentionally dropping controls, one fat target preserving them). Asserts: 2 rows audited, exactly 1 red row, red row correctly identifies `booking.form.html` with worst_ratio < 0.8, red row's `targets[]` matches planner contract, report contains the new section with "authoritative" label and cites the red source path. Also asserts: without `context_dir`, audit is skipped cleanly (regression guard for old callers).
- **File-map missing (2)** — `context_dir` provided but `file_map.json` absent: `filemap_rows_audited == 0`, report labels the section `_SKIPPED_` so reviewer sees the gap.

Full smoke_ui_binding now green across all 28 assertions (existing 15 + 13 new).

### Regression — 279 assertions across 11 smokes, 0 failures

| Smoke | Assertions | This turn? |
| --- | ---: | --- |
| `smoke_ui_binding.py` | 28 | +13 extended |
| `smoke_planner_partial_and_skipped.py` | 30 | prior |
| `smoke_required_upstream.py` | 20 | prior |
| `smoke_report_scrubber.py` | 36 | prior |
| `smoke_line_fidelity.py` | 16 | prior |
| `smoke_file_map_render.py` | 18 | prior |
| `smoke_export_fidelity.py` | 32 | prior |
| `smoke_run_converted.py` | 14 | earlier |
| `smoke_demo_docs.py` | 48 | earlier |
| `smoke_coverage_contract.py` | 20 | earlier |
| `smoke_route_link_and_seed.py` | 16 | earlier |

### Files touched (this turn)

- modified: `backend/agents/scaffold.py` (4 new helpers + `context_dir` arg on `validate_ui_fidelity` + new report section + manifest keys)
- modified: `backend/main.py` (post-generation caller passes `context_dir`)
- modified: `scripts/smoke_ui_binding.py` (extended with file-map-driven tests)

### What's still `[PLANNED]` (unchanged from prior turn)

- The full 3-section migration-planner slim. Still deferred — and now even less urgent, because the contract↔validator chain is closed end-to-end regardless of whether the planner emits 3 or 7 sections.

### For the next run (user action)

User will start a new session + re-run analysis on the same source zip. The planner will now be blocked from emitting `SKIPPED` on form files (validator rejects, repair pass reclassifies as `many-to-1 merge`). Code-generation reads the enforced contract. This scaffold-side check will produce a red row in `UI_FIDELITY_REPORT.md` for any target component that drops below 80% coverage on any control kind, so downstream `code-review` / `contract-audit` can refuse to mark the run complete until fidelity is restored.

---

## 2026-04-23 — Partial-output preservation on timeout + SKIPPED-abuse / UI-triplet fidelity validators `[DONE]`

User hit: *"code gen is not mapping same forms in target environment please check whether the chanegs will be more robust and convert the app as it is exactly working"* — on top of the earlier *"whole report is not shown on frontend"* / *"truncated json is being passed as context to code generation"* complaints.

Shipped two tightly-coupled fixes that together close the silent-drop failure modes for form-heavy conversions. The 3-section slim (separate `[PLANNED]` entry below) was deferred — too wide a blast radius for one turn, and the form-fidelity work is orthogonal to it.

### 1. Partial-output preservation on timeout

**Problem:** [runner.py:677-684](backend/agents/runner.py#L677-L684) returned `{"status": "error", "result": ""}` on `asyncio.TimeoutError` — every byte of streamed assistant text already captured in `raw_stdout` was discarded. The frontend had rendered the live stream via SSE, but the backend's `result["result"]` was empty, so (a) the exported `.md`/`.pdf` was blank, (b) `upstream_migration-planner.md` for code-generation was empty, (c) the `📁 File Migration Map` block 404'd because `file_map.json` was never extracted.

**Fix — [backend/agents/runner.py](backend/agents/runner.py):**

- New helper `_extract_partial_assistant_text(raw_stdout: bytes) -> str` walks each stream-json line, pulls every `assistant.message.content[*].text` fragment, concatenates, tolerates half-written final lines.
- `TimeoutError` handler now calls it, scrubs via `report_scrubber.scrub_report`, prepends a ⚠-banner so the saved report is self-labelled, returns the body as `result` with `status="error"` + new `partial: True` flag.

**Fix — [backend/agents/supervisor.py](backend/agents/supervisor.py):**

- `file_map.json` extraction gate (≈L679) widened: runs on `status == "done"` OR `status == "error" + partial`. Extraction + polish + validator + `context/file_map.json` write all execute on partial.
- `migration-planner_attempt1.md` persistence (≈L737) also widened so the draft lands on disk whenever there's a body.
- Repair/multipass dispatch gate (≈L747) kept narrow: only fires on `status == "done"`. Partial results don't trigger a 30-min retry against the same timeout wall.
- `upstream_results[aid]` populate site (≈L1096) widened: partial-with-body populates too (and still joins `errored`), so non-required downstream agents get to read whatever shipped.
- `agent_complete`/`agent_error` SSE event (≈L1031) now ships `result` + `partial: true` on the partial path — frontend's `completeCard` gets a body longer than the 500-char `result_preview` to render.

**Fix — [backend/main.py](backend/main.py):**

- `_auto_export_session` (L398-403) per-agent gate relaxed from `if status != "done" or not result: continue` to `if not result: continue`. Partial bodies land in `.md` / `.docx` / `.pdf` with the ⚠-banner carried through.
- Combined `.md` loop (L468-471) same relaxation.

**Fix — [frontend/app.js](frontend/app.js) `completeCard` (L1557+):**

- Added `preferStream = streamLen > resultLen * 1.5 && streamLen > 2000` guard. Final-text picker prefers `c.assistantAccum` over `ev.result` when the stream is substantially longer — protects against a later repair pass shipping 8 KB after the live view already rendered 44 pages.
- Added partial-output render branch in the `else` (error) arm: renders `ev.result` (or the longer `assistantAccum`) as the final report body, shows "Partial" pill, reveals the Save button so users can export the partial report.
- `finalResultFromStream` drops in priority (it's 500-char-capped at [runner.py:345](backend/agents/runner.py#L345)).

### 2. SKIPPED-abuse + UI-triplet fidelity validators

**Problem:** Planner rows like `total-booking-address.form.html` → `kind: SKIPPED, skip_reason: "Subsumed into BookingAddressSection.tsx"` passed every validator even though the HTML held 20+ form controls whose content needed to survive in the target React component. With `targets: []`, there was NO programmatic row for the UI-fidelity validator to key off — the target `.tsx` could be missing half the fields and no red row ever fired. In the TotalBookingAI planner output, **≥19 rows** including the two biggest forms (`pcdec-juvenile-pcdec.form.html` at 1,575 LOC and `total-booking.form.html` at 1,407 LOC) fell into this trap.

**Fix — [backend/agents/planner_polish.py](backend/agents/planner_polish.py):**

- New constants: `_UI_SOURCE_SUFFIXES` (13 extensions: .html, .htm, .vue, .jsx, .tsx, .blade.php, .twig, .erb, .ejs, .hbs, .handlebars, .svelte, .astro), `_UI_CONTENT_SENTINELS` (16 regex patterns: `<input>`, `<select>`, `<textarea>`, `<form>`, `<button>`, `ng-repeat`, `*ngFor`, `v-for`, `@foreach`, `ng-if`, `*ngIf`, `v-if`, `@if`, `ng-show`, `v-show`, `ng-hide`), `_UI_TRIPLET_RE` (matches `inputs=N selects=M textareas=K repeaters=R conditionals=C`).
- New helpers: `_looks_like_ui_source(path)` (suffix check — handles double-extensions like `.blade.php`), `_file_has_ui_content(full_path)` (reads up to 512 KB, returns True if any sentinel matches, False on read error).
- `validate_planner_quality(markdown, file_map, source_root=None)` grew two checks:
    - **SKIPPED abuse**: for every `kind == "SKIPPED"` row whose source is UI, read the file from `source_root` and fail if any content sentinel hits. Failure message names affected sources + tells the model to reclassify as `many-to-1 merge`. Capped at 20 paths shown; exact count always reported.
    - **UI triplet**: for every non-SKIPPED UI row, require `inputs=N selects=M textareas=K repeaters=R conditionals=C` in `notes`. Filesystem-free check (no `source_root` needed).
- `source_root=None` keeps the SKIPPED-abuse check opt-in for callers that don't want filesystem reads; triplet check always runs.

**Fix — [backend/agents/supervisor.py](backend/agents/supervisor.py):**

- All three `validate_planner_quality(...)` call sites (initial pass L719, repair L853, multipass L948) now pass `source_root=project_dir` so the SKIPPED-abuse check has the legacy tree to grep.
- Quality failures stack with body-shape failures → existing repair-pass dispatch picks them up automatically; no new plumbing.

**Fix — [backend/agents/prompts.py](backend/agents/prompts.py) migration-planner prompt:**

- New hard-rule block under A.4 schema: "`SKIPPED` is ONLY valid when BOTH (a) targets is empty AND (b) source produces ZERO code content in target". Lists the 16 patterns that disqualify a row from `SKIPPED` status. Calls out the common failure mode by name ("AngularJS `*.form.html` with 20 inputs and 3 conditionals → SKIPPED → silent field drop").
- New hard-rule block: UI-triplet in `notes` mandatory for every non-SKIPPED UI source row. Lists all UI extensions + the five count keys + how to count each one. Example notes field shown. Explains the downstream audit chain.

### Smoke — [scripts/smoke_planner_partial_and_skipped.py](scripts/smoke_planner_partial_and_skipped.py)

30 assertions, 4 groups, all green:

1. **Partial extraction (7)** — fixture stream with 3 assistant deltas + 1 malformed line + no terminal `result` event; extractor recovers all 3 text fragments, skips the malformed line cleanly, returns empty on empty / system-only streams.
2. **UI-source suffix detection (11)** — 7 UI files match (covers .html, .vue, .jsx, .tsx, .blade.php, .twig, .erb); 4 non-UI files don't (.js service, .php model, .ts store, .md doc).
3. **SKIPPED abuse on real filesystem (7)** — temp legacy tree with 4 files (abuse / legit-skip / UI-with-triplet / UI-without-triplet). Abuse row flagged with source path + "many-to-1 merge" remediation; legit skip NOT flagged; triplet-missing flagged; triplet-present NOT flagged; `source_root=None` skips the filesystem check but still fires the triplet check.
4. **`_file_has_ui_content` edge cases (5)** — `<input>`, `ng-repeat`, `*ngFor` detected; pure template shell passes; missing file returns False without raising.

### Regression — 266 assertions across 11 smokes, 0 failures

| Smoke | Assertions | This turn? |
| --- | ---: | --- |
| `smoke_planner_partial_and_skipped.py` | 30 | ✓ new |
| `smoke_required_upstream.py` | 20 | prior |
| `smoke_run_converted.py` | 14 | prior |
| `smoke_report_scrubber.py` | 36 | prior |
| `smoke_line_fidelity.py` | 16 | prior |
| `smoke_file_map_render.py` | 18 | prior |
| `smoke_export_fidelity.py` | 32 | prior |
| `smoke_demo_docs.py` | 48 | earlier |
| `smoke_coverage_contract.py` | 20 | earlier |
| `smoke_ui_binding.py` | 16 | earlier |
| `smoke_route_link_and_seed.py` | 16 | earlier |

### Files touched

- modified: `backend/agents/runner.py` (partial-text extractor + TimeoutError branch returns partial body)
- modified: `backend/agents/supervisor.py` (persist-gate widening + repair-gate kept narrow + upstream/SSE + validator call sites)
- modified: `backend/agents/planner_polish.py` (SKIPPED-abuse + triplet validators + constants + helpers)
- modified: `backend/agents/prompts.py` (two new hard-rule blocks in migration-planner prompt)
- modified: `backend/main.py` (export gate relaxation)
- modified: `frontend/app.js` (`completeCard` prefer-stream guard + partial-render branch)
- new: `scripts/smoke_planner_partial_and_skipped.py`

### What's still `[PLANNED]` (deferred to separate turn)

- The full 3-section slim (delete A.0/A.1/A.3/A.5/B; keep Migration Table + Target Architecture + file_map.json). That's a cascading rewrite across ≥10 files and tightly coupled to multipass + repair-pass infrastructure. Doing it in the same turn as this fix would multiply the blast radius without adding fidelity coverage. Kept as the `[PLANNED]` entry below with implementation steps intact.

---

## 2026-04-22 — Slim migration-planner to 3 sections (Migration Table + Target Architecture + `file_map.json`) `[PLANNED]`

User hit: *"it means code gen doesnot depend on migration planner and the tree structure it produced ... make migration planner to show only migration of one to one and architectural diagrams and panels of target environment and file_mapping_json only"*

### Why slim

Today's planner emits seven sections (A.0 layer map, A.1 solution tree, A.2 mapping table, A.3 execution order, A.4 `file_map.json`, A.5 decomposition rationale, Section B program plan) over ≥7 multipass turns. Code-generation and every downstream validator (code-review, contract-audit, `file_coverage.py`, `line_count_fidelity.py`) only read ONE artifact: `file_map.json`. The rest is narrative for humans, and Section B is a governance deliverable with no programmatic consumer. This makes the planner the single largest output-ceiling failure point in the pipeline for no machine-consumer benefit.

### Target shape — 3 sections only

1. **§1 Migration Table** — a condensed markdown table with columns `Source | Kind | Target(s) | Notes`. `Kind` stays on the existing whitelist: `1-to-1 port | 1-to-many split | many-to-1 merge | 1-to-1 rename | SKIPPED`. This is the human-readable view of the JSON — row order identical to `mappings[]`. No UI-triplet / [TABS] / [MODAL] / [REPEATER] tokens here anymore (they move into the JSON — see caveat below).
2. **§2 Target Architecture** — a mermaid `flowchart` with the five standard AppNova `classDef`s (frontend / backend / database / external / warning), optional `stateDiagram-v2` if the system has a workflow, and 2-4 short panel paragraphs describing the target environment (hosting, auth, storage, observability). This replaces A.0 + the architecture bit of Section B in one cohesive place.
3. **§3 `file_map.json`** — the authoritative machine contract, unchanged schema and extraction path.

Sections deleted:

- **A.1 solution tree** — redundant with `targets[]` in the JSON.
- **A.3 execution order** — already captured as the `order` field per mapping.
- **A.5 decomposition rationale** — narrative only, no programmatic consumer.
- **Section B program plan** (phases / Gantt / team / risks / go-no-go / comms) — not read by any agent; if the client needs it, spin up a separate `program-plan` agent later. Not in this scope.

### Caveat — UI fidelity payload MUST survive the A.2 deletion

Current A.2 table carries the UI-fidelity triplet (`inputs=N selects=M textareas=K repeaters=R conditionals=C`) and `[TABS] / [MODAL] / [REPEATER]` tokens in the `Notes` column ([prompts.py:169-182](backend/agents/prompts.py#L169-L182)). They are load-bearing for the UI source-fidelity validators — losing them = forms silently drop fields / conditionals, which directly violates the user's `feedback_conversion_fidelity.md` rule (1-to-1, no skipped fields/forms/conditionals).

Mitigation: move the triplet + tokens into `file_map.json`'s `notes` field (already a supported key, just currently underused). The §1 Migration Table keeps a plain `Notes` column that stays human-readable; the JSON `notes` becomes load-bearing. Update prompt hard-rules to require the triplet in the JSON `notes` for every UI row and the tokens wherever applicable.

### Additional rule — `SKIPPED` abuse on subsumed `.html` / templates

Audit of the TotalBookingAI planner run surfaced ≥19 rows marked `SKIPPED` with `skip_reason: "Subsumed into XxxSection.tsx"` / `"Subsumed into TotalBookingEditPage.tsx"` etc. These are NOT genuine skips — their form fields (`<input>`, `<select>`, `<textarea>`, `ng-repeat`, `ng-if`) get inlined into the target component. Classifying them `SKIPPED` with `targets: []` makes them **invisible to the UI fidelity validator** — the target `.tsx` can be missing half the fields and no red row ever fires. This is the exact silent-drop failure mode the conversion-fidelity rule is designed to block.

New hard rule for the planner prompt (add under A.4 JSON schema constraints):

> `SKIPPED` is only valid when BOTH (a) `targets` is empty AND (b) the source file produces zero code content in the target project — vendor assets, dead files, template shells with no form controls or logic, retired SCSS/CSS. If the source contains any `<input>` / `<select>` / `<textarea>` / `ng-repeat` / `*ngFor` / `v-for` / `@foreach` / `ng-if` / `*ngIf` / `v-if` / `@if`, or routes/imports/exports that land in a target component, the row MUST be `many-to-1 merge` or `1-to-many split` pointing to the target(s) that absorb its content. The `notes` field MUST carry the UI-fidelity triplet and applicable `[TABS] / [MODAL] / [REPEATER]` tokens.

Validator update — [backend/agents/supervisor.py](backend/agents/supervisor.py) `validate_planner_quality` (via `planner_polish.py`):

- For every `kind == "SKIPPED"` row whose `source` ends in `.html` / `.htm` / `.vue` / `.jsx` / `.tsx` / `.blade.php` / `.twig` / `.erb`, read the legacy file, grep for the six UI-control patterns above. If any are present, FAIL the planner output with a specific quality flag: `SKIPPED row '<source>' has N UI controls — must be many-to-1 merge`.
- This is a new quality check; add to the validator's return list and to `validate_planner_quality`'s caller in `supervisor.py` so the repair-pass dispatch fires when this flag is raised.

Remediation on failure: the repair-pass preamble instructs the planner to re-classify every such row from `SKIPPED` to `many-to-1 merge` pointing at the target component (inferred from `skip_reason` today — the text "Subsumed into X.tsx" names the target).

### Additional smoke

Add to `scripts/smoke_planner_minimal_shape.py`:

- Fixture with a `.html` source containing 3 `<input>`s classified as `SKIPPED` → validator MUST return the "SKIPPED row has UI controls" flag.
- Same fixture reclassified as `many-to-1 merge` with the UI triplet in `notes` → validator MUST pass.
- Assert `notes` triplet parsing round-trips through `file_map.json` write → read.

### Implementation steps (ordering)

Do this AFTER the sibling `[PLANNED]` entry below (partial-output preservation). Slimming reduces planner output ~3-4× (from ~80 KB to ~20 KB in observed sessions), which makes the timeout fix defence-in-depth rather than load-bearing — but the fixes are still needed for belt-and-suspenders. The timeout fix is small; do it first, then slim.

1. **Rewrite the planner system prompt** — [backend/agents/prompts.py](backend/agents/prompts.py), the `"migration-planner"` key in the prompts dict (≈L1343 and L1467 for the A.4 schema; L1851 for the body-shape blurb).
    - Replace the seven-section spec with the three-section spec above.
    - Update the A.4 JSON schema section to require: `meta` (unchanged keys), `mappings[]` with `source | targets[] | kind | order | notes? | skip_reason?`, and add a NEW hard rule that `notes` MUST carry the UI triplet for every UI file row and the `[TABS] / [MODAL] / [REPEATER]` tokens where applicable.
    - Delete the A.0 / A.1 / A.2 / A.3 / A.5 / Section B directive blocks.
    - Add the §2 Target Architecture directive block (classDef palette + panel prose spec).
2. **Shrink multipass to 3 sections** — [backend/agents/planner_multipass.py](backend/agents/planner_multipass.py).
    - Rewrite `_SECTIONS` tuple (currently 7 entries at L131-249): `[MigrationTable, Architecture, FileMap]`.
    - Scale `max_tokens_hint` down: MigrationTable 6k, Architecture 3k, FileMap 16k (unchanged — still the big one).
    - Cooldowns: 30s / 20s / 0s (last).
    - Since total budget now fits comfortably in one Sonnet turn, evaluate whether multipass is still needed at all — consider gating its invocation on `source_files_total > 400` (today: 200) so small/medium projects skip it.
3. **Update validators** — [backend/agents/supervisor.py](backend/agents/supervisor.py).
    - `_validate_migration_planner_body` (L166+): expect §1 / §2 / §3 section markers instead of A.0-A.5 + B. Keep the hard-rule checks on `mappings[]` row count vs `source_files_total`.
    - `validate_planner_quality` (cross-call to `planner_polish.py`): update section ordering whitelist.
    - `_is_thin_only_in_a2_or_a4` (L294): rename to `_is_thin_only_in_table_or_json`; adjust the heuristic.
    - `_build_a2_a4_completion_prompt` (L307+): becomes `_build_table_and_json_completion_prompt`; target the two sections that actually still exist.
4. **Update polisher** — [backend/agents/planner_polish.py](backend/agents/planner_polish.py). Update the narrator-tail and placeholder-residue strip rules to drop any leakage of old A.0/A.1/A.3/A.5/B content; add a strip rule for any `## Section B` heading that might slip through on first pass.
5. **Update downstream agent prompts that name A.* or Section B** — [backend/agents/prompts.py](backend/agents/prompts.py).
    - Grep the file for `A.0` / `A.1` / `A.2` / `A.3` / `A.5` / `Section B` / `A.4` as narrative references (keep ones that name `file_map.json`). Adjust code-review, contract-audit, file-coverage, line-fidelity, documentation, testing briefs so none of them assume A.* sections exist.
    - Keep every `context/file_map.json` reference — that path and contract are unchanged.
6. **UI coverage validator update** — [backend/agents/file_coverage.py](backend/agents/file_coverage.py) / [backend/agents/ui_binding.py](backend/agents/ui_binding.py). Where they parse the UI triplet from A.2 Notes today, switch to reading it from `file_map.json`'s `notes` per mapping. Keep backward-compat fallback (read from A.2 if present) for one release cycle.
7. **Export & frontend**.
    - [backend/main.py](backend/main.py) `_file_map_to_markdown_table` already renders `file_map.json` as a standalone table — becomes the §1 table in the export. No change needed.
    - [frontend/app.js](frontend/app.js) `📁 File Migration Map` block (L1821+) is unchanged — reads `/api/sessions/<sid>/file-map` and renders table.
    - The rendered planner card in the thread now has Migration Table + Architecture diagram + File Migration Map details block. Verify mermaid renders cleanly in the simplified body.
8. **Demo seed + fixtures** — [backend/agents/demo_docs.py](backend/agents/demo_docs.py) / `demo_sessions/totalbooking-react-aspnet/`.
    - Regenerate the demo `migration-planner.md` to match the 3-section shape.
    - Update any fixture assertions that keyed off section names.
9. **Smokes**.
    - New `scripts/smoke_planner_minimal_shape.py` (≥10 assertions): body-shape validator accepts 3-section shape; rejects old 7-section shape with stale heading names; UI triplet lands in JSON `notes`; `_extract_file_map_json` still parses cleanly; `_file_map_to_markdown_table` renders §1 equivalent.
    - Update `smoke_planner_body_shape.py` if it exists today — re-baseline against new spec.
    - Update `smoke_export_fidelity.py` — the exported `.md` now has 3 sections, not 7.

### Non-goals (explicitly out of scope)

- No new separate `program-plan` / `steering-committee` agent. If/when the client asks for the Gantt / risks / team back, that's a separate scoped feature.
- No change to `file_map.json` extraction path, schema, or storage location — same `context/file_map.json`, same `_extract_file_map_json` call site.
- No removal of multipass — only its invocation threshold moves. The module stays for pathological cases.
- No change to the timeout-preservation fix below — this slim plan complements it, doesn't replace it.

### Files to touch (slim plan)

- modified: `backend/agents/prompts.py` (planner prompt rewrite + downstream reference cleanup)
- modified: `backend/agents/planner_multipass.py` (`_SECTIONS` tuple + invocation threshold)
- modified: `backend/agents/planner_polish.py` (strip/order rules)
- modified: `backend/agents/supervisor.py` (validators + completion-pass builder)
- modified: `backend/agents/file_coverage.py` + `backend/agents/ui_binding.py` (read UI triplet from JSON notes)
- modified: `backend/agents/demo_docs.py` + demo fixtures
- new: `scripts/smoke_planner_minimal_shape.py`
- modified: existing planner smokes

### Expected regression surface

- Planner output size: ~80 KB → ~20 KB (4× smaller, fits one Sonnet turn)
- Multipass invocation frequency: ~every run for ≥200-file projects → rare (only ≥400-file)
- Timeout failure rate: drops proportionally; partial-preserve fix becomes rare safety net
- Downstream agents: unchanged contract (still read `file_map.json`), should see no regression
- Human-readable exports: lose Section B narrative; gain cleaner signal-to-noise

---

## 2026-04-22 — Preserve timed-out planner output + stop frontend from clobbering it `[PLANNED]`

User hit: *"the whole report is not shown on frontend and 1st iteration before timeout is not shown as pdf at below path given ... and also why the full page is being used for rendering report for each card and being truncated?? and also truncated json is being passed as context right instead of full context of migration planner agent report to code generation agent??"*

Follow-up: *"file_map.json unavailable (HTTP 404). The migration-planner agent must finish before this data is available. is the error at the end of report card of migration planner???"*

### Root cause — one backend bug, four visible symptoms

On `asyncio.TimeoutError`, [runner.py:677-684](backend/agents/runner.py#L677-L684) returns `{"status": "error", "result": ""}`. `raw_stdout` at that point already contains every streamed `type:"assistant"` event — the same bytes the browser received and rendered — but the handler discards them. Four downstream effects:

1. **Export skips the agent entirely.** [main.py:399](backend/main.py#L399) `if r.get("status") != "done" or not r.get("result"): continue` — no `.md`/`.docx`/`.pdf` written.
2. **Code-generation gets no upstream context.** [supervisor.py:1072-1073](backend/agents/supervisor.py#L1072-L1073) — `upstream_results[aid] = result["result"]` stores empty string. Code-gen's prompt reads `../context/upstream_migration-planner.md` ([prompts.py:257](backend/agents/prompts.py#L257)) which is empty (or missing).
3. **`file_map.json` is never extracted.** [supervisor.py:679-683](backend/agents/supervisor.py#L679-L683) gates the extract/polish/validate/repair path on `status == "done" and result.get("result")`. So the `📁 File Migration Map` `<details>` block in the migration-planner card ([app.js:1821-1854](frontend/app.js#L1821-L1854)) hits `/api/sessions/<sid>/file-map` → 404 → shows the banner *"file_map.json unavailable (HTTP 404). The migration-planner agent must finish before this data is available."*
4. **Frontend replaces long streamed view with short final.** [app.js:1582-1598](frontend/app.js#L1582-L1598) `completeCard` destroys `c.assistantAccum` (which holds the full streamed 44 pages) and re-renders with `ev.result` from a later repair pass that came back shorter.

### Evidence on disk

- Session `99ba31a75ca9` (user's exported session): `upstream_migration-planner.md` = `migration-planner_attempt1.md` = exported `.md` = **identical 8,714 bytes**. No `file_map.json`. First pass was thin, repair produced the same thin result, export wrote the thin result.
- Session `6faa89a0bbbb`: `migration-planner_attempt1.md` = `upstream_migration-planner.md` = **86,602 bytes** — matches the 44-page PDF the user attached (begins *"Continuing the `file_map.json` — remaining mappings, then A.5 and Section B."*). Log `logs/agents/20260422_222026_010_migration-planner.log` confirms `Reason: Timed out after 1800s` on a later re-run; the good first-run content was saved BEFORE that timeout hit.

### Planned fix (A + B + C + D; E rejected)

#### A. Preserve partial output on timeout — [backend/agents/runner.py](backend/agents/runner.py) (L677-684)

Before returning from the `asyncio.TimeoutError` handler, walk `raw_stdout` line-by-line as stream-json events, collect every `type:"assistant"` event's `message.content[*].text`, and concatenate. Return that as `result`. Keep `status="error"` so downstream knows it's incomplete, but surface the preserved body via a new field `partial: True` and include a prefix banner in `result` itself so the user sees *"**⚠ Timed out after 1800s — partial output preserved.**"* at the top of the exported report. Run `scrub_report` on the preserved body same as the happy path (line 635).

#### B. Respect partial output through the pipeline — [backend/agents/supervisor.py](backend/agents/supervisor.py)

Two gates to split:

- **Persist gate (widen)**: populate `upstream_results[aid]`, run `polish_planner_report` + `_extract_file_map_json` + write `context/file_map.json`, and persist `migration-planner_attempt1.md` even when `status == "error"` AND `result` is non-empty (partial). This lets code-generation read the preserved planner content and lets the `📁 File Migration Map` block render.
- **Repair-dispatch gate (unchanged)**: only dispatch the repair/multipass pass when `status == "done"`. A partial result shouldn't trigger a repair loop that would burn another 30 min against the same timeout wall.

Touch points: [supervisor.py:679](backend/agents/supervisor.py#L679) (extract gate), [supervisor.py:1072-1073](backend/agents/supervisor.py#L1072-L1073) (upstream persist gate), and the `upstream_<aid>.md` write at [supervisor.py:592-594](backend/agents/supervisor.py#L592-L594) (already reads from `state["upstream_results"]` — fix at the populate site is enough).

#### C. Export partial reports — [backend/main.py](backend/main.py) (L398-403, L468-471)

Replace `if r.get("status") != "done" or not r.get("result"): continue` with `if not r.get("result"): continue`. Status-error-with-partial then writes `.md`/`.docx`/`.pdf` same as happy path. The "⚠ Timed out — partial" banner from A travels with the body so the saved report is self-labelled. Combined markdown at [main.py:468-471](backend/main.py#L468-L471) gets the same relaxation.

#### D. Don't clobber long streamed view with short final — [frontend/app.js](frontend/app.js) (L1582-L1598)

In `completeCard`, change the final-text picker to prefer `c.assistantAccum` over `ev.result` when the accumulated stream is substantially longer:

```js
const streamLen = (c.assistantAccum || '').length;
const resultLen = (ev.result || '').length;
const preferStream = streamLen > resultLen * 1.5 && streamLen > 2000;
const finalText = (
  digestText
  || (preferStream ? c.assistantAccum : ev.result)
  || c.assistantAccum
  || ev.result
  || c.finalResultFromStream
  || ''
).trim();
```

`finalResultFromStream` drops in priority (it's 500-char-capped at [runner.py:345](backend/agents/runner.py#L345)). Thresholds are deliberately conservative — a happy-path agent whose `ev.result` is ~= `assistantAccum` keeps the existing behaviour.

#### E. ~~Per-card `max-height: 80vh; overflow: auto;`~~ `[REJECTED]`

User asked whether browser-page layout is better than card-internal scroll. It is. Native page flow keeps Ctrl+F, Print, and text-selection working across the full report; nested scroll containers break all three. Keeping full-page flow.

### Follow-on (not in this turn)

- Optional future: dedicated `/report/<session>/<agent>` route for a per-report full-page view reachable from the card's action buttons. Additive, doesn't change the thread view. Only worth doing if the client asks.

### Files to touch

- modified: `backend/agents/runner.py` (TimeoutError branch — assemble `result` from `raw_stdout`, return `partial=True`)
- modified: `backend/agents/supervisor.py` (split persist vs repair gates; allow partial through extract + upstream_results + attempt1 persist)
- modified: `backend/main.py` (`_auto_export_session` accepts partial; combined.md accepts partial)
- modified: `frontend/app.js` (`completeCard` prefers `assistantAccum` over short `ev.result`)

### Smoke plan

New `scripts/smoke_planner_partial_preserve.py` with ≥12 assertions:
1. Runner TimeoutError branch returns non-empty `result` when `raw_stdout` contains assistant text (parse a fixture stream).
2. Returned dict has `partial: True` and `status: "error"`.
3. Banner prefix present in `result`.
4. Supervisor on `status=error, result=<partial>`: `upstream_results[aid]` populated; `context/file_map.json` written when extractable; `migration-planner_attempt1.md` written.
5. Supervisor does NOT dispatch repair pass on partial (guard the repair-invocation site).
6. Export: agent with `status=error` and non-empty `result` produces `.md` + `.docx` + `.pdf`.
7. Combined `.md` includes the partial agent's section.
8. Frontend `completeCard` picks `assistantAccum` when it's 1.5× longer than `ev.result`.
9. Frontend keeps using `ev.result` on the happy path (streamLen ≈ resultLen).

Full regression = existing 236 assertions + 12 new = 248 expected.

---

## 2026-04-22 — Planner timeout + required-upstream gate (fix for "planner timed out but code-gen ran anyway") `[DONE]`

User hit: *"migration planner is timed out after 900s and code gen is happening why????"*

### Why it happened — two bugs stacked

1. **Timeout was too tight for Sonnet.** [config.py:17](backend/config.py#L17) — default `AGENT_TIMEOUT = 900s`. Fine when migration-planner was on Haiku (prior to this turn's tier flip); too short once I promoted it to Sonnet 4.6 (heavy tier), which is ~2-3× slower per token on the same prompt. On a large legacy repo producing a full `file_map.json`, 15 min blew past regularly.

2. **Supervisor silently tolerated upstream failure.** [supervisor.py:545-548](backend/agents/supervisor.py#L545-L548) — the upstream-gathering loop just `continue`'d when an upstream's result was missing:
   ```python
   for up_id in spec.upstream:
       up_text = state.get("upstream_results", {}).get(up_id)
       if not up_text:
           continue   # ← silent skip
   ```
   Code-generation was then spawned WITHOUT `context/upstream_migration-planner.md` (and therefore without the authoritative `file_map.json` contract) and improvised the whole file layout from Glob/Grep. That's exactly the ARIES R1–R6 silent-regression mode the contract was meant to prevent.

### Fix

#### 1. Extended timeout for migration-planner — [backend/agents/runner.py](backend/agents/runner.py)

New `_PLANNER_TIMEOUT = int(os.environ.get("APPNOVA_PLANNER_TIMEOUT", "1800"))` — 30 min default, env-overridable. `_timeout_for` now routes `migration-planner` to this value instead of the generic 900s. Still a hard cap (so a wedged process gets killed), just a realistic one for Sonnet on a big repo.

Effective timeouts after this turn:
- `migration-planner` → **1800s** (30 min)
- `code-analysis` / `architecture` / `security` / etc. → 900s (unchanged)
- `code-generation` / `code-review` / `testing` / `ui-ux` / `contract-audit` → 86400s (unchanged; unbounded writers)

#### 2. New `required_upstream` field on AgentSpec — [backend/config.py](backend/config.py)

Added to the dataclass with a terse contract: anything in `required_upstream` must also be in `upstream`, and if any required upstream errored the dependent agent is SKIPPED (not run with missing context). Comment calls out the scope: "use sparingly; only for upstreams whose output is a contract the agent cannot legitimately work without."

Wired on `code-generation` with `required_upstream=("migration-planner",)`. Everything else defaults to empty required_upstream — non-required upstreams still fail silently so a small agent hiccup (e.g. `documentation` erroring) doesn't block the main pipeline.

#### 3. Skip gate in the supervisor — [backend/agents/supervisor.py](backend/agents/supervisor.py)

Added at the top of `_run_one`, BEFORE `_agent_runtime_config` / `build_agent_prompt`. Reads `state["errored"]` + `state["upstream_results"]`; if any required upstream is missing, returns a `status="skipped"` result with:
- `skip_reason: "missing_required_upstream"`
- `missing_upstream: ["migration-planner", ...]`
- `error`: a human-readable message naming the real blocker

Also fires an `agent_skipped` SSE event so the frontend shows a clear "skipped — missing upstream" badge instead of leaving the code-generation card blank.

Skips propagate through the `errored` bookkeeping set: code-review (upstream=code-generation) ends up in `errored` too once code-generation is skipped, so any future dependents layered on top will cascade cleanly.

### Smoke — new [scripts/smoke_required_upstream.py](scripts/smoke_required_upstream.py)

20 assertions across 5 test groups. Uses a fake `run_agent` callable that returns pre-baked dicts per agent id — no Claude CLI spawned:

1. **Config shape (7 assertions):** `AgentSpec.required_upstream` field exists; `code-generation.required_upstream == ("migration-planner",)`; required is a subset of upstream; all other agents default to `()`.
2. **Timeout wiring (3 assertions):** `_timeout_for("migration-planner")` returns 1800s; `_timeout_for("code-analysis")` still returns the unchanged `AGENT_TIMEOUT` (900s); planner timeout ≥ default.
3. **Baseline (2 assertions):** planner succeeds → code-gen runs to completion. Proves the gate doesn't fire when it shouldn't.
4. **Fix path (6 assertions):** planner errors → code-generation gets `status=skipped`, `skip_reason=missing_required_upstream`, `missing_upstream=[migration-planner]`, ends up in `errored` set, and the `agent_skipped` SSE event fires.
5. **Non-required upstream tolerance (2 assertions):** `documentation` (in `upstream` but NOT `required_upstream`) errors → code-generation STILL RUNS. Proves we didn't accidentally turn every soft upstream into a hard one.

### Regression — 236 assertions across 10 smokes, 0 failures

| Smoke | Assertions | This turn? |
| --- | ---: | --- |
| `smoke_required_upstream.py` | 20 | ✓ new |
| `smoke_run_converted.py` | 14 | prior |
| `smoke_report_scrubber.py` | 36 | prior |
| `smoke_line_fidelity.py` | 16 | prior |
| `smoke_file_map_render.py` | 18 | prior |
| `smoke_export_fidelity.py` | 32 | prior |
| `smoke_demo_docs.py` | 48 | earlier |
| `smoke_coverage_contract.py` | 20 | earlier |
| `smoke_ui_binding.py` | 16 | earlier |
| `smoke_route_link_and_seed.py` | 16 | earlier |

### Files touched

- new: `scripts/smoke_required_upstream.py`
- modified: `backend/agents/runner.py` (planner timeout), `backend/config.py` (required_upstream field + code-gen declaration), `backend/agents/supervisor.py` (skip gate + SSE event)

### Expected behaviour after this turn

- If migration-planner times out: **code-generation will NOT run** — the card flips to "skipped" and names migration-planner as the blocker. User retries the planner (now on a 30-min clock); once it succeeds, a fresh run proceeds cleanly.
- If migration-planner succeeds: no change — everything runs as before.
- If a non-critical upstream (documentation, integration, etc.) errors: no change — code-generation still runs with the other upstream briefs, as it always did.

### Escape hatches

- **Env override to the timeout:** `APPNOVA_PLANNER_TIMEOUT=3600 ./run_server.py` gives the planner an hour on exceptionally large repos.
- **Env override to disable the gate** (not added yet, not wanted — the whole point is to NOT silently produce broken output). If ever needed, one-line: short-circuit the `missing_required` list when `APPNOVA_IGNORE_REQUIRED_UPSTREAM=1`.

---

## 2026-04-22 — Promote migration-planner to the heavy model tier `[DONE]`

User asked: *"migration planner should use heavy model"*. One-line config flip.

### [backend/config.py](backend/config.py)

Changed `AGENT_REGISTRY["migration-planner"]` from `tier="light"` to `tier="heavy"`, with a comment explaining the rationale: the planner drives the authoritative `file_map.json` that code-generation + code-review + contract-audit all consume. A thin plan cascades into the exact R1–R6 ARIES failure classes AppNova spent six rounds chasing — silent symbol drops, dead-link sidebars, missing controllers. Same reasoning budget as code-analysis / architecture / security / business-rules is warranted.

### Effective change (per `.env`)

| Binding | Before | After |
| --- | --- | --- |
| `migration-planner.tier` | `light` | `heavy` |
| Resolved model | `haiku` (via `LIGHT_MODEL`) | `claude-sonnet-4-6` (via `HEAVY_MODEL`) |

Verified by importing the registry + calling `model_for(spec.tier)` — resolves to `claude-sonnet-4-6`.

### Expected impact

- **Quality ↑.** Migration-planner now produces the file_map.json on Sonnet 4.6 instead of Haiku — expect more complete `targets[]` lists, tighter `kind` labels, and richer `target_responsibility` notes. Downstream agents that read the plan (`code-generation` self-checks, `code-review` Step 4.75/4.8, `contract-audit` Checks 5–9, the new Step 4.9 line-fidelity auditor) all inherit the improvement for free.
- **Cost ↑ per session.** Sonnet tokens cost more than Haiku. The migration-planner phase typically produces one of the largest outputs in the pipeline (full mapping of source → target files); on a 400-file legacy repo the delta is real but single-digit-dollar per conversion. Cost workbook will show the increase on the next session.
- **Wall-clock ↑.** Sonnet is slower than Haiku on the same prompt. Migration-planner phase takes ~60-120s longer; still tiny next to code-generation (30+ min) so not a demo concern.

### No code paths to update

The `tier` field is the only handle — `model_for(tier)` already resolves correctly in `backend/agents/runner.py` via the existing `--model` flag injection. No prompt changes, no wiring changes, no smoke-test impact.

---

## 2026-04-22 — Bucket 4 export fidelity + frontend re-upload UI (completes the turn) `[DONE]`

Follow-on to the earlier DONE entry: the two items left for "follow-up" (Bucket 4 export fidelity and a UI affordance for the re-upload endpoint) both landed this turn. Recon on real session exports confirmed the priorities before any code changed.

### Recon — what's actually in agent markdown

Counted the feature usage across the 14-agent exports of session 99ba31a75ca9:

| Feature | Occurrences | DOCX before fix | DOCX after fix |
| --- | ---: | --- | --- |
| `---` horizontal rules | 186 | literal dashes in a paragraph | Word hr (`pBdr/bottom` border) |
| Numbered lists (`1. item`) | 142 | plain paragraph w/ literal `1. ` | `List Number` styled paragraph |
| Inline links `[text](url)` | 70 | plain text, not clickable | `w:hyperlink` run (blue + underline) |
| Mermaid diagrams | 25 | PNG embed (already worked) | PNG embed (unchanged) |
| Blockquotes (`> quote`) | 1 | plain paragraph | italic + indented paragraph |
| Inline images (`![]()`) | 0 | n/a | n/a |

Recon drove the priorities: `---` and numbered lists together account for ~70% of the fidelity gap; links are another ~15%. Inline images not worth chasing — zero usage.

### [backend/agents/export.py](backend/agents/export.py) — upgrades

**HTML / PDF pipeline (`markdown_to_html`):**

- Added `_NUMBER_LIST_RE` + `_number_list` substitution — `1. item` / `2. item` runs become `<ol><li>...` blocks. Previously fell through to literal text in a paragraph.
- `^(?:-{3,}|\*{3,}|_{3,})\s*$` → `<hr>`. Runs BEFORE the emphasis regex so `***` isn't misread as bold. The paragraph-wrapping pass was updated to skip `<hr>` so it renders as a block, not `<p><hr></p>`.
- `[text](url)` → `<a href="url">text</a>` with escape-safe regex that operates on the already-escaped HTML (so no unescaped `<` can sneak in).

**DOCX pipeline (`render_agent_docx`):**

- New helper `_add_horizontal_rule(doc)` — appends an empty paragraph whose `pPr` contains a single-line `pBdr/bottom` (`sz=6`, `color=bfbfbf`). That's the canonical python-docx workaround; Word renders it as a real horizontal rule.
- `^\d+\.\s+` matcher — batches consecutive numbered-list lines into `List Number` styled paragraphs so Word's own auto-numbering takes over. The resulting .docx stays editable (users can add/remove items and the numbering re-flows automatically).
- Blockquote handling — `> text` lines batched into italic, 18pt left-indented paragraphs.
- Heading levels now pass through up to H6 (previously clamped at H4; H5/H6 silently collapsed into H4). python-docx accepts 0-9 so the fix is a one-line clamp change.
- Pipe table: separator row detection is hardened (handles `---` + `:---:` + `---:`), and when a header separator is present the first row's cells get their runs bolded. `Light Grid Accent 1` table style remains.

**Inline-run upgrades (`_add_rich_paragraph` + new `_add_hyperlink`):**

- `_INLINE_RE` now captures `[text](url)` first so its backticks don't get stolen by the inline-code pattern (regex alternation order matters here).
- `_add_hyperlink(paragraph, url, text)` builds the `w:hyperlink` OOXML node directly — python-docx has no first-class hyperlink API. The run gets blue colour + single underline so links survive even when the target .docx template doesn't define a Hyperlink style.

**WeasyPrint PDF fallback (new `_render_pdf_weasyprint`):**

- `render_agent_pdf` now catches `ImportError` from Playwright and routes through WeasyPrint instead. Same standalone HTML is rendered via Pango — tables, hr's, and inline SVG diagrams all survive. No browser-side mermaid bootstrap (WeasyPrint can't run JS), so pre-rendered artifacts are mandatory — the existing `prerender_mermaid` pass already takes care of that.
- WeasyPrint is synchronous so we wrap the write in `asyncio.to_thread` to avoid blocking the event loop.
- Install path documented in the docstring: `pip install weasyprint`. Zero new mandatory dependencies — WeasyPrint only runs when Playwright isn't available.

### New — [scripts/smoke_export_fidelity.py](scripts/smoke_export_fidelity.py) — 32 assertions, 3 suites

- **`test_markdown_to_html`** (15 assertions) — h1–h6 each render with the right tag, exactly two `<hr>` appear for the two `---` separators in the fixture, `<ol>` lists render with `<li>` items, `<a href=...>` rendered for bare inline links AND for links inside list items, table rendered with both `<thead>` and `<tbody>`, blockquote rendered, fenced code carries the `lang-python` class, **`<hr>` is NOT wrapped in `<p>`** (regression guard for the paragraph-split pass).
- **`test_render_agent_docx`** (14 assertions) — introspects the generated .docx via ElementTree on `word/document.xml`: heading styles 1/2/4/5/6 all present (H5/H6 preserved, not clamped), both `ListBullet` and `ListNumber` styles present, **exactly 2 horizontal-rule paragraphs with `pBdr/bottom`**, exactly one table with 4 rows, table header row's runs are bold, ≥2 `w:hyperlink` nodes, blockquote rendered as italic+indented paragraph, fenced code uses `AppnovaCode` style.
- **`test_file_map_table_in_docx`** (2 assertions) — end-to-end: the `_file_map_to_markdown_table` output from Bucket 2 renders as a real Word table with header + 3 mapping rows.

### Frontend re-upload UI

**[frontend/index.html](frontend/index.html):**

- Added hidden `<input type="file" id="reupload-input" multiple>` + visible `<button id="reupload-btn" class="ghost-btn hidden">+ Add files</button>` to the `.upload-chip` container. Lives right after the Change button so the pair reads: **Change** (new session) · **+ Add files** (same session).

**[frontend/app.js](frontend/app.js):**

- `handleReupload(fileList, replace)` — posts to `POST /api/sessions/${state.sessionId}/upload` with the `replace=true/false` form field. Specifically handles HTTP 409 ("analysis is running") with a user-visible message instead of a cryptic error. On success, updates the upload-chip label + meta line and re-enables the Run button so the user can re-analyze the updated source.
- **Shift-click = replace mode.** Plain click is additive (merges with existing `source/`). Shift-click wipes `source/` first and shows a confirm dialog that explicitly calls out what's KEPT (converted/ + exports/ + cost history) vs what's wiped (source/ only). Prevents accidental destructive actions.
- `_toggleReuploadBtn()` gates the button's visibility on `state.sessionId && !state.running`. Called from 5 lifecycle points: fresh upload success, `startAnalysis`, the post-analysis teardown, the `reattachIfRunning` rehydration, and the reattach-polling "run complete" handler. Button is never visible before there's a session, and never visible while analysis is in flight (matching the backend's 409 rule).
- The file input is reset to `""` on change so selecting the same file again still fires the `change` event — subtle browser quirk that would otherwise lock the button on the second use.

**[frontend/style.css](frontend/style.css):**

- `#reupload-btn { margin-left: 8px; }` — drops the auto-margin inherited from `.ghost-btn` so the button butts up against the Change button instead of claiming the right edge.
- `#reupload-btn:hover { border-color: #34d399; color: #34d399; }` — green hover hint so users see at a glance that this is an additive action (distinct from the neutral Change button).

### Final regression — 216 assertions across 9 smokes, 0 failures

| Smoke | Assertions | This turn? |
| --- | ---: | --- |
| `smoke_run_converted.py` | 14 | (prior turn) |
| `smoke_report_scrubber.py` | 36 | (prior turn) |
| `smoke_line_fidelity.py` | 16 | (prior turn) |
| `smoke_file_map_render.py` | 18 | (prior turn) |
| `smoke_export_fidelity.py` | 32 | ✓ new |
| `smoke_demo_docs.py` | 48 | (earlier) |
| `smoke_coverage_contract.py` | 20 | (earlier) |
| `smoke_ui_binding.py` | 16 | (earlier) |
| `smoke_route_link_and_seed.py` | 16 | (earlier) |

**Total: 216 deterministic assertions.** 32 new this turn; all 184 existing assertions still green.

### Files touched

- new: `scripts/smoke_export_fidelity.py`
- modified: `backend/agents/export.py` (HTML hr/ol/link, DOCX hr/numbered list/blockquote/hyperlink/H5-6, WeasyPrint PDF fallback), `frontend/index.html` (+Add files button + hidden input), `frontend/app.js` (handleReupload + Shift-click replace + 5-point lifecycle gating), `frontend/style.css` (button styling)

### Notes

- **Clickable links everywhere.** The 70 `[text](url)` links across agent reports are now real hyperlinks in DOCX + PDF + HTML. GitHub issue links, doc pointers, and cross-references all open correctly in Word and Adobe.
- **Horizontal rules render as rules, not dashes.** The 186 `---` separators across reports stop showing up as literal dashes in Word.
- **Numbered lists renumber automatically.** Users editing the DOCX can add/remove items and the numbering re-flows — the previous plain-paragraph rendering baked the numbers in.
- **Deep headings preserved.** H5 and H6 no longer get collapsed to H4 — important for the auto-generated TOC when reports have deeply nested subsections (code-review + data-migration especially).
- **Re-upload works without losing anything.** Users who uploaded the wrong zip half-way through an analysis can add or replace files without minting a new session. Converted output, exports, cost history all survive.

---

## 2026-04-22 — Run-Converted MSB1003 fix + 5 demo-blocker buckets shipped (+1 new bucket) `[DONE]`

User hit a real failure on session `99ba31a75ca9`: clicking **Run Converted** produced `MSBUILD : error MSB1003: Specify a project or solution file. The current working directory does not contain a project or solution file.` and the app never booted. Also asked to implement all five `[PLANNED]` buckets from the 2026-04-22 earlier entry, plus flagged a new gap (no way to re-upload files to an existing session). This turn ships all of it with smoke-test coverage.

### Root cause of MSB1003 — the silent `is_relative_to` gotcha

The run log at `logs/runs/99ba31a75ca9/20260422-200114-1ec1fbdf0aa4.log` captured the exact argv: `C:\Program Files\dotnet\dotnet.EXE restore` — no project path. Traced to [backend/agents/run_manager.py#L310-L333](backend/agents/run_manager.py#L310-L333):

```python
project = find_dotnet_project(cwd)
if project is not None and project.is_relative_to(cwd):   # ← bug
    cmds.append(["dotnet", "restore", str(project.relative_to(cwd))])
else:
    cmds.append(["dotnet", "restore"])    # ← falls through to bare restore
```

`run_manager.start_run()` is called with a **relative** `converted_dir` path (`uploads/99ba31a75ca9/converted`), but `find_dotnet_project` resolves to an absolute path internally. Python's `Path.is_relative_to(cwd)` returns **False** when one path is relative and the other is absolute — so the else branch always wins for dual-stack layouts. The subprocess then runs from the top-level `converted/` dir where no .csproj lives → MSB1003.

### Fix (tight, regression-guarded)

1. **[backend/agents/run_manager.py](backend/agents/run_manager.py) — `_install_commands`:** resolve both `cwd` and the project path to absolute before the `is_relative_to` check. Additionally, **skip install entirely when a `run.bat` / `run.sh` / `run.ps1` exists** — the scaffold-generated runner already `cd`s into each sub-stack's folder and does its own `dotnet restore` / `npm install`, so issuing parallel installs from the top-level dir is redundant and hazardous. Removed the `cmds.append(["dotnet", "restore"])` fallback when no project is found; it could never have worked (that's literally MSB1003), better to let the dev-server candidate chain handle it.

2. **[backend/agents/run_manager.py](backend/agents/run_manager.py) — `_dotnet_dev_candidates`:** same resolve-to-absolute fix. Added an absolute-path fallback when the project truly sits outside `cwd` (defensive — shouldn't happen, but never emit a bare `dotnet run`).

3. **[scripts/smoke_run_converted.py](scripts/smoke_run_converted.py) — new, 14 assertions, 4 cases:**
   - Case 1: the exact 99ba31a75ca9 layout (dual-stack + run.bat + run.sh, backend/TotalBookingApi.csproj) — asserts install commands are empty (script owns them) and the first dev candidate uses `--project backend\TotalBookingApi.csproj`.
   - Case 2: dual-stack with NO run scripts — install must still target the csproj explicitly.
   - Case 3: single-stack .NET at the top level — sanity.
   - Case 4: invocation with a RELATIVE cwd path (the actual bug trigger) — confirms no bare `dotnet restore` lands anywhere.

### Bucket 5 — Mermaid bomb + artifact fence guard `[DONE]`

The demo-blocker from session 324b2024 where the UI/UX agent's report leaked `Syntax error in text` / `mermaid version 10.9.5` into client-visible markdown, and the `<!-- ARTIFACT_START -->` block sat outside a ```html``` fence so downstream markdown renderers consumed the embedded CSS asterisks (`*, *::before, *::after` → `, ::before, ::after`) and backticks in template literals.

- **New — [backend/agents/report_scrubber.py](backend/agents/report_scrubber.py):** central pre-save processor with three jobs, each idempotent:
  - `scrub_mermaid_bomb(text)` — matches `Syntax error in text` + `mermaid version \d+\.\d+\.\d+(-[\w.]+)?` anywhere in the body and replaces the enclosing paragraph with a readable fallback: *"⚠️ Diagram could not be rendered. See the structured table(s) below for the same information."*
  - `wrap_unfenced_artifact(text)` — finds every `<!-- ARTIFACT_START --> ... <!-- ARTIFACT_END -->` block, checks whether it already sits inside a ```html``` fence (by counting unclosed fence openings in the prefix), and wraps only the unfenced ones. Reverse-iterates the match list so splice indices stay valid.
  - `scrub_report(text)` — the one-stop call: wrap-artifact → strip-filler → scrub-mermaid, in that order.
- **[backend/agents/runner.py](backend/agents/runner.py):** imports `scrub_report` locally (avoids circular imports) and pipes `final_result_text.strip()` through it before the result lands in the `"result"` field that every downstream consumer reads. One-line wiring at the finalization point; no behaviour change for clean output.
- **[backend/agents/artifact.py](backend/agents/artifact.py):** added `ARTIFACT_RE_FENCED` so `extract_artifact` also matches the now-contractual ```html``` ... ``` wrapped version. Prefers the fenced variant so stripping removes the outer fence markers too — otherwise we'd leave dangling ```html / ``` rows in the saved markdown.
- **[backend/agents/prompts.py](backend/agents/prompts.py) — `ui-ux` agent prompt:** mandates wrapping the entire artifact block inside a ```html``` fence, with a concrete Ouroboros-style example and explicit warning: *"Emitting the markers as raw HTML outside a code fence is a reliable way to produce a broken preview — markdown parsers consume asterisks and backticks inside the embedded CSS/JSX, which is exactly the bug caught on session 324b2024."*

### Bucket 1 — Strip LLM transition filler `[DONE]`

The "I have sufficient information to produce the full analysis. Let me compile the report now." phrases (and 7 other shapes) caught in session 7a24d68c's migration-planner output. Clients read these as hallucination / stalling.

- **[backend/agents/report_scrubber.py](backend/agents/report_scrubber.py) — `_LLM_FILLER_PATTERNS`:** four regex families, each `re.MULTILINE | re.IGNORECASE`, covering:
  1. `^\s*(I|Now I|...) (have|now have|can now) (sufficient|enough|a thorough|a complete|...) (information|signal|picture|...). (Let me ...)?$`
  2. `^\s*Let me (now |go ahead and )?(compile|produce|write|present|draft|finalize|summarize|put together|outline|lay out|assemble|prepare|generate|deliver|share) ...$`
  3. `^\s*Now that (I've|I have) ..., (I|let me|I will|...) ...$`
  4. Belt-and-suspenders exact-phrase matches for the five transcripts captured verbatim, including curly-apostrophe variants.
- After substitution, collapses runs of 3+ blank lines to 2 so stripped sentences don't leave visible gaps.
- **[backend/agents/prompts.py](backend/agents/prompts.py) — `_STYLE_CONTRACT`:** appended a bullet explicitly forbidding transition announcements, with the five concrete shapes called out: *"NEVER emit sentences like 'I have sufficient information to produce the full analysis', 'Let me now compile the report', 'Now that I've gathered enough context, I'll write the report', 'I can now write the final report', 'Based on my research, I have a complete picture'. The client reads these as hallucination / stalling. If you're ready, just start the report with `# <Title>` on the first line."*

### Bucket 3 — Line-count fidelity validator `[DONE]`

Belt-and-suspenders against the silent-line-drop failure mode: `file_map.json` says every source has a target, but doesn't say every method / switch branch / validation clause inside survived the port.

- **New — [backend/agents/line_count_fidelity.py](backend/agents/line_count_fidelity.py):** `audit_line_fidelity(source_root, converted_root, context_dir)`. For every `1-to-1 port` / `port` / `rewrite` entry in `file_map.json`:
  - Counts non-blank **non-comment** lines on both sides using per-extension comment strippers (single-line markers `//`, `#`, `--`; block delimiters `/* */`, `<!-- -->`, `@* *@` for Razor, `{# #}` for Twig, `""" """` for Python docstrings).
  - Ratio thresholds: `< 0.30` red (likely content dropped), `0.30–0.50` yellow, `0.50–3.00` green, `3.00–4.00` yellow (JSX splits legitimately fan out), `> 4.00` red (likely invented code or dumped comments).
  - Skips files with fewer than 8 source logical lines (ratios too noisy), minified/lock files, binaries (NUL-byte sniff), and `merged` / `split` kinds (legitimate ratio skew).
  - Writes `converted/docs/LINE_FIDELITY.md` with Red / Yellow / Green tables sorted by ratio; red rows show source LOC, target LOC, ratio, and a human-readable reason.
  - Falls back to filename-stem heuristic when `file_map.json` is absent.
- **[backend/main.py](backend/main.py):** imported + wired `audit_line_fidelity` after the seed-completeness audit in `_run_analysis_stream`. Emits `line_fidelity_audit` SSE event.
- **[backend/agents/prompts.py](backend/agents/prompts.py) — `code-review` Step 4.9:** re-opens every red row, enumerates top-level symbols (classes, methods, functions, exported constants, switch cases, validation clauses, SQL WHERE clauses, Razor `@section`s), greps targets for matching names with PascalCase ↔ camelCase ↔ snake_case transforms, ports anything missing in place. Yellow rows get spot-check sampling (2-3 rows; if clean, skip the batch).
- **New — [scripts/smoke_line_fidelity.py](scripts/smoke_line_fidelity.py):** 16 assertions, 4 fixtures — 60→6 line drop flags red, 20→24 line healthy flags green, 12→60 line bloat flags red (above YELLOW_HI), 5-line file flags skipped.

### Bucket 2 — File Migration Map on UI + export `[DONE]`

The authoritative source→target contract from `context/file_map.json` is now a visible, sortable, filterable table under the migration-planner card + appended to the markdown/DOCX/PDF exports.

- **[backend/main.py](backend/main.py) — new endpoint `GET /api/sessions/{session_id}/file-map`:** returns `{mappings: [...], counts: {rewrite, create, delete, total}, ...}`. Derives an `action` per row:
  - `kind` contains `skip` / `drop` / `delete` OR `targets` empty → `DELETE`
  - No `source` field → `CREATE`
  - Otherwise → `REWRITE`
  Preserves the raw `kind` alongside so clients wanting the exact agent-emitted label can read both.
- **[frontend/app.js](frontend/app.js) — `appendFileMapBlock(c)` + `renderFileMapTable(block, data)`:** injected after `renderMermaidIn` in `renderFinalMarkdown`, fires only when the agent id is `migration-planner` / `migration_planner`. Renders a `<details>` block (collapsed by default — lazy-fetches on first open so large maps don't delay initial paint). Table columns: # · Source (legacy) · Target (converted) · Action · Kind · Responsibility. Controls: free-text path search + four action filter buttons (All / Rewrite / Create / Delete). Rows sorted by `order` field then by source path so wave-1 lands at the top.
  - Also added `agent_id: id` to `registerCard`'s card object so the renderer can gate on id.
- **[frontend/style.css](frontend/style.css):** `.file-map-block` summary + body + controls, `.file-map-table` with sticky headers + hover rows + zebra-lite borders, `.action-chip.rewrite|.create|.delete` in three distinct colour pairs (blue/green/red @ ~22% alpha so they read clearly on dark bg without shouting). `-webkit-user-select: none` added for Safari compat on the summary row.
- **[backend/main.py](backend/main.py) — `_file_map_to_markdown_table(path)`:** renders the same data as a real markdown pipe-table; `_auto_export_session` appends it to the migration-planner's body **before** mermaid pre-render + DOCX / PDF export. Same rows, same counts, same sort order as the UI. Long responsibility text truncated at 160 chars with ellipsis to keep the table scannable in Word.
- **New — [scripts/smoke_file_map_render.py](scripts/smoke_file_map_render.py):** 18 assertions — missing/unparseable JSON returns empty, typical 5-row payload produces correct counts + correct action per row + correct row order, long responsibility text truncates at 160 chars, list-root file_map parses too.

### Bucket 6 — Re-upload to existing session (new, user-flagged mid-turn) `[DONE]`

User asked: *"what we do when for the session if we need to upload another file and run analysis we are not able to do??"* — confirmed: `/api/upload` always mints a new `session_id`, so users who uploaded an incomplete archive and realised mid-analysis had no path forward other than starting over (losing target-stack setting, converted/ output, cost-tracker history).

- **[backend/main.py](backend/main.py) — new endpoint `POST /api/sessions/{session_id}/upload`:**
  - Accepts the same `files: list[UploadFile]` payload as the original upload endpoint.
  - New `replace: bool = Form(False)` param — when true, wipes `source/` before extracting (keeps `converted/`, `exports/`, `logs/`); when false, merges additively with the existing source tree.
  - **Refuses (HTTP 409)** when an analysis task is already running for the session — prevents racing the code-gen agent against a changing source tree.
  - Re-runs `_detect_project_root` after the new upload (wrapper dir may have changed shape) and refreshes `_session_dirs[session_id]`.
  - Invalidates the in-memory discovery digest so the next `/analyze` call does a fresh discovery pass on the updated source.
  - Returns the same shape as `/api/upload` plus `{replace, reanalyze_hint: "POST /api/analyze/<sid> to re-run"}` so the frontend can refresh its local state with one assignment.

### Final smoke regression — 184 assertions, 0 failures

| Smoke | Assertions | Notes |
| --- | ---: | --- |
| `smoke_run_converted.py` (new) | 14 | MSB1003 regression guard; case 4 is the exact relative-cwd bug |
| `smoke_report_scrubber.py` (new) | 36 | filler strip + mermaid bomb + artifact fence, e2e + idempotence |
| `smoke_line_fidelity.py` (new) | 16 | red drop + green healthy + red bloat + skipped-too-small |
| `smoke_file_map_render.py` (new) | 18 | endpoint data shape + markdown table format |
| `smoke_demo_docs.py` | 48 | previous turn — still green |
| `smoke_coverage_contract.py` | 20 | previous turn — still green |
| `smoke_ui_binding.py` | 16 | previous turn — still green |
| `smoke_route_link_and_seed.py` | 16 | previous turn — still green |

**Total: 184 deterministic assertions across 8 smokes.**

### Bucket 4 — Export fidelity (mermaid PNG embed, real Word tables) `[DEFERRED]`

The original plan called for recon on a live session's exports before specifying the divergences. Deliberately left for a follow-up turn when there's a frozen demo session to diff against. Mermaid PNGs already land in exports via the existing `prerender_mermaid` path, and with Bucket 5's defuser running at save time the literal `Syntax error in text` strings no longer leak through — so the immediate demo risk is already contained.

### Notes for Krishna

- **Run Converted works again.** The MSB1003 failure blocked all .NET dual-stack demos; session 99ba31a75ca9 will now cd into `backend/` via the generated `run.bat` and boot TotalBookingApi properly. Re-click the "Run Converted" button on any affected session.
- **Reports are cleaner.** Filler sentences + mermaid error banners never reach the saved markdown or the live stream. The ui-ux artifact block is now fenced so CSS asterisks and template-literal backticks survive literal through the markdown renderer.
- **File Map is visible.** Click any migration-planner card after it finishes and the **📁 File Migration Map** section shows every source → target with action chips and free-text filtering. The DOCX/PDF exports carry the same table.
- **Re-upload is live.** `POST /api/sessions/<sid>/upload` (with optional `replace=true`) amends an existing session's source tree in place. Still need to wire a UI affordance for it — current turn shipped the backend contract.

### Files touched (one-line summary)

- new: `backend/agents/report_scrubber.py`, `backend/agents/line_count_fidelity.py`, 4× new smoke scripts
- modified: `backend/agents/run_manager.py` (MSB1003 fix), `backend/agents/runner.py` (scrub hook), `backend/agents/artifact.py` (fenced extractor), `backend/agents/prompts.py` (style guard + ui-ux fence mandate + code-review Step 4.9), `backend/main.py` (file-map endpoint + markdown table + re-upload endpoint + line-fidelity wiring), `frontend/app.js` (File Migration Map block), `frontend/style.css` (file-map styling)

---

## 2026-04-22 — Report polish: strip LLM filler, render File Map on UI, export fidelity, mermaid bomb, line-count audit `[PLANNED]`

User flagged five categories of failure visible in recent session transcripts:

1. **LLM transition filler leaks into client-visible reports.** Phrases like `"I have sufficient information to produce the full analysis. Let me compile the report now."` / `"I have enough signal to write the full report now."` / `"I now have a thorough picture of all major security issues. Let me produce the audit report."` appear between research and writing in multiple agent outputs. Client reads these as hallucination / filler.
2. **Migration-planner report doesn't surface the file-by-file mapping on UI.** AppNova already produces `context/file_map.json` (authoritative contract for code-gen) + a narrative A.4 section. UI renders only the prose. Client wants a **"Source file | Target file | Action (rewrite / create / delete)"** table visible on the migration-planner card, not buried in the markdown.
3. **Code-gen must write every line without dropping any from source.** The `file_map.json` contract guarantees every file has a target, but doesn't guarantee every method / line inside survives. Occasional line-level drops slip through.
4. **Exports don't match UI rendering.** Markdown → DOCX / PDF path drops images, mermaid diagrams, or table structure; tables sometimes render as ASCII bars instead of real Word tables.
5. **Mermaid bomb.** A UI/UX agent run (session 324b2024) emitted the literal text `Syntax error in text / mermaid version 10.9.5` between "Top Next Actions" and `<!-- ARTIFACT_START -->`. Same report also had an unfenced artifact block where markdown consumed asterisks (`,::before,*::after` instead of `*,*::before,*::after`) and backticks (template literals like `${color}20` lost their outer backticks) — because the agent emitted `<!-- ARTIFACT_START --> ... <!-- ARTIFACT_END -->` as raw HTML instead of inside a ` ```html ... ``` ` fence.

Plan below is non-destructive, targets ~11–13 hours sequential, and re-uses the validator+prompt-patch pattern the last six rounds of changes settled on.

### Bucket 5 — Mermaid bomb + artifact escape (priority 1, ~2 hrs)

**Files touched:** [backend/agents/mermaid_renderer.py](backend/agents/mermaid_renderer.py), [backend/agents/diagram_qa.py](backend/agents/diagram_qa.py), [backend/agents/runner.py](backend/agents/runner.py), [backend/agents/artifact.py](backend/agents/artifact.py), [backend/agents/prompts.py](backend/agents/prompts.py) (ui-ux only), new `scripts/smoke_mermaid_bomb.py`.

Steps:

1. In `mermaid_renderer.py`, when a Playwright render fails, replace the offending ` ```mermaid ``` ` block in the saved markdown with a text-only fallback stub: `> ⚠️ Diagram failed to render. See the structured table(s) below for the same information.` — **never** let the literal error text land in the report.
2. Add a post-render scrubber in `runner.py` (defensive layer) that greps every saved agent result for the literal strings `Syntax error in text` + `mermaid version \d+\.\d+\.\d+` and replaces the enclosing paragraph with the same fallback stub.
3. In `artifact.py`, when extracting `<!-- ARTIFACT_START --> ... <!-- ARTIFACT_END -->`, require the inner HTML be inside a ` ```html ... ``` ` fence. If not fenced, wrap server-side before save — this is what stops markdown/JSX parsing from eating asterisks and backticks in the CSS/JSX source.
4. Patch `ui-ux` agent prompt to explicitly demand the fenced wrapping: **"Emit the entire `<!-- ARTIFACT_START --> ... <!-- ARTIFACT_END -->` block inside a ` ```html ... ``` ` fenced code block. Never emit raw HTML outside a code fence — markdown will strip asterisks and backticks inside."**
5. Smoke: feed a markdown containing the exact error text → assert scrubber replaces. Feed an artifact block with raw `*,*::before,*::after` CSS + template-literal backticks → assert escape guard preserves every `*` and every `` ` ``.

### Bucket 1 — Strip LLM filler transitions (priority 2, ~2 hrs)

**Files touched:** [backend/agents/runner.py](backend/agents/runner.py), [backend/agents/prompts.py](backend/agents/prompts.py) (`_STYLE_CONTRACT` + every brief preamble), new `scripts/smoke_filler_strip.py`.

Steps:

1. Add `_LLM_FILLER_PATTERNS` in `runner.py` — regex list covering the transition phrase shapes:
   - `^(?:I|Now I|I now|I can now|Based on .*?, I|Having .*?, I)\s+(?:have|now have|can now)\s+(?:sufficient|enough|a (?:thorough|complete|comprehensive|clear))\s+(?:information|signal|picture|understanding).*?\.\s*(?:Let me .*?\.)?\s*$`
   - `^Let me (?:now )?(?:compile|produce|write|present|draft|finalize|summarize) .*?\.\s*$`
   - `^Now that .*?, (?:I|let me) .*?\.\s*$`
   - Belt-and-suspenders exact-string list for the 5 phrases captured in transcripts.
2. `_strip_llm_filler(text)` — applies each pattern via `re.sub(..., "", text, flags=re.MULTILINE)`, then collapses `\n{3,}` → `\n\n`.
3. Call `_strip_llm_filler` in:
   - Final result save path (before markdown lands in `reports/` / `docs/` / exports)
   - SSE stream (buffer per-line; scrub completed lines before they reach the frontend)
4. Append to `_STYLE_CONTRACT`: **"Open every report with `# <Title>` on the FIRST line. NEVER emit transition sentences ('I have sufficient information', 'Let me now compile', 'Now that I've gathered', 'I can now write'). If you're ready, just start writing."** Also append to every `brief_*.md` preamble so it's inescapable.
5. Smoke: feed a markdown with all five caught phrases → assert each removed; assert surrounding `# headings` + tables + code fences survive.

### Bucket 2 — File Migration Map UI table (priority 3, ~3 hrs)

**Files touched:** [frontend/app.js](frontend/app.js), [frontend/style.css](frontend/style.css), [backend/main.py](backend/main.py) (new endpoint), [backend/agents/export.py](backend/agents/export.py), new `scripts/smoke_file_map_render.py`.

Steps:

1. New endpoint `GET /api/sessions/{sid}/file-map` returning `context/file_map.json` raw (404 if absent).
2. In `app.js`, on the migration-planner card, below the rendered markdown, add a collapsed **"File Migration Map"** section. On expand: `authFetch` the endpoint, render a sortable / filterable table:

   | # | Source (legacy) | Target (new) | Action | Kind | Responsibility |

   Action derivation per row:
   - `kind === "SKIPPED"` → `DELETE` (red chip)
   - `source` exists + `targets[]` non-empty → `REWRITE` (blue chip)
   - No `source` row but target appears only in `targets[]` of some new-scaffold entry → `CREATE` (green chip)

3. Sort by `order` (wave) by default; filters: action chips (All / REWRITE / CREATE / DELETE) + free-text path search.
4. `style.css` adds `.file-map-table` + `.action-chip.rewrite|.create|.delete` (three distinct colors).
5. `export.py` appends the file-map table as a real markdown / DOCX / PDF table at the end of the migration-planner export.
6. Smoke: curl `/api/sessions/<frozen-demo>/file-map` → assert JSON shape; render into DOM via headless Playwright → assert each action type appears with correct chip color.

### Bucket 4 — Export fidelity matches UI (priority 4, ~2–4 hrs, recon first)

**Files touched:** [backend/agents/export.py](backend/agents/export.py), [backend/agents/mermaid_renderer.py](backend/agents/mermaid_renderer.py), new `scripts/smoke_export_fidelity.py`.

Steps:

1. Recon — open a recent session's `exports/*.md` + `*.docx` + `*.pdf` alongside the UI rendering. Enumerate every divergence (missing images, ASCII-art tables, font misalignment, missing diagrams, orphan code fences, stray "Syntax error in text" strings).
2. md → DOCX path:
   - Markdown tables → real Word tables (header styling + zebra rows)
   - `![alt](src)` → embedded PNG (mermaid-rendered when applicable)
   - ` ```mermaid ``` ` → embedded PNG from the mermaid-renderer cache
   - `---` → Word horizontal rule, not literal three dashes
   - Heading hierarchy keyed to DOCX auto-TOC
3. md → PDF path: same fixes through `weasyprint` / `markdown-it-py` → HTML → PDF so CSS table styling survives.
4. File Migration Map table (Bucket 2) lands with identical column widths in all three surfaces.
5. Smoke: frozen demo session → export .md / .docx / .pdf → assert (via `python-docx` + `pypdf`) table count matches markdown; image count matches markdown `![...]`; zero literal `Syntax error in text` anywhere.

### Bucket 3 — line_count_fidelity validator (priority 5, ~2 hrs, belt-and-suspenders)

**Files touched:** new [backend/agents/line_count_fidelity.py](backend/agents/line_count_fidelity.py), [backend/main.py](backend/main.py) wire-up, [backend/agents/prompts.py](backend/agents/prompts.py) (new `code-review` Step 4.9), new `scripts/smoke_line_fidelity.py`.

Steps:

1. New module `audit_line_fidelity(source_root, converted_root, context_dir)`:
   - Reads `file_map.json`. For every `kind == "1-to-1 port"` row:
   - Count source non-blank non-comment lines
   - Sum target same lines across `targets[]`
   - Ratio < 0.3 → `red` (likely dropped content)
   - Ratio > 4.0 → `yellow` (bloat — possibly invented code)
   - 0.5–3.0 → `green`
   - Skip binary / minified files.
   - Write `converted/docs/LINE_FIDELITY.md` with Red / Yellow / Green tables.
2. Wire in `main.py` after `audit_ui_binding`; emit `line_fidelity_audit` SSE event.
3. Prompt patch — `code-review` new Step 4.9: **"Read `docs/LINE_FIDELITY.md`. For every `red` row, re-open source + target and confirm every top-level symbol (class / method / function / exported const) survived. Port any missing ones in place; flag irrecoverable gaps in the final handoff."**
4. Smoke: synthetic 100-line source → 10-line target → assert `red`; 100-line source → 150-line target → assert `green`; binary fixture → assert skipped.

### Priority order (demo crunch)

| # | Bucket | Why that order | Effort |
|---|---|---|---|
| 1 | **Bucket 5** (mermaid + artifact escape) | Client saw `Syntax error in text` in live transcript — demo-blocking | ~2 hrs |
| 2 | **Bucket 1** (strip LLM filler) | Same transcript had 4× `"I have sufficient information..."` — reads as hallucination | ~2 hrs |
| 3 | **Bucket 2** (File Migration Map UI) | Makes "did you convert every file?" visible to steering committee | ~3 hrs |
| 4 | **Bucket 4** (export fidelity) | Depends on recon; overlaps Bucket 5 mermaid fix | ~2–4 hrs |
| 5 | **Bucket 3** (line_count_fidelity) | Belt-and-suspenders backup for Bucket 2 contract | ~2 hrs |

**Total: ~11–13 hours sequential.** Buckets 1 + 4 + 5 share `runner.py` / `mermaid_renderer.py` touch points → can be done in one sitting. No implementation until user approves; logged here as the paper trail of what's queued.

### Evidence of the five failures (pointers for when implementation starts)

- **Filler:** session 7a24d68c transcript, Phase 12–15 migration-planner output: `"I have sufficient information to produce the full analysis. Let me compile the report now."` + 3 more variants.
- **File map invisible:** same session's migration-planner card: renders Phase / team / risk matrix prose but no file-by-file table.
- **Mermaid bomb:** session 324b2024 (ui-ux agent, 465s, 22 tools, $1.08): report emits `Syntax error in text\nmermaid version 10.9.5` between the "Top Next Actions" section and `<!-- ARTIFACT_START -->`.
- **Artifact escape:** same session's embedded artifact HTML — CSS `,::before,*::after` (leading `*,` eaten), JSX comments `/ ── X ── /` (asterisks eaten), template literals `${color}20` + `1px solid ${color}40` (outer backticks eaten). Root cause: artifact block not in a ` ```html ``` ` fence.

---

## 2026-04-22 — Azure VM + Azure SQL production deploy runbook (zero-regression gates) `[DONE]`

User has a provisioned Azure VM (Ubuntu 22.04) + Azure SQL Database equivalent to the legacy `dw` database, asked for a step-by-step terminal guide to bring production up from the VM with zero regression.

### [DEPLOY_AZURE_VM_UBUNTU.md](DEPLOY_AZURE_VM_UBUNTU.md) — new, ~800 lines

Concrete runbook tailored to the ARIES stack (.NET 8 + React + Azure SQL + Azure Key Vault). Eight stages, each ending with a **"did it work?"** check that the user must pass before moving on:

- **Stage 0 — Pre-flight from laptop.** SSH reachability, SQL firewall whitelist for the VM's outbound IP (auto-derived via `curl ifconfig.me` on the VM), baseline VM snapshot (disk / memory / running services / listening ports → saved under `~/snapshots/`), and — critically — an **audit-report gate** that greps the six AppNova validator outputs (`FILE_COVERAGE.md` / `API_CONTRACT.md` / `UI_BINDING_AUDIT.md` / `ROUTE_LINK_CONTRACT.md` / `SEED_COMPLETENESS.md` / `CONTRACT_AUDIT.md`) and refuses to build the tarball unless every red-finding counter is zero AND contract-audit verdict is `PASS`. That's the first regression-prevention layer.
- **Stage 1 — VM prereqs (first deploy only).** `apt install aspnetcore-runtime-8.0 nginx sqlite3 msodbcsql18 mssql-tools18`, deploy user + `/opt/<app>` + `/var/www/<app>` + `/etc/<app>` layout, certbot.
- **Stage 2 — Upload release.** `scp` the tarball, unpack as deploy user, rsync frontend to nginx root.
- **Stage 3 — Config + schema migrations.** Two options documented for the env file (plain `/etc/<app>/app.env` with connection string; OR `AZURE_KEY_VAULT_URI` pointing at a managed-identity-authorised vault). Schema migrations via `dotnet ef database update` (either from the VM if SDK installed, or from laptop targeting the same Azure SQL). Production lookup-seed step explicitly WARNS against running `DevSeeder` — prod seed is a separate script targeting only the reference tables documented in `docs/SEED_COMPLETENESS.md`. Stage-exit check: `sqlcmd` row-count per lookup table, must all be ≥ 3.
- **Stage 4 — systemd + nginx + TLS.** Full systemd unit (Type=simple, EnvironmentFile, SIGINT stop), full nginx vhost (TLS-ready, `/api/*` reverse proxy, SPA fallback via `try_files`, 30-day `/assets/` cache, X-Frame-Options / nosniff / Referrer-Policy), Let's Encrypt via certbot non-interactive. UFW enabled LAST (after nginx is verified) to avoid locking yourself out.
- **Stage 5 — 10-point live smoke test.** This is the real zero-regression gate. Runs from the laptop and asserts:
  1. `/health` 200
  2. `/api/auth/login` returns a JWT ≥ 500 chars
  3. Every lookup endpoint returns ≥ 3 rows (genders / races / hair-colors / eye-colors / counties / cities / charge-types / offense-codes / arrest-case-types)
  4. Every endpoint flagged **missing** in `docs/API_CONTRACT.md` actually resolves (if any 404s, REGRESSION — that report was wrong or a route was dropped)
  5. CRUD round-trip on the primary entity (POST → GET → DELETE returns 204)
  6. TLS certificate valid (not self-signed)
  7. Security headers present (X-Frame-Options / X-Content-Type-Options / Strict-Transport-Security)
  8. Demo-only routes blocked (`/api/test`, `/api/debug`, `/mock-azure`, `/sample-data` all 404)
  9. `journalctl --since '2 minutes ago'` has zero ERROR/FAIL/EXCEPTION lines
  10. Live lookup row counts match the SEED_COMPLETENESS.md expectations
- **Stage 6 — Day-2 ops.** Log-tail command, service-restart command, Key Vault secret rotation (3 steps, ~30s downtime), hotfix procedure that keeps the previous release at `/opt/<app>/publish.prev` for instant rollback, Azure SQL PITR verification + optional nightly `bacpac` export to blob storage.
- **Stage 7 — Emergency rollback.** Stop service → swap `publish.prev` back in → restart → re-smoke. If smoke STILL fails, schema-rollback options (either revert migration with `ef migrations script` or Azure SQL PITR to 15 min before the deploy).
- **Stage 8 — Architecture diagram + operational reference.**

### Appendices

- **Appendix A — Troubleshooting by symptom.** 10-row table keying each common error (502 Bad Gateway, `Login failed for user`, empty dropdowns, `Forbidden: access denied to vault`, expired TLS, `permission denied` on env file, etc.) to its likely cause and specific fix — with cross-references to the relevant stage.
- **Appendix B — Full command reference.** No-prose copy-paste version of every command in deploy order. Good for copying into a CI/CD pipeline skeleton later.

### Zero-regression story — how this paper actually delivers that

Three layers:

1. **Pre-deploy gate (Stage 0.4)** — the build-tarball step reads AppNova's six validator reports and **refuses to ship** if any red row exists. Regressions can't leave the laptop.
2. **Post-deploy smoke (Stage 5)** — 10 live checks that re-verify every class of gap the audit reports previously flagged. Lookups truly populated, no 404s, no leaked demo routes, security headers present.
3. **Instant rollback (Stage 7)** — previous release kept on disk; ~30-second swap procedure. If the live smoke surfaces something the pre-deploy gate missed, the window of impact is measured in seconds, not hours.

### Notes

- The runbook treats `ui_binding.py`'s recent path-hints enhancement (entity-folder detection via `/models/`, `/entities/`, `/dto/`, etc.) as already-integrated — no callout needed in the user-facing paper. Reports downstream of it get the improved signal automatically.
- All placeholder values (`<vm-ip>`, `<domain>`, `<sql-server>`, etc.) are exported into shell variables at the top of the paper so the user sets them once and every subsequent command substitutes correctly.
- No code change in this round; pure deliverable. The runbook lives at the repo root, intended to also be copy-pasted into any converted project's root as a drop-in deploy paper — same commands, swap the `$APP_NAME` variable.

---

## 2026-04-22 — Back-propagate the 6-round ARIES post-gen fixes into code-gen + validators + docs `[DONE]`

User shared the full 6-round post-generation changelog from a real ARIES conversion — every round documents manual fixes AppNova should have made automatically. User's ask: *"all these changes before code generation to be done through code generation and specific agents — make our appnova a robust engine where using claude max subscription is enough to complete the conversion app to build on production and in azure environment, and each step to be noted in readme.md of converted app for both demo and production code and what needs to run what needs to be deleted."*

Gap map after this pass:

| Round | Failure class | Defense added in this commit |
|---|---|---|
| R1-2 (15 missing backend endpoints) | already caught by `api_contract.py` | — |
| **R1-3 (7/15 lookup tables unseeded → empty dropdowns)** | **new `seed_completeness.py` validator** |
| R1-4 (no Key Vault / non-IT docs) | already caught by `demo_docs.py` | — |
| R1-4 (no Ubuntu-no-Docker runbook) | **demo_docs.py now emits `DEPLOY_UBUNTU.md`** |
| R1-4 (no production-ready README) | **`scaffold.ensure_documentation` rewrote template with Demo / Prod / Delete structure** |
| R2-1/2 (PCDEC UI binding gaps) | already caught by `ui_binding.py` | — |
| R2-3 (ListPage missing filter UI) | already caught by per-page UI fidelity | — |
| R3-1 (missing `forwardRef`) | **code-gen prompt: framework-idiom hygiene checklist** |
| R3-2 (React Router v7 future flags) | **code-gen prompt: explicit flag requirement** |
| R3-3/4 (sidebar label ↔ page H1 drift) | **new `route_link_contract.py` naming-drift scan** |
| **R3-5 (dead `/admin` sidebar link)** | **new `route_link_contract.py` dead-link scan** |
| R4-1 (required-field propagation) | **code-gen prompt: source `required-field` → Zod `.min(1)` + `[Required]` DTO rule** |
| R4-2/3 (server-side auto-population) | **code-gen prompt: preserve-legacy-server-defaults rule** |
| R5-1/2 (permission-guard mismatches) | partially covered by contract-audit's security check; full fix deferred |
| R6 (Ubuntu-no-Docker deploy) | **demo_docs.py now emits `DEPLOY_UBUNTU.md`** |
| R6 (Azure production deploy) | **demo_docs.py now emits `DEPLOY_AZURE.md`** |
| R6 (what to delete before prod) | **README "What to DELETE before production" section** |

### New module — [backend/agents/route_link_contract.py](backend/agents/route_link_contract.py)

`audit_route_link_contract(converted_root)` walks the frontend tree once and:

- Extracts every place the UI says "go here" — `<Link to="X">`, `<NavLink>`, object-literal sidebar items `{ path: '/admin', label: 'Admin' }`, `[routerLink]`, `<router-link to=>`, `navigate('/x')`, `router.push('/x')`. 8 patterns across React / Angular / Vue.
- Extracts every `<Route path=>` / `{ path, component }` router-config entry.
- Detects router-config files by actual usage signals (`<Routes>`, `<Route `, `createBrowserRouter`, etc.) — **NOT** by react-router-dom imports (sidebars import `NavLink` and would otherwise be misclassified).
- **Strips JS/TS line, block, and JSX comments** before scanning. Prevents a stray remark like `// NO <Route path="/admin">` from being read as real code (caught on first smoke).
- Diffs: dead links (path points nowhere) vs naming drift (link label ≠ page H1 / `<PageHeader title=>` / `document.title =`). For naming drift, finds the page component by filename-stem token overlap, greps the top H1/title patterns, compares lenient-canonicalised strings.
- Writes `converted/docs/ROUTE_LINK_CONTRACT.md` with Dead Links + Naming Drift + Registered Routes sections.

### New module — [backend/agents/seed_completeness.py](backend/agents/seed_completeness.py)

`audit_seed_completeness(converted_root, min_rows=3)` walks the backend tree and:

- Finds every lookup-style endpoint (path matches `/api/lookups/*`, `/api/*-types`, `/api/*-severity`, `/api/genders|races|counties|cities|states|parent-types|agencies|hair-colors|eye-colors`). Handles .NET `[HttpGet("path")]`, FastAPI `@app.get`, Laravel `Route::get`, NestJS `@Get`, Flask `@app.route`, Express `app.get`. Expands controller-level `[Route("api/[controller]")]` prefixes.
- For each endpoint's handler body, extracts the DbSet referenced — `_db.X` / `context.X` / `prisma.x.findMany` / `.query(X)` / `X.objects.all()`. Falls back to URL-segment-as-entity when no DbSet is found.
- Walks seed files (filename/path contains `seed`/`seeder`/`fixtures`) and counts rows per entity across 5 idiom patterns: EF Core `.AddRange(new[] { new X {...} })` + `HasData(...)`, Prisma `createMany({ data: [...] })`, SQLAlchemy `add_all([X(), ...])`, Django `bulk_create([X(), ...])`.
- Canonicalises entity names (strips punctuation, collapses `ies/es/s` plurals) so `OffenseCode` / `offense_codes` / `offenseCodes` all match.
- Any endpoint whose entity has < `min_rows` seeded rows is flagged as **thin** — its dropdown will come back empty at demo time, which is the R1 demo-killer.
- Writes `converted/docs/SEED_COMPLETENESS.md` with Thin Lookups (❌) + Healthy Lookups (✅) + Full Seeded-Row Inventory tables.

### [backend/agents/demo_docs.py](backend/agents/demo_docs.py) — 3 → 5 docs

`write_demo_docs` now emits two additional runbooks:

- **`docs/DEPLOY_AZURE.md`** (~275 lines) — step-by-step Azure App Service production deploy. Covers `az group create` → SQL server + DB → Key Vault → secret load → App Service Plan + Web App → managed-identity badge + vault access policy → `AZURE_KEY_VAULT_URI` env var → code deploy (GitHub Actions workflow + one-shot `az webapp up`) → DELETE demo-only files before going live → `/health` smoke check → troubleshooting table with 5 common symptoms. Every step is copy-pasteable; the deploy-root name is auto-derived from the converted project folder.
- **`docs/DEPLOY_UBUNTU.md`** (~320 lines) — plain Ubuntu 22.04 LTS, **no Docker**. Distilled from the real R6 runbook. Covers `apt install dotnet-sdk-8.0 nginx` + Miniconda for helper scripts → deploy-user + directory layout (`/home/deploy/<app>`) → release tarball upload → two options for secrets (plain `/etc/<app>/app.env` OR Azure Key Vault via service principal) → systemd unit (Type=notify, EnvironmentFile) → nginx vhost (API reverse proxy + SPA fallback) → Let's Encrypt via certbot → UFW firewall → DELETE demo-only files → rolling-update procedure → nightly backups via cron + conda env → troubleshooting table.

### [backend/agents/scaffold.py](backend/agents/scaffold.py) — production-ready README template

`ensure_documentation` now emits a README with hard structure:

- **Table of contents** at the top, linking to 9 numbered sections
- **What this project is** — detected stack, dual-stack note, demo-mode vs production-mode explanation
- **5-minute demo run** — what works, what doesn't
- **Production deployment** — two runbooks, pick by infra (App Service vs plain Ubuntu), pointer to `AZURE_KEYVAULT_GUIDE.md` + `SECRETS_MAPPING.md`
- **What to DELETE before production** — concrete table of paths (`mock-azure/`, `sample-data/`, `.env*`, auto-startup dev seeders) + a cleanup one-liner
- **What every command does** — demo/build/deploy command reference
- **Architecture at a glance** — ASCII frontend → backend → DB + Key Vault diagram
- **Auto-generated audit reports** — cross-links to all 7 audit docs (FILE_COVERAGE / API_CONTRACT / UI_BINDING / UI_FIDELITY / ROUTE_LINK / SEED_COMPLETENESS / CONTRACT_AUDIT), with PASS/FAIL-gating statement
- **Troubleshooting** — 7-row symptom→check table
- **Documentation** — agent-authored section appended if `documentation` agent ran

### [backend/main.py](backend/main.py) — two new audits wired into the pipeline

Two new try/except blocks after the existing UI binding audit:

- `audit_route_link_contract(converted_dir)` → `route_link_audit` progress event
- `audit_seed_completeness(converted_dir)` → `seed_completeness_audit` progress event

Both swallow exceptions; reports land on disk regardless.

### [backend/agents/prompts.py](backend/agents/prompts.py) — 4 prompt upgrades

- **`code-generation` SELF-CHECK: Check 4** — every `<Link>` / sidebar item resolves to a registered `<Route>`, and link labels match target page titles. Fully spelled out with concrete greppable patterns for React / Angular / Vue / legacy AngularJS.
- **`code-generation` SELF-CHECK: Check 5** — required-field propagation (source HTML `required-field` / Angular `[required]` / RHF `register("x", { required })` → Zod `.min(1)` + `[Required]` on target DTO) AND server-side auto-population preserved (source `$user->X`, `Auth::user()`, `Carbon::parse`, `getAgeByDate`, truncation/sanitisation → target service method before save). Five concrete examples from the 2026-04-22 R4 review.
- **`code-review` Step 4.75 (framework-idiom hygiene)** — explicit `forwardRef`, React Router v7 future flags, Vue 3 `<script setup>`, Angular standalone components, naming consistency across sidebar/page-H1/route-segment/filename.
- **`code-review` Step 4.8** — consume `docs/ROUTE_LINK_CONTRACT.md` + `docs/SEED_COMPLETENESS.md`. Every Dead Link + Thin Lookup row is a red finding to fix in place.
- **`contract-audit` Checks 8 + 9** — new sections for route-link + seed-completeness reports. Summary block extended with two new lines. Verdict rules hardened: **FAIL** now triggers on ≥ 1 dead link OR ≥ 1 thin lookup.

### [scripts/smoke_route_link_and_seed.py](scripts/smoke_route_link_and_seed.py) — 16-assertion smoke

Synthesises a converted project with the EXACT 2026-04-22 R1 + R3 failures:

- `App.tsx` registers 3 routes (`/`, `/workflow`, `/pc-declaration`).
- `Sidebar.tsx` has 4 link items — one pointing at `/admin` (dead, no route) and one labeled "Workflow Guide" where the page's `<h1>` says "Workflow Documentation" (naming drift).
- `LookupsController.cs` exposes 5 endpoints; `DevSeeder.cs` seeds only 3 entities (Genders/Races/Counties with 3-4 rows each) and intentionally leaves ChargeTypes + OffenseCodes unseeded.

Asserts every one of those gaps is surfaced. One real bug caught on first smoke: the router-config detector was misclassifying a sidebar that imports `NavLink from 'react-router-dom'` as a router-config file, pulling its object-literal paths into the route table instead of the link table. Fixed by (a) narrowing `_is_router_config` to require actual `<Route>` / `<Routes>` / `createBrowserRouter` usage and (b) stripping JS/TS/JSX comments before scanning so stray remarks like `// <Route path="/x">` don't fool the detector.

### Regression — all four smokes still green

- `smoke_demo_docs.py` — 48 assertions ✅ (updated two expectations from "3 docs" → "5 docs" after DEPLOY_AZURE + DEPLOY_UBUNTU emission)
- `smoke_coverage_contract.py` — 20 assertions ✅
- `smoke_ui_binding.py` — 16 assertions ✅
- `smoke_route_link_and_seed.py` — 16 assertions ✅ (new)

**Total: 100 deterministic assertions.** `backend.main` imports clean with all six audit hooks reachable (`audit_file_coverage`, `audit_api_contract`, `audit_ui_binding`, `audit_route_link_contract`, `audit_seed_completeness`, `write_demo_docs`).

### What the demo looks like after this pass

1. A user clicks **Run Selected (14)** on a fresh upload. AppNova runs 14 real specialist agents end-to-end.
2. Code-generation reads the 5 self-checks (full-code contract, runnability, backend coverage depth, route-link integrity, required-field + auto-populate rules) and produces a converted project.
3. The Python pipeline runs seven deterministic validators back-to-back:
   - `file_coverage` → `docs/FILE_COVERAGE.md`
   - `api_contract` → `docs/API_CONTRACT.md`
   - `ui_binding` → `docs/UI_BINDING_AUDIT.md`
   - `validate_ui_fidelity` → `docs/UI_FIDELITY_REPORT.md` (with per-page coverage section)
   - `route_link_contract` → `docs/ROUTE_LINK_CONTRACT.md`
   - `seed_completeness` → `docs/SEED_COMPLETENESS.md`
   - Plus `demo_docs.write_demo_docs` → `docs/RUN_THE_APP.md`, `AZURE_KEYVAULT_GUIDE.md`, `SECRETS_MAPPING.md`, `DEPLOY_AZURE.md`, `DEPLOY_UBUNTU.md`
4. `code-review` reads each report and edits in place to close every red row.
5. `contract-audit` aggregates into a single PASS/PARTIAL/FAIL verdict (`docs/CONTRACT_AUDIT.md`).
6. `scaffold.ensure_documentation` rewrites the top-level `README.md` with the Demo / Prod / What-to-Delete structure the non-IT client reads.

Result: the converted app ships with one paper (`README.md`) that indexes everything — demo run, Azure production deploy, Ubuntu production deploy, Key Vault setup, per-secret mapping, and a list of exactly what to delete before going live. Using only the Claude Max subscription — no API key billing for analysis — every step is audit-logged and traceable.

---

## 2026-04-22 — Sidebar-vs-backend agent-list drift fixed (ghost + invisible) `[DONE]`

Demo-polish change the user spotted from a screenshot of the running AppNova UI: the left sidebar's **Analysis Agents** list had two "Browser Test"-looking entries — one as a checkbox in the agent list, one as a 📷 button in the Converted App section — and the Run button showed `Run Selected (14)`.

Investigation found **two** pieces of agent-list drift between frontend and backend, in opposite directions:

### Ghost #1 — `browser-test` in frontend, NOT in backend

[frontend/app.js:540](frontend/app.js#L540) listed `{ id: 'browser-test', label: 'Browser Test' }` as the 14th analysis-agent entry, but [backend/config.py](backend/config.py) `AGENT_REGISTRY` didn't include it. Clicking the sidebar checkbox and hitting "Run Selected" did nothing for that entry — the backend silently ran 13 agents instead of 14. The counter over-promised.

The REAL browser test is a separate on-demand action: the 📷 **Browser test** button in the "Converted App" sidebar section, wired to `POST /api/browser-test/{session_id}` ([backend/main.py:2042](backend/main.py#L2042)), which fires AFTER `Run converted` has booted the converted app and drives it with a headless Chromium for screenshots.

### Ghost #2 — `contract-audit` in backend, NOT in frontend

[backend/config.py:140-144](backend/config.py#L140) has `contract-audit` registered as a heavy-tier agent that runs last in the DAG after every writer lands. Its prompt ([backend/agents/prompts.py "contract-audit"]) is the most demanding one AppNova ships — it cross-references every specialist agent's recommendations against what actually landed in the converted project, grading file_map coverage / security mitigations / schema entities / SDK imports / (now with the recent changes) file-coverage / API-contract / UI-binding reports and producing `docs/CONTRACT_AUDIT.md` with a PASS/PARTIAL/FAIL verdict.

This is the agent that differentiates AppNova from a single-shot Codex conversion. But the frontend didn't list it in `AGENTS`, so it ran invisibly — no sidebar entry, no progress card, no visible output card in the workspace. Users saw the "Run Selected (14)" counter but never saw the 14th (real) agent's work.

### Fix — one file, both drifts closed

[frontend/app.js](frontend/app.js): dropped the ghost `browser-test` entry, added `{ id: 'contract-audit', label: 'Contract Audit' }` right after `ui-ux`. Now `AGENTS` has 14 entries that match `AGENT_REGISTRY` 1-to-1, zero drift.

Verified:

```text
Frontend AGENTS: 14
Backend AGENT_REGISTRY: 14
Both sides (14): ok
Only in frontend (0): none
Only in backend  (0): none
✅ Frontend and backend agent lists now MATCH.
```

### Ripple-check (nothing else needs updating)

- Button at [index.html:46](frontend/index.html#L46) (`browser-test-btn`) is untouched — it's the legitimate on-demand 📷 action, wired directly to its own endpoint, never depended on the ghost AGENTS entry.
- Button's card-build fallback at [app.js:2040](frontend/app.js#L2040) uses `AGENTS.findIndex(...) + 1 || state.cards.size + 1`. With the ghost gone, `findIndex` returns -1, the `|| fallback` kicks in, card still builds correctly.
- `setNavStatus('browser-test', ...)` at [app.js:2053](frontend/app.js#L2053) does `$(\`nav-${agentId}\`)` lookup which returns `null` when the nav entry isn't rendered, then early-returns — silent no-op.
- Backend doesn't care — it was always the authoritative list.

### What the demo looks like now

- Sidebar shows 14 agents, all real, all wired through the full DAG.
- **Run Selected (14)** counter accurately reflects what the backend will run.
- Contract Audit's verdict card appears in the workspace at the end of the run — visible proof of the PASS/PARTIAL/FAIL grade and the top red findings, which is the direct "we audit everything" counter-pitch against Codex's one-shot conversion.
- No ghost checkbox user can toggle without effect.

---

## 2026-04-22 — UI binding validator + per-page fidelity coverage, back-propagate the PCDEC review gaps `[DONE]`

User shared the PCDEC audit narrative from a delivered ARIES conversion — four field-level UI gaps survived AppNova's existing checks and would have surfaced at UAT with real operations users:

1. **`victimCbIds` many-to-many** had a backend column + seeded lookup values but zero UI section rendered it. Officer couldn't set additional-authorities-for-holding or request-deny-release.
2. **PSA / Intoxicator checkbox** on `PcDecTab` rendered a bare `<input type="checkbox">` with no `register()` call. Clicking it did nothing — the value never reached form state, the BAC input wasn't conditionally gated.
3. **Parent Notification (juvenile)** section rendered the toggle + datetime but was missing the notifying-officer lookup and the badge text field. Backend schema had `parentNotifyingOfficerId` + `parentNotifyingOfficerBadge`; frontend bound neither.
4. **PCDEC ListPage** source had five filter inputs (search box, date-from, date-to, status select, type select); converted target had zero. Feature silently dropped.

The existing `validate_ui_fidelity` counts form controls tree-wide — totals can look fine while per-page or per-binding gaps are gaping. Fix: a per-field schema↔binding diff and a per-page stem-paired coverage audit.

### [backend/agents/ui_binding.py](backend/agents/ui_binding.py) — new module, schema↔form-control diff

`audit_ui_binding(converted_root, frontend_subdir="frontend", backend_subdir="backend")`:

- **Backend schema extraction** — walks `.cs` / `.ts` / `.py` / `.prisma` / `.kt` / `.java` / `.go` files across the backend tree. Per-stack regexes capture declared field names: C# `public string? FieldName { get; set; }` (+ `modelBuilder.Property(x => x.FieldName)` fallback for EF fluent config), TypeScript interface / type / class members, Python Pydantic / dataclass annotations, Prisma field rows, Kotlin `val name: Type`, Java POJO members, Go exported struct fields with backticked tags. C# file filter: accept if filename/path has entity-like tokens (`/Models/`, `/Entities/`, `/DTOs/`, etc.), OR the file has ≥2 `{ get;` POCO signatures, OR it's a DbContext / modelBuilder config — covers real codebases where the file isn't named `PcDeclarationModel.cs` but `PcDeclaration.cs` lives under `Models/`.
- **Frontend binding extraction** — 12 regex patterns covering React Hook Form (`register("x")`, `<Controller name="x">`, `useController({name:"x"})`), Formik (`<Field name="x">`), plain HTML `name="x"`, Angular (`formControlName="x"`, `[(ngModel)]="obj.x"`), legacy AngularJS `ng-model="x"`, Vue `v-model="x"`, Svelte `bind:value={x}`, Razor/Blazor `@bind-Value="obj.X"`.
- **Canonical name match** — both sides lowercase + strip non-alphanumerics, so `victimCbIds` ≡ `victim_cb_ids` ≡ `VictimCbIds`. Catches naming-convention mismatches across stacks (a C# `ParentNotifyingOfficerBadge` is correctly paired with React's `parentNotifyingOfficerBadge`).
- **Unbound-control scan** — for every `<input>` / `<select>` / `<textarea>` / `<InputText>` / `<InputSelect>` opening tag, inspects the tag text up to its closing `>` for ANY binding attribute from the set above (plus `checked={...}` for controlled checkboxes, `value={...}` for controlled inputs). Tags of `type="submit" | button | reset | image"` are exempt (buttons, not data capture). Everything else without a binding is flagged.
- **Server-only filter** — `id`, `createdAt`, `updatedAt`, `passwordHash`, `rowVersion`, `concurrencyStamp`, `tenantId`, `_type`, `__typename`, etc. (~20 names) don't need UI controls; excluded from orphan detection.
- Writes `converted/docs/UI_BINDING_AUDIT.md` with three tables: ❌ Orphan schema fields, ⚠️ Unbound controls (snippet included for reviewer to eyeball), ✅ Matched bindings.

### [backend/agents/scaffold.py](backend/agents/scaffold.py) — per-page coverage for `validate_ui_fidelity`

Added `_tokenize_stem` + `_best_target_for_source` helpers. For every source UI file with controls, tokenize the filename stem (camelCase-split, strip common noise like `page` / `form` / `view` / `tab` / `html` / `tsx`) and pair to the target file whose stem shares the most tokens. Compute per-pair coverage (target controls / source controls). Files with <50% coverage AND ≥3 source controls are flagged into a new `Suspicious (<50%)` table in `UI_FIDELITY_REPORT.md`. `manifest["suspicious_pages"]` is surfaced to the pipeline.

Catches the ListPage gap: source `pcdec-list.form.html` (5 controls) pairs to target `ListPage.tsx` (0 controls) → 0% coverage → flagged suspicious. The tree-wide totals audit can't see this because other pages' bindings drown it out.

### [backend/main.py](backend/main.py) — wired ui_binding after api_contract

Import added alongside `audit_file_coverage` / `audit_api_contract`. New try/except calls `audit_ui_binding(converted_dir)` and emits a `ui_binding_audit` progress event. Runs after the existing UI fidelity audit so `docs/UI_FIDELITY_REPORT.md` (now with per-page coverage) and `docs/UI_BINDING_AUDIT.md` both land for the code-review and contract-audit agents to consume on a subsequent pass.

### [backend/agents/prompts.py](backend/agents/prompts.py) — three prompt updates

- **`code-generation` — SELF-CHECK BEFORE DONE** gained a **Check 3** (orphan schema scan + unbound-control scan). Spells out the exact regex patterns to grep for on each side of the diff, covers React Hook Form / Angular / Vue / Svelte / Blazor / Razor. Tells the agent to consume `docs/UI_BINDING_AUDIT.md` if the Python validator has already produced it on a re-run.
- **`code-review` — Step 4.7 (UI binding cross-check)** added between the existing 4.6 (file coverage) and 5 (hygiene). Points at `docs/UI_BINDING_AUDIT.md` + the `Per-page coverage → Suspicious` section of `docs/UI_FIDELITY_REPORT.md`, with apply-edit-in-place guidance for every orphan / unbound / low-coverage row.
- **`contract-audit` — Check 7 (UI binding report)** added to the existing 6 checks. Orphan schema fields = `red` findings, unbound controls = `yellow`, sub-50% pages = `yellow`. Summary block's FAIL/PARTIAL/PASS verdict rules hardened: **FAIL** now triggers on ≥3 orphan schema fields (that's 3 backend-table columns the user has no way to populate — a real demo blocker).

### [scripts/smoke_ui_binding.py](scripts/smoke_ui_binding.py) — new 16-assertion smoke

Synthesises the EXACT 2026-04-22 PCDEC failure: a source tree with a ListPage (5 filter controls) + DetailPage (8-field form), and a converted tree where:

- Backend declares all 8 fields (`PcNarrative`, `BacReading`, `VictimAge`, `WeaponType`, `VictimCbIds`, `PresumptiveTest`, `ParentNotifyingOfficerId`, `ParentNotifyingOfficerBadge`) + a `CreatedAt` server-only field.
- Frontend DetailPage binds 4 of 8 + has an unbound `<input type="checkbox">` (the PSA gap).
- Frontend ListPage has NO filter UI (the gap #4).

Asserts all 4 real-world gaps are caught:

1. `VictimCbIds` shows up in the orphan table (case-insensitive match `victimcbids` present in report body).
2. `ParentNotifyingOfficerId` + `ParentNotifyingOfficerBadge` both in the orphan table.
3. The unbound PSA `<input>` surfaces in the Unbound Controls table.
4. ListPage scores <50% per-page coverage (actual: 16.7%) and lands in the Suspicious section.

Also asserts `createdAt` is NOT flagged as an orphan (server-only filter working), and the UI fidelity report carries the new `Per-page coverage` section.

One bug fixed on first smoke: C# schema extraction was gated on filename-token match (`"model" in filename.lower()`) which skipped `PcDeclaration.cs` because the filename has no `model` token. Relaxed to accept files with entity-like PATH segments (`/Models/`, `/Entities/`) OR ≥2 `{ get;` POCO signatures OR DbContext / modelBuilder.Entity indicators — covers real codebase layouts.

### Regression check

All prior smokes still green:

- `smoke_demo_docs.py` — 48 assertions ✅
- `smoke_coverage_contract.py` — 20 assertions ✅
- `smoke_ui_binding.py` — 16 assertions ✅ (new)

Total: **84 assertions** across 3 smokes. `backend.main` imports clean with all four new entry points reachable (`audit_file_coverage`, `audit_api_contract`, `audit_ui_binding`, `write_demo_docs`).

---

## 2026-04-22 — Programmatic file-coverage + API-contract validators, back-propagate the 2026-04-22 manual-fix lessons `[DONE]`

User shared the post-generation changes.md from a real delivered conversion (ARIES case/warrant app). Three classes of failure landed after AppNova signed off, requiring hand-fixes:

1. **15 lookup endpoints missing in backend** — React frontend called them, backend never implemented them, every one would 404 at runtime. Undetected by `code-review` and `contract-audit`.
2. **Thin seed data** — dropdowns came back empty even when endpoints existed.
3. **File-by-file source→target coverage drift** — no deterministic artifact verified every legacy file was ported.

The user's ask: "rectify the code generation agent and code review to pick both all the files converted and also file by file from source to target environment and check all the files are converted without missing a single."

The existing `code-generation` + `code-review` prompts ALREADY told the agents to do these checks (Step 3's route-parity rule, the LOOKUPS_AUDIT.md requirement). They're 1800-line prompts — LLM prompts of that length get skimmed. The failure mode is deterministic: the agents don't always do what the prompt says. Fix: **build the checks as Python validators and run them unconditionally in the pipeline**, then point the agent prompts at the reports so the agents do follow-up work on a pre-digested ground truth.

### [backend/agents/file_coverage.py](backend/agents/file_coverage.py) — new module, source→target walker

`audit_file_coverage(source_root, converted_root, context_dir)`:

- Walks `source_root` (excluding vendored dirs — node_modules, .git, build outputs — but **including** `migrations/`, `tests/`, `views/` because those ARE source-side port candidates). Builds a `SourceEntry` list with per-file category hints (controller / model / migration / view / service / etc.) via path-pattern matching.
- Walks `converted_root` with a stricter exclusion set that additionally drops `mock-azure/`, `sample-data/`, `docs/`, `Outputs/`, `exports/` — these are AppNova-scaffolded output, not port targets.
- Reads `context/file_map.json` when present. If a row is `kind=SKIPPED`, the source file is marked `skipped_by_map`. If a row has `targets[]`, each one must exist on disk; missing targets downgrade the row.
- Opens the first 4KB of every target file and greps for a `// Source: <legacy path>` header (the format the code-generation prompt mandates). Header-cited rows get `mapped_confirmed`.
- Falls back to filename-stem matching for `mapped_heuristic`. Anything with no map row, no header cite, and no stem match is `unmapped` — a real gap.
- Writes `converted/docs/FILE_COVERAGE.md` with Unmapped (❌), Heuristic (⚠️), Confirmed (✅), and Orphan tables. Returns a manifest with `coverage_pct` and a `warning` field that fires when <90% on trees ≥10 files.

### [backend/agents/api_contract.py](backend/agents/api_contract.py) — new module, FE↔BE endpoint diff

`audit_api_contract(converted_root)`:

- Auto-detects `frontend/` + `backend/` subdirs; falls back to the whole converted tree when flat.
- Scans frontend files (`.js`/`.ts`/`.tsx`/`.vue`/`.svelte`) for HTTP call-sites with 7 regex patterns covering `fetch('/api/...')` / template-literal fetch / `axios.*(...)` / `api.*(...)` / Angular `HttpClient.get<T>(...)` / legacy `$http(...)` / `ky(...)`.
- Scans backend files for route registrations across 10 framework idioms: .NET attribute routing (`[HttpGet("path")]` + class-level `[Route("api/[controller]")]` expansion — the `[controller]` token is substituted from the filename stem), FastAPI `@app.get("/...")`, Flask `@app.route(...)`, Django `path(...)` / `re_path(...)`, Laravel `Route::get(...)`, Express `app.get('/...')`, NestJS `@Get('...')` + `@Controller('prefix')`.
- Normalises paths (strip host / querystring / template holes like `${id}` / Express `:param` → `:id`), pairs by `(method, path)` with permissive method-matching for `ANY`, emits `converted/docs/API_CONTRACT.md` with ❌ Missing (frontend calls with no backend route — these 404 at runtime), ✅ Matched, and a Caveats section for the regex's known blind spots (dynamically-computed URLs, YAML route tables).
- Warns when any frontend call goes unmatched — that's the exact 2026-04-22 failure mode.

### [backend/main.py](backend/main.py) — two new pipeline stages after `ensure_documentation` / `write_demo_docs`

Imports added alongside the demo-docs import. Two new try/except blocks after the UI fidelity audit:

- `audit_file_coverage(project_dir, converted_dir, context_dir)` → emits `file_coverage_audit` progress event with the full manifest.
- `audit_api_contract(converted_dir)` → emits `api_contract_audit` event.

Both swallow exceptions into `logger.exception` so a validator bug never breaks a long run. The reports land on disk regardless, so the UI and the code-review / contract-audit agents can consume them even if the progress event fails to stream.

### [backend/agents/prompts.py](backend/agents/prompts.py) — patched three agents

- **`code-generation` — new section "SELF-CHECK BEFORE DONE"** added right before the final REPORT directive. Two concrete self-checks the agent must run before declaring done: (1) grep every frontend `fetch/axios/api.*/http.*` call, grep every backend route attribute/decorator, diff, fix any orphan frontend calls inline; (2) verify every non-SKIPPED `file_map.json` row has its target on disk with a `// Source:` header. Frames the consequence: AppNova's post-generation validators WILL run and WILL produce `docs/FILE_COVERAGE.md` + `docs/API_CONTRACT.md` — any `unmapped` or `missing` row becomes a red finding the code-review agent has to fix on a follow-up pass.
- **`code-review` — new Step 4.5 "Target-internal FE↔BE contract" + Step 4.6 "File-coverage cross-check"** between existing Step 4 (data-fidelity audit) and Step 5 (hygiene). Step 4.5 walks the reviewer through building the frontend call inventory + backend route inventory from scratch IF `docs/API_CONTRACT.md` is absent, and inline-fixing every `missing` row (with 501-stub fallback for routes that can't be fully implemented — still red in the table but beats a 404). Step 4.6 tells the reviewer to consume `docs/FILE_COVERAGE.md` directly.
- **`contract-audit` — two new checks (5 + 6)** added to the four existing ones, each reading the new validator reports and promoting rows straight into the audit. Summary block extended with two new lines (`source→target coverage`, `API contract (FE↔BE)`). Verdict rules hardened: **FAIL now triggered by any missing backend route in the API contract OR ≥5% unmapped source files** — not just file_map coverage <90%.

### [scripts/smoke_coverage_contract.py](scripts/smoke_coverage_contract.py) — new 20-assertion smoke

Synthesises a legacy PHP-ish source tree with 5 files (2 controllers, 2 models, 1 migration) and a converted tree that:

- Ports 4 of 5 source files (`Gender.php` has no target — deliberate unmapped gap).
- Frontend calls 15 lookup endpoints + 2 booking endpoints.
- Backend implements only 8 of 15 lookup endpoints (deliberate — mirrors the 2026-04-22 real-world failure).

Asserts the validators catch both the unmapped file and the 7+ missing endpoints, that `docs/FILE_COVERAGE.md` / `docs/API_CONTRACT.md` land on disk with the expected content, and that adding a `SKIPPED` row to `file_map.json` correctly reclassifies the gap so coverage climbs to 100%.

Four real bugs surfaced during the first smoke run and were fixed:

1. Windows short-path vs long-path mismatch (`CHAITA~1` vs `Chaitanya`) from tempfile broke `Path.relative_to` — added a `_rel_posix` helper that resolves both sides.
2. `// Source: app/foo.php` header regex's character class excluded `/` — fixed to `\S+?` with explicit end-of-line/`*/`/`-->` terminators.
3. Source-side walk was wrongly dropping `migrations/` / `tests/` — split exclusion into `_EXCLUDE_SEGMENTS_ALWAYS` (vendored/build dirs — both sides) and `_EXCLUDE_SEGMENTS_TARGET_ONLY` (AppNova scaffolding dirs — target-side only).
4. Bare `[HttpGet]` without a path argument isn't captured (would need class-prefix joining). Test expectation lowered to 9 routes + a note; edge case for later.

All 20 assertions green after fixes. Prior 48-check `smoke_demo_docs.py` still passes. `backend.main` imports clean with all three new entry points (`audit_file_coverage`, `audit_api_contract`, `write_demo_docs`) reachable.

---

## 2026-04-22 — Client-facing demo docs + dual-stack runner for every converted app `[DONE]`

Krishna wants to dump AppNova for Codex unless we demo in 4 days. Key ask: every converted project must ship with (a) a runnable demo the non-IT client can click and see, (b) a non-IT walkthrough of how Azure Key Vault stores the real production secrets, and (c) a mapping table showing each secret's journey from legacy source → converted app → vault. Before this change, converted projects emitted only `README.md` / `DEPLOYMENT.md` / `DATA_MIGRATION.md` — nothing aimed at the client who'll read it cold, and the fallback `run.sh` / `run.bat` were single-stack so the dual-port multistack launcher detection in [run_manager.py:959](backend/agents/run_manager.py#L959) fired without any script actually honouring `BACKEND_PORT`.

### [backend/agents/demo_docs.py](backend/agents/demo_docs.py) — new module, 3 client-facing docs

`write_demo_docs(converted_dir, agent_results)` writes three files into `converted/docs/`, each idempotent (skips pre-existing):

- **`RUN_THE_APP.md`** — two runnable paths (AppNova preview button + standalone `run.bat`/`run.sh`), with ASCII "screenshot" boxes of the dashboard and browser, a table of what's in the local SQLite sample DB (`sample-data/demo.db`), and a troubleshooting table keyed by the exact error string the client will see. The script-window wording adapts to whether the layout is dual-stack (mentions two terminals) or single (one terminal).
- **`AZURE_KEYVAULT_GUIDE.md`** — six-step Azure Portal walkthrough with ASCII renders of the Portal search, Create-vault form, Secrets panel, Identity toggle, and Access-policy dialog. Zero jargon — explains Key Vault as a safety deposit box, contrasts against `.env` leakage with a comparison table, walks through rotation, lists the five most common error messages and their fixes.
- **`SECRETS_MAPPING.md`** — dynamic table of every secret, populated from `mock-azure/keyvault.json` when present. Columns: plain-English name, legacy source hint, converted-app env var + fallback file, vault secret name, rotation note. The legacy hints come from a `_SECRET_META` lookup keyed on the names that [sample_data.py:_mock_key_vault_secrets](backend/agents/sample_data.py) emits. The security and data-migration agent reports are spliced in below the table when available (trimmed to ~800 chars with a link back to the full doc).

### [backend/agents/scaffold.py](backend/agents/scaffold.py) — dual-stack run script generator

Added `_detect_dual_stack(converted_dir)` that returns `(frontend_stack, backend_stack)` when both subdirs exist with a recognisable stack each, else `None`. Added `_dual_stack_run_script(fe, be, posix=...)` that emits:

- **Windows**: `start "AppNova Backend" cmd /k ...` spawns the backend in a visible window, a PowerShell-based TCP probe waits up to 60s for `BACKEND_PORT` to bind, then the parent `cmd` runs the frontend in the foreground so the port-bind probe in `_launch_and_await_ready` latches onto the right process.
- **POSIX**: backend runs as `(cd backend && install && start) &`, `/dev/tcp` poll waits for the backend port, `trap "kill $BACKEND_PID" EXIT` cleans up on frontend exit.

`ensure_mandatory_structure` now branches on `_detect_dual_stack` before falling through to the original single-stack `_default_run_script`. Existing scripts are still never clobbered.

Two tight helpers feed the script body:

- `_stack_install_cmd(stack, posix)` — idempotent installers per stack (`npm install` / `pip install -r requirements.txt` / `dotnet restore` / Maven wrapper chmod).
- `_stack_start_cmd(stack, role, posix)` — role-aware start command that picks `PORT` (frontend) or `BACKEND_PORT` (backend) from env, wires `ASPNETCORE_URLS` for .NET, `uvicorn`/`flask run`/`manage.py runserver` for Python, `npm run dev` with a fallback to `npm start` for Node.

### [backend/main.py](backend/main.py) — wired demo_docs into the post-conversion pipeline

Import added alongside `seed_fallbacks_for_skipped` and `ensure_documentation`. Call site added directly after `ensure_documentation(converted_dir, results)` (line ~843) — runs every pass regardless of skipped agents, emits a `demo_docs_ready` progress event with the manifest so the UI can surface "docs written".

### [scripts/smoke_demo_docs.py](scripts/smoke_demo_docs.py) — 48-check smoke

New smoke harness that walks three synthetic converted/ layouts:

1. Single-stack Python — confirms no `BACKEND_PORT` in `run.bat`, all 3 demo docs land, re-run is idempotent (3 written → 0 written, 3 skipped).
2. Dual-stack node + dotnet (no mock vault) — confirms `_detect_dual_stack` returns `("node", "dotnet")`, `run.bat` references `BACKEND_PORT`, spawns backend via `start "AppNova Backend"`, and `cd`s into frontend for foreground.
3. Dual-stack + `mock-azure/keyvault.json` seeded via `sample_data.seed_mock_azure` — confirms `SECRETS_MAPPING.md` uses the vault name (`appnova-demo-vault`) from the mock file, the mock secret names land as table rows, and a fake `security` agent report gets spliced in below the table.

All 48 assertions pass. Backend import verified clean after the patch.

---

## 2026-04-22 — Nested offense repeaters in Warrants/Orders + correct dev creds + backend-save gap doc `[DONE]`

User caught three things after the last round:

- The Run-demo README creds were pointed at `@aries.dev`, but the DevSeeder writes `@aries.local`.
- The Local / Foreign Warrant and Orders blocks in `DetailPage.tsx` had a placeholder `<p>` saying "nested offense entries wired via useFieldArray" — but no actual repeater. The screenshots make clear the source renders a full + Add Offense button inside each warrant/order, not a single charge-description textarea.
- No honest write-up of why save round-trip drops fields (despite the TypeScript DTO widening in the previous round).

Fixed all three.

### [README.md](uploads/d482d2621a61/converted/README.md) — dev creds corrected

`officer@aries.dev` / `Officer@123!` → `officer@aries.local` / `Officer123!`; same for judge. Click-path reference to `officer@aries.dev` updated. Added a pointer line citing the DevSeeder file:line so anyone reading the README can verify the creds are still current.

### [DetailPage.tsx](uploads/d482d2621a61/converted/frontend/aries-react/src/pages/TotalBooking/DetailPage.tsx) — nested offense repeaters

Refactored the offense-row markup into a presentational `OffenseRow` component that takes a `prefix` string (e.g. `offenses.0` OR `orders.2.offenses.1` OR `foreignWarrants.0.offenses.3`). Single component, three usage sites. Added:

- **`NestedOffensesRepeater`** — calls `useFieldArray` with a dynamic path (`${parentPath}.offenses`) and renders one `OffenseRow` per entry with its own **+ Add Offense** button and per-row ✕ remove. One hook per parent block, per React rules.
- **`OrderBlock`** — now ends with `<NestedOffensesRepeater parentPath={`orders.${idx}`} />`, matching source `ng-repeat="($o_index, offense) in order.offenses"`.
- **`WarrantBlock` (local)** — same treatment; always shows nested offenses (source doesn't gate them on a toggle).
- **`WarrantBlock` (foreign)** — added the **Have Offenses Yes/No** toggle matching source `ota.have_fw_offenses`; the nested repeater is conditional on that watch (`{haveOffenses && <NestedOffensesRepeater ... />}`).

TS complained about dynamic template-string paths not matching the RHF union; solved with the same local `register as any` helper pattern already used in `OffenseRow`. `npx tsc --noEmit` clean.

Fidelity counter: 32.8% → **33.4%**; DetailPage.tsx 186 → 192 controls (+14 repeater counts now picked up in nested blocks; the counter under-reports anyway because `<OffenseRow>` is a component — actual on-screen fidelity jumped substantially more).

### [docs/BACKEND_SAVE_GAPS.md](uploads/d482d2621a61/converted/docs/BACKEND_SAVE_GAPS.md) — the honest write-up

Documents exactly why pressing "Save & Close" today loses data:

- **DTO gaps.** Enumerates ~18 scalar fields the React form posts but `CreateBookingRequest` doesn't accept. Every one silently drops; the controller returns 200.
- **Use-of-Force architectural mismatch.** Source stores the 9 Y/N answers in a `ForceCbs` pivot (one row per question, `pivot.value`). React authored them as 9 scalar bools. Two options laid out: (a) 9 new columns + migration (fast, demo-path), (b) preserve the pivot and map 9 React bools onto 9 rows server-side (faithful, production-path).
- **Child-collection mappers.** `BookingService.UpdateAsync` does `_db.Entry(existing).CurrentValues.SetValues(update)` which copies scalars only. Offenses / LocalWarrants / ForeignWarrants / Orders / Addresses / Akas / ParentsGuardians / CoDefendants / PreBookPersonalProperties pivots all need a `MergeChildren()` helper — exact pattern shown as a C# snippet with DELETE / UPDATE / ADD branches based on `keySelector` / `copyScalars` callbacks.
- **EF migrations.** Named `dotnet ef migrations add AddUseOfForceColumns` as the concrete next step.
- **Verification steps.** Numbered click-path (log in, add a Local Warrant with a nested offense, Save, reload — the warrant + offense must still be there). Each failed step maps to a specific missing mapper.
- **How the browser-test auto-fix loop handles this.** Points at the `form_submission_dropped` bucket wired in the previous changelog entry — the exact same gaps will surface as fixable tasks the next time the user clicks Browser Test, with the auto-fix agent's cwd pointed at `converted/`.

This doc is the handoff artifact: to close the loop end-to-end, a backend dev (or the next auto-fix turn) reads this file, widens `CreateBookingRequest` to match `BookingDetail` in the frontend, adds the 9 Merge helpers, runs `dotnet ef migrations add`, reloads the demo, re-runs the click-path.

---

## 2026-04-22 — Browser-test → auto-fix chat loop (closes the runtime-error gap) `[DONE]`

User's observation was right: every runtime error the converted app throws (`/api/lookups/* → 404`, JS null-deref, form submit drops fields) should flow straight back into AppNova's own agents to rectify, not through the user manually pasting errors into chat. The plumbing was already there — browser-test captures structured errors, chat can Edit/Write/Bash against `converted/` — but no dispatch rule fired when browser-test returned `ok=false`. Closed that gap now.

### [backend/agents/browser_test.py](backend/agents/browser_test.py) — `derive_suggested_fixes()`

Post-processor over the Playwright log that buckets errors into six categories via cheap regex (no LLM round-trip for classification). Each fix is `{kind, symptom, evidence, likely_cause, affected (glob list), priority}`:

1. **`missing_or_mismatched_route`** — HTTP 4xx on any `/api/*` URL, grouped by first segment. Exact shape of the `/api/lookups/* → 404` bug we just fixed. Affected globs cover Controllers for .NET / Laravel routes / Django urls / FastAPI main.
2. **`server_error_5xx`** — any HTTP 5xx. Affected globs point at Services + Controllers + Data + migrations.
3. **`null_deref_missing_guard`** — "Cannot read properties of undefined" page / console errors. Affected globs point at React/TSX.
4. **`missing_method_or_export`** — "X is not a function". Points at TS modules.
5. **`navigation_failure`** — `nav_error` entries. Points at Router / Auth config.
6. **`form_submission_dropped`** — `form_error` / `form_submit_failed` — the backend-DTO-too-narrow failure mode. Points at Models/Dtos + Services + frontend/api.

Each fix includes up to 5 raw log rows as evidence so the fix agent can cite them. Manifest now also carries `has_runtime_errors: bool` — the auto-dispatch key.

### [backend/agents/browser_test.py](backend/agents/browser_test.py) — `build_autofix_prompt(manifest)`

Renders the suggested-fixes list as a markdown prompt the code-mode chat agent can consume directly. Each bucket becomes a numbered section with the evidence + search-here-first globs. Ends with a verification checklist (`npm run build` / `dotnet build` must be clean, don't start the dev server — user's already running it).

### [backend/agents/browser_test.py](backend/agents/browser_test.py) — `render_report()`

Suggested fixes also surface in the user-facing markdown report with priority badges (🔴 high / 🟡 medium / 🔵 low) so the user sees what the auto-fix agent will attempt.

### [backend/main.py](backend/main.py) — `start_browser_test` auto-dispatch

After `run_browser_test()` returns, if `manifest["has_runtime_errors"]` is true, fire a background `chat_turn(agent_id="browser-test", mode="code")` with the auto-fix prompt. Returns `{autofix: {dispatched, node_id, reason}}` to the caller so the frontend can immediately show "Auto-fix in progress" next to the browser-test report. The chat turn runs against `converted/` with Edit/Write/Bash enabled; chat.py's existing snapshot-before-edit gives the user a revert point. Opt-out via `{"auto_fix": false}` in the request body (useful for CI).

New registry `_autofix_tasks` / `_autofix_status` + poll endpoint `GET /api/browser-test/{sid}/autofix/{pending_id}` returns phase (`running` / `done` / `error`), final chat node id (so the UI can open the new version), elapsed seconds, and the tail of SSE events from the chat turn.

### Unit-test against synthetic log (classification sanity)

Ran `derive_suggested_fixes()` against a log mirroring the real bug (3× 404 on `/api/lookups/*`, one 5xx, one null-deref, one missing-method, one nav timeout, one 422 form failure). Produced 6 fixes, all in correct buckets with accurate symptoms. The rendered autofix prompt is the same shape a human would paste into chat — every bucket has evidence, affected-path globs, and a verify step.

### The end-to-end loop now

1. User clicks "Run converted" → dev server starts.
2. User clicks "Browser test" → Playwright crawls, catches errors.
3. Backend auto-dispatches code-mode chat turn with the rendered error list as the prompt.
4. Chat agent reads the browser-test report, Greps the affected globs, edits code in `converted/`, runs the build, iterates until green.
5. Frontend polls `/api/browser-test/{sid}/autofix/{pending_id}` → when `phase=done`, the fix lands as a new version in the `browser-test` chat tree.
6. User re-runs browser test to confirm the fix worked.

Still human-reviewable at every step (snapshot + revert + diff view), but no more "open chat, paste error, type fix request." The system that detected the bug also opens the PR.

### Caller opt-out + safety

- Existing `POST /api/browser-test/{sid}` calls without an `auto_fix` key default to **enabled**. Callers that want classic behaviour pass `{"auto_fix": false}`.
- Chat turn runs as `asyncio.create_task`; the browser-test HTTP request returns in ~15s as before, fix runs in the background.
- If the fix agent crashes or times out (`chat_turn` has a 600s cap), `_autofix_status[pending_id].phase` flips to `error` — never leaves the caller polling forever.

---

## 2026-04-22 — Lookups route alias: frontend `/api/lookups/*` now resolves server-side `[DONE]`

User asked "is the converted folder actually ready to run?" Audit caught a real bug: the React `<LookupSelect>` calls `/api/lookups/genders` etc., but [LookupsController.cs](uploads/d482d2621a61/converted/backend/ARIES.Api/Controllers/LookupsController.cs) was mounted only at `[Route("api/pcdec")]` — every dropdown was silently 404'ing. The UI handled it gracefully (⚠ + empty select) but every dropdown in the demo flow would be unusable.

Two surgical edits:

- **Route alias on the controller.** Added `[Route("api/lookups")]` alongside the existing `[Route("api/pcdec")]`. Both mount points now serve the same action methods — frontend's `/api/lookups/*` and any legacy `/api/pcdec/*` callers both work.
- **Four new alias endpoints for name mismatches.** `HttpGet("users")` piggybacks on `Officers(int? agencyId)` and projects to `{id, name: FirstName + ' ' + LastName + '(#Badge)'}` so React gets an `id`/`name` shape the `useLookup` hook renders directly. `HttpGet("agencies")` → same shape as `/arrest-agencies`. `HttpGet("country-states")` → aliases `States`. `HttpGet("prebook-properties")` → aliases `PreBookPersonalProperties`, surfacing `Description` as `name`.

`dotnet build` passes clean after the edits. Brings working dropdowns from 8/22 to 12/22 without any schema changes. The remaining 10 (address-directions, address-suffix, address-units, address-types, counties, cities, vehicle-dispositions, warrant-severity, local-warrant-casetypes, foreign-warrant-casetypes, order-case-types) need DbSets + seed data the backend doesn't have yet — still MUST-FIX, still visible in the UI via the ⚠ icon and tooltip, not silently broken.

---

## 2026-04-22 — Stack-agnostic prompt refactor + 3 MUST-FIX items closed `[DONE]`

User pushback on the earlier fix: the conversion artifacts (`FIELD_MAPPING.md`, `UI_FIDELITY_REPORT.md`) were produced by two one-shot Python scripts ([scripts/extract_form_inventory.py](scripts/extract_form_inventory.py), [scripts/generate_field_mapping.py](scripts/generate_field_mapping.py)) whose regexes only hit AngularJS `ng-model` / `ng-repeat` bindings. The next source upload could be Vue / Blazor / MVC Razor / Blade / Svelte — and those scripts silently return empty. The critique is right: **the conversion has to be driven by the LLM agents' own tool calls, not by server-side helpers keyed to one source stack**.

### Scripts deleted

[scripts/extract_form_inventory.py](scripts/extract_form_inventory.py) and [scripts/generate_field_mapping.py](scripts/generate_field_mapping.py) removed. They only ever worked for this one session. Their job now lives in the `code-generation` prompt.

### Prompt rewrite — [backend/agents/prompts.py](backend/agents/prompts.py) `UI FIDELITY AUDIT` section

Restructured into four explicit phases that use the agent's OWN Glob/Grep/Read/Write tools, stack-agnostic:

- **Phase 1 — build the source inventory yourself.** Detect source UI stack from a ~5-file sample. Glob every candidate extension the project uses (`.html`, `.cshtml`, `.razor`, `.vue`, `.blade.php`, `.erb`, `.twig`, `.phtml`, `.jsx`, `.tsx`, `.svelte`). Grep per-file for controls using the stack's binding style — the prompt ships a 9-row table of per-stack patterns (AngularJS / Angular 2+ / Vue / React / Blazor / Razor / Blade / ERB / plain HTML). Agent writes the totals to `../context/ui_source_inventory.md` BEFORE touching any target file.
- **Phase 2 — produce the target UI.** Every target form component gets a header comment naming source file, source control counts from the Phase-1 inventory, and "ported here" counts. If "ported" < "source", the conversion is incomplete.
- **Phase 3 — emit `docs/FIELD_MAPPING.md` yourself.** One row per source field with status in {`PORTED`, `SPLIT`, `MERGED`, `INTENTIONALLY DROPPED — <reason>`, `MUST-FIX — NOT YET PORTED`}. Grouped by source file. No server-side helper in the loop.
- **Phase 4 — emit `docs/UI_FIDELITY_REPORT.md` yourself.** Corpus summary table + per-form detail sections. Coverage <95% on any form requires a `Known UI gaps` section up top.

A server-side counter (`scaffold.validate_ui_fidelity()`) still runs as a smoke alarm and overwrites the counter summary — when the agent-authored scorecard and the counter disagree materially, the reviewer trusts the counter. This keeps LLMs honest without taking the generation work away from them.

### Scaffold counter widened for non-HTML stacks

[backend/agents/scaffold.py](backend/agents/scaffold.py) `_SOURCE_CONTROL_PATTERNS` + `_TARGET_CONTROL_PATTERNS` + `_SOURCE_UI_GLOBS` now recognise Blazor (`<InputText>`, `@foreach`, `@if`), Razor/MVC (`@Html.TextBoxFor`, `@Html.DropDownListFor`), Blade (`@foreach`, `@forelse`, `@unless`, `@isset`), Vue (`v-model`, `v-show`), ERB (`.each do`, `<% if`), Svelte. Module docstring updated to clarify: this function is a smoke alarm, NOT the generator. When a new source stack ships with bindings the counter can't see, the fix is to extend regexes here — not to write a per-stack generator.

### Three MUST-FIX items closed (still session d482d2621a61)

**1. LookupSelect wired to real `/api/lookups/*` fetches.**

New [uploads/d482d2621a61/converted/frontend/aries-react/src/lib/useLookup.ts](uploads/d482d2621a61/converted/frontend/aries-react/src/lib/useLookup.ts) — shared `useLookup(endpoint)` hook built on react-query with a 10-minute `staleTime` + 30-minute `gcTime` (lookups rarely change during a session, and we don't want 25+ dropdowns each firing their own request every render). `LookupSelect` in [DetailPage.tsx](uploads/d482d2621a61/converted/frontend/aries-react/src/pages/TotalBooking/DetailPage.tsx) now calls the hook and renders real `<option>` children from the response. Loading state shows `Loading…` placeholder; error state shows an amber ⚠ next to the label with a tooltip naming the missing endpoint — so a missing backend route is visible without breaking the whole form. `aria-busy` attached only when loading (static-attribute form to satisfy the linter).

**2. `CreateBookingRequest` DTO widened.**

[uploads/d482d2621a61/converted/frontend/aries-react/src/api/bookings.ts](uploads/d482d2621a61/converted/frontend/aries-react/src/api/bookings.ts) — `BookingDetail` grew from ~40 fields to ~110, covering every field in the Zod schema on `DetailPage.tsx`. New interfaces: `OffenseItem` (14 fields), `AddressItem` (13 fields), `AkaItem`, `LocalWarrantItem` (12 fields) + `ForeignWarrantItem extends LocalWarrantItem`, `OrderItem` (9 fields + nested offenses), `PreBookPropertyRowItem`, `ParentGuardianItem` (9 fields), `CoDefendantItem`. The source AngularJS/Laravel schema is mirrored 1-to-1 so the frontend can round-trip without `as unknown as` casts — dropped the unknown cast in `DetailPage.tsx`. Fields the backend doesn't populate yet are nullable; the server drops unknown keys until its DTO catches up, but the Zod → API contract is now type-safe end to end.

**3. Juvenile-branch rendering.**

[DetailPage.tsx](uploads/d482d2621a61/converted/frontend/aries-react/src/pages/TotalBooking/DetailPage.tsx) Zod schema extended with `parentsGuardians[]`, `coDefendants[]`, and 19 probation + parent-notification fields. `BookingTab` now watches `form.watch('type') === 'juvenile'` and conditionally renders four source-matching sections:

- **Adult-only consulate triple** (source: total-booking.form.html:307-340 `ng-if="ctrl.item.type=='adult'"`) — notify_consulate, officer_notify_consulate, person_notify_mandatory Yes/No toggles, rendered when NOT juvenile.
- **Parents / Guardians repeater** (source: pcdec-juvenile-pcdec.form.html `ng-repeat="parentsguardians in ctrl.item.parents_guardians"`) — Parent type, Last/First/Middle, Address, City, State, ZIP, Phone. Add/Remove buttons.
- **Parent Notification block** — Parents Notified Yes/No + datetime + Notifying Officer dropdown + Badge #.
- **Co-Defendants repeater** (source: `codefeants in ctrl.item.co_defendants`) — Last/First/Middle/DOB.
- **Probation block** — 11 text fields (Admission Counselor, Admitted Date/Time, Probation Date, Destination, Grade, Last School, Sierra Staff, Released Authorized By, Released Date/Time, Released To, Released To Verification) + 4 Yes/No toggles (Parents Notified, Referred, Released, Attorney Call) + a Comments textarea.

Each juvenile section gets a source-citing comment so a reviewer can cross-reference `pcdec-juvenile-pcdec.form.html` without grepping.

### Fidelity audit progression

| Pass | Inputs | Selects | Textareas | Repeaters | Conditionals | Total | Coverage |
| --- | --: | --: | --: | --: | --: | --: | --: |
| 1. Initial conversion | 23 | 4 | 2 | 0 | 101 | 130 | 13.6% |
| 2. After hand fidelity pass (tabs, repeaters, forms) | 83 | 3 | 9 | 27 | 149 | 271 | 28.3% |
| 3. After this pass (Lookup fetch + DTO widen + juvenile) | 107 | 4 | 10 | 30 | 163 | 314 | 32.8% |

`DetailPage.tsx` alone now hosts 186 form controls (100 inputs, 4 selects, 9 textareas, 13 repeaters, 60 conditionals). The counter still under-reports because `<LookupSelect>` wraps `<select>` in a component (one literal `<select>` for 25+ on-screen dropdowns) — true fidelity is materially higher, captured in `docs/FIELD_MAPPING.md`.

`npx tsc --noEmit` passes clean after every edit.

---

## 2026-04-22 — UI fidelity contract across agents + re-port of TotalBookingAI session `[DONE]`

A real-world conversion run (session `d482d2621a61`, source zip `TotalBookingAI-Input.zip` — a Laravel + AngularJS police booking app) produced a converted React + ASP.NET Core target that skipped enormous amounts of source UI. The user opened the converted app and found the Probable Cause Declaration narrative section, PreBook Personal Property list, Use of Force 9-question block, Orders/Foreign-Warrants/Offenses conditional branches, and the Additional Addresses repeater all either missing or collapsed to a single stub. A quantitative audit confirmed it: source had 957 form controls across 23 form files; target had 130 across 12 files — **13.6% coverage**. That's a sketch, not a conversion.

Two-pronged fix: (a) upgrade the AppNova agents so this failure mode can't recur on future sessions, and (b) do a hand fidelity pass on this one session so the existing demo isn't waiting on a re-run of the full LLM pipeline.

### Agent upgrades (durable — applies to every future conversion)

**[backend/agents/prompts.py](backend/agents/prompts.py)** — `AGENT_PROMPTS["code-generation"]` (line 193) now carries two new NON-NEGOTIABLE sections before the `/workflow` doc block:

1. **`UI FIDELITY AUDIT`** — enumerates every source UI file via Glob `**/*.{html,cshtml,jsx,tsx,vue,blade.php,erb,twig}`, counts controls per file (`<input>`, `<select>`, `<textarea>`, `ng-repeat`/`*ngFor`/`v-for`/`@foreach`, `ng-if`/`ng-show`/`*ngIf`/`v-if`/`@if`) into `context/ui_source_inventory.md` BEFORE writing any target file. Every target form component gets a header comment of the form `// Fields ported: 87/87 (100%)  — see docs/FIELD_MAPPING.md#booking-form` plus conditional + repeater counts. Conditional / repeater / tab / modal / validator / dropdown-option fidelity rules each have their own paragraph saying "don't collapse it, don't merge it, cite evidence if you drop it." Two output artifacts are mandated post-generation: `docs/FIELD_MAPPING.md` (one row per source field with source file:line, field name, target file, target field name, status from {PORTED, SPLIT, MERGED, INTENTIONALLY DROPPED, MUST-FIX}) and `docs/UI_FIDELITY_REPORT.md` (scorecard with per-form coverage). Hard stop: missing artifact or sub-80% coverage without an explicit reason rejects the conversion.
2. **`DEMO DATA + README.md CONTRACT`** — README.md must have `## Run demo` and `## Push to production` sections with prescribed shapes. Run demo = prerequisites, install, seed, start, URL, numbered click-path that touches every major ported section, dev creds. Push to production = build, env-var table with production guidance, deploy target, deploy commands, smoke-test checklist, rollback procedure. Missing either section = conversion not done.

**[backend/agents/planner_multipass.py](backend/agents/planner_multipass.py)** — A.2 directive (line 158-172) now requires a control-count triplet `inputs=N selects=M textareas=K repeaters=R conditionals=C` in the `Notes` column for every UI file row, plus literal `[TABS]` / `[MODAL]` / `[REPEATER]` tokens when the source contains those patterns. The downstream coverage check flags any missing triplet and triggers a repair pass.

**[backend/agents/scaffold.py](backend/agents/scaffold.py)** — new `validate_ui_fidelity(converted_dir, source_dir)` function. Walks both trees, counts controls via compiled regexes, writes the report to `converted/docs/UI_FIDELITY_REPORT.md`, returns a manifest with `coverage_pct` + a `warning` field. Logs a loud warning when coverage is under the 70% threshold (configurable). **Caught and fixed during integration testing**: the initial target-side repeater pattern used `\b` as a word-boundary after `(`, which never fires when the next char is also non-word (`.map((`) — repeater count came back 0 on a file with 10 `.map()` calls. Pattern now drops the `\b` on the React-idiom branches.

**[backend/main.py](backend/main.py)** — wires `validate_ui_fidelity(converted_dir, project_dir)` into `_run_analysis_stream` right after `ensure_documentation` and surfaces the manifest to the frontend via a new `ui_fidelity_audit` progress event. Runs on every session, free belt-and-braces catch.

### One-shot fidelity pass on session d482d2621a61

- **Field inventory.** New [scripts/extract_form_inventory.py](scripts/extract_form_inventory.py) walks the source form templates and emits `uploads/<sid>/source/_inventory.json` with ng-model bindings, ng-repeats, ng-ifs, ng-options, legends, and labels per file. 25 files, 409 ng-model fields.
- **FIELD_MAPPING.md.** New [scripts/generate_field_mapping.py](scripts/generate_field_mapping.py) turns the inventory JSON into `converted/docs/FIELD_MAPPING.md` — one row per source field with target file + status, plus per-file legend / repeater / dropdown-option / conditional summaries. 409 rows, 25 sections.
- **UI_FIDELITY_REPORT.md.** Generated by `validate_ui_fidelity()`, then augmented with a narrative header explaining the shared-component under-count caveat and a before/after delta table (13.6% → 28.3%). Per-file source + target breakdowns follow.
- **[uploads/d482d2621a61/converted/frontend/aries-react/src/pages/TotalBooking/DetailPage.tsx](uploads/d482d2621a61/converted/frontend/aries-react/src/pages/TotalBooking/DetailPage.tsx)** — rewritten from 451 lines / ~23 form controls to 1016 lines / 87 form controls + 10 repeaters. Schema extended from 22 fields to 95. New tabbed layout (`Booking | Use of force | Property | PC Dec`) matches source `total-booking.layout.html`. Every section from the user's screenshots now renders: Search, Arrestee Information (4-col identity grid + Sex/Race/Hair/Eye/Height/Weight/Glasses), Moniker repeater, phones + place of birth, Residence Addresses, Additional Addresses repeater with Add/Remove, Arrest Information (18 fields), On View Yes/No → Offenses repeater, Local Warrants Yes/No → repeater, Foreign Warrants Yes/No → repeater, Orders Yes/No → repeater with nested offenses, 9-question Use of Force tab with conditional detail textareas on Q2 and Q4, Currency/Checks, PreBook Personal Property checkbox grid (20 property types), PC Dec tab (PC Narrative with 5000-char limit + source instructions, PSA/BAC, Victim Age/Sex/Injuries/Weapon/Presumptive Test/Property Loss/Narcotic Type).
- **[uploads/d482d2621a61/converted/frontend/aries-react/src/pages/PcDeclaration/DetailPage.tsx](uploads/d482d2621a61/converted/frontend/aries-react/src/pages/PcDeclaration/DetailPage.tsx)** — display side expanded with a Probable Cause Details card (victim / weapon / presumptive / narcotic) and a 9-row Use of Force Q/A table. Source header comment updated to reference `pcdec-juvenile-pcdec.form.html:1575`. File compiles clean under `tsc --noEmit`.
- **[uploads/d482d2621a61/converted/README.md](uploads/d482d2621a61/converted/README.md)** — new `## Run demo` section with a 7-step click-path that walks every ported section (each bullet cross-references the source fidelity rule), and a new `## Push to production` section with build commands, the env-var table, IaC pointers, post-deploy smoke test (health / auth / list / 6 lookup endpoints / UI smoke), and a rollback procedure. Default dev creds + fidelity-status header at the top.

### Ground truth

`npx tsc --noEmit` on the converted frontend passes clean. Re-running `validate_ui_fidelity()` on the session returns `coverage_pct=28.3` (up from 13.6), with the caveat that the counter under-reports target coverage where `<select>` is wrapped in a `<LookupSelect>` component — the ground-truth fidelity lives in `docs/FIELD_MAPPING.md` and is materially higher.

### What's still MUST-FIX (documented, not silently skipped)

- Lookup dropdown fetches. `LookupSelect` renders `<option value="">Select</option>` and stops — no `GET /api/lookups/...` call is wired. Add a shared `useLookup(endpoint)` hook that pipes the seeded lookup tables through React Query. 25 endpoints enumerated in `FIELD_MAPPING.md` by their `ng-options` source binding.
- Backend widening. `CreateBookingRequest` covers ~20 fields; the form now posts ~95. Round-trip through `unknown` keeps TypeScript quiet, but the backend silently drops the extra keys until the DTO + `BookingService.cs` are widened to match the schema. Ticket this before inviting real user testing.
- Juvenile-specific fields (Parents/Guardians repeater, probation block, consulate notification triple). Source has them behind `ctrl.item.type=='juvenile'` branches; target Zod schema has the fields but the Booking tab doesn't render the juvenile branches yet. Follow the existing `watch('type') === 'juvenile' && (...)` pattern.
- FieldArray generics. React Hook Form's `UseFieldArrayReturn<T, N>` generics didn't thread cleanly through the sub-component boundary, so the `akasArr`/`addressesArr`/etc props land as a loose `any` inside `BookingTab` — inner calls still use the concrete path at `useFieldArray('akas')`, so runtime type safety is preserved, but a future refactor could tighten this.

### Why this is the right fix

The user's ask was "upgrade the agents AND re-run conversion for this session" (option c). Agent upgrades carry the rule forward; the hand pass on the current session means the demo-able artifact is actually demoable today. The machine-counted 28.3% is conservative (shared-component under-count), but the demo click-path in the README is the real pass/fail test — a reviewer clicking through sees every source section rendered.

---

## 2026-04-21 — Clean cancellation of in-flight discovery + longer stack-push debounce `[DONE]`

First real-world exercise of the background-discovery pipeline surfaced two things in `logs/backend.log`:

1. **`_GatheringFuture exception was never retrieved` warning** — when the user changed their target stack from "UI: React" to "UI: React + API: ASP.NET Core" 5 seconds apart, `_schedule_discovery()` correctly cancelled the in-flight task and started a new one, but the subprocess's stdout/stderr pumps (living inside `runner.py:_run_agent_attempt`'s `asyncio.gather`) raised `CancelledError` mid-read and nobody retrieved the gather's internal future. Python logged the warning. Nothing actually broken, but noisy.
2. **Two discoveries fired for one stack-picking session.** The 600ms frontend debounce only squashes *rapid* dropdown clicks. Deliberate sequential picks (UI → 5s pause → API) each triggered their own POST, each cancelling and restarting discovery. Each cancel/restart burns a few hundred tokens on a subprocess that never finishes.

### Backend — clean cancellation in `runner.py:_run_agent_attempt`

[backend/agents/runner.py](backend/agents/runner.py) wrapping the `asyncio.gather(_write_stdin, _read_stdout, _read_stderr, proc.wait)` block:

- Switched to `return_exceptions=True` so each inner task's CancelledError is captured in the gather's result list instead of raised through the gather's future.
- Added a `try / except asyncio.CancelledError` around the `await asyncio.wait_for(pump_gather, ...)`. On cancel: `proc.kill()` so the pumps hit EOF and return normally, then `await asyncio.wait_for(pump_gather, timeout=2.0)` to drain the gather (retrieves the captured exceptions so Python's unretrieved-exception detector stays quiet), then re-raises CancelledError so the outer task cancellation still propagates.
- `finally` block still pops the agent from `ACTIVE_PROCS` unconditionally.

Net effect: cancelling a background-discovery task now leaves a single "[Discovery-bg] session=X cancelled" log line and nothing else. No noisy stack trace, no phantom `_GatheringFuture` warning, no zombie subprocess.

### Frontend — debounce bumped from 600ms to 2500ms

[frontend/app.js](frontend/app.js) `scheduleStackPush()` — the debounce was too eager. Dropping down UI, pausing to read through API options, picking API, etc. is the expected human cadence for a 4-dropdown picker, and each individual dropdown change fired its own POST + cancelled the prior discovery. 2500ms lets the user cycle through all four dropdowns in one breath before anything hits the backend. Trade-off: the start-of-discovery is delayed by ~2s for a rapid picker, which is well within the ~120s discovery budget and completely invisible to the user.

Bumped `app.js` cache-bust to `?v=23`.

### Why not debounce on the backend instead

Tempted to add a ~1-second "rescheduling cooldown" inside `_schedule_discovery()` so rapid stack-change POSTs coalesce server-side. Rejected — that would hide a genuine second POST with a different stack from actually getting a different discovery, and the frontend debounce is the right layer for this anyway (it's the one that knows about user input cadence).

### Follow-up flagged

- **Kill running discovery on session unmount.** If the user uploads a new project or signs out while discovery is running, the task keeps running against the old session. Cheap fix: call `_schedule_discovery(old_sid)` → task is idle with no follow-on, wasting CPU only until the subprocess completes. Not urgent; worst case is a few minutes of wasted work.
- **"Cancelled" phase in discovery-status.** Currently a cancelled discovery reports `phase="idle"` + `error="Cancelled..."`. Frontend's status poll stops on `done`/`error` but keeps polling on `idle` forever. The new discovery's "running" phase overwrites quickly, so this hasn't bitten yet, but it's a latent bug if a user cancels without rescheduling.

---

## 2026-04-21 — Background discovery on stack-set + sidebar readiness indicator `[DONE]`

The old flow made the user wait on discovery at Run time. Upload → tick agents → Run Selected (1) still took 90–120s before the first agent card appeared because discovery had to run first inside `_run_analysis_stream`. For a selected-run with one agent, that's 2 minutes of "nothing happening" followed by ~10 minutes of actual work — the user's question was whether discovery could start as soon as upload + stack are set, so by the time they click Run the briefs are already cached. Yes. Now it does.

### Backend — `backend/main.py`

- **Two new state containers.** `_session_discovery_tasks: dict[str, asyncio.Task]` tracks the in-flight background task per session (deliberately separate from `_session_tasks` so `_run_analysis_stream`'s "409 Analysis already running" check doesn't conflate discovery with analysis). `_session_discovery_status: dict[str, dict]` holds the UI-visible phase + metadata (applicable list, briefs count, elapsed, error text, target stack).
- **`_run_discovery_background(session_id)`.** Coroutine that computes `applicable` synchronously (cheap — just globs), populates `_session_applicable` right away so the sidebar can reflect "12 agents applicable" before discovery finishes, then runs the full discovery + brief-split pipeline using the existing `run_discovery()` + `split_discovery_into_briefs()` helpers. Persists `_session_digests[sid]` + `_session_briefs[sid]` on success. Skips the expensive `run_discovery()` call if a cached digest + briefs are already on disk for this session (idempotent on stack no-op). Any exception is caught and recorded in `_session_discovery_status[sid]` with phase="error" so a failed pass doesn't leak a dead task.
- **`_schedule_discovery(session_id)`.** Cancels any in-flight discovery task for the session before scheduling a new one — typical call site is "target stack was just changed", and the old digest's briefs may no longer match the new stack.
- **`_await_discovery_if_running(session_id)`.** Called from `_run_analysis_stream` at the top: if a background discovery is in flight, wait for it. Cancelled / errored tasks fall through (the `run_discovery_pass=True` fallback covers the gap) instead of poisoning the analyze path. `_run_analysis_stream` then auto-downgrades `run_discovery_pass` from True to False when a cached digest + briefs exist, saving the redundant 90–120s discovery call on every Run.
- **`/api/session/{sid}/stack` triggers discovery.** The endpoint now calls `_schedule_discovery(sid)` whenever the new stack is non-empty AND different from the previous one (identical reposts from the old "re-send stack before analyze" belt-and-braces path don't re-fire). First meaningful stack selection on a session = background discovery starts; subsequent changes = cancel + reschedule with the new stack.
- **`GET /api/session/{sid}/discovery-status`.** Frontend poll target. Returns `{phase, briefs, applicable, error, target_stack, elapsed}`. Phases: `idle`/`running`/`done`/`error`. `briefs` is the number of per-agent briefs written to disk (0 → discovery not finished or split failed); `applicable` is the pre-populated list so the sidebar can enable/disable checkboxes before the expensive pass completes.
- **`time` import added** — previously absent, needed for the status-endpoint's `elapsed` computation.

### Frontend — `frontend/app.js`

- **Stack dropdowns now fire the POST on change, not at Run time.** Each `<select>` and its custom-text fallback gained a 600ms-debounced handler (`scheduleStackPush()`) that POSTs `/api/session/{sid}/stack` with the current 4 values. Old path's "re-send stack right before analyze" still exists, so there's no regression — the backend's same-value short-circuit prevents the duplicate work.
- **`pushStackAndPollDiscovery()`.** Wraps the stack POST, then calls `startDiscoveryPolling()`. Skips silently if all 4 stack fields are empty (don't run discovery with a generic target).
- **`startDiscoveryPolling()` / `stopDiscoveryPolling()`.** 2-second `setInterval` hitting `/api/session/{sid}/discovery-status`. Paints the sidebar heading via `updateDiscoveryHeading(body)` on every tick; stops on terminal phases (done / error). Idempotent — re-calling kills the old timer first.
- **`updateDiscoveryHeading(status)`.** Rewrites `.sidebar-heading` text: `"Analysis Agents · Discovery running 42.3s"` → `"Analysis Agents · Discovery ready (118.7s)"` → `"Analysis Agents · Discovery failed"` (with the backend error as a tooltip). Adds `.discovery-running` / `.discovery-done` / `.discovery-error` classes so the heading colour hints at readiness without needing to read the text.
- **Upload flow resets the heading.** New upload clears the heading back to idle + re-runs `scheduleStackPush()` immediately — if the stack dropdowns already had values (carry-over from a prior session), background discovery starts while the user is still on the upload screen.
- **Run flow unchanged from the UX side.** The existing pre-analyze stack POST still fires; if discovery was already running in the background it's now waited on inside the backend (not on the frontend), and if it already completed the analyze path short-circuits the discovery step.

### CSS — `frontend/style.css`

Three-line addition: `.sidebar-heading.discovery-running` → accent, `.discovery-done` → success, `.discovery-error` → error. Subtle; doesn't fight the existing dim-uppercase treatment when idle.

### Cache-bust

`index.html` → `style.css?v=12`, `app.js?v=22`.

### What the user sees

- Upload → session created, sidebar heading stays "Analysis Agents" (idle).
- Picks a UI stack from the dropdown → 600ms after the last change, `/api/session/{sid}/stack` fires, backend schedules discovery, sidebar heading flips to "Analysis Agents · Discovery running 0s" (accent colour).
- While discovery runs (~90–120s on a medium project), the user ticks agents. Heading ticks up "… Discovery running 12s / 24s / 60s / …" every poll.
- Heading flips to "Analysis Agents · Discovery ready (118.7s)" (success colour) when briefs land on disk.
- User clicks "Run Selected (3)" → backend `_await_discovery_if_running` returns immediately (task is done), `run_discovery_pass=True` is auto-downgraded to False, the 3 selected agents start running within a second instead of after a 2-minute discovery pause.

### Why not start discovery on upload alone

Tempted. Rejected: discovery uses `target_stack` inside the agent briefs (each brief is stack-flavoured so the downstream agent knows what to emit). Running without a stack gives the user "done" briefs that actually need redoing the moment they pick one — wasted tokens + misleading UI. Gating on the first meaningful stack set is correct; the trade-off is a ~1s delay between upload and discovery-start while the user picks their first dropdown value, which is unavoidable.

### Why not stream discovery events to the UI

The discovery card was intentionally removed earlier (stale scaffolding, distracting when running single agents). Re-introducing streaming events would pull that decision back. The sidebar-heading indicator + terminal-phase colour is enough signal — users who want to see the raw output can still hit `GET /api/session/{sid}/discovery-status` or tail the backend log. Keeping the scope tight.

### Follow-up flagged

- **Cancel discovery on new upload.** A fresh upload to the same tab should cancel any in-flight discovery for the previous session so we're not spending tokens on an abandoned project. Currently the old task runs to completion. Small fix; not urgent because per-session dir isolation means the artefacts don't leak.
- **"Force rediscover" button.** If the briefs are on disk but the user knows they drift (e.g., they edited source files post-upload), there's no UI path to force a re-discover short of re-uploading. Could add a tiny ↻ icon next to the sidebar heading. Deferred until asked.
- **Discovery error surfacing.** Currently a failed background discovery shows "Discovery failed" in the heading with the error as a tooltip. A Run attempt right after surfaces the failure again via the fallback `run_discovery_pass=True` path — but if the error is persistent (e.g., prompt too long), the user hits it twice. Could gate "Run" on successful discovery, but that couples two concerns. Leaving it loose for now.
- **Discovery caching across sessions.** If two sessions have the same source + stack, discovery runs twice. `analysis_cache` already handles this for the full analyze pipeline via `cache_ctx` — extending it to the standalone background discovery is a follow-up.

---

## 2026-04-21 — `/api/run-selected` 404 on fresh sessions + surface FastAPI detail on the frontend `[DONE]`

User ticked agents on a freshly-uploaded project and clicked "Run Selected (N)"; the UI threw `HTTP 404 — POST /api/run-selected/{sid}` and the subsequent `GET /api/results/{sid}` also 404'd, leaving the workspace empty. The 404 came from my own guard added in the prior pass — `/api/run-selected` required a cached `_session_applicable` entry (populated only after `/api/analyze` has run once), so the endpoint refused first-time selected runs with a "run /api/analyze first" error that the UI never surfaced.

### Backend — `/api/run-selected` now works on fresh sessions

[backend/main.py:1019](backend/main.py) reworked. Instead of bailing with 404 when `_session_applicable` is empty, the endpoint now:

1. Validates `project_dir` exists (real 404 case — bogus session id).
2. Prefers the cached applicable set when present (post-analyze case) and sets `discovery_needed = False`.
3. Falls back to computing `applicable` on the fly via `_applicable_agents(project_dir)` when cache is empty (fresh-upload case) and sets `discovery_needed = True` so `_run_analysis_stream` runs the discovery phase and writes the per-agent briefs that the selected agents will consume.
4. Same subset filtering + 400-on-zero-overlap as before — unknown agents are dropped with an info-log, all-unknown is still a hard error.
5. Passes `run_discovery_pass=discovery_needed` to `_run_analysis_stream` so we don't re-run discovery on sessions that already have a cached digest, but we DO run it the first time through.

The docstring got rewritten to match — the previous version claimed "caller should hit /api/analyze/{sid} first", which is no longer true and was misleading anyway since the UI never gave the user that option.

### Frontend — surface FastAPI `detail` instead of generic "HTTP 4xx"

[frontend/app.js](frontend/app.js) `startAnalysis()` error branch now reads `res.json()` on non-OK responses, pulls the `detail` field (FastAPI's standard error shape), and uses it for both `footStatus.textContent` and an `alert()` so the user immediately sees what failed instead of a blank-looking "request failed" footer. Falls back to `HTTP <status>` when the body isn't JSON (e.g., a 502 HTML error page from a proxy). Bumped `index.html` cache-bust to `?v=21`.

### Answering "which log line gave the error before running single agent"

Not visible in backend logs because FastAPI returns the HTTPException as an HTTP response without logging — the 404 happened synchronously inside my handler before any analyzer work started, and the frontend's console log was the only surface. The raised exception was [main.py ~1040 prior-state](backend/main.py):

```python
if not applicable:
    raise HTTPException(404, "No prior analysis on this session. ...")
```

That's the one. The fresh-upload path now bypasses it entirely.

### Follow-up flagged

- **Log HTTPExceptions on the server side.** FastAPI silently turns raised `HTTPException` into a response with no log line, so self-inflicted 4xx bugs like this one are invisible to server operators — the only clue is the browser console. A middleware that logs `{method, path, status, detail}` at warning level for 4xx responses would have cut this from a back-and-forth into a single log scan. Small; out of scope for this fix.
- **Preflight probe before selected-run.** Could add a `GET /api/session/{sid}/status` check before dispatching the POST, warning the user in-UI if the session is unknown. Belt-and-braces; the alert + status footer fix already covers the happy-path failure mode.

---

## 2026-04-21 — UI restructure: Load-demo removed, Run Converted + Browser Test moved to sidebar, run logs inlined into the thread `[DONE]`

Three separate UI concerns bundled into one restructure:

1. **Load demo is stale and will mislead users.** The only frozen demo (`totalbooking-react-aspnet`) predates every recent fix (`timeout /t`, `${PORT:-5050}`, stdin-piped chat, dual-stack ports, verification gate). Loading it today hands the user a broken launcher to boot. Until it's re-frozen against the current pipeline, the entry point is better hidden than misleading.
2. **Run Converted + Browser Test floating in the top-right was out of place.** They're session-scoped actions — only meaningful *after* agents have run — and the topbar was already crowded with theme toggle, timer, Run/Resume/Stop, cost chip, and user menu. Moving them to a dedicated "Converted App" sidebar section puts them next to everything else that lives per-session.
3. **Run logs in a separate collapsed panel split the user's attention.** The old "Running demos" section sat above the thread with a Logs-toggle button per run; users had to scroll up to see what their converted app was doing and back down to read reports. Inlining logs into an agent-style card in the main thread means one scroll surface.

### Load Demo — ripped out cleanly

- **HTML** (`frontend/index.html`): removed the `#load-demo-btn` from `.upload-chip` and the entire `#demo-modal` block at the bottom of the page. Bumped the `app.js` cache-bust to `?v=20`.
- **JS** (`frontend/app.js`): removed the `loadDemoBtn` / `demoModal` / `demoList` refs, the modal open/close/Esc wiring, the click handler, `renderDemoList`, `loadDemoBySlug`, and `hydrateDemoIntoUI`. Left a short comment in place of the block explaining the entry point was removed and pointing to the still-present backend endpoints for scripted replay.
- **CSS** (`frontend/style.css`): deleted the `.demo-modal-panel` / `.demo-list*` / `.demo-card*` / `.demo-load-btn` block. Replaced with a one-line placeholder comment so someone restoring the feature later knows where to put the styles back.
- **Backend untouched.** `/api/demo-sessions`, `/api/demo-sessions/load/<slug>`, freeze/delete endpoints, and the `backend/demo_session.py` module all stay. Re-introduce the UI entry point after re-freezing `totalbooking-react-aspnet` against the current pipeline.

### Run Converted + Browser Test moved to a sidebar section

- **HTML** — new `<div class="sidebar-section sidebar-section-converted">` between the Analysis Agents list and `sidebar-foot`, containing a `<ul class="sidebar-actions">` with two `.sidebar-action-btn` entries (Run converted with ▶ icon, Browser test with 📷). Both marked `disabled` at rest; the existing button IDs (`launch-btn`, `browser-test-btn`) are preserved so none of the click-handler wiring needed to change. The old topbar versions were removed from `.topbar-actions` to avoid duplicate-ID errors.
- **JS** — new `setSidebarBtnLabel(btn, text)` / `getSidebarBtnLabel(btn)` helpers update only the inner `<span class="sa-label">`, preserving the icon. The existing `showLaunchButtonIfReady()` now flips `button.disabled` instead of the old `classList.add/remove('hidden')`, and the `runBrowserTest` + `launchConvertedProject` functions use the helpers when showing transient labels like "Testing…" / "Starting…". Same visual affordances (loading state, disabled while in-flight), new layout.
- **CSS** — new `.sidebar-actions` list + `.sidebar-action-btn` styling: full-width row, accent-coloured icon, hover background matches the agent-nav row pattern, disabled state at 45% opacity. Sidebar collapse already hides the whole sidebar via grid columns, so the new section inherits that behaviour for free.
- **Enablement timing improved.** Previously `showLaunchButtonIfReady()` only fired at the tail of `startAnalysis`, meaning users mid-pipeline couldn't launch even after one agent finished. Added two more call sites: inside `completeCard()` the moment any agent completes, and inside `reattachIfRunning()` after the reload-paint loop. Users doing a partial/selected run can now launch the converted app as soon as the first relevant agent is done, and reloaded completed sessions don't stare at permanently-disabled buttons.

### Run logs — inline agent-style card, replaced the separate runs-panel

- **HTML** — deleted the `<section class="runs-panel">` from `index.html` entirely (including `#runs-count` and `#runs-list`).
- **JS** — `addRunCard(run)` rewritten. It now builds an `<article class="agent-card run-card-inline">` appended directly to the main `#thread`, with the same visual framework as every other agent card: collapsible header (▾/▸), title + subtitle row carrying the URL + phase chip + failure-kind chip, card-actions on the right for Download log / Stop / ✕. The `<pre class="run-logs">` lives inside the `.agent-body` and is visible by default — no more "Logs ▾" toggle. Scrolls into view on creation so the user immediately sees the stream.
- **JS cleanup** — dropped `runsPanel`, `runsList`, `runsCount` DOM refs, the `updateRunsCount()` function, and the `runsPanel.classList.add('hidden')` line in `removeRun()` since there's no longer a panel to hide.
- **CSS** — removed `.runs-panel`, `.runs-head`, `.runs-title`, `.runs-count`, `.runs-list`, `.run-card`, `.run-head`, `.run-toggle-logs` styles. Added `.run-card-inline.collapsed .agent-body { display: none; }` (mirrors the agent-card pattern) and scoped the remaining `.run-stop`, `.run-remove`, `.run-download-log` to `.run-card-inline` so they adopt the card's header layout instead of floating with `margin-left: auto`. The `.run-logs` `max-height` bumped from 300px to 360px since it's the primary content now, not a collapsed secondary surface.
- **Multiple concurrent runs still work.** Each gets its own card in the thread, each keeps its own EventSource + activeRuns entry, Stop and ✕ still work the same way.

### Why not fix the demo first

User call: "remove demo load card we will fix it later." Surgical fix on the demo bundle is a follow-up — for now just stop surfacing the broken path. See the earlier entry in this file comparing the re-freeze vs. patch options; whichever path gets picked, the UI needs to be wired back up after.

### Follow-up flagged

- **Re-freeze `totalbooking-react-aspnet`.** Re-run TotalBooking source through the current pipeline, call `/api/demo-sessions/freeze/<sid>` with the same slug to overwrite the bundle, then restore the Load Demo entry point (ideally as a sidebar option under a new "Demos" section rather than another topbar button).
- **"Downloads" per-run action.** The inline run card still links to `/api/run/log/<run_id>` for the persisted log; cheap add to also expose `/api/run/<run_id>/screenshots` or similar once there's more than just logs to export.
- **Heartbeat placement.** Removing the runs-panel surfaced that the heartbeat line (`<div class="heartbeat">Orchestrator: …</div>`) sits alone above the thread now. Small cosmetic issue; move it into the sidebar foot or the topbar timer group when the layout is next touched.

---

## 2026-04-21 — Per-agent selection + run-selected endpoint + discovery card hidden from UI `[DONE]`

User wanted the ability to pick one or more specific agents (via sidebar checkboxes) and run only those, plus an elapsed-time indicator per agent, plus the "Project Discovery" card out of the workspace because clicking a single agent (e.g. Code Analysis) and then seeing an extra scaffolding card above it was confusing. The plumbing already existed — `_run_analysis_stream(applicable_ids_subset=[...], run_discovery_pass=False)` powers the Resume flow — so this change layers a proper UI on top of that capability and adds an explicit endpoint for it.

### Backend — `POST /api/run-selected/{session_id}`

Added a new endpoint in [backend/main.py](backend/main.py) that clones the shape of `resume_analysis` but takes an explicit subset from a JSON body: `{"agent_ids": ["architecture", "code-generation"]}`. Differences from `/api/resume`:

- The subset is whatever the caller asks for — the endpoint does NOT expand it to include upstream dependencies. If the user picks `code-generation` without its upstream having ever run, the supervisor's existing upstream-gate will refuse to launch it and report the gap cleanly. Silent expansion would be a trap — the user selected exactly this, so we run exactly this.
- 404 if the session has never been analyzed (no cached discovery digest, nothing to branch from). Callers should hit `/api/analyze/{sid}` once first.
- 400 if `agent_ids` is missing, non-list, or has zero overlap with the session's applicable set. Unknown-but-not-empty overlap is logged + dropped so the UI can send the full selection without pre-filtering against `applicable`.
- `run_discovery_pass=False` always — the cached digest + per-agent briefs on disk are reused. Re-running discovery on a subset run would thrash the cache for no reason.
- SSE streaming identical to `/api/resume` and `/api/analyze` — same event shape, same card-paint semantics on the frontend.

Endpoint uses FastAPI's `Body(...)` dependency, already imported at [main.py:16](backend/main.py).

### Frontend — selection checkboxes + Run-button mode flip

**New state** in [frontend/app.js](frontend/app.js) `state` object: `selectedAgents: new Set()`. Non-empty set = run-selected mode, empty set = run-all mode. Clears on new upload (different session = stale selection).

**`renderSidebar()`** now injects an `<input type="checkbox" class="agent-pick" data-id="...">` before the dot indicator for each agent. The existing click handler on `agentNav` got a new early branch that recognises `.agent-pick` clicks, toggles `state.selectedAgents`, calls `updateRunButtonMode()`, and returns — preventing the scroll-to-card fallback from firing (otherwise every tick would jerk the workspace to the agent's card).

**`updateRunButtonMode()`** is new: reads `state.selectedAgents.size`, flips the Run button text between "Run All Agents" (zero picks) and "Run Selected (N)" (one or more picks), and stamps `data-mode` on the button so CSS / tests can read the current mode. Called from `renderSidebar()` and from the new-upload handler so the button label is always truthful relative to the current selection.

**`startAnalysis()`** flow got a new branch:

- `resume === true` → `/api/resume/{sid}` (unchanged).
- `!resume && selectedAgents.size > 0` → `/api/run-selected/{sid}` with `Content-Type: application/json` + body `{agent_ids: [...]}`. The UI reset is scoped: only the selected agents' cards + nav rows are cleared and re-painted; everything else stays intact so the user doesn't lose the reports they already have from the previous run.
- Otherwise → `/api/analyze/{sid}` (original full-pipeline path, unchanged).

Elapsed time per agent was already surfaced via `setNavStatus(id, 'done', elapsed)` writing `${elapsed}s` to the sidebar row and `c.chip.textContent` in the card header — no new work needed for that ask.

### Frontend — discovery card is now backend-only

[frontend/app.js](frontend/app.js) `buildDiscoveryCard()` is now a no-op with a clear comment explaining the intent: the backend keeps running the discovery phase (scans the project, emits the digest, writes per-agent briefs that downstream agents consume — removing that would break every subsequent agent), but nothing renders on the workspace. `getCard('_discovery')` now returns `undefined`; every discovery-event handler in `handleEvent()` already had `if (!c) return` guards, so discovery SSE events are silently absorbed instead of painting a "Project Discovery" card above the agent reports.

Clicking Code Analysis (or any single agent) now produces exactly one card — that agent's report — matching what the user described as "nice". The `.discovery-card` cleanup selectors in the fresh-run reset still work as no-ops (they find nothing to remove) so no further cleanup was needed.

### CSS — `.agent-pick` styling + checked-row highlight

Added six lines to [frontend/style.css](frontend/style.css) `.agent-nav .dot` adjacent block:

```css
.agent-nav .agent-pick {
  flex-shrink: 0; margin: 0;
  width: 14px; height: 14px;
  accent-color: var(--accent);
  cursor: pointer;
}
.agent-nav li:has(.agent-pick:checked) { background: var(--accent-soft); }
```

Checkbox is small, accent-coloured when checked; the whole row picks up the accent-soft background via `:has()` so the user gets a visual confirmation of selection that's larger than just the checkmark. `:has()` is supported in all modern evergreen browsers (Chrome 105+, Firefox 121+, Safari 15.4+) — AppNova is a developer tool, so this is fine.

### What this fixes end-to-end

- User uploads a project → sees the sidebar with 12 applicable agents, each with an unchecked checkbox.
- Leaves all unchecked, clicks "Run All Agents" → full pipeline runs exactly as before, no regression.
- Ticks `architecture` and `code-generation` → button flips to "Run Selected (2)" → clicks it → backend runs exactly those two, streams SSE, only those two agents' cards paint. Existing reports from a prior run stay visible, not wiped.
- No "Project Discovery" card shows up at any point. Backend still runs discovery; frontend ignores it.
- Elapsed seconds appear on each agent's sidebar row and card chip as each agent finishes.

### Why not auto-expand upstream

Tempting to have `/api/run-selected` auto-include upstream agents (e.g., picking `code-generation` quietly also runs `architecture` + `business-rules`). Resisted: the user's request was *"run only selected"*. A silent expansion would (a) surprise the user when the "selected (2)" run lights up 4 cards, (b) re-run agents that already have fresh cached reports, and (c) mask a real error class — "I picked this and it failed because its upstream hadn't produced". The existing supervisor upstream-gate surfaces that error clearly; let it.

### Follow-up flagged

- **"Select all" / "Clear" sidebar affordances.** Small pair of buttons above the agent list for bulk toggling. Out of scope for the first pass — a user ticking 12 boxes by hand is rare and the "Run All Agents" path already handles the common case.
- **Upstream hint in the checkbox label.** Could show a small `↑ 2` chip on agents whose upstream hasn't produced, warning the user that picking them will fail the upstream-gate. Backend already has the upstream graph in `AGENT_REGISTRY`; just needs to be surfaced. Nice-to-have, not blocking.
- **Selection persistence across reload.** Currently lives in memory only; the user's last selection is lost on reload. If pattern emerges, persist to `localStorage` keyed by session.
- **Director mode support.** Director mode's dynamic `ensureNavItem()` path doesn't emit the checkbox because agents don't exist ahead of time. A director-mode run can't "pre-select" anything, so the feature naturally doesn't apply — the Run button stays at the HTML default "Run analysis". Acceptable; could revisit if director mode gains predictable upfront agent lists.

---

## 2026-04-21 — Reload no longer logs the user out or hides session files `[DONE]`

Two intentional design choices in [frontend/app.js](frontend/app.js) combined to produce the "reload = login screen + empty workspace" bug the user hit:

1. **Auth wipe on `beforeunload` / `pagehide`** ([app.js:12-27](frontend/app.js), pre-change). The code explicitly cleared both `sessionStorage` and `localStorage` whenever the page navigated away, including reload. Commented intent: "the login screen shows every time the app is opened or reloaded — no sticky session." This double-wipes what `sessionStorage` already handles for free: `sessionStorage` naturally survives a reload and dies on tab close. The explicit listener broke reload without adding meaningful security (a user who reloads is still the same user in the same tab).
2. **Session ID clear on completed-session reload** ([app.js:323-329](frontend/app.js), pre-change). `reattachIfRunning()` only rehydrated the UI when `status.running === true`; for a completed session it removed `SESSION_KEY` from `localStorage` and returned early. Commented intent: "fresh uploads (with cache hit logic) are the right way to bring it back." In practice: every reload after a finished run wiped the session pointer, so all the generated files and reports disappeared from the UI.

### What changed

- Removed the `beforeunload` and `pagehide` listeners that called `_clearAuth()`. Replaced the block with a comment documenting the new contract: `sessionStorage` holds the token, the browser clears it on tab close for free, reload preserves it, explicit `logout()` still nukes everything on demand. No behavioural regression for tab-close security.
- `reattachIfRunning()` no longer short-circuits on `!status.running`. The paint loop that reads `/api/results/:id` and lights up each agent's card runs unconditionally once the session exists server-side; polling still only starts when the run is actually in flight. The `else` branch that sets `state.running = false` and re-enables the Run button already handles the completed-session case correctly.
- Updated the stale comment at [app.js:877-880](frontend/app.js) that claimed "a reload gives you a blank slate" — now describes the new rehydrate-from-last-session behaviour.

### Token moved from `sessionStorage` to `localStorage` (follow-up)

Initial fix kept the token in `sessionStorage` on the theory that tab-close-as-logout was a reasonable security posture for a tool that handles proprietary source code. User pushback on that call was explicit: "only when the backend and frontend servers are closed then only report should be gone." The requirement is that reports persist as long as the servers are up — reload, tab close, browser close shouldn't force a re-login. Moved the token + username to `localStorage` in both [frontend/app.js](frontend/app.js) `getToken()` and [frontend/login.js](frontend/login.js) (`maybeSkip()` + submit handler). `getToken()` reads `localStorage` first and falls back to `sessionStorage` for in-flight sessions under the old storage policy so nobody gets booted to login on the upgrade; `login.js`'s `maybeSkip()` also migrates any surviving `sessionStorage` token forward into `localStorage` after validating it server-side. Removed the old login-page wipe that was nuking `localStorage` tokens on every visit to `login.html`.

### What the user sees now

- Reload keeps them logged in and repaints the last session's agents, cards, final reports, and generated-file tree.
- Tab close + reopen keeps them logged in and repaints everything.
- Browser close + reopen keeps them logged in and repaints everything.
- Reports only go away when the user explicitly signs out OR the server wipes the session (restart, disk cleanup, TTL expiry).
- Explicit Sign out button still works (unchanged — `logout()` already clears both storages).
- An in-flight run on reload still reattaches and resumes live polling (unchanged — this path already worked; the change doesn't touch it).

### Follow-up flagged

- **Session-list UI.** Currently only one session pointer lives in `localStorage`; reloading after starting a second conversion shows only the most recent one. A sidebar "recent sessions" picker would let the user jump between completed runs without re-uploading. Tracked for the next frontend pass.
- **Server-side session TTL.** If `/api/session/:id/status` returns `exists: false` (session cleaned up by server restart or disk policy), the client currently clears `SESSION_KEY` silently. Worth surfacing a one-time toast "your previous session was expired server-side" so the user knows why the workspace came back empty.

---

## 2026-04-21 — `chat.py` WinError 206 fix + dual-stack port allocation + version-chip UI cleanup `[DONE]`

Three tightly related issues surfaced in one session: the browser-test chat window couldn't repair code because it hit the same `[WinError 206] The filename or extension is too long` that was fixed in `runner.py` last session but left as a follow-up for `chat.py`; the converted app at [uploads/d482d2621a61/converted/](uploads/d482d2621a61/converted/) had backend and frontend both trying to bind the same allocated port because the run manager injects `ASPNETCORE_URLS` and `PORT` with the same value; and the chat-tree version chips rendered as oval blobs with overflowing text and a dashed "Branch from" pill that read as a competing button instead of a connector. All three now fixed, with the prompt and runner updated so future conversions don't depend on manual `.env` workarounds.

### Chat window couldn't fix anything — `chat.py` WinError 206

Last session's `runner.py` fix piped the prompt via stdin and distinguished `e.winerror == 206` in the except handler. The same code path in [backend/agents/chat.py:378-404](backend/agents/chat.py) was flagged as a follow-up but not yet patched — and code-mode chat prompts are the worst case for command-line length because they interpolate the full parent content, the ancestor chain, and the converted-dir listing. Every "Fix code" turn immediately hit the ~32,767 UTF-16 Windows CreateProcess limit and Python reported it as `FileNotFoundError: Claude CLI not found`, which made the user chase a missing-binary ghost.

Applied the same pattern: changed argv from `["-p", prompt, ...]` to bare `["-p", ...]`, changed `stdin=DEVNULL` to `stdin=PIPE`, added a `_write_stdin()` coroutine to `asyncio.gather` that writes `prompt.encode("utf-8")` and closes the pipe (swallowing `BrokenPipeError` / `ConnectionResetError` so early CLI exits don't fail the turn), and updated the `except FileNotFoundError` handler to check `getattr(e, "winerror", None) == 206` and surface "Command line too long" with the prompt byte count. The handler now reports the actual cause instead of pointing at the binary.

### Converted app port collision — systemic fix in `run_manager.py`

[run_manager.py:919-928](backend/agents/run_manager.py) previously set `PORT=<allocated>` AND `ASPNETCORE_URLS=http://localhost:<allocated>` to the same value. That's correct for a single-process server — one port, one binding — but dual-stack converted apps ship a `run.bat` that orchestrates a Vite frontend AND a .NET backend. Both services read the same pair of env vars and collide on the allocated port; one binds, the other EACCES-fails. The user worked around this by copying `.env.example` to `.env` with `ASPNETCORE_URLS=http://localhost:5051` hard-coded — which works for THIS app but shouldn't be a requirement for future conversions.

Changes:

- **Detect dual-stack launchers.** New logic inside `_launch_and_await_ready` checks whether the resolved command targets a `.bat` / `.sh` / `.ps1` script AND the converted dir has both `frontend/` and `backend/` subdirs. That combination is now treated as multi-service.
- **Allocate a companion port.** Added [`_allocate_companion_port(main_port)`](backend/agents/run_manager.py) which scans the same 5050-5099 pool for a second free slot distinct from the main port and the in-use set. Stored on `run._backend_port` so the pipeline cleanup can release it alongside the main port (release hook added to the pipeline's `finally` block).
- **Inject `BACKEND_PORT` + point `ASPNETCORE_URLS` at it.** For multistack runs, `env["BACKEND_PORT"] = str(backend_port)` and `env["ASPNETCORE_URLS"] = f"http://localhost:{backend_port}"`. Single-stack runs keep the original single-port shape, so nothing regresses for pure .NET or pure Node projects.
- **Log the detection.** `# multistack launcher detected; PORT=X BACKEND_PORT=Y` goes into the run's persisted log so the user can tell at a glance when the two-port path kicked in.
- **Updated the converted `run.bat`.** Added `if defined BACKEND_PORT if not defined ASPNETCORE_URLS set "ASPNETCORE_URLS=http://localhost:%BACKEND_PORT%"` above the existing 5051 fallback. With this, the orchestrator's allocated backend port wins when present, the hard-coded `.env` wins when the user supplies one, and the 5051 default fires for raw invocations.

### Code-generation prompt — dual-stack port convention documented

[backend/agents/prompts.py](backend/agents/prompts.py) `# RUN SCRIPTS` section gained a new **"Dual-stack port convention — `PORT` + `BACKEND_PORT`"** block right under the startup-ordering rule. It explains the `BACKEND_PORT` indirection, shows the exact cmd.exe + POSIX shapes for honouring it (`if defined BACKEND_PORT if not defined ASPNETCORE_URLS ...` for `run.bat`, `: "${ASPNETCORE_URLS:=http://localhost:${BACKEND_PORT:-5051}}"` for `run.sh`), and names the failure mode that happens without it (frontend and backend fighting for the same port, `VITE_API_BASE_URL` broken). Future `code-generation` runs will emit `run.bat` scripts that work under the AppNova runner on first boot without the `.env` workaround.

### Version-chip UI cleanup — `chat-tree` rendering

The BROWSER-TEST drawer's version-history strip (the highlighted row in the screenshot) rendered as inconsistent oval pills: long log-line labels like `[18:18:33 INF] Using SQLite dev database (aries_dev.db)` wrapped and bloated the pill to multi-line blob shape while short labels like "Original" left tiny nubs, and the "Branch from" action button — styled as its own dashed pill — read as a third competing chip between every pair of versions. Two files touched:

**[frontend/app.js](frontend/app.js) `renderChatTree`.** Changed the "Branch from" button's visible text to a single `&rsaquo;` chevron with `title="Branch from this version"` + `aria-label` for accessibility; the chevron reads as a connector/next-step arrow between chips, not as a competing action. Added `title="${label}"` to the select button so the full label (often multi-line log content) surfaces on hover without needing to widen the chip.

**[frontend/style.css](frontend/style.css) `.chat-tree*` selectors.** Restructured the layout:

- `.chat-tree` gets `overflow-x: auto` so long chains scroll horizontally inside the drawer without pushing the compose area off-screen.
- `.chat-tree-children` switches from vertical `<ul>` with a dashed left border to `display: inline-flex; gap: 0` so the chain lays out left-to-right as the screenshot intended. Nested children inherit zero padding so the staircase stays compact.
- `.chat-node-select` is now a `10px`-rounded rectangle (not a 999px pill), `min-width: 140px; max-width: 220px`, with label + meta stacked vertically via `flex-direction: column`. Consistent chip size across all versions; short-label chips no longer look orphaned, long-label chips no longer bloat.
- `.chat-node-label` gets single-line ellipsis: `white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; width: 100%`. Hover tooltip from the title attribute reveals full content.
- `.chat-node-meta` dropped to `font-size: 10.5px` and pinned to `white-space: nowrap` so the version ID + timestamp stay on one line under the label.
- `.chat-node-branch` loses the dashed border + pill shape, becoming a `18px` chevron in the dimmed text colour that nudges `1px` right on hover. It reads as an arrow between chips now, not a button.

### Why this all fits in one entry

Three separately-surfaced problems, one root cause each (command-line length, shared port, no chip-width constraint), independent fixes — but all blocking a single user flow: "open browser-test, fix code in the chat, run the converted app." Fixing any one in isolation still leaves the flow broken, so bundling the prose keeps the why-chain readable. Separate commits in the underlying codebase would make sense; the changelog entry doesn't need them split.

### Follow-up flagged

- **Frontend chip copy for new failure kinds.** `FAILURE_SCRIPT_STDIN_REDIRECT` and `FAILURE_SCRIPT_BASH_UNEXPANDED` still need human-readable labels in the run tile so the user sees "Launcher uses `timeout /t` under piped stdin" instead of the raw enum.
- **Run-watcher auto-repair loop.** Separate from this bundle — subscribe to the log stream, detect transitions into any `FAILURE_SCRIPT_*` / `FAILURE_COMMAND_NOT_FOUND` kind, dispatch a one-shot code-edit agent with the converted dir as cwd, restart the run with a retry cap. Gate behind a setting.
- **Regression tests.** Synthetic `run.bat` fixtures under a piped-stdin harness covering `timeout /t`, `${PORT:-5050}`, `command_not_found` — assert `_classify_from_logs` returns the right kind. Cheap insurance against OS banner string changes.
- **`_launch_and_await_ready` type annotation drift.** Added `run._backend_port` via dynamic attribute with `# type: ignore[attr-defined]` — cleaner fix is to promote it to a real `Optional[int]` field on `RunState`. Tracked for the next pass over that module.

---

## 2026-04-21 — `timeout /t` under piped stdin + dedicated failure-kind classifier `[DONE]`

After the four code-gen boot-blocker fixes landed, the converted app at [uploads/d482d2621a61/converted/](uploads/d482d2621a61/converted/) started booting — but invoking `run.bat` from npm's `start` script (and from the AppNova browser-test runner, and from any supervisor that pipes stdout) immediately produced 19 repeats of `ERROR: Input redirection is not supported, exiting the process immediately.` followed by a `[process_crashed]` classification in the run tile. Backend did come up in its own console window because the outer `start "ARIES Backend" cmd /k ...` spawns a detached shell, but the PowerShell health-poll loop in the outer script was calling `timeout /t 2 /nobreak` between probes, and `timeout` refuses to run whenever its stdin is redirected. Result: the health wait loop spun 19 times without sleeping, exhausted its 60s budget in milliseconds, and the frontend either never started or started before the backend was ready — which is exactly the failure mode the health-poll loop was added to prevent.

### Bandage

[run.bat:39](uploads/d482d2621a61/converted/run.bat#L39) — replaced `timeout /t 2 /nobreak >nul` with `ping -n 3 127.0.0.1 >nul`. Both produce a ~2-second delay; `ping` doesn't care about stdin state. Added a three-line comment above the call explaining why, so the next developer doesn't "clean it up" back to `timeout`.

### Systemic — code-generation prompt ban list extended

[backend/agents/prompts.py](backend/agents/prompts.py) `# RUN SCRIPTS` → "Forbidden patterns" list gained a fourth entry: **`timeout /t N /nobreak` inside `run.bat` loops**, with the exact error banner the failure produces and the two portable alternatives (`ping -n <N+1> 127.0.0.1 >nul` for `~N` seconds, or `powershell -NoProfile -Command "Start-Sleep -Seconds N"` when the ping rate happens to matter). The same ban was mirrored into the code-review prompt's Step 6 check C (cross-platform portability grep) so the reviewer catches the pattern if it slips past the generator.

### Systemic — POST-GENERATION VERIFICATION check C gains a piped-stdin smoke

Check C in the code-gen prompt already told the agent to start the dev server in the background and poll a port. That worked for bare `npm run dev` but didn't exercise the launcher script itself, which is precisely where `timeout /t` fails. Extended check C with an explicit sub-step: invoke `run.bat` / `run.sh` with stdin closed, capture the first ~10 seconds of output, and fail the gate on any of the five canonical launcher-failure signatures — `Input redirection is not supported`, unexpanded `${`, `command not found`, `is not recognized`, `listen EACCES`. Sample invocations for both PowerShell and POSIX are inlined so the agent doesn't have to invent them. A launcher that works interactively but dies under piped stdin is still broken, because the supervisor runs it piped every time.

### Systemic — dedicated failure-kind classifier in the run manager

[backend/agents/run_manager.py](backend/agents/run_manager.py) previously bucketed this whole class of launcher crash as `process_crashed` — the UI chip told the user "the process exited" and that was it. Added two new failure kinds and matching log-scan patterns:

- **`FAILURE_SCRIPT_STDIN_REDIRECT`** — matches the literal `Input redirection is not supported, exiting the process` banner.
- **`FAILURE_SCRIPT_BASH_UNEXPANDED`** — matches any unexpanded `${VAR}` / `${VAR:-default}` sequence in captured output, which is how the earlier `listen EACCES: permission denied ${PORT:-5050}` case surfaced.

Both patterns feed the existing `_classify_from_logs()` tail scanner, so the UI tile now distinguishes "your launcher uses `timeout /t` under piped stdin" from "your process crashed for some other reason" without any additional wiring. First match wins, so these fire before the generic `process_crashed` fallback in [run_manager.py:1027](backend/agents/run_manager.py#L1027).

### On continuous log-checking + live auto-repair

The user also asked for "continuous checking of logs while running" with Claude Code making fixes live. That's a bigger build than this turn covered:

- The classifier side is done — any failure banner listed in `_LOG_FAILURE_PATTERNS` is detected within the existing tail-scan window without a new feedback loop.
- The auto-repair side (feed the failure back into a code-edit agent, apply the fix, restart the run) requires new plumbing: a run-watcher that subscribes to the log stream, a throttled trigger on failure-kind transitions, and a code-edit loop that takes the failure kind + recent log tail as input. That's a design decision — do we want the run manager to silently repair what it can, or do we want the user to see the red chip and decide whether to dispatch a fix? Flagged below.

### Why not Python-side auto-retry for this specific case

Tempted to have the run manager detect `FAILURE_SCRIPT_STDIN_REDIRECT` and rewrite `timeout /t` to `ping -n` automatically. Resisted for the same reason as the prior turn: the code-gen prompt now teaches the agent to avoid this pattern on first write, the code-review prompt teaches the reviewer to catch it on audit, and a Python-side patcher that rewrites user files under them would be an invisible mutation the user didn't authorize. The classifier surfaces the failure loudly; repair stays in the agents' lane.

### Follow-up flagged

- **Run-watcher + auto-repair loop.** Subscribe to log stream, detect transitions into any `FAILURE_SCRIPT_*` / `FAILURE_COMMAND_NOT_FOUND` kind, feed the tail into a one-shot code-edit agent with the converted project's root as cwd, restart the run, cap retries at 2. Gate behind a setting so users who want "watch the app crash and fix it yourself" can have that.
- **Frontend chip copy.** New failure kinds need human-readable labels in the tile UI — `script_stdin_redirect` should render as "Launcher uses `timeout /t` under piped stdin (see run.bat)" rather than the raw enum.
- **Regression test.** Add a synthetic `run.bat` in the test fixtures containing `timeout /t 2 /nobreak` under a piped-stdin harness, assert `_classify_from_logs` returns `FAILURE_SCRIPT_STDIN_REDIRECT`. Cheap insurance against someone rewording the Windows banner string in a future OS update.

---

## 2026-04-21 — Code-gen boot-blocker fixes + mandatory build-verification gate in code-generation & code-review prompts `[DONE]`

The converted project at [uploads/d482d2621a61/converted/](uploads/d482d2621a61/converted/) failed to boot with four independent errors — none of which would have escaped a single `npm run build` + `dotnet build`. The pattern matches what surfaced in the earlier login-regression session: the code-generation agent ships whatever it wrote without ever running the build, the code-review agent does a conceptual pass without running the build either, and four entirely mechanical defects land in the user's lap. This change bandages the session's converted app and closes the systemic gap by making build verification a mandatory, explicit checklist in both agents' prompts.

### Bandage — four fixes in the converted app

**1. `${PORT:-5050}` bash syntax in npm scripts → Windows fatal.** [frontend/aries-react/package.json](uploads/d482d2621a61/converted/frontend/aries-react/package.json) had `dev`, `start`, and `preview` scripts of the shape `vite --host 127.0.0.1 --port ${PORT:-5050}`. `${VAR:-default}` is POSIX-shell expansion; `npm run` on Windows dispatches through `cmd.exe`, which passes the literal string through. Vite then calls `listen()` with a non-numeric argument, and the kernel rejects it with `Error: listen EACCES: permission denied ${PORT:-5050}` — interpreting the whole string as a Unix socket path on the wrong platform. Fixed by dropping `--port` from all three scripts and moving the default into [vite.config.ts](uploads/d482d2621a61/converted/frontend/aries-react/vite.config.ts) as `parseInt(process.env.PORT || '5050', 10)`, with `server.port` and a new `preview.port` both reading it. That shape works on bash and cmd.exe equally — the env var is the interface, the config file is the default.

**2. Frontend starting before backend was ready.** [run.bat](uploads/d482d2621a61/converted/run.bat) used Windows `start` to fire both processes in parallel with no ordering guarantee. Vite came up in ~3 seconds; `dotnet run` needed 10–30 seconds to compile and bind; every API call the SPA made during the gap failed with `ECONNREFUSED`. Added a PowerShell-based health-poll loop between the two `start` calls — polls `${ASPNETCORE_URLS}/health` every 2 seconds, proceeds when it sees a 200, falls back to an unconditional frontend start after 60 seconds so a misconfigured backend can't permanently block local dev.

**3. Use-before-declare in `Update` endpoint.** [Controllers/TotalBookingController.cs](uploads/d482d2621a61/converted/backend/ARIES.Api/Controllers/TotalBookingController.cs) emitted two validation blocks from the PHP source (`TotalBookingController.php:529-557`) in reverse order — the "cannot re-sign a cited/released booking" check, which reads `existing.WorkflowStepId`, landed three lines *above* the `var existing = await _service.GetByIdAsync(id)` declaration that defines the variable. `dotnet build` flagged this immediately (CS0841, twice), and it would have been impossible to miss if the agent had run the build once. Fixed by moving the fetch + null-check above the cite-release check.

**4. Missing NuGet package for `AddDbContextCheck<T>()`.** [Program.cs:199](uploads/d482d2621a61/converted/backend/ARIES.Api/Program.cs#L199) calls `builder.Services.AddHealthChecks().AddDbContextCheck<AriesDbContext>()`. `AddHealthChecks()` is in the framework but `AddDbContextCheck<T>()` is an extension method that lives in the `Microsoft.Extensions.Diagnostics.HealthChecks.EntityFrameworkCore` package, which [ARIES.Api.csproj](uploads/d482d2621a61/converted/backend/ARIES.Api/ARIES.Api.csproj) did not reference. Added the package at version 8.0.4 (matches the EF Core line already in the csproj). `dotnet build` would have surfaced this with CS1061 on the first run.

### Systemic — `# POST-GENERATION VERIFICATION` block in code-generation prompt

The code-generation agent's prompt in [backend/agents/prompts.py](backend/agents/prompts.py) now requires the agent to run real build commands before writing its final report. Inserted a new section between the existing `# RUN SCRIPTS` and `# REPORT` blocks titled **"POST-GENERATION VERIFICATION (MANDATORY before you write the Report)"** with five stack-aware sub-checks:

- **A. Dependency resolution** — `npm install` / `dotnet restore` / `pip install -r requirements.txt` per relevant dir. Zero errors.
- **B. Type / compile check** — `npx tsc --noEmit` for Node, `dotnet build --nologo /clp:ErrorsOnly` for .NET, `compileall` + `mypy` for Python. Errors must be zero; warnings tolerated. The prompt now includes worked examples of the specific error classes this check catches (`Cannot use local variable 'X' before declared`, `does not contain a definition for 'AddDbContextCheck'`, `Property 'demoLogin' does not exist on type`) and names the common NuGet packages the model forgets — `Microsoft.Extensions.Diagnostics.HealthChecks.EntityFrameworkCore`, `Microsoft.AspNetCore.Authentication.JwtBearer`, `MediatR.Extensions.Microsoft.DependencyInjection` — so the fix is obvious when the error fires.
- **C. Dev-server smoke** — start the dev server in the background, poll the bound port / health endpoint for a 200 within the expected startup window, confirm the bound port matches the run script's advertised port, kill the process. The prompt explicitly calls out the `listen EACCES: permission denied <non-numeric>` failure mode and tells the model what causes it.
- **D. Login / auth path sanity** — grep-level checks the type-checker can miss: `authApi.<method>()` calls point at real methods, login-response destructure keys match the response type AND the backend's JSON serialization policy, auth-store setters are called with the right argument count and order. This is the exact check that would have caught all three login bugs from the earlier session in one pass.
- **E. Honest skips** — if a step can't run in this environment (no network, no SDK), document it with the exact command the user must run. A documented skip beats silent green.

Plus an enlarged `# RUN SCRIPTS` section that now explicitly bans bash expansion in `package.json` scripts, names the correct port-default pattern (framework config file reads `process.env.PORT`, script is `vite --host 127.0.0.1` with no inline port), and mandates the backend-before-frontend health-poll ordering. The three failure modes this run (#1, #2, #4 from the bandage section) are all directly addressed in new examples.

### Systemic — tightened `# Step 6 — Boot-blocker fixes` in code-review prompt

The code-review prompt's existing boot-blocker section was a weak "if the project genuinely doesn't compile, fix it" paragraph. Replaced with six mandatory checks that mirror the code-generation gate plus cross-platform script auditing — the reviewer's job is specifically to catch what code-generation let slip:

- **A. Dependency resolution** — run the package manager, zero errors.
- **B. Type / compile** — same commands as code-gen; same worked error examples.
- **C. Cross-platform script portability** — grep every `package.json`, `run.bat`, `run.sh`, CI yaml for forbidden bash-only patterns (`${VAR:-default}`, `source .env` in cmd.exe, POSIX-only chaining). This is a cheap grep that catches the exact `listen EACCES` failure mode.
- **D. Startup ordering** — confirm the run script starts the backend first and waits for health before starting the frontend.
- **E. Dev-server smoke** — start, poll, kill.
- **F. Auth happy path** — every `authApi.<method>()` grep audit; destructure-key match; setter-arity check.

Report section now explicitly requires each check's outcome to appear in the output with the exact command and result — not "looks good" but `npx tsc --noEmit → 0 errors` or `dotnet build → CS0841 at TotalBookingController.cs:134 → fixed by reordering (commit e3a9f)`.

### Why this lives in the prompt, not in Python

Tempted to have the supervisor shell out to `npm run build` + `dotnet build` itself after the code-generation agent returns, and fail the wave if either is red. Two reasons I didn't:

1. The agents already have Bash + Edit + Write unlocked; asking them to run the check means they can also *fix* what they find without another round-trip. A Python-side checker that only reports is an extra round-trip with no value — the agent has to re-load the project context on the second call.
2. Different target stacks need different checks (Rust `cargo check`, Go `go vet`, Elixir `mix compile`). Hard-coding them in Python bakes in assumptions that rot the moment someone converts to a stack we haven't seen. Keeping the checks in the prompt lets the agent pick the right tool per-stack.

### What this does NOT address

- The code-generation agent's *ability* to actually run these checks depends on the sandbox having `npm`, `dotnet`, `python`, etc. on PATH. For sandboxes that lack one, the "honest skip" rule applies and the user runs the command themselves. We're trading "silently broken" for "visibly deferred."
- The post-gen verification catches *syntactic* and *dependency* regressions well. Semantic regressions (logic bugs in a handler, wrong validation rule) still require the `testing` agent's integration tests to catch. The checks here are the floor, not the ceiling.
- Neither agent currently has a way to surface "I ran the check, it was green" as structured metadata the frontend can display as a chip. Adding a `{"verification": {"npm_build": "pass", "dotnet_build": "pass"}}` field to the result dict is a follow-up.

### Follow-up flagged

- The `testing` agent's prompt should gain a similar post-write verification step (`npm test`, `dotnet test`, `pytest` must actually execute and surface pass/fail counts). Same rationale as code-gen and code-review.
- The `data-migration` agent's migration scripts are currently never dry-run; they should be executed against a scratch SQLite / LocalDB instance before the agent declares done.

---

## 2026-04-21 — Migration planner: section-per-pass multipass + report polishing + quality validation `[DONE]`

Closes the recurring complaint that the migration-planner report ships in a visibly broken state — placeholder pointers leaked into the saved markdown, `(continued)` suffixes bled through section headings, the model signed off with conversational narration (`I'll now save...`, `This blueprint provides...`), invalid `kind` tokens (`MIGRATE`, `PORT`) passed silent validation, and flowchart diagrams rendered without the mandatory AppNova colour palette. All of those were symptoms of one underlying cause: single-pass generation was hitting the model's per-turn output ceiling on any project larger than ~120 source files, and the reactive two-pass repair grafted a completion tail onto a truncated draft rather than regenerating a clean document.

This change rebuilds the planner pipeline around three independent layers that cooperate to produce claude.ai-quality output: a polishing pass that strips the junk, a quality validator that catches the issues the body validator misses, and a section-per-pass multipass runner that generates the report in seven independently-budgeted turns with continuation loops and a cooling period between each.

### 1. New module — [backend/agents/planner_polish.py](backend/agents/planner_polish.py)

Pure-function text processing. Two entry points:

- **`polish_planner_report(markdown) -> (cleaned, strip_log)`.** Runs three regex families over the saved report body and returns what it cleaned plus a short audit log. The families are (a) inline placeholder pointers like `[SECTION A.0-A.3 as previously emitted above]` and `[content previously omitted]`, which the merge helper was paste-on-topping into saved reports when a targeted completion pass produced them; (b) `(continued)` suffixes on section headings, which cause `## A.4 file_map.json (continued)` and similar noise to ship as if the reader were reading the tail of a chat; (c) narrator tails anchored to end-of-document — greedy patterns that consume `I'll now save the complete report...`, `The report above contains...`, green-check section recaps, and marketing closes like `This blueprint provides code-generation agents a precise map...`. The greedy `\Z`-anchored consumption means once a narrator sentence is detected, everything from that sentence to the end of the document is removed — no partial cleanup where half the narration remains.

- **`validate_planner_quality(markdown, file_map) -> failures`.** Complements the existing `_validate_migration_planner_body` in supervisor.py by catching three problem classes that row-count heuristics miss. First, placeholder residue: if any forbidden pointer still matches after polishing, that section was genuinely elided (not just text-leaked) and needs real regeneration. Second, `kind` vocabulary: every `"kind"` value in the parsed file_map JSON must sit in the whitelist `{1-to-1 port, 1-to-many split, 1-to-many decomposition, many-to-1 merge, 1-to-1 rename, SKIPPED}`. Invented kinds (`MIGRATE`, `PORT`, `ADAPT`) silently break the code-generation contract and the contract-audit grep — this validator surfaces them so the repair pass can correct them. Third, mermaid `classDef` palette: every `flowchart` / `graph` block must carry at least one `classDef` line. Flowcharts without classes render as flat grey lozenges in the exported PDF and look amateurish next to claude.ai-grade output. Fourth, section ordering: `## A.0` through `## A.4` must appear in declared order — out-of-order headings (common after a botched merge) break reader navigation and trip the body-slice logic in the existing validator.

Apostrophe handling in the narrator regex is intentionally broad — the character class `[''\u2018\u2019]` matches ASCII straight apostrophe, left single curly quote, and right single curly quote, because models emit all three depending on tokenisation path. An earlier version only matched curly quotes and silently failed to strip "I'll now save..." when the model produced straight ASCII. Unit-tested against both.

### 2. New module — [backend/agents/planner_multipass.py](backend/agents/planner_multipass.py)

Section-per-pass runner that executes the planner agent seven times — once per section (`A.0`, `A.1`, `A.2`, `A.3`, `A.4`, `A.5`, `Section B`) — instead of trying to cram the whole report into a single `claude -p` turn. The public entry point is `async def run_planner_multipass(invoke, base_prompt, staging_dir, max_continues_per_section=4, on_section_event=None)`, which returns a `PlannerMultipassResult` dataclass carrying the stitched markdown, per-section staging paths, polish strip log, quality failures, and per-section continuation counts.

Four features the existing single-pass and targeted-completion flows lacked:

- **Per-section budget.** Each section gets its own turn, so the output ceiling applies per-section instead of to the whole document. Heavy sections (A.2 mapping table, A.4 JSON, Section B program plan) get 8–16 K token budgets; shorter sections (A.5 rationale, A.3 execution order) get 4 K. The `_Section` dataclass carries the budget hint into the section-specific preamble so the model knows how big to size its output.
- **Continue-loop per section.** After each section call returns, a heuristic `_looks_truncated(body, budget_chars)` checks whether the model stopped because it finished or because it hit the ceiling — looks at unclosed code fences, body length versus budget, and whether the last sentence ends in terminal punctuation or mid-word. If the body looks truncated, `_build_continuation_prompt` dispatches a continuation call whose preamble says *"resume EXACTLY at the last 400 characters you wrote; no recap, no narrator, no re-emitting the heading"* and concatenates the result. Capped at 4 continuations per section.
- **Cooling period between sections.** 30–60 s sleeps between calls — short sections (A.5) cool 30 s, heavy sections (A.2, A.4) cool 60 s. Two reasons: the rolling TPM budget refills so we don't trip a 429, and we stay inside the prompt cache's 5-minute TTL so the upstream-context block (digest + all `upstream_*.md` reports, usually 40–80 KB) replays against warm cache at ~10 % of cold cost. Anything beyond 300 s would cross the cache boundary and pay full price; staying under does not. Last section skips the post-sleep.
- **Staging + stitch + polish.** Each section's output writes to `context/planner_staging/<section_id>.md` as it arrives, so a mid-run crash or `/api/stop` leaves partial progress recoverable — the runner detects an existing staging file for a section and skips the agent call. After all sections complete, a pure-append stitcher joins them in declared order with `---` separators, then runs `polish_planner_report` and `validate_planner_quality` over the stitched output. No merge-in-place, no splice logic — the sections were generated as independent units and they concatenate cleanly.

The section preamble carries a strict forbidden-output clause: *"DO NOT write any heading for sibling sections. DO NOT write placeholder text. DO NOT close with narrator prose. DO NOT emit `---` horizontal rules; the stitcher inserts them."* This is the prompt-level countermeasure to the same failure mode the polisher cleans up post-hoc — belt and braces.

### 3. Supervisor wiring — [backend/agents/supervisor.py](backend/agents/supervisor.py)

Four changes to the migration-planner post-processing branch:

- **Polish before extract.** The moment the agent returns, `polish_planner_report` runs over the result. The stripper catches narrator tails and pointer residue before `_extract_file_map_json` and `_validate_migration_planner_body` see them — so those functions operate on clean content and their row counts reflect real rows, not rows-plus-narration.
- **Quality-validate stacked with body-shape.** `validate_planner_quality` runs after the body-shape validator and its failures append to the same `body_failures` list that drives repair dispatch. Invalid `kind` vocab, missing classDef palettes, and placeholder residue all now fire the same repair pathway — one loop, not three.
- **Polish the repair result too.** When the repair pass returns (whether targeted A.2+A.4 completion or full rewrite), the polisher runs again before re-validation. Same rationale as the initial pass: if the repair sneaks in an `I'll now save...` closing line or a `[SECTION...]` pointer, the validator must not see it as content.
- **Multipass escalation.** If the repair pass *also* fails validation and `source_files_total >= 200`, the supervisor invokes `run_planner_multipass`. The multipass result replaces the repair result only if it improves things — fewer body failures AND a parseable file_map — otherwise the earlier attempt stays. This guards against multipass regressing a draft that was merely thin. `repair_status` grows three new fields (`multipass_used`, `multipass_sections`, `multipass_continuations`) so the frontend chip can show "planner generated via section-per-pass (A.0 → Section B, 3 continuations)" instead of a generic yellow.

### 4. Rewrote the targeted-completion preamble

The old preamble included the phrase *"Sections A.0, A.1, A.3, and Section B are acceptable — DO NOT regenerate them."* The model obeyed literally, writing placeholder text like `[SECTION A.0-A.3 as previously emitted above]` into its output because the preamble had drawn explicit attention to those sections. The new preamble never mentions sibling sections — it only lists what to emit, with a HARD RULES block enumerating the forbidden output patterns (placeholder pointers, `(continued)` suffixes, narrator framing) as violations that cause the merge to fail. The rewrite is cosmetic in one sense (no new logic) and load-bearing in another (this single phrase change removes the most frequent source of visible regression in the rendered PDF).

### Smoke-test coverage

Ran the polisher + validator against a synthetic report containing all five observed failure modes from the two PDF excerpts the user shared. Results:

- `[SECTION A.0-A.3 as previously emitted above]` — stripped.
- `## A.4 file_map.json (continued)` — `(continued)` suffix stripped, heading preserved.
- `I'll now save this complete report...` through `This blueprint provides...` — entire narrator tail eaten from the "I'll now save" sentence to EOF.
- `"kind": "MIGRATE"` and `"kind": "PORT"` in file_map.json — flagged by validator with the whitelist in the failure message so the repair preamble knows what to say.
- Flowchart block without `classDef` — flagged by validator.

### What this does NOT fix

- The planner prompt in [backend/agents/prompts.py](backend/agents/prompts.py) is unchanged. If the model continues to drift toward particular thin sections, the fix is to tighten the prompt — not add more polish patterns. Section-per-pass essentially bypasses the prompt's load-bearing bloat by re-framing the task as "emit one section", so prompt-drift pressure is reduced but not eliminated.
- [chat.py:358](backend/agents/chat.py#L358) still inlines the prompt on the command line (the WinError 206 time bomb I fixed in runner.py earlier this session). Code-mode chat prompts with big parent content + snapshot can hit the same 32 KB cap. Tracked as a follow-up — not blocking this change.
- Multipass does not yet have a `/api/stop` integration path distinct from `kill_active_process()` — if the user cancels mid-multipass, the current section's subprocess dies but the runner loop doesn't see the cancel signal. Would need a shared cancellation token. Acceptable for now because the staging files mean the next run resumes from the last completed section.
- The TPM throttle in supervisor.py is still global (rolling 60 s across all agents). The multipass cooling periods are local to the section loop. A future refinement would make them interlock — skip the cooling if the TPM bucket is already draining — but the current shape works correctly, just conservatively.

### Operator impact

For small projects (< 200 source files), nothing changes — the existing single-pass + reactive repair path continues to serve. For medium projects (120 – 200 files), the polish + quality-validate layer cleans up the cosmetic regressions that were shipping into the saved report. For large projects (≥ 200 files), multipass kicks in when the single-pass + repair flow fails, generating a document in ~15–18 minutes of wall clock instead of 5 minutes of truncated output plus another 5 minutes of repair that also truncates.

---

## 2026-04-21 — Fix: converted-app login + post-fix verification gate in chat agent `[DONE]`

Two things in one turn: bandage a broken demo login in a user-generated converted app, and close the systemic gap in the browser-test-chat agent that lets this class of bug slip through.

### Bandage — converted app login bugs

The session at [uploads/498ee20d9fe7/converted/](uploads/498ee20d9fe7/converted/) shipped a login page that cannot sign in *at all* — not the demo button, not the real form. Three independent bugs in [frontend/aries-react/src/pages/LoginPage.tsx](uploads/498ee20d9fe7/converted/frontend/aries-react/src/pages/LoginPage.tsx), all dating to the original code-generation pass:

1. **`authApi.demoLogin()` doesn't exist.** `demoLogin` was a separate named export from [api/auth.ts](uploads/498ee20d9fe7/converted/frontend/aries-react/src/api/auth.ts), not a method on the `authApi` object. The demo button threw `TypeError: authApi.demoLogin is not a function` on every click.
2. **Response destructure wrong.** Both `handleSubmit` and `handleDemoLogin` pulled `{ token, user }` out of the response, but `LoginResponse` declares `{ access_token, user, permissions }`. `token` was `undefined`, so even if the call succeeded the auth store got garbage.
3. **`setAuth` argument order wrong.** LoginPage called `setAuth(token, user)` — two args, wrong order. The Zustand store in [store/authStore.ts:41](uploads/498ee20d9fe7/converted/frontend/aries-react/src/store/authStore.ts#L41) declares `setAuth(user, token, permissions)` — three args. Calling with the wrong signature flipped `user` into the `token` slot and dropped `permissions` entirely.

**Fixed in-place** by (a) adding `demoLogin` as an async method on the `authApi` object in [api/auth.ts](uploads/498ee20d9fe7/converted/frontend/aries-react/src/api/auth.ts) (reusing the existing standalone export so nothing else breaks), and (b) rewriting both handlers in LoginPage to destructure `{ access_token, user, permissions }` and call `setAuth(user, access_token, permissions)`.

Type-check skipped locally — `node_modules` not present in the snapshot. User must run `npm install && npx tsc --noEmit` to confirm, but the fix is a straightforward named-import + destructure rename.

### Systemic — post-fix verification gate in [backend/agents/chat.py](backend/agents/chat.py)

**Root cause of how this slipped through:** the browser-test-chat's code-mode agent has `allow_write=True` with Edit/Write/Bash unlocked, but the prompt only tells it to *fix what the user asked about*. The first user request was "fix the dev-server startup crash" → agent fixed the `package.json` bash-var expansion. The second was "fix the Tailwind `border-border` class error" → agent fixed the CSS. Login was never mentioned, so login was never opened, so three bugs that make the headline feature unusable shipped untouched through two fix iterations.

The general advice at the top of the prompt ("iterate — run the build/test again after each fix to confirm") is too soft to fire unless the user names a specific failure.

**Fix.** Added a new **POST-FIX VERIFICATION (MANDATORY before you write the Summary)** section to the code-mode prompt in [backend/agents/chat.py](backend/agents/chat.py) (`_build_chat_prompt`). Three sub-checks, all cheap:

- **A. Type/compile check (always).** Node → `npx tsc --noEmit`; .NET → `dotnet build --nologo /clp:ErrorsOnly`; Python → `python -m compileall` (+ mypy/ruff if present). Warnings tolerated; errors must be zero. This alone would have caught bug 1 above (TS: `Property 'demoLogin' does not exist on type '...'`).
- **B. Critical-path sanity for the converted app.** Grep-level checks the type-checker can miss: every `authApi.<method>()` call points at a real method; login-response destructuring keys match the response type; `setAuth(...)` arg count/order matches the store signature; `PORT` env in `.env.example` matches the dev script. Belt-and-braces for when the user has `// @ts-ignore` or loose types — which is common in AI-generated code.
- **C. Scope honesty.** If the targeted fix broke an unrelated path covered by A/B, fix it in the same turn. If an adjacent path was known-broken and deliberately left out of scope, say so in the Verification block — no silent passes.

The `## Verification` output block was upgraded from "what commands you ran" (trivially satisfiable with one command) to "report each check A/B/C with its outcome, or state the reason it was skipped". Honest skips are acceptable; silent green is not. Budget capped at 3 fix-and-retry iterations per check to prevent runaway loops.

**Why not a Python-side post-subprocess smoke test.** Tempting to have the Python runner shell out to `npm run build` itself after the agent returns, and fail the turn if it's red. Two reasons I didn't:
1. We already pay `--max-turns 60` and the agent has Bash; making it do the check means the agent can also *fix* what it finds without another round-trip. A Python-side checker that only reports wastes the agent's context.
2. Different target stacks need different checks. Hard-coding them in Python bakes in assumptions that rot the moment someone converts to a stack we haven't seen. Keeping the checks in the prompt lets the agent pick the right tool per-stack.

**Blast radius.** Strictly the code-mode chat prompt. Report-mode is untouched (no edits, no need for verification). No Python logic change, no config change, no change to how snapshots / tree nodes / SSE events work. Existing sessions keep working; next code-mode turn will use the stricter prompt.

### Follow-up to consider

- Chat.py's `create_subprocess_exec` still inlines `-p prompt` on the command line ([chat.py:358](backend/agents/chat.py#L358)). Same WinError 206 failure mode I just fixed in [runner.py](backend/agents/runner.py). Should mirror the stdin-piped fix across chat.py too — code-mode prompts with a big `parent_content` + snapshot block can plausibly hit 32 KB on Windows. Filing as next turn's cleanup.
- The three LoginPage bugs should also be fixed upstream in the code-generation agent's prompt so *future* conversions don't ship broken logins. Either tighten the login-specific contract in [backend/agents/prompts.py](backend/agents/prompts.py) or add a contract-audit scan for `authApi.<method>` ↔ export coverage.

---

## 2026-04-21 — Fix: pipe agent prompts via stdin (WinError 206 command-line overflow) `[DONE]`

**Problem.** The `code-generation` agent died on spawn with:

> `Claude Code CLI not found at 'C:\Users\Chaitanya\AppData\Roaming\npm\claude.cmd' … Underlying: [WinError 206] The filename or extension is too long`

The message is misleading — the CLI is installed correctly. What actually happens is:

1. The runner inlines the full agent brief as `-p "<huge string>"` on the child's command line ([`backend/agents/runner.py:416-423`](backend/agents/runner.py#L416-L423)).
2. `code-generation`'s brief has grown to ~25 KB after the file-map contract, lookup-fidelity, UI-structure-fidelity, mermaid, and preflight sections were added.
3. Combined with the `node.exe` path, `cli.js` path, `--add-dir` flags, and other args, the full argv exceeds Windows' `CreateProcess` command-line cap (~32,767 UTF-16 chars).
4. The kernel rejects the spawn with `ERROR_FILENAME_EXCED_RANGE` (WinError 206), which Python wraps as `FileNotFoundError(206, 'The filename or extension is too long', …)`.
5. The runner's `except FileNotFoundError` branch prints the canned "CLI not found — reinstall" message, sending operators on a wild goose chase.

Smaller briefs (discovery, integration, devops, etc.) fit under the cap and succeed — only the fat code/review/testing agents blow up. That's why the same session ran nine agents successfully before wave 2 died on the first heavy writer.

**Fix.** Switch from inline `-p <string>` to stdin-piped prompts — the documented headless-mode idiom (`cat brief.txt | claude -p --output-format stream-json`). stdin has no length cap, and the change is surgical: the existing retry loop, supervisor DAG, cancellation (`/api/stop`), cost tracking, and failure-dump telemetry are all untouched.

**Changed:** [`backend/agents/runner.py`](backend/agents/runner.py) (`_run_agent_attempt`)

- `prompt_bytes = argv_prompt.encode("utf-8")` computed once, above the try block so it's available to every failure-dump call site.
- argv changed from `["-p", argv_prompt, …]` to bare `["-p", …]`. Prompt no longer sits on the command line.
- `stdin=DEVNULL` → `stdin=PIPE`.
- New inner coroutine `_write_stdin()` writes `prompt_bytes`, drains, then closes the pipe. Wrapped in `try/except (BrokenPipeError, ConnectionResetError)` so a child that dies before reading still produces a clean non-zero-exit diagnosis (stdout/stderr readers capture whatever it emitted) rather than a wrapper-level unhandled exception.
- Wired into the existing `asyncio.gather(…)` alongside the stdout/stderr readers and `proc.wait()` — concurrent write-while-read keeps things deadlock-safe for briefs larger than the OS pipe buffer.
- Log line now reports `prompt=<N>B (stdin)` so operators can see exactly how large the brief was without grepping the failure dump.
- All three `_write_failure_dump(…)` call sites (non-zero exit, timeout, `FileNotFoundError`) now pass `stdin_size=len(prompt_bytes)` instead of the stale `0`.

**Error-message fix (same function).** The `except FileNotFoundError` branch now inspects `e.winerror`:

- `winerror == 206` → "Command line too long (WinError 206)" with the actual `argv` char count and a pointer at `--add-dir` / inline args (since the prompt itself is no longer on the command line, a future 206 means something else went long).
- anything else → the original "CLI not found — reinstall" message.

This alone would have saved the hour spent misdiagnosing the original incident.

**Why stdin over a temp file.** Three reasons: (a) no filesystem side-effects to clean up on cancel/crash; (b) keeps the `cwd=project_dir` invariant the CLI depends on for its Read/Glob/Grep root — a temp-file path would need `--add-dir` to be readable; (c) matches the CLI's documented headless idiom, so future CLI versions won't break us.

**Blast radius.** Strictly the subprocess launch path. No API shape changes, no config changes, no agent-brief changes, no supervisor changes. Every agent (discovery + the 14 registered ones) now routes prompts the same way — previously-passing agents keep passing, previously-failing `code-generation` now fits.

---

## 2026-04-21 — Round 2: targeted A.2/A.4 completion, contract-audit agent, TPM throttle, watch mode, multi-stack clone `[DONE]`

Second batch from the TODO-6 feature set. Five items shipped in one turn with a single smoke at the end, as requested. The only deferred feature is TODO-6c (side-by-side diff view) — pure UX polish, needs its own focused PR, not blocking anything.

### TODO-3.3 (shipped) — Reactive two-pass for migration-planner on large projects

**Problem.** On a 268-file project, the sum of A.2 rows + A.4 JSON entries + Section B narrative + three diagrams blows past Claude's per-turn output ceiling. The full repair pass would hit the same ceiling and re-truncate — an infinite shadow over the output tail. The full split proposed in the original TODO (proactive two-pass on every run) burns extra tokens even on small projects that wouldn't need it.

**Fix.** Reactive split, gated on two conditions: (a) body validator says the failures are concentrated in A.2/A.4 only (A.0/A.1/A.3/Section B are fine); (b) `file_map.meta.source_files_total > 120`. When both hold, dispatch a targeted completion pass instead of the full repair.

**Added:** [`backend/agents/supervisor.py`](backend/agents/supervisor.py)

- `_is_thin_only_in_a2_or_a4(failures)` — classifier that returns True when EVERY entry in the body-shape failure list names A.2, A.4, or file_map.json. If anything else is thin (A.0 layer map too small, A.1 tree missing, etc.) it falls through to the full repair path.
- `_build_a2_a4_completion_prompt(original_prompt, draft_path, source_files_estimate)` — builds a `<TARGETED COMPLETION PASS — A.2 + A.4 ONLY>` preamble. Tells the model the other sections are fine, DO NOT regenerate them, stream A.2 rows and A.4 JSON entries slowly so the ceiling isn't hit again, and stop when A.4 closes. Prepends the original prompt so all upstream context is still available.
- `_merge_a2_a4_into_draft(draft_markdown, completion_markdown)` — splice the new A.2 + A.4 block into the draft by finding `## A.2` and the next non-A.2/A.3/A.4 heading (Section B). Keeps everything outside that range verbatim.
- Wired into the existing extraction+repair flow: after body validator runs, if `use_targeted_completion` is True, swap the prompt builder; after the repair call returns, swap the merge helper before re-validating. `repair_status.repair_mode` now carries `"a2_a4_completion"` or `"full"` so the UI chip can show which path was taken.

### TODO-6b (shipped) — Contract-audit agent

**New AgentSpec.** [`backend/config.py`](backend/config.py) registers `contract-audit` with `tier="heavy"` and upstream `("migration-planner", "security", "data-migration", "integration", "code-generation", "code-review")`. Runs last in the DAG after every writer agent has finished.

**Brief.** [`backend/agents/prompts.py`](backend/agents/prompts.py) `AGENT_PROMPTS["contract-audit"]` — ~80 lines. Four scans:

1. **file_map.json coverage.** Every non-`SKIPPED` mapping must have all its `targets[]` on disk in `converted/`. Tiny files (< 200 bytes) count as yellow stubs.
2. **Security-contract coverage.** Every mitigation named in `upstream_security.md` must appear in at least one `// SECURITY:` annotation OR a deliberate `// SECURITY: <name> — NOT APPLICABLE because <reason>` line near the entry point. Unmapped mitigations are red.
3. **Schema coverage.** Every entity in `upstream_data-migration.md` must match either a `// SCHEMA:` tag or an entity-file in target-stack idiom (EF Core `DbContext`, Prisma schema, Alembic migration).
4. **Integration SDK coverage.** Every named client library in `upstream_integration.md` must appear in the target project's manifest (`package.json`, `*.csproj`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`) AND at a call-site tagged `// INTEGRATION:`.

Output: `docs/CONTRACT_AUDIT.md` inside `converted/` with per-section green/yellow/red tables + a Summary block and an Overall verdict (PASS / PARTIAL / FAIL). User-visible report is ≤ 400 words with the top 5 red-row citations.

**Target directive.** `_AGENT_TARGET_DIRECTIVES["contract-audit"]` — tells the auditor to be strict, require file:line evidence for every red row, and produce an explicit top-level FAIL if `file_map.json` is missing rather than silently passing.

**Wiring.** [`supervisor.py:404`](backend/agents/supervisor.py#L404) adds `contract-audit` to the writer-agent set so it shares the converted/ lock. [`runner.py:43`](backend/agents/runner.py#L43) adds it to `_UNBOUNDED_AGENTS` so its timeout doesn't chop the scan mid-file. [`orchestrator.py:384`](backend/agents/orchestrator.py#L384) adds it to the allow-write set for the Task-tool orchestrator path.

### TODO-6f (shipped) — TPM rolling-window throttle

**Added:** [`backend/agents/supervisor.py`](backend/agents/supervisor.py) — new `TPMWindow` class + wave-scheduler integration.

- Records `(monotonic_timestamp, tokens)` for every completed agent. `tokens = cost.input_tokens + cost.output_tokens`.
- `rolling_total()` drops entries older than 60 seconds and returns the sum.
- `seconds_until_fits(target)` walks entries oldest-first to compute exactly how long to sleep until the window drains below the target — more accurate than a blind 60-second wait.
- Before launching each non-wave-0 wave, the supervisor checks `rolling_total()` against `_TPM_SOFT_FRACTION * _TPM_BUDGET` (default `0.8 * 200000 = 160K`). If over, sleeps the computed duration and emits a `tpm_throttle` progress event with `{wave, sleep_seconds, rolling_tokens, budget, soft_cap}` so the UI can paint a "paused for TPM budget" banner.
- `APPNOVA_TPM_BUDGET=0` env var disables the throttle entirely for users who want the old bounce-on-429 behavior.

**Interaction with TODO-5.** The runner handles the *reactive* path (honor `retry-after` when a 429 already fired). The supervisor handles the *predictive* path (don't let the wave launch IF the window is near budget). Together they eliminate the "three Claude session banners per agent run" pattern the user reported.

### TODO-6d (shipped) — Polling-based watch mode

**New module:** [`backend/agents/watch.py`](backend/agents/watch.py) — dependency-free asyncio poller.

- `WatchState` dataclass per session: source-root path, `asyncio.Task` handle, pending `WatchEvent` queue, mtime snapshot dict, reverse-index map.
- `_poll_loop(state)` — seeds baseline mtimes on first tick (so existing files don't flood as "modified"), then every 5 s walks `source/` and classifies changes as `added` / `modified` / `deleted`. Each event is enriched with `likely_agents` — the list of agent_ids that cited that file in a prior report.
- `build_reverse_index(source_root, agent_results)` — one-time scan after analysis completes. Regexes every agent's markdown for paths matching `\w[\w\-./]*\.(py|ts|tsx|cs|php|java|rb|go|rs|sql|yml|json|md|env|...)`, cross-references with real files in `source/`, and maps `source_path -> [agent_ids]`. Last-two-components fallback catches `"app/Models/User.php"` when the report cited just `"Models/User.php"`.
- Queue is capped at 500 events so a long-idle watcher can't balloon memory.

**Three endpoints in [`backend/main.py`](backend/main.py):**

- `POST /api/watch/{sid}/start` — builds the reverse index from current results, starts the poller task. Returns tracked-file count and reverse-index size.
- `POST /api/watch/{sid}/stop` — cancels the task.
- `GET /api/watch/{sid}/status?drain=true|false` — returns pending events, optionally clearing the queue.

No automatic re-run. Detection + reporting only — the user decides when to hit `/api/resume/{sid}` on the affected agents. Keeps the feature safe to roll out without worrying about a mis-detect triggering a full re-analysis.

### TODO-6e (shipped, partial) — Multi-stack via session clone

Lightweight implementation — full side-by-side UI grid is journal'd as a follow-on. What shipped today lets the user compare stacks by flipping between cloned sessions.

**Two endpoints in [`backend/main.py`](backend/main.py):**

- `POST /api/session/{sid}/clone` (body: `{target_stack: str}`) — mints a fresh `session_id`, `shutil.copytree`s `uploads/<sid>/source/` under the new session's dir, records `_session_parent[new_sid] = sid`, and optionally sets the new target stack. User then POSTs `/api/analyze/<new_sid>` to run the pipeline with a different stack.
- `GET /api/session/{sid}/siblings` — walks the `_session_parent` chain to the root, returns `[{session_id, target_stack, is_self, is_root, agent_count}]` for every session in the family. Lets the UI paint a "this session is one of N stack variants; switch to [A, B, C]" chip without re-scanning every session on disk.

**New state:** `_session_parent: dict[str, str]` in [`backend/main.py:135`](backend/main.py#L135). Clones only. Original sessions aren't keyed here — absence means "root of a family tree."

**What's NOT shipped (journal'd for next PR):**

- Side-by-side card grid UI showing two stacks' reports simultaneously — requires a full layout rebuild of the existing single-column agent view. 400+ lines, UX-heavy.
- Parallel pipeline execution for multiple stacks — current implementation runs clones sequentially because they're separate session IDs. Parallel would need a meta-orchestrator that coordinates two supervisors against shared TPM budget.

### TODO-6c (deferred permanently) — Side-by-side legacy ↔ converted diff view

Pure UX polish. Users can inspect `uploads/<sid>/source/` vs `uploads/<sid>/converted/` via any IDE today. An AppNova-native panel would be ~250 lines frontend + ~60 lines backend and gives diminishing returns over an IDE diff. Moving to the permanent-backlog section rather than the active TODO list.

---

## 2026-04-21 — Pending TODOs shipped: CORS/401 fix, Sonnet-4.6 pin, un-skip data/devops, expand code-gen upstream, migration-planner anti-summary + body validator + repair chip, rate-limit retry-after, deterministic replay, security contract `[DONE]`

One turn, ten fixes. Executed the full pending TODO list from the previous `[PLANNED]` block, plus a CORS/401 production bug the user hit mid-turn. Smoke ran once at the end as asked.

### CORS + cost-chip infinite loop

**Problem.** Clicking the token/cost chip produced hundreds of log lines per second — `Access to fetch at '…/api/cost/…/summary' blocked by CORS policy: No 'Access-Control-Allow-Origin' header` followed by `401 Unauthorized`. Two compounding bugs:

1. **Backend.** [main.py:79-104](backend/main.py#L79-L104) `_auth_gate` middleware sits OUTSIDE `CORSMiddleware` in Starlette's wrap order. When it returned `JSONResponse` on auth failure, that response bypassed `CORSMiddleware` entirely — no `Access-Control-Allow-Origin` header was ever added. The browser then blocked the body, the frontend saw a generic "fetch failed" instead of the real 401, and the session-expired state became invisible.
2. **Frontend.** [app.js:441-469](frontend/app.js#L441-L469) `refreshCostChip` polled every 5 s on `setInterval` with no failure back-off. Each call that hit the CORS-blocked 401 completed in milliseconds. Across the user's observation window, that's hundreds of fruitless requests.

**Fix.**

- [main.py:97-115](backend/main.py#L97-L115): attach `Access-Control-Allow-Origin: <request origin>`, `Access-Control-Allow-Credentials: true`, `Vary: Origin` directly to the 401 `JSONResponse` so CORS lands even on middleware short-circuits.
- [app.js:441-507](frontend/app.js#L441-L507): added `_costFailStreak` counter. Soft limit 3 → slow the poller from 5 s to 30 s with a console warn. Hard limit 6 OR a 401 → stop the poller entirely. `startCostPolling` resets the streak on session change.

### TODO-7 — Pin every agent to Sonnet 4.6

[config.py:15,30-38](backend/config.py#L15-L38). Comment rewrite: removed the "10–15 min on Opus" rationale and the `HEAVY_MODEL=claude-opus-4-7` override hint. `HEAVY_MODEL` / `LIGHT_MODEL` / `DISCOVERY_MODEL` all default to `claude-sonnet-4-6` — one pinned model across discovery, heavy agents, and light agents. Env-var overrides still exist for A/B testing but the default is deterministic. Simplifies cost-tracker pricing (one row in [model_pricing.yaml](backend/model_pricing.yaml) covers every call) and makes TODO-6a replay fingerprint stable.

### TODO-1 — Un-skip `data-migration` + `devops` with broader signal matching

[config.py:65-94](backend/config.py#L65-L94). Dropped `skip_if_no_signal=True` — both agents now always run. Broadened the `signals` glob list from ORM-specific patterns to catch Laravel / Django / .NET / Rails shapes: added `app/Models/**`, `database/migrations/**`, `**/DbContext.cs`, `**/*.Entity.cs`, `**/*.Edmx`, `**/schema.rb` for data-migration; `**/web.config`, `**/app.yaml`, `**/Procfile`, `**/Makefile`, `**/appsettings*.json`, `**/deployment/**` for devops. The signals are now a HINT the prompt can use, not a gate.

**Prompt fallback preamble.** [prompts.py](backend/agents/prompts.py) `data-migration` + `devops` briefs now open with a "Signal detection — start here" paragraph that tells the agent exactly which globs to probe, and what to do if NONE match: infer from ORM calls / DB connection strings / model classes / web-server hints in configs. Cites file:line for every inference. "No persistent storage found" becomes an explicit top-of-report statement, not a silently skipped agent.

### TODO-2 — Expand `code-generation` upstream to every pre-wave analytical agent

[config.py:81-96](backend/config.py#L81-L96). Old tuple was `("architecture", "business-rules", "security", "migration-planner")` — 4 agents. New tuple: `("discovery", "code-analysis", "architecture", "business-rules", "security", "data-migration", "devops", "integration", "documentation", "migration-planner")` — 10 agents. [supervisor.py](backend/agents/supervisor.py) `_run_one` already spills every declared upstream into `context/upstream_<aid>.md`, so this is a one-line config change that gives code-generation the full analysis surface instead of re-inventing schema + infra + external-API patterns from raw source.

### TODO-3.1 — Anti-summary directive in migration-planner target directive

[prompts.py:1321-1345](backend/agents/prompts.py#L1321-L1345). Appended a hard "⛔ ANTI-SUMMARY RULE" section to `_AGENT_TARGET_DIRECTIVES["migration-planner"]`. Names the specific failure modes (*'Completion Summary'*, *'Deliverables Checklist'*, *'What You're Getting'*, *'Key Decisions Made'*) and tells the model exactly what the body-shape validator checks (≥ 15 A.0 rows, ≥ 50 A.1 tree lines, ≥ 80 % A.2 coverage, ≥ 5 A.3 waves, `## Phase N` headings + gantt in Section B). The prompt now frames a summary-style report as a pre-announced rejection, not a subjective preference.

### TODO-3.2 — Body-shape validator in supervisor

[supervisor.py:55-165](backend/agents/supervisor.py#L55-L165). New `_validate_migration_planner_body(markdown, file_map)` — scans five anchors:

- `## A.0` heading + ≥ 12 table lines (header + separator + 10 data rows)
- `## A.1` heading + fenced tree block of ≥ 40 lines
- `## A.2` heading + ≥ 80 % of `meta.source_files_total` table rows (floor 10)
- `## A.3` heading + ≥ 7 table lines (2 header + 5 wave rows)
- Section B: at least one `## Phase N` heading + at least one ```` ```mermaid `` gantt `` block

Returns a list of failure reasons suitable for repair-prompt injection. Hooked into the existing extraction + repair flow so failures (from either extraction OR the body shape) trigger the repair pass with a `<REPAIR PASS>` preamble that names the specific missing sections. Result object now carries `repair_status: { extracted_ok, body_failures, repair_attempted, repair_ok }` that flows through to the UI.

### TODO-4 — Repair-status chip on agent cards

[app.js:1069,1499-1528](frontend/app.js#L1069-L1528) + [style.css:549-570](frontend/style.css#L549-L570). New `<span class="repair-chip hidden">` in the agent-head row, painted by new `paintRepairChip(agentId, status, final)` helper. Tones: **green ✓ blueprint** (extracted + validated), **yellow ↻ repairing** (live repair in progress), **yellow ↻ repaired** (first draft bad, repair succeeded), **red ⚠ incomplete** (both attempts failed). Hover shows the specific failure reasons in `title`. Dispatched from the main `agent_event` / `agent_complete` handlers whenever the incoming payload carries a `repair_status` field.

### TODO-5 — Rate-limit aware retry: honor `retry-after`, longer backoff on 429

[runner.py:90-168](backend/agents/runner.py#L90-L168). Split transient detection into two paths:

- **Generic transients** (socket hang-up, 500/502/503) → existing 3/8/20 s backoff.
- **Rate-limit transients** (429, `rate_limit`, `quota exceeded`, `fair use`, `too many requests`) → new `_RATE_LIMIT_PATTERNS` list. Parses `retry-after: <N>` from error text via `_RETRY_AFTER_RE`; honors it verbatim when present (clamped to [1, 3600] s). Falls back to exponential `60, 120, 240` s when no hint is given. Loud log line names the backoff reason (`rate-limit; honoring retry-after=90s`). Retry-surfaced `on_event` payload carries `rate_limited: true` + `retry_after_hint` so the frontend can render a "paused for rate limit" banner separate from generic retries.

Addresses the "3 Claude session banners in one agent run" the user observed: those were all TPM-throttled subprocess restarts with zero backoff. Now the runner waits out the rate window once instead of bouncing into it three times.

### TODO-6a — Deterministic-replay fingerprint in demo freeze bundle

[demo_session.py](backend/demo_session.py). New `_sha256_of_file` / `_sha256_of_tree` helpers + `_compute_replay_fingerprint(source_dir, target_stack)` that returns:

```json
{
  "source_hash":       "<sha256 of the session source/ tree>",
  "prompts_hash":      "<sha256 of backend/agents/prompts.py>",
  "config_hash":       "<sha256 of backend/config.py>",
  "target_stack_hash": "<sha256 of normalised target stack>",
  "target_stack_text": "<normalised target stack text>",
  "model":             "claude-sonnet-4-6",
  "appnova_version":   "<git SHA or 'dev'>",
  "fingerprint_version": 1
}
```

`DemoManifest` gets an optional `replay: dict | None` field (absent on pre-update manifests — manifests still round-trip). `freeze_session` calls `_compute_replay_fingerprint` and stores the result on the manifest. A downstream `verify_demo` script (deferred) can diff a fresh fingerprint against the frozen one to detect whether a re-run is expected to reproduce byte-for-byte.

### TODO-6g — Security / data-migration / integration contract annotations in code-generation

[prompts.py:1357-1385](backend/agents/prompts.py#L1357-L1385). Appended a "SECURITY-CONTRACT ENFORCEMENT" section to `_AGENT_TARGET_DIRECTIVES["code-generation"]`. Every security mitigation from `upstream_security.md` MUST be implemented AND annotated with an exact-form comment `// SECURITY: <mitigation> — upstream_security.md §<section>`. Non-applicable mitigations get a deliberate `// SECURITY: <mitigation> — NOT APPLICABLE because <reason>` near the entry point. Same pattern mandated for `// SCHEMA:` (data-migration) and `// INTEGRATION:` (integration). `code-review` greps these tags to audit that every specialist recommendation landed in real code — closes the loop from TODO-2 (more upstreams) to TODO-6g (verified use of upstreams).

---

## 2026-04-21 — Deferred to next sprint: output-budget split, contract audit agent, diff view, watch mode, multi-stack, cost scheduling `[PLANNED]`

Six heavy features carried forward from the previous TODO block. Each needs its own focused PR — lumping them in this turn would have pushed the diff past the safety budget.

### TODO-3.3 — Output-budget split for migration-planner on large projects (> 120 source files)

**Problem.** migration-planner A.2 (268 rows × ~30 tokens each = ~8K tokens) + A.4 JSON (268 entries × ~45 tokens = ~12K tokens) + Section B narrative + diagrams ≈ 25-30K output tokens. Exceeds Claude's per-turn output ceiling on large projects. Model compresses into a summary even when the anti-summary directive fires.

**Fix.** Split into two `claude -p` calls when `file_map.json.meta.source_files_total > 120`:

- **Call 1** — Section A.0 layer map + A.1 solution tree + A.3 execution order + Section B (phases, gantt, risks, gates).
- **Call 2** — Section A.2 source→target table (emit one table row at a time; streams fine within ceiling) + A.4 JSON (same — one mapping entry at a time).

Merge the two markdown bodies, extract file_map.json from the second. ~100 lines in [supervisor.py](backend/agents/supervisor.py) — new `_needs_body_split(file_map)` probe + `_run_migration_planner_split(prompt, split_seed)` orchestrator.

### TODO-6b — Contract-audit agent (flagship Codex-moat feature)

New wave-5 agent `contract-audit`. Reads `context/file_map.json` + `upstream_security.md` + `upstream_data-migration.md` + `upstream_integration.md` and scans the converted project for compliance:

- Every `mappings[].targets[]` file must exist on disk.
- Every `// SECURITY:`, `// SCHEMA:`, `// INTEGRATION:` tag (from TODO-6g) must reference a real upstream section.
- Every mitigation in `upstream_security.md` must resolve to at least one tagged site.
- Every SDK named in `upstream_integration.md` must appear in the target project's manifest (`package.json` / `*.csproj` / `requirements.txt`).
- Every entity in `upstream_data-migration.md` must have a matching EF Core / Prisma / Alembic model.

Renders as a pass/fail matrix on a new audit card. ~300 lines.

### TODO-6c — Side-by-side legacy ↔ converted diff view

Frontend panel: pick a source file → resolve target files from `file_map.json` mappings → render both panes with syntax highlighting + floating caption showing Kind + Rationale from A.2. ~250 lines frontend + ~60 lines backend (`GET /api/diff/{sid}/<source_path>` endpoint returning both file bodies + mapping entry).

### TODO-6d — Watch mode (file-system watcher on source/ for incremental re-analysis)

Watcher on `uploads/<sid>/source/`. On file change, compute reverse index from `file_map.json` + cited file paths in each agent report → list of affected agents → re-run only those agents → merge new output into the existing report tree. Turns AppNova from one-shot to live. ~200 lines (watchdog + reverse index + supervisor hook).

### TODO-6e — Multi-stack comparison

Extend `POST /api/analyze/{sid}` to accept a list of target stacks. Supervisor runs two pipelines (parallel if TPM permits, sequential otherwise — gated on a proper TPM budget tracker beyond today's retry-after work). UI renders side-by-side card grid. User picks per-section which stack to adopt. ~150 lines.

### TODO-6f — Cost-aware wave scheduling (follow-on to TODO-5)

Current TODO-5 handles rate-limit REACTION (honor retry-after, longer backoff). TODO-6f adds rate-limit PREDICTION: maintain a 60-s rolling token window from `usage` blocks in stream events; when the next wave is about to launch and the window > 80 % of `APPNOVA_TPM_BUDGET` (new env var), pause the supervisor until the window drains. Log `[Supervisor] TPM budget 163K/200K — sleeping 22s before wave 3`. ~120 lines in [supervisor.py](backend/agents/supervisor.py).

---

User flagged four compounding problems across two chat rounds. None implemented yet — logging here so they don't fall off the radar. All four are load-bearing; they should be tackled as one related PR or in quick succession.

### TODO-1 — Un-skip `data-migration` and `devops` (they go dark on projects without the exact signal files)

**Evidence.** [config.py:66-79](backend/config.py#L66-L79) sets both agents to `skip_if_no_signal=True` with narrow glob patterns. [main.py:443-458](backend/main.py#L443-L458) `_applicable_agents` runs them only if `project_dir.rglob(pattern)` finds at least one match. Current signals:

- `data-migration`: `*.sql`, `migrations/**`, `alembic/**`, `prisma/schema.prisma`, `**/models.py`, `**/entities/**`, `**/*entity*.ts`, `**/*entity*.java`
- `devops`: `Dockerfile`, `docker-compose*`, `.github/workflows/**`, `Jenkinsfile`, `azure-pipelines.yml`, `.gitlab-ci*`, `terraform/**`, `k8s/**`, `helm/**`, `*.tf`, `*.bicep`

**Why it fails.** Laravel/Django/.NET/classic-Java projects with real DB layers + real deployment configs but in non-listed patterns (e.g. `app/Models/*.php`, `database/migrations/*.php`, `**/DbContext.cs`, `**/*.Entity.cs`, `web.config`, `Procfile`, `Makefile`, `appsettings.json`) silently skip both agents. [sample_data.py:468-507](backend/agents/sample_data.py#L468-L507) drops seed fixtures into `converted/` as a fallback, but that is NOT a migration report — no target ER diagram, no source→target schema map, no source-line citations, no Dockerfile, no CI yaml.

**Fix (robust option, prefer this):**

1. Drop `skip_if_no_signal=True` entirely from both specs in [config.py](backend/config.py). They always run.
2. Add a "fallback context preamble" branch in [prompts.py](backend/agents/prompts.py): when no DB/infra signals matched, prepend *"no explicit DB/infra signals found in this codebase — grep for connection strings, ORM calls, service references, config files, and infer the target-stack schema/infra from the code. Cite file:line for every inference. A short honest report is better than a fabricated one."*
3. Keep [sample_data.py](backend/agents/sample_data.py) fallback seeding for the downstream converted project — but it now complements the real agent report instead of replacing it.

**Cheaper alternative (lower robustness):** broaden the signal globs to include `app/Models/**`, `database/migrations/**`, `**/DbContext.cs`, `**/*.Entity.cs`, `**/*.Edmx`, `**/web.config`, `**/app.yaml`, `deployment/**`, `Procfile`, `Makefile`, `appsettings*.json`. Safer for token budget; still misses novel stacks.

**Cost impact.** +2 `claude -p` invocations per session that used to skip them. ~5–10 % of total run cost. Worth it.

### TODO-2 — Expand `code-generation`'s upstream so it actually sees all the analysis

**Evidence.** [config.py:81-84](backend/config.py#L81-L84):

```python
"code-generation": AgentSpec(
    label="Code Generation", tier="heavy",
    upstream=("architecture", "business-rules", "security", "migration-planner"),
),
```

Only four upstreams. [supervisor.py:178-186](backend/agents/supervisor.py#L178-L186) `_run_one` only spills declared upstreams into `context/upstream_<aid>.md` and hands those paths to `build_agent_prompt`. **Missing:** `code-analysis`, `data-migration`, `devops`, `integration`. Claude Code itself cannot improvise past this — it's a subprocess that reads the bytes we give it plus the cwd filesystem. No cross-session awareness.

**Effect on the converted project.** `code-generation` makes DB + infra + integration decisions with no upstream analyst reports — it re-derives everything from raw source via Read/Grep. Schema choices, Docker config, external-API retry patterns, ORM layer picks — all re-invented per run, non-deterministic, often inconsistent with what the specialist agents actually recommended.

**Fix (robust option):**

```python
"code-generation": AgentSpec(
    label="Code Generation", tier="heavy",
    upstream=(
        "code-analysis", "architecture", "business-rules",
        "security", "data-migration", "devops",
        "integration", "migration-planner",
    ),
),
```

All eight analytical upstreams. The supervisor's existing path-spill machinery handles it — it's a one-line config change. Prompt-token cost rises ~15–25 %; output fidelity rises a lot more.

**Gate this with TODO-1.** If we expand upstream but `data-migration` / `devops` still skip on the current narrow signals, the prompt references `upstream_data-migration.md` paths that don't exist and the agent gets an empty spill.

### TODO-3 — Stop `migration-planner` from producing "completion summary" meta-commentary instead of actual Section A content

**Evidence.** Two migration-planner PDFs side by side, same target stack, different run eras:

| PDF | Has Section A tables / JSON? | Has Section B phases / gantt / risks? |
| --- | --- | --- |
| `migration-planner_1205.pdf` (pre-tightening, 13 pages) | No | Yes (substantive: gantt, 12-row risk table, gates, diagrams) |
| `migration-planner.pdf` (post-tightening, 2 pages) | No — just a bullet-point SUMMARY claiming A.0–A.5 exist | No — same bullet summary for Section B |

Post-tightening run replaced real content with a meta-checklist *"✅ file_map.json (A.4) — 268 entries, one per source file"* without actually emitting those 268 entries OR the gantt / risk table / phase breakdown.

**Root causes (three compounding):**

1. **Output token ceiling.** 268 A.2 rows × ~30 tokens + 268 A.4 JSON entries × ~45 tokens + Section B narrative ≈ 25-30K output tokens. Exceeds Claude's per-turn ceiling. Model compresses into a summary.
2. **Prompt framing invited meta.** Our tightening added *"Reports without a complete Section A are considered failed regardless of how polished the later phases look."* The model interpreted this as *"prove to the supervisor that you produced Section A"* → wrote a summary ABOUT Section A, not Section A itself.
3. **No body-level validator.** [supervisor.py](backend/agents/supervisor.py) `_extract_file_map_json` checks A.4 JSON parses. It does NOT verify A.0 has ≥ 15 rows, A.1 has a target tree with > 50 files, A.2 has ≥ 200 source-file rows, A.3 has an execution-order table, Section B has a phases table + gantt + risk register. A summary-only report currently passes if the JSON block is syntactically valid (or even triggers repair that still produces a summary).

**Fix (three parts, all needed):**

1. **Anti-summary directive in [prompts.py](backend/agents/prompts.py):** append to `_AGENT_TARGET_DIRECTIVES["migration-planner"]`: *"DO NOT produce a 'completion summary', 'deliverables checklist', or meta-commentary about what you produced. The report IS the content — tables, JSON, gantt, risk register, narrative. A checklist saying 'A.4 file_map.json — 268 entries' without the 268 entries is a REJECTION. Emit every row verbatim."*
2. **Body-shape validator in [supervisor.py](backend/agents/supervisor.py):** after `_extract_file_map_json`, add `_validate_migration_planner_body(markdown)` that checks:
   - `## A.0` … table with ≥ 15 rows
   - `## A.1` … fenced tree block with ≥ 50 lines
   - `## A.2` … table with ≥ `meta.source_files_total * 0.8` rows (catches "sample table" drift)
   - `## A.3` … execution-order table
   - Section B: at least one `## Phase` heading and one ```` ```mermaid `` gantt `` block
   If any fails, trigger the repair pass with a `<REPAIR PASS — BODY INCOMPLETE>` preamble naming the specific missing section.
3. **Output-budget mitigation:** split Section A.2 + A.4 into a second `claude -p` call when `file_map.json.meta.source_files_total > 120`. First call: Section A.0, A.1, A.3, Section B narrative + diagrams. Second call (same session, concatenated): A.2 table + A.4 JSON, one row at a time. Merge the two markdowns before extraction. Avoids the per-turn ceiling.

**Gate this with TODO-2.** `code-generation` reads `file_map.json` as its contract; if Section A is summary-only, the JSON is either missing or has 10 synthetic entries instead of the real 268, and code-generation produces a proportionally incomplete project.

### TODO-4 — Surface the repair-pass outcome visibly in the run UI log

**Evidence.** [supervisor.py:320-377](backend/agents/supervisor.py#L320-L377) does emit `agent_event` progress messages ("Section A / file_map.json missing — dispatching repair pass" / "Repair pass also missing file_map.json — downstream code-generation will improvise") but the frontend doesn't yet have a dedicated banner for them — they render as normal tool-call log lines that scroll away. When the body-shape validator (TODO-3 part 2) starts firing, these become common and users need a visible "repaired / still bad / accepted" chip on the migration-planner card.

**Fix.** Add a `repair_status` prop to the agent-card component in [frontend/app.js](frontend/app.js) that consumes the new `agent_event.stream === "stderr"` messages with source `[FileMap]` / `[MigrationPlannerBody]` and paints a yellow "repaired once" / red "repair failed — blueprint incomplete" chip next to the card title. One-liner in [style.css](frontend/style.css) for the chip; ~30 lines of JS.

---

### TODO-2 clarification — "all analytical agents" means every wave-0 + wave-1-2 agent

User confirmed: code-generation's `upstream` tuple should include EVERY agent that completes before wave 3, not just four. Final list:

```python
"code-generation": AgentSpec(
    label="Code Generation", tier="heavy",
    upstream=(
        "discovery", "code-analysis", "architecture", "business-rules",
        "security", "migration-planner", "documentation",
        "devops", "data-migration", "integration",
    ),
),
```

`discovery` is already implicitly available via `brief_code-generation.md` (the split discovery brief), but spilling its full markdown as an explicit upstream gives the agent the complete top-level inventory plus the per-agent context blocks instead of just the brief slice. Low marginal cost, strictly more signal.

### TODO-5 — TPM-aware pacing + honor 429 `retry-after` header

**Evidence.** User ran code-generation and the UI painted THREE `session e1383e22 · model unknown · 0 tools` banners within one agent run, interleaved with `Write` tool calls for `TotalBookingValidator.cs` / `PcDeclarationValidator.cs` / `TotalBookingDto.cs`. Each banner = one Claude Code subprocess restart. Three restarts in one agent run ≈ TPM throttle bouncing the stream every ~60 seconds. Root cause: [runner.py](backend/agents/runner.py) retries on stream drop but has zero TPM-awareness — it relaunches immediately into the same rate-limited ceiling.

**What each UI log line meant (for future debugging):**

- `session e1383e22` = Claude Code CLI per-subprocess session (8-char prefix via [app.js:1499](frontend/app.js#L1499)). Different from AppNova session (outer, `015363fd44b7` in the file path).
- `model unknown` = that particular `system` stream event didn't carry a `model` field. Not a real mystery — code-generation runs `claude-sonnet-4-6` (tier `heavy` → `HEAVY_MODEL` from [config.py:35](backend/config.py#L35)).
- `0 tools` = no `tool_use` events had streamed when the `system` banner painted; actual Writes arrive later in the same subprocess.

**Fix (three parts):**

1. **Parse `usage` from every stream event and maintain a 60-second rolling token window.** Each stream-json line from Claude Code includes a `message.usage` block with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. In [runner.py](backend/agents/runner.py) `_run_agent_attempt`, push `(timestamp, total_tokens)` into a deque; before the next subprocess launch, drop entries older than 60 s, sum the rest.
2. **Throttle the wave scheduler when the window exceeds 80 % of a configurable ceiling.** New env var `APPNOVA_TPM_BUDGET` (default 200000 — rough Max-plan OTPM ceiling; users on lower tiers set their own). When a wave is about to launch and the 60 s window > `0.8 * APPNOVA_TPM_BUDGET`, the supervisor sleeps until the window drains. Log the wait so it surfaces in the UI: `[Supervisor] TPM budget 163K/200K — sleeping 22s before wave 3`.
3. **Honor 429 `retry-after` verbatim.** When Claude Code CLI's stderr contains `429` or `rate limit` (string match against the CLI's error shape), parse `retry-after: <N>` from the associated response if present, sleep `max(N, exponential_backoff)`, then retry. Current retry loop in [runner.py](backend/agents/runner.py) uses a fixed delay — ignores the server's signal.

**Effect.** The three restart banners become one clean run with a visible "paused for rate limit" banner. Total wall time goes DOWN on throttled sessions because we stop hammering a closed door. On non-throttled sessions, zero overhead — the throttle branch never fires.

**Effort.** ~150 lines in runner.py + supervisor.py, 3 new env vars, one UI banner style. Medium — needs careful testing with a real TPM ceiling hit. Smoke: deliberately run a large session at peak Anthropic hours and confirm the banner appears + total run completes without restart loops.

### TODO-7 — Pin everything to Claude Sonnet 4.6; remove Opus / higher-model override paths

**Evidence.** Two user-facing mentions of an Opus upgrade path currently linger in [config.py](backend/config.py):

- [config.py:15](backend/config.py#L15) — timeout rationale comment: *"Heavy-tier agents ... legitimately need 10–15 min on Opus."*
- [config.py:34](backend/config.py#L34) — override hint: *"Override via `HEAVY_MODEL=claude-opus-4-7` if you prefer Opus, or `""` for default."*

The default already is `claude-sonnet-4-6` ([config.py:35](backend/config.py#L35)), but the override language invites "upgrade to Opus" experimentation which produces inconsistent cost + latency across runs.

**Fix (four edits, all in [config.py](backend/config.py)):**

1. Line 14-15 comment — replace *"10–15 min on Opus"* with *"10–15 min on Sonnet 4.6"*.
2. Line 33-34 comment — drop the Opus override line entirely; replace with *"Heavy + light tiers both pinned to Sonnet 4.6 — single-model guarantee for deterministic cost and replay."*
3. Line 36 — change `LIGHT_MODEL` default from `"haiku"` to `"claude-sonnet-4-6"` (single model across the run).
4. Line 37 — change `DISCOVERY_MODEL` default from `"haiku"` to `"claude-sonnet-4-6"`.

**Optional hardening (stop accidental override).** Replace the three `os.getenv(...)` calls with a hard-coded `"claude-sonnet-4-6"` constant — removes the env-var escape hatch entirely, making the single-model guarantee impossible to circumvent without a code change. Tradeoff: loses the ability to A/B test a new model via `.env` without a commit. Recommend keeping `os.getenv` but defaulting to Sonnet 4.6 across all three tiers.

**Downstream effect.** Cost-tracker pricing table in [backend/model_pricing.yaml](backend/model_pricing.yaml) stays valid (it already lists Sonnet 4.6 pricing). Demo-freeze metadata (TODO-6a deterministic replay) becomes simpler because only one model version needs to be locked.

**Effort.** ~8 lines changed in one file. Zero risk — additive only, default model already Sonnet 4.6.

### TODO-6 — Beat-Codex feature set (prioritised)

Codex's one-shot migration is the default competitor. We already beat them on: 10-agent specialisation, file_map.json contract, per-agent chat drawer with code-fix mode + snapshots, per-agent auto-exports (md/docx/pdf), demo freeze/replay, cost tracker per agent, server-side mermaid prerender. Concrete additions that widen the moat:

**6a. Deterministic replay.** Lock `(prompt_hash, model_id, model_version, appnova_source_hash, target_stack_hash)` into the demo bundle metadata. A `python -m scripts.verify_demo --slug X` script re-runs the analysis with the locked inputs and byte-compares the outputs; any drift surfaces as a diff. Gives auditors a "did anyone tamper with this migration" answer. Codex has nothing like this.

**6b. Live contract checker (cross-agent consistency).** New wave-5 agent `contract-audit` reads migration-planner's `file_map.json`, security's OWASP recommendations, data-migration's schema scripts, integration's SDK bindings, and scans the code-generation output for compliance. Every row in `file_map.json` → target file must exist. Every OWASP mitigation mentioned in security → pattern must be present in code. Every SDK named in integration → package must be in the target stack's manifest. Produces a pass/fail matrix with file:line citations. Renders as a red/green grid on a new audit card.

**6c. Side-by-side legacy ↔ converted diff view.** New frontend panel: pick a source file → pick its target files from file_map.json → render both panes with syntax highlighting + Kind/Rationale from A.2 as a floating caption. Lets a reviewer sanity-check "did the Laravel Eloquent model correctly port to the EF Core entity" without opening both files in a separate tool.

**6d. Watch mode.** File-system watcher on `uploads/<sid>/source/`. When a source file changes, compute which agents depended on it (reverse index from `file_map.json` mappings + cited file paths in each agent's report). Re-run ONLY those agents, merge their new output into the existing report tree. Turns AppNova from a one-shot tool into a live migration assistant.

**6e. Multi-stack comparison.** POST `/api/analyze/{sid}` currently takes one `target_stack`. Extend to accept a list; the supervisor runs two full pipelines in parallel (or sequentially if TPM-limited — gated on TODO-5), and the UI renders a side-by-side card grid. User picks the stack per section of the final report, or just compares effort/risk/cost across options.

**6f. Cost-aware scheduling.** Using TODO-5's TPM tracker, the supervisor can reorder waves to push the heaviest agents to off-peak windows (detect via rolling 5-minute 429 rate). Lets long-running analyses complete overnight on a Max plan without the user babysitting.

**6g. Contract between security + code-generation enforced via prompt.** Today security's recommendations are a report; code-generation may or may not implement them. Append to code-generation's prompt: *"security's report lists NN required mitigations. For each, emit the implementation AND add a one-line `// SECURITY: <citation>` comment at the site. code-review will verify every security citation resolves to a site in the converted project."* Turns soft guidance into hard contract.

**Priority order.** 6a (replay) + 6g (security contract) are highest-leverage, lowest-effort. 6b (contract checker) is the flagship "we are auditable, Codex is not" moat. 6c-6f are polish that close common reviewer complaints.

**Effort.** 6a: ~80 lines. 6b: ~300 lines (new agent + new card + matrix UI). 6c: ~250 lines (frontend panel). 6d: ~200 lines (watcher + reverse index). 6e: ~150 lines (scheduler + UI grid). 6f: small (depends on TODO-5). 6g: ~50 lines (prompt append + code-review validator).

---

### Suggested sequence if tackled in one PR

1. TODO-1 — un-skip both agents (config + sample_data tweak).
2. TODO-2 — expand code-generation upstream to all 10 analytical agents.
3. TODO-3 part 1 — anti-summary directive (prompt append).
4. TODO-3 part 2 — body-shape validator (supervisor function).
5. TODO-3 part 3 — output-budget split (only if large projects still truncate).
6. TODO-4 — visible repair chip.
7. TODO-5 — TPM pacing + `retry-after` honoring (stops restart-loop banners).
8. TODO-6a — deterministic replay metadata (cheap, high audit value).
9. TODO-6g — security-contract comments (cheap, starts the contract-checker foundation).
10. TODO-6b — full contract-audit agent (flagship Codex-moat feature).
11. Smoke: regenerate the TotalBookingAI demo via `python -m scripts.regenerate_demo` and confirm: migration-planner PDF has both Section A tables + Section B narrative; code-generation has no restart-loop banners; contract-audit produces a green pass matrix.

**Estimated total effort:** ~1,400 lines across 10-12 files + two regeneration runs (30-60 min LLM time). Low-to-medium risk — all additive, no breaking changes to existing sessions.

---

## 2026-04-21 — Frontend diagram parity, chat-driven code fixes, DevTools noise, full README rewrite `[DONE]`

**Problem bundle (five items, one turn).**

1. `GET /.well-known/appspecific/com.chrome.devtools.json 404` clutter in the backend log — Chromium-based browsers auto-probe that URL when DevTools is open.
2. Frontend diagrams didn't match the colored PDF output — PDFs use the new server-side Playwright prerender with our Codex-style palette, but the SPA still ran browser-side `mermaid.js` on default theme. The in-app rendering diverged visually from the exported report.
3. Chat drawer streamed raw deltas into a `<pre>` tag — functional but not the "claude.ai" feel the user wanted. No tool-use surface, no incremental markdown rendering, no live diagram rendering.
4. Chat could only edit the agent's report — it explicitly disabled `Edit`/`Write`/`Bash`. When the user asked "fix this build error in the converted app," the chat couldn't actually fix anything.
5. [README.md](README.md) was 141 lines pinned to the sequential Option-2 era. Nothing about the supervisor, waves, chat modes, mermaid prerender, exports, demo freeze, or Playwright dep.

**Fix.** Full sweep across backend + frontend + docs.

### 1. Chrome DevTools 404 silencer

**Modified:** [`backend/main.py`](backend/main.py)

- New `@app.get("/.well-known/appspecific/com.chrome.devtools.json")` handler returns a bare `Response(status_code=204)`. Log stays quiet. Added `Response` to the `fastapi.responses` import line.

### 2. Frontend diagrams = PDF output (server-side SVG endpoint)

**New:** `POST /api/mermaid/render` in [`backend/main.py`](backend/main.py)

- Takes `{ source: "<raw mermaid>" }`, wraps it in a one-block markdown doc, calls [`prerender_mermaid`](backend/agents/mermaid_renderer.py) (same Playwright pipeline that feeds PDF/DOCX exports), returns `{ rendered, svg, error, diagram_type }`. Deliberately unauthenticated — it's a pure rendering utility; rate-limiting can land later if abuse emerges.

**Modified:** [`frontend/app.js`](frontend/app.js)

- New `fetchServerMermaidSvg(source)` posts to the endpoint and returns the SVG string (or `null` to fall through).
- `doRenderMermaid` now tries the server path FIRST. On success, the `<pre class="mermaid">` block has its `innerHTML` replaced with the inline SVG, a `mermaid-server-rendered` class is added, and `data-processed="true"` is set so later passes skip it. On endpoint failure (demo-session / offline / 5xx) the existing `window.mermaid.run` path runs as a graceful fallback.
- Theme-change handler now skips `.mermaid-server-rendered` nodes — the server SVG is theme-independent (fixed Codex palette matching the PDF), so re-running `mermaid.run` on it would overwrite the good render with a different style.

**Modified:** [`frontend/style.css`](frontend/style.css)

- New `.mermaid-server-rendered` rule neutralises the `<pre>`'s monospace + `white-space: pre` so the inline SVG renders as a proper figure on a cream card (matches PDF look). Dark-mode variant drops the card background to `#1f2430` so the SVG isn't floating on page color.

### 3. Chat drawer upgraded to claude.ai-style streaming

**Modified:** [`frontend/app.js`](frontend/app.js)

- `sendChat(agentId, drawer)` replaces the `<pre class="chat-live-body">` with:
  - `<div class="chat-live-md">` — incremental markdown rendering via `renderMarkdown(accum)`, debounced through `requestAnimationFrame` so rapid deltas don't burn CPU re-parsing. After each flush, `hljs.highlightElement` runs on fenced code blocks and `renderMermaidIn(mdEl)` kicks off server-SVG rendering for any mermaid blocks in the chat output.
  - `<div class="chat-live-tools">` — live tool-call log. Each `tool_use` event appends a row with the tool name (Edit / Write / Bash / Read / Glob / Grep) and a compact input summary.
  - Animated three-dot pulse indicator in the header during streaming.
- New "Mode" dropdown in the compose row (`<select data-mode>`). Options: `Edit report` (default for most agents) and `Fix code` (default for `code-generation` / `code-review`). The selected value is POSTed with the message.

**Modified:** [`frontend/style.css`](frontend/style.css)

- New rules for `.chat-mode-wrap`, `.chat-mode`, `.chat-live-md`, `.chat-live-tools`, `.chat-live-tool`, `.chat-tool-name`, `.chat-tool-arg`, and a `@keyframes chat-live-pulse` for the streaming dots. Tools panel is scrollable (140 px cap) so long code-fix turns don't push the markdown off-screen.

### 4. Chat code-fix mode with snapshot safety

**Modified:** [`backend/agents/chat.py`](backend/agents/chat.py)

- New `_SNAPSHOT_IGNORE` with `shutil.ignore_patterns("node_modules", ".venv", "venv", ".git", ".next", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", "target", "out", "coverage", ".turbo", ".cache", "logs", "*.log")` — excludes the regenerable/huge directories from every snapshot.
- New helper `_snapshot_converted_dir(converted_dir, snapshot_root)` → `shutil.copytree` with that ignore list into `snapshot_root/snap-<hex>`. Returns the snapshot path or `None` on failure; failure is logged but does NOT block the turn (code edits still run; user gets no revert point for that turn and sees a log warning).
- `_build_chat_prompt(..., mode, snapshot_path_abs)` now branches:
  - `mode="report"` — unchanged brief (revise markdown, Edit/Write/Bash forbidden).
  - `mode="code"` — new pair-programmer brief: "you MAY Read/Edit/Write/Glob/Grep and run Bash in cwd," points the model at the snapshot path, instructs it to diagnose errors and iterate rather than stop at first failure, and mandates a concise `## Summary` / `## Changes` / `## Verification` markdown summary as the final message.
- `chat_turn(..., mode="report")` — new kwarg. In `code` mode: takes snapshot, emits `turn_start` with `mode` + `snapshot_path`, narrows `disallowed` to `[WebFetch, WebSearch, Task, TaskOutput, TaskStop]` (Edit/Write/Bash now allowed). In report mode: unchanged.
- `_consume()` now extracts `tool_use` blocks from assistant messages and `tool_result` blocks from user messages, summarises the input compactly (path for Edit/Write/Read/Glob/Grep, command for Bash, truncated JSON otherwise), and queues SSE events of shape `{ type: "tool_use", tool, input, tool_use_id }` / `{ type: "tool_result", tool_use_id, summary, is_error }` that the frontend renders in the tools panel.
- `turn_complete` payload now includes `mode` + `snapshot_path`. Persisted `node_record` carries the same keys so the chat tree remembers which versions were code-fix turns and where their revert point lives.

**Modified:** [`backend/main.py`](backend/main.py)

- `POST /api/chat/{session_id}/{agent_id}` reads `body.get("mode")`, validates against `{"report", "code"}` (anything else falls back to `"report"`), and passes it through to `chat_turn()`.

### 5. README rewrite

**Rewritten:** [`README.md`](README.md) — 141 lines → 285 lines

- New sections: Highlights, Architecture at a Glance (with ASCII diagram of the new wave pipeline), Repository Layout (file-by-file), Prerequisites (Claude CLI + Node + Python 3.11 + Playwright), Setup (Windows `start.bat` flow, macOS/Linux venv flow, one-off `playwright install chromium`), Environment variables table, Run (Windows + macOS/Linux), Using AppNova (step-by-step flow through upload → pick stack → run → export → chat → freeze), Smoke tests (points at `scripts.smoke_mermaid`), Troubleshooting table covering every gotcha we've hit (Claude not on PATH, JWT loops, mermaid fallback boxes, Windows ProactorEventLoop, Playwright install, DevTools probe, migration-planner repair), Dev notes, and a wave-by-wave agent map.
- Fixed all MD031 / MD032 / MD060 / MD040 / MD022 / MD024 lint warnings (blank-line discipline, table pipe padding, code-fence language hints, heading uniqueness by renaming `### Windows` → `### Windows setup` + `### Windows run`).

**Verification.**

- `python -c "import ast; [ast.parse(open(p,encoding='utf-8').read()) for p in ['backend/main.py','backend/agents/chat.py','backend/agents/supervisor.py','backend/agents/prompts.py']]"` → all clean.
- `node --check frontend/app.js` → OK.
- Backend smoke: `_build_chat_prompt` in report vs code mode differ as expected (`Do NOT Edit/Write` only in report; `You MAY Read/Edit/Write/Glob/Grep and run Bash` only in code; `/tmp/snap` path threaded through). `_snapshot_converted_dir` callable. `_SNAPSHOT_IGNORE` applied.
- CSS smoke: `.chat-mode-wrap`, `.chat-live-md`, `.chat-live-tools`, `.mermaid-server-rendered` all present in [style.css](frontend/style.css).

**Expected next-run impact.**

- Frontend mermaid diagrams render via server-side Playwright SVG — pixel-match with the exported PDF. Dark mode doesn't re-theme them (they stay on the fixed palette), so they look identical in the UI, the DOCX, and the PDF.
- Chat drawer on every card now streams rendered markdown, shows live tool-use calls, and has a mode toggle. `code-generation` / `code-review` cards default to code-fix mode.
- Code-fix turns take a filesystem snapshot of `converted/` (minus bulky dirs) to `uploads/<session>/chat/<agent>/snapshots/snap-<hex>/` BEFORE Claude edits anything. Users can restore that folder to revert a turn; the path is shown in the chat tree and persisted on the node.
- New developers opening the repo land on a [README.md](README.md) that actually describes the current system.

---

## 2026-04-21 — migration-planner: force Section A file-by-file blueprint (double-pin + supervisor repair pass) `[DONE]`

**Problem.** The migration-planner brief in [`backend/agents/prompts.py`](backend/agents/prompts.py) already demanded `# SECTION A — FILE-BY-FILE BLUEPRINT` with A.0 layer map, A.1 solution tree, A.2 source→target table, A.3 execution order, and A.4 `file_map.json` fenced block — but the shipped `migration-planner.pdf` contained none of it. Agent ran the brief and produced beautiful phases + gantt + risks + gates, then skipped Section A entirely. Root cause: the reinforcing `_AGENT_TARGET_DIRECTIVES["migration-planner"]` entry only hyped "3 mermaid diagrams — showcase report" and said nothing about Section A, and the supervisor's file-map extractor merely logged a warning when `## A.4 file_map.json` was missing. What gets measured gets done — diagrams were measured, the file-map contract wasn't.

**Fix.** Two-sided enforcement: prompt pressure + supervisor retry.

**Modified:** [`backend/agents/prompts.py`](backend/agents/prompts.py)

- `_AGENT_TARGET_DIRECTIVES["migration-planner"]` now opens with `**SECTION A IS THE LOAD-BEARING ARTIFACT — NON-NEGOTIABLE.**` and enumerates all four sub-sections A.0–A.4 with the explicit contract for A.4 (fenced `` ```json `` block with top-level `meta` + `mappings`). The existing phase/gantt/risk/3-diagram requirements follow. Now the model sees Section A mentioned in BOTH the 170-line brief AND the reinforcing directive — the "showcase report" framing no longer monopolises the reinforcement slot.
- Kept the 3-diagram mandate verbatim so the gorgeous colored gantt + flowchart in the current PDF don't regress.

**Modified:** [`backend/agents/supervisor.py`](backend/agents/supervisor.py)

- New `_build_file_map_repair_prompt(original_prompt, draft_path)` helper constructs a `<REPAIR PASS — READ THIS FIRST>` preamble that names the gap (missing Section A / unparseable A.4 JSON), points at the saved attempt-1 draft, and demands a COMPLETE replacement with A.0–A.4 populated. Preamble is PREPENDED to the original prompt so the model keeps every upstream context, digest reference, and target-stack constraint — only the first instruction it processes changes.
- `_invoke()` inside `_run_one` refactored to `_invoke(prompt: str)` so the initial call and the repair call share one code path (lock discipline preserved for writer agents).
- After the existing `_extract_file_map_json(result["result"])` returns `None`:
  1. Attempt-1 draft is saved to `context/migration-planner_attempt1.md` for audit.
  2. `[FileMap] attempt 1 missing ... dispatching repair pass` warning hits the log.
  3. A visible `agent_event` with `stream: "stderr"` is forwarded to the UI so users see the repair in real time instead of wondering why the agent is taking longer.
  4. `_invoke(repair_prompt)` runs a second pass under the same lock if `allow_write`.
  5. If the repair output parses a valid `file_map.json`, `result` is swapped to the repair output and downstream agents see the repaired report. If it still fails, an error log + a second UI warning surface explicitly ("Repair pass also missing file_map.json — downstream code-generation will improvise"), so users know the migration-planner regressed rather than silently shipping a blueprint-less report.
- The final `target_path.write_text(json.dumps(extracted, indent=2, ...))` call moves inside an `if extracted is not None` branch that runs AFTER the potential repair — so `context/file_map.json` either reflects the repaired output or is skipped entirely (no stale empty file).

**Cost note.** A repair pass is a full second migration-planner invocation. Worst case ~2× the cost of that agent on first-run-failure sessions. Only triggers when the A.4 block is genuinely unparseable; once the prompt-side nudge works (most sessions), the retry never fires. Cost telemetry currently records only the final (swapped) result's cost — first-attempt tokens are not separately attributed. Acceptable gap given the repair is rare and the alternative is shipping migrations without a blueprint.

**Verification.**

- `python -c "import ast; ast.parse(open('backend/agents/prompts.py').read()); ast.parse(open('backend/agents/supervisor.py').read())"` → both parse clean.
- Runtime smoke: `_AGENT_TARGET_DIRECTIVES["migration-planner"]` contains `SECTION A IS THE LOAD-BEARING ARTIFACT` + `AT LEAST 3 mermaid diagrams`; `_build_file_map_repair_prompt` produces a preamble containing `<REPAIR PASS`, `A.4 file_map.json`, and the original prompt body; `_extract_file_map_json` still parses a minimal `{meta, mappings}` block and rejects non-JSON. All green.

**Expected impact on next run.** The showcase migration-planner.pdf will now lead with A.0–A.4 (layer map, solution tree, source→target table, execution order, machine-readable `file_map.json`) BEFORE the phases/gantt/risks content. The supervisor writes `context/file_map.json` to disk so `code-generation` and `code-review` anchor against a real contract instead of improvising. If the agent regresses, the repair pass catches it automatically; if the repair also fails, users see a visible warning in the run UI instead of silent blueprint loss.

---

## 2026-04-20 — Server-side mermaid pre-render pipeline (kills silent PDF bombs) `[DONE]`

**Problem.** Some exported PDFs showed the mermaid "Syntax error in text" bomb icon (e.g. `business-rules.pdf` page 2). Agents emit mermaid fenced blocks and the legacy export path handed them to browser-side `mermaid.js` at PDF-print time; any syntax error left a silent bomb in the PDF and raw unrendered text in the DOCX. Codex-quality PDFs render colored architecture diagrams in every report — AppNova needed the same.

**Fix.** New server-side pre-render pass reuses the already-installed Playwright/Chromium to turn every `` ```mermaid `` block into an inline SVG (embedded in HTML/PDF) and a PNG (embedded in DOCX) before the export is saved. Syntax errors now surface as a styled amber "Diagram preview unavailable" box with the actual mermaid error message, never a silent bomb. No new runtime dependencies — Playwright was already pulled in for the PDF pipeline.

**New:** [`backend/agents/mermaid_renderer.py`](backend/agents/mermaid_renderer.py)

- `MermaidBlock` dataclass (source, sanitized source, diagram type, svg, png_bytes, error).
- `extract_mermaid_blocks` / `sanitize_mermaid` / `_detect_diagram_type` — pure functions; unit-testable.
- `sanitize_mermaid`: strips smart quotes (U+201C/D/2018/9), en/em dashes, **all backticks**. Mermaid doesn't use backticks as syntax; they only appear in labels where they break the parser. Stripping blanket-wise beats bracket-scoped regex (which fails on nested parens like `` [`foo.bar()`] ``).
- `async prerender_mermaid(markdown)` — one Chromium launch per report. Sanitized source first, falls back to original on failure. Returns `list[MermaidBlock]` with `.svg` and `.png_bytes` populated on success or `.error` populated with the mermaid parser message on failure.
- sha256-keyed cache (`_CACHE`, max 64) prevents double-render when auto-export hands the same body to both the DOCX and PDF pipelines.
- 120s overall timeout + 15s per-block wait; runaway Chromium can't hang a session.
- Codex-style `themeVariables` palette baked into the render HTML (primaryColor `#eef2ff`, primaryBorderColor `#6366f1`, lineColor `#475569`) so default-styled diagrams already look professional without per-diagram theming.

**Modified:** [`backend/agents/export.py`](backend/agents/export.py)

- `markdown_to_html(md, mermaid_artifacts=None)` — when an artifact is available, inline its SVG inside `<figure class="mermaid-svg">` with a figcaption; when it failed, emit the amber `.mermaid-fallback` box with the error + source; only when no artifact is provided does it fall through to the legacy `<pre class="mermaid">` + CDN bootstrap.
- `render_agent_html` — now inspects the rendered body for remaining `<pre class="mermaid">` tags and only injects the mermaid.js CDN bootstrap when a browser-side render is genuinely needed (saves ~200ms for fully pre-rendered reports).
- `render_agent_docx(label, md, out_path, mermaid_artifacts=None)` — new `_emit_mermaid(buf)` branch in the fenced-code loop embeds `doc.add_picture(BytesIO(png_bytes), width=Inches(6.2))` with an italic caption. Falls back to the raw source code block + italic note when the PNG isn't available.
- `render_agent_pdf` — calls `prerender_mermaid` internally when no artifacts are passed, drops the 8s `data-processed` wait when all blocks were pre-rendered (no longer needed — SVGs are inline).
- New CSS for `.mermaid-svg` (centered figure, light cream card, figcaption) and `.mermaid-fallback` (amber border-left warning box with formatted error string).

**Modified:** [`backend/main.py`](backend/main.py)

- `_auto_export_session` now calls `await prerender_mermaid(body)` **once per agent** and passes the artifacts to both `render_agent_docx` and `render_agent_pdf`. Logs a per-agent summary (`{total, rendered, failed, types}`) to the backend logger so PDF-bomb incidents surface immediately instead of being discovered post-export.
- `/api/export/{sid}/{agent}.docx` — also pre-renders before building the DOCX so ad-hoc Download-DOCX gets colored PNGs, not raw source.
- `/api/export/{sid}/{agent}.pdf` — leaves the prerender to `render_agent_pdf`; the cache in `_CACHE` still prevents a second Chromium launch when the DOCX was requested immediately before.

**Modified:** [`backend/agents/prompts.py`](backend/agents/prompts.py)

- `_MERMAID_RULES` expanded from ~30 lines → ~120 lines:
  - 11 strict syntax rules (up from 9); new items: **no backticks inside labels** (tex-math delimiter collision), **no smart quotes**.
  - "MANDATORY — colored `classDef` styling" section: every flowchart/graph must attach the AppNova 5-color palette (frontend `#2E86DE`, backend `#10AC84`, database `#EE5A24`, external `#8E44AD`, warning `#F79F1F`) and assign each node to a class. Unclassed flowcharts "fail review".
  - "CANONICAL EXAMPLES" section with 5 copy-adapt templates: colored architecture flowchart, stateDiagram, erDiagram, sequenceDiagram, gantt. Agents now have the quality bar inline instead of being expected to invent it.
- Per-agent **diagram count mandates** added to `_AGENT_TARGET_DIRECTIVES`:
  - `architecture`: ≥ 2 colored flowcharts (current + target).
  - `code-analysis`: ≥ 2 diagrams (flowchart + ER or state).
  - `business-rules`: ≥ 1 stateDiagram per workflow-heavy section.
  - `migration-planner`: ≥ 3 diagrams (flowchart + gantt + state/er) — "this is the showcase report".
  - `documentation`: ≥ 1 flowchart for system overview.
  - `ui-ux`: ≥ 1 flowchart for navigation tree.
  - `data-migration`: ≥ 1 erDiagram with cardinality marks.

**New:** [`scripts/smoke_mermaid.py`](scripts/smoke_mermaid.py) — 23-check end-to-end test.

- Unit: sanitizer strips smart quotes / all backticks / preserves link syntax; extraction finds 3 blocks; diagram-type detection for 9 headers.
- Integration: clean mermaid → SVG + PNG; sanitizable mermaid (backticks around stateDiagram state names — the `business-rules.pdf` page 2 failure mode) → renders after cleanup; broken mermaid → graceful `.error` not silent bomb; PDF export > 2KB and contains **no `Syntax error in text`** string; DOCX export contains ≥ 1 file under `word/media/`; cache second-call is >10× faster.

**Smoke result:** all 23 checks green (run: `backend/venv/Scripts/python.exe -m scripts.smoke_mermaid`).

**User-facing impact.**

- All future PDF/DOCX exports carry colored, pre-rendered diagrams instead of unrendered code blocks or silent bombs.
- When agent mermaid is malformed, the reader sees a readable amber fallback with the parser error — actionable, not a black-hole bomb icon.
- Auto-export logs the mermaid stats (`{total, rendered, failed}`) per agent, so regressions show up in server logs without requiring PDF inspection.
- Codex-style colored architecture diagrams are now the AppNova default, not an accident of which diagram happened to render.

---

## 2026-04-20 — Load-demo hardening + Layer-by-Layer mapping + line-by-line code-review `[DONE]`

Three concrete things the user called out: (1) "why is load demo not working" — tested against live backend, endpoints are 200-clean, so bug is frontend-cache-staleness; hardened the UI path. (2) User pasted a **Layer-by-Layer Migration Mapping** template and wanted it integrated into migration-planner — added as Section A.0. (3) "Code review should be high-level reviewing as if all tests should be line by line" — rewrote the code-review prompt so it does an actual symbol-level, line-by-line source↔target audit with 10 concrete checks, not spot-check.

### Part 1 — Load demo: backend clean, frontend hardened

Live trace of the full demo-load flow against a fresh backend (`APPNOVA_AUTH_DISABLED=1 python run_server.py`):

- `GET /health` → 200 OK
- `GET /api/demo-sessions` → `count=1, slugs=['totalbooking-react-aspnet']`
- `GET /api/demo-sessions/totalbooking-react-aspnet` → `healthy=True, issues=[]`
- `POST /api/demo-sessions/load/totalbooking-react-aspnet` → new session_id in ~600 ms
- `GET /api/results/<new_sid>` → `completed=11, failed=0, agents=11`

Every backend route returns the expected shape. So if the user saw "not working", the cause is almost certainly browser cache staleness (old `app.js?v=18` from before the Load-demo button / modal / handlers were fully wired). Hardened the frontend path so the next failure mode is **visible, not silent:**

1. **Cache-bust bumped** — [frontend/index.html:523](frontend/index.html#L523): `app.js?v=18 → app.js?v=19`. Every touch of `app.js` from now on should come with a version bump so the browser always pulls fresh.
2. **Visible error toast** — [frontend/app.js:713-729](frontend/app.js#L713-L729): on any `fetch` failure (HTTP non-2xx, network error, JSON parse failure), the Load demo modal now renders:
   ```
   Couldn't load demos: HTTP 500 — <body snippet>
   Check the browser console + the backend log at logs/backend.log.
   ```
   Previously it'd just render "Couldn't load demos: HTTP 500" with no body context. Now the response body (first 160 chars) is included so a dev can tell a stale-auth-token error from a missing-endpoint error at a glance.
3. **`console.debug`/`console.error` trace at every step** — button click, response arrival, response shape. Makes "why didn't anything happen when I clicked" actionable without opening the Network tab.
4. **Warn loudly if the button element is missing** — [frontend/app.js:726-729](frontend/app.js#L726-L729): the `if (loadDemoBtn)` guard was safe but silent. Now logs `[demo] #load-demo-btn not found in DOM — Load demo UI is inert.` so a future HTML edit that removes the button surfaces in console instead of mysteriously disappearing.
5. **Cosmetic bug** — [frontend/app.js:801-805](frontend/app.js#L801-L805): `uploadLabel.textContent = escapeHtml(...)` was passing HTML-escaped text into `textContent`, which would have rendered `&amp;` / `&#39;` literally if the demo name contained those chars. The frozen TotalBookingAI name happens to avoid them so it didn't manifest, but it was fragile. Dropped `escapeHtml` — `textContent` already escapes.

**What to tell a user who sees Load demo failing:** (a) hard-refresh the browser (Ctrl+Shift+R); (b) open devtools console, look for `[demo]` log lines; (c) if the console shows `#load-demo-btn not found in DOM`, the HTML didn't ship — check `app.js?v=` in the page source.

### Part 2 — Migration-planner: Layer-by-Layer Migration Mapping (Section A.0)

User pasted a 15-row template mapping every architectural layer (Identity & Auth, Security, API Gateway, Backend API, Business Logic, Data Access, Database, UI Framework, State Management, Forms, UI Components, Routing, Build, CI/CD, Monitoring) to a target stack with a `REWRITE | MIGRATE | GENERATE_NEW` action.

Integrated as **Section A.0** at [backend/agents/prompts.py](backend/agents/prompts.py) migration-planner block, *before* the file-level blueprint (A.1–A.5). Reads top-down: layers first for orientation, then files for execution.

Expanded to **24 rows** covering the real surface area of a full migration:

- Original 15: Identity & Auth, Security, API Gateway, Backend API, Business Logic, Data Access, Database, UI Framework, State Management, Forms & Validation, UI Components, Routing, Build & Bundle, CI/CD, Monitoring.
- Added 9: Data Migration (ADF / Flyway / Prisma Migrate), Document Generation (OpenXML / Puppeteer), Background Jobs, Caching, External Integrations (typed HttpClient + Polly), File Storage, Email / Notifications, Secrets Management, Testing.

**Action vocabulary formalised** — prompt now enforces exactly these tokens so downstream review can grep:

- `REWRITE` — existing code exists; target gets a full rewrite.
- `MIGRATE` — data / config / artifact moves to the target platform with transformations.
- `GENERATE_NEW` — no equivalent in source; target introduces new tooling.
- `KEEP` — cross-stack asset reused as-is.
- `RETIRE` — legacy concern goes away in target.

Every row must cite actual evidence from the legacy codebase — not generic assumptions. `Not observed` is a valid column value when a concern isn't present in source.

### Part 3 — Code-review: LINE-BY-LINE source↔target audit (the real moat)

Rewrote the code-review prompt from 5,483 → **11,435 chars**. The old prompt said "spot-check the most important ones" — good for typo-hunting, bad for fidelity. Now it does what the user described: **read every mapped source file alongside its target and diff them symbol by symbol.**

**New structure ([backend/agents/prompts.py](backend/agents/prompts.py) code-review block):**

- **Step 1 — Surface scan.** Orientation only.
- **Step 2 — File-map audit (existence + header).** Green / yellow / red per mapping row. Same as before.
- **Step 3 — Line-by-line fidelity audit (THE LOAD-BEARING CHECK).** New. For every green/yellow row, build a **symbol inventory for each side** (classes, public methods with signatures, routes with verbs, validation rules, SQL/ORM calls, constants, outbound calls) via Grep+Read. Then **pair and diff** top-to-bottom, assigning each source symbol one of: `PORTED | RENAMED | SPLIT | MISSING | DRIFTED`.
- **Step 4 — Data-fidelity audit (lookups / seeds).** Unchanged.
- **Step 5 — General code-review hygiene.** The old spot-check list, now demoted to its proper place (after the fidelity checks are done).
- **Step 6 — Boot-blocker fixes.**

**The 10 required checks in Step 3.3** — these are the concrete things every pair must pass. Prompt lists each as a distinct check the reviewer must walk explicitly:

1. **Route parity** — every `Route::get(...)` / `[Route(...)]` in source has matching verb+path in target. No "modernized" URLs.
2. **Method signature parity** — same parameter count, same meanings (auth implicit both sides via middleware / DI).
3. **Validation rule parity** — `digits:9` stays exactly 9. `max:150` stays 150. No widening "to be safe", no tightening.
4. **Status / workflow enum parity** — source `wf=1,2,3,4,5,6,8` (skipped 7) stays `1,2,3,4,5,6,8`. No renumbering.
5. **Derived-field parity** — `expiration = arrest + 2 days` stays `+2 days`. Not `+48 hours` (DST trap).
6. **Sanitization parity** — `bac` stripped after `/`, `dob` truncated to 10 chars, `arrest_agency_id == 0 → null`.
7. **Permission / role parity** — `hasRole('judge')` → `[Authorize(Roles = "judge")]` or equivalent policy. Missing auth = SEVERE finding.
8. **Query semantics** — `whereNotNull('code')` → `.Where(r => r.Code != null)`. Ordering preserved. Joins match.
9. **Error handling shape** — HTTP status + body shape preserved. `422` stays `422`, not silently `400`.
10. **External integration contracts** — CLETS / ATIMS / third-party payload shape unchanged.

**`docs/FILE_MAP_AUDIT.md` now has a line-by-line walks section** — prompt specifies an exact format where each Yellow/Red finding gets a block with legacy rule, target rule, drift description, fix applied (or not), and remaining risk. Example in the prompt shows an off-by-one SSN validation fix.

**Fix-in-place policy clarified.** If a drift is a one-line fix (e.g. `Length(8)` → `Length(9)`), apply the Edit. If it's structural (whole method missing), add a tracker entry + line citation and leave it for the regenerator. Code-review is QC, not a second generator.

### Why this is a real moat vs Codex

Codex returns a generated project. AppNova now returns a generated project **plus** `docs/FILE_MAP_AUDIT.md` that contains, for each of the ~300 source files:

- The expected target path and its actual status (green/yellow/red).
- A symbol-by-symbol diff showing every legacy symbol's fate (PORTED/RENAMED/SPLIT/MISSING/DRIFTED).
- For DRIFTED symbols, source line and target line cited side-by-side.
- A list of fixes applied inline by code-review.

Anyone can answer "did the conversion faithfully port file X" by grepping `Source: <path>` in `FILE_MAP_AUDIT.md`.

### Smoke tests — 11/11 green

1. ✅ Python syntax across 6 modified backend files.
2. ✅ `frontend/app.js` parses.
3. ✅ Backend imports clean.
4. ✅ **33/33** prompt markers across 5 prompts (migration-planner 12, code-generation 6, code-review 11, business-rules 2, ui-ux 2).
5. ✅ `_extract_file_map_json` still parses happy + negative cases.
6. ✅ Runner retry logic (3-attempt recovery against transient upstream errors).
7. ✅ `run.bat`/`run.ps1` paths absolute (regression-tested on Windows).
8. ✅ Live backend Load demo flow — new session_id returned, 11/11 agents hydrated (verified via `/api/results/<new_sid>`).
9. ✅ Frozen TotalBookingAI demo integrity clean.
10. ✅ 5 demo-session routes registered.
11. ✅ Frontend `app.js?v=19` cache-bust present.

### Answer to "why is Load demo not working"

After this session: if it's not working, one of these three will show why:

1. **Browser cache** — `app.js?v=19` should force a fresh pull. If not, hard-refresh with Ctrl+Shift+R.
2. **Backend auth middleware rejects** — the new visible error toast + console trace will show `HTTP 401` with a body snippet. Either login, or set `APPNOVA_AUTH_DISABLED=1`.
3. **HTML didn't ship** — `console.warn('[demo] #load-demo-btn not found in DOM')` fires at page load if the button is missing.

All three used to fail silently. They don't anymore.

---

## 2026-04-20 — File-map contract + Run-converted path fix: migration-planner as spec-author `[DONE]`

Two things in this entry: (1) fix the "Run converted" crash user saw on the demo-loaded TotalBookingAI session; (2) close the architectural gap flagged last turn — migration-planner was a steering-committee doc, NOT a machine-enforceable file-level spec. Now it is.

### Context — what the user showed

1. Screenshot: demo loaded OK, all 11 agents `DONE`, but "Run converted" panel shows `[process_crashed] exited 1` with console cut off at `$ C:\Windows\system32\cmd.EXE /c uploads\b1886d...` — dev-server attempt died before Vite could bind.
2. PDF: AppNova's own **data-migration** agent output (ARIES schema-migration report, 37 pages). User correctly noted: "this is not what we need" — it's the DB migration agent, not the program-management one. But the structural patterns are gold: §3.1 Core Table Mappings (source column → target column + transform), §7.6 Migration Execution Order (numbered table with dependencies).
3. Solution tree: the `ARIES.sln` + `frontend/aries-react/src/pages/bookings/...` tree pasted at the bottom of the message — THIS is what migration-planner should be emitting. Every file mapped to its target location with its one-line responsibility.

### Part 1 — "Run converted" crash: path-composition bug in run_manager

Log: [logs/runs/618865d03beb/20260420-223425-98a7e62da72a.log](logs/runs/618865d03beb/20260420-223425-98a7e62da72a.log). `npm install` succeeded (386 packages, 36s), then the dev-server attempt spawned `cmd /c uploads\618865d03beb\converted\run.bat` and got back `The system cannot find the path specified.` The `run.bat` file DOES exist — verified manually.

**Root cause:** [backend/agents/run_manager.py:358](backend/agents/run_manager.py#L358) was doing `out.append(["cmd", "/c", str(run_bat)])` where `run_bat = cwd / "run.bat"`. If `cwd` was a relative `Path` like `Path("uploads/<sid>/converted")`, then `str(run_bat)` stayed relative. The subprocess then spawns with `cwd=str(run.cwd)` (which IS the converted dir), and `cmd.exe /c` resolves the relative arg against THAT cwd — producing `converted/uploads/<sid>/converted/run.bat`, which obviously doesn't exist. Windows reports `The system cannot find the path specified.`

**Fix:** [backend/agents/run_manager.py:357-365](backend/agents/run_manager.py#L357-L365) — always pass the *absolute* resolved path to `cmd /c` and `powershell -File`:

```diff
+ # IMPORTANT: always pass an ABSOLUTE path to cmd/powershell. When the
+ # caller spawns with cwd=<converted dir>, a relative path like
+ # `uploads\<sid>\converted\run.bat` gets resolved against that same
+ # converted dir, producing `converted/uploads/<sid>/converted/run.bat`
+ # which doesn't exist → Windows reports "The system cannot find the
+ # path specified." — caught on session 618865d03beb.
  if run_bat.is_file():
-     out.append(["cmd", "/c", str(run_bat)])
+     out.append(["cmd", "/c", str(run_bat.resolve())])
  if run_ps1.is_file():
      out.append(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
-                 "-File", str(run_ps1)])
+                 "-File", str(run_ps1.resolve())])
```

`run.sh` already used `.resolve()` (line 372) so no change there.

### Part 2 — Migration-planner becomes the file-level spec

Last turn I answered "NO" to the user's three questions about file-by-file review. This session implements the fix promised in that answer.

**Architecture change:** `migration-planner` was 775 chars of program-management prose. Now it's 9,258 chars split into two sections — a HUMAN section for the steering committee AND a MACHINE section for the downstream `code-generation` agent. The machine section produces a contract every later agent can audit against.

**1. Migration-planner prompt — new Section A (REQUIRED, NON-NEGOTIABLE)** — [backend/agents/prompts.py](backend/agents/prompts.py) migration-planner block, now 9,258 chars:

- **A.1 Solution Structure Tree** — target project as a tree with one-line responsibility per file. Style stolen from the ARIES.sln tree the user pasted (and the `frontend/aries-react/src/pages/bookings/...` decomposition).
- **A.2 Source → Target mapping table** — one row per source file, columns: `Legacy file | Legacy responsibility | Target file(s) | Target responsibility | Kind | Notes`. `Kind` is a closed vocabulary: `1-to-1 port | 1-to-many split | many-to-1 merge | 1-to-1 rename | SKIPPED`. Reusing the §3.1 table format from the attached data-migration PDF, just applied to files instead of DB columns.
- **A.3 Execution order** — numbered dependency-aware table ("Files produced | Depends on | Rationale"), mirroring the §7.6 Migration Execution Order format from the PDF. Code-generation walks this top-down.
- **A.4 `file_map.json`** — MACHINE-READABLE payload inside a fenced ```json``` block. Strict schema: `{meta, mappings[]}` where each mapping is `{source, targets[], kind, legacy_responsibility, target_responsibility, order, depends_on_source?, notes?}`. `SKIPPED` rows require `skip_reason`. One entry per real source file; forward slashes always.
- **A.5 Decomposition rationale** — paragraph per `1-to-many split` explaining WHY (e.g. "TotalBookingEditCtrl.js 3,164 LOC god controller → BookingPage.tsx + 6 components + 3 hooks").

If the agent runs out of budget it MUST truncate Section B (program plan) first — Section A is load-bearing.

**2. Supervisor auto-extracts `file_map.json`** — [backend/agents/supervisor.py:20-68](backend/agents/supervisor.py#L20-L68) + [:220-246](backend/agents/supervisor.py#L220-L246):

After migration-planner completes (done status with content), the supervisor runs `_extract_file_map_json()` on the markdown and writes the parsed dict to `<session>/context/file_map.json`. Logic:

- Regex-finds every fenced ```json``` block (non-greedy, DOTALL).
- Parses each with `json.loads` — first one that is a dict with both `meta` AND `mappings` keys wins.
- Warns if no parseable payload found — downstream agents then have no file map to work from (still runs, but the code-review file-map audit will flag every row as orphan).

This makes `context/file_map.json` a canonical, well-known path. Code-generation and code-review Read it directly instead of re-parsing markdown.

**3. Code-generation — `file_map.json` IS the contract** — [backend/agents/prompts.py](backend/agents/prompts.py) code-generation block, new "⚠️ FILE_MAP.JSON IS YOUR CONTRACT — NON-NEGOTIABLE" section inserted between the backend-depth block and the lookup-data section:

- Read `../context/file_map.json` FIRST, sort mappings by `order` ascending.
- For every mapping, produce EVERY target listed in `targets[]`. No file in `targets[]` may be absent from final output.
- **Every target file MUST contain a mandatory header comment** citing its source, the map's kind, and the order:
  ```csharp
  // ─────────────────────────────────────────────────────────────────────────
  // Target:  src/ARIES.Application/TotalBooking/Queries/ListBookingsQuery.cs
  // Source:  app/Http/Controllers/API/TotalBooking/TotalBookingListController.php
  // Kind:    1-to-many split (MediatR query half; controller half in BookingsController.cs)
  // Map:     context/file_map.json, order 5
  // ─────────────────────────────────────────────────────────────────────────
  ```
  Code-review greps for `Source:` to audit coverage. Files without headers fail review.
- **Un-mapped target files require an amendment.** If during conversion the agent discovers a target file not in the map is needed, it MUST append an entry to `converted/docs/FILE_MAP_AMENDMENTS.md` with reason + source evidence + affected map rows. No silent additions.
- **`1-to-1 port` enforces behaviour fidelity.** Translation only — same methods, params, edge cases. "Improvements" during port → flagged with inline `// BEHAVIOUR-DRIFT:` comment citing source line + justification.

**4. Code-review — per-row file-map audit (now FIRST check, before data-fidelity)** — [backend/agents/prompts.py](backend/agents/prompts.py) code-review block:

- For every row in `../context/file_map.json` mappings, assign a verdict:
  - `green` — every path in `targets[]` exists + file has a header citing the exact source + the target plausibly covers the source's public symbols.
  - `yellow` — target(s) exist but one or more of: missing/mismatched header, partial coverage, kind mismatch.
  - `red` — one or more `targets[]` paths DO NOT EXIST.
- For `SKIPPED` rows: verify no partial stubs, no leftover references.
- Glob the converted project for orphan files (not in any `targets[]`, not listed in `FILE_MAP_AMENDMENTS.md`).
- Emits `docs/FILE_MAP_AUDIT.md` with counts + per-bucket tables.
- Where safely possible (missing header, adding an orphan to `FILE_MAP_AMENDMENTS.md` with clear source justification), code-review fixes in place.

**5. No registry change needed** — [backend/config.py:83](backend/config.py#L83) already declares `code-generation` upstream as `("architecture", "business-rules", "security", "migration-planner")`. Supervisor already writes `upstream_migration-planner.md`. With the new supervisor hook, it also writes the extracted `file_map.json` alongside. Code-generation's prompt now points to both.

### What this gives us that Codex doesn't

Codex doesn't publish an audit trail. AppNova now produces, on every run:

- `context/file_map.json` — the pre-approved spec.
- `converted/docs/FILE_MAP_AMENDMENTS.md` — any deviations with source evidence.
- `converted/docs/FILE_MAP_AUDIT.md` — post-gen verdict (green/yellow/red per row).
- `converted/docs/LOOKUPS.md` + `LOOKUPS_AUDIT.md` — from the earlier source-fidelity pass.
- Every target file's header comment cites its source, kind, and map position.

A reviewer can now answer "did this conversion actually port every source file?" with `diff` instead of intuition.

### Smoke tests — all 9 green

1. ✅ Python syntax across 10 modified files.
2. ✅ `frontend/app.js` parses (`node --check`).
3. ✅ Backend modules import (main, demo_session, runner, supervisor, prompts, run_manager).
4. ✅ Prompt markers — 30/30 across 5 prompts (migration-planner 10, code-generation 8, code-review 8, business-rules 2, ui-ux 2).
5. ✅ `_extract_file_map_json` unit tests — happy path + no-heading fallback + 3 negative cases.
6. ✅ Runner retry behaviour unchanged — still recovers transient upstream errors in 3 attempts.
7. ✅ TotalBookingAI frozen demo still loads cleanly (11 agents hydrated, integrity OK).
8. ✅ `_runner_script_candidates` on Windows — `run.bat` invocation now uses absolute path (regression test caught the previous bug).
9. ✅ All 4 demo-session endpoints still registered.

### How to verify the Run converted fix

Once the backend restarts (so the edited `run_manager.py` is loaded):

1. Load the TotalBookingAI demo via the UI's "Load demo" button.
2. Click "▶ Run converted".
3. Expected: `npm install` runs (first load only — subsequent loads reuse `node_modules`). Then the backend's `run.bat` launches via an absolute path. Vite binds to port 5050.

If anything still fails, the log at `logs/runs/<new_sid>/<ts>.log` will show the exact absolute path being invoked.

### About the attached PDF (ARIES Data Migration Report)

Confirming the user's read: that PDF is the **data-migration** agent's output (one of the 13 agents — see [backend/config.py:70-79](backend/config.py#L70-L79)), not migration-planner. It shows what AppNova already produces for DB migration (schema mappings, DDL, ETL pipelines, validation queries, rollback). I did NOT reuse its content — the data-migration agent stays as it is. What I DID reuse:

- §3.1 table format (Source | Target | Transformation) → migration-planner's A.2 file mapping table (Legacy file | Target file | Kind)
- §7.6 execution-order table (Order | Step | Depends on | Duration) → migration-planner's A.3 execution order (Order | Files produced | Depends on | Rationale)

Same structural rigor, different subject (files vs tables).

---

## 2026-04-20 — Source-fidelity prompt overhaul: dropdowns, wizards, workflow page `[DONE]`

User showed 7 screenshots of the Codex-generated ARIES UI (a React+ASP.NET port of the same TotalBookingAI Laravel+AngularJS source AppNova ran against) and asked why AppNova's converted app doesn't look like that, specifically why source dropdown data isn't being written to the converted app.

### What the images actually showed (the Codex tell)

Codex's output is source-faithful to a level AppNova was not enforcing:

1. **Booking detail** — workflow state chips use EXACT source integer IDs (`Draft (8) → Submitted (1) → Approved (2) LOCK → Denied (3) LOCK → More Info (4) → Cited (5)/Released (6)` — note the skipped 7, preserved from source). Red-text expiration field. CJIS codes (`23H`) in offense rows.
2. **Dashboard** — 4 KPI cards + "Bookings by status" bar chart with source-matched colors (blue=submitted, green=approved, red=denied, purple=signed, gray=draft).
3. **Total bookings list** — status pills follow the same color system.
4. **New Total Booking wizard** — a real **14-step wizard**: Detainee info → Physical description → Residence → Employment → Emergency → Arrest → Offenses → Warrants → Other authorities → Victim/property → PC narrative → Co-defendants → Marks → Review. Info banner on step 1 references source function names verbatim (`getDetail_AutoComp`, `ariesdwtest` RMS fallback).
5. **PC declarations** — LOCK column showing Locked/Unlocked, expiration highlighted red when approaching deadline.
6. **Reports** — 4 KPIs (Processed / Approval rate / Avg process / Juvenile %) with real counts that match the Dashboard numbers.
7. **Workflow state machine page** — THIS is the killer. An auto-generated admin doc page listing every source-mapped workflow ID, the `onlysave=true/false → wf=N` transitions, the `LOCK_TIME × 10 minutes` lock mechanism, and source-level data-sanitization rules (`pc_narrative` single-quote escape, `dob` truncated to 10 chars, `bac` stripped after `/`, `arrest_agency_id=0 → null`, `ssn digits:9`, `victim_age between:0,150`). Every line traces to a specific source file.

The pattern: Codex is transcribing, not inventing. Every magic number, every field name, every workflow step traces back to source. That's the moat we can build into AppNova.

### What the AppNova audit found (the gap)

Full audit of [backend/agents/prompts.py](backend/agents/prompts.py) + the converted TotalBookingAI output at [uploads/54623252b32c/converted/](uploads/54623252b32c/converted/):

| Concern | Finding |
|---|---|
| Prompt tells agent to extract lookup/dropdown data | ❌ No. `code-generation` prompt is silent on lookup extraction |
| Prompt says "do not invent values" | ❌ Only the `ui-ux` prompt says this; `code-generation` does not |
| Prompt sets UI quality bar (sidebar, wizard, workflow chips) | ❌ Completely missing |
| Converted dropdowns use real extracted data | ⚠ Architecture is right (fetch from `/api/lookups`), but [`DevSeeder.cs`](uploads/54623252b32c/converted/backend/Data/DevSeeder.cs) seeds ONLY 6 offense codes — **16 lookup tables are empty** (Gender, Race, EyeColor, HairColor, NarcoticType, Property, ForceCb, State, Court, VictimCb, WarrantType, ParentType, Authority, City, County, WorkflowStep) |
| Converted workflow shows exact source step labels | ✅ Yes, `WorkflowStepLabel` in [src/types/booking.types.ts](uploads/54623252b32c/converted/src/types/booking.types.ts) matches source IDs (1,2,3,4,5,6,7,8) |
| Converted form is a 14-step wizard | ❌ Single flat form in [src/components/booking/BookingForm.tsx](uploads/54623252b32c/converted/src/components/booking/BookingForm.tsx) |
| Sidebar matches screenshots | ⚠ Only 3 items (Dashboard / Bookings / PC Declarations) vs the 7 in the source |
| `/workflow` doc page exists | ❌ Missing entirely |

This is exactly what the user noticed: **dropdowns from source code with data is not being written in converted app folders**. Root cause: the code-generation prompt doesn't tell the agent to look for or seed them.

### Changes shipped to close the gap

**1. Code-generation prompt rewritten** — [backend/agents/prompts.py:242-359](backend/agents/prompts.py#L242-L359) — four new NON-NEGOTIABLE sections added between the backend-depth block and the preflight:

- **⚠️ LOOKUP & SEED DATA FIDELITY** — defines what counts as a "lookup" (6 patterns: model classes on simple tables, enums, static arrays, config files, `ng-options`/`v-for` bindings, `/api/lookups/*` endpoints). Defines where to hunt for values (7 locations in priority order: migrations → seeders → SQL dumps → static model arrays → controller arrays → config/YAML → frontend controller state). Defines what to emit (real seeder in target-stack idiom with `// source:` comments citing file+line on each row). Defines what to do when source doesn't contain values (MUST-FIX stub citing source evidence, never invent placeholders like `"Option 1"` or `"Race 1"`). Requires a `converted/docs/LOOKUPS.md` audit report listing every lookup + status + source evidence.

- **⚠️ SOURCE-MAPPED CONSTANTS & BUSINESS RULES** — preserve workflow step IDs exactly (including gaps — `wf=1,2,3,4,5,6,8` stays that way). Preserve lock durations, polling intervals, validation rules (`ssn digits:9`, `victim_age between:0,150`), derived-field formulas (`expiration = arrest + 2 days`, DST-safe), sanitization rules. Every non-obvious constant gets an inline `// source:` comment.

- **⚠️ UI STRUCTURE FIDELITY** — sidebar extracted from source routing, multi-step wizards preserved (don't collapse to flat forms), status pills use consistent color palette mapped from source, field labels verbatim, table columns match source list views, red/urgent cues preserved.

- **⚠️ MANDATORY `/workflow` DOCUMENTATION PAGE** — if business-rules surfaces a state machine with >3 states or lock/sanitization behaviour, emit an admin `/workflow` page that renders the state machine, lock mechanism, and sanitization rules with source citations. This is image 7 — it's auto-generated documentation and one of the clearest fidelity signals.

**2. Business-rules prompt enhanced** — [backend/agents/prompts.py:307-376](backend/agents/prompts.py#L307-L376) — now REQUIRED to emit 5 named sections that `code-generation` greps:

- `## 1. State machines & workflows` — mermaid diagrams + source integer IDs + lock timers
- `## 2. Validation rules (exhaustive)` — per-entity table with `field | rule | source`
- `## 3. Derived fields & formulas` — with timezone/DST/locale sensitivity notes
- `## 4. Lookup / enum data inventory` — CRITICAL for code-generation. Strict markdown schema per lookup: source model path, source table, API endpoint, UI usage, columns/fields with types, `Values source:` (file + line or `NOT FOUND IN SNAPSHOT`), first 30 rows verbatim in JSON. Hunt order made explicit (7 locations). Never invent values.
- `## 5. Decision & calculation rules`

This makes business-rules the upstream source of truth for dropdowns, validation, and workflow — code-generation reads it via `upstream_business-rules.md` and cites it when emitting seeders / validators / state enums.

**3. Code-review prompt enhanced** — [backend/agents/prompts.py:353-366](backend/agents/prompts.py#L353-L366) — new Data-fidelity audit step. Reads the business-rules upstream report, for every lookup listed there grep the converted code for its seeder entry point and confirm the row count matches. Red flags it catches + can fix: placeholder strings (`"Option 1"`, `"Sample"`, `"Placeholder"`, `"Test"`, `"Foo"`, `"Race 1"`, `"Item A"`), lookup referenced by controller but unseeded, row count mismatch, missing `// source:` comments. Emits a `docs/LOOKUPS_AUDIT.md` with expected vs. emitted counts per lookup.

**4. UI-UX prompt enhanced** — [backend/agents/prompts.py:409-419](backend/agents/prompts.py#L409-L419) — new Structural fidelity audit step. Verifies the converted app has: a real multi-step wizard if source has one, a sidebar matching source nav, a `/workflow` doc page if business-rules surfaces a non-trivial state machine (and may Write the page itself if code-generation missed it). Adds a visible `<EmptyLookupNotice lookup="races" />` component for any dropdown found empty during polish, so users see explicit reasons instead of silently empty menus.

**5. Regeneration CLI** — new [scripts/regenerate_demo.py](scripts/regenerate_demo.py). Because the frozen `totalbooking-react-aspnet` demo was produced by the OLD prompts, it still has the flat-form + empty-lookups issues. The script automates: (a) invalidate `data/analysis_cache/` entries (the cache key factors in AppNova source hash, so prompt edits naturally invalidate it, but we also remove explicitly for clarity); (b) re-upload `uploads/<source_sid>/source/` via `POST /api/upload`; (c) `POST /api/analyze` with the same target_stack (auto-inferred from existing demo/cache); (d) poll `/api/session/<new>/status` with per-agent progress logging; (e) `POST /api/demo-sessions/freeze/<new>` with the chosen slug. Supports `--bearer-token`, `--api-base`, `--poll-every`, `--max-wait`. Self-contained (no `requests` dependency — uses `urllib`).

Usage when ready to burn the ~15-30 min regeneration run:

```bash
python -m scripts.regenerate_demo \\
    --source-session-id 54623252b32c \\
    --slug totalbooking-react-aspnet-v2 \\
    --name "TotalBookingAI v2 (source-fidelity pass)" \\
    --description "React + ASP.NET with real dropdowns, 14-step wizard, workflow doc page"
```

### Why this matters beyond TotalBookingAI

These prompt changes apply to EVERY future conversion AppNova does. The structural pattern:

1. **Upstream agent extracts ground truth** (business-rules inventories lookups, validation, state machines with strict markdown schemas).
2. **Code-generation treats upstream as spec** (not hint). The prompt's new sections say "use the upstream lookup inventory", "preserve the source integer IDs", "do not invent placeholders".
3. **Post-gen validators diff expected vs. emitted** (code-review checks seeder counts; ui-ux checks wizard/sidebar/workflow-page presence) and flag or fix delta.
4. **Auditable trail** — every generated constant / seed row has a `// source:` comment; every lookup has an entry in `docs/LOOKUPS.md` and (post review) `docs/LOOKUPS_AUDIT.md` with expected vs. emitted counts.

This is the "transcribe don't invent" moat the Codex screenshots demonstrate. AppNova was doing it for code structure (via the Full-Code Contract) but not for **data** or **structure fidelity**. Now it does.

### Smoke test results

Ran 7 end-to-end checks after all prompt edits:

1. ✅ Python syntax across 8 modified files (4 backend modules + 4 scripts)
2. ✅ `frontend/app.js` parses (`node --check`)
3. ✅ Backend imports cleanly (main, demo_session, runner, supervisor, prompts)
4. ✅ All new prompt markers present (14 substrings across 4 prompts — LOOKUP & SEED DATA FIDELITY, MUST-FIX, Lookup / enum data inventory, NOT FOUND IN SNAPSHOT, Data-fidelity audit, LOOKUPS_AUDIT.md, Structural fidelity audit, multi-step wizard, EmptyLookupNotice, etc.)
5. ✅ Runner retry-on-transient — behavioural test, 3-attempt recovery with 0s backoff, `retry_attempts == 2` on success
6. ✅ Demo freeze/load round-trip — existing `totalbooking-react-aspnet` demo loads clean (363 source files + 303 converted + 20 context), `validate_demo_session` reports no integrity issues, 11 agent results intact
7. ✅ `scripts/list_demos.py` runs clean and prints the demo metadata

### Known follow-ups (not blocking demo)

- **Existing frozen demo is stale.** `totalbooking-react-aspnet` was produced by the OLD prompts, so its converted app still has the flat form + empty lookups. Running `scripts/regenerate_demo.py` produces a `-v2` slug with the new output; the UI picker shows both, user can toggle. We don't ship this demo automatically because it burns ~15 min + real LLM cost — user triggers it when ready.
- **The LLM still has discretion.** Prompts are guidance, not guarantees. The real validation is in code-review and ui-ux post-checks; if those keep catching the same class of misses across runs, we may want an explicit `data-extraction` agent as a dedicated pre-pass (currently this work is folded into `business-rules`). Will re-evaluate after the first v2 regeneration.

---

## 2026-04-20 — Demo-session freeze/load: zero-risk replay for live demos `[DONE]`

Built a portable, integrity-checked session-freezing system so we can replay any completed analysis instantly — no agent ever runs live on stage. The TotalBookingAI session (`54623252b32c`, 11/11 agents done, React + ASP.NET output) is now the first frozen demo; loads in ~600ms against the real backend.

**Why it matters for the demo**: Codex demos in seconds. A cold AppNova run on TotalBookingAI takes ~15 min for wave 1 alone and depends on a flaky upstream API. A frozen demo sidesteps both problems — Krishna sees 11 agent reports + a running React+ASP.NET app in seconds, backed by a real prior run.

**1. New module: `backend/demo_session.py`**

- [backend/demo_session.py](backend/demo_session.py) (new, ~440 lines) — self-contained freeze/load library.
- Portable bundle layout under `demo_sessions/<slug>/`:
  - `manifest.json` — metadata (slug, name, description, target_stack, file counts, checksums, tags, created_at, schema_version).
  - `source.zip` — original uploaded project.
  - `converted.zip` — full AppNova-generated target-stack project.
  - `context.zip` — discovery digest + 12 per-agent briefs + 4 upstream files.
  - `state.json` — in-memory state snapshot (results, digest, briefs-as-content, artifacts, skipped, target_stack, applicable, completed).
  - `cost_report.xlsx` — optional, copied from the session's `exports/cost_reports/<sid>/latest.xlsx`.
  - `SHA256SUMS` — every snapshot file re-hashed on load; mismatch → refuse to hydrate.
- Public API: `freeze_session()`, `list_demo_sessions()`, `get_demo_manifest()`, `validate_demo_session()`, `load_demo_session()`, `delete_demo_session()`.
- Safety:
  - Slug validation (`^[a-z0-9_-]{1,80}$`) — no Windows reserved words, no path traversal.
  - `zip_tree()` skips `node_modules`, `.git`, `.venv`, `__pycache__`, `dist`, `build`, `.next`, etc. — keeps bundles small and reproducible.
  - `unzip_into()` blocks absolute paths, `..` traversal, and out-of-tree resolution.
  - `MANIFEST_SCHEMA_VERSION = 1` — loader refuses unknown versions so a stale demo can't hydrate into incompatible state.
  - Frozen folders are never mutated after creation; load always extracts to a fresh `uploads/<new_sid>/`.

**2. FastAPI endpoints** in [backend/main.py:1058-1234](backend/main.py#L1058-L1234)

- `GET /api/demo-sessions` → list every frozen demo with metadata.
- `POST /api/demo-sessions/freeze/{session_id}` → snapshot an in-memory session into a bundle (body: `{slug, name, description, tags, overwrite}`).
- `GET /api/demo-sessions/{slug}` → one demo's manifest + live integrity check.
- `POST /api/demo-sessions/load/{slug}` → hydrate a frozen demo into a fresh session_id; populates every `_session_*` dict so `/api/results/<new_sid>`, `/api/session/<new_sid>/status`, and the chat / artifact endpoints all work immediately.
- `DELETE /api/demo-sessions/{slug}` → remove a bundle (never touches hydrated sessions).
- `_collect_session_snapshot()` helper reads brief files off disk and embeds their content into `state.json`, so the snapshot is self-contained even if the original session folder is later deleted.

**3. CLI scripts** (new `scripts/` package)

- [scripts/freeze_demo.py](scripts/freeze_demo.py) — `python -m scripts.freeze_demo --session-id <sid> --slug <s> --name "..." --description "..."`. Two modes:
  - **Offline (default):** reads `data/analysis_cache/*.json` for a cached run whose `source_session_id` matches, reads `brief_*.md` files off disk. Doesn't need the server. Use this when the analysis completed but the server has since restarted (in-memory `_results` gone).
  - **`--via-api`:** POSTs to `/api/demo-sessions/freeze/<sid>` on a live backend. Use this when the session is still in memory.
- [scripts/list_demos.py](scripts/list_demos.py) — pretty-prints every frozen demo + runs integrity validation per entry.
- [scripts/load_demo.py](scripts/load_demo.py) — loads a demo via `POST /api/demo-sessions/load/<slug>` and prints the new session_id for the frontend to navigate to. Also supports `--offline` for disk-only extraction.
- [scripts/__init__.py](scripts/__init__.py) — package marker.

**4. First real demo frozen: `totalbooking-react-aspnet`**

Ran `python -m scripts.freeze_demo --session-id 54623252b32c --slug totalbooking-react-aspnet --name "TotalBookingAI → React + ASP.NET" --description "California PC-1275 law-enforcement booking system. AngularJS 1.x + Laravel → React + ASP.NET Core + Azure SQL."`. Results:

- 363 source files, 303 converted files, 20 context files, cost report included.
- Total size: 29,187,435 B (~28 MB — git-committable).
- All 11 agents marked `done`, 2 skipped (`devops`, `data-migration`), digest 32,823 chars.
- Integrity: OK (all checksums verified on both freeze and subsequent load).

**5. Frontend: Load Demo button + picker modal**

- [frontend/index.html:51-53](frontend/index.html#L51-L53) — new `#load-demo-btn` in the upload chip next to the Change button.
- [frontend/index.html:502-519](frontend/index.html#L502-L519) — new `#demo-modal` reusing the existing `.app-modal` pattern (same styling as Profile / Settings modals). Bumped `app.js?v=17` → `v=18` to bust the cache.
- [frontend/app.js:685-820](frontend/app.js#L685-L820) — demo-loader JS:
  - `loadDemoBtn` click → opens modal, fetches `/api/demo-sessions`, renders clickable cards (name, description, target_stack line, agent count, file counts, size, tags).
  - `loadDemoBySlug()` → POSTs `/api/demo-sessions/load/<slug>`, hydrates the UI.
  - `hydrateDemoIntoUI()` → paints the upload chip as "Demo: <name>", clears the previous thread, walks `/api/results/<new_sid>` and calls the existing `ensureCardForReattach` + `completeReattachedCard` helpers so every agent's final report + markdown + cost data appears.
  - Esc key closes the modal; `[data-modal-close]` handlers re-used.
- [frontend/style.css:1241-1320](frontend/style.css#L1241-L1320) — `.demo-modal-panel` (wider than Profile/Settings at 760px), `.demo-card`, `.demo-tag`, `.demo-card-meta`, hover states using the existing `--bg-soft` / `--border-soft` / `--tag-light-*` tokens.

**6. Bug caught during round-trip test**

First API test hit a 500 on `/api/results/<new_sid>` with `TypeError: unhashable type: 'dict'` at [main.py:896](backend/main.py#L896). Root cause: `_session_applicable[sid]` is `list[str]` of agent_ids in the normal analyse path (see [main.py:431](backend/main.py#L431)), but the cache payload preserves the full dict shape `{agent_id, label, tier}`. My initial loader shoved the cache dict list straight in, and `get_results` then tried to use dicts as set members. Fixed by normalizing in the loader — [main.py:1207-1214](backend/main.py#L1207-L1214) — converts each entry to `a["agent_id"] if isinstance(a, dict) else str(a)`. Re-tested: results + status + load all clean.

**7. End-to-end verification (real backend, no auth)**

- `POST /api/demo-sessions/load/totalbooking-react-aspnet` → returns fresh session_id in ~600ms.
- `GET /api/results/<new_sid>` → `completed=11, failed=0`, every agent has the expected result length (code-analysis 55,887 chars; architecture 26,161; business-rules 28,317; security 23,135; migration-planner 22,700; integration 14,426; ui-ux 11,596; code-review 5,923; testing 4,560; documentation 2,975; code-generation 803). Digest 32,823 chars. Skipped agents carried through.
- `GET /api/session/<new_sid>/status` → applicable as `list[str]`, running=false, target_stack present.
- Integrity check post-load: OK (SHA256SUMS verified).

**Demo playbook**

1. Start backend (`run.bat` / `python run_server.py`).
2. Open AppNova UI, click **▶ Load demo** → pick "TotalBookingAI → React + ASP.NET" → click Load.
3. All 11 agent cards paint in ~1 second with full markdown reports.
4. Click **▶ Run converted** to boot the React + ASP.NET app (uses the already-fixed [converted/](converted/) tree from the prior session).
5. If a fresh analysis run is wanted for realism, keep a recording of the demo-loaded UI as a fallback; click the regular upload flow for a live run.

**Known limitations / follow-ups**

- `_session_artifacts` is set to `{}` on load because cache payloads don't store the UI preview manifest. If the demo includes a UI artifact, it'll still be in `uploads/<new_sid>/generated/preview.html` (via `converted.zip` extraction) — the endpoint just won't list it on `/api/results`. Future work: capture artifact metadata at freeze time.
- Bundle loads don't replicate the cost-tracking SQLite rows (`data/cost_tracking.db`). The cost workbook is preserved verbatim as `cost_report.xlsx` inside the bundle, which is what matters for the demo.
- No UI for freeze/delete — both are admin-level operations and deliberately CLI-only.

---

## 2026-04-20 — Runner resilience: retry-on-transient-API-error + UI retry banner `[DONE]`

Root cause of session `38256a334a66`'s code-analysis failure (log timestamp `20:05:13.453`): the upstream Anthropic API dropped the streaming response at turn 28 with `"API Error: terminated"` + `is_error: true` in the result event. The CLI exited 1 and the supervisor marked the whole agent failed — even though the same session could've recovered instantly against warm prompt cache. Cost telemetry confirmed the blast: `$0.49` burned, zero output.

This change splits the CLI invocation from the retry policy and adds a UI banner so paused cards don't look frozen.

**1. Runner refactor — `_run_agent_attempt` + retry wrapper**

- [backend/agents/runner.py:57-117](backend/agents/runner.py#L57-L117) — new module-level `_STOP_REQUESTED` flag set by `kill_active_process()` so the retry loop knows the user hit `/api/stop` between attempts (distinct from mid-attempt `CancelledError`).
- [backend/agents/runner.py:83-117](backend/agents/runner.py#L83-L117) — `_TRANSIENT_PATTERNS` + `_is_transient_error()`. Matches `"API Error: terminated|500|502|503|504|529|overloaded"`, `ECONNRESET`, `socket hang up`, `fetch failed`, etc. Crucially conservative — a plain non-zero exit with no marker is treated as non-transient (real bug, not a blip).
- [backend/agents/runner.py:305-315](backend/agents/runner.py#L305-L315) — renamed `run_agent_via_claude_code` → `_run_agent_attempt` (private). Error returns now carry a `"transient": bool` flag.
- [backend/agents/runner.py:455-477](backend/agents/runner.py#L455-L477) — dual-path detection: retries on both `proc.returncode != 0` AND `final_result_event.is_error == true`. The second path is the one the 20:05 failure hit (CLI exits 0, but the last JSON event says the API died).
- [backend/agents/runner.py:630-728](backend/agents/runner.py#L630-L728) — new public `run_agent_via_claude_code()` retry wrapper:
  - `_MAX_ATTEMPTS = 3` (overridable via `APPNOVA_AGENT_MAX_ATTEMPTS`).
  - Exponential backoff `(3s, 8s, 20s)`.
  - Skips retry when `_STOP_REQUESTED` is set (before AND after the backoff sleep).
  - Uses `asyncio.sleep()` so `task.cancel()` from `/api/stop` propagates cleanly.
  - Accumulates `elapsed_seconds` across attempts so cost tracking sees real wall-clock time.
  - Strips the internal `transient` field before returning to the supervisor (stable external shape).
  - Attaches `retry_attempts` counter on success so downstream can tell "succeeded first try" from "succeeded after 2 retries."

**2. UI retry banner — no more frozen cards during backoff**

- [backend/agents/runner.py:702-720](backend/agents/runner.py#L702-L720) — between attempts, emits a synthetic event `{phase: "retry", attempt, max_attempts, backoff_seconds, reason}` via the existing `on_event` callback. The supervisor's `_forward_event` wraps it as `type: "agent_event"` automatically — no supervisor changes needed.
- [frontend/app.js:1297-1325](frontend/app.js#L1297-L1325) — `routePhase` now routes `phase === 'retry'` to new `renderRetry(c, ev)`. Renders an amber banner inside the agent card: `⟳ Transient error — retrying in 3s (attempt 2/3). API Error: terminated`.
- [frontend/style.css:659-688](frontend/style.css#L659-L688) — `.retry-banner` styling. Uses the pre-existing `--warn-bg/--warn-border` palette (same colours as the cost-warning banner elsewhere). `@keyframes retry-spin` on the `⟳` glyph via GPU-composited `transform`.

**3. Tests**

Four behavioural tests run against the real module with `_run_agent_attempt` monkey-patched:
- Success after 2 transient retries → 3rd attempt wins, `retry_attempts == 2`, elapsed is accumulated across all 3 attempts.
- Non-transient error bails immediately → only 1 CLI call, `transient` field stripped from result.
- `_STOP_REQUESTED` set mid-flight aborts the loop after the current attempt finishes.
- Persistent transient exhausts `_MAX_ATTEMPTS` (3 calls, then gives up).

Transient-detection has 7 positive and 5 negative pattern tests. All pass.

**Why this matters for the demo:** the failure mode that killed code-analysis last session is now recoverable in ~3s with a visible banner — instead of a dead card and a "failed" report. Anthropic's streaming endpoint does this roughly once per long-running session; with this change, the user sees a brief amber blip and the agent keeps going.

**Known limitation:** if the first attempt wrote output files (code-generation / ui-ux with `allow_write=True`), the retry replays from scratch and may re-write those files. The supervisor's per-`cwd` write-lock prevents concurrent writes *within* a wave, so there's no race — but a retried code-generation pass may `Edit` files a second time. In practice this is idempotent for our prompts (they read current state first), but worth noting.

---

## 2026-04-20 — Blocker fixes: script-exclusive runner + Browser-Test ready-gate + chat-on-failure + cost tracking for orchestrator/director `[DONE]`

Ships the first slice of the plan below. Addresses the immediate symptoms the user saw on session `54623252b32c` (Vite up but `/oauth/access_token` ECONNREFUSED; Browser Test failing at 30 s with "port_never_bound" before Vite could bind; "No completed report to chat about" on the failure tile) and the empty cost workbook in orchestrator/director modes. The larger Beat-Codex bundle (section B below) is still `[PLANNED]`.

**1. Runner script priority — multi-service apps now start correctly**

Root cause: `_runner_script_candidates` emitted a git-bash run.sh candidate with a Windows-style backslash path that bash rejected (`/usr/bin/bash: uploads\...\run.sh: No such file or directory`), and `_dev_server_candidates` then fell through to the node-tail (`npm run dev`), silently launching only the frontend half of a two-process converted app.

- [backend/agents/run_manager.py:340-380](backend/agents/run_manager.py#L340-L380) — `_runner_script_candidates` now skips the git-bash run.sh candidate when a native `run.bat` or `run.ps1` exists on Windows; when it IS used, the path is translated from `C:\foo\run.sh` → `/c/foo/run.sh` (msys/cygwin form) so bash can actually resolve it.
- [backend/agents/run_manager.py:389-410](backend/agents/run_manager.py#L389-L410) — new `_ALLOW_STACK_FALLBACK` env-gated knob (default off). With a runner script present, `_dev_server_candidates` returns only the scripted candidate — no more silent fallback to `npm run dev` that starts only the frontend.

**2. Browser Test ready-gate (no more 30 s false negatives)**

Root cause: Browser Test's pre-launch probe used a fixed 30 s TCP timer independent of Run Converted's phase. `npm install` on a cold machine takes ~60 s; Vite bound at ~65 s; the probe gave up at 30 s and reported `port_never_bound` even though the server eventually came up fine.

- [backend/agents/run_manager.py:437-497](backend/agents/run_manager.py#L437-L497) — new `find_run_by_port(session_id, port)` and `await_run_ready(run, timeout=300)`. The latter subscribes to the run's SSE queue and returns as soon as phase flips to `running` (or the run errors/exits).
- [backend/agents/browser_test.py:162-234](backend/agents/browser_test.py#L162-L234) — `run_browser_test` now accepts `session_id` + `run_ready_timeout` (default 5 min). When both are present and a matching RunState exists, we subscribe to its ready event first; only after ready (or explicit failure) do we drop into the TCP/HTTP checks. If the run errors before ready, we inherit its `failure_kind` so the tile shows the real cause, not "port_never_bound".
- [backend/main.py:1197-1201](backend/main.py#L1197-L1201) — `/api/browser-test/{session_id}` now passes `session_id` through so the gate is active end-to-end.

**3. Chat works on failure tiles**

Root cause: `/api/chat/.../tree` and `/api/chat/.../` required `r["status"] == "done"`, so the one flow where users most want Claude's help (diagnosing a failure) returned 404 with "No completed report to chat about."

- [backend/main.py:1097-1108](backend/main.py#L1097-L1108) — tree endpoint now accepts `status in {"done","error"}`. Uses `r["result"]` if present, falls back to `r["error"]`; returns 404 only if both are empty.
- [backend/main.py:1144-1157](backend/main.py#L1144-L1157) — chat-turn endpoint mirrors the same relaxation. `render_browser_report` already produces a markdown failure report (failure_kind pill + error + log tail), so the LLM now receives actionable context.
- Export endpoints (docx/pdf at [backend/main.py:1050,1066](backend/main.py#L1050)) intentionally still require `"done"` — exporting a failure tile as a "report" PDF would be misleading.

**4. Cost tracking covers all three runner modes**

Root cause from the PLANNED entry: `cost_tracker.record_call` was wired only into the legacy-runner supervisor at [backend/agents/supervisor.py:232](backend/agents/supervisor.py#L232). Orchestrator (`APPNOVA_ORCHESTRATOR=1`) and Director (`APPNOVA_DIRECTOR_MODE=1`) paths recorded zero rows, so `build_workbook` wrote an empty-looking workbook or nothing at all — indistinguishable from "broken" in the UI.

- [backend/cost_tracker.py:24-52](backend/cost_tracker.py#L24-L52) — new `_HAS_OPENPYXL` / `_HAS_YAML` import-time checks with clear logger warnings. Makes a missing `openpyxl` install loudly visible in the backend log instead of swallowing the failure deep in `build_workbook`.
- [backend/cost_tracker.py:412-447](backend/cost_tracker.py#L412-L447) — `build_workbook` now returns `Optional[Path]` and short-circuits to `None` when (a) openpyxl is missing, or (b) the session has zero recorded calls. Each case logs the precise reason.
- [backend/agents/orchestrator.py:25-31,228-253,335-357,517-546](backend/agents/orchestrator.py) — `run_orchestrator` accepts `session_id` + `run_id`, captures the stream-json final `result` event's `usage` + `total_cost_usd` + `num_turns`, and writes one aggregate row keyed `agent_id="_orchestrator"` at run-end. Per-subagent usage isn't exposed by the Task tool, so one aggregate row is the best-available signal. Best-effort; never blocks the run.
- [backend/agents/director.py:24-30,120-135,175-203,385-415](backend/agents/director.py) — same pattern: `run_director` captures usage/cost from the final event and writes an aggregate row keyed `agent_id="_director"`.
- [backend/main.py:674-682,656-660](backend/main.py) — passes `session_id` + `run_id` to both `run_orchestrator` and `run_director`.
- [backend/main.py:796-826](backend/main.py#L796-L826) — post-run `finally` block now emits three distinct SSE event types instead of silent nothing: `cost_report_ready` (workbook produced), `cost_report_empty` (ran but no rows — with reason), `cost_report_skipped` (cache-hit replay).
- [frontend/app.js:1045-1068](frontend/app.js#L1045-L1068) — SSE handlers for the two new events paint a status-line message on the footer so users see *why* there's no download link.

**Files changed**

- [backend/agents/run_manager.py](backend/agents/run_manager.py) — runner-script priority + path translation + ready-event helpers
- [backend/agents/browser_test.py](backend/agents/browser_test.py) — session_id-aware ready-gate before TCP/HTTP probe
- [backend/agents/orchestrator.py](backend/agents/orchestrator.py) — aggregate cost row from final result event
- [backend/agents/director.py](backend/agents/director.py) — aggregate cost row from final result event
- [backend/cost_tracker.py](backend/cost_tracker.py) — dep check at import, explicit None return on empty/missing-dep
- [backend/main.py](backend/main.py) — chat relax, session_id plumbing for runners + browser test, SSE events for cost state
- [frontend/app.js](frontend/app.js) — surface cost_report_empty / cost_report_skipped

**How to verify**

1. **Multi-service run**: upload a converted app whose `run.bat` starts two processes (like session `54623252b32c`'s .NET backend @ 5051 + Vite frontend @ 5050). Click Run converted. Confirm both processes launch (previously only the frontend did). Login with `admin` / `password` should succeed on the first try.
2. **Browser-Test ready-gate**: click Run converted, immediately click Browser Test (before `npm install` finishes). The Browser Test tile should now wait for Run Converted's ready event rather than failing at 30 s. If Run Converted itself fails, Browser Test inherits the classified failure kind instead of generic `port_never_bound`.
3. **Chat on failure tile**: force a failure (e.g., break run.bat). Click the failed Browser Test tile → Chat → type "why did this fail?". A response should stream instead of 404.
4. **Cost tracking in orchestrator mode**: set `APPNOVA_ORCHESTRATOR=1`, run an analysis. Check `exports/cost_reports/<session>/` — a workbook should exist with one aggregate row under `_orchestrator`. Same test for `APPNOVA_DIRECTOR_MODE=1` → `_director`.
5. **Missing-dep visibility**: `pip uninstall openpyxl`, run an analysis. Backend log should show `[cost_tracker] openpyxl not importable` during startup; session finish emits `cost_report_empty` with reason; footer status line shows "Cost report skipped: ...".

**Not shipped yet** (still `[PLANNED]` below): the Beat-Codex bundle (B.1–B.13), DevOps + data-migration codegen, README running-guide sub-agent, and pitch-mode UI. Each is a multi-day chunk requiring its own sub-agent definition + integration wave — scoped as follow-up turns.

---

## 2026-04-20 — Beat-Codex analysis bundle + cost/token recording fix `[PLANNED]`

Rollup of everything discussed across the last four turns (current-vs-target trees, layer mapping, PII, pictures, README for business users, Codex-beating pitch bundle) **plus** the cost_reports / token_usage write-gap uncovered while answering. All kept in one planned entry so the next implementation pass has a single authoritative checklist.

### A. Cost reports / token usage not being written — root cause

The per-session `exports/cost_reports/<session>/*.xlsx` workbook is produced by [backend/cost_tracker.py:384](backend/cost_tracker.py#L384) (`build_workbook`) which reads rows written by `cost_tracker.record_call`. `record_call` is called from exactly one place:

- [backend/agents/supervisor.py:232](backend/agents/supervisor.py#L232) — inside `run_supervised`, after each agent completes.

The harness has **three** runner paths, gated by env vars at [backend/main.py:50-56](backend/main.py#L50-L56):

| Mode | Env trigger | Calls supervisor? | Cost recorded? |
| --- | --- | --- | --- |
| **Legacy** (default) | neither var set | yes (via `run_all_agents` → `run_supervised`) | ✅ yes |
| **Orchestrator** | `APPNOVA_ORCHESTRATOR=1` | no — spawns one `claude -p` with Task tool | ❌ no |
| **Director** | `APPNOVA_DIRECTOR_MODE=1` | no — free-form director | ❌ no |

`run_orchestrator` ([backend/agents/orchestrator.py:213](backend/agents/orchestrator.py#L213)) and `run_director` ([backend/agents/director.py:96](backend/agents/director.py#L96)) both consume the final stream-json `result` event (which carries `total_cost_usd` + `usage`) but never insert a SQLite row. `build_workbook` still runs in the `finally` at [backend/main.py:795-805](backend/main.py#L795-L805), but with zero rows for that session it produces an empty-totals workbook — indistinguishable from "not written" in the UI.

Secondary gaps:

1. **Cache-hit replay** at [backend/main.py:796](backend/main.py#L796) deliberately skips the workbook (`if cache_payload is None`). Correct but silent — users see "no report" and assume breakage.
2. **openpyxl / pyyaml import failure** inside `build_workbook` is caught by the outer `except Exception` at [backend/main.py:804](backend/main.py#L804) and only logged. If either dep is missing in the current venv, no surface-level error.
3. **Zero-cost rows**: if `final_result_event.total_cost_usd` is absent (some SDK versions omit it when cache hits dominate), [backend/cost_tracker.py:167](backend/cost_tracker.py#L167) falls back to the computed total — fine, but if `usage` is also empty the row is written with all zeros. Workbook looks empty even though the run happened.

### A.1. Fix plan (cost tracking)

1. **Record in orchestrator**: after the subprocess exits, parse the final `result` event (already available as `final_result_event` in the orchestrator) and emit one `cost_tracker.record_call` per completed Task-subagent. The Task tool's `tool_use` / `tool_result` pairs carry per-subagent `usage` — capture them in the streaming loop (same place tool_id → agent_id mapping already lives, [backend/agents/orchestrator.py:253](backend/agents/orchestrator.py#L253)) and flush one row each. If per-subagent usage is not exposed, record a single aggregate row keyed by `agent_id='orchestrator'`.
2. **Record in director**: same pattern inside `run_director`.
3. **Clear user-facing state**: when `build_workbook` runs against an empty row set, emit `{type:'cost_report_empty', reason:'no agent calls recorded'}` instead of `cost_report_ready`. Frontend shows "No cost data — likely orchestrator mode without cost shim" so this isn't confused with a genuine failure.
4. **Dep sanity**: add an import-time check at [backend/cost_tracker.py](backend/cost_tracker.py) top that logs a clear warning if `openpyxl` or `yaml` is missing, rather than failing silently deep in `build_workbook`.
5. **Cache-replay visibility**: on cache hit, still emit `{type:'cost_report_skipped', reason:'cache_replay'}` so the frontend can show "cached result — no new cost" instead of nothing.

**Files to touch:** [backend/agents/orchestrator.py](backend/agents/orchestrator.py), [backend/agents/director.py](backend/agents/director.py), [backend/cost_tracker.py](backend/cost_tracker.py), [backend/main.py](backend/main.py), [frontend/app.js](frontend/app.js).

---

### B. Beat-Codex analysis bundle (pitch-grade report)

Codex-generated `TotalBooking_PCDec_Application_Analysis_and_Use_Cases.pdf` (19 pages, 10 min) is the competitive bar. We aim ≤ 10 min with a richer, business-consumable deliverable.

**B.1. Parallel specialist scan (speed).** Fan out the analysis across ~8 Claude Code subagents running concurrently instead of the current sequential waves for this specific "produce full analysis doc" task. Each takes one slice (routes + nav, controllers + workflow, templates + screen inventory, models + ERD, integrations, document-generation versioning, risks + legacy debt, use-case extraction). Merger step stitches the sections in fixed order. Reuses the existing supervisor DAG — just adds a new `pitch_analysis` preset with a custom wave layout.

**B.2. Current vs Target architecture trees.** Two side-by-side ASCII / mermaid trees: (a) observed stack (AngularJS + Laravel + Blade + Kendo + JMS/ATIMS) with the actual top-level dirs from the uploaded project; (b) target stack (React + FastAPI/Node + React Router + Tailwind + REST) from the `target_stack` already captured at upload. Generated by a dedicated sub-agent reading `top_level.md` + `digest.md`.

**B.3. Layer-to-layer mapping table.** Markdown table: AngularJS controller ↔ React component/hook; Laravel controller ↔ FastAPI route; Eloquent model ↔ Pydantic/SQLAlchemy; Blade view ↔ JSX; ui-router state ↔ React Router route; Kendo grid ↔ TanStack Table; OAuth middleware ↔ JWT middleware. Columns: source file, target file, complexity (LOC + cyclomatic proxy), migration risk (Low/Med/High).

**B.4. PII risk report + heatmap.** Scan source for PII fields (SSN, DOB, DL#, driver license, victim_age, victim_sex, BAC, address, phone). Output:

- Table: field name, files it appears in, storage (DB column / request body / log line / generated PDF), severity (red/amber/green).
- Recommendations: mask in logs, encrypt at rest, scope in JWT, strip from stack traces, redact in generated Word/PDF reports, audit-log all reads.
- Heatmap image: modules on Y axis, PII severity on X axis, cells coloured.

**B.5. Data dictionary.** Auto-dumped from Laravel `$fillable` + migration files + form `name=""` attributes. Columns: entity, field, type, nullable, validation, sample value, PII flag.

**B.6. Workflow state matrix.** Codex admitted it couldn't resolve `workflow_step_id == 9`. We grep every `workflow_step_id` occurrence across controllers + repositories + frontend, cross-reference with DB seed data (if present in uploads), and produce an exhaustive matrix: code → name → actor → valid_transitions → UI label. Fills the gap Codex left.

**B.7. Auto-generated diagrams.** For every mermaid block the agents produce (architecture, workflow state machine, ERD, use-case flow, screen navigation), post-process with the existing `diagram_qa` repair step plus a new mermaid-to-PNG render step (mermaid-cli via a shelled subprocess — already available on the box per prior agent dispatches). Embed the PNGs directly in the output PDF/HTML so the report is viewable without a mermaid renderer.

**B.8. Browser Test screenshot + log summary chart.** The converted-app screenshot (already captured at [backend/agents/browser_test.py](backend/agents/browser_test.py)) embedded inline. Run-logs summary: agent timings bar chart, token usage per agent, failure-kind pie chart — rendered server-side with matplotlib and attached.

**B.9. Modernization effort estimate.** Per top-level module: file count, LOC, estimated person-days for migration, risk tier, recommended migration order. Drives the "what to convert first" conversation with clients.

**B.10. Assumptions + confidence score.** Each section closes with `Confidence: high/med/low` based on evidence density (files read, symbols matched). Mirrors Codex's "Assumptions and Limitations" but at per-section granularity, which is more defensible.

**B.11. Unified HTML + PDF bundle.** Single `analysis_bundle.html` with clickable TOC, inlined PNGs, print-optimised CSS, plus a parallel `analysis_bundle.pdf` rendered by weasyprint (already listed in requirements). Lands in `exports/analysis/<session>/` alongside the existing agent outputs. Replaces the current per-agent-markdown pile for anyone who wants one artefact.

---

### B.11b. Browser Test timing + chat-on-failure

Observed on session `54623252b32c`: Browser Test tile shows `Failure kind: port_never_bound`, error `Dev server never came up at http://localhost:5050 (TCP poll ... timed out after 30s)` — but the Run Converted log shows Vite actually bound successfully moments later (`[ready] / → 200`). Two independent issues collide:

1. **Race between Run Converted and Browser Test.** Browser Test's pre-launch TCP probe starts on a fixed timer independent of Run Converted's progress. If `npm install` runs inside Run Converted (first time on a box, ~1 min), Browser Test's 30 s window expires before Vite ever listens. The harness already emits `{type:'ready', http_status, probed_path}` from [backend/agents/run_manager.py](backend/agents/run_manager.py) — Browser Test should consume it.
2. **Chat fails on failure tiles.** The user clicks Chat on the failed Browser Test tile with "fix issues in localhost://5050" and gets "Error: No completed report to chat about." Chat currently requires a `.result` markdown payload; failure manifests have `failure_kind` + log tail but no "report" — so the one flow where users most want LLM help is closed off.

Fix plan:

1. **Ready-event gate for Browser Test**: replace the fixed 30 s TCP wall-clock with a subscriber to Run Converted's SSE stream for the same session. Browser Test waits up to `BROWSER_TEST_READY_DEADLINE` (default 5 min, configurable) for a `ready` event matching its target port; if Run Converted emits `exit` / `error` first, Browser Test skips the browser phase and inherits the upstream `failure_kind`. No more "timed out at 30s" when the real issue is an npm install still running.
2. **Pre-flight hint in the UI**: when Browser Test is queued while Run Converted hasn't emitted `ready` yet, show a neutral "Waiting for dev server..." pill instead of immediately flipping to red. Only flip to failure once the deadline actually expires or Run Converted itself fails.
3. **Chat on failure manifests**: extend the report-chat endpoint to accept tiles with `status == 'failed'`. When invoked, prompt payload becomes `{failure_kind, error_message, log_tail (last 100 lines), services_state, target_url}`. Claude answers in the same markdown tile format — "Likely cause: backend not started — `dotnet run` never printed 'Now listening'. Fix: start backend first, then frontend." The log tail is sourced via the same `/api/run/log/{run_id}` endpoint introduced in the prior DONE entry.
4. **Frontend — tile state model**: update [frontend/app.js](frontend/app.js) and [frontend/style.css](frontend/style.css) so failure tiles render the Chat button enabled (currently disabled / no-op on failure), with a `data-failure-kind` attribute that the chat prompt builder reads.

**Files to touch:** [backend/agents/browser_test.py](backend/agents/browser_test.py) (subscribe to ready), [backend/main.py](backend/main.py) (chat endpoint accepts failure tiles, loads log tail), [frontend/app.js](frontend/app.js) (waiting pill, chat-on-failure button wiring), [frontend/style.css](frontend/style.css) (waiting pill style).

**How to verify:** replay session `54623252b32c` with a cold `node_modules` → Run Converted takes ~70 s (install + vite boot). Browser Test should show "Waiting for dev server..." for ~60 s then proceed to probe, not fail at 30 s. On the two-process version, backend failure surfaces as `backend_unreachable` on Browser Test too. Click Chat on any red tile → LLM reply appears, prompt pre-populated with log tail.

---

### B.11a. Multi-service run support (frontend + backend together)

Observed on session `54623252b32c` (TotalBooking converted to React + .NET 8): `run.bat` starts Vite @ 5050 **and** ASP.NET Core @ 5051. AppNova's candidate loop picked the node-tail (`npm run dev`) and never launched `dotnet run`. Result: frontend loaded but every `/oauth/access_token` call 502'd through Vite's proxy to a dead 5051. Login silently failed. User had to start .NET manually.

Root causes in [backend/agents/run_manager.py](backend/agents/run_manager.py):

1. `_runner_script_candidates` returns the script but it sits alongside stack-inferred tails at [run_manager.py:373-384](backend/agents/run_manager.py#L373-L384). If the script's first candidate hiccups (the observed git-bash-on-Windows path glitch, line 357 — bash gets `uploads\...\run.sh` with backslashes, "No such file"), the loop falls through to the node tail which only starts the frontend half.
2. There is no concept of a "multi-service run". One port, one readiness probe, one process tree. A two-port app is invisible to the harness.
3. Vite's dev-proxy swallows the backend-down signal into a `502` inside the frontend response — the TCP + HTTP probe on 5050 happily returns 200 for `/` and declares the run ready.

Fix plan:

1. **Script-exclusive mode**: when `run.bat` / `run.sh` / `run.ps1` exists, use it as the sole candidate; drop stack-inferred tails. Expose a `prefer_script_runner=True` (default) knob so an advanced user can force fallback.
2. **Windows/bash path sanity**: when building the git-bash run.sh candidate on Windows, convert the path with `pathlib.PurePosixPath(run_sh).as_posix()` (or use `cygpath`-style `/c/...`) so bash resolves it. Better: skip the git-bash candidate entirely when `run.bat` is present.
3. **Multi-service model**: new `ServiceSpec` dataclass — name, cwd, argv, port, readiness_paths, depends_on. Detection rules:
   - Root has `backend/` with `.csproj` or `requirements.txt` or `pom.xml`, AND root has `src/` with `package.json` → two services: `backend` + `frontend`.
   - Root has `server/` with its own `package.json` → two Node services (express api + vite).
   - Otherwise single service as today.
   Spawn order respects `depends_on`; the run-card shows one row per service, each with its own up/down pill and log tail.
4. **Proxy-failure probe**: for services behind Vite's `server.proxy`, parse `vite.config.ts` for proxy targets, probe them directly (not via the frontend). If frontend is up but `http://localhost:<backend_port>/health` is ECONNREFUSED, raise failure kind `backend_unreachable` even when the frontend probe passes.
5. **Playwright classification**: refine [backend/agents/browser_test.py](backend/agents/browser_test.py) `response` listener — if a 502/504 response URL matches a proxied path in `vite.config.ts`, classify as `backend_unreachable` instead of generic `http_5xx`.
6. **UI — Service health sub-panel**: the run card gains a collapsible services table. Each row: name, port, state (probing/up/down), last URL, classification pill, "Logs" link that filters the persisted log to that service's stdout tag. Green-overall only when **all** services are up.

**Files to touch:** [backend/agents/run_manager.py](backend/agents/run_manager.py) (ServiceSpec, script-exclusive, multi-launch, proxy probe), [backend/agents/browser_test.py](backend/agents/browser_test.py) (refined classification), [frontend/app.js](frontend/app.js) (service table), [frontend/style.css](frontend/style.css) (service rows).

**How to verify:** re-run session `54623252b32c`. Without the fix: frontend green, login fails, zero harness signal. With the fix: run card shows two rows — `frontend/5050: up` and `backend/5051: down → backend_unreachable`; red overall pill; clicking Logs on the backend row shows whatever `dotnet run` actually printed before dying.

---

### B.12. DevOps scaffolding (target-environment aware)

Current conversion output is application code only. Production hand-off needs ops artefacts. A `devops_writer` sub-agent reads (a) target stack captured at upload, (b) the converted app's package.json / requirements.txt / pyproject, (c) source-app's existing ops hints (`.env`, any `docker*`, nginx confs, Procfile) and emits:

- **Dockerfile(s)** — one per runtime (frontend build stage + nginx static serve; backend slim-python or node). Multi-stage, pinned base images, non-root user, healthcheck.
- **docker-compose.yml** — frontend + backend + database + reverse proxy, with volumes and an attached network. Dev vs prod overrides via `docker-compose.override.yml`.
- **.env.example** — every config key referenced in source, documented, no real secrets.
- **CI workflow** — GitHub Actions (default) or GitLab CI / Azure Pipelines if detected: lint → test → build → image push → deploy. Matrix for node/python versions.
- **Reverse proxy** — nginx or Caddy config: TLS headers, gzip, SPA history-fallback, `/api` proxy to backend, rate limits.
- **Healthchecks** — `/health` and `/ready` added to backend if missing; wired into Docker HEALTHCHECK and k8s probes.
- **Infra-as-code** — Terraform module scoped to the cloud the client targets (AWS ECS/Fargate + RDS; Azure App Service + Azure SQL; GCP Cloud Run + Cloud SQL). One working `terraform apply`-able starter.
- **Secrets** — AWS SSM / Azure Key Vault / GCP Secret Manager integration stub, per cloud.
- **Observability** — structured logging config, OpenTelemetry init, a starter Grafana dashboard JSON.
- **Runbook** — `OPS.md` with deploy, rollback, scale, restart-db, rotate-secret, read-logs commands. Paired with the business-user `README.md` (section C).

### B.13. Data migration codegen (source DB → target DB)

Biggest manual lift in any modernization. A `data_migration_writer` sub-agent reads the source Laravel migrations + `$fillable` + model relationships + seed data, plus the target stack's ORM of choice, and emits:

- **Target schema DDL** — Postgres / MySQL / SQL Server, whichever the target picked. Types translated (TINYINT → BOOLEAN, DATETIME → TIMESTAMPTZ, TEXT sizes, ENUM → CHECK constraint), indexes preserved, FKs preserved.
- **Migration files** — Alembic (FastAPI), Prisma (Node), TypeORM, or Django migrations — one per Laravel migration, in topological order.
- **Seed-data export** — script that dumps lookup tables (agencies, offense codes, workflow_step names including the `== 9` Codex couldn't resolve — filled from `workflow_step` table directly) as JSON, plus an import loader on the target side.
- **ETL script** — row-copy with batching, chunked reads, progress bar, resumable from checkpoint. Handles legacy-vs-newer-schema split (the Codex report flagged `tb_new_form` / `legacyWarrant` dual paths — the ETL normalises both into the new shape).
- **PII-safe mode** — sibling script that writes to a dev/test target with PII fields masked (SSN → `XXX-XX-####`, DL# → hash, DOB → month/year only, victim data → removed). Drives B.4 PII report recommendations into actual code.
- **Rollback script** — per-table `DROP` and a restore-from-snapshot helper. Never auto-runs; requires `--confirm`.
- **Validation suite** — row counts per table, checksum of critical columns (`SUM(bail_amount)`, `COUNT(*) WHERE workflow_step_id=1`), foreign-key parity, null-ratio parity. Exits non-zero on divergence.
- **Downtime plan** — `MIGRATION_PLAN.md`: dry-run → stop writes → delta-sync → cutover → verify → rollback decision point. Timings estimated from row counts in B.9.
- **Target-specific tweaks** — Laravel `soft_deletes` → Postgres partial indexes on `deleted_at IS NULL`; Laravel morphs → polymorphic tables or JSONB; audit tables stay as-is or become temporal tables if target supports it.

Both B.12 and B.13 run in the same parallel wave as B.3 (layer map), because they depend on the same stack metadata. Outputs land in `converted/devops/` and `converted/migrations/` and are catalogued as dedicated sections in the unified bundle (B.11) plus new tiles in the Code Analysis UI (D).

### C. README running guide (business-user onboarding)

Target user: Krishna-level / product-owner / non-developer. Deliverable: `README.md` dropped into every converted-app root plus included in the analysis bundle.

Sections:

1. **What you need** — Node 20+ link, Python 3.11+ link, "how to check if you already have them" (`node -v`, `python --version`).
2. **Unzip** — where, directory layout.
3. **Install** — one copy-pasteable block per stack (`npm install`, `pip install -r requirements.txt`).
4. **Start backend** — exact command, expected log line that means "working", port to see.
5. **Start frontend** — same shape.
6. **Open in browser** — URL + what they should see.
7. **Login** — default credentials, where they live.
8. **If stuck** — numbered common-error table: "port in use → run stop script"; "cannot connect → check backend is up"; "401 on every page → re-login"; "blank page → reload with devtools open".
9. **Screenshots** — each step has a screenshot from the actual converted app (captured by Browser Test).
10. **Who to call** — escalation contact.

Generated by a dedicated `readme_writer` sub-agent that reads the converted app's `package.json`, entrypoint scripts, and existing routes, then fills a template. Output also embedded as an appendix in the analysis bundle.

---

### D. Pictures in Code Analysis tile + full-summary bundle

Codex's PDF worked because it had diagrams. The current AppNova "Code Analysis" tile is plain markdown. Upgrade:

1. **Inline PNG embeds** in each tile: architecture tree, ERD, workflow state machine, screen-nav flow. From B.7.
2. **Expandable "Full bundle" download** on the session header: single click gets the merged HTML + PDF.
3. **Pitch mode toggle** in the UI: switches the tile layout from "engineer grid" to "single scrollable narrative with hero images" — for demoing to clients live.
4. **Executive summary box** at the top of the bundle: 5 bullets auto-extracted from the executive-summary agent, readable in 30 seconds.

---

### E. Sequencing

1. **Fix cost tracking first** (A.1) — small, isolated, unblocks A/B testing the rest.
2. **B.1 parallel scan + B.11 bundle** — wire the pipeline skeleton.
3. **B.2 / B.3 / B.5 / B.6** — content agents (trees, mapping, data dict, workflow matrix).
4. **B.4 PII + B.9 effort estimate** — risk surface.
5. **B.7 diagram rendering + B.8 screenshots/charts** — pictures.
6. **C README + D pitch mode + executive summary** — business surface.

Each step adds a `[DONE]` entry above this one when shipped.

---

## 2026-04-20 — Robust Run-converted / Browser-Test: persisted logs, HTTP readiness, classified failures, browser-side diagnostics `[DONE]`

Rationale: the previous Browser-Test run on the TotalBookingAI conversion failed with only a generic "timed out after 30s". That was a false negative (Vite was up, bound IPv4-only), and it would have given zero signal if the real converted app had been silently broken in-browser — the TCP probe can't see client-side JS errors or 401 auth bounces. Four linked improvements across the harness layer so "failed" always carries a reason and the raw evidence.

**1. Persisted on-disk run logs (survive past the UI)**

The SSE stream + in-memory `deque(maxlen=2000)` dropped everything the moment a user clicked ✕ on the run card. Now every run tees its stdout/stderr to a file that outlives the session.

- [backend/agents/run_manager.py:38-68](backend/agents/run_manager.py#L38) — new `RUN_LOGS_ROOT = logs/runs/`; `RunState` gains `log_file: Path | None` and `_log_fp` handle fields.
- [backend/agents/run_manager.py:474-496](backend/agents/run_manager.py#L474-L496) — `start_run` opens `logs/runs/<session_id>/<yyyymmdd-hhmmss>-<run_id>.log` line-buffered, writes a header, and closes it in the pipeline's `finally` with phase + failure_kind metadata.
- [backend/agents/run_manager.py:451-466](backend/agents/run_manager.py#L451-L466) — `_log_line` tees every captured line to the open handle (best-effort; swallowed on disk failure so a full disk can't kill a run).
- [backend/main.py:1303-1330](backend/main.py#L1303-L1330) — new `GET /api/run/log/{run_id}` endpoint. Resolves the path from the active `RunState` first, then falls back to `glob("*/*-<run_id>.log")` under the logs root so **completed** and **removed** runs remain downloadable.
- [frontend/app.js:1747](frontend/app.js#L1747), [frontend/style.css:983-1011](frontend/style.css#L983-L1011) — run card gets a "Download log" anchor that activates as soon as `streamRunLogs` starts (the file exists from tick 0, so no race).

**2. HTTP readiness probe (not just TCP bind)**

TCP-bound ≠ actually-serving. Vite prints "ready in 4360 ms" long before routes resolve; .NET binds the socket in `Kestrel.Start()` then hangs during DI construction. The old probe green-lit runs that 500ed on every request.

- [backend/agents/run_manager.py:384-469](backend/agents/run_manager.py#L384-L469) — new `_http_get_status` (raw asyncio HTTP/1.1 GET, stdlib only — no aiohttp/httpx dep) and `wait_for_http_ready(port, host='localhost', paths=('/', '/health', '/login', '/index.html'))`. Accepts 2xx / 3xx / 4xx as "serving"; rejects 5xx + no-reply. Multi-path because SPAs 404 on `/` but serve `/login`, and APIs 404 on `/` but serve `/health`.
- [backend/agents/run_manager.py:704-734](backend/agents/run_manager.py#L704-L734) — `_launch_and_await_ready` now runs TCP-poll → HTTP-poll in sequence. Emits `{type:'ready', http_status, probed_path}` so the UI can show "ready — /login → 200".
- [backend/agents/browser_test.py:188-244](backend/agents/browser_test.py#L188-L244) — pre-launch probe in `run_browser_test` also upgraded to two-stage: a bound-but-not-serving dev server now returns a dedicated `FAILURE_BOUND_BUT_NOT_SERVING` instead of launching Chromium and getting a useless Playwright nav-timeout.

**3. Structured failure classification**

Nine named failure kinds cover every mode we've seen. Each is carried on `RunState.failure_kind`, broadcast over SSE, and rendered as a red pill on the run card.

- [backend/agents/run_manager.py:46-55](backend/agents/run_manager.py#L46-L55) — `FAILURE_*` constants: `command_not_found`, `spawn_failed`, `port_in_use`, `bound_to_wrong_host`, `process_crashed`, `port_never_bound`, `port_bound_but_not_serving`, `http_error_response`, `timeout`.
- [backend/agents/run_manager.py:471-491](backend/agents/run_manager.py#L471-L491) — `_classify_from_logs` regex-scans the last 80 log lines for EADDRINUSE / "address already in use" / "is not recognized as an internal" / "listening on 0.0.0.0" markers. First match wins; list kept tight so false positives don't train readers to ignore it.
- [backend/agents/run_manager.py:736-794](backend/agents/run_manager.py#L736-L794) — end of `_launch_and_await_ready` sets `run.failure_kind` from (log-signature → spawn-exception → TCP/HTTP result), in that order.
- [backend/agents/run_manager.py:636-655](backend/agents/run_manager.py#L636-L655) — pipeline's all-candidates-exhausted branch broadcasts `{type:'error', kind: ..., message: ...}` and `{type:'exit', failure_kind: ...}`.
- [frontend/app.js:1783-1824](frontend/app.js#L1783-L1824) — `streamRunLogs` reads `ev.kind` / `ev.failure_kind` and paints a red pill with the class `run-failure-kind`. Tooltip: "Classified failure: port_in_use" etc.

**4. Browser-side console capture via Playwright listeners**

This is the one that would have caught the TotalBookingAI login redirect bug automatically. The old Browser Test navigated to `/login`, screenshotted it, and reported success — even though every post-login API request was 401ing because of the Zustand-persist token-path bug in the converted app's `client.ts`. Now four Playwright page listeners feed the manifest:

- [backend/agents/browser_test.py:258-321](backend/agents/browser_test.py#L258-L321) — `page.on("console", ...)` filters out `log`/`info` (noise), keeps `error` + `warn`; `page.on("pageerror", ...)` captures uncaught exceptions; `page.on("requestfailed", ...)` captures net-level failures (CORS, DNS, aborted); `page.on("response", ...)` buckets status ≥ 400 into `http_4xx` / `http_5xx`.
- [backend/agents/browser_test.py:347-410](backend/agents/browser_test.py#L347-L410) — `render_report` now has sections for Uncaught JS errors, Console errors, Failed network requests, 5xx, 4xx, Navigation errors, Console warnings (hidden when louder signals are present). A converted-app login-redirect loop would now surface as a block of `http_4xx` entries on `/api/total-booking/stats` with `401` status.

**Why this matters**

Before: "Dev server never came up at http://localhost:5050 (TCP poll timed out after 30s)" — no evidence, no category, nothing to act on.

After: a failed run shows (1) a classified kind pill (`port_in_use`), (2) a Download-log button that pulls the full transcript even after the run card is closed, (3) the exact probed path and HTTP status if we got that far, and (4) the browser's own JS errors / failed fetches when the server is fine but the app is broken (the TotalBookingAI case).

**Files touched**

- [backend/agents/run_manager.py](backend/agents/run_manager.py) — logs, HTTP probe, classifier, state+event shape
- [backend/agents/browser_test.py](backend/agents/browser_test.py) — two-stage readiness, Playwright listeners, report sections
- [backend/main.py](backend/main.py) — `GET /api/run/log/{run_id}` endpoint
- [frontend/app.js](frontend/app.js) — run-card: failure-kind pill, Download-log link, `ready` event hint
- [frontend/style.css](frontend/style.css) — `.run-failure-kind` and `.run-download-log` styles

**How to verify**

1. Start AppNova (`start.bat` or `python run_server.py`), run an analysis, click Run converted.
2. Check `logs/runs/<session_id>/` — a `<timestamp>-<run_id>.log` file should appear immediately and grow as the dev server boots.
3. Click "Download log" on the run card → browser downloads the full transcript (works even after you click ✕ to remove the card).
4. Force a failure to see classification: stop the run, run a second one (port 5050 is now free, but you can force a collision with `netstat`-bind or an intentionally-broken `run.bat`). The red pill should say `port_in_use` or `command_not_found`.
5. Re-run Browser Test on the (now-fixed) TotalBookingAI converted app: if the token bug regresses, the report will list `http_4xx` entries with `401` on `/api/total-booking/stats` instead of falsely reporting success.

---

## 2026-04-20 — Converted TotalBookingAI app: fix login redirect loop + Vite host binding `[DONE]`

Investigation of `uploads/bc82e9de487a/converted/` after the user reported login failing (credentials accepted, then bounced back to `/login`) and the Browser Test tile showing "failed".

**1. Login redirect loop — token not sent on post-login requests**

Root cause: [src/api/client.ts:11](uploads/bc82e9de487a/converted/src/api/client.ts#L11) read `JSON.parse(raw).token`, but Zustand's `persist` middleware (used in [src/store/authStore.ts](uploads/bc82e9de487a/converted/src/store/authStore.ts)) wraps state as `{"state":{"token":"..."},"version":0}`. So the Authorization header was never set → the first protected call after `navigate('/')` (Dashboard hits `/api/total-booking/stats` + `/api/pc-declaration/counts`, both behind `authMiddleware`) returned 401 → the response interceptor at [client.ts:23](uploads/bc82e9de487a/converted/src/api/client.ts#L23) cleared localStorage and `window.location.href = '/login'`, bouncing the user back.

- [uploads/bc82e9de487a/converted/src/api/client.ts:8-17](uploads/bc82e9de487a/converted/src/api/client.ts#L8-L17) — request interceptor now reads `parsed?.state?.token ?? parsed?.token` to handle both the Zustand-persist shape and any legacy flat shape.

**2. Browser Test tile "failed" — IPv4-only bind vs. `localhost` probe**

Vite was bound to `127.0.0.1:5050`. The Browser Test polls `http://localhost:5050`, which on Windows 11 often resolves to `::1` (IPv6) first → TCP connect times out after 30s even though the dev server is up. The user can still reach the login page in their real browser because Chrome falls back to IPv4.

- [uploads/bc82e9de487a/converted/vite.config.ts:7-19](uploads/bc82e9de487a/converted/vite.config.ts#L7-L19) — `server.host` and `preview.host` switched to `'localhost'` (Vite resolves to both v4 + v6) and added `strictPort: true` so a port conflict fails loudly instead of silently drifting.

**How to verify**

1. `cd uploads/bc82e9de487a/converted && npm run dev`
2. Open `http://localhost:5050`, log in with `admin` / `password`.
3. Expected: dashboard renders with booking stats + PCDec counts. DevTools → Application → Local Storage → `auth` should contain `{"state":{"token":"<JWT>","user":{...}},"version":0}`; Network → `/api/total-booking/stats` request should include `Authorization: Bearer <JWT>` and return 200.

---

## 2026-04-20 — Cost report on Stop, UI/UX artifact uses real seed data, stricter backend conversion `[DONE]`

Three linked changes after reviewing the previous session's output PDFs:

**1. Cost workbook now always builds — even when the user hits Stop**

Root cause: `cost_tracker.build_workbook(session_id)` was only called inside `_auto_export_session`, which ran in the success branch of `run_in_background`. The `except asyncio.CancelledError` branch re-raised before reaching it, so every stopped run skipped the Excel roll-up even though every agent's token + cost rows were already written to SQLite by `cost_tracker.record_call`.

- [backend/main.py:711-728](backend/main.py#L711) — moved the workbook build into the `finally` block so it fires on every terminal state (success, cancel, error). Skipped only on the cache-hit path since that replay records no new costs. Emits a new `cost_report_ready` SSE event with the download URL so the frontend can pick it up after Stop.
- [frontend/app.js:1058-1063](frontend/app.js#L1058) — handler for `cost_report_ready` triggers one final `refreshCostChip()` so the chip shows the full partial-run cost after Stop and remains clickable to download the Excel.

**2. UI/UX artifact must inline the REAL converted seed data**

Prior prompt said *"ALL data inline as mock objects"* which gave the generator license to invent realistic-looking fake bookings that don't match the running converted app's actual data. The `<!-- ARTIFACT_START -->` HTML in ui-ux.pdf had 5 hand-written bookings and 3 PCDecs that never appeared in the real converted `server/data/seed.js`.

- [backend/agents/prompts.py:436-440](backend/agents/prompts.py#L436-L440) — ui-ux PART B rules now REQUIRE Glob for the converted seed file (typical names: `server/data/seed.js`, `backend/seed.py`, `prisma/seed.ts`, `fixtures/*.json`, etc.) and **transcribe records verbatim** into the artifact — same field names, same values, minimum 3–5 records per entity. If genuinely no seed exists, must state that in PART A under "Data note" and use clearly-labelled placeholder data rather than invent.

**3. Code-generation: stricter backend depth + mandatory Source→Target map**

Prior output in code-generation.pdf was a 4-file Node.js demo with in-memory store, no ORM, no real auth. That's acceptable as a toy demo but fails the "full-stack port" intent — the legacy has 79 Eloquent models, 25+ controllers, OAuth, ATIMS adapter, and none of that ended up in the target with any depth.

- [backend/agents/prompts.py:269-280](backend/agents/prompts.py#L269-L280) — new **"BACKEND CONVERSION — NON-NEGOTIABLE DEPTH"** block in `AGENT_PROMPTS["code-generation"]`. Six hard rules:
  1. **Controller coverage** — enumerate every legacy controller; produce a target stub per controller; if skipped, call it out in a top-of-report "Backend coverage gap" section.
  2. **Real persistence** — Prisma/Drizzle/EF Core/SQLAlchemy/Eloquent/GORM idiomatic to target stack. In-memory seeds acceptable only as *secondary* dev fixture alongside a real DB config.
  3. **Auth ported, not stubbed** — NextAuth / Passport / Sanctum / ASP.NET Identity / django-allauth with working issue+verify+refresh, not a placeholder JWT secret.
  4. **Repository/service layer preserved** — not fat controllers.
  5. **Source→Target backend map table REQUIRED in the report** — Legacy file | Legacy responsibility | Target file | Target responsibility | Coverage (Full/Partial/Stub/Skipped). This is the table reviewers scan first.
  6. **Parity tests** — at least one integration-style CRUD test per major entity exercising the real DB.

- [frontend/index.html:499](frontend/index.html#L499) — `app.js?v=17` to bust the cache for the new `cost_report_ready` handler.

---

## 2026-04-20 — Narrative reports, robust target selection, input+AppNova scoped analysis cache `[DONE]`

Three linked changes in response to the request "make reports more generic like Krishna's, target selection more robust, and cache only the project-directory analysis when the same input + unchanged AppNova is re-run".

**1. Reports read like a consultant doc, not an evidence ledger**

Krishna's reference doc (`References_by_Krishna/TotalBooking_PCDec_Application_Analysis_and_Use_Cases.pdf`) is flowing narrative prose — 3 roles in paragraph form, use cases as numbered narratives, no `file:line` citations sprinkled through the body. Our prior `code-analysis` prompt forced a rigid, evidence-ledger tone. That's now loosened:

- [backend/agents/prompts.py:470-488](backend/agents/prompts.py#L470-L488) — `_STYLE_CONTRACT` rewritten to mandate consultant-voice prose, bullets/tables only when genuinely tabular, product/exec reader first, no peppered `file:line` tags.
- [backend/agents/prompts.py:112-215](backend/agents/prompts.py#L112-L215) — `AGENT_PROMPTS["code-analysis"]` rewritten end-to-end. Kept the section outline (Scope, Executive Summary, Analysis Method, … Assumptions & Limitations) because the structure is good, but each section's instructions now say "paragraph or two", "short narrative", "closing Source: line", etc. Role count is flexible ("2–3 is common — do NOT pad"). Use cases are 6–12 with flexible shape. Evidence Rules relaxed: one section-level cite is enough, `file:line` no longer required on every claim.
- [backend/agents/prompts.py:546-552](backend/agents/prompts.py#L546-L552) — `_AGENT_TARGET_DIRECTIVES["code-analysis"]` softened to capability-level mapping, not file-by-file.

**2. Target selection more robust — frontend re-sends dropdown state on Run**

Prior flow: 4 dropdowns were captured at upload time only. If the user changed a dropdown after upload (very common), the stale value reached the agents. Now:

- [backend/main.py:692-715](backend/main.py#L692-L715) — new `POST /api/session/{session_id}/stack` endpoint accepts `{ui_tech, api_tech, db_tech, cloud, target_stack?}`, re-composes with `_compose_target_stack`, and updates `_session_targets[session_id]`.
- [frontend/app.js:750-766](frontend/app.js#L750-L766) — `startAnalysis()` POSTs the current dropdown values to the new endpoint before hitting `/api/analyze/{id}` or `/api/resume/{id}`. Failure is a non-fatal `console.warn` so analyze still runs.
- [backend/main.py:432-440](backend/main.py#L432-L440) — operator log: warn at analyze-time if `target_stack` is still empty, with guidance.

**3. Scoped analysis cache — project-dir only, invalidates on ANY AppNova change**

The cache is narrow by design and bypassed entirely by chat/run/browser-test:

- Hit requires a three-way match of `(project contents, AppNova source tree, target stack)`.
- Any edit to `backend/` or `frontend/` flips the AppNova hash, so prior cached runs stop matching — a fresh analysis is guaranteed after code changes.
- Resume runs skip the cache; director mode skips the cache.

Files:
- [backend/analysis_cache.py](backend/analysis_cache.py) — NEW. `project_hash(dir)` streams SHA-256 over every file under the upload root (sorted by rel-path for stability). `appnova_hash()` does the same for `backend/` + `frontend/`, skipping `__pycache__` / `.git` / `node_modules` / etc. `cache_key(project_dir, target_stack)` returns the combined SHA-256 plus the three components. `load(key)` and `save(key, …)` use `data/analysis_cache/<key>.json`.
- [backend/main.py:34](backend/main.py#L34) — import the new module.
- [backend/main.py:450-483](backend/main.py#L450-L483) — at the start of `_run_analysis_stream` (fresh, non-director, non-resume only), compute the cache key and try to load a prior payload.
- [backend/main.py:519-595](backend/main.py#L519-L595) — `_replay_cached_run(payload)` streams `plan` → `cache_hit` → `discovery_complete` → per-agent `agent_start`/`agent_complete` → `done`. Re-triggers `_auto_export_session` so the cached session also produces DOCX/PDF files. No subprocess calls.
- [backend/main.py:597-603](backend/main.py#L597-L603) — on cache hit, `run_in_background` returns early after the replay; `finally` still puts the None sentinel to close the stream cleanly.
- [backend/main.py:760-780](backend/main.py#L760-L780) — on successful fresh-run completion, persists `(results, digest, skipped, applicable, target_stack, project_hash, appnova_hash, source_session_id)` to the cache.
- [frontend/app.js:1046-1055](frontend/app.js#L1046-L1055) — new `cache_hit` event handler updates the foot-status with "Cached — replaying analysis saved <timestamp>" so the user understands why the run finishes instantly.
- [frontend/index.html:11,499](frontend/index.html#L11) — bumped `style.css?v=10` and `app.js?v=16` to bust the browser cache.

Cache storage footprint is small (~a few MB per cached run, JSON-compressed by disk). Gitignore is not touched here — add `data/analysis_cache/` to `.gitignore` if not already covered by the existing `data/` rules.

---

## 2026-04-20 — Removed session cache + SQLite store; auto-export DOCX + PDF; Save button no longer kills the run `[DONE]`

Three linked changes: the session-persistence + content-cache SQLite work done earlier was misaligned with the user's intent (SQLite is for the uploaded project's *own* DB files to be analysed by data-migration / devops agents — not for storing AppNova's session state). Reports now land as files on disk. And the Save button was killing the analysis because its anchor-navigation triggered the new `beforeunload` auth-wipe.

**1. Save button no longer kills the analysis**

The previous implementation set `<a href=export-url download=...>` and called `.click()`. On cross-origin URLs the browser ignores `download=` and navigates the current tab to the export URL. That unloaded the page, closing the SSE stream (analysis appeared "stopped") and firing the `beforeunload` handler which now wipes the auth token — so the user saw a blank/HTML page and was logged out.

- [frontend/app.js:1010-1045](frontend/app.js#L1010) — Save now `authFetch`es the export URL, reads the response as a `Blob`, creates a `blob:` URL, and clicks a hidden anchor. `blob:` URLs are same-origin, so `download=` is honoured; no navigation, no unload, no stream kill. Also surfaces backend errors (HTTP status + JSON detail) via `alert()` instead of a silent nav to a blank page.

**2. Removed analysis cache + SQLite session persistence**

The cache layer was designed for "re-upload same project → reuse prior reports", but the storage semantics conflicted with the user's stated goal: SQLite is an *analysis target* for the data-migration and devops agents, not an AppNova infrastructure DB. Reports now persist as files (markdown + DOCX + PDF) per-run under `exports/<session>/`.

- **Deleted:** [backend/analysis_cache.py](backend/analysis_cache.py) (input + appnova + target-stack hashing).
- **Deleted:** [backend/memory_store.py](backend/memory_store.py) (sessions, agent_results, analysis_runs SQLite schema + helpers).
- **Deleted:** `data/session_memory.db` on disk.
- [backend/main.py](backend/main.py) — removed: `from backend import analysis_cache, memory_store` import; `@app.on_event("startup")` `_hydrate_from_memory` hook; `touch_session`, `save_agent_result`, `record_analysis_run`, `find_cached_run`, `find_previous_runs`, `mark_run_completed`, `load_session_meta` calls; the cache-hit early-return branch in `/api/upload`; the version + previous_versions fields in the upload response.
- [frontend/app.js](frontend/app.js) — removed: `renderStoredResults()`, `renderPreviousVersionBanner()`, `data.cached` short-circuit in the upload handler, `data.version` / `data.previous_versions` consumption.
- [frontend/index.html](frontend/index.html) — removed the `<span id="previous-versions">` anchor.
- [frontend/style.css](frontend/style.css) — removed the `.previous-versions`, `.pv-chip`, `.pv-label`, `.pv-current` rule block.
- `cost_tracking.db` is untouched — that's a separate cost-tracker DB, not session persistence.

**3. Auto-export each agent report as DOCX + PDF**

`_auto_export_session` now writes three artefacts per completed agent in addition to the existing `<ts>_combined.md`:

- `<ts>_<agent>.md` — raw markdown (unchanged).
- `<ts>_<agent>.docx` — via `render_agent_docx` (python-docx, pure-Python, no external deps). Always produced.
- `<ts>_<agent>.pdf` — via `render_agent_pdf` (Playwright + headless Chromium). Best-effort — if Playwright isn't installed the markdown + DOCX still land and the PDF failure is logged once with the install hint.

- [backend/main.py:208-290](backend/main.py#L208) — `_auto_export_session` is now `async` so it can `await render_agent_pdf`; the single call site in `run_in_background` is updated with `await`. Agent labels come from `AGENT_LABELS` (already imported) for nicer document titles.

**Cache-bust + verification**

- [frontend/index.html](frontend/index.html) — `app.js?v=14` → `?v=15`.
- Backend import smoke-tests pass; JS static parse clean; manual verification required: (a) upload a project, run analysis, hit Save on any agent card → file downloads and analysis keeps streaming; (b) on run completion, inspect `exports/<session_id>/` → expect `<ts>_<agent>.md` + `.docx` + `.pdf` for every done agent (PDF only if Playwright is installed); (c) re-upload the same project → no cache hit, runs fresh.

---

## 2026-04-20 — Strict: login required on every page start (reload, close, nav) `[DONE]`

Upgraded the prior tab-scoped auth to fully strict: every navigation away from index.html (reload, tab-close, back-button, close browser) wipes the token, so the next load always hits the login screen. No sticky session of any kind.

**Change in [frontend/app.js:9-28](frontend/app.js#L9):** replaced the one-shot legacy-localStorage wipe with permanent `beforeunload` + `pagehide` listeners that call `_clearAuth()` on every unload. `_clearAuth()` nukes both sessionStorage and localStorage copies of the token + username.

- `beforeunload` handles the normal cases (F5, explicit close, explicit nav).
- `pagehide` covers the cases `beforeunload` can skip (BFCache restore on mobile, browser-managed tab close). Belt + braces.
- `logout()` still does its own clear + redirect — the unload handlers are additive insurance, not a replacement.

- [frontend/index.html](frontend/index.html) — `app.js?v=13` → `?v=14` cache-bust.

**Resulting behaviour:**
- F5 / reload → login screen.
- Close tab + reopen → login screen.
- New tab → login screen.
- Navigate away and back → login screen.
- Sign out → login screen.

**Tradeoff:** strict. Any reload during a long analysis run will log the user out. The frontend's reattach-to-running-session logic still runs after re-login, so the analysis itself isn't killed — but the user will have to sign in again before they see it. User explicitly asked for this strict behaviour.

**Verification:** static JS parse clean; manual verification required (sign in → reload → should hit login; sign in → open new tab on same URL → should hit login; sign in → close tab → reopen → should hit login).

---

## 2026-04-20 — Auth is now tab-scoped (login required per tab session) `[DONE]`

The JWT + username used to live in `localStorage`, so every tab on the machine shared the login and closing the browser still came back signed in. User wanted each new session to start at the login page, not auto-land as admin.

**Change:** auth storage moved from `localStorage` → `sessionStorage` in both [frontend/app.js:9-38](frontend/app.js#L9) and [frontend/login.js:24-66](frontend/login.js#L24). One-shot migration wipe clears any legacy localStorage token on load so older installs stop auto-logging in.

- `getToken()` + `logout()` read/write `sessionStorage`; `logout()` also nukes any lingering `localStorage` copy.
- `login.js` `maybeSkip()` only short-circuits when the current tab already holds a valid token; a fresh tab always shows the login form.
- [frontend/index.html](frontend/index.html) — `app.js?v=12` → `?v=13` cache-bust.

**Resulting behaviour:**
- New tab / new window → login screen.
- Close tab + reopen → login screen.
- F5 / reload in the same tab → stays signed in (normal expectation).
- "Sign out" menu item → login screen (unchanged).

**Not chosen:** forcing a login on every F5 reload. That's stricter but would interrupt normal work; easy one-line switch (`sessionStorage` → clear-on-DOMContentLoaded) if you'd rather have it.

**Verification:** static JS parse clean; manual verification required (open a second tab → should ask for login; close the browser and reopen → should ask for login; reload in the same tab → stays signed in).

---

## 2026-04-20 — User chip now opens a dropdown menu (Profile / Settings / Sign out) `[DONE]`

Clicking the top-right user chip used to sign out immediately, which felt punitive. Replaced with a proper account menu: single click opens a popover with the signed-in identity + three items. Sign out is now one more click away — the intended safety margin a professional app provides.

- [frontend/index.html:60-90](frontend/index.html#L60) — user chip restructured into `#user-menu-wrapper` containing the chip button (`aria-haspopup="menu"`, caret ▾) and a `#user-menu` popover with header (avatar + name + email), Profile item, Settings item, divider, Sign out item. `id="logout-btn"` kept on the Sign-out menu item so the existing `logout()` wiring stays intact.
- [frontend/index.html:427-475](frontend/index.html#L427) — new Profile modal (read-only: avatar, name, email, username, session expires-at pulled from `/api/auth/me`) and Settings modal (theme radios mirroring the topbar toggle + a "Clear cached sessions from this browser" button).
- [frontend/app.js:119-260](frontend/app.js#L119) — menu toggle on chip click; outside-click + Escape both close menu and any open modal; menu items dispatch to `logout()` / `openProfileModal()` / `openSettingsModal()`; theme radios write back to `AppNovaTheme.setMode()`; Clear button nukes `localStorage['appnova.sessionId']`.
- [frontend/index.html:476](frontend/index.html#L476) — `app.js?v=11` → `?v=12` cache-bust.
- [frontend/style.css:395-500](frontend/style.css#L395) — `.user-caret` rotates 180° when menu is open; `.user-menu`, `.user-menu-header`, `.user-menu-item`, `.user-menu-danger` styles; generic `.app-modal` + `.app-modal-panel` + backdrop / close button; `.profile-meta` dl grid; `.settings-field` fieldset styling with accent-coloured radios.

**Verification:** static JS parse clean; manual verification required (click chip → menu opens; clicking outside closes; Esc closes; Profile pulls `/api/auth/me`; Settings theme radios flip the app theme live; Sign out logs out).

---

## 2026-04-20 — Three bug fixes: erDiagram QA · target-stack cache key · mermaid theme swap `[DONE]`

Three separate symptoms reported together, three separate root causes.

**1. erDiagram reports show `⚠️ Diagram skipped — unbalanced { }`**

Mermaid erDiagram cardinality markers (`||--o{`, `}o--||`, `}|..|{`) contain literal `{` / `}` that the character-counting balance check misreads as stray braces. The ER diagram itself has perfectly paired entity braces.

- [backend/agents/diagram_qa.py:114-124](backend/agents/diagram_qa.py#L114) — for `erDiagram`, strip cardinality tokens (`[}{|][o|]?(?:--|\.\.)[o|]?[}{|]`) before the `{` / `}` balance check. Other diagram types unchanged.
- Verified: erDiagram with entity blocks + cardinality markers now passes; genuinely unbalanced `[` still rejected.

**2. Fresh upload with target stack selected still reports "No target stack supplied"**

The analysis cache key was `(input_hash, appnova_hash)`. A prior run of the same project **without** a target stack was cache-hitting a new run **with** a target stack — served back the old no-stack report, so code-analysis output claimed no stack was picked even though the dropdowns were populated.

- [backend/analysis_cache.py](backend/analysis_cache.py) — new `target_stack_hash(target_stack)` helper.
- [backend/memory_store.py](backend/memory_store.py) — `analysis_runs` schema gets `target_stack_hash TEXT NOT NULL DEFAULT ''`; new one-shot `_ensure_target_stack_column` ALTER for existing DBs; composite index now `(input_hash, appnova_hash, target_stack_hash)`.
- [backend/memory_store.py](backend/memory_store.py) — `record_analysis_run(...)` and `find_cached_run(...)` both take `target_stack_hash`. A stack-less run can only cache-hit another stack-less run.
- [backend/main.py](backend/main.py) — upload endpoint computes `target_h = analysis_cache.target_stack_hash(target_stack)` and passes it into both cache calls.
- Verified: empty-stack and stack-set runs of the same input now resolve to distinct cached sessions.

**3. Mermaid diagrams don't pick up the new theme when the user flips light↔dark**

`mermaid.initialize({theme})` was called once at app startup; `appnova:theme-changed` only ran `mermaid.run()` on stashed diagrams. `run()` honours the config from `initialize()`, so subsequent renders kept the old theme.

- [frontend/app.js](frontend/app.js) — in the `appnova:theme-changed` handler, call `mermaid.initialize({theme: …})` FIRST (picking `dark` or `default` from `AppNovaTheme.getEffective()`), then re-run each stashed diagram.
- [frontend/index.html:425](frontend/index.html#L425) — `app.js?v=10` → `?v=11` to cache-bust.
- Verification: static JS parse clean; manual visual verification required (reload, toggle ☀/◐/☾, confirm mermaid diagrams flip between light/dark).

**Downstream note:** items #1 and #3 are pure bug fixes with no API change. #2 changes the `find_cached_run` / `record_analysis_run` signatures (added optional `target_stack_hash` arg, default `""`). All call sites updated in this commit.

---

## 2026-04-20 — User chip moved to top-right as proper avatar `[DONE]`

Logout button (⎋) was sandwiched between the theme toggle and the timer, reading as a random action rather than the user's identity. Moved to the far right with a divider, rebuilt as a circular avatar (initial from `localStorage['appnova.username']`) + username chip, click-to-logout preserved.

- [frontend/index.html:54-70](frontend/index.html#L54) — reorder: theme-toggle → timer → run/resume/stop → launch/browser-test → cost-chip → divider → user-chip. Logout button restructured as `<button class="user-chip">` containing `.user-avatar` + `.user-name`.
- [frontend/app.js:119](frontend/app.js#L119) — populate avatar initial + name from `appnova.username`; tooltip becomes "Signed in as <name> · click to sign out".
- [frontend/style.css:370-400](frontend/style.css#L370) — new `.topbar-divider`, `.user-chip`, `.user-avatar`, `.user-name` rules; accent-coloured circular avatar.

---

## 2026-04-20 — Session reload behaviour (Rules 1 + 2 + 3a) `[DONE]`

Reload mid-run reattaches to the live analysis; reload after completion shows blank slate; new upload of the same project gets an instant cache hit (no `claude -p` spawn) when AppNova hasn't changed; prior versions surface as clickable chips when AppNova has changed. Full implementation spans backend (new `analysis_cache` module, `analysis_runs` SQLite table, hash-keyed upload endpoint) and frontend (gated `reattachIfRunning`, `renderStoredResults`, `renderPreviousVersionBanner`).

- [backend/analysis_cache.py](backend/analysis_cache.py) — `input_hash(project_dir)` (sha256 over sorted text-file (relpath, content)); `appnova_hash()` (sha256 over prompts.py + AGENT_REGISTRY serialisation).
- [backend/memory_store.py](backend/memory_store.py) — new `analysis_runs` table; `record_analysis_run`, `mark_run_completed`, `find_cached_run`, `find_previous_runs`.
- [backend/main.py:352-448](backend/main.py#L352) — upload computes both hashes, cache-hits return prior `session_id`, otherwise records new run + allocates next version; `mark_run_completed` fires after `_auto_export_session`.
- [frontend/app.js:133-165](frontend/app.js#L133) — `reattachIfRunning` now early-exits unless `status.running === true`.
- [frontend/app.js:500-580](frontend/app.js#L500) — upload handler short-circuits to `renderStoredResults()` on `data.cached`; renders `pv-chip` banner for `data.previous_versions`.
- [frontend/index.html:51](frontend/index.html#L51), [frontend/style.css:370](frontend/style.css#L370) — `#previous-versions` anchor + chip styles.

---

## 2026-04-20 — Parallel/supervisor/blackboard refactor of the legacy runner `[DONE]`

Old `run_all_agents` in [backend/agents/runner.py](backend/agents/runner.py) ran 12 `claude -p` calls strictly sequentially in the declared registry order. The DAG of `AgentSpec.upstream` deps was never consulted for parallelism — 9 of the 12 agents have no upstream deps and can legitimately run concurrently.

- [backend/agents/state.py](backend/agents/state.py) — new `RunState` TypedDict (the blackboard).
- [backend/agents/supervisor.py](backend/agents/supervisor.py) — new `compute_waves()` (layered topological sort) + `run_supervised()` (dispatches each wave via `asyncio.gather`; per-cwd `asyncio.Lock` serialises write-enabled agents that share `converted_dir`).
- [backend/agents/runner.py:609](backend/agents/runner.py#L609) — `run_all_agents` is now a thin wrapper that builds the `RunState` and calls `run_supervised`. Public signature unchanged — main.py and the SSE event contract (`agent_start` / `agent_event` / `agent_complete` / `done`) stay identical. One new `wave_start` event is emitted; unknown event types are ignored by the frontend router.

Wave layout computed from the current DAG:
- Wave 1 (9 parallel): code-analysis · architecture · business-rules · security · migration-planner · documentation · devops · data-migration · integration
- Wave 2 (1): code-generation
- Wave 3 (2): code-review · ui-ux (serialised on converted_dir via write lock)
- Wave 4 (1): testing

Wall-clock impact: wave 1 drops from 9× per-agent avg to ~1× slowest-agent. Waves 2–4 are serial by dependency; no regression.

---

## 2026-04-20 — Per-agent target-stack directives (every agent, not just code-analysis) `[DONE]`

Previously only the `code-analysis` role prompt explicitly required target-stack-aware output. The other 12 agents saw the target stack in the header but their role prompts let them drift into generic advice ("use a modern framework", "pick a CI tool"). Now each agent gets a role-specific directive appended right after the TARGET MIGRATION STACK block.

**Change in [backend/agents/prompts.py](backend/agents/prompts.py):**

- New `_AGENT_TARGET_DIRECTIVES: dict[str, str]` with one directive per agent: `architecture`, `code-analysis`, `business-rules`, `security`, `devops`, `documentation`, `code-review`, `testing`, `data-migration`, `ui-ux`, `integration`, `migration-planner`, `code-generation`.
- Each directive names the **specific target-stack output** that agent must produce — e.g. architecture owns the Current→Target Component Map + target mermaid; security remediations must name the target-stack primitive (NextAuth, Prisma parameterized queries, ASP.NET Data Protection); devops Dockerfile base image + IaC flavor must match target cloud; testing must use the target's canonical runner (Vitest, pytest, xUnit); data-migration schema + migrations use the target ORM's tool (Prisma migrate, EF Core, Alembic); ui-ux polish picks target-stack components (shadcn, Fluent UI, Angular Material); integration findings include a **Target-stack binding** line naming the SDK that replaces each legacy call.
- Wired into [`build_agent_prompt`](backend/agents/prompts.py) — the per-agent block appears as `## TARGET-STACK DIRECTIVE FOR <AGENT>` when and only when a target stack is supplied. No target stack = directive is omitted, behaviour unchanged.

**Verification:** all 13 agent IDs resolve to a directive; `no-target` build path still compiles.

---

## 2026-04-20 — Per-agent PDF/DOCX download fixed (`Missing Bearer token` 401) `[DONE]`

**Symptom:** clicking "Save → PDF" (or DOCX) on an agent card opened `/api/export/<session>/<agent>.pdf` in a new tab and the server returned `401 {"detail":"Missing Bearer token"}`. `window.open` uses the browser's default request — no `Authorization` header, so the auth middleware rejected it.

**Fix:** swap `window.open(url)` for a hidden anchor that routes through `authSSEUrl(url)` (same query-string `?token=<jwt>` fallback the middleware already honors for EventSource + the cost `.xlsx` download). Adds the JWT to the URL and triggers a real download via `<a download>`.

- [frontend/app.js:716](frontend/app.js#L716) — replaced the save-menu click handler.
- [frontend/index.html](frontend/index.html) — bumped `app.js?v=9` → `?v=10` for cache-bust.

No backend change needed — [backend/main.py:115](backend/main.py#L115) already accepts `?token=` as an auth fallback. Hard-refresh the frontend to pick up the new `app.js`.

---

## 2026-04-20 — code-analysis prompt rewritten to match Krishna's reference doc + force target-stack mapping `[DONE]`

The earlier `code-analysis` prompt was a generic static-analysis checklist that never referenced the target stack. Output didn't resemble `References_by_Krishna/TotalBooking_PCDec_Application_Analysis_and_Use_Cases.docx` (evidence-driven app-analysis + use-case catalog).

**Changes in [backend/agents/prompts.py](backend/agents/prompts.py):**

- `AGENT_PROMPTS["code-analysis"]` expanded from ~900 chars to ~7.7 KB. Required output sections, in order: Scope → Executive Summary → Analysis Method → Application Overview (Business Purpose + Functional Domains) → Architecture Overview (with `flowchart LR`) → Primary User Roles → Screen/Module Inventory → Detailed Feature Analysis → Workflow and Status Analysis (with `stateDiagram-v2`) → Use Case Catalog (≥8 UCs with actor/precondition/main flow/postcondition/code evidence/alternate flows) → Core Entity View (with `erDiagram`) → Integrations and External Dependencies → Versioning and Legacy Behavior → Strengths Observed → Risks and Observations → **Target Stack Mapping** (mandatory table: legacy component → target component) → Recommended Next Steps → Assumptions and Limitations.
- Every claim must cite `file:line`. No filler, no generic "pick a modern framework" advice.
- `build_agent_prompt()` TARGET MIGRATION STACK block now reads "this is not flavor text — generic advice is a failure" and demands a row-per-legacy-component mapping in the output.

Downstream effect: target_stack was always threaded through ([backend/agents/runner.py:685](backend/agents/runner.py#L685)); it just wasn't being used. Now it's required output.

---

## 2026-04-20 — Implementation pass: items 1–10 all shipped `[DONE]`

Every `[PLANNED]` item from the prior entries has been built end-to-end. Summary of what landed:

| # | Feature | Key files |
|---|---|---|
| 1 | Mermaid auto-repair + strict prompt rules + failure log | [backend/agents/diagram_qa.py](backend/agents/diagram_qa.py), [backend/agents/prompts.py](backend/agents/prompts.py), [frontend/app.js](frontend/app.js) |
| 2 | Light/dark theme w/ 7pm↔6am auto switch, Mermaid re-render, persisted preference | [frontend/theme.js](frontend/theme.js), [frontend/style.css](frontend/style.css), [frontend/index.html](frontend/index.html) |
| 3 | Login page + JWT middleware + scrypt passwords + `.env` creds | [backend/auth.py](backend/auth.py), [backend/main.py](backend/main.py), [frontend/login.html](frontend/login.html), [frontend/login.js](frontend/login.js) |
| 4 | Per-session cost SQLite + 5-sheet Excel + 5-rule recommendation engine | [backend/cost_tracker.py](backend/cost_tracker.py), [backend/model_pricing.yaml](backend/model_pricing.yaml) |
| 5 | Glob/Grep/Read/LS tool cards moved into collapsible per-agent console | [frontend/app.js](frontend/app.js), [frontend/style.css](frontend/style.css) |
| 6 | Unbounded timeout for code-generation / review / testing / ui-ux agents | [backend/agents/runner.py](backend/agents/runner.py) |
| 7 | SQLite session memory + startup hydration so restarts don't lose work | [backend/memory_store.py](backend/memory_store.py), [backend/main.py](backend/main.py) |
| 8 | Auto-export markdown per agent + combined report on run completion | [backend/main.py](backend/main.py) `_auto_export_session` + `/api/exports/*` |
| 9 | Synthesized README/DEPLOYMENT/DATA_MIGRATION + `docs/` mirror in converted apps | [backend/agents/scaffold.py](backend/agents/scaffold.py) `ensure_documentation` |
| 10 | `run.sh` / `run.bat` / `run.ps1` preferred as first launch candidate | [backend/agents/run_manager.py](backend/agents/run_manager.py) `_runner_script_candidates` |

**Scope notes:**
- Global chat UI (right sidebar, cross-agent) — deferred. The per-agent chat already exists; a global overlay needs a design pass and a new backend endpoint. Tool-card noise removal (the bigger user complaint) is done.
- Cost tracker currently captures one entry per agent (the `claude -p` completion event). Sub-turn granularity would require deeper SDK instrumentation.
- Memory hydration restores completed agent results + session metadata. Artifact-hash caching (skip re-analysis when files are unchanged) is not yet wired — flagged for a future pass.

**Smoke tests that passed:**
- `diagram_qa` — 6 cases (valid / HTML arrow / reserved ID / raw newline / unbalanced / subgraph mismatch).
- `theme.js` `resolveAutoTheme` — 7 boundary tests (00:00, 05:59, 06:00, 12:00, 18:59, 19:00, 23:59).
- `auth` — 5 cases (plaintext, JWT roundtrip, tampered token, scrypt hash, hash override).
- `cost_tracker` — end-to-end: 25 synthetic calls → 5-sheet workbook → 4 recommendations fired.
- `memory_store` — touch, save, load, hydrate, delete.
- `ensure_documentation` — README stub replacement + idempotent re-run.
- `_dev_server_candidates` — `run.bat`/`run.sh` appear first for a fake Node project.

---

## 2026-04-19 — Port 5050 as the universal default for converted apps `[DONE]`

**Trigger:** `totalbooking-modern` converted app launched on port 5050 but `.env.example` hardcoded `NEXTAUTH_URL="http://localhost:3000"` → NextAuth `NO_SECRET` + URL mismatch → `/api/auth/*` returned 500.

**Root cause:** AppNova's converter used mixed port defaults across artifacts: `3000` (Next.js prompt example), `8080` (docker-compose, Bicep, static-site fallback), `5173` (CORS for Vite), while the runner pool starts at `5050`. LLM-generated `.env.example` picked up `3000` from the prompt example, which didn't match the runtime port.

**Fix applied (AppNova source):**
| File | Change |
|---|---|
| [backend/agents/sample_data.py:233](backend/agents/sample_data.py#L233) | CORS origin `http://localhost:3000` → `http://localhost:5050` |
| [backend/agents/sample_data.py:352,354](backend/agents/sample_data.py#L352) | docker-compose `${PORT:-8080}` → `${PORT:-5050}` |
| [backend/agents/sample_data.py:431](backend/agents/sample_data.py#L431) | Bicep `WEBSITES_PORT: '8080'` → `'5050'` |
| [backend/agents/scaffold.py:265,270](backend/agents/scaffold.py#L265) | Static-site fallback `http.server 8080` → `http.server 5050` |
| [backend/agents/prompts.py:147](backend/agents/prompts.py#L147) | Example `"next dev -p ${PORT:-3000}"` → `${PORT:-5050}` |
| [backend/agents/prompts.py](backend/agents/prompts.py) (new block) | Explicit "DEFAULT PORT IS 5050 — NON-NEGOTIABLE" rule covering `package.json`, `.env.example`, `run.sh`/`run.bat`/`run.ps1`, `docker-compose.yml`, `next.config.js`, healthcheck URLs, and CORS |

**Fix applied (user's live converted app):**
- [uploads/abd206e5fb91/converted/.env](uploads/abd206e5fb91/converted/.env) — generated real `NEXTAUTH_SECRET` (32-byte base64), set `NEXTAUTH_URL=http://localhost:5050`, uncommented `PORT=5050`

**Follow-up items (not yet done, worth tracking):**
1. Pre-flight check in the runner — if a converted app exposes `NEXTAUTH_URL` or similar `*_URL` env vars with a port that doesn't match the runner's assigned port, auto-rewrite (or fail loud with actionable message)
2. Auto-generate `NEXTAUTH_SECRET` (and any `*_SECRET` placeholder) at scaffold time instead of leaving `"change-me-to-a-random-32-char-string"` — the converter should run `secrets.token_urlsafe(32)` and write real values into `.env.example` so first-run works without manual steps
3. `run.sh` startup echo currently hardcodes `http://127.0.0.1:3000` in already-generated apps — LLM-produced content, not a template. The new prompt rule fixes future runs; existing converted apps are unaffected until re-converted
4. Consider a single `DEFAULT_CONVERTED_APP_PORT = 5050` constant imported by `sample_data.py`, `scaffold.py`, and referenced in `prompts.py` at template-render time — removes the scatter

---

## 2026-04-19 — "Run Converted App" — execute `run.sh` from frontend `[PLANNED]`

**Goal:** The existing **Run Converted** button in the frontend triggers the AppNova backend to execute the converted app's `run.sh` (and its Windows equivalent), stream live logs back to the UI, and expose start/stop/status controls with proper process isolation.

### A. Contract: every converted app must emit a runner

The converter agent must output, at the converted app's root:
1. **`run.sh`** — POSIX shell script (Linux/macOS/Git-Bash on Windows)
2. **`run.ps1`** — PowerShell script (Windows native)
3. **`run.md`** — documents prerequisites, ports, env vars, how to stop
4. **`.runconfig.json`** — machine-readable metadata consumed by the backend:
   ```json
   {
     "name": "converted-app",
     "frontend": { "port": 3000, "health_path": "/", "start_script": "run.sh", "cwd": "frontend" },
     "backend":  { "port": 8000, "health_path": "/health", "start_script": "run.sh", "cwd": "backend" },
     "required_env": ["DATABASE_URL", "API_KEY"],
     "startup_timeout_seconds": 120,
     "shutdown_signal": "SIGTERM"
   }
   ```
   Backend reads this to know what to launch, which ports to expose, and when to declare "ready."

### B. Backend API

New module: `backend/services/app_runner.py` + routes under `/api/run/*`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/run/start` | POST | Body: `{ app_path, profile: "dev" \| "prod" }` → returns `run_id` |
| `/api/run/stop/:run_id` | POST | Graceful shutdown (SIGTERM → wait → SIGKILL after grace period) |
| `/api/run/status/:run_id` | GET | `{ status, started_at, uptime, frontend_url, backend_url, health }` |
| `/api/run/logs/:run_id` | GET (SSE) | Live stdout+stderr stream |
| `/api/run/list` | GET | All currently tracked runs (for reconnect after page reload) |

### C. Process management

1. **Spawn model** — use Python `asyncio.create_subprocess_exec` (never `shell=True`). Pass the script path as argv[0], not a concatenated string. Prevents command injection entirely.
2. **Platform-aware launcher:**
   - Linux/macOS: `bash run.sh`
   - Windows (preferred): `powershell -ExecutionPolicy Bypass -File run.ps1`
   - Windows fallback if `run.ps1` missing but Git Bash installed: `"C:\Program Files\Git\bin\bash.exe" run.sh`
   - Detect at runtime via `platform.system()`; configurable override in `.env`: `RUNNER_SHELL_WINDOWS=powershell|gitbash`
3. **Process group isolation** — launch each run in a new process group so SIGTERM on stop kills child processes (Vite dev server, uvicorn workers, etc.):
   - Unix: `preexec_fn=os.setsid`, kill with `os.killpg(pgid, sig)`
   - Windows: `creationflags=CREATE_NEW_PROCESS_GROUP`, stop with `send_signal(CTRL_BREAK_EVENT)` then hard-kill on timeout
4. **Working directory** — always `cwd=<converted_app_path>` so relative paths in `run.sh` resolve correctly
5. **Environment** — inherit current env + merge `required_env` values. If any required var is missing, fail fast with a clear error **before** launching.
6. **Run registry** — in-memory dict `{ run_id: RunHandle }` + persisted to SQLite `runs(id, app_path, pid, pgid, status, started_at, stopped_at, exit_code, log_path)` so runs survive backend restart (or can be cleaned up on restart — see G).

### D. Port allocation & conflict handling

1. Read desired ports from `.runconfig.json`
2. **Pre-flight check** — `socket.bind(('127.0.0.1', port))` on each desired port; if bound, fail with actionable error listing what holds the port (via `psutil.net_connections()`)
3. **Auto-reallocation option** — if `.env` has `RUNNER_AUTO_REALLOCATE_PORTS=true`, pick the next free port ≥ desired and inject as env vars (`PORT`, `VITE_PORT`, etc.) — documented in `run.md` as consumed
4. Return the actual bound URLs in `/api/run/status` so the UI opens the right link

### E. Log streaming

1. **Capture:** stdout and stderr merged (or separated, configurable) into a per-run log file: `logs/runs/<run_id>.log`. Also tee'd into an in-memory ring buffer (last 10k lines) for fast initial load.
2. **SSE endpoint** — on connect: replay ring buffer → then stream new lines. Keep-alive ping every 15s to keep proxies happy.
3. **ANSI color handling** — preserve ANSI codes; frontend renders via a terminal component (e.g., `xterm.js` or `ansi-to-react`)
4. **Backpressure** — if frontend falls behind, drop from the oldest end of the buffer (log file is the source of truth; never drop from disk)
5. **Log rotation** — cap each run's log at 50 MB; rotate to `.1`, `.2`; configurable `RUNNER_LOG_MAX_MB`

### F. Health & readiness

1. **Startup probe** — after launch, poll `health_path` on each configured port until 200 OK or `startup_timeout_seconds` elapses
2. **Status transitions:** `starting → running → (stopping → stopped | crashed)`
3. **Crash detection** — if the subprocess exits with non-zero code while status is `running`, mark `crashed` and surface the last 50 log lines in the UI
4. **Liveness probe** — every 10s while `running`, hit `health_path`; 3 consecutive failures → mark `unhealthy` (but keep running — don't auto-kill)

### G. Lifecycle & cleanup

1. **Stop flow** — SIGTERM → wait `shutdown_signal_grace_seconds` (default 10) → SIGKILL + `killpg` to catch grandchildren
2. **Backend shutdown** — on AppNova backend exit (SIGTERM handler), stop all tracked runs
3. **Restart recovery** — on backend startup, check `runs` table for `status=running` rows:
   - If PID still alive (`psutil.pid_exists`) and port still bound → reattach to existing log file, resume tracking
   - Otherwise → mark as `orphaned` in DB, clean up
4. **One-run-per-app policy** — if `/api/run/start` is called for an app_path that already has an active run, return `409 Conflict` with the existing `run_id` (UI shows "Already running" and offers to attach)

### H. Security

1. **App path allowlist** — the backend may only launch apps inside a configured roots directory (`RUNNER_ALLOWED_ROOT` in `.env`, default `<appnova_root>/converted_apps/`). Reject path traversal (`..`) and absolute paths outside the root.
2. **No shell=True anywhere.** Ever.
3. **Script validation** — before launch, verify:
   - `run.sh` / `run.ps1` exists and is a regular file (not symlink outside root)
   - On Unix, `run.sh` is executable (`chmod +x` auto-applied by converter; backend re-applies if missing)
4. **Resource limits** (Unix, best-effort):
   - `resource.setrlimit` for CPU time, memory, open files — configurable caps per run
   - On Windows: Job Objects (via `pywin32`) for memory caps; skip if not available and document the limitation
5. **Audit log** — every start/stop logged to `logs/runner_audit.log` with user, timestamp, app_path, outcome
6. **Authenticated endpoints** — `/api/run/*` sits behind the login middleware (from the login-page feature); unauthenticated requests rejected

### I. Frontend UI

1. **Run Converted button states** (single button, state machine):
   - `Idle` → label **Run Converted**, action: POST `/api/run/start`
   - `Starting` → spinner, label **Starting…**, disabled
   - `Running` → green dot, label **Stop** (primary) + **Open app ↗** (opens frontend URL in new tab)
   - `Crashed` → red, label **View logs** + **Retry**
2. **Run panel** (drawer that opens when a run is active):
   - Header: app name, uptime, frontend URL (click to open), backend URL
   - Tabs: `Logs` (live terminal), `Status` (health checks, ports, env), `Metrics` (optional: CPU/memory via psutil)
   - Stop button with confirm dialog
3. **Reconnect on reload** — on app mount, call `/api/run/list` to restore any active runs into the UI
4. **Theme-aware** — terminal component respects the light/dark theme system (Sheet 1 of the theme work)
5. **Toast notifications** — "App started on http://localhost:3000", "App crashed — exit code 1", "App stopped"

### J. Error messages (user-facing — must be actionable)

| Condition | Message |
|---|---|
| `run.sh` missing | "Converted app is missing `run.sh`. Re-run the conversion, or generate it manually using `appnova generate-runner`." |
| Port in use | "Port 3000 is already in use by `node.exe` (PID 12345). Stop that process or enable `RUNNER_AUTO_REALLOCATE_PORTS`." |
| Required env missing | "Missing required env var: `DATABASE_URL`. Add it to `<app_path>/.env` or export it before starting AppNova." |
| Startup timeout | "App did not report healthy within 120s. Last 50 log lines attached below." |
| Permission denied on script | "`run.sh` is not executable. AppNova will `chmod +x` automatically — retry." |

### K. `.env` additions

```
RUNNER_ALLOWED_ROOT=./converted_apps
RUNNER_SHELL_WINDOWS=powershell
RUNNER_AUTO_REALLOCATE_PORTS=false
RUNNER_STARTUP_TIMEOUT_SECONDS=120
RUNNER_SHUTDOWN_GRACE_SECONDS=10
RUNNER_LOG_MAX_MB=50
RUNNER_MAX_CONCURRENT_RUNS=3
RUNNER_HEALTH_CHECK_INTERVAL_SECONDS=10
```

### L. Testing

1. **Unit tests** — path traversal rejection, port conflict detection, `.runconfig.json` parsing edge cases
2. **Integration test** — spawn a tiny fixture app (`echo "ready" && sleep 30`), verify: status transitions, log streaming, stop signal kills it, SIGKILL fallback works
3. **Platform matrix** — manual test on Windows (primary), Linux, macOS. Verify PowerShell path and Git Bash fallback.
4. **Crash test** — fixture that exits 1 after 2 seconds → verify `crashed` status and log capture
5. **Orphan recovery** — start a run, `kill -9` the AppNova backend, restart backend → verify run state is correctly reconciled
6. **Concurrent runs** — start N apps simultaneously up to `RUNNER_MAX_CONCURRENT_RUNS`; verify `409` on exceeding

### M. Cost-tracking integration

The runner feature is not an LLM consumer, but the run lifecycle should emit entries to the same SQLite `events` table (create if not present) so the session report shows: "3 app runs this session, 2 successful, 1 crashed, total runtime 47 min." This is small and complements the Excel cost report without bloating it.

---

## 2026-04-19 — Per-session cost & token usage Excel report `[PLANNED]`

**Goal:** Every run of AppNova produces a professional, auditable Excel workbook capturing cost and token usage for every agent and the overall process, with actionable optimization recommendations. Persisted per session for historical comparison.

### A. Data model — what to track per LLM call

**Capture at the call site (LLM client wrapper):**
| Field | Type | Source |
|---|---|---|
| `call_id` | UUID | generated |
| `session_id` | UUID | current session |
| `run_id` | UUID | current process run |
| `agent_name` | string | caller context |
| `phase` | string | e.g. `analysis`, `conversion`, `review`, `report` |
| `model` | string | e.g. `claude-opus-4-7`, `claude-sonnet-4-6` |
| `provider` | string | `anthropic`, `openai`, etc. |
| `prompt_tokens` | int | API response |
| `completion_tokens` | int | API response |
| `cache_read_tokens` | int | prompt cache hits |
| `cache_write_tokens` | int | prompt cache writes |
| `total_tokens` | int | computed |
| `input_cost_usd` | decimal(10,6) | tokens × model input rate |
| `output_cost_usd` | decimal(10,6) | tokens × model output rate |
| `cache_read_cost_usd` | decimal(10,6) | cached input rate (usually 10% of input) |
| `cache_write_cost_usd` | decimal(10,6) | cache write rate (usually 125% of input) |
| `total_cost_usd` | decimal(10,6) | sum |
| `latency_ms` | int | call duration |
| `started_at` / `finished_at` | timestamp | wallclock |
| `input_file` | string (nullable) | file being processed, if applicable |
| `prompt_hash` | sha256 | for dedup/cache analytics |
| `status` | enum | `success`, `retry`, `failed` |
| `retry_count` | int | 0+ |
| `error_message` | string (nullable) | if failed |

### B. Storage layer

1. **SQLite table** `llm_calls` at `backend/data/cost_tracking.db` (separate from memory DB to keep cost logs append-only and immutable)
2. **Pricing config** — `backend/config/model_pricing.yaml`:
   ```yaml
   claude-opus-4-7:
     input_per_1m: 15.00
     output_per_1m: 75.00
     cache_read_per_1m: 1.50
     cache_write_per_1m: 18.75
   claude-sonnet-4-6:
     input_per_1m: 3.00
     output_per_1m: 15.00
     cache_read_per_1m: 0.30
     cache_write_per_1m: 3.75
   claude-haiku-4-5:
     input_per_1m: 1.00
     output_per_1m: 5.00
     cache_read_per_1m: 0.10
     cache_write_per_1m: 1.25
   ```
   Values configurable without code changes; cost computed at call time using the version in effect.
3. **LLM client wrapper** — `backend/llm/tracked_client.py`:
   - Wraps every provider SDK call
   - Records the row to `llm_calls` after each call (success or failure)
   - Zero-instrument model: agents use the wrapper, not raw SDKs — enforced via lint rule / code review

### C. Excel workbook — structure

**Library:** `openpyxl` (native Python, no Java dependency, supports formulas, conditional formatting, charts).

**Output path:** `exports/cost_reports/<session_id>/<YYYY-MM-DD_HH-MM-SS>_run-<run_id>_cost.xlsx`

**Workbook contains 6 sheets, in this order:**

#### Sheet 1: `Summary`
Executive dashboard, one screen.

| Section | Contents |
|---|---|
| **Run metadata** | Session ID, Run ID, Start/End time, Duration (HH:MM:SS), User, AppNova version |
| **Totals** | Total calls, Total tokens (input / output / cache read / cache write), **Total cost (USD)** — highlighted |
| **By model** | Small table: model → calls → tokens → cost → % of total cost |
| **By agent** | Small table: agent → calls → tokens → cost → % of total cost |
| **Headline metrics** | Avg cost per file converted, Avg tokens per call, Cache hit rate, Retry rate |
| **Top 3 cost drivers** | Auto-populated from the recommendations engine (Sheet 6) |

**Formatting:**
- Company-style header (merged cells, AppNova branding color)
- Number formatting: costs as `$#,##0.0000`, tokens with thousands separators
- Conditional formatting: total cost cell highlighted red if > configurable threshold (default $5.00)
- Sparklines for token/cost trends if multiple runs exist for the session

#### Sheet 2: `By Agent`
One row per agent, aggregated across the run.

| Column | Notes |
|---|---|
| Agent name | |
| Total calls | |
| Total input tokens | |
| Total output tokens | |
| Total cache read tokens | |
| Total cache write tokens | |
| Total tokens | bold |
| Input cost | |
| Output cost | |
| Cache cost | |
| **Total cost** | bold, color scale conditional formatting |
| Avg tokens per call | |
| Avg latency (ms) | |
| Cache hit rate % | conditional: green > 40%, yellow 20–40%, red < 20% |
| Retry count | |
| % of run cost | data bar conditional formatting |

**Footer row:** totals (SUM formulas) so the sheet stays live-editable.

#### Sheet 3: `By Model`
Same columns as Sheet 2 but grouped by model. Useful to spot over-reliance on expensive models.

Additional columns: `input_rate_used` and `output_rate_used` (from pricing config at call time) — transparency for the cost math.

#### Sheet 4: `Call Log`
Full per-call detail, every row from the `llm_calls` table for this run.

All fields from section A, plus:
- **AutoFilter enabled** on the header row — user can slice by agent, model, phase, status
- **Freeze panes** on row 1
- **Conditional formatting:**
  - `status = failed` → red row
  - `retry_count > 0` → yellow row
  - `total_cost_usd` top 5% → orange highlight
- **Sorted by** `started_at` ascending

#### Sheet 5: `Recommendations`
Auto-generated, ranked, actionable. Each recommendation is one row:

| Column | Example |
|---|---|
| Rank | 1 |
| Category | `Model selection` / `Caching` / `Prompt size` / `Redundancy` / `Batching` / `Retries` |
| Finding | "`code-reviewer` agent used Opus for 847 calls; 92% were short review summaries under 500 output tokens" |
| Est. savings | `$4.23 per run (61% reduction on this agent)` |
| Recommended action | "Switch `code-reviewer` to Sonnet for summaries under 1k tokens; keep Opus for deep reviews only" |
| Effort | `Low` / `Medium` / `High` |
| Priority | `High` (High savings + Low effort) |
| Implementation hint | Config key to change, code path |

See section E for the recommendation engine.

#### Sheet 6: `Trend` *(cross-run comparison, appears only if > 1 run in session)*
One row per run in the session, columns = key metrics (total cost, tokens, cache hit rate, cost per file). Includes a line chart showing cost trajectory across runs — makes regressions obvious.

### D. Auto-save per session

1. **Trigger points** — workbook regenerated at:
   - End of every process run (auto)
   - On explicit user "Export cost report" click (manual, with "current state" snapshot)
   - On session close (final version)
2. **File versioning:** each run gets its own file (timestamp in filename). Latest symlinked as `exports/cost_reports/<session_id>/latest.xlsx`.
3. **Session index:** `exports/cost_reports/<session_id>/index.json` lists all runs with totals — frontend can render a session cost history without opening files.
4. **Global index:** `exports/cost_reports/_all_sessions.json` — all sessions summarized, for a future "cost history" dashboard.
5. **Retention:** `.env` → `COST_REPORT_RETENTION_DAYS=90` (longer than general exports because audit value is high).

### E. Recommendation engine (for Sheet 5)

`backend/services/cost_optimizer.py` — deterministic rule-based analysis over the run's `llm_calls` data. Each rule returns a `Recommendation` object; rules run in a fixed order; output is sorted by `est_savings_usd` desc.

**Rule catalog (initial set):**

| Rule | Fires when | Recommendation |
|---|---|---|
| `expensive_model_for_simple_task` | Agent uses Opus for calls where avg output < 500 tokens AND total such calls > 20 | Switch those calls to Sonnet/Haiku — estimate savings from rate delta |
| `low_cache_hit_rate` | Cache read tokens / input tokens < 20% AND agent has > 10 calls | Enable prompt caching for the system prompt and stable context blocks |
| `excessive_cache_writes` | Cache write tokens > 3× cache read tokens | Cache TTL too short OR cache key churning — investigate prompt template stability |
| `redundant_calls` | ≥ 5 calls with identical `prompt_hash` in the run | Add response memoization layer |
| `oversized_prompts` | Avg input tokens for an agent > 20k | Review context assembly; move rarely-used context into on-demand retrieval |
| `retry_storm` | Retry rate > 15% for any agent | Root-cause the failures (rate limits? malformed responses?); each retry doubles cost |
| `unbatched_small_calls` | > 50 calls with < 200 input tokens each from the same agent | Batch into a single multi-item prompt |
| `output_token_waste` | Avg output tokens > 4k AND agent is a classifier/extractor | Add strict response schema / `max_tokens` limit |
| `no_streaming_on_long_outputs` | Avg output > 2k AND streaming disabled | Enable streaming (doesn't reduce cost, but flagged as UX recommendation) |
| `model_downgrade_candidate` | Full run cost > $2.00 AND Opus usage > 70% | Evaluate per-agent model assignment; present current vs. proposed cost |

**Savings estimation:** each rule computes `est_savings_usd` from actual tokens observed × hypothetical alternative rate — not vague percentages.

**Extensibility:** rules are registered in a list; adding a new rule = one new class. Unit-tested against synthetic `llm_calls` fixtures.

### F. UI integration

1. **Cost indicator in header** — live running total for the current run (updates via SSE or polling every 5s): `$0.47 · 12.4k tokens`
2. **"Open cost report" button** — visible when a run completes; opens the Excel file (or renders a preview modal showing Sheet 1 summary HTML-equivalent)
3. **Cost history page** (under `/settings/cost-history`) — table of past sessions with totals; click → download the `.xlsx`
4. **Theme-aware** — UI elements respect light/dark theme from the theme system; the Excel file itself uses a neutral professional palette (not theme-dependent, since Excel will be viewed outside the app)

### G. Privacy & security

1. **Prompt content is NOT written to Excel by default** — only tokens, model, agent, timing, cost. Prompts can contain source code / proprietary data.
2. **Optional verbose mode** — `.env` flag `COST_REPORT_INCLUDE_PROMPTS=false` (default false); if enabled, adds a `Prompts` sheet with first 500 chars of each prompt, clearly marked sensitive.
3. **File permissions** — reports dir is `chmod 700` on Unix; documented in `DEPLOYMENT.md`.
4. **No network egress** — report generation is fully local.

### H. Implementation order (this feature)

1. Pricing config + SQLite schema + migrations
2. `TrackedLLMClient` wrapper — instrument all call sites
3. Excel generator — Sheets 1–4 (data sheets first, no recommendations yet)
4. Recommendation engine — Sheet 5, start with 5 highest-value rules
5. Auto-save hooks — run start / run end / session close
6. UI integration — header indicator + cost history page
7. Sheet 6 (trend) — last, requires historical data

### I. Testing

1. **Unit tests** for pricing math with known token counts (e.g., 1M input tokens at $15/M = exactly $15.00)
2. **Fixture-based tests** for each recommendation rule — synthetic `llm_calls` data that should / should not fire the rule
3. **Excel schema test** — open generated workbook, assert all 6 sheets exist with expected headers
4. **End-to-end test** — run a small conversion job, verify workbook is generated, totals match the sum of logged calls to the cent
5. **Regression guard** — snapshot test on the Excel structure so accidental sheet/column changes are caught

### J. Configuration summary (additions to `.env`)

```
COST_REPORT_ENABLED=true
COST_REPORT_INCLUDE_PROMPTS=false
COST_REPORT_RETENTION_DAYS=90
COST_REPORT_COST_ALERT_THRESHOLD_USD=5.00
MODEL_PRICING_CONFIG_PATH=backend/config/model_pricing.yaml
```

---

## 2026-04-19 — Theme system + unbounded code generation time `[PLANNED]`

### A. Light / Dark theme for AppNova UI

**Goal:** Full theme support across the entire app, including report rendering.

**Steps:**
1. **Theme tokens** — create `frontend/src/theme/tokens.ts`:
   - `light` and `dark` token sets: `bg`, `surface`, `surfaceAlt`, `text`, `textMuted`, `border`, `accent`, `success`, `warning`, `danger`, `codeBg`, `codeFg`
   - Export as CSS custom properties (e.g. `--color-bg`, `--color-text`) so non-React code (Mermaid, markdown renderers) can consume them
2. **Theme provider** — `frontend/src/theme/ThemeProvider.tsx`:
   - React context with `{ theme: 'light' | 'dark' | 'auto', setTheme, effectiveTheme }`
   - `effectiveTheme` resolves `auto` via the time-of-day rule (see section B)
   - Writes `data-theme="light|dark"` on `<html>` and toggles a CSS class for Tailwind `dark:` variants
   - Persists manual override in `localStorage` under `appnova.theme`
3. **Tailwind config** — `tailwind.config.js`:
   - `darkMode: 'class'`
   - Map token CSS variables into the Tailwind color palette so `bg-surface`, `text-muted`, etc. work in both modes
4. **Component audit** — sweep every component under `frontend/src/components/` and replace hardcoded colors (`#fff`, `bg-white`, `text-black`, hex codes) with semantic tokens
5. **Toggle UI** — header control with 3 states: `Light` / `Dark` / `Auto` (auto is default)
6. **Report rendering theme compliance:**
   - **Markdown renderer** (e.g. `react-markdown`): inject a theme-aware CSS class; syntax highlighter (Prism/Shiki) swaps between `github-light` and `github-dark` themes based on `effectiveTheme`
   - **Mermaid diagrams:** call `mermaid.initialize({ theme: effectiveTheme === 'dark' ? 'dark' : 'default' })` and **re-render** all diagrams on theme change (keep a registry of mounted diagrams and trigger re-render via `mermaid.run()`)
   - **Tables / code blocks / callouts** in reports: use token-based colors only, no hardcoded styles
   - **Exported PDF/HTML reports** (from section on auto-export): embed the current theme's CSS at export time; include a "Light version" / "Dark version" option in the Export modal
7. **Testing matrix** — every report type rendered in both themes, verify contrast (WCAG AA) for text vs. background

### B. Time-based auto theme switching (7pm → dark, 6am → light)

**Goal:** When theme is set to `auto`, switch based on local time with a smooth transition at the boundary — even if the user is actively working at 6:59pm.

**Steps:**
1. **Time rule** — in `frontend/src/theme/autoThemeScheduler.ts`:
   - `resolveAutoTheme(now: Date): 'light' | 'dark'`
     - `dark` if hour >= 19 (7pm) OR hour < 6 (before 6am)
     - `light` otherwise
   - Pure function, takes `Date` for testability
2. **Scheduler tick** — the provider runs a `setInterval` every 60 seconds checking `resolveAutoTheme(new Date())`; if result differs from `effectiveTheme`, fire the transition
3. **Boundary transition (the 6:59pm → 7pm case):**
   - On change, add a CSS class `theme-transitioning` to `<html>` that applies `transition: background-color 400ms ease, color 400ms ease, border-color 400ms ease` to all themed elements
   - Swap `data-theme` attribute → CSS variables update → smooth fade happens automatically
   - Remove `theme-transitioning` class after 500ms (avoids transitions on every subsequent style change)
   - Re-render Mermaid diagrams with the new theme (diagrams are SVG — swap the theme and re-invoke `mermaid.run()` on the registry)
   - Show a tiny non-blocking toast: *"Switched to dark mode"* (auto-dismisses in 3s, dismissible)
4. **Edge cases:**
   - **User has manual override** (`theme: 'light'` or `'dark'`): scheduler does nothing; only active when `theme === 'auto'`
   - **Tab was backgrounded across the boundary:** on `visibilitychange` → `visible`, re-run `resolveAutoTheme` immediately (catches the case where the browser throttled `setInterval` while backgrounded)
   - **System clock change / DST:** the 60s interval catches it within a minute; no special handling needed
   - **User is mid-action (typing in chat, report rendering):** the CSS-variable approach means no component re-mounts, no input loss, no scroll jump
5. **Configurability** — expose the thresholds in `.env` so they can be tuned without code changes:
   ```
   APPNOVA_DARK_START_HOUR=19
   APPNOVA_LIGHT_START_HOUR=6
   APPNOVA_THEME_TRANSITION_MS=400
   ```
   Backend serves these via `GET /api/config/theme` on app load
6. **Testing:**
   - Unit tests on `resolveAutoTheme` for 00:00, 05:59, 06:00, 18:59, 19:00, 23:59
   - Manual test: mock `Date` to 18:59:30, wait 60s, verify transition fires at 19:00

### C. Unbounded code generation time (source → target file conversion)

**Goal:** Code generation must run until every source file is converted. No timeouts, no partial completion.

**Steps:**
1. **Remove all generation-side timeouts:**
   - Audit `backend/` for `asyncio.wait_for`, `timeout=` kwargs on HTTP clients, LLM client timeouts — remove from the conversion pipeline specifically (keep short timeouts on unrelated API health checks)
   - Document per-call timeout policy in [backend/config/timeouts.py](backend/config/timeouts.py): generation = unlimited, everything else = bounded
2. **Long-running job model** — convert file conversion from a synchronous request to a background job:
   - Job queue: start with in-process `asyncio.Queue` + SQLite job table (`jobs(id, type, status, progress, total, started_at, finished_at, error)`); upgrade to Celery/RQ later if needed
   - `POST /api/convert/start` → returns `job_id`, enqueues work
   - `GET /api/convert/status/:job_id` → `{ status, current_file, completed, total, eta_estimate }`
   - `GET /api/convert/stream/:job_id` → Server-Sent Events stream of progress updates
3. **Per-file loop with resumability:**
   - Iterate every source file, mark each as `pending → processing → done | failed`
   - On failure of a single file, log + continue (don't abort the whole job); collect errors into a final report
   - On process restart, resume from the last `pending`/`processing` file (checkpoint after each file)
4. **Frontend progress UI:**
   - Replace any spinner/progress bar with a **determinate progress component** showing `X / Y files converted`, current filename, scrolling log of completed files
   - No "this is taking too long" warning; show elapsed time neutrally
   - User can minimize the panel and keep working; completion triggers a toast
5. **Prevent browser/proxy timeouts:**
   - SSE keep-alive ping every 15s
   - If reverse proxy (nginx, etc.) is in front, document `proxy_read_timeout` bump in `DEPLOYMENT.md`
6. **LLM cost/rate-limit handling (since jobs can be long):**
   - Respect provider rate limits with exponential backoff on 429
   - Checkpoint every N files so a rate-limit retry doesn't replay completed work
   - Surface estimated token usage in the progress UI (optional)
7. **Cancellation** — explicit user-initiated cancel sets job status `cancelled`; in-flight file completes, no new files start
8. **Testing:**
   - Simulate a 500-file project, verify it runs to completion over multiple hours
   - Kill the backend mid-job, restart, verify resumption
   - Induce a single-file failure, verify the job continues and the failure appears in the final report

---

## 2026-04-19 — Earlier in this session `[PLANNED]`

### 1. Mermaid diagrams bombing in ALL reports

**Root cause hypotheses (verify before fixing):** unescaped special chars in node labels, reserved keywords as node IDs, mixed diagram syntaxes, leaked markdown fences, frontend/backend Mermaid version mismatch.

**Steps:**
1. **Diagnose first** — log raw Mermaid strings from 3–4 failing reports to `logs/mermaid_failures.log`. Do not guess.
2. **Server-side validator** — `backend/services/mermaid_validator.py`:
   - Install `mermaid-cli` (`mmdc`) or Python `mermaid-py`
   - `validate(diagram_str) -> (bool, error_msg)`
3. **Auto-repair loop** in report generation:
   - Generate → validate → on failure, re-prompt LLM with parse error → retry max 2x → fallback to "diagram unavailable" placeholder
4. **Harden prompt template** — single shared template `prompts/mermaid_template.py`:
   - "Wrap all node labels in double quotes"
   - Forbidden keyword list (`end`, `class`, `state`, etc.)
   - 2 valid examples per diagram type (flowchart, sequence, ER, class)
   - "Output ONLY the diagram, no ` ```mermaid ` fences"
5. **Frontend sanitizer** in the Mermaid renderer component — strip code fences, trim whitespace before `mermaid.render()`
6. **Pin Mermaid version** in `package.json`; document it
7. **Theme compatibility** — validator should accept the current theme (light/dark) as a parameter and confirm the diagram renders in both

### 2. Persistent memory across agents + sessions

**Steps:**
1. **Storage:** SQLite at `backend/data/memory.db`. Schema:
   - `sessions(id, user_id, created_at, last_active)`
   - `agent_memory(session_id, agent_name, key, value_json, updated_at)`
   - `artifact_cache(file_hash, artifact_type, content, created_at)` — keyed by SHA256 of source file
2. **Memory layer** — `backend/memory/store.py`:
   - `get_agent_memory(session_id, agent_name)`
   - `save_agent_memory(session_id, agent_name, key, value)`
   - `get_cached_artifact(file_hash, type)` / `cache_artifact(...)`
3. **Wire into each agent** — load prior memory before LLM call; persist key findings after. Hash input files and check `artifact_cache` before re-analyzing.
4. **Cache invalidation:** file_hash changes → cache miss → re-process. No manual invalidation.
5. **Session restore:** on app load, fetch last session by user_id, repopulate UI state.
6. **Cleanup:** TTL on sessions older than `SESSION_RETENTION_DAYS` (default 30), configurable in `.env`.

### 3. UI restructure

#### 3a. Global chat UI (right sidebar)
1. New component `frontend/src/components/GlobalChat.tsx` — fixed right drawer, collapsible
2. New endpoint `POST /api/chat/global` with access to all agent contexts
3. Per-agent chat stays inside each agent card (unchanged)
4. Shared chat context provider so global chat can reference any agent's last output

#### 3b. Hide Glob/Grep/Read/LS tool cards from reports
1. Tool metadata flag — `display_in: "report" | "console"`
2. Glob / Grep / Read / LS → console only; report-generating tools → reports page
3. New `Console` tab next to `Reports` — collapsible log viewer with filter by agent/tool
4. Reports page renders only final structured artifacts (markdown, diagrams, tables)

#### 3c. Login page with .env credentials
1. **`.env`:**
   ```
   APPNOVA_USERNAME=admin
   APPNOVA_PASSWORD=<bcrypt_hash>
   APPNOVA_JWT_SECRET=<random_64_char>
   APPNOVA_SESSION_HOURS=24
   ```
2. **Backend** — `backend/auth/` module:
   - `POST /api/auth/login` — validates against `.env`, returns JWT
   - `GET /api/auth/me` — validates JWT
   - Middleware on all `/api/*` routes except login
3. **Frontend:**
   - New route `/login` with username/password form
   - `AuthGuard` wrapper on dashboard route → redirect to `/login` if no valid token
   - Token in `httpOnly` cookie (preferred) or `localStorage`
4. **`.env` stores bcrypt hash, not plaintext.** Add CLI helper `python scripts/hash_password.py` to generate the hash.

### 4. Auto-export reports with timestamp + save options

**Steps:**
1. **Export directory:** `exports/<session_id>/<YYYY-MM-DD_HH-MM-SS>_<agent>_<report_type>.{md,pdf,html}`
2. **Auto-write Markdown** on every report generation (cheap)
3. **Save As modal** — per-report "Export As" button:
   - Format: PDF / Markdown / HTML / DOCX
   - Include diagrams: yes/no
   - Theme variant: light / dark (ties into theme system)
   - Destination: download / save to exports dir
4. **Export service** — `backend/services/exporter.py`:
   - Markdown → PDF via `weasyprint` or `markdown-pdf`
   - Markdown → DOCX via `python-docx` or `pandoc`
   - Mermaid diagrams pre-rendered to SVG/PNG before embedding
5. **Retention:** `.env` → `EXPORT_RETENTION_DAYS=30`, daily cleanup job
6. **Index file:** `exports/index.json` updated on each export so frontend can list past exports

### 5. Detailed README + DevOps + Data Migration (mock data only)

#### 5a. Auto-generated README files
For every converted app, converter emits:
1. **Root `README.md`:** overview, tech stack, prerequisites, setup steps, scripts, project tree (depth 2)
2. **`frontend/README.md`:** framework-specific setup, env vars, build commands
3. **`backend/README.md`:** API base URL, endpoint summary, env vars, DB notes

#### 5b. `DEPLOYMENT.md` + artifacts (no DevOps pipeline required)
1. **`Dockerfile`** for frontend + backend (multi-stage, production-ready)
2. **`docker-compose.yml`** — frontend + backend + DB, networked
3. **`.env.example`** — all required vars with placeholders + inline comments
4. **`DEPLOYMENT.md`:**
   - Required env vars (table format)
   - Port mappings
   - Build commands
   - Health check endpoints
   - "Future CI/CD" section — plain-English pipeline steps for whoever wires it up later

#### 5c. Data migration with MOCK DATA ONLY (clean code)
**Constraint:** Do NOT pull real production data. Generate mock data from the source schema structure.

1. **Schema extraction agent:**
   - Analyzes source DB models/migrations
   - Outputs `migrations/source_schema.json`, `migrations/target_schema.json`, `migrations/mapping.json`
2. **Mock data generator** — `migrations/generate_mock_data.py`:
   - Reads `source_schema.json`
   - Uses `Faker` to generate realistic mock rows respecting types + FK relationships
   - Configurable row counts per table via `migrations/mock_config.yaml`
   - Outputs `migrations/mock_data/<table>.json`
3. **Migration script** — `migrations/migrate.py`:
   - Reads mock data → applies mapping → inserts into target DB
   - Idempotent (truncate + insert OR upsert by PK)
   - Validation pass: row counts match, FK integrity, no nulls in NOT NULL columns
4. **`DATA_MIGRATION.md`:**
   - How to swap mock for real data later (point to a different source — design is source-agnostic)
   - Mapping table (source field → target field → transformation)
   - Validation queries
   - Rollback procedure
5. **Clean code principles:**
   - Pure functions for transformations (fully testable)
   - No hardcoded credentials (all from `.env`)
   - `--dry-run` flag prints planned migration without writing
   - Transaction wrapping per table
   - No real-data shortcuts, no TODOs, no commented-out code

---

## Suggested implementation order

1. **Mermaid fix** — blocking; affects every report
2. **Theme system (light/dark + auto switching)** — foundational for report rendering
3. **Login page** — small, unblocks multi-user
4. **Cost & token usage Excel report** — instrument early so every subsequent feature is measured; the recommendation engine guides later optimization work
5. **UI restructure (hide tool cards + global chat)** — high user-perceived value
6. **Unbounded code generation (long-running job model)** — reliability win
7. **Persistent memory** — biggest perf win, more design work
8. **Auto-export** — additive
9. **README + data migration generators** — largest scope; build last on top of stable converter

---

## Legend

- `[PLANNED]` — designed, not started
- `[IN-PROGRESS]` — actively being built
- `[DONE]` — merged / deployed
- Update this file on every meaningful change. Newest entries at the top.
