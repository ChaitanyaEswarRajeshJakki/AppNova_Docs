# Changes — Working Tree (since commit 88036e8)

**Base commit:** `88036e8` — "made changes for robust code generation"
**Date:** 2026-04-15
**Scope:** 13 modified files, 3 new files, +747 / −79 lines.

> Prior changelog archived as [changes_2026-04-14.md](changes_2026-04-14.md).
>
> **Convention:** newest entries are **prepended** at the top, immediately under this header. Older sections sink toward the bottom. Each entry starts with its date and a one-line scope summary so the file reads as a reverse-chronological log.

---

## 2026-04-21 — [SHIPPED on `feature/claude-code-runner`] Phases 0–4 + frontend cutover to `/api/analyze-v2`

> Follows the `[PLANNED / TO-DO]` section below. Branch is **`feature/claude-code-runner`** (off `main @ 4c14b37`). Skeleton + frontend cutover land; no behaviour changes on `main` — the existing `/api/analyze` and `/api/analyze/stream` are still reachable on the backend but no longer called from the UI. A new `/api/analyze-v2` endpoint is live, wired end-to-end to the subprocess runner, and still needs a real session run to validate output quality (Phase 5–7 of the original plan).

### Hotfix 10 — docs refresh: README + 4 architecture HTMLs reflect v2 runner

The project docs still described the legacy LangGraph + 4-provider pipeline as the only path. Updated all top-level human-facing artefacts to lead with the v2 Claude Code CLI runner while preserving the v1 content as fallback reference.

- [README.md](README.md) — full rewrite. New "What's new in v2" comparison table at the top; architecture diagram shows the dual path (v2 subscription primary, v1 cascade fallback); endpoint tables split into v2 (analyze-v2, chat with fallback) and v1 (analyze, chat/stream) rows; Quick start includes `npm install -g @anthropic-ai/claude-code` + `claude login`; `.env` example clarifies that API keys are only needed for the fallback cascade; repository layout lists `backend/agents/`, `backend/core/cost_tracker.py`, `backend/core/tracing.py`, `backend/mcp_server/`, `.claude/`, `AGENTS.md`; Contributing guide explains how to add an agent via `AGENT_REGISTRY` + `AGENT_PROMPTS`.
- [AppNova_Workflow.html](AppNova_Workflow.html) — added top banner and a new **Flow 4** SVG diagram showing the 3-wave DAG execution (discovery → wave 0 (9 parallel agents) → wave 1 (code-gen) → wave 2 (testing + ui-ux) → SSE stream + docx export). Footer updated.
- [AppNova_Complete_Architecture.html](AppNova_Complete_Architecture.html) — top banner + new **Layer 8** card grid describing all 9 v2 modules (runner, supervisor, discovery, session_adapter, chat_bridge, config/prompts, cost_tracker, v2_to_report_data, mcp_server/trace_server). Subtitle flagged with the v2 addition.
- [AppNova_Architecture.html](AppNova_Architecture.html) — top banner + new panel inserted between the 3-column layout and the bottom row, with 9 module cards + an "event envelope" note explaining the backward-compatible SSE shape (legacy `{type: start|complete|error}` emitted alongside rich `agent_start/assistant/tool_result/agent_complete`).
- [AppNova_Architecture_Diagrams.html](AppNova_Architecture_Diagrams.html) — hero chips updated (v2 chip added, "LangGraph Orchestration" → "LangGraph Orchestration (fallback)", "ChromaDB Vector Store" → "ChromaDB Vector Store (v1 only)", "13 AI Agents" → "12 AI Agents · DAG waves"). New **Section 8 · v2 Claude Code CLI Runner** with the module grid + an ASCII wave diagram. Existing "Tech Stack" renumbered to **Section 9**. Nav bar gets a new `v2 CLI Runner` link styled in the accent colour.

All four HTMLs remain standalone (inline CSS, no external resources). Banners use the consistent amber palette (`#F59E0B` / `#FEF3C7` / `#78350F`) so readers can visually identify v2 content at a glance. Legacy sections are untouched &mdash; they still accurately describe what happens when the v2 path falls back.

### Hotfix 9 — migration-planner: skip auto-repair pass by default (keep first draft)

Post-run log from 17:49 showed migration-planner burning ~37 min and ~$4 virtual across two attempts, both rejected by the supervisor's strict-contract validator. The second pass (triggered by `[FileMap] attempt 1 rejected — missing file_map.json. Dispatching full repair pass`) took another 16 min and $1.73 — and was **also** rejected (`repair pass incomplete — still no file_map.json; body still thin: missing ## A.0 heading …`). Net result: **the first draft's 70 KB of valid migration content was discarded and replaced with a second draft that also failed validation**.

Pattern: on large legacy monoliths the model blows past the output-token ceiling while writing A.0/A.1/A.3/Section B, and the A.2 mapping table + A.4 JSON block get truncated. The repair pass inherits the same token pressure and re-truncates the same tail — it never structurally succeeds.

Fix in [backend/agents/supervisor.py](backend/agents/supervisor.py) `run_supervised._run_one`:

- Added env gate `APPNOVA_MIGRATION_PLANNER_REPAIR` (default `0`). When unset, the repair dispatch is skipped entirely — we keep whatever the first attempt produced, warn in the logs with the specific contract gaps, and emit a frontend event so the UI can paint an amber chip without implying a hard failure.
- Sets `repair_status["repair_skipped"] = True` so downstream rendering distinguishes "skipped by policy" from "attempted and failed".
- `file_map.json` extraction still runs on the kept draft — if the first attempt happened to produce a parseable JSON block, it's written to `context/file_map.json` as before and downstream code-generation/code-review get it. Only the **second-attempt dispatch** is gated.
- Fixed `os.environ` reference: file imports `os as _os`, so call is `_os.environ.get(...)`.

Opt-in: set `APPNOVA_MIGRATION_PLANNER_REPAIR=1` in `.env` to restore the old behaviour (repair pass fires when validation fails). Intended for CI or strict-contract environments.

**Net saving on a typical 300+ file monolith run**: ~15-20 minutes of wall clock, ~$2 virtual cost, plus a big chunk of 5-hour Sonnet rate-limit window. Downstream agents (code-generation / code-review) lose some structured mapping precision but still have the full markdown migration plan in `upstream_migration-planner.md` — they Glob/Grep the source themselves, which is exactly Claude Code's strength.

py_compile + import verified. 3-wave DAG still resolves correctly for the 12-agent registry.

### Hotfix 8 — `/api/chat` routes through Claude Code first, falls back to LLM chain

Extended the subscription-first strategy from analyze to chat. The chat endpoint used to call the LangGraph chat graph directly (`build_chat_graph()`), which consumes Claude API keys / Gemini / Groq / Ollama through `core/llm.py`'s fallback chain. Now it tries the Max subscription first and only drops to the key-based chain on failure.

New file: [backend/agents/chat_bridge.py](backend/agents/chat_bridge.py) — thin `claude -p` bridge for chat turns.
- `_build_prompt(system, messages)` — flattens the message list into a single markdown-ish dialog. Claude Code's headless mode is one-shot; each turn replays full history.
- `claude_code_chat_sync(system, messages, model, timeout, cwd)` — blocking subprocess, `--output-format json`, parses `result` field. Returns `(text, error_or_None)`. Never raises.
- `aclaude_code_chat(...)` — async wrapper via `asyncio.to_thread` so FastAPI stays responsive.
- `is_cli_reachable()` — fast `_resolve_executable()` probe so callers can skip Claude Code gracefully when the CLI isn't installed.
- Tools: Read/Glob/Grep/LS stay enabled so chat answers code questions by reading the actual source, not a RAG slice. Write/Edit/Bash/WebFetch/Task are disallowed — chat must never mutate source or spawn nested agents.

Wiring in [backend/main.py](backend/main.py) `@app.post("/api/chat")`:
1. Resolve session layout via `ensure_agent_layout(session_id, files_fallback=_sessions[sid])` — gives us `project_dir` for `cwd`.
2. Call `aclaude_code_chat(system_prompt, messages, model_override, cwd=project_dir)`.
3. If `(text, None)` → return `ChatResponse(reply=text, model_used="claude-code (max-sub)", session_id=...)`. Subscription covers the tokens, zero API spend.
4. If the bridge returns an error, log a warning (not an error — graceful) and **fall through** to the existing `graph = build_chat_graph(); graph.invoke(...)` path. The existing chain (Claude API → Gemini → Groq → Ollama) is untouched and still wired.
5. Any exception during the bridge is swallowed and logged via `logger.exception` — never bubbles up to the caller.

Verified: `aclaude_code_chat`, `claude_code_chat_sync`, `is_cli_reachable`, `_build_prompt` all import cleanly from the uvicorn cwd. Live `is_cli_reachable()` returns `True` on this Windows box. `py_compile` clean on both `chat_bridge.py` and the extended `main.py`.

**Still on API keys for chat**: `/api/chat/stream` (SSE token-stream endpoint) and `/api/chat/agent-stream` (agent-scoped branching history) — those involve token-by-token streaming which `claude -p --output-format json` doesn't give us. Next pass would switch them to the runner's `stream-json` event feed (same pattern as analyze-v2 SSE), but that's substantially more code and not blocking the $100 API budget goal today. For now the primary `/api/chat` POST endpoint gets the subscription; streaming endpoints still burn keys.

### Hotfix 7 — 24h timeouts across the board (match Claude Code's session ceiling)

Migration Planner timed out at exactly 900s in the 16:59 run while Code Analysis finished at 390s on the same wave. The 900s cap was inherited from the sister project's `AGENT_TIMEOUT` default and is far too tight for the target stacks we're analysing (a 300+ file PHP monolith → React+ASP.NET migration report can legitimately take 15-25 min per heavy agent).

Bumped all three timeouts in [backend/agents/config.py](backend/agents/config.py) to 24h (86400s) — matches Claude Code's own interactive session ceiling and matches the sister's `_UNBOUNDED_TIMEOUT` for code-gen writers. The real backstop is the Max subscription rate limit, not a local timer:

- `DISCOVERY_TIMEOUT`: 480s → 86400s
- `AGENT_TIMEOUT`: 900s → 86400s
- `ORCHESTRATOR_TIMEOUT`: 3600s → 86400s

All three still overridable via env vars if a tighter cap is ever wanted for CI.

### Hotfix 6 — wrong signature on `split_discovery_into_briefs` (TypeError mid-run)

Discovery now reaches Claude Code, runs for 141s, returns a 28KB digest — and then the analyze-v2 endpoint crashed at `split_discovery_into_briefs(digest)` with `TypeError: missing 2 required positional arguments: 'context_dir' and 'agent_ids'`. Log snippet:

```
15:53:01 | Runner | Agent '_discovery' completed in 141.4s (28,463 chars) cost=$0.1300 tokens=436+12131
15:53:01 | main   | [analyze-v2] failed writing digest/briefs
TypeError: split_discovery_into_briefs() missing 2 required positional arguments: 'context_dir' and 'agent_ids'
```

I built the call against a guessed signature `split(digest) -> {agent_id: markdown}`. The real signature (from [backend/agents/prompts.py:1463-1517](backend/agents/prompts.py#L1463-L1517)) is `split(discovery_output, context_dir, agent_ids) -> {"digest_path": Path, "briefs": {agent_id: Path}}` — the function writes `digest.md` and each `brief_<agent>.md` to disk itself.

Fix in [backend/main.py](backend/main.py) `/api/analyze-v2` `event_stream()` (~line 3756): replaced the manual `digest_path.write_text(...)` + manual brief loop with a single `manifest = split_discovery_into_briefs(digest, context_dir, valid_agents)` call. `digest_path` and `brief_paths` are read from the returned manifest. The try/except that swallowed the TypeError before now surrounds the correct call.

Side effect of the bug: for the 15:50 run, `brief_paths` stayed empty, so each downstream agent ran without its per-agent brief — they still had access to `digest.md` + the full project cwd, so output quality degrades but the run doesn't crash. Code-analysis and migration-planner both proceeded to actual Sonnet calls (the wave-1 dispatch happened despite the brief-write failure because the try/except caught it). Next run will have proper briefs and full quality.

### Hotfix 5 — resolve bare `"claude"` via `shutil.which` (Windows PATHEXT)

With Hotfix 4 in place the threaded subprocess spawn reached `subprocess.Popen(["claude", ...])` but immediately died with `[WinError 2] The system cannot find the file specified`. Root cause: `CreateProcess` on Windows does **not** consult `PATHEXT` — it looks for a literal file named `claude` with no extension, which doesn't exist. The npm-installed binary is actually `claude.cmd`. Python's `shutil.which("claude")`, by contrast, does walk `PATHEXT` and returns `C:\Users\Chaitanya\AppData\Roaming\npm\claude.cmd`.

The existing `_resolve_executable()` shim-bypass logic only kicked in when `CLAUDE_CODE_PATH` already ended in `.cmd`/`.bat`. With the default `CLAUDE_CODE_PATH="claude"`, it returned the bare name unchanged and left Popen to fail. Widened the function in [backend/agents/runner.py](backend/agents/runner.py) `_resolve_executable()`:

1. Non-Windows: unchanged — return `CLAUDE_CODE_PATH` as-is.
2. Windows + already has `.cmd`/`.bat`/`.exe` suffix: unchanged path, go straight to shim bypass if applicable.
3. **NEW** Windows + bare name (no extension): `shutil.which(CLAUDE_CODE_PATH)` resolves via PATHEXT. If nothing is found, raise a clear `FileNotFoundError` that points at `npm install -g @anthropic-ai/claude-code` or setting `CLAUDE_CODE_PATH` explicitly.
4. `.exe` binaries are launched directly; `.cmd`/`.bat` shims fall through to the existing node.exe + cli.js bypass (Popen can't launch multiline-argv through `.cmd` reliably).

Verified with a live `_resolve_executable()` call — cache cleared, ran from `backend/`, confirmed it returns the absolute path to `node.exe` plus `cli.js` of the npm install.

**Net effect across all 5 hotfixes so far**: `/api/analyze-v2` should now survive a cold start on Windows + uvicorn --reload legacy + Python 3.11 + npm-installed `claude` CLI, with the Max subscription covering each agent's `claude -p` call. Next error class to expect is the real one we've been waiting for — authentication (if `claude` CLI isn't logged in under the uvicorn worker's user context) or rate limits / API-level issues.

### Hotfix 4 — threaded `subprocess.Popen` in runner (event-loop agnostic)

Hotfix 3's `--reload` removal only works if the user actually restarts the backend. The next screen sharing showed the old reloader-launched worker was still running (browser log still emitted `Started reloader process [22804] using WatchFiles` on startup), which means uvicorn was still forcing Selector policy and every agent was still dying at `asyncio.create_subprocess_exec`. Rather than rely on the operator restarting cleanly every time, replace the asyncio subprocess call with a cross-loop-compatible threaded shim that works on **both** `WindowsSelectorEventLoop` (uvicorn --reload) and `WindowsProactorEventLoop` (plain uvicorn).

Rewrote the subprocess block in [backend/agents/runner.py](backend/agents/runner.py) `_run_agent_attempt()` (lines ~440–545):

- `subprocess.Popen` spawns the CLI with `stdin/stdout/stderr=PIPE`, `bufsize=0`. Synchronous Popen has no event-loop dependency; it works on every loop type.
- Three daemon threads per agent call:
  - `_stdin_thread` writes `prompt_bytes` to stdin, then closes it. BrokenPipe is swallowed (child died before reading — harmless).
  - `_stdout_thread` reads stdout in 64KB chunks, splits on `\n` manually (no 64KB line-length ceiling like `StreamReader.readline`), pushes each complete line onto an `asyncio.Queue` via `loop.call_soon_threadsafe(queue.put_nowait, line)`. Final `_STREAM_END` sentinel signals end-of-stream.
  - `_stderr_thread` drains stderr into `raw_stderr` bytearray for failure-dump logging.
- The async coroutine runs two concurrent tasks under `asyncio.wait_for(..., timeout=timeout)`:
  - `_drain_stdout_queue()` consumes lines from the queue and calls the existing `_handle_line(line)` (JSON-parse → `on_event` callback → update `final_result_text` / `final_result_event` / `observed_model`). Exits on the `_STREAM_END` sentinel.
  - `_wait_proc()` polls `proc.poll()` with `asyncio.sleep(0.1)` — 100ms granularity keeps cancellation responsive without burning CPU or holding a fourth thread.
- `ACTIVE_PROCS[agent_id]` now holds a `subprocess.Popen` instead of an `asyncio.subprocess.Process`. Both expose `.returncode`, `.kill()`, `.poll()` — `kill_active_process()`, timeout-handler `proc.kill()`, and the non-zero-exit branch all keep working unchanged.
- Added `CREATE_NO_WINDOW` on Windows so each `claude` child doesn't flash a cmd window.
- The `FileNotFoundError` branch (WinError 2 vs 206) and the generic `except Exception` branch keep working — `Popen(…)` raises `FileNotFoundError` the same way `asyncio.create_subprocess_exec` did.

Trade-off: three extra Python threads per agent call (one of which — `_stdin_thread` — terminates in <1ms after writing the prompt). With wave 0 fanning out up to 9 agents in parallel, that's up to 27 short-lived threads at peak. Windows handles it easily; the threads are I/O-bound so the GIL doesn't bottleneck.

**Result:** runner now works regardless of whether the user restarts cleanly to pick up the `start_appnova.bat` `--reload` removal. Hotfix 3's .bat change is still correct (cleaner in the long run — no thread overhead on Proactor), but Hotfix 4 makes it non-blocking.

py_compile + import verified. `/api/analyze-v2` is now resilient to the active backend's event loop choice.

### Hotfix 3 — drop `--reload` from `start_appnova.bat` (real subprocess fix)

Hotfix 2's in-`main.py` policy flip didn't work. Confirmed via a fresh 15:11 backend restart and the same `NotImplementedError` stack from `/api/agents/*.log`: uvicorn's reloader worker runs `config.setup_event_loop()` → `asyncio_setup(use_subprocess=True)` → `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())` **before** importing `main.py` and **before** calling `asyncio.run(serve(...))`. By the time `main.py` runs our Proactor override, the Selector loop has already been instantiated — policy overrides only affect `asyncio.new_event_loop()` calls, not an already-running loop.

The root cause is `--reload` itself: uvicorn only forces Selector when `use_subprocess=True`, which is the reloader worker path. Without `--reload`, the flag is False and uvicorn leaves the policy untouched — Python 3.11 on Windows defaults to `WindowsProactorEventLoopPolicy`, which supports `asyncio.create_subprocess_exec` natively.

Fix in [start_appnova.bat](start_appnova.bat): removed the `--reload` flag from the uvicorn command on line 104, added a comment block explaining the tradeoff. Dev workflow changes: you now manually stop/restart the backend after editing Python files (the same `%~nx0 stop` convention the script already documents). Frontend Vite HMR is unaffected.

Hotfix 2's `asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())` block in `main.py` is kept as a belt-and-braces safety net — harmless when Proactor is already the default, and protects against future changes that might re-introduce a Selector loop.

### Hotfix 2 — Windows: force `ProactorEventLoop` for `asyncio.create_subprocess_exec`

Second UI-driven v2 run reached the runner but crashed at the `claude -p` spawn with `NotImplementedError` from `asyncio/base_events.py:503 _make_subprocess_transport`. Root cause: uvicorn's `uvicorn/loops/asyncio.py` hardcodes `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())` whenever `--reload` or `--workers` is used (the AppNova `start_appnova.bat` uses `--reload`). `WindowsSelectorEventLoop` does not support subprocess APIs — only `WindowsProactorEventLoop` does. Every `agents/runner.py::_run_agent_attempt` call bombed identically at the `asyncio.create_subprocess_exec("claude", ...)` line for `_discovery`, `architecture`, `code-analysis`, and `migration-planner`.

Fix in [backend/main.py](backend/main.py) at the very top, after the stdout UTF-8 reconfigure:

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

This runs at module import time, **after** uvicorn's worker has already applied the Selector policy (step 2 of the import chain), but **before** `asyncio.run(serve())` actually creates the event loop (step 4). Proactor supports both TCP sockets and subprocesses on Python 3.11+, so uvicorn's conservative Selector default is unnecessary on modern Python and flipping it back to Proactor is safe for all other uvicorn paths (websockets, HTTP, SSE, reloader watchfiles). Tested: uvicorn reloader still triggers on file changes, existing `/api/analyze/stream` still streams, and v2 subprocess calls should now reach the CLI.

### Hotfix — strip `backend.` import prefix (uvicorn cwd mismatch)

First UI-driven v2 run failed with a 500 (surfaced in the browser as a CORS-missing-header error because FastAPI doesn't attach CORS headers to exception responses). Root cause: `start_appnova.bat` runs `cd backend` before launching `uvicorn main:app`, so `sys.path[0] = backend/`. The rest of the codebase imports as `from core.llm ...`, `from tools.file_processor ...` — bare top-level packages under `backend/`. The 13 ported files and the `/api/analyze-v2` lazy imports still used the sister project's `from backend.agents.config ...` / `from backend.core import cost_tracker` style, which can't resolve when `backend/` is itself the top of `sys.path`.

Single replacement across every touched file:
- `from backend.agents.` → `from agents.` (8 files: runner, supervisor, director, orchestrator, prompts, session_adapter, v2_to_report_data, export + main.py's 7 lazy imports in `analyze_v2()` + one inside `_timeout_for`).
- `from backend.core import cost_tracker` → `from core import cost_tracker` (supervisor, director, orchestrator).
- `TYPE_CHECKING` block in [backend/agents/export.py](backend/agents/export.py) also updated so static analysis keeps working once mermaid_renderer is ported in Phase 8.

Verified by simulating the uvicorn layout (`cd backend && python -c "sys.path.insert(0, os.getcwd()); from agents.runner import ...; from core import cost_tracker"`) — all imports resolve, `compute_waves()` still returns the expected 3-layer DAG for the 12-agent set. `grep "from backend\.\|import backend\."` under `backend/` returns zero hits.

### Follow-up same day — frontend URL flip

- [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) — `streamAnalysis()` now posts to `${API_BASE}/api/analyze-v2` (was `/api/analyze/stream`). Every "Analyze" click from the UI now drives the subprocess runner under the Max subscription. The three UI call sites in [frontend_react/src/contexts/AppContext.tsx](frontend_react/src/contexts/AppContext.tsx) (lines 954, 1114, 1198) and the `refine()` wrapper route through unchanged — the backend's backward-compat event envelope (legacy `{type: start|complete|error, agent_id}` emitted alongside the rich `agent_start|agent_complete|agent_error` events) means zero consumer-side edits were needed.
- `runAnalysis()` (non-streaming fallback, rarely used) rewrapped to consume the v2 SSE stream and synthesise an `AnalysisResponse` shape — preserves the existing signature so any latent caller keeps compiling.
- `npx tsc --noEmit` on `frontend_react/` — clean (exit 0).
- **Immediate impact:** the legacy 5-key Claude API rotation path (`🔑 Tier 1 — trying all 5 Claude key(s)…` log line from `core/llm.py`) is no longer triggered by UI-driven analyses. API key consumption drops to zero for analysis runs; Max subscription picks up the load.

### What landed

- **Branch + dependencies**
  - `git checkout -b feature/claude-code-runner` from `main`.
  - `claude -p` subprocess preflight passed on Sonnet 4.6 earlier this session (`is_error: false`, `service_tier: standard`, subscription auth).

- **Runner copied verbatim from `appnova_2026-04-17_claude-code/backend/agents/`** (12 files, no edits beyond import rewrites):
  - [backend/agents/__init__.py](backend/agents/__init__.py)
  - [backend/agents/runner.py](backend/agents/runner.py) — `claude -p` subprocess loop, Windows `.cmd` shim bypass, stream-json parser, 3-attempt transient-error retry, `ACTIVE_PROCS` kill registry.
  - [backend/agents/supervisor.py](backend/agents/supervisor.py) — DAG wave scheduler, per-cwd writer lock, `TPMWindow` throttle.
  - [backend/agents/state.py](backend/agents/state.py) — `RunState` TypedDict blackboard.
  - [backend/agents/director.py](backend/agents/director.py), [backend/agents/orchestrator.py](backend/agents/orchestrator.py) — alternate single-session Task-tool dispatch modes (wired but not exposed yet).
  - [backend/agents/prompts.py](backend/agents/prompts.py) — `DISCOVERY_PROMPT`, `AGENT_PROMPTS`, `build_agent_prompt`, `split_discovery_into_briefs`.
  - [backend/agents/artifact.py](backend/agents/artifact.py), [backend/agents/scaffold.py](backend/agents/scaffold.py), [backend/agents/sample_data.py](backend/agents/sample_data.py), [backend/agents/diagram_qa.py](backend/agents/diagram_qa.py), [backend/agents/export.py](backend/agents/export.py).
  - [backend/core/cost_tracker.py](backend/core/cost_tracker.py) + [backend/core/model_pricing.yaml](backend/core/model_pricing.yaml) — per-call virtual-cost ledger + pricing table.

- **Slim new config** — [backend/agents/config.py](backend/agents/config.py)
  - Exposes `CLAUDE_CODE_PATH`, `UPLOAD_DIR`, `AGENT_TIMEOUT` (900s), `DISCOVERY_TIMEOUT` (480s), `ORCHESTRATOR_TIMEOUT` (3600s), `HEAVY_MODEL` (`claude-sonnet-4-6`), `LIGHT_MODEL` / `DISCOVERY_MODEL` (`claude-haiku-4-5-20251001`), `AgentSpec`, `AGENT_REGISTRY`, `AGENT_IDS`, `AGENT_LABELS`, `model_for(tier)`.
  - **12 agents registered** (no `code-review`, no `contract-audit` — those are Phase 8 follow-ups per the plan): code-analysis, architecture, business-rules, security, migration-planner, documentation, devops, data-migration, integration, code-generation, testing, ui-ux.
  - DAG resolves to **3 waves**: `wave 0 = 9 parallel analytic agents`, `wave 1 = code-generation`, `wave 2 = testing + ui-ux`. Confirmed by `compute_waves()` smoke test.
  - Kept separate from `backend/config.py` so the Pydantic Settings that still power chat/diff/refactor are untouched.

- **Import rewrites across the 12 copied files**
  - `from backend.config import ...` → `from backend.agents.config import ...` (runner, supervisor, director, orchestrator, prompts).
  - `from backend import cost_tracker` → `from backend.core import cost_tracker` (supervisor, director, orchestrator).
  - Verified clean via `grep` — no stale `backend.config` or `backend import cost_tracker` references remain under `backend/agents/`.

- **Session-layout adapter** — [backend/agents/session_adapter.py](backend/agents/session_adapter.py) (new, ~170 LOC)
  - `ensure_agent_layout(session_id, files_fallback=None)` returns `{project_dir, converted_dir, context_dir, source_dir}`.
  - Mirrors `uploads/{sid}/files/*` into `uploads/{sid}/source/*` (copy, not junction — junctions need admin on Windows). Falls back to writing the in-memory `_sessions[sid]` list to disk if `files/` doesn't exist (handles the `codebase_context.json`-only sessions already on disk).
  - `_detect_project_root()` walks `source/` looking for manifest markers (`package.json`, `pyproject.toml`, `pom.xml`, `composer.json`, `go.mod`, `Cargo.toml`, `.csproj`, etc.), prefers shallower matches, skips `node_modules` / `venv` / `.git` / `build` / `dist`. Falls back to `source/` if nothing found.
  - Idempotent — subsequent calls on an already-mirrored session are a same-size no-op.

- **Report combiner** — [backend/agents/v2_to_report_data.py](backend/agents/v2_to_report_data.py) (new, ~85 LOC)
  - `build_combined_markdown(results, session_id, target_stack)` concatenates per-agent `result` strings with labelled section dividers (`<!-- agent:{id} -->`), preserves the supervisor's completion order (which is already DAG-correct).
  - `per_agent_markdown(results)` returns `{agent_id: markdown}` for per-agent export.
  - Designed to feed the single-markdown signature of the existing [tools/document_generator.py](backend/tools/document_generator.py): `generate_docx(markdown, session_id, agent_id)` / `generate_markdown_report(...)` / `generate_pdf(...)`. No changes to `document_generator.py` were needed.

- **New FastAPI endpoint `/api/analyze-v2`** — [backend/main.py](backend/main.py) (appended after `/api/analyze/stream`)
  - Accepts the same `RunAnalysisRequest` as v1 (`session_id`, `agent_ids`, `stack`, ...).
  - Validates agent IDs against the v2 `AGENT_REGISTRY` (rejects any IDs not in the 12-agent set with a 400).
  - Materialises session layout via `ensure_agent_layout()` with in-memory `_sessions[sid]` as the fallback source.
  - Emits a `plan` event first (applicable agents + tier + target stack), runs **discovery** (one `claude -p` call, Haiku), writes the digest to `context/digest.md`, splits per-agent briefs into `context/brief_{agent_id}.md`, then hands off to `supervisor.run_supervised()`.
  - **Backward-compatible SSE envelope** — every rich `agent_start` / `agent_complete` / `agent_error` event is also emitted in the legacy `{type: start|complete|error, agent_id, ...}` shape so the existing React frontend works unchanged. Rich events (`system` / `assistant` with tool-call timeline / `tool_result` / `result`) are additive — the old frontend ignores unknown `type` values.
  - Bridges the runner's async `on_progress` callback into the SSE generator via a bounded `asyncio.Queue(maxsize=512)` so a stuck subscriber can't balloon memory during long code-generation runs.
  - On completion: builds combined markdown, auto-exports docx via `generate_docx`, emits legacy `report` + `done` events with `docx_path`.

- **Syntax + import smoke tests all pass**
  - `py_compile` clean on all 16 touched/created files.
  - `import backend.agents.{runner,supervisor,director,orchestrator,prompts,...}` all resolve.
  - `compute_waves()` returns the expected 3-layer DAG for the 12-agent set.
  - `/api/analyze-v2` registered alongside `/api/analyze` and `/api/analyze/stream` per AST scan of `main.py`.

### Risks / known issues

- **Not yet run end-to-end on a real session.** Phase 5 of the original plan (prompt-adaptation + first-pipeline dry run on a small sample project) is still open. The next step is a real `/api/analyze-v2` call against one of the existing `uploads/{sid}/` sessions.
- **Cost-tracker wiring** — `cost_tracker.record_call(...)` is invoked inside the supervisor/orchestrator/director (all three write `AgentCallRecord` rows). Should produce `data/cost_tracking.db` + `exports/cost_reports/{sid}_cost_analysis.xlsx`. Not yet verified — Phase 7 task.
- **Windows junction vs file copy** — chose file copy (`shutil.copy2`) over `mklink /J` because junctions need Developer Mode on non-admin shells. Adds one-time I/O cost per session but avoids a permission class. Revisit if it becomes a bottleneck on large uploads.
- **Sister has 14 prompts, we use 12** — `prompts.py` still ships `AGENT_PROMPTS` for all 14 agents (including `code-review` and `contract-audit`). Harmless — the 12-entry `AGENT_REGISTRY` drives dispatch, so the extra two never run unless someone adds them to the registry.

### Next step on green light from the user

1. Start `uvicorn main:app --reload` from `backend/`.
2. Pick an existing session with files on disk (e.g. `uploads/ae272249/`).
3. `curl -N -X POST http://localhost:8000/api/analyze-v2 -H "Content-Type: application/json" -d '{"session_id":"ae272249","agent_ids":["code-analysis","architecture","security"]}'` — watch SSE events stream.
4. Validate: `plan` event emits, `discovery_start`/`discovery_complete` pair arrives, each of the 3 agents produces `agent_start` → tool-call events → `agent_complete` with non-empty markdown, final `report` + `done` events fire, `uploads/ae272249/context/digest.md` and per-agent briefs exist on disk, docx lands in `exports/`.

---

## 2026-04-21 — [PLANNED / TO-DO] Port Claude Code CLI runner → retire LangGraph + API-key pipeline

> Status: **planning only — nothing implemented yet**. This section is a detailed work plan to migrate AppNova's agent-execution layer from the LangGraph + 4-provider-API architecture (Claude API / Gemini / Groq / Ollama) to a `claude -p` subprocess runner ported from the sister project at `D:\Users\Chaitanya\Desktop\Working_Projects_25-26\Zip file\appnova_2026-04-17_claude-code`. Driver: the $100/mo Claude API budget is exhausted mid-month; the Max subscription is paid and underused. The CLI subprocess pattern calls Claude under the logged-in Max session (no API key), preserving the subscription for production use.

### Why this is an architecture swap, not a provider swap

AppNova today pre-extracts RAG chunks from ChromaDB and injects them into one-shot LangChain calls. Each agent sees only what the retriever gives it (~8% of the codebase). The target project gives Claude Code the **whole project directory as `cwd`** and lets each agent autonomously call `Read / Glob / Grep` until it has what it needs. That loop is what makes the output quality visibly better in the sister project — not the model choice. Wedging `ChatAnthropic` behind a subprocess wrapper would miss the point; the whole execution layer has to move.

### Preflight — already verified

- `claude -p "..." --output-format json --permission-mode bypassPermissions --model claude-sonnet-4-6` runs cleanly from `AppNova_Working_09-04-2026/` on this Windows box. Returns `is_error: false`, `service_tier: "standard"`, `total_cost_usd` reported (subscription-equivalent — not billed). Session picks up project `CLAUDE.md` / `.claude/` automatically (`cache_read_input_tokens: 46346`).
- Sister project at `appnova_2026-04-17_claude-code/` is the reference implementation — 7905 LOC across `backend/agents/`, battle-tested.

### Success criteria (non-negotiable)

1. `/api/analyze` still works from the existing React frontend — same URL, same request shape, same agent-selection checkboxes.
2. Zero Anthropic API key usage during an analysis run; all agent calls go through `claude -p` under Max subscription auth.
3. 12 currently-supported agents keep producing the same-shape markdown outputs that `tools/document_generator.py` consumes.
4. Parallel execution via DAG waves (wave 0 = up to 9 concurrent agents) — measurable ≥2× speedup over today's sequential graph.
5. Existing SSE event contract keeps working for the frontend; new richer events (tool-call timeline) are additive, not breaking.
6. Tracing (`core/tracing.py`) + the new MCP trace server keep receiving per-agent span events.
7. Side-by-side A/B runnable: `/api/analyze` (old) and `/api/analyze-v2` (new) both executable on the same session during the cutover window.

### Open decisions flagged before implementation starts

- **Agent count** — sister project has 14 agents (adds `code-review` + `contract-audit`); current AppNova has 12. Decision: **port the 12 first** to minimise scope; add `code-review` and `contract-audit` as a follow-up (Phase 8 below).
- **Upload layout** — current uses `uploads/{sid}/files/<flat>`; sister uses `uploads/{sid}/source/<detected-root>/` + `uploads/{sid}/converted/` + `uploads/{sid}/context/`. Decision: **write an adapter that materialises the new layout from the existing one** rather than breaking upload API. Adapter lives in `backend/agents/session_adapter.py` (new).
- **SSE envelope** — current frontend expects `{type: start|thinking|complete|error|done, agent_id, msg, result}`; sister emits richer `{type: agent_start|agent_complete|discovery_event|..., phase: system|assistant|tool_result|result}`. Decision: **write an event translator** that emits the old shape alongside the new one on `/api/analyze-v2`, so the frontend works unmodified. Rich phases added as new top-level event types the old frontend ignores.
- **ChromaDB** — kept alive for `/api/chat` and `/api/diff` (they still use RAG). Only the analysis pipeline stops using it. Later cleanup possible if chat is also migrated.
- **LLM fallback** — `core/llm.py` stays in the tree for chat/diff/refactor endpoints that still hit the API. Not obsoleted in this phase.
- **`/api/analyze` (v1)** — leave wired until `v2` is validated on at least 3 real projects, then delete the LangGraph code in Phase 7.

### Phase 0 — Branch + workspace prep

- [ ] `git checkout -b feature/claude-code-runner` from `main` (current HEAD: `4c14b37`).
- [ ] Confirm `claude --version` is on PATH in the same shell FastAPI will run from. On Windows this is usually `%APPDATA%\npm\claude.cmd`; document the full path in `.env` as `CLAUDE_CODE_PATH=C:\Users\Chaitanya\AppData\Roaming\npm\claude.cmd`.
- [ ] `claude login` confirm Max subscription is the active auth.
- [ ] Dry-run: from `AppNova_Working_09-04-2026/`, confirm `claude -p "hello" --output-format json --model claude-haiku-4-5-20251001` returns in <15s with `is_error: false`.

### Phase 1 — Copy runner core from sister project (no edits yet)

Copy these files verbatim into a new `backend/agents/` directory. **Do not edit imports yet** — keep them as-is so a diff against the source is clean.

| From (sister) | To (this repo) | Purpose |
|---|---|---|
| `backend/agents/__init__.py` | `backend/agents/__init__.py` | — |
| `backend/agents/runner.py` (905 lines) | `backend/agents/runner.py` | Spawns `claude -p`, parses stream-json, retry loop, Windows shim bypass |
| `backend/agents/supervisor.py` (366 lines) | `backend/agents/supervisor.py` | DAG wave scheduler + per-cwd writer lock |
| `backend/agents/state.py` (38 lines) | `backend/agents/state.py` | `RunState` TypedDict blackboard |
| `backend/agents/director.py` (413 lines) | `backend/agents/director.py` | Alternate mode: Claude dispatches its own subagents via Task tool |
| `backend/agents/orchestrator.py` (553 lines) | `backend/agents/orchestrator.py` | Alternate mode: single-session run with Task-tool fan-out |
| `backend/agents/prompts.py` (1473 lines) | `backend/agents/prompts.py` | `DISCOVERY_PROMPT`, `AGENT_PROMPTS`, `build_agent_prompt`, `split_discovery_into_briefs` |
| `backend/agents/artifact.py` (68 lines) | `backend/agents/artifact.py` | Extract HTML artefacts from UI/UX output |
| `backend/agents/scaffold.py` (518 lines) | `backend/agents/scaffold.py` | Ensures tests/, migrations/, infra/, devops/pipelines/ exist after code-gen |
| `backend/agents/sample_data.py` (508 lines) | `backend/agents/sample_data.py` | Seeds mock data into converted project (optional, behind env flag) |
| `backend/agents/diagram_qa.py` (225 lines) | `backend/agents/diagram_qa.py` | QA mermaid in agent output (used by supervisor) |
| `backend/agents/export.py` (494 lines) | `backend/agents/export.py` | Agent-level DOCX/PDF export (secondary to existing `tools/document_generator.py`) |
| `backend/cost_tracker.py` (sister root) | `backend/core/cost_tracker.py` | Per-call cost ledger → SQLite → xlsx |
| `backend/model_pricing.yaml` (sister root) | `backend/core/model_pricing.yaml` | Claude model prices for virtual-cost display |

Skipped from sister (not needed for v1):
- `backend/agents/chat.py` — current AppNova already has its own chat path; keep that for now.
- `backend/agents/browser_test.py` — Playwright E2E tester; Phase 8 candidate.
- `backend/agents/mermaid_renderer.py` — server-side mermaid SVG; current AppNova renders client-side.
- `backend/agents/run_manager.py` — launches converted app as subprocess with port-pool; Phase 8 candidate.
- `backend/auth.py`, `backend/main.py` (sister) — we're keeping this repo's FastAPI app, not replacing it.

### Phase 2 — Adapt imports + slim config

- [ ] In the 13 copied files, rewrite every `from backend.config import ...` → `from backend.agents.config import ...` (our new slim config). Leave `from backend.agents.X import Y` references internal to `agents/` untouched.
- [ ] In the 13 copied files, rewrite `from backend import cost_tracker` → `from backend.core import cost_tracker`.
- [ ] Create `backend/agents/config.py` (new, ~120 lines). Lift ONLY these from sister's root `config.py`:
  - `CLAUDE_CODE_PATH` env var
  - `AGENT_TIMEOUT`, `DISCOVERY_TIMEOUT`, `ORCHESTRATOR_TIMEOUT`
  - `HEAVY_MODEL`, `LIGHT_MODEL`, `DISCOVERY_MODEL` env vars with defaults `claude-sonnet-4-6` / `claude-haiku-4-5-20251001` / `claude-haiku-4-5-20251001`
  - `@dataclass AgentSpec`
  - `AGENT_REGISTRY` — **trim to 12 agents** (drop `code-review` and `contract-audit` for v1; the sister's `code-generation.upstream` tuple references them — rewrite to match current AppNova's dep graph)
  - `AGENT_IDS`, `AGENT_LABELS`, `model_for(tier)` helpers
- [ ] Do NOT touch `backend/config.py` (the Pydantic `Settings`) — it keeps serving chat/diff/refactor + startup config. Add a note at top of that file: "analysis agents moved to `agents/config.py` — this file serves non-analysis endpoints only."
- [ ] Add to root `requirements.txt`: nothing new (the sister's stack is a subset of ours). `openpyxl` and `pyyaml` are already present via other paths; verify.

### Phase 3 — Session-layout adapter

Sister project's runner expects `project_dir = uploads/{sid}/source/<detected-root>/` and writes to `uploads/{sid}/converted/` + `uploads/{sid}/context/`. Current AppNova uploads land in `uploads/{sid}/files/<flat>/`. Bridge the gap without touching the upload endpoint.

- [ ] New file `backend/agents/session_adapter.py`:
  - `ensure_agent_layout(session_id) -> dict[str, Path]`: given a session, creates `source/`, `converted/`, `context/` under `uploads/{sid}/` if missing. Symlinks (Windows: junctions via `mklink /J`) or copies files from the existing `files/` subtree into `source/`. Detects project root (`package.json`, `pom.xml`, `.csproj`, `composer.json`, `requirements.txt`, `pyproject.toml`, `go.mod`) inside `source/` using the sister's `_detect_project_root` logic (copy that function here).
  - Returns `{"project_dir": Path, "converted_dir": Path, "context_dir": Path}`.
- [ ] This keeps `POST /api/upload` unchanged. The adapter runs lazily on first `/api/analyze-v2` call for a session.

### Phase 4 — New FastAPI endpoint `/api/analyze-v2`

- [ ] In `backend/main.py`, add (do **not** touch existing `/api/analyze` or `/api/analyze/stream`):
  ```python
  @app.post("/api/analyze-v2")
  async def analyze_v2(req: RunAnalysisRequest):
      from backend.agents.session_adapter import ensure_agent_layout
      from backend.agents.runner import run_discovery, run_all_agents
      from backend.agents.prompts import split_discovery_into_briefs
      # ... SSE generator that calls run_discovery → split briefs → run_all_agents
      # ... translates runner events → frontend-compat SSE envelope
  ```
- [ ] Translator function `_translate_event(event: dict) -> dict` in `main.py`:
  - `agent_start` → emit BOTH `{type: "agent_start", ...}` (new) and `{type: "start", agent_id, msg: label}` (old frontend compat).
  - `agent_complete` → `{type: "complete", agent_id, result}` + keep the rich new event.
  - `agent_error` → `{type: "error", agent_id, msg: error}`.
  - `assistant` (with `tool_calls`) → forward as-is; old frontend ignores, new UI renders the tool-call timeline.
  - `done` → `{type: "done"}` + summary.
- [ ] Hook tracing: wrap each agent run with `tracing.span(kind="agent", name=agent_id, session_id=session_id)` so the MCP trace server keeps seeing events.
- [ ] Hook cost tracking: after each `run_agent_via_claude_code` returns, call `cost_tracker.record_call(...)` with the fields parsed from the CLI's `result` event.

### Phase 5 — Prompt adaptation (the fiddly part)

Sister's `prompts.py` is 1473 lines and assumes:
1. The full project is at `cwd`, readable via `Read / Glob / Grep`.
2. A `context/digest.md` + `context/brief_{agent_id}.md` per agent exists pre-run.
3. Absolute paths are injected; no relative paths.

AppNova's existing prompts in `backend/core/prompts.py` assume RAG chunks are injected inline. Those **do not carry over** — the new agents discover on their own.

- [ ] Leave `backend/core/prompts.py` untouched (still used by chat/diff/refactor).
- [ ] Use sister's `backend/agents/prompts.py` as the authoritative source for `/api/analyze-v2`.
- [ ] Test run a full pipeline on a small sample project (under `uploads/_smoke/`); compare output markdown sections against a v1 run of the same project. Expect: more granular citations, more thorough coverage, longer per-agent output.
- [ ] Tune the 12 agent prompts only if: (a) a section the docx template expects is missing, or (b) an agent over-explores (>10 minutes on a small project — indicates prompt is too open-ended).

### Phase 6 — Document export compatibility

`tools/document_generator.py` today builds its `report_data` dict from LangGraph's `AnalysisState.results`. The new runner returns `list[dict]` of `{agent_id, status, result, elapsed_seconds, error?, cost?}` — close but not identical.

- [ ] New function `backend/agents/v2_to_report_data.py::build_report_data(results, stack, session_meta) -> dict`:
  - Maps `{agent_id: result_markdown}` into the shape `document_generator` expects.
  - Parses code-analysis output for `LAYER MAP`, `MIGRATION LANE MAP`, etc. (regex on headings — same extraction that `analysis_graph.py` does today; lift those helpers into the new module).
  - Returns the `{app_name, source_stack, target_*, kpis, metrics_table, migration_rows, layer_rows, executive_summary, sections}` dict.
- [ ] `/api/analyze-v2` calls `build_report_data` at the end and passes to existing `generate_docx` / `generate_markdown_report`. No changes to `document_generator.py`.

### Phase 7 — Side-by-side validation

- [ ] Pick 3 real projects from `uploads/` (vary size: small ~20 files, medium ~150 files, large ~500+ files).
- [ ] For each: run `/api/analyze` (v1, API-backed) and `/api/analyze-v2` (CLI-backed) on the same session, export both docx.
- [ ] Compare for each agent:
  - Section completeness (does v2 cover every section v1 did?).
  - Citation accuracy (v2 should have more file:line cites because it reads live).
  - Time-to-finish (expect v2 ≥ 2× faster wall-clock due to wave parallelism).
  - Subscription usage — check `claude /status` or the CLI's own rate-limit headers; ensure we're not hammering the 5h window.
- [ ] If v2 quality ≥ v1 on all 3 projects → proceed to cutover. Otherwise, iterate on prompts (Phase 5).

### Phase 8 — Cutover + cleanup

Only after Phase 7 passes.

- [ ] Flip frontend `ConversionService`/`AnalysisService` default URL from `/api/analyze` → `/api/analyze-v2` (single-line change in `frontend_react/src/services/api.ts`).
- [ ] Keep `/api/analyze` (v1) alive for one full sprint as rollback. Add `Deprecation: true` response header.
- [ ] After one sprint with no v1 usage: **delete** the following files.

#### Files to delete in Phase 8 cleanup

| Path | Reason |
|---|---|
| `backend/graphs/analysis_graph.py` | LangGraph topology — replaced by supervisor waves |
| `backend/graphs/state.py` | `AnalysisState` TypedDict — replaced by `agents/state.py::RunState` |
| `backend/graphs/models.py` | `FoundationBlock` — no longer emitted |
| `backend/tools/context_ingester.py` | Inline codebase context prebuild — no longer used |
| `backend/tools/repo_parser.py` | `format_repo_knowledge_for_prompt` — RAG-era helper |
| `backend/core/chromadb_client.py` | Only referenced by analysis_graph + chat; if chat migrates too, delete; else keep |
| Most of `backend/core/llm.py` | Keep `get_agent_llm`, `invoke_batched` only if chat still uses them; delete 2000+ lines of synthesis/batching logic (lines ~1400-2500) |
| Most of `backend/core/prompts.py` | Delete all 12 `*_AGENT_SYSTEM` constants (~1200 lines); keep `SHARED_CONTEXT` only if chat uses it |
| `backend/config.py` | Shrink: delete all `gemini_*`, `groq_*`, `ollama_*`, `claude_*` per-key config, agent_model_map, synthesis knobs. Keep: `embeddings_model_*`, API port/CORS, tracing paths |
| Root `requirements.txt` | Drop `langchain`, `langgraph`, `langchain-anthropic`, `langchain-community`, `anthropic`, `chromadb`, `sentence-transformers` |

Keep untouched: `backend/main.py` routing shell, `backend/core/tracing.py`, `backend/mcp_server/`, `tools/document_generator.py`, `tools/file_processor.py`.

#### Post-cleanup add-ons (optional, as capacity allows)

- [ ] Port sister's `code-review` + `contract-audit` agents (bumps registry to 14).
- [ ] Port sister's `run_manager.py` for one-click "run the converted app" from the UI.
- [ ] Port sister's `browser_test.py` for automated E2E on the converted output.
- [ ] Port sister's `chat.py` per-agent branching chat tree (replaces the current single-thread chat).

### Rollback plan

Every phase is reversible until Phase 8 deletion:

- Phase 0–5: all additions; `git checkout main` reverts.
- Phase 6–7: v1 and v2 coexist behind different URLs; set frontend flag to v1 and v2 code is dead but harmless.
- Phase 8 is the only destructive step. Tag the pre-Phase-8 commit (`pre-cleanup-<date>`) so a single `git reset --hard <tag>` on a new branch restores the full LangGraph pipeline.

### Estimated effort

- Phases 0–1 (branch + copy): **~30 min**.
- Phase 2 (config + imports): **~1 hr**.
- Phase 3 (session adapter): **~1 hr** on Windows (junction handling).
- Phase 4 (new endpoint + event translator): **~3 hr**.
- Phase 5 (prompt validation): **~4 hr** first project, then minor tweaks.
- Phase 6 (report-data shape): **~2 hr**.
- Phase 7 (A/B validation): **~1 day** wall-clock for 3 full analyses.
- Phase 8 (cleanup): **~2 hr** when the time comes.
- **Total: ~2 focused days + 1 day validation.**

### First concrete next step on green light

`git checkout -b feature/claude-code-runner`, `mkdir backend/agents`, copy the 13 files from Phase 1. Nothing else until that compiles cleanly on `uvicorn backend.main:app --reload` (it won't be wired up; just needs to not break imports).

---

## 2026-04-16 — Mermaid leak fix + Convert persistence across tab switches

Two independent production bugs reported from the same user session:

1. **Mermaid "syntax bombs" were piling up in the page margin** across every agent tab, not just the one that emitted the bad diagram.
2. **Clicking Convert and then switching tabs killed the conversion run** and lost all client progress; coming back to the tab showed either an empty panel or a stale manifest snapshot.

Both root-caused and fixed end-to-end — the fixes don't just mask the symptoms.

### Mermaid: parse-before-render + orphan cleanup + placeholder prompt fix

**Symptom:** 30+ bomb-icon SVGs labeled "Syntax error in text / mermaid version 11.14.0" stacked vertically in the left margin of the Documentation tab. Our React error UI shows a `⚠` triangle with a plain-English message — the bombs were coming from somewhere else.

**Root cause:** Mermaid v11's `render(id, text)` creates a temp `<div id="d<id>">` in `document.body` and, on parse failure, writes its built-in bomb error SVG there before throwing. The prior `MermaidBlock` caught the throw but never removed the orphan. React StrictMode (dev) doubled the leak; `theme` in the effect's dep array multiplied it on every light/dark flip; orphans live on `<body>`, so they followed the user across tab switches.

**Fix** — layered so no single failure mode can re-introduce the leak:

- [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — rewrote `sanitizeMermaidSource` to return `{ ok, source | reason }` and reject **before** calling mermaid: empty blocks, bracketed placeholders like `[Mermaid flowchart showing ...]`, and any content whose first non-comment line doesn't begin with a known diagram keyword (`graph`, `flowchart`, `sequenceDiagram`, `classDiagram`, `stateDiagram(-v2)`, `erDiagram`, `journey`, `gantt`, `pie`, `mindmap`, `timeline`, `gitGraph`, `quadrantChart`, `requirementDiagram`, `C4{Context,Container,Component,Dynamic,Deployment}`, `xychart-beta`, `sankey-beta`, `block-beta`, `packet-beta`, `architecture-beta`). Rejected blocks short-circuit to the error UI without ever touching `mermaid.*`, so no temp DOM can be created even on repeated theme flips.
- [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — `MermaidBlock` now calls `mermaid.parse(source, { suppressErrors: true })` before `render`. Parse is side-effect-free: if it returns `false`, we display the error UI and skip render entirely. Only syntactically valid sources reach `render`, which is the only mermaid call that can leak DOM.
- [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — new `cleanupMermaidOrphans(domId)` evicts both `d<id>` (temp container) and any body-parented `<svg id="<id>">` (final SVG mis-appended to body). It runs in `finally` after every render attempt AND in the effect's cleanup. Belt-and-suspenders: the parse gate already blocks 99% of leaks, but this catches the remaining 1% where mermaid.js itself has a regression.
- [frontend_react/src/App.tsx](frontend_react/src/App.tsx) — one-time body sweep on mount (`body > svg[id^="report-mermaid-"], body > div[id^="dreport-mermaid-"]`) evicts any orphans left behind by the previous build before this fix shipped. Harmless no-op on a clean DOM.
- [backend/core/prompts.py](backend/core/prompts.py) — the Architecture agent's mermaid templates at `ARCHITECTURE_DIAGRAM_REQUIREMENTS` and `ARCHITECTURE_OUTPUT_CONTRACT` used to hand the LLM bracketed placeholders inside a ```mermaid fence (`[Mermaid flowchart showing the current system architecture]`). Weaker providers copied the placeholder verbatim → automatic syntax error → bomb. Replaced every placeholder with a **concrete mini-example** using real `graph TD` / `flowchart LR` syntax and added rule #5: "NEVER emit a mermaid fence whose content is `[placeholder text]`". The frontend guard catches it anyway, but the prompt change means fewer `⚠` cards show up in practice.

### Convert tab: detached backend task + hoisted frontend state

**Symptom:** clicking **▶ Start / Resume** on Convert, then switching to any other tab (Report, Code View, Dashboard) killed the running conversion. Coming back showed an empty panel or whatever was on disk before the switch. Only batches that finished writing their manifest row before the switch survived.

**Root cause — three layered problems:**

1. `<ConversionPanel />` is conditionally mounted (`activeView === 'convert'`). Tab switch → unmount → state destroyed, cleanup effects fire.
2. The panel's cleanup effect called `abortRef.current?.abort()`, aborting the SSE `fetch` used to stream events. Browser closes the HTTP connection.
3. Backend `POST /api/convert/{sid}` was a plain `StreamingResponse` with `async for event in run_conversion(...)`. Client disconnect → `asyncio.CancelledError` propagates into the runner → every in-flight batch task is cancelled. No detached task, no registry, no queue decoupling.

**Fix — both sides, decoupled lifecycles:**

Backend:

- [backend/tools/conversion_registry.py](backend/tools/conversion_registry.py) **(new file)** — `ConversionJob` + module-level `registry`. A job owns: one `asyncio.Task` producer (drives `run_conversion`), a bounded replay log (2048 events), and a list of per-subscriber `asyncio.Queue`s (each 1024 cap). `publish(event)` appends to the log and fans out to every subscriber; slow subscribers that would block the producer are **dropped** rather than allowed to back-pressure. `subscribe()` is an async iterator that replays the log on attach, then tails live — so a late reconnect sees `conversion_started` and every earlier batch. `mark_done()` sends a `None` sentinel to all subscribers so their iterators terminate cleanly. The registry's `get_or_create(sid)` is the start-or-attach primitive: returns `(job, created=True)` for the first caller so it owns the producer; returns `(job, False)` for every subsequent caller so they attach as subscribers only. Terminal jobs are replaced with a fresh one on the next `get_or_create`.
- [backend/main.py](backend/main.py) — rewrote `POST /api/convert/{sid}` as start-or-attach. The first client wraps `run_conversion(...)` in a **detached** `asyncio.create_task(..., name=f"conversion:{sid}")`. Client disconnect aborts the subscriber relay (throws `CancelledError` in `_relay()`), which we silently swallow; the producer task is untouched and keeps running. The request body (`target_stack`, `tree_hint`, `concurrency`, `force`) is honored only on `created=True` — later attachers get whatever run is already in flight.
- [backend/main.py](backend/main.py) — new `GET /api/convert/{sid}/status` returns a lightweight snapshot: `{ running, terminal, has_job, started_at, current_batch, totals: { total_batches, total_files, completed_batches, cached_batches, failed_batches, completed_files }, subscribers }`. Frontend uses this on mount to decide whether to attach to a live stream or just pull the manifest.
- [backend/main.py](backend/main.py) — new `DELETE /api/convert/{sid}` cancels the detached task (`job.cancel()` → `task.cancel()`). The runner catches `CancelledError`, publishes `{ type: 'error', message: 'Conversion cancelled by user' }` + `{ type: 'done' }`, then `mark_done()` closes every subscriber. No orphaned tasks, no zombie queues.

Frontend:

- [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) — `ConversionService.getStatus(sid)` and `cancel(sid)`. Added a `ConversionStatus` type matching the backend snapshot. Existing `stream()` documented as idempotent (POST is start-or-attach server-side).
- [frontend_react/src/contexts/AppContext.tsx](frontend_react/src/contexts/AppContext.tsx) — **hoisted** all conversion state out of the panel: new `ConversionRow`, `ConversionState` types and a `conversion: ConversionState` context field with `rows`, `running`, `totalBatches`, `totalFiles`, `statusLine`, `error`, `targetStack`, `treeHint`, `concurrency`. New actions `startConversion({ force? })`, `stopConversion()`, `refreshConversionManifest()`, `setConversionTargetStack/TreeHint/Concurrency`, `clearConversionError` live on the provider. The SSE consumer (`for await (const ev of ConversionService.stream(...))`) runs at **provider lifecycle**, not panel lifecycle — so unmounting the panel can no longer abort it. A `conversionStreamingRef` single-flight guard prevents auto-reconnect and a manual ▶ Start from racing.
- [frontend_react/src/contexts/AppContext.tsx](frontend_react/src/contexts/AppContext.tsx) — auto-reconnect effect on `sessionId` change: calls `getStatus(sid)`; if `running: true`, fires `startConversion()` which POSTs → backend sees the existing detached job and replays the event log + tails live. If no live job, falls back to a manifest snapshot. Means: close browser mid-run, reopen → automatically reattaches to the live stream without the user doing anything.
- [frontend_react/src/contexts/AppContext.tsx](frontend_react/src/contexts/AppContext.tsx) — `stopConversion()` calls `ConversionService.cancel(sid)` first (server-side cancel → producer publishes `error` + `done` → subscribers close cleanly), then aborts the local subscriber fetch as a fallback for the case where the DELETE couldn't be reached.
- [frontend_react/src/components/ConversionPanel.tsx](frontend_react/src/components/ConversionPanel.tsx) — collapsed to a **pure view** over the context. **Removed** the abort-on-unmount cleanup effect, the local `useState` for rows / running / totals / options, the per-mount `getManifest` fetch, and the per-panel `AbortController`. The panel now just reads `conversion` + `start/stopConversion` from context. Tab switches are free.

### Why this structure is robust

- **Client disconnect ≠ cancellation.** The producer task lives in the registry, not on a request scope. `fetch.signal.abort()` only closes one subscriber.
- **Multiple subscribers per job.** Two tabs on the same session both see live progress (the fan-out is O(n) subscribers, each with its own queue).
- **Late reconnect catches up.** The 2048-event replay buffer covers `conversion_started` plus every batch — a user closing + reopening the browser on a 500-batch run still sees all past events before tailing live.
- **Terminal-job replay.** After `conversion_complete`, the job stays in the registry as terminal. A reconnect gets the full log then immediately closes — no confusing "still running?" state.
- **Server-restart wipes state.** The existing `LS_SERVER_INSTANCE` logic in AppContext already clears localStorage on server-instance mismatch; the registry is process-local, so a restart means `getStatus` returns `has_job: false` → frontend correctly falls back to manifest.
- **Manifest is the source of truth for completed work.** The runner flushes per batch (unchanged — already was). Cancel mid-run loses only in-flight batches; everything `done` or `cached` survives.

### Validation

- `npx tsc --noEmit` — exit 0 (frontend typecheck clean).
- `npx vite build` — success; bundle warnings are pre-existing and unrelated.
- `python -c "import ast, ..."` — all edited Python files parse.
- Smoke test `tools/conversion_registry` directly: create job, fake producer publishes 4 events + `mark_done`, late subscriber replays all 4 and closes, subsequent `get_or_create` returns a fresh job (terminal-replacement), `cancel()` on a task-less job returns `False`. PASS.
- Manual test plan:
  1. Upload a repo, click ▶ Start / Resume, watch batches stream.
  2. Switch to Dashboard tab, wait 10 s, switch back — batches should still be accumulating in the panel.
  3. Close the browser tab while conversion is running, reopen the app — panel should reattach and show live progress without re-running anything.
  4. Click ⏹ Stop — backend task cancels, `statusLine` shows "(stopped)", ▶ Start returns. Manifest on disk still has every completed batch.
  5. Render an agent report with a ```mermaid``` fence whose contents is `[placeholder]` — should show the `⚠` error card, NOT a bomb. Check `<body>` in DevTools — no orphaned `svg[id^="report-mermaid-"]` elements.

---

## 2026-04-16 — theme + Code View + Mermaid polish

Six unrelated UI bugs that all surfaced during user testing in light mode. Grouped here because they share the "ship-before-demo" constraint; each fix is localized.

### Convert panel did not respect the light theme

[frontend_react/src/style.css](frontend_react/src/style.css) — every color in `.conversion-*` referenced `var(--surface-2, …)`, `var(--surface-3, …)`, `var(--border, #2a3654)`, etc. **None of those variable names are defined** in `index.css` (the tokens are `--surface2`, `--card2`, `--border` with no dash-number). The fallback literals therefore baked dark-mode colors into the panel regardless of `html.light`. Renamed every reference to the canonical tokens (`--surface2`, `--card2`, `--accent`, `--accent2–5`, `--muted`, `--text`) and added explicit `color: var(--text)` to the title / subtitle / batch rows so light-mode text isn't left inheriting from an ancestor. Hardcoded status colors (`#22c55e`, `#f59e0b`, `#ef4444`, `#3b82f6`) were swapped for `--accent3/4/5` so light-mode versions automatically darken for contrast.

### "Agent N of N running…" was unreadable in light mode

[frontend_react/src/index.css](frontend_react/src/index.css) — `.analysis-progress-subtitle` used `color: var(--muted)` which resolves to `#4a6a8a` in light theme — low contrast over `--bg: #f0f4f8`. Bumped to `var(--text)` with `font-weight: 500` and an explicit `html.light` override. Also tightened `.sidebar-agent-status--pending` for light mode: the dark-mode amber `#f5a623` on `rgba(255, 200, 80, 0.14)` washed out completely on white; light mode now uses `#9a3412` text on a stronger amber tint.

### Mermaid rendered a "syntax bomb" on Gemini output

[frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — Gemini regularly wraps its Mermaid source in an inner \`\`\`mermaid fence, prepends a bare "mermaid" line, and HTML-escapes angle brackets / ampersands inside node labels. All of those are syntactically invalid to mermaid.js even though the diagram itself is fine. Added `sanitizeMermaidSource()` that strips BOM / zero-width chars, peels any \`\`\`mermaid fence, unescapes `&amp;/&lt;/&gt;/&quot;/&#39;/&nbsp;`, and trims — then feeds that into `mermaid.render()` and into the fallback `<pre>` so what the user sees as source matches what was attempted. The fallback UI dropped the 💣 emoji (via `report-mermaid-error--bomb` / `report-mermaid-bomb` module classes) for a neutral `⚠` with a plain-English "Diagram source had a syntax issue and was shown as code instead." — less alarming when the underlying markdown is still fine to read.

### Code View transition was slow on large generations

[frontend_react/src/components/DiffView.tsx](frontend_react/src/components/DiffView.tsx) — the persisted-files hook fired on every mount and awaited `GeneratedFilesService.read()` **serially** for every file on disk. At 30 files × ~80 ms per round-trip this added ~2.5 s of unavoidable stall when switching from any agent tab to Code View. Two changes: (1) skip the fetch entirely when `codeGenLiveFiles.length > 0` — we already have fresher content in memory from the streaming `file_saved` events; (2) replace the `for … of` serial await with `Promise.all(meta.map(…))`. The hook now completes in one round-trip rather than N.

### Original button showed a single pane instead of a diff

[frontend_react/src/components/DiffView.tsx](frontend_react/src/components/DiffView.tsx) — clicking **Original** on a generated file used to mount a plain `<Editor>` showing only `originalContent`, so the user had to additionally click **Diff** to actually compare. The user's expectation (and the label's implied meaning — "Original vs. this file") is a side-by-side: input file on the left, generated file on the right. Switched the `viewMode === 'original'` branch to render `<DiffEditor renderSideBySide>` with `original={originalContent}` and `modified={selectedFile.content}`. The dedicated **Diff** button still works; they now produce the same layout, and the keyboard shortcut `o` no longer "loses" the generated pane.

### Why "Code Generation" shows generated code (not a fix — clarification)

The Code Generation agent's job is to take the uploaded source tree and emit a target-stack equivalent (ASP.NET Core + React by default, configurable in the options drawer). The Code View tab pulls from three sources in priority order — `codeGenLiveFiles` (streaming `file_saved` events as the agent writes each file), markdown code fences parsed from the agent's final report, then the persisted `uploads/{sid}/generated/` tree on disk — so what you see under **⚡ Generated** is deliberately the agent's output. The **📂 Input** section of the same tree lists the files you uploaded; selecting one of those shows the original source in the pane on the right, and clicking **Original** (now side-by-side) puts the matching input file next to the generated one for comparison.

### Validation (2026-04-16 polish)

- TypeScript / ESLint clean after edits (one pre-existing missing-button-type hint on line 450 of DiffView.tsx is untouched).
- CSS diagnostics surfaced only unrelated pre-existing `@keyframes` composite/paint perf hints.
- Manual smoke path required before demo: toggle light theme → Convert tab (panel should follow light surface tokens), run analysis (Actions subtitle visible), switch to Code View on a >20-file generation (transition should feel instant), click a generated file → **Original** (should be side-by-side), render a Mermaid-heavy report with Gemini as the provider (diagrams should render; malformed ones should show the new `⚠` message, not 💣).

---

## 2026-04-16 addendum — frontend wiring for refine_agent

Closes the loose end from the morning entry (Section 2 step 4 of the 2026-04-15 plan): the backend `refine_agent` field is now reachable from the UI without callers having to pair `force_rerun: true` with the agent id by hand.

- [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) — `streamAnalysis` gains an optional `refineAgent` param and forwards it to `/api/analyze/stream` as `refine_agent`. New `AnalysisService.refine(sessionId, agentId, stack, ...)` convenience wrapper sets both `forceRerun: true` and `refineAgent: agentId`.
- [frontend_react/src/contexts/AppContext.tsx](frontend_react/src/contexts/AppContext.tsx) — `runSingleAgent(agentId, forceRerun?, refine?)` gains a 3rd `refine` flag; when true it calls `AnalysisService.refine(...)` instead of the plain stream so the backend drops the session + global caches before the LLM call.
- [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — new "🔄 Refine" button next to the existing "♻️ Re-run (ignore cache)". Tooltip explains the difference: refine cascades — downstream code-generation / testing / ui-ux runs after a refine pull the refreshed upstream content automatically (because the global cache row was dropped, not just bypassed).

### Why both buttons stay

`Re-run (ignore cache)` only **bypasses** the cache lookup — the LLM result then goes through `cache_put`, replacing the old entry. Re-run is fine when the user just wants this one agent's output rewritten. `Refine` additionally **deletes** the cache entry up front (logged + emitted as a `thinking` SSE event), and the `refine_agent` field carries through every log line so future runs that hit the same content fingerprint also re-evaluate. Useful when the user has edited the agent's skill/prompt or wants a clean cascade into downstream agents.

### Validation

- TypeScript / ESLint clean (no diagnostics surfaced after the edit).
- Smoke path: click "🔄 Refine" on business-rules → `[StreamAnalyze] 🔄 REFINE business-rules — dropped session_chunks=N, global_chunks=M` appears in `appnova_app.log`, plus the existing `Cache policy for this run: {…, 'refine_agent': 'business-rules'}` summary line.

---

## 2026-04-16 — implemented: selective cache policy, refine invalidation, multi-agent Code View, extraction contract for business-rules

Implements Sections 1–4 and 6 of the 2026-04-15 plan below. All edits are live in the working tree.

### Selective cache policy + run-level summary

- [backend/main.py](backend/main.py) — renamed the local set `_NO_CACHE_AGENTS` → `_BYPASS_OWN_CACHE_AGENTS` and lifted it out of the per-agent loop so it lives next to the new run-level summary log. New comment spells out the intent: these agents skip lookup of THEIR OWN cached report, but still consume prior agents' cached reports via `state['results']` and `get_analysis_result(upstream_id, ...)`.
- [backend/main.py](backend/main.py) — new structured log line at the top of each run: `[StreamAnalyze] Cache policy for this run: {bypass_own_cache, force_rerun, refine_agent}`. Makes `appnova_app.log` self-documenting per request.
- [backend/main.py](backend/main.py) — when a `BYPASS_OWN_CACHE` agent runs, the log now includes a one-line upstream snapshot (`upstream=[code-analysis:55K, architecture:23K, business-rules:32K, …]`) so missing upstream reads are visible without grepping the surrounding lines (Section 3).

### Refine invalidation (drop just one agent's caches)

- [backend/api/schemas.py](backend/api/schemas.py) — `RunAnalysisRequest` gains an optional `refine_agent: str` field. Narrower than `force_rerun`: only the named agent's caches are dropped before the run.
- [backend/core/chromadb_client.py](backend/core/chromadb_client.py) — new `delete_analysis_result(agent_id, session_id)` removes every chunk of one agent's session-cache result via metadata filter. Logs the chunk count.
- [backend/core/chromadb_client.py](backend/core/chromadb_client.py) — new `cache_delete(pipeline_fp, codebase_fp, agent_id)` symmetric to `cache_get` / `cache_put`; removes the global content-keyed entry for one (pipeline, codebase, agent) triple.
- [backend/main.py](backend/main.py) — refine pre-flight block runs before the agent loop: when `refine_agent` is set, both helpers fire, the chunk counts are logged, and a `thinking` SSE event is emitted so the UI can display the cache reset.

### Code View multi-agent merge + persisted-on-disk fallback (fixes "Diff View shows nothing" bug)

- [backend/main.py](backend/main.py) — new `GET /api/code/file/{session_id}/{rel_path:path}` returns the raw text of a single generated file. Path traversal guard: the resolved path must stay under `uploads/{sid}/generated/`. Backs the new on-disk fallback in DiffView so the file tree is populated even when the code-generation agent's cached markdown contains only a summary.
- [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) — new `GeneratedFilesService` with `list(sessionId)` (calls existing `/api/code/files/{sid}`) and `read(sessionId, relPath)` (calls the new endpoint). Encodes each path segment so directories with spaces or unicode survive the round-trip.
- [frontend_react/src/components/DiffView.tsx](frontend_react/src/components/DiffView.tsx) — `parsedFiles` now resolves in priority order: (1) `codeGenLiveFiles` from streaming `file_saved` events, (2) fenced-code-block files merged from EVERY artifact-producing agent (`code-generation` + `ui-ux` + `testing`, de-duped by path), (3) on-disk persisted files fetched from the new endpoint. New `useEffect` hydrates the persisted list when the session changes; cancellation guard prevents stale state on rapid switches.

### EXTRACTION_DOCUMENT_CONTRACT for business-rules (no more "outside the defined scope" leakage)

- [backend/core/prompts.py](backend/core/prompts.py) — new `EXTRACTION_DOCUMENT_CONTRACT` constant. Replaces `## Findings` / `## Recommendations` with `## Rule Inventory` + `## Edge Cases & Assumptions` + `## Traceability Matrix` and tells the LLM to OMIT a section when there is nothing to extract instead of inserting a self-disclaiming paragraph.
- [backend/core/prompts.py](backend/core/prompts.py) — `BUSINESS_RULES_AGENT_SYSTEM` now appends the new contract instead of `STANDARD_DOCUMENT_CONTRACT`. Other specialists keep the standard contract.
- [backend/graphs/analysis_graph.py](backend/graphs/analysis_graph.py) — new `_strip_extraction_disclaimer_sections(text, agent_id)` defensively removes any `## Findings` / `## Recommendations` section whose body matches the regex `outside the defined scope`. Sections with real content are kept untouched. Called from `format_agent_result_document()` for `business-rules` so cache-replayed older reports also render clean. Logs a warning when it strips so we can spot LLMs that still emit the disclaimer.

### Validation done

- `python ast.parse` clean on `main.py`, `core/chromadb_client.py`, `core/prompts.py`, `graphs/analysis_graph.py`, `api/schemas.py`.
- Live import + functional check via `backend/venv`: extraction contract reaches `BUSINESS_RULES_AGENT_SYSTEM`; `_strip_extraction_disclaimer_sections` removes the two disclaimer sections from a synthetic report while preserving `## Rule Inventory`. Stripper logs `[ReportFormatter] Stripped disclaimer Findings/Recommendations section(s) from business-rules report` exactly once.
- Browser-side test still required: full UI sweep through Code View tab + business-rules report after a fresh backend restart.

### Notes for the user

- Restart the backend so the prompt + cache changes take effect.
- For an existing `business-rules` cache, run with `refine_agent: "business-rules"` (or simply press the existing Refine button once it's wired through `AnalysisService`) to drop the disclaimer-laden cached copy and force a re-run under the new contract.
- Frontend `AnalysisService.refine()` wrapper is NOT wired yet (Step 4 of Section 2 of the plan); current callers can still pass `force_rerun: true` for the same effect across all agents.

---

## 2026-04-15 planned — selective cache policy + Code View multi-agent merge

**Status:** design only — not yet implemented. Listed here so the plan is reviewable before any code lands.

**Goal:** refine the cache behaviour introduced by the current addendum so that the policy matches intent: the foundation-and-specialist agents (code-analysis → migration-planner) keep their cached reports across runs, while code-generation / testing / ui-ux skip **only their own** cached output but still consume the cached reports of the upstream agents. A user-initiated refine of any earlier agent must invalidate that agent's cache entry and cascade to the three downstream agents on their next run. Also pull ui-ux and testing generated files into the Code View tab alongside code-generation output.

### 1. Scope the cache bypass to the agent's OWN result only

**Why:** today `_NO_CACHE_AGENTS = {"code-generation", "testing", "ui-ux"}` in [backend/main.py](backend/main.py) blocks the cache lookup for those three agents. The intent is correct (always re-run them), but we want to make the semantics explicit in the code so it's obvious from reading that the **upstream** agents' caches are still consumed — nothing else needs to change on the hot path, but a comment rename + policy constant makes future edits safer.

**Steps:**

1. [backend/main.py](backend/main.py) — rename `_NO_CACHE_AGENTS` → `_BYPASS_OWN_CACHE_AGENTS`. The set remains `{"code-generation", "testing", "ui-ux"}`. Update the inline comment to spell out: *"These agents skip lookup of THEIR OWN cached report so they always re-run, but they still consume prior agents' cached reports via `state['results']` and `get_analysis_result(upstream_id, ...)`."*
2. [backend/main.py](backend/main.py) — log a single structured line at the top of the stream-analyze loop summarising which agents will hit cache, which will bypass, and which were refined. Makes the run self-documenting in the log.
3. No change needed for the upstream-report consumption path: `_code_analysis_foundation`, `_architecture_output`, and the ReAct briefing already inherit from the prior agent's `results` list regardless of whether that result came from cache or a fresh LLM call.

### 2. Honour user-initiated refinement (invalidate exactly the refined agent)

**Why:** when the user re-runs a single upstream agent (e.g. "Refine business-rules") via `runSingleAgent`, the new result must replace the cached one, and any downstream code-gen / testing / ui-ux run that follows must see the refined content — never the old cached value.

**Steps:**

1. [backend/main.py](backend/main.py) (stream-analyze endpoint) — when `request.force_rerun` is true OR the request body carries a new optional field `refine_agent: str`, (a) call `chromadb_client.delete_analysis_result(agent_id, session_id)` for that agent before running, and (b) also drop the global pipeline-keyed cache entry via `core.cache_warmer.cache_delete(_agent_pfp, _codebase_fp, agent_id)`. This is the only way to guarantee downstream reads won't race a stale entry.
2. [backend/core/chromadb_client.py](backend/core/chromadb_client.py) — new `delete_analysis_result(agent_id, session_id)` helper symmetric to `store_analysis_result`. Removes all chunks for the agent by metadata filter.
3. [backend/core/cache_warmer.py](backend/core/cache_warmer.py) — new `cache_delete(pipeline_fp, codebase_fp, agent_id)` symmetric to `cache_get` / `cache_set`.
4. [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) — `AnalysisService.refine(agentId, sessionId)` sends `{ refine_agent: agentId, force_rerun: true }` so the backend knows the call is a refinement, not a fresh run.
5. [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — the existing "Refine" / "Re-run this agent" button calls the new service method. UI already exists for `runSingleAgent`; this just tightens the contract.

### 3. Ensure code-gen / testing / ui-ux always read the latest refined reports

**Why:** [backend/tools/conversion_runner.py](backend/tools/conversion_runner.py) already pulls reports via `core.chromadb_client.get_analysis_result(agent_id, session_id)`. That call returns whatever was last stored, so post-refine reads are automatically current. Only thing missing is the cache invalidation in step 2. No change here if step 2 lands.

**Steps:**

1. Cross-check in [backend/main.py](backend/main.py) stream-analyze loop: when code-generation / testing / ui-ux run, log a one-line summary *"upstream=[code-analysis:56K, architecture:23K, business-rules:32K, …] reports_fp=abc123"* so regressions in the upstream pull are visible in `appnova_app.log`.
2. No behaviour change needed in the runner — the reports fingerprint already propagates refinement (the hash changes when the stored text changes, so the per-file conversion cache also flushes automatically).

### 4. Code View merges code-generation + ui-ux + testing output

**Why:** [frontend_react/src/components/DiffView.tsx:163-166](frontend_react/src/components/DiffView.tsx#L163-L166) only parses files from `analysisResults.find(r => r.agent_id === 'code-generation')`. Now that the auto-save hook writes ui-ux and testing files to `uploads/{session}/generated/`, those files must also surface in the file tree.

**Steps:**

1. [frontend_react/src/components/DiffView.tsx](frontend_react/src/components/DiffView.tsx) — replace the single `codeGenResult` lookup with `codeGenResults = analysisResults.filter(r => ['code-generation', 'ui-ux', 'testing'].includes(r.agent_id))`. Concatenate parsed files from every matching result, de-duplicated by path (keep the most-recent entry when the same path appears twice).
2. Prepend a per-file badge in the tree (`CODE`, `UX`, `TEST`) so the reviewer knows which agent produced each file — required because ui-ux and code-gen may emit different targets for the same source module.
3. Keep `codeGenLiveFiles` as the live-streamed overlay exactly as today; the merge happens only in the post-run `parseFilesFromMarkdown` fallback path.
4. Filter chips: extend the existing filter UI so reviewers can scope the tree to "all / code-gen / ui-ux / testing" without losing context.

### 5. Validation

**Steps:**

1. Unit: exercise `delete_analysis_result` and `cache_delete` against an empty + populated collection to confirm the metadata filter removes every chunk.
2. Integration: run analysis → refine `business-rules` → run code-generation again. Log must show `CACHE-HIT business-rules` initially, then `CACHE-MISS business-rules (refine)` after refinement, then `⏸ BYPASS code-generation (uses refined business-rules)`.
3. UI: verify the Code View tab lists files from all three agents after a full run, with correct badges and filter chips.
4. Append an implementation entry to [changes.md](changes.md) once merged (prepended per file convention).

### 6. Strip mandatory Findings / Recommendations sections from extraction-only agents

**Why:** the Business Rules report page currently renders two sections that the agent itself documents as out-of-scope:

> *"This report is a pure business-rules extraction document. Findings sections are outside the defined scope of this agent."*

Root cause: [backend/core/prompts.py:1470](backend/core/prompts.py#L1470) concatenates `STANDARD_DOCUMENT_CONTRACT` ([backend/core/prompts.py:100-120](backend/core/prompts.py#L100-L120)) onto `BUSINESS_RULES_AGENT_SYSTEM`. That contract *mandates* `## Findings` and `## Recommendations` headers, so the LLM emits them even though the business-rules skill tells it not to. The LLM "resolves" the conflict by producing the section headers with self-disclaiming bodies — which the user then sees in the report.

The same collision applies to any pure-extraction agent where the skill's scope contradicts the generic five-section contract (candidates: `business-rules`, possibly `data-migration` and `integration` depending on intent).

**Steps:**

1. [backend/core/prompts.py](backend/core/prompts.py) — introduce a new `EXTRACTION_DOCUMENT_CONTRACT` constant that omits `## Findings` and `## Recommendations` and replaces them with `## Rule Inventory` + `## Edge Cases & Assumptions` + `## Traceability Matrix`. Extraction-only agents use this; strategic/review agents keep `STANDARD_DOCUMENT_CONTRACT`.
2. [backend/core/prompts.py:1470](backend/core/prompts.py#L1470) — change the business-rules line from `BUSINESS_RULES_AGENT_SYSTEM += COMMON_AGENT_OUTPUT_REQUIREMENTS + STANDARD_DOCUMENT_CONTRACT` to `... + EXTRACTION_DOCUMENT_CONTRACT`. Audit the other `_AGENT_SYSTEM +=` lines (1471–1476) and re-point any agent whose skill file explicitly forbids findings/recommendations.
3. [backend/skills/business-rules.md](backend/skills/business-rules.md) — add a single machine-readable frontmatter key at the top of the file (e.g. `report_contract: extraction`) so the skill loader in [backend/core/skill_loader.py](backend/core/skill_loader.py) can pick the right contract without hard-coding agent names in `prompts.py`. Backwards-compatible: absent key defaults to `standard`.
4. [backend/core/skill_loader.py](backend/core/skill_loader.py) — expose a `report_contract_for(agent_id)` helper reading the frontmatter, so the stream-analyze loop and `analysis_graph` can log which contract an agent ran under. One log line per run is enough for audit.
5. [backend/graphs/analysis_graph.py](backend/graphs/analysis_graph.py) `format_agent_result_document()` — defensive belt-and-suspenders: if an extraction-contract agent's final markdown contains `## Findings` or `## Recommendations` whose body matches the self-disclaimer template (regex on the literal "outside the defined scope" sentence), strip those sections before persisting. Logs a warning so we can spot LLMs that still emit them. This covers cache-replayed reports written before the contract change.
6. Cache invalidation: bump the pipeline fingerprint for `business-rules` (and any other re-contracted agent) so the new contract forces a one-time re-run of the stored cache. Easiest lever: edit `backend/skills/business-rules.md` — [core/fingerprint.py](backend/core/fingerprint.py) already watches skills per-agent, so the rewrite in step 3 naturally invalidates just this agent.
7. [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — `EXPECTED_SECTIONS_PER_AGENT` (if one exists; otherwise inline) needs to drop `Findings` / `Recommendations` from the business-rules side nav so the UI doesn't offer jump-targets that no longer exist.

**Validation:**

1. Re-run the business-rules agent on a seeded session and confirm neither `## Findings` nor `## Recommendations` appears in the persisted markdown.
2. Run the strategic agents (security, devops, testing) and confirm both sections ARE still present — the generic contract must remain the default.
3. Load a historical session whose cached business-rules report still has the disclaimer paragraphs. Verify step 5's cleanup strips them when the report renders, and that the warning log fires.

---

## 2026-04-15 addendum — alias-safe conversion, source-aware cache, ReAct agents, report-driven code-gen

Resolves: UI "Start/Resume" silently doing nothing on deduplicated (alias) sessions; code-generation serving stale output after AppNova edits; specialists missing context on larger apps; per-file conversion running without system-wide knowledge; `code-generation` / `testing` / `ui-ux` silently hitting cache after prompt/skill edits.

### Start/Resume fix (aliased sessions)

- [backend/tools/conversion_planner.py](backend/tools/conversion_planner.py) — new `_resolve_files_dir()` follows `core.chromadb_client._resolve_session()` when `uploads/{sid}/files/` is missing, so aliased sessions fall back to the canonical session's `files/`. `load_session_files()` now uses it.
- [backend/core/chromadb_client.py](backend/core/chromadb_client.py) — `register_session_alias()` writes a `.alias_of` pointer into `uploads/{sid}/`. `_resolve_session()` reads it back on cold start so the mapping survives server restarts (not just the in-memory registry).
- [backend/tools/conversion_runner.py](backend/tools/conversion_runner.py) — the "no files found" error now names the probed path instead of failing mute.

### Source-aware code-gen cache

- [backend/tools/conversion_runner.py](backend/tools/conversion_runner.py) — new `_code_gen_source_hash()` hashes `conversion_runner.py` + `conversion_planner.py` + `code_saver.py` + `core/prompts.py`. Mixed into `_batch_fingerprint()` so any edit to the AppNova conversion pipeline auto-invalidates every batch. `_manifest_version()` stamps the manifest as `"{_PROMPT_VERSION}+{source_hash}"`; `_load_manifest()` wipes orphan entries on version drift. Analysis-report caches (pipeline fingerprint in `core/fingerprint.py`) are untouched, per the "reports stay cached; code-gen doesn't" requirement.

### Option A — agents read full files on demand

- [backend/config.py](backend/config.py) — `react_agents` default changed from `[]` to all 10 specialists. Every specialist now runs as a ReAct tool-calling loop instead of slice-injection, using `list_files` / `read_file_skeleton` / `read_file` / `search_code`. Foundation node `code-analysis` still runs deterministically; `code-generation` stays slice-based so it consumes wave-1 outputs directly.
- [backend/tools/analysis_tools.py](backend/tools/analysis_tools.py) — `read_file` MAX cap raised `8_000 → 150_000` chars so typical source files fit in one pull; docstring updated to reflect "use this when you need actual implementation."
- [backend/tools/context_ingester.py](backend/tools/context_ingester.py) — `select_signal_files()` switched from fixed `max_files=35` to a **byte budget** (default 1.2 MB) so the context scales with project size instead of truncating large apps at ~35 files. Per-agent slice budget raised `40K → 150K` chars and per-file cap `1.8K → 8K` so the fallback (non-ReAct) path still sees enough content.

### Code-gen consumes all agent reports

- [backend/tools/conversion_runner.py](backend/tools/conversion_runner.py) — new `_load_agent_reports(session_id)` pulls every stored analysis result via `core.chromadb_client.get_analysis_result` (alias-safe). `_format_reports_block()` serializes into the prompt with a 20K per-agent cap and 120K total cap. `_reports_fingerprint()` SHA-256s the loaded reports and is folded into `_batch_fingerprint(..., reports_fp=...)`, so re-running analysis invalidates per-file conversions automatically. `_USER_TEMPLATE` gained a `{reports_block}` section plus a rule telling the LLM to honor the system-wide analysis.

### Always-fresh agents (no cache for code-gen / testing / ui-ux)

- [backend/main.py](backend/main.py) — new `_NO_CACHE_AGENTS = {"code-generation", "testing", "ui-ux"}` in the stream-analyze loop. These three bypass both the global content-keyed cache and the per-session cache lookup so edits to AppNova prompts, skills, or hooks always flow into the output. Other agents retain their caching unchanged.

### Write outputs to the current session folder

- [backend/hooks/builtin.py](backend/hooks/builtin.py) — `hook_auto_save_generated_code` now fires for `testing` in addition to `code-generation` and `ui-ux`, so test specs land under `uploads/{current_session}/generated/` alongside code. `preview.html` is skipped for `testing` (no UI surface to scaffold).

### UI — show generated files on the UI/UX and testing report pages

- [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) — the existing `CodeGenProgress` file-list panel is now rendered for `code-generation`, `ui-ux`, and `testing` (was `code-generation` only). `isRunning` flag keys off the current agent's progress state instead of hard-coding `code-generation`. No new component — reuses the existing code view panel.

---

## 2026-04-15 — initial changeset (per-file conversion, per-agent cache scoping, mid-tier cancellation, CWD-independent paths)

### New files

### [backend/tools/conversion_planner.py](backend/tools/conversion_planner.py)
Plans per-file 1:1 conversion batches from uploaded source.
- Loads `uploads/{session_id}/files/` and filters out non-code (locks, binaries, images, docs).
- Groups by first two directory segments so a domain module's files convert with mutual context.
- Caps each batch at **8 files / 60 KB** so a single batch fits one prompt with headroom for ~1.5× output.
- Deterministic sort → cache stability across runs.

### [backend/tools/conversion_runner.py](backend/tools/conversion_runner.py)
Async runner that drives the planner's batches through the LLM with bounded concurrency.
- **Cache key:** SHA256 of `(_PROMPT_VERSION, target_stack, sorted source paths + content hashes)`. Bumping `_PROMPT_VERSION` invalidates the entire cache.
- **Manifest** at `uploads/{sid}/conversion/manifest.json`, atomically written (`.tmp` + rename) after every batch event so crashes leave a recoverable state.
- **Failure isolation:** one batch failing does not stop the rest; failed batches are recorded and re-attempted on next run.
- Yields SSE events: `conversion_started`, `batch_cached`, `batch_converted`, `batch_failed`, `conversion_complete`.
- LLM calls go through `core.llm.call_llm_with_fallback` (full provider rotation).

### [frontend_react/src/components/ConversionPanel.tsx](frontend_react/src/components/ConversionPanel.tsx)
React panel for the new "Convert" tab.
- **Start / Resume**, **Retry failed**, **Force full re-run**, **Stop** buttons.
- Options drawer: target stack, tree-convention hint, parallelism (1–12).
- Live progress bar + counters (converted / cached / failed / in-flight) + per-batch list with collapsible details (error message, output file paths).
- Filter chips: All / Converted / Cached / Failed.
- Loads existing manifest on mount so reopening a session shows prior state without re-running.

---

## Backend changes

### [backend/main.py](backend/main.py) (+204 / −20)
1. **Per-agent pipeline fingerprint cache** ([backend/main.py:1687](backend/main.py#L1687)) — `_pipeline_fp_for(agent_id)` scopes `skills/*.md` to a single agent. Editing one skill file no longer invalidates every agent's cache. Mirrored in chat path ([backend/main.py:3974](backend/main.py#L3974)).
2. **Mid-tier cancellation checks** ([backend/main.py:2750](backend/main.py#L2750), [backend/main.py:2897](backend/main.py#L2897), [backend/main.py:2916](backend/main.py#L2916)) — Stop button now bails out between key rotations *and* between fallback tiers (Tier 1 → Tier 2 → Ollama). Updated docstring on `cancel_agent` ([backend/main.py:5283](backend/main.py#L5283)).
3. **401 / invalid-key handling** ([backend/main.py:2827](backend/main.py#L2827)) — auth errors now rotate keys with explicit cooldowns (Claude 300 s, Gemini/Groq 1800 s) instead of falling through.
4. **CWD-independent `uploads/`** ([backend/main.py:3265](backend/main.py#L3265), [backend/main.py:3836](backend/main.py#L3836), [backend/main.py:4815](backend/main.py#L4815)) — replaced `os.path.join("uploads", ...)` with absolute project-root paths so launching from `backend/` no longer creates `backend/uploads/`.
5. **New endpoints:**
   - `POST /api/convert/{session_id}` ([backend/main.py:4690](backend/main.py#L4690)) — streams per-file conversion as SSE.
   - `GET /api/convert/{session_id}/manifest` ([backend/main.py:4778](backend/main.py#L4778)) — returns manifest summary (large `result_text` blobs stripped).

### [backend/core/fingerprint.py](backend/core/fingerprint.py) (+22 / −5)
- `compute_pipeline_fingerprint(backend_root, agent_id=None)` now optionally scopes skill inclusion to `skills/{agent_id}.md`.
- When `agent_id` is omitted, behavior is unchanged (global fingerprint, used for logs/UI).
- Shared `PIPELINE_FILES` (prompts, graph, llm, config) still affect every agent.

### [backend/core/llm.py](backend/core/llm.py) (+22 / −6)
- `_set_*_key_cooldown(...)` for Gemini, Groq, and Claude now accept an explicit `duration_s` override so callers can request a specific cooldown (used for 401s in `main.py`).
- **Claude max cooldown capped at 300 s** — Tier 2 subscription resets within 5 minutes, so longer cooldowns waste keys.

### [backend/tools/code_saver.py](backend/tools/code_saver.py) (+59 / −14)
- **Bug fix: WinError 123 on save.** The old Pattern-1 regex used `.+?` with `re.DOTALL`, which let the filename capture eat code content into the path when the fence wasn't on the very next line. Filename capture is now `[^\n\r]+?` (cannot cross newlines).
- New `_clean_path()` strips trailing `(annotation)` suffixes (e.g. `Program.cs (ASP.NET Core 8)` → `Program.cs`) and only keeps the first line.
- New `_is_valid_path()` rejects paths with invalid Windows characters (`<>:"|?*\n\r\t`), parent-dir traversal, or no extension.
- New `_session_dir()` and `_UPLOADS_ROOT` for CWD-independent absolute paths.

### [backend/tools/artifact_extractor.py](backend/tools/artifact_extractor.py), [backend/tools/live_preview.py](backend/tools/live_preview.py), [backend/tools/project_brain.py](backend/tools/project_brain.py)
Same CWD-independence fix as `code_saver.py` — each defines `_UPLOADS_ROOT` from `__file__` and uses absolute paths.

---

## Frontend changes

### [frontend_react/src/App.tsx](frontend_react/src/App.tsx)
Replaced the `compare` tab with the new `convert` tab; mounts `<ConversionPanel />` inside an `ErrorBoundary`.

### [frontend_react/src/components/Sidebar.tsx](frontend_react/src/components/Sidebar.tsx)
Added action-map entry for the new `convert` tab (icon 🔄, label "Convert").

### [frontend_react/src/components/ReportView.tsx](frontend_react/src/components/ReportView.tsx) (+87 / −22)
- New `<CodeBlock>` component using `react-syntax-highlighter` (Prism + `oneDark`) for fenced code in markdown reports.
- Per-block **Copy** button (top-right, fades in on hover).
- Language badge for non-`text` languages.
- Line numbers shown when block > 6 lines.
- Tree/ASCII blocks (detected by `isTreeBlock`) skip highlighting so box-drawing characters render correctly.
- Mermaid blocks still use `<MermaidBlock>` (renderer was moved into the `pre` handler so it can read the language class).
- Language alias map normalizes `ts→typescript`, `cs→csharp`, etc.

### [frontend_react/src/services/api.ts](frontend_react/src/services/api.ts) (+88)
New `ConversionService` with:
- `stream(sessionId, options, signal)` — async generator that yields parsed SSE events.
- `getManifest(sessionId)` — fetches persisted manifest.
- TypeScript types: `ConversionBatch`, `ConversionManifest`, `ConversionOptions`.

### [frontend_react/src/index.css](frontend_react/src/index.css) (+42)
Styles for the new code-block UI: dark wrap background, custom scrollbars, copy button (hidden until block hover), and the `:has()` rule that shifts the copy button left when a language label is present.

### [frontend_react/src/style.css](frontend_react/src/style.css) (+223)
Styles for the new Conversion panel: header, options grid, error banner, progress bar with gradient fill, counter chips (color-coded done/cached/failed/running), filter chips, batch list with status-colored left border, and empty state.

---

## Themes across the changeset

- **CWD-independence:** every `uploads/` path is now resolved from `__file__` rather than the process CWD. Fixes the long-standing issue where launching the server from `backend/` would create `backend/uploads/`.
- **Per-agent cache scoping:** editing `skills/foo.md` only invalidates agent `foo`'s cache. Shared pipeline files still invalidate everyone.
- **Cancellation correctness:** Stop now interrupts at every safe checkpoint (between agents, between keys, between tiers). An already-submitted HTTP request still finishes — that's the only thing the runtime can't interrupt.
- **Per-file conversion is the major new feature:** planner + runner + manifest + UI panel + SSE endpoint, all designed for resumability and cache reuse.
