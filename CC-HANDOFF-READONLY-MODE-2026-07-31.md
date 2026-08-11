# CC-HANDOFF-READONLY-MODE-2026-07-31

**Model: Opus** — security gate on WorldTour athlete data; a silent fail-open creates false safety, which is high blast radius even though the diff is small.

**Repo:** `/Users/lukehardiman/Dev/trainingpeaks-mcp` (upstream `JamsusMaximus/trainingpeaks-mcp`, local `main` at v3.1.0)
**Branch:** create `feature/read-only-mode` off `main`. Luke handles fork remote, push, and the upstream PR — CC does code + tests only.

## Objective

Add a deterministic read-only mode to tp-mcp. When enabled, write-capable tools are never registered or listed, and any call to one is hard-rejected server-side. The guarantee must not depend on model behavior, prompts, or client settings.

## Why

This server will run against coach accounts holding 100+ professional athletes. Prompt-level guardrails are probabilistic; tool non-registration is deterministic. The patch must be written upstream-mergeable (repo style, typed, tested) — a PR will be opened after local validation, and the fork retires if it merges.

## Phase 0 — investigate and report BEFORE any code

1. Map the registration path: `src/tp_mcp/server.py` already defines `_READ_ONLY_PREFIXES` (~L1409: `tp_get_`, `tp_list_`, `tp_download_`, `tp_search_`, `tp_validate_`, `tp_analyze_`) and `_READ_ONLY_EXTRA` (`tp_auth_status`), applied ~L1464 as `read_only_hint` annotations. Confirm the single chokepoint where tools are registered AND the chokepoint where tool calls are dispatched.
2. Enumerate every registered tool and classify it with that existing predicate. Output the full two-column list (tool → available / blocked in read-only mode) in the Phase 0 report. Flag edge cases explicitly: `tp_refresh_auth`, `tp_copy_workout`, `tp_pair_workout` / `tp_unpair_workout`, `tp_apply_training_plan`, anything ambiguous.
3. Locate `serve` argument parsing in `src/tp_mcp/cli.py` and any existing env-var conventions.
4. Identify the test framework and exact run commands (README references tests/CI, ruff, mypy). Report them.

**STOP. Report findings and the tool classification list. Luke signs off before Phase 1.**

## Phase 1 — implement

1. **Activation:** `tp-mcp serve --read-only` AND env var `TP_MCP_READ_ONLY=1` (either enables it). On startup in read-only mode, log one stderr line: `READ-ONLY MODE: <N> write tools disabled.` Never log to stdout (stdio protocol).
2. **Enforcement layer 1 — registration:** in read-only mode, register only tools passing the read-only predicate. Allowlist semantics: any tool not matching the predicate — including tools added upstream in future — is excluded by default.
3. **Enforcement layer 2 — dispatch:** if a non-allowlisted tool name is called anyway (stale client cache, injection), return an explicit MCP error — `Tool disabled: server is running in read-only mode.` — with no TrainingPeaks API call made.
4. `tp_refresh_auth` falls outside the predicate and stays blocked in read-only mode — acceptable, the terminal re-auth path exists. Do not special-case it in.
5. **Tests:**
   a. Read-only `tools/list` contains zero tools failing the predicate.
   b. Dispatching `tp_create_workout` and `tp_delete_workout` in read-only mode returns the explicit error and makes no HTTP request.
   c. Default (non-read-only) mode tool list is byte-identical to `main`.
   d. A synthetic fake write tool injected in a test is excluded in read-only mode (proves allowlist, not blocklist).
6. **README:** short "Read-only mode" section in upstream style, documenting flag, env var, and the two-layer guarantee.
7. Minimal diff. No changes to auth/cookie handling, tool implementations, or anything else. Pass ruff + mypy.

## Acceptance

- Claude Desktop config `"args": ["serve", "--read-only"]`, fresh chat: write tools absent from the tool list; asking Claude to delete a workout yields tool-unavailable, not a TrainingPeaks API call.
- Full test suite green in both modes.

## Out of scope

GitHub fork/remote/PR mechanics (Luke). Coach install guide update (after validation). Windows. Any auth changes.
