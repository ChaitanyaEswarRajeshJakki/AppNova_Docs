# AppNova — AI-Powered Codebase Intelligence Platform

> Turn any codebase into a queryable, explainable, migratable knowledge base.
> Chat with your repo, generate architecture diagrams, produce migration plans,
> convert legacy code to modern stacks file-by-file, and export full analysis
> reports — powered by your **Claude Code Max subscription** (no API keys
> required for the happy path) with a 4-provider LLM cascade as backup.

[![Python](https://img.shields.io/badge/Python-3.11.9-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8.0-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Max%20Subscription-D97706)](https://docs.claude.com/en/docs/claude-code/overview)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0-1C3C3C?logo=langchain)](https://www.langchain.com/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-FF6B6B)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🖼️ Frontend Architecture at a Glance

![AppNova React Frontend — layered architecture infographic](AppNova_Frontend_Architecture.svg)

> Full interactive version: [AppNova_Frontend_Architecture.html](AppNova_Frontend_Architecture.html) · Raw SVG: [AppNova_Frontend_Architecture.svg](AppNova_Frontend_Architecture.svg)

---

## 🆕 What's new in v2 — Claude Code CLI runner (2026-04-21)

AppNova v2 replaces the LangGraph + 4-provider LLM pipeline with a subprocess-based **Claude Code CLI runner** that calls your Max subscription. See [changes.md](changes.md) for the full 9-hotfix changelog.

| | v1 (legacy, still works) | v2 (new default) |
|---|---|---|
| **Auth** | 5 Claude API keys rotated | Claude Code Max subscription (zero API spend) |
| **Per-agent context** | RAG slice from ChromaDB (~8% of codebase) | Full project dir as `cwd`; Read/Glob/Grep on demand |
| **Execution** | Sequential LangGraph nodes | DAG waves — 14 agents parallel in wave 0 |
| **Runtime** | ~30 min sequential | ~8-10 min with wave parallelism |
| **Tool calls** | Not exposed to frontend | Streamed live (stream-json events) |
| **Failure mode** | Pipeline halts on LLM error | Per-agent retries + graceful fallback to v1 chain |
| **Frontend change** | N/A | Single-line URL flip in `api.ts` |

Both paths coexist. `/api/analyze-v2` uses the CLI runner; `/api/analyze` (legacy) is still reachable for rollback. `/api/chat` tries Claude Code first with transparent fallback to the LLM cascade.

---

## ✨ What is AppNova?

**AppNova** is a self-hosted AI development assistant that ingests entire codebases (any size, any language) and delivers:

- 💬 **Conversational code exploration** — ask natural-language questions about any file, function, or architectural decision (`/api/chat` — Claude Code primary)
- 🧠 **14 specialist agents** — architecture, security, testing, business rules, DevOps, data migration, UI/UX, and more (`/api/analyze-v2` — subscription-backed)
- 🗺️ **Auto-generated architecture diagrams** — Mermaid component trees, dependency graphs, call flows
- 🔄 **Per-file code conversion** — convert a legacy codebase to a target stack with 1:1 file mapping, cached, resumable, parallel
- 🛣️ **Migration planning** — phased roadmap with effort estimates, risks, and acceptance criteria
- 📊 **Exportable reports** — `.docx` and `.md` for stakeholders
- ⚡ **Live preview** — run generated projects in a sandboxed dev server from the UI
- 🔌 **4-provider LLM fallback** — Claude API → Gemini → Groq → Ollama, fires only when Claude Code subscription fails
- 🔒 **100% local code** — source never leaves your machine; only prompts go to Claude

---

## 📐 Architecture (v2)

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                   Frontend (React 18 + Vite 8)                          │
│   Sidebar · ReportView · ChatView · DiffView · ConversionPanel          │
└──────────────────────────┬─────────────────────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼─────────────────────────────────────────────────┐
│                   FastAPI backend (backend/main.py)                     │
│                                                                         │
│   /api/analyze-v2 ──▶ agents/session_adapter ─ uploads/{sid}/source/    │
│                  └──▶ agents/runner.run_discovery ──▶ claude -p         │
│                          (Haiku; one pass; writes digest.md + briefs)   │
│                  └──▶ agents/supervisor.run_supervised                  │
│                          │                                              │
│        ┌─── wave 0 (14 agents in parallel) ──────┐                      │
│        │ code-analysis    architecture          │                       │
│        │ business-rules   security              │                       │
│        │ migration-planner documentation        │                       │
│        │ devops  data-migration  integration    │                       │
│        │ testing  ui-ux  refactoring codegen    │                       │
│        └────────────────────────────────────────┘                       │
│                  │                                                      │
│         wave 1 ─▶ code-generation (writes converted/)                   │
│                  │                                                      │
│         wave 2 ─▶ testing  ·  ui-ux                                     │
│                                                                         │
│   /api/chat ─────▶ agents/chat_bridge ──▶ claude -p (Read/Glob/Grep)    │
│                  └─▶ falls back to LangGraph chat_graph on error ────┐  │
│                                                                      ▼  │
│   Legacy (v1, still reachable):                                         │
│   /api/analyze ──▶ LangGraph analysis_graph ─▶ ChromaDB RAG             │
│   /api/chat/stream ─▶ LangGraph chat_graph  ─▶ 4-provider fallback      │
│                                                │                        │
│                                        Claude API → Gemini              │
│                                        → Groq → Ollama                  │
└────────────────────────────────────────────────────────────────────────────┘
         │
         ▼ each `claude -p` subprocess spawned here:
┌────────────────────────────────────────────────────────────────────────────┐
│  Claude Code CLI (npm global; uses Max subscription auth)               │
│  ├─ Read/Glob/Grep on cwd=uploads/{sid}/source/<detected-root>/         │
│  ├─ Stream-json events → asyncio.Queue → SSE to browser                 │
│  └─ Write/Edit only for code-generation (cwd=converted/ + --add-dir     │
│     source/)                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Core components

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React 18, TypeScript 5.9, Vite 8 | IDE-style UI with agent tabs, streaming reports, live diff, Monaco editor |
| API | FastAPI 0.115 + Uvicorn 0.31 | REST + Server-Sent Events |
| **v2 Runner** | **`claude -p` subprocess + threaded pipes** | **DAG wave scheduler against Claude Code Max subscription** |
| **v2 Cost tracking** | **`backend/core/cost_tracker.py` + SQLite + openpyxl** | **Per-call virtual-cost ledger** |
| v1 Orchestration | LangGraph 1.0, LangChain 0.3 | Analysis / chat / diff state graphs (fallback path) |
| Vector store | ChromaDB 1.5 (HNSW) | Semantic code retrieval (v1 only) |
| Embeddings | Jina Embeddings v2 Base Code (via sentence-transformers) | Local, CPU/GPU |
| LLMs | Claude Code subscription primary · Claude API / Gemini 2.5 Flash / Groq Llama 3.3 70B / Ollama fallback | 2-tier primary + 4-tier cascade |
| Docs | python-docx, markdown2 | `.docx` + `.md` export |
| Reports | react-markdown + remark-gfm + react-syntax-highlighter (Prism oneDark) | Rich rendering with copy-buttons and Mermaid |

---

## 🤖 The 14 specialist agents

Each agent is registered in [`backend/agents/config.py`](backend/agents/config.py) and has a system prompt in [`backend/agents/prompts.py`](backend/agents/prompts.py). The supervisor orchestrates them via a DAG scheduler.

| Agent ID | Tier | Wave | Purpose |
|---|---|---|---|
| `code-analysis` | heavy | 0 | Technical debt scoring, anti-patterns, complexity metrics |
| `architecture` | heavy | 0 | Service decomposition, dependency maps, migration phases |
| `business-rules` | heavy | 0 | State machines, validation rules, domain logic extraction |
| `security` | heavy | 0 | OWASP Top 10, secrets scan, vulnerability remediation |
| `migration-planner` | heavy | 0 | Phased roadmap, effort estimates, risk assessment |
| `documentation` | light | 0 | ADRs, developer guides, API docs, architecture decisions |
| `devops` | light | 0 | Docker, CI/CD, IaC (Terraform/CloudFormation) |
| `data-migration` | light | 0 | Schema analysis, ETL scripts, data-driven migration |
| `integration` | light | 0 | OpenAPI specs, event-driven design, service contracts |
| `refactoring` | heavy | 1 | Before/after code patterns, decomposition strategies |
| `code-generation` | heavy | 1 | Full target-stack project generation with Write/Edit |
| `testing` | light | 2 | Unit tests, integration tests, E2E scenarios |
| `ui-ux` | heavy | 2 | Component library, accessibility improvements, design tokens |
| `data-modeling` | light | 0 | Schema optimization, denormalization advice, query tuning |

**Tiers → models** (override with `HEAVY_MODEL` / `LIGHT_MODEL` / `DISCOVERY_MODEL` env vars):

- `heavy` → `claude-sonnet-4-6`
- `light` → `claude-haiku-4-5-20251001`
- discovery pass → `claude-haiku-4-5-20251001`

**Execution model** — the runner streams stream-json tool-call events per agent. The frontend receives them as `agent_start` / `assistant` (with tool_calls) / `tool_result` / `agent_complete`.

---

## 🔄 Per-file conversion pipeline (flagship v1 feature)

Still available via `/api/convert/{session_id}` — converts every source file in the uploaded codebase 1:1 into your target stack, with **full caching, resumability, and parallelism**.

- **Planner** ([`tools/conversion_planner.py`](backend/tools/conversion_planner.py)) groups files by the first two directory segments so a domain module's files convert with mutual context.
- **Runner** ([`tools/conversion_runner.py`](backend/tools/conversion_runner.py)) executes batches with bounded concurrency (1–12 parallel), persists an atomic manifest.
- **Failure isolation** — one failed batch never blocks the rest. Re-running picks up exactly the failed batches.
- **Prompt-version bump** in `conversion_runner.py` invalidates the entire cache automatically.
- **UI** — [`ConversionPanel.tsx`](frontend_react/src/components/ConversionPanel.tsx) gives you Start/Resume, Retry Failed, Force Full Re-run, Stop, plus live progress counters.

The v2 `code-generation` agent is a simpler alternative: one subprocess writes the whole target project in `uploads/{sid}/converted/` using Claude Code's Write/Edit tools directly.

---

## 🌐 Complete API surface

All routes live in [`backend/main.py`](backend/main.py). Every route is tagged for OpenAPI; Swagger UI is served at `http://127.0.0.1:8000/docs`.

### System & models
| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Liveness + provider info |
| GET | `/api/server-instance` | Unique server-instance id (UI reconnect hint) |
| GET | `/api/logs/stream` | SSE log broadcast |
| GET | `/api/models` | All available LLM models across providers |
| GET | `/api/models/freshness` | Check per-provider API availability |
| GET | `/api/agents` | List agent ids loaded from `skills/` |

### Upload & indexing
| Method | Route | Purpose |
|---|---|---|
| POST | `/api/upload` | Multipart upload (folder drag-drop) |
| POST | `/api/upload/github` | Clone and index a GitHub repo |
| GET | `/api/index-status/{session_id}` | Chunk-indexing progress |
| POST | `/api/index-stop/{session_id}` | Cancel indexing |
| POST | `/api/index-resume/{session_id}` | Resume paused indexing |
| GET | `/api/session/{session_id}/file` | Read a single file |
| GET | `/api/session/{session_id}/repo-knowledge` | Static parse summary |

### Analysis & chat
| Method | Route | Purpose |
|---|---|---|
| **POST** | **`/api/analyze-v2`** | **SSE — v2 subscription-backed DAG runner (default in UI)** |
| POST | `/api/analyze` | Legacy — LangGraph + API keys (rollback only) |
| POST | `/api/analyze/stream` | Legacy SSE variant |
| **POST** | **`/api/chat`** | **Claude Code primary; LangGraph fallback** |
| GET | `/api/chat/stream` | Legacy SSE token stream (still on LLM cascade) |
| POST | `/api/chat/agent-stream` | Chat against a specific agent's report |
| POST | `/api/chat/attach` | Attach code snippets to chat |
| POST/GET | `/api/chat/history/{session_id}` | Save / fetch chat history |

### Code generation & conversion
| Method | Route | Purpose |
|---|---|---|
| POST | `/api/code/save` | Save edited generated file |
| GET | `/api/code/files/{session_id}` | List generated files |
| GET | `/api/code/download/{session_id}` | Zip of generated project |
| POST | `/api/convert/{session_id}` | Per-file conversion (SSE) |
| GET | `/api/convert/{session_id}/manifest` | Conversion manifest summary |
| POST | `/api/generated/run/{session_id}` | Execute generated code in sandbox |

### Preview & diff
| Method | Route | Purpose |
|---|---|---|
| POST | `/api/preview/start/{session_id}` | Start self-healing dev-server preview |
| POST | `/api/preview/stop/{session_id}` | Stop preview |
| GET | `/api/preview/status/{session_id}` | Live status + log tail |
| POST | `/api/diff` | Produce side-by-side diff payload |
| GET | `/api/artifact/{session_id}` | Fetch inline UI/UX artifact HTML |
| GET | `/api/artifact/{session_id}/meta` | Artifact metadata |

### Brain, skills, hooks
| Method | Route | Purpose |
|---|---|---|
| GET | `/api/brain/{session_id}` | Fetch `PROJECT.md` brain |
| PUT | `/api/brain/{session_id}/notes` | Save notes |
| POST | `/api/brain/{session_id}/regenerate` | Regenerate summary |
| GET/POST | `/api/skills` | List / upload skill prompts |
| GET | `/api/skills/{agent_id}` | Skill for a specific agent |
| GET | `/api/hooks` | Installed pre/post hooks |

### Export, session, cache
| Method | Route | Purpose |
|---|---|---|
| POST | `/api/export` | Generate `.md` or `.docx` report |
| GET | `/api/export/download/{filename}` | Download exported file |
| POST | `/api/refactor` | Legacy refactor endpoint |
| POST | `/api/execute` | Execute code in sandbox |
| POST | `/api/requirements` | Infer requirements doc |
| GET | `/api/session/{session_id}` | Session metadata |
| GET | `/api/session/{session_id}/files` | Uploaded file list |
| DELETE | `/api/session/{session_id}` | Delete session + data |
| POST | `/api/session/{session_id}/refresh` | Re-index without re-upload |
| GET | `/api/session/{session_id}/state` | Analysis state |
| POST | `/api/session/{session_id}/cancel-agent/{agent_id}` | Stop a running agent |
| GET | `/api/session/{session_id}/events` | Session event log |
| GET | `/api/cache/stats` | Fingerprint-cache hit rates |
| GET | `/api/active-session` | Spectator-mode current session |

---

## 🔁 LLM fallback cascade (backup path)

When the Claude Code subscription is unavailable (CLI missing, rate-limited, or the bridge returns an error), AppNova falls through to the legacy cascade in [`backend/core/llm.py`](backend/core/llm.py).

1. **Claude API** (Tier 2) — up to 5 keys, 300 s max cooldown (Tier-2 resets in 5 min)
2. **Gemini 2.5 Flash** — up to 9 keys, grouped by project
3. **Groq Llama 3.3 70B** — up to 11 keys
4. **Ollama** (local) — qwen-32k / deepseek-coder-v2 / llama3.2 / mistral — final fallback that never rate-limits

**Key rotation rules**

- **429 / rate-limit** → cool this key, rotate to next key on same provider.
- **Daily quota exhausted** → 24 h cooldown (Gemini) / 1 h (Groq).
- **401 / invalid key** → rotate with explicit cooldowns (Claude 300 s, Gemini/Groq 1800 s).
- **All keys cold on this provider** → fall to next provider.
- **All providers cold** → fall to Ollama; if Ollama fails, raise.

**Cancellation** is honored at three safe checkpoints: before an agent starts, between key rotations inside a tier, and between fallback tiers.

**Fingerprint caching** ([`backend/core/fingerprint.py`](backend/core/fingerprint.py)): every analysis result is keyed by `(pipeline_fp, codebase_fp, agent_id)`. `pipeline_fp` is now **per-agent and per-discovery-digest hash**.

---

## 🚀 Quick start

### Requirements

- **Python 3.11.9** (exact version, verified by `start_appnova.bat`)
- **Node.js 18+**
- **Git**
- **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code` (for v2)
- **Claude Code Max subscription** with `claude login` completed (for v2)
- *(Optional)* API keys for Claude / Gemini / Groq, or a running Ollama server — only needed if the v2 subscription path fails.

### Windows — one-command start

```powershell
.\start_appnova.bat
```

The launcher:

1. Verifies Python 3.11.9.
2. Creates `backend/venv` and installs `backend/requirements.txt`.
3. Starts FastAPI on `http://127.0.0.1:8000` **without `--reload`** (uvicorn's reloader forces `WindowsSelectorEventLoopPolicy`, which breaks `asyncio.create_subprocess_exec` — see Hotfix 3)
4. Starts Vite dev server on `http://localhost:5173`.
5. Opens the UI in your browser.

Stop with `.\start_appnova.bat stop` (kills port 8000 listener + Node + Ollama).

### macOS / Linux — manual start

```bash
# Backend — NO --reload when using v2; Proactor/epoll default is correct
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend (in another terminal)
cd frontend_react
npm install
npm run dev
```

### Environment variables

Create a `.env` in the project root (v2 path needs zero API keys; all cascade keys are optional):

```ini
# ── v2 Claude Code CLI runner ──
# CLAUDE_CODE_PATH=claude            # defaults to `claude`; override if not on PATH
# HEAVY_MODEL=claude-sonnet-4-6      # heavy-tier agents (arch/security/code-gen/…)
# LIGHT_MODEL=claude-haiku-4-5-20251001   # light-tier agents (docs/devops/…)
# DISCOVERY_MODEL=claude-haiku-4-5-20251001
# AGENT_TIMEOUT=86400                # 24h default (matches Claude Code session ceiling)
# DISCOVERY_TIMEOUT=86400
# APPNOVA_MIGRATION_PLANNER_REPAIR=0 # set to 1 to re-enable strict-contract repair pass

# ── v1 LLM fallback cascade (only used when v2 path fails) ──
LLM_PROVIDER=auto                    # auto | claude | gemini | groq | ollama

# Claude API keys (up to 5; leave unused slots blank)
CLAUDE_API_KEY=
CLAUDE_API_KEY_2=
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_CACHE_TTL=5m                  # 5m or 1h

# Gemini (up to 9 keys, grouped by project)
GEMINI_API_KEY=
GEMINI_API_KEY_2=

# Groq (up to 11 keys)
GROQ_API_KEY=
GROQ_API_KEY_2=

# Ollama (local fallback, no key needed)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen-32k
OLLAMA_USE_GPU=true

# Embeddings (v1 only)
EMBEDDING_MODEL_PATH=./models/jina-embeddings-v2-base-code
FORCE_CPU_EMBEDDINGS=false
```

---

## 🧭 Typical workflow

1. **Upload** — drop a folder into the UI, or paste a GitHub URL. AppNova extracts to `uploads/{sid}/files/`.
2. **Analyze** — pick one or more agents from the sidebar. The UI posts to `/api/analyze-v2`. Behind the scenes:
   a. Session adapter mirrors `files/` → `source/` and detects the project root (`package.json`, `pom.xml`, `.csproj`, etc.).
   b. One discovery `claude -p` call (Haiku) writes `context/digest.md` + `context/brief_<agent>.md`.
   c. Supervisor dispatches wave 0 — up to 14 agents run `claude -p` subprocesses in parallel. Each has Read/Glob/Grep on the source dir.
   d. Wave 1 dispatches `code-generation` + `refactoring`; wave 2 dispatches `testing` + `ui-ux` in parallel.
3. **Chat** — ask follow-ups. The chat bridge tries Claude Code first; on failure falls through to the LangGraph chat graph.
4. **Generate or convert** — v2 `code-generation` writes a full target-stack project under `uploads/{sid}/converted/`. Or use the legacy **Convert** tab for per-file 1:1 batched conversion.
5. **Preview** — one-click self-healing dev-server launcher runs the generated project in-browser.
6. **Export** — one click produces a `.docx` or `.md` report combining every agent's output.

---

## 📂 Repository layout

```text
AppNova/
├── backend/
│   ├── main.py                      ← FastAPI entry; all routes (incl. /api/analyze-v2)
│   ├── config.py                    ← Pydantic settings (v1 env vars)
│   ├── requirements.txt             ← Backend deps
│   ├── agents/                      ← v2 runner package (NEW)
│   │   ├── config.py                ← 14-agent registry + tier→model map
│   │   ├── runner.py                ← `claude -p` subprocess + threaded pipes
│   │   ├── supervisor.py            ← DAG wave scheduler + per-cwd lock
│   │   ├── state.py                 ← RunState TypedDict blackboard
│   │   ├── director.py              ← Alt: Claude-driven Task-tool dispatch
│   │   ├── orchestrator.py          ← Alt: single-session orchestrator
│   │   ├── prompts.py               ← DISCOVERY_PROMPT + AGENT_PROMPTS
│   │   ├── session_adapter.py       ← files/ → source/ + root detection
│   │   ├── v2_to_report_data.py     ← Runner results → document_generator
│   │   ├── chat_bridge.py           ← /api/chat → claude -p (Read/Glob/Grep)
│   │   ├── artifact.py / scaffold.py / sample_data.py / diagram_qa.py / export.py
│   ├── core/
│   │   ├── llm.py                   ← v1 4-provider fallback + key rotation
│   │   ├── cost_tracker.py          ← Per-agent virtual-cost ledger (NEW)
│   │   ├── model_pricing.yaml       ← Claude model prices for ledger (NEW)
│   │   ├── tracing.py               ← Structured span logger → SQLite (NEW)
│   │   ├── fingerprint.py           ← Pipeline × codebase cache keys
│   │   ├── chromadb_client.py       ← Vector store wrapper (v1 only)
│   │   ├── prompts.py               ← v1 prompt templates
│   │   ├── skill_loader.py          ← Hot-loads skills/*.md
│   │   └── logger.py                ← Loguru + SSE broadcaster
│   ├── mcp_server/                  ← MCP stdio server exposing traces (NEW)
│   │   └── trace_server.py          ← `claude mcp add appnova-traces`
│   ├── graphs/                      ← v1 LangGraph pipelines (fallback only)
│   │   ├── analysis_graph.py
│   │   ├── chat_graph.py
│   │   └── diff_graph.py
│   ├── skills/                      ← 14 agent Markdown prompts (v1; v2 uses agents/prompts.py)
│   ├── tools/                       ← Upload, code-exec, document-gen, conversion
│   ├── api/                         ← Pydantic schemas & sub-routers
│   ├── hooks/                       ← Pre/post processing hooks
│   ├── data/                        ← (gitignored) cost_tracking.db
│   └── chroma_data/                 ← (gitignored) vector store
├── frontend_react/
│   ├── src/
│   │   ├── App.tsx                  ← Root layout, tab bar
│   │   ├── main.tsx                 ← React entry
│   │   ├── services/api.ts          ← HTTP + SSE clients (now /api/analyze-v2)
│   │   ├── contexts/AppContext.tsx  ← Global session state
│   │   └── components/              ← Sidebar, ReportView, ChatView, …
│   ├── package.json
│   └── vite.config.ts
├── .claude/                         ← Project-scoped Claude Code config (NEW)
│   ├── settings.json                ← Permission allowlist + PostToolUse hooks
│   ├── hooks/remind.sh              ← Nudge to keep changes.md current
│   └── skills/log-change/           ← Project skill: prepend-to-changes
├── AGENTS.md                        ← Human-readable agent contract (NEW)
├── uploads/                         ← (gitignored) per-session files
├── logs/                            ← (gitignored) Loguru output + agent dumps
├── exports/                         ← (gitignored) generated .docx/.md reports
├── start_appnova.bat                ← Windows launcher (no --reload; Hotfix 3)
├── changes.md                       ← Current changelog (2026-04-21 = v2 port)
├── changes_2026-04-14.md            ← Prior changelog (archive)
└── LICENSE                          ← MIT
```

---

## 🧪 Tech stack

**v2 runner** — Python `subprocess.Popen` + threaded pipes · `@anthropic-ai/claude-code` (npm global) · `shutil.which` shim resolution · `asyncio.Queue` via `loop.call_soon_threadsafe` · ChromaDB adapter for concurrent sessions.

**Backend** — FastAPI 0.115 · Uvicorn 0.31 · LangChain 0.3 · LangGraph 1.0 · ChromaDB 1.5 · sentence-transformers 2.7 · python-docx 1.1 · markdown2 · loguru · python-multipart · Pygments.

**Frontend** — React 18.3 · TypeScript 5.9 · Vite 8.0 · Tailwind 4.2 · Monaco Editor 4.7 · Mermaid 11.14 · react-markdown 9.0 · remark-gfm 4.0 · react-syntax-highlighter 15.5 · axios 1.x.

**LLM SDKs** — `@anthropic-ai/claude-code` CLI (primary) · langchain-anthropic · langchain-google-genai · langchain-groq · langchain-ollama · langchain-openai (extensibility).

---

## 🔌 MCP integration (bonus)

[`backend/mcp_server/trace_server.py`](backend/mcp_server/trace_server.py) is a local stdio MCP server exposing AppNova's trace SQLite read-only. Register it once and Claude Code CLI sessions can query cost, errors, and performance metrics.

```powershell
pip install mcp
claude mcp add appnova-traces -- python -m mcp_server.trace_server
```

Exposed tools: `list_sessions`, `get_session`, `get_node_runs`, `get_errors`, `get_token_usage`.

---

## 🧑‍💻 Contributing

1. Fork & branch from `main`.
2. **Add an agent** — extend `AGENT_REGISTRY` in [`backend/agents/config.py`](backend/agents/config.py) with a new `AgentSpec`, then add the system prompt in [`backend/agents/prompts.py`](backend/agents/prompts.py).
3. **Add a skill (v1 parallel)** — drop a Markdown file into `backend/skills/{agent-id}.md`; it's loaded on next request and bumps its own fingerprint.
4. **Add a provider** — extend `backend/core/llm.py` `call_llm_with_fallback` (mirror the Claude/Gemini/Groq patterns for key-rotation + cooldown). The v2 path skips this chain entirely.
5. Run the linters/tests you have locally, then open a PR.

See recent architectural work in [`changes.md`](changes.md) (2026-04-21 section for the v2 port + 9 hotfixes) and the prior long-form changelog in [`changes_2026-04-14.md`](changes_2026-04-14.md).

---

## 📄 License

[MIT](LICENSE) © 2026 AppNova contributors.

---

## 🔗 Related docs

- [changes.md](changes.md) — v2 port (2026-04-21) + 9 hotfixes, reverse-chronological decision log
- [AGENTS.md](AGENTS.md) — human-readable agent contract
- [AppNova_Architecture.html](AppNova_Architecture.html) — interactive architecture overview
- [AppNova_Architecture_Diagrams.html](AppNova_Architecture_Diagrams.html) — full mermaid diagram set
- [AppNova_Workflow.html](AppNova_Workflow.html) — end-to-end workflow diagram
- [APPNOVA_PIPELINE_AND_LLM_FALLBACK.md](APPNOVA_PIPELINE_AND_LLM_FALLBACK.md) — deep-dive on the fallback state machine
- [APPNOVA_VS_CLAUDE_CODE_ROADMAP.md](APPNOVA_VS_CLAUDE_CODE_ROADMAP.md) — feature-parity roadmap
- [IMPLEMENTATION_PLAN_CODE_RENDER.md](IMPLEMENTATION_PLAN_CODE_RENDER.md) — code-rendering/preview plan
- Swagger UI — `http://127.0.0.1:8000/docs` (live API reference)
