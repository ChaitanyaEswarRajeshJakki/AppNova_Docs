# AppNova — Code Modernization Studio

> Turn any legacy codebase into a runnable, demoable target stack — line-by-line, 1-to-1, with a full audit trail.
> Drive Claude Code headless through a DAG of specialist agents, get back architecture diagrams, security audits, a file-by-file migration blueprint, an actually-runnable converted project, and `.md` + `.docx` + `.pdf` reports — all on your **Claude Max subscription** (zero API spend for analysis runs).

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Max%20Subscription-D97706?logo=anthropic&logoColor=white)](https://docs.claude.com/en/docs/claude-code/overview)
[![Playwright](https://img.shields.io/badge/Playwright-1.47-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Mermaid](https://img.shields.io/badge/Mermaid-Server--Rendered-FF3670?logo=mermaid&logoColor=white)](https://mermaid.js.org/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5-FF6B6B)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🖼️ Frontend Architecture at a Glance

![AppNova React Frontend — layered architecture infographic](AppNova_Frontend_Architecture.svg)

> Full interactive version: [AppNova_Frontend_Architecture.html](AppNova_Frontend_Architecture.html) · Raw SVG: [AppNova_Frontend_Architecture.svg](AppNova_Frontend_Architecture.svg)

---

## ✨ What is AppNova?

AppNova is a self-hosted modernization studio that ingests a legacy codebase and delivers a complete, demoable migration package:

- 💬 **Per-agent chat drawer** on every report card — ask follow-ups, request edits, or flip into **Fix code** mode and let Claude edit the converted project in place. Every code-mode turn snapshots `converted/` first so any edit is reversible.
- 🧠 **14 specialist agents** — discovery, code-analysis, architecture, security, business-rules, integration, data-migration, devops, migration-planner, code-generation, documentation, code-review, testing, ui-ux, run as a DAG of waves.
- 📚 **Playbook + RAG layer** — every supported migration type ships a `PlaybookDefinition` ([`backend/playbooks/`](backend/playbooks/)) with idiomatic-translation hints, type-mapping tables, parity floors, and per-agent prompts. The optional **ChromaDB RAG** layer ([`backend/playbooks/rag/`](backend/playbooks/rag/)) retrieves hand-authored gold examples + verified prior conversions, spliced into `code-generation` and `migration-planner` prompts as a `RETRIEVED EXAMPLES` block. Disable with `APPNOVA_RAG_ENABLED=0`.
- 🛡️ **Production-ready placeholder hardening** — deploy-details form (24 fields incl. Azure AD GUIDs / Key Vault refs / SMTP / SSO), regex-based leak detector, **automatic quarantine pass** rewrites leaked literals to `__FIELDNAME__` placeholders + ships a deterministic `docs/SECRETS_MAPPING.md` with `az keyvault secret set` / `dotnet user-secrets set` commands.
- 🗺️ **Server-side Mermaid prerender** — every ` ```mermaid ` block is rendered to SVG/PNG by a Playwright/Chromium pass before the report is saved. Same pixel-perfect output in browser, PDF export, and DOCX.
- 🔄 **`file_map.json` contract** — `migration-planner` ships an authoritative source→target file map; `code-generation`, `code-review`, `testing`, and deterministic auditors (`file_coverage`, `parity_checker`, `round_trip_tester`, `deploy_audit`) all read it.
- 🧮 **Eval harness** — `python -m backend.harness {score|score-all|diff}` produces a CSV scorecard of coverage / leak / cost / elapsed numbers. Zero LLM cost; regression-detects prompt-edit changes via threshold gates.
- ⏱️ **Topbar run-elapsed timer** survives hub→workspace navigation (server-side stamped, frontend rehydrates from `/api/session/<sid>/status`).
- 📦 **Auto-export** writes every finished report as `.md`, `.docx`, **and** `.pdf` the moment it completes.
- 🧊 **Demo sessions** freeze a completed run (reports + exports + converted project) into [`demo_sessions/`](demo_sessions) for zero-token replay.
- 💵 **Cost tracker** persists per-agent token counts to a 5-sheet Excel workbook.
- 🔒 **100% local code** — your source never leaves your machine; only prompts go to Anthropic.

---

## 📐 Architecture at a Glance

```text
┌───────────────────────────────────────────────────────────────────────────┐
│   Browser  (frontend/)  —  static HTML/JS, no build step                  │
│   hub.html · index.html · review.html · login.html                        │
│   Cards per agent · Chat drawer · Export panel · Demo list                │
└──────────────────────────┬────────────────────────────────────────────────┘
                           │ REST + SSE  (login.html → JWT → /api/*)
┌──────────────────────────▼────────────────────────────────────────────────┐
│   FastAPI backend  (backend/main.py — :8002)                              │
│                                                                           │
│   /api/upload                  multipart / zip → uploads/{sid}/source/   │
│   /api/analyze/{sid}           SSE — wave/agent events                   │
│   /api/chat/{sid}/{aid}        per-card chat (report or code-fix mode)   │
│   /api/mermaid/render          server-side SVG cache                      │
│   /api/export/{sid}/{aid}.*    .docx / .pdf re-download                   │
│   /api/demo-sessions/*         freeze · load · list · delete              │
│   /api/session/{sid}/deploy-config  deploy-form CRUD + materialise        │
│   /api/rag/*                   seed / ingest / query endpoints            │
│                                                                           │
│   ┌─────────────────────────────────────────────────────────────────┐     │
│   │ Supervisor  (agents/supervisor.py) — DAG → topological waves    │     │
│   │                                                                 │     │
│   │  Wave 0:  discovery                                             │     │
│   │  Wave 1:  code-analysis · architecture · security               │     │
│   │           business-rules · integration · data-migration · devops│     │
│   │  Wave 2:  migration-planner             ← writes file_map.json  │     │
│   │  Wave 3:  code-generation               ← writes converted/     │     │
│   │           (multipass: 50-row chunks w/ cooldown when enabled)   │     │
│   │  Wave 3b: documentation                 ← writes converted/docs/│     │
│   │  Wave 4:  code-review · testing · ui-ux                         │     │
│   │  Wave 5:  migration_pipeline (deterministic, post-agent)        │     │
│   │           field_extractor → parity_checker → round_trip_tester  │     │
│   │           rag-learn → gated write into {playbook}__learned      │     │
│   └─────────────────────────────────────────────────────────────────┘     │
│                                                                           │
│   Post-processing (deterministic, zero LLM cost):                        │
│   • file_coverage     source→target coverage audit (fails < 70%)         │
│   • deploy_audit      literal + regex leak scan over converted/           │
│   • quarantine_leaks  rewrite leaks → __FIELDNAME__ placeholders         │
│   • render_secrets_mapping → docs/SECRETS_MAPPING.md                     │
│   • mermaid prerender (Playwright Chromium → SVG cache by sha256)        │
│   • context_attestation scan (✅ full / ⚠ partial / ❌ gap per agent)    │
│   • export.py        md → html → docx (python-docx) / pdf (Chromium)     │
│   • cost_tracker     per-agent token ledger → 5-sheet .xlsx              │
└──────────────────────────┬────────────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────────────┐
│   Claude Code CLI  →  Anthropic servers  →  streamed tool calls           │
│   • Read / Glob / Grep on cwd=uploads/{sid}/source/                       │
│   • Write / Edit on cwd=uploads/{sid}/converted/  (writer-agents only)   │
│   • Per-cwd writer lock serialises code-gen · code-review · testing · ui  │
└───────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

| Decision | Why it matters |
|---|---|
| **Parallel waves over a hardcoded loop.** Agents declare `upstream` deps; `compute_waves()` topologically layers them. | Wave size is whatever the DAG allows — independent agents run concurrently. |
| **Blackboard state.** Completed agents write markdown to `RunState`; later waves read via file paths, not in-memory passing. | Crash-resumable — a dropped wave can be re-run from where it died. |
| **Writer-agent lock.** code-generation, code-review, testing, ui-ux all write into `converted/` and serialise on a per-cwd lock. | Concurrent writers can't trample shared files. |
| **`file_map.json` is enforced.** If migration-planner ships without a parseable `## A.4 file_map.json` block, supervisor saves the draft and dispatches a repair pass. | Downstream code-generation reads `context/file_map.json` as its authoritative contract. |
| **Coverage gate (70% floor).** code-generation is downgraded to `error` when file-coverage < 70%, hard-skipping code-review / testing / ui-ux. | Prevents silently-narrow conversions from reaching downstream agents. |
| **Chat snapshots.** "Fix code" mode copies `converted/` to `chat/{agent}/snapshots/snap-xxxx/` before Claude edits anything. | Any turn is reversible by restoring the snapshot folder. |
| **Playbook resolves once per run.** `resolve_playbook(upload_dir)` picks the best-matching `PlaybookDefinition` by scoring `source_signals` against the file tree. | Idiomatic-translation hints, parity floors, and skip lists are applied consistently across every agent. |
| **RAG is best-effort enrichment.** `build_agent_prompt` appends a `RETRIEVED EXAMPLES` block when retrieval yields hits; deterministic mapping + parity + coverage gates remain authoritative. | If ChromaDB is missing or `APPNOVA_RAG_ENABLED=0`, the pipeline behaves identically to pre-RAG. |

---

## 🤖 The 14 specialist agents

Every agent is registered in [`backend/config.py`](backend/config.py) (`AGENT_REGISTRY`). All tiers pin to **Claude Sonnet 4.6** by default so demo-freeze replays are byte-for-byte reproducible. Override per-tier via `HEAVY_MODEL` / `LIGHT_MODEL` / `DISCOVERY_MODEL`.

| Agent ID | Tier | Wave | Output |
|---|---|---|---|
| `discovery` | heavy | 0 | Tech inventory, narrative overview, per-agent context briefs |
| `code-analysis` | heavy | 1 | Module graph, complexity, tech debt, ER diagram |
| `architecture` | heavy | 1 | Layer map, Mermaid flowcharts, ADRs |
| `business-rules` | heavy | 1 | Rules catalog, validation matrix, per-workflow state machines |
| `security` | heavy | 1 | OWASP mapping, secrets scan, auth audit |
| `integration` | light | 1 | External API touchpoints, retry/circuit patterns, target-stack bindings |
| `data-migration` | light | 1 | Schema map, target ER diagram, migration SQL/ORM scripts |
| `devops` | light | 1 | Dockerfiles, CI YAML, IaC, monitoring (reads `deploy_config.json` + canonical templates) |
| `migration-planner` | heavy | 2 | Phases, gantt, risks, **Section A file-by-file blueprint + `file_map.json`** |
| `code-generation` | heavy | 3 | Full target-stack project in `converted/` (chunked multipass when `APPNOVA_CODEGEN_MULTIPASS=true`) |
| `documentation` | light | 3 | Real `docs/README.md`, `docs/SETUP.md`, `docs/DEPLOY.md`, `docs/API.md`, `docs/DATA_DICTIONARY.md` written **into the converted tree** |
| `code-review` | heavy | 4 | Gap + fidelity audit against `file_map.json` (requires code-generation) |
| `testing` | light | 4 | Unit + integration + E2E scaffolds in target-stack conventions |
| `ui-ux` | heavy | 4 | Navigation tree flowchart, component polish, SCSS migration |

### After-the-agents auditors (deterministic, zero LLM cost)

| Auditor | When | Effect |
|---|---|---|
| [`file_coverage`](backend/agents/file_coverage.py) | post `code-generation` | Coverage %. Downgrades to `error` when < 70% (override: `APPNOVA_COVERAGE_FLOOR`). |
| [`deploy_audit`](backend/agents/deploy_audit.py) | post `code-generation` | 8 literal leaks + 5 regex patterns (Azure AD GUID, secret-token, Server=Password=, User Id=, Azure FQDN). Writes `docs/DEPLOY_AUDIT.md`. |
| [`quarantine_leaks`](backend/agents/deploy_audit.py) | when `APPNOVA_QUARANTINE_LEAKS=true` (default on) | Rewrites each leak: literal → user-supplied value OR `__FIELDNAME__` placeholder. |
| [`render_secrets_mapping`](backend/agents/deploy_audit.py) | always after deploy_audit | `docs/SECRETS_MAPPING.md` — one row per placeholder with `az keyvault` + `dotnet user-secrets` fill commands. |
| [`context_attestation` scan](backend/agents/supervisor.py) | post each agent (except migration-planner) | Classifies `## Context` block as `full / partial / gap / weak / missing`. Painted as chip on each card. |
| [`enrich_file_map_from_context`](backend/agents/synthesize_file_map.py) | post `migration-planner` | Deterministic union of planner's map with `field_inventory.json` + `source_routes.json` + stylesheet walker. Auto-augmented rows carry `_disk_inferred=true`. |
| [`write_source_route_manifest`](backend/agents/source_routes.py) | pre `migration-planner` | Walks source for state/path/page declarations (AngularJS ui-router, React Router, Vue, Blazor, ASP.NET, Rails, Laravel, Django). Writes `context/source_routes.json`. |

---

## 📚 Playbook + RAG layer

### Playbook system

A `PlaybookDefinition` ([`backend/playbooks/schema.py`](backend/playbooks/schema.py)) is six frozen dataclasses:

| Layer | Dataclass | Purpose |
|---|---|---|
| 1 | `PlaybookMapping` | Source ↔ target field/type mapping, synonym pairs, ignored-field regex |
| 2 | `PlaybookTransformation` | `codegen_style`, global `prompt_preamble`, per-agent `agent_hints` |
| 3 | `PlaybookValidation` | `coverage_floor_pct`, `parity_green_floor_pct`, `require_round_trip` |
| 4 | `PlaybookWorkflow` | `skip_agent_ids`, `extra_agent_ids`, `fail_fast`, `round_trip_mode` |
| 5 | `PlaybookFeedback` | Report formats, cost-report toggle, post-step hook IDs |
| 6 | `PlaybookRAG` | RAG kill-switch + retrieval policy (per-playbook) |

Registered playbooks ([`backend/playbooks/registry.py`](backend/playbooks/registry.py)):

| Playbook ID | Source | Target |
|---|---|---|
| `laravel-to-dotnet` | Laravel PHP + Eloquent + Blade | .NET 8 Minimal API + React 18 TS |
| `angularjs-to-react` | AngularJS 1.x ($scope / $http / ui-router) | React 18 + TS + Hook Form + Router v6 |
| `react-upgrade` | React class components / vanilla JS | React 18 functional + TS strict |
| `generic` | Any unrecognised stack | Stack-agnostic agent hints |

`resolve_playbook(upload_dir)` scores every playbook against the file tree via `fnmatch` on `source_signals`. Best match wins (falls back to `GENERIC_PLAYBOOK`). Context is injected into every agent prompt as a `## PLAYBOOK GUIDANCE — <source> → <target>` block.

### RAG (ChromaDB, optional)

Three collections per playbook in one persistent ChromaDB store under `<repo>/chroma/`:

| Collection | Source | Lifetime | Trust |
|---|---|---|---|
| `{playbook}__curated` | Hand-authored source→target pairs (JSONL seeds) | Permanent, version-controlled | High — retrieved first |
| `{playbook}__learned` | Auto-stored verified conversions (gated by parity ≥ floor + supervisor_ok) | Permanent | Medium — fallback after curated |
| `{playbook}__source__{sid}` | Chunks of the current upload | Per-session, deleted on session close | Context-only |

Disable entirely with `APPNOVA_RAG_ENABLED=0`. When chromadb is unimportable the layer gracefully no-ops.

---

## 🧮 Eval harness

```bash
python -m backend.harness score <session_root>       # one session
python -m backend.harness score-all [--csv out.csv]  # all sessions under uploads/
python -m backend.harness diff baseline.csv new.csv  # Δ table with REGR/IMPR/SAME pills
```

Gates checked: `file_coverage ≥ 70%`, `deploy_audit.leak_count == 0`, `context_attestation.verdict == 'full'`. Cost: zero LLM calls (pure file I/O). CI integration:

```yaml
- run: python -m backend.harness score-all --csv eval.csv --exit-on-fail
```

---

## 🚀 Quick start

### Requirements

- **Python 3.11** (exact major.minor; verified by `start.bat`)
- **Node.js 18+**
- **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code` with `claude login` (Max subscription)
- **Playwright Chromium** — `playwright install chromium` (Mermaid prerender + PDF export)
- **ChromaDB** — installed via `requirements.txt` (RAG layer; degrades to no-op if missing)

### Windows — one-command start

```powershell
.\start.bat
```

The launcher:

1. Verifies Python 3.11 and creates `backend/venv`.
2. Installs `backend/requirements.txt`.
3. Starts FastAPI on **`http://127.0.0.1:8002`** without `--reload` (uvicorn's reloader forces `WindowsSelectorEventLoopPolicy`, breaking `asyncio.create_subprocess_exec` — see `changes.md`).
4. Serves the static `frontend/` on **`http://127.0.0.1:5500`** via `http.server`.
5. Opens `login.html` in your browser.

Stop with `.\start.bat stop`.

### macOS / Linux — manual start

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --host 127.0.0.1 --port 8002

# Serve frontend (another terminal)
cd frontend
python3 -m http.server 5500
```

### Environment variables

Create a `.env` in the project root:

```ini
# ── Claude Code CLI ──
CLAUDE_CODE_PATH=claude                   # or absolute path e.g. C:\Users\Public\npm-global\claude.cmd
HEAVY_MODEL=claude-sonnet-4-6
LIGHT_MODEL=claude-sonnet-4-6
DISCOVERY_MODEL=claude-sonnet-4-6
AGENT_TIMEOUT=1200                        # seconds per agent (24h for long monoliths)
DISCOVERY_TIMEOUT=480
SERVER_PORT=8002

# ── Code-gen multipass ──
APPNOVA_CODEGEN_MULTIPASS=true            # chunk file_map.json into 50-row slices
APPNOVA_CODEGEN_CHUNK_SIZE=50            # rows per chunk
APPNOVA_CODEGEN_COOLDOWN_SECONDS=30      # sleep between chunks (max 270s for cache TTL)

# ── Quality gates ──
APPNOVA_COVERAGE_FLOOR=70                 # % minimum file-coverage before code-gen downgrades
APPNOVA_QUARANTINE_LEAKS=true            # auto-rewrite leak literals to __FIELDNAME__ placeholders
APPNOVA_MIGRATION_PLANNER_REPAIR=0       # 1 = re-enable strict repair pass (default off)

# ── RAG layer ──
APPNOVA_RAG_ENABLED=1                    # 0 to disable ChromaDB entirely
APPNOVA_RAG_DIR=./chroma                 # persistent Chroma store path

# ── Playwright (shared machine-wide install) ──
PLAYWRIGHT_BROWSERS_PATH=C:\Users\Public\ms-playwright

# ── Director mode (optional) ──
APPNOVA_DIRECTOR_MODE=0                  # 1 = Claude decides which subagents to spawn
```

---

## 🌐 API surface

All routes live in [`backend/main.py`](backend/main.py). Swagger UI at `http://127.0.0.1:8002/docs`.

### Core analysis

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/upload` | Multipart upload (folder drag-drop or zip) |
| POST | `/api/upload/github` | Clone and index a GitHub repo |
| POST | `/api/analyze/{session_id}` | SSE — DAG wave runner (primary) |
| GET | `/api/session/{session_id}/status` | Run status + `run_started_at` / `run_finished_at` |
| POST | `/api/session/{session_id}/cancel-agent/{agent_id}` | Stop a running agent |

### Chat & code-fix

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/chat/{session_id}/{agent_id}` | Per-card chat (report or code-fix mode) |
| GET | `/api/session/{session_id}/snapshots` | List per-turn snapshots of `converted/` |

### Deploy config

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/session/{session_id}/deploy-config` | Fetch 24-field deploy form + warnings |
| POST | `/api/session/{session_id}/deploy-config` | Save + materialise to `source/context/deploy_config.json` |

### Export & review

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/export/{session_id}/{agent_id}.md` | Re-download markdown |
| GET | `/api/export/{session_id}/{agent_id}.docx` | Re-download DOCX |
| GET | `/api/export/{session_id}/{agent_id}.pdf` | Re-download PDF |
| GET | `/api/review/{session_id}/file` | Fetch source + target file pair for diff view |
| GET | `/api/mermaid/render` | Server-side SVG render (Playwright cache) |

### Demo sessions

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/demo-sessions/freeze/{session_id}` | Snapshot a completed run |
| GET | `/api/demo-sessions` | List frozen demos |
| POST | `/api/demo-sessions/load/{demo_id}` | Restore a demo snapshot |
| DELETE | `/api/demo-sessions/{demo_id}` | Remove a demo |

### RAG

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/rag/seed` | Seed `__curated` from JSONL examples |
| GET | `/api/rag/stats` | Collection sizes + hit counts |

### Eval harness (CLI only — no HTTP endpoint)

```bash
python -m backend.harness score <session_root>
python -m backend.harness score-all [--uploads-dir uploads/] [--csv out.csv] [--exit-on-fail]
python -m backend.harness diff baseline.csv new.csv [--exit-on-regression]
```

---

## 📂 Repository layout

```text
AppNova/
├── backend/
│   ├── main.py                      ← FastAPI entry; all routes (:8002)
│   ├── config.py                    ← 14-agent AGENT_REGISTRY + tier→model map
│   ├── requirements.txt             ← Backend deps (incl. playwright, chromadb)
│   ├── agents/                      ← Agent runner package
│   │   ├── config.py                ← AgentSpec registry (mirrors backend/config.py)
│   │   ├── runner.py                ← `claude -p` subprocess + threaded pipes + Windows shim
│   │   ├── supervisor.py            ← DAG wave scheduler + post-run auditors + per-cwd lock
│   │   ├── state.py                 ← RunState TypedDict blackboard
│   │   ├── prompts.py               ← DISCOVERY_PROMPT + AGENT_PROMPTS + build_agent_prompt
│   │   ├── session_adapter.py       ← files/ → source/ + project-root detection
│   │   ├── deploy_audit.py          ← Literal + regex leak scanner + quarantine pass + secrets-mapping
│   │   ├── deploy_templates/        ← 9 canonical deploy templates (systemd, apache, nginx, IIS, etc.)
│   │   ├── file_coverage.py         ← Source→target coverage audit
│   │   ├── source_routes.py         ← 9-framework route detector → source_routes.json
│   │   ├── synthesize_file_map.py   ← file_map.json enrichment (field_inventory + routes + stylesheets)
│   │   ├── codegen_multipass.py     ← Chunked code-gen runner (50-row slices + crash-resume)
│   │   ├── parity_checker.py        ← Field-level parity between source and converted
│   │   ├── round_trip_tester.py     ← Automated live or plan round-trip validation
│   │   ├── migration_pipeline.py    ← Post-agent deterministic pipeline (field_extractor→parity→rag-learn)
│   │   ├── browser_test.py          ← Playwright browser-test dispatcher
│   │   ├── chat.py                  ← Per-card chat + code-fix mode + snapshot logic
│   │   ├── artifact.py / export.py  ← HTML artefacts + md→html→docx/pdf export
│   │   ├── mermaid_renderer.py      ← Playwright Mermaid SVG/PNG cache
│   │   ├── director.py              ← Alt: Claude-driven Task-tool dispatch (APPNOVA_DIRECTOR_MODE=1)
│   │   └── example_deploy_config.json ← Synthetic fixture for prompt examples
│   ├── playbooks/
│   │   ├── schema.py                ← 6-layer PlaybookDefinition dataclasses
│   │   ├── registry.py              ← PLAYBOOK_REGISTRY + resolve_playbook() + get_playbook()
│   │   ├── examples/                ← Curated JSONL seeds (per playbook)
│   │   └── rag/
│   │       └── client.py            ← Chroma persistent client + collection accessors
│   ├── harness/
│   │   ├── eval.py                  ← EvalScorecard + score_session + write_scorecard_csv
│   │   └── cli.py                   ← score / score-all / diff / run subcommands
│   ├── cost_tracker.py              ← Per-agent virtual-cost ledger → 5-sheet .xlsx
│   ├── model_pricing.yaml           ← Claude model prices for ledger
│   ├── auth.py                      ← JWT authentication layer
│   ├── projects.py                  ← Project management helpers
│   ├── dev_chat.py                  ← Development chat utility
│   └── analysis_cache.py            ← Result fingerprint caching
├── frontend/                        ← Static HTML/JS — no build step
│   ├── hub.html / hub.js            ← Project hub (list, create, open sessions)
│   ├── index.html / app.js          ← Main workspace (agent cards, SSE stream, deploy form)
│   ├── review.html / review.js      ← Side-by-side source↔target diff view
│   ├── login.html / login.js        ← JWT login flow
│   ├── style.css                    ← All styles
│   └── theme.js                     ← Dark/light theme toggle
├── demo_sessions/                   ← (gitignored) frozen run snapshots
├── uploads/                         ← (gitignored) per-session files
├── exports/                         ← (gitignored) auto-generated .md/.docx/.pdf reports
├── chroma/                          ← (gitignored) ChromaDB persistent store
├── data/                            ← (gitignored) cost_tracking.db
├── logs/                            ← (gitignored) Loguru output + agent dumps
├── start.bat                        ← Windows launcher (no --reload; port 8002)
├── changes.md                       ← Reverse-chronological change log
└── LICENSE                          ← MIT
```

---

## 🧪 Tech stack

**Agent runner** — Python `subprocess.Popen` + threaded pipes · `@anthropic-ai/claude-code` (npm global, 2.1.x native binary at `bin/claude.exe`) · `shutil.which` shim resolution · `asyncio.Queue` via `loop.call_soon_threadsafe` · `CREATE_NO_WINDOW` on Windows.

**Backend** — FastAPI 0.115 · Uvicorn 0.32 · python-docx 1.1 · Playwright 1.47 (Mermaid prerender + PDF) · loguru · openpyxl 3.1 (cost workbook) · PyYAML 6.0 · chromadb 0.5 (RAG, optional).

**Frontend** — Static HTML5 + vanilla JS (no build step) · Multiple-page app (`hub`, `index`, `review`, `login`).

**Auth** — JWT via `backend/auth.py`; login.html handles OAuth flow.

---

## 🧭 Typical workflow

1. **Login** — open `login.html`, authenticate with your credentials (or skip for local single-user mode).
2. **Hub** — open `hub.html`, click "New project", give it a name. The folder on disk becomes `<slug>-<session_id>`.
3. **Upload** — drop a folder or paste a GitHub URL. AppNova extracts to `uploads/{slug-sid}/source/`.
4. **Deploy config** — expand "Deployment Details" and fill in `app_canonical_name`, `db_name`, `public_fqdn`, Azure AD fields, Key Vault name, etc. Click Save. The JSON materialises to `source/context/deploy_config.json` for agents.
5. **Analyze** — choose target stack, click "Run All Agents". The SSE stream delivers:
   - Wave 0: discovery (tech inventory + per-agent briefs)
   - Wave 1: 7 analytic agents in parallel (code-analysis, architecture, security, business-rules, integration, data-migration, devops)
   - Wave 2: migration-planner (file_map.json contract)
   - Wave 3: code-generation (writes `converted/`), documentation (writes `converted/docs/`)
   - Wave 4: code-review, testing, ui-ux in parallel
   - Wave 5: deterministic pipeline (parity, round-trip, rag-learn)
6. **Review** — open `review.html` for the side-by-side source↔target diff view. Coverage chip, deploy-audit chip, and context-attestation chip on each agent card tell you at a glance how complete and leak-free the run was.
7. **Chat / Fix** — click the Chat button on any agent card to ask follow-ups, request edits, or enter "Fix code" mode. Fix mode snapshots `converted/` before each edit so you can revert.
8. **Export** — reports auto-export as `.md`, `.docx`, and `.pdf`. Download from the export panel or re-fetch via `/api/export/{sid}/{aid}.*`.
9. **Freeze / Demo** — click "Freeze as demo" to snapshot the run into `demo_sessions/` for zero-token replay.

---

## 🔌 Contributing

1. Fork & branch from `main`.
2. **Add an agent** — extend `AGENT_REGISTRY` in [`backend/config.py`](backend/config.py) with a new `AgentSpec`, then add the system prompt under `AGENT_PROMPTS` in [`backend/agents/prompts.py`](backend/agents/prompts.py). Declare `upstream` deps; supervisor auto-layers it into the right wave.
3. **Add a playbook** — define a `PlaybookDefinition` in [`backend/playbooks/registry.py`](backend/playbooks/registry.py) with `source_signals`, `mapping`, `transformation`, `validation`, `workflow`, and `rag` layers. Add curated examples to `backend/playbooks/examples/<id>.jsonl` and seed with `POST /api/rag/seed`.
4. **Extend the eval harness** — add threshold checks to [`backend/harness/eval.py`](backend/harness/eval.py)'s `_evaluate_thresholds`. The `score-all --exit-on-fail` flag is the CI hook.

See [`changes.md`](changes.md) for the full reverse-chronological change log.

---

## 📄 License

[MIT](LICENSE) © 2026 AppNova contributors.

---

## 🔗 Related docs

- [changes.md](changes.md) — Full reverse-chronological change log
- [AppNova_Architecture.html](AppNova_Architecture.html) — Interactive architecture overview
- [AppNova_Architecture_Diagrams.html](AppNova_Architecture_Diagrams.html) — Mermaid diagram set
- [AppNova_Workflow.html](AppNova_Workflow.html) — End-to-end workflow diagram
- [AppNova_Complete_Architecture.html](AppNova_Complete_Architecture.html) — Deep-dive architecture
- Swagger UI — `http://127.0.0.1:8002/docs` (live API reference)
