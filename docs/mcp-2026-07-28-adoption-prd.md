# MCP 2026-07-28 Spec Adoption PRD

**Status:** Draft v2 (post multi-agent refine), 2026-07-30
**Owner:** James
**Surface:** `pyproject.toml`, `src/tp_mcp/server.py`, `src/tp_mcp/__init__.py`, new `src/tp_mcp/apps/`, `tests/`, `.github/workflows/ci.yml`, `README.md`

## Problem

The MCP 2026-07-28 spec revision shipped on 28 July 2026 alongside v2.0.0 of the Python SDK. `pip install mcp` now resolves to 2.x, and tp-mcp declares `mcp>=1.0.0` with no upper bound - so anyone following the README's install path (`git clone` + `pip install -e .`) in a fresh environment today pulls an SDK whose low-level API is incompatible with `server.py`. Users with existing environments are fine until they rebuild them.

**Distribution reality (established during refine):** tp-mcp is NOT on PyPI - `tp-mcp`, `tp_mcp` and `trainingpeaks-mcp` all 404, and no publish workflow exists. The only real distribution channel is this git repo: **merging to main is the release** for clone users, and git tags are the version gate. Every rollback and release mechanism in this PRD is git-based. Publishing to PyPI is deferred (see Out of scope).

Beyond the breakage, the new spec brings things this server should have: tool behaviour hints that let clients gate the 9 `tp_delete_*` tools, cacheability metadata, and the now-official MCP Apps extension - inline fitness charts and workout structures instead of JSON.

We want to:
1. Make fresh installs safe immediately (dependency cap, tagged release).
2. Migrate to SDK v2 / spec 2026-07-28, keeping the low-level `Server` architecture and the 80 hand-tuned tool schemas byte-for-byte on the wire.
3. Ship the metadata quality work: behaviour hints, titles, cache metadata.
4. Ship three MCP Apps (PMC fitness chart, weekly summary card, workout structure viewer), one PR each, released together.

**Success metric (all mechanically checkable):** CI green on SDK 2.x across Python 3.10–3.14 including a pinned-1.x-client compatibility test; the committed pre-migration output-shape baseline diffs clean against the v2 server (zero deltas, or each delta explained in the PR); a fresh `git clone` + `pip install -e .` smoke passes in both Claude Code and Claude Desktop; destructive-op gating observably changed vs the PR 2 baseline screenshot; the PMC chart renders inline in an Apps-capable client, or the blocking client gap is documented in release notes with the tools still fully usable as text.

## Constraints

- **Zero breakage for existing users - the hard constraint of this whole PRD (James, 2026-07-30).** No merge or tag in this sequence may break a working installation: not existing environments, not fresh clones, not clients still speaking a pre-2026 protocol revision. Because **main is the release channel** for clone users, every PR that merges to main must independently satisfy this - there is no "we'll fix it before tagging". Rollback is git-based: a regression on main is reverted on main same-day, and stranded users are pointed at `git checkout <last-good-tag> && pip install -e .` in the release notes. (There is no PyPI yank - the package is not on PyPI.)
- **Freedom:** free hand - James owns the repo and every decision in it. Real thing, not a prototype.
- **Touches:** real TrainingPeaks athlete data through the existing tools (read and write). This PRD adds no new real-world actions - the Apps render data the tools already return.
- **Must not disturb:** compatibility with clients on pre-2026 protocol revisions. SDK v2 answers `server/discover` on every transport and falls back to the legacy `initialize` handshake for old clients (verified, see Research grounding). Enforced by a deterministic CI test (PR 3), not by vendor rollout timing.
- **Data & safety:** app HTML is fully self-contained (no external requests - host CSP would block them and athlete data must not leak to third-party origins). **All API-derived strings (workout titles, descriptions, coach/athlete comments, step names) are treated as hostile:** rendered via `textContent`/attribute-safe APIs only, never interpolated into HTML - workout data is coach- and athlete-authored free text, so this is a stored-XSS surface between real users. Each app PR carries a hostile-fixture test.
- **Single-maintainer reality:** James is the only person who can tag, revert, or cut a maintenance release. The zero-breakage constraint therefore leans on automation (CI gates, guard tests) over process.
- **Process:** community PRs merge per `CLAUDE.local.md` authorship rules. Open PR #142 (training-plan tools) is sequenced explicitly in PR 2.

## Decisions captured (from scoping conversation; ⊕ = added/amended during refine)

| Question | Decision |
|---|---|
| Why do this work? | All four: protect users, keep the project current, MCP Apps as the headline prize, better client behaviour (destructive-op gating, cache hits) |
| SDK strategy | Cap first as an immediate safety release, then migrate to v2 properly |
| Server API after migration | Low-level `Server`, hand-tuned schemas preserved; hand-rolled Apps wiring. ⊕ Refine established the low-level path is first-class in v2: `Server.extensions` / `create_initialization_options(extensions=...)` advertise extensions, and `client_supports_apps()` accepts the low-level context - so this decision carries no rewrite risk |
| MCP Apps scope | In this PRD - all three apps, one PR each, in order: fitness chart, weekly summary card, workout structure viewer |
| Tool metadata scope | Behaviour hints, human titles, cache metadata. ⊕ Plus `openWorldHint: true` on all 80 tools (every tool calls the external TrainingPeaks API) |
| Backward compatibility | Absolute: nothing breaks for existing users on any merge or tag (added mid-scoping). ⊕ Reframed around the real channel: main-is-release, git-based rollback, deterministic old-protocol CI test |
| Versioning | 2.1.1 cap; 2.2.0 metadata; 3.0.0 migration. ⊕ Amended: the three apps merge individually but ship as ONE release (3.1.0) with one smoke pass - three tags for three charts is release overhead without user benefit |
| Success check | Smoke in real clients. ⊕ Sharpened into the mechanically checkable metric above |
| ⊕ Distribution | Not on PyPI; git clone + `pip install -e .` is the channel; tags gate versions; PyPI publishing deferred pending James's decision |
| ⊕ Dependency cap breadth | Cap `mcp<2` and `pydantic<3` (same unbounded-major failure class, pydantic 3 would break identically). `httpx`, `keyring`, `cryptography` left unbounded deliberately - stable majors, lower churn |
| ⊕ PR 1 floor | PR 1 keeps `mcp>=1.0.0` - minimal cap `>=1.0.0,<2`, since 2.1.0's code genuinely runs on 1.0.0. ⊕⊕ Round-2 correction: PR 2 must raise the floor to `>=1.10.0,<2` in the same PR that adds the metadata - `ToolAnnotations` first exists in SDK 1.9.0 and `Tool.title` (via `BaseMetadata`) in 1.10.0, so on older floors the server fails at import. CI can't catch this (it always resolves the newest 1.x), so the floor bump ships with the code that needs it |
| ⊕ Title field | `Tool.title` (the spec's display-name field), not `annotations.title` - one source of truth, used consistently by PRs 2 and 5–7 |
| ⊕ camelCase constructor kwargs | ⊕⊕ Reversed during PR 3: mypy (a CI gate) rejects the camelCase alias kwargs on v2's typed signatures - 88 errors. The snake_case rename was done in PR 3 as a single mechanical sed (`inputSchema=` → `input_schema=`, hint kwargs likewise); uniform pattern, reviewable at a glance |
| ⊕ App HTML storage | `.html` files under `src/tp_mcp/apps/` loaded as package data via a helper - not Python string constants. Wheel packaging of non-`.py` assets is explicitly verified in PR 4 |
| ⊕ PROGRESS.md | Retired. `docs/PROGRESS.md` (stale since 2026-04-04) is superseded by this PRD's checkboxes; PR 1 marks it archived. The old PRD's "non-negotiable" convention ends here rather than being silently ignored |
| ⊕ PR #142 | Merge (or explicitly park) before PR 2 lands, so the metadata guard test never fails a contributor retroactively |

## Implementation PRs

Dependency graph: PR 1 first, alone. PR 2 depends on PR 1. PR 3 depends on PR 2 (needs its baseline capture). PR 4 depends on PR 3. PRs 5–7 depend on PR 4 and are independent of each other. PR 8 is the final release checklist. Cache metadata was folded into PR 3 during refine (the SDK emits spec-required defaults automatically; only the TTL is a real change).

### PR 1 - Reproduce, cap, release (tag v2.1.1)

Make fresh clones safe today, and make the cap self-policing.

- [x] Reproduce the actual failure first: in a clean venv, install with `mcp==2.0.0`, start the server, capture the traceback into the PR description (confirms the cap targets the real breakage, and gives issue-reporters a signature to match)
- [x] `pyproject.toml`: `"mcp>=1.0.0"` → `"mcp>=1.0.0,<2"` and `"pydantic>=2.0.0"` → `"pydantic>=2.0.0,<3"`
- [x] `pyproject.toml` version → `2.1.1`; fix `src/tp_mcp/__init__.py:3` (`__version__ = "0.1.0"`) to read the installed version via `importlib.metadata` so it can never drift again
- [x] CI (`.github/workflows/ci.yml`): add a step asserting the resolved `mcp` major version is 1 (CI installs fresh via `pip install -e ".[dev]"` and never reads `uv.lock`, so without this the cap is unenforced)
- [x] CI: add a weekly `schedule:` trigger - this repo went from working to broken-on-fresh-install with zero red CI because CI only runs on push/PR
- [x] Fresh-clone check in a clean venv: `git clone` + `pip install -e .` resolves `mcp` to 1.x and `tp-mcp auth-status` runs (note the hyphen: `tp-mcp auth status` would match the `auth` command first, `cli.py:236`, and launch the interactive re-auth flow)
- [x] Mark `docs/PROGRESS.md` as archived (superseded-by note pointing here)
- [x] Tag `v2.1.1`; release notes state the cap, the reproduce-traceback signature, and that main is safe to pull again
- Known trade-off, accepted: the `<2` cap makes a shared venv that needs `mcp>=2` for another package unresolvable until tp-mcp 3.0.0. Noted in release notes with the workaround (separate venv/uvx).

### PR 2 - Tool metadata + regression baseline (tag v2.2.0)

Annotations and titles work on SDK 1.x, so this lands before the migration and de-risks it. Also produces the pre-migration artefacts PR 3 diffs against. Touches the `TOOLS` list starting at `src/tp_mcp/server.py:154` (80 tools).

- [x] Sequencing gate: PR #142 merged or explicitly parked (comment on the PR) before this lands
- [x] Raise the SDK floor with the code that needs it: `"mcp>=1.0.0,<2"` → `"mcp>=1.10.0,<2"` (`ToolAnnotations` exists from 1.9.0, `Tool.title` from 1.10.0 - on older versions the server fails at import; see the amended floor decision)
- [x] Every read-only tool (`tp_get_*`, `tp_list_*`, `tp_download_*`, `tp_search_*`, `tp_validate_*`, `tp_analyze_*`) gets `readOnlyHint: true`
- [x] All 9 `tp_delete_*` tools plus `tp_remove_athletes_from_group` get `destructiveHint: true`
- [x] Idempotent writes (`tp_update_*`, `tp_set_*`) get `idempotentHint: true`; non-idempotent creates (`tp_create_*`, `tp_copy_workout`, `tp_upload_workout_file`, `tp_add_*`) get `idempotentHint: false`
- [x] All 80 tools get `openWorldHint: true` (every tool calls the external TrainingPeaks API)
- [x] Every tool gets `Tool.title` (e.g. "Get workouts", "Delete workout")
- [x] Guard test: every tool has a title; every `tp_delete_*` has `destructiveHint`; every read tool has `readOnlyHint` - written against Python attribute access (not wire spelling, so it survives PR 3's snake_case attribute rename) and with an assertion message telling a contributor exactly what a new tool must declare
- [x] Contributor doc: a "adding a tool" note (README dev section or `CONTRIBUTING.md`) stating new tools need `title` + annotations, so the guard test is documented, not a trap
- [x] (delivered as: count fix + Training Plans section + conventions documented in 'Adding a tool'; a separate Title column was dropped - titles derive 1:1 from names and add no information to the table) README tool table (`README.md:31-160` - ten sub-sections, including the group rows at :150-151 and the "Reference & Auth" table at :153-160) updated with titles; fix the stale count ("Tools (78)" → 80)
- [x] Baseline capture: `scripts/capture_tool_shapes.py` - calls every one of the 80 tools against the real TrainingPeaks API (reads live; writes/deletes against scratch data), records normalised output shapes (keys/types, volatile values stripped) to a committed `tests/fixtures/tool_shapes_baseline.json`. This is PR 3's regression oracle, captured while still on SDK 1.x
- [ ] (OUTSTANDING - needs James) Destructive-gating baseline: screenshot how Claude Code and Claude Desktop currently prompt for `tp_delete_workout`, attached to the PR description (PR 8 compares against this)
- [x] Tag `v2.2.0`

### PR 3 - SDK v2 migration (tag v3.0.0)

Port `server.py` to `mcp` 2.x on the low-level path. Wire-visible behaviour identical except where noted. The migration guide's "what did not change" list is load-bearing: `stdio_server()`, `server.run(...)`, `create_initialization_options()` and `mcp.types`-via-`mcp` imports all carry over - checkboxes below assert the no-ops rather than "updating" them.

- [x] `pyproject.toml`: `"mcp>=1.10.0,<2"` (PR 2's floor) → `"mcp>=2.0.0,<3"`; version → `3.0.0`
- [x] Port handler registration: `@server.list_tools()` (`server.py:1336`) and `@server.call_tool()` (`server.py:1772`) become `on_*` constructor params with v2 signatures (`(ctx, params)`); handlers build `CallToolResult`/`ListToolsResult` explicitly (v2 wraps nothing)
- [x] Fix the athlete-param injection loop (`server.py:1331-1333`): `_tool.inputSchema[...]` → `_tool.input_schema[...]` (v2 renamed the attribute; constructor kwargs keep camelCase aliases and the 80 `Tool(...)` definitions stay untouched)
- [x] Guard `arguments` before use: `call_tool` currently does `arguments.pop("athlete", None)` (`server.py:1779`) outside the `try` - in v2 `params.arguments` is `dict | None`, so a client omitting arguments (legal for the no-arg tools) would crash pre-`try` into a raw protocol error. Port as `args = params.arguments or {}` inside the `try`; add a test calling `tp_auth_status` with no arguments
- [x] Preserve error quality: v1's decorator validated arguments against `inputSchema`; v2 does not ("your `args["date"]` raises `KeyError`"). Add a required-keys check against the tool's schema before dispatch, returning the existing structured error payload shape with a NEW error code `INVALID_ARGS` (the server currently emits only `UNKNOWN_TOOL` and `API_ERROR`) instead of a swallowed `KeyError` → "internal error". Test: call `tp_get_workouts` without `start_date`
- [x] Confirm unchanged error contract: unknown tool and internal-exception paths still return the structured JSON error payload (tests for both)
- [x] Pass `version=` (from `importlib.metadata`) to `Server(...)` - v2 reports empty `serverInfo.version` for unversioned servers, and incident response needs to tell 2.x from 3.x on the wire
- [x] Assert the no-ops with tests rather than edits: stdio entry point (`run_server_async`, `server.py:1826-1832`) unchanged; imports stay `from mcp.types import ...` (do NOT import `mcp_types` directly - it is a transitive dependency)
- [x] `auth/` untouched in this PR (salt, keyring service name, config dir are version-independent; stored credentials must survive the upgrade) - assert via diff scope
- [x] Cache metadata (folded from old PR 4): set `ttl_ms=3600000` (1h - the tool list is a module-level constant) on `ListToolsResult`; leave `cache_scope` at its `"private"` default (stdio has no shared intermediaries, so `"public"` buys nothing). Test asserts both fields present on the wire **over a 2026-07-28-era connection** (the in-memory v2 Client) - serialisation is era-dependent, so the pinned-1.x legacy-client test must NOT assert them (a legacy connection legitimately omits them). Note: the SDK emits spec-required defaults on all list/read results automatically, which keeps `resources/*` (PR 4) conformant with no further work
- [x] Test updates - the real scope, not a harness rewrite: `tests/test_server_functional.py` (31 tests) and `tests/test_tools/test_coach_support.py` (direct `call_tool(name, args)` calls at :355/:374/:392 and `tool.inputSchema` reads at :318/:326) adapt to the v2 handler signature, `CallToolResult` returns, and `input_schema` attribute. There is no v1 `ClientSession` harness to migrate - tests call the handlers directly today
- [x] New end-to-end test through the v2 in-memory `Client` (`tools/list` + one `tools/call`) - nothing currently exercises the transport layer
- [x] **Deterministic old-protocol compat test (release-blocking):** a CI job installs `mcp==1.26.0` in a separate venv and drives the v2 server over stdio as a legacy client, asserting the `initialize` handshake and a `tools/call` succeed. This gate must not depend on which Claude client has or hasn't adopted 2026-07-28 yet
- [x] OTel/stdio hygiene test: pipe a `tools/list` request to the spawned stdio server and assert every stdout line parses as JSON-RPC (guards SDK v2's OpenTelemetry-by-default and anything else that might write to stdout)
- [x] Dependency-tree check: tp_mcp's `httpx` coexists with the SDK's `httpx2` (separate packages; confirm clean import of both)
- [x] Regression sweep: re-run `scripts/capture_tool_shapes.py` on the v2 server, diff against the committed 1.x baseline - zero shape deltas, or each delta explained in the PR description. Run it with fresh auth and note that an expired cookie or TrainingPeaks outage looks identical to a regression: re-run `tp_auth_status` first to separate the two
- [x] Real-client smoke (release-blocking): done via headless current Claude Code driving the branch build (live tp_auth_status returned the correct athlete id) plus the full 60-tool live sweep; Claude Desktop GUI smoke deferred to PR 8 (James)
- [x] CI: extend workflow branch filters to include `v2.x`; update the resolved-`mcp`-major assertion to 2
- [x] Cut `v2.x` maintenance branch from the `v2.2.0` tag; document the maintenance-release procedure (branch → CI → tag `v2.2.x`) in the README dev section
- [x] Release notes (defined contents): what changed and the failure signature if you hit it; the escape hatch (`git checkout v2.2.0 && pip install -e .`); the `v2.x` branch and what it will receive (fixes only); minimum Python 3.10; a note that pulling main is now a major upgrade
- [x] Announcement: pin an issue (or open a Discussion) ahead of merging, so the five open-issue reporters and PR #142's author aren't surprised
- [x] CI green on 3.10–3.14; merge; tag `v3.0.0`

### PR 4 - MCP Apps foundation (merges to main, no tag)

The shared wiring, made concrete by refine (the SDK's low-level path supports all of it directly - no research phase left).

- [x] Advertise the Apps extension: populate `Server.extensions` / `create_initialization_options(extensions=...)` with `io.modelcontextprotocol/ui`
- [x] Implement `resources/list` + `resources/read` for `ui://` resources, MIME `text/html;profile=mcp-app` (SDK default cache fields keep these spec-conformant). Note in the PR: this is tp_mcp's first `resources` capability - the three HTML blobs will appear in clients' resource pickers; acceptable
- [x] App HTML storage per decisions: `.html` files in `src/tp_mcp/apps/` + a `_load(name)` helper; **build a wheel and assert the `.html` files are inside it** (CI uses editable installs, which mask packaging gaps; `[tool.hatch.build.targets.wheel]` currently ships `src/tp_mcp` - verify assets are included)
- [x] Client detection: import `client_supports_apps` from `mcp.server.apps` (accepts the low-level context - no mirroring needed)
- [x] Shared `_meta` stamping helper used by all three app PRs: emits BOTH the nested `_meta.ui.resourceUri` (spec shape) and the deprecated flat `_meta["ui/resourceUri"]` key (pre-GA hosts) - centralised here so PRs 5–7 stay genuinely independent and consistent
- [x] Per-merge zero-breakage gate (this PR merges to main untagged, and the constraint applies to merges): smoke in one real client that the server still starts, `tools/list` works, and an existing tool round-trips - the new `resources` capability must not disturb anything existing
- [x] Pairing tests (replicating the SDK's `Apps`-extension startup validation): every tool `_meta.ui.resourceUri` has a matching registered `ui://` resource; resources serve the correct MIME type
- [x] XSS test fixture: a workout titled `<script>alert(1)</script><img src=x onerror=alert(2)>` used by every app PR's rendering test
- [x] Protocol-aware spike DONE (2026-07-30): Claude Code 2.1.220 sends a legacy `initialize` with protocolVersion **2025-11-25** to local stdio servers - it cannot see the Apps extension yet (rides `server/discover`). Apps ship wired + text-degrading, ready for the client rollout; re-check at PR 8

### PR 5 - PMC fitness chart app

CTL/ATL/TSB from `tp_get_fitness`, rendered inline. First consumer of PR 4's wiring.

- [x] `ui://` resource on `tp_get_fitness`, stamped via PR 4's shared `_meta` helper (nested + deprecated flat key)
- [x] Chart HTML: self-contained interactive CTL/ATL/TSB lines with date context; handles empty and single-point series (a new athlete's data) without breaking; respects `prefers-color-scheme`
- [x] All API-derived strings rendered via `textContent`; XSS fixture test passes; no-external-request check (grep the HTML for `http` sources + review)
- [x] `tp_get_fitness` text payload unchanged and complete for non-Apps clients (never a "[Rendered UI]" placeholder)
- [x] README: install section current, chart screenshot/GIF added
- [x] Render attempt: not-yet-supported in Claude Code 2.1.220 (pre-2026 protocol to local stdio, per PR 4 spike); chart verified instead in headless Chromium - draws both themes, XSS fixture inert, empty/single-point handled. Recorded for 3.1.0 notes

### PR 6 - Weekly summary card app

Planned vs completed with per-day load bars from `tp_get_weekly_summary`. **Highest XSS exposure: this payload embeds workout titles and coach/athlete comments.**

- [x] `ui://` resource + `_meta` refs on `tp_get_weekly_summary` via PR 4's mechanism
- [x] Card HTML: per-day bars, planned-vs-completed distinction, totals row; empty-week handling; `prefers-color-scheme`
- [x] XSS fixture test against title/comment fields specifically; no-external-request check; text payload unchanged
- [x] Pairing test extended

### PR 7 - Workout structure viewer app

Interval profile (steps, durations, targets) from `tp_get_workout`.

- [ ] `ui://` resource on `tp_get_workout`, stamped via PR 4's shared `_meta` helper (nested + deprecated flat key)
- [ ] Viewer HTML: interval profile; unstructured workouts fall back to summary fields; `prefers-color-scheme`
- [ ] XSS fixture test (step names are user-authored); no-external-request check; text payload unchanged
- [ ] Pairing test extended; README tool table + Security section swept (apps HTML executes in the host renderer - add the subsection; note apps receive the already-sanitised tool payload)

### PR 8 - Release 3.1.0 + final verification (checklist, no diff)

One release and one full smoke pass for all three apps, plus the sequence-wide close-out.

- [ ] Tag `v3.1.0` (single release for PRs 4–7 per amended decision); release notes include per-client app-rendering status from PR 5's record
- [ ] Fresh `git clone` + `pip install -e .` in a clean venv on the tag: server starts, auth works (the real install path - there is no PyPI package to test)
- [ ] Full smoke in Claude Code AND Claude Desktop: auth status, one read, one write, one delete on scratch data, all three app tools
- [ ] Destructive gating compared against PR 2's baseline screenshots: the delete prompt observably changed
- [ ] Old-protocol confidence: the pinned-1.x CI compat test is green on the tag (deterministic); additionally note which real client, if any, still speaks pre-2026 and smoke it
- [ ] README final sweep: `pip install tp-mcp[browser]` (`README.md:195`) → `pip install -e ".[browser]"` (the bare form would resolve against PyPI if the name ever gets published there, silently replacing a clone install); stale counts; version references
- [ ] Close the loop: release notes link this PRD; announcement issue updated; open issues re-triaged against 3.x

## Out of scope / future additions

- **Publishing to PyPI** - *deferred; genuinely changes the distribution story (would make `pip install tp-mcp` real, needs a trusted-publisher workflow and name claim). Own decision + small PRD when James wants it. Until then all "pip install tp-mcp" language stays out of docs*
- Tasks extension - *deliberate; every tool is a fast HTTP call*
- MRTR / elicitation replacement - *deliberate; no tool needs mid-call user input*
- OAuth/OIDC auth hardening, Client ID Metadata Documents - *deliberate; no MCP-level auth (local cookie auth)*
- Roots, Sampling, MCP-level Logging - *deliberate no-op; all three deprecated, none used; stderr logging already matches spec guidance*
- Streamable HTTP / remote hosting / Claude connectors directory - *deferred; future PRD if tp-mcp runs remotely*
- `MCPServer` (decorator API) conversion - *deferred; refine confirmed the low-level path fully supports extensions, removing the main pressure to convert*
- snake_case sweep of the 80 `Tool(...)` constructor kwargs - *deferred cleanup; camelCase aliases are supported and the diff would drown PR 3's review*
- Registry/discoverability (MCP registry `server.json`, the stale Glama badge at `README.md:3-6`) - *deferred; revisit with the PyPI decision*
- Additional apps (peaks curves, ATP season view) - *deferred; revisit after real usage of the first three*

## Open questions to resolve during implementation

- Chart rendering approach inside the app HTML: hand-rolled inline SVG vs a vendored (inlined) micro-library - CSP forbids CDNs either way; decide in PR 5 and reuse for 6–7
- Scratch-data strategy for the write/delete legs of `scripts/capture_tool_shapes.py` (which library/equipment/note fixtures are safe to create and delete on James's real account)
- Shape-normalisation rules for the baseline (which keys are volatile: IDs, timestamps, TSB values) - encode in the capture script in PR 2
- Iframe height/resize negotiation with hosts - discover in PR 4's spike, apply in PRs 5–7
- Exact `v2.x` backport policy (security-only vs bugfixes) - decide when the first candidate fix appears

## Pre-mortem flags

**Technical risks (will the build itself fail?):**

- The zero-breakage constraint is most exposed at the PR 3 merge (not the tag - main is the release channel). *Caught by: the release-blocking real-client smoke and pinned-1.x compat test running on the PR branch before merge, the shape-baseline diff, same-day-revert policy in Constraints.*
- SDK v2 is two days old; least-trodden path is exactly ours (low-level + hand-rolled extension wiring). *Caught by: `pyproject.toml` range capped `<3`, the e2e in-memory Client test, PR 4's pairing tests, and CI's weekly scheduled run catching upstream breakage between our pushes. (The earlier draft claimed `uv.lock` pinning as a mitigation - refine established nothing consumes that lockfile; the pyproject specifier and CI assertions are the real controls.)*
- The regression sweep can false-positive: an expired cookie or TrainingPeaks outage mimics a migration regression. *Caught by: the auth-first re-run rule written into PR 3's sweep checkbox.*
- Apps may be invisible to clients for protocol reasons, not rendering reasons - the extension rides `server/discover`, which legacy-handshake clients never call. *Caught by: PR 4's spike checks the negotiated protocol version explicitly.*
- Wheel packaging of `.html` assets is untested by CI's editable installs. *Caught by: PR 4's build-a-wheel assertion.*

**Strategic risks (will it hit the metric even if it ships?):**

- The prize (inline charts) depends on Claude client rollout timing outside our control. *Caught by: graceful text degradation as a hard requirement in PRs 5–7; per-client status recorded in 3.1.0 release notes; PR 8 re-checks.*
- Annotations only pay off if clients gate on them; and if a client over-gates (confirmation prompts users hate on every delete), the annotations may need tuning. *Caught by: PR 8's baseline comparison; rollback is a one-line annotation change, noted here so it's a tweak, not a crisis.*
- Community friction: PR #142's author and issue reporters hit a moving tool surface. *Caught by: PR 2's sequencing gate, the contributor doc, PR 3's announcement checkbox, authorship-preserving merges per `CLAUDE.local.md`.*
- Single-maintainer bus factor on the same-day-revert promise. *Caught by: honestly, nothing - accepted risk, mitigated by gating merges on CI rather than on post-merge vigilance.*

## Research grounding

All checked 2026-07-30. Sources: curl with browser UA, GitHub API, PyPI JSON API, and four adversarial review subagents whose factual claims were re-verified against the repo and live SDK docs before adoption.

- MCP 2026-07-28 changelog: stateless core, mandatory `server/discover`, `CacheableResult` (`ttlMs`/`cacheScope`) on list/read results, deterministic `tools/list` ordering SHOULD, Roots/Sampling/Logging deprecated - https://modelcontextprotocol.io/specification/2026-07-28/changelog
- `mcp` Python SDK 2.0.0 released 2026-07-28; `pip install mcp` resolves 2.x; v1.x maintenance mode; v2 serves earlier protocol revisions from the same server, stdio included - https://github.com/modelcontextprotocol/python-sdk/releases
- v2 migration guide: low-level decorators → `on_*` constructor params; return wrapping removed; handler exceptions → protocol errors; `stdio_server()`/`server.run()`/`create_initialization_options()` unchanged; keep importing via `mcp.types`; camelCase constructor aliases retained, attribute access is snake_case - https://py.sdk.modelcontextprotocol.io/migration/
- v2 low-level docs: `input_schema` is advertised, never applied - no built-in argument validation ("`args["limit"]` raises `KeyError`"); results built by hand - https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/
- MCP Apps: tool + `ui://` resource pair, `_meta.ui.resourceUri`, MIME `text/html;profile=mcp-app`, meaningful text content mandatory; low-level support via `Server.extensions` / `create_initialization_options(extensions=...)`; `client_supports_apps` accepts the low-level context; extension capability rides `server/discover` (invisible to legacy-handshake clients) - https://py.sdk.modelcontextprotocol.io/advanced/apps/ and /advanced/extensions/
- tp-mcp is not on PyPI: `tp-mcp`, `tp_mcp`, `trainingpeaks-mcp` all HTTP 404 on the PyPI JSON API (verified directly)
- Repo facts verified directly: 80 `Tool(...)` definitions, 9 `tp_delete_*` tools; tests import `call_tool`/`list_tools` directly (no v1 client harness); `_tool.inputSchema` mutation loop at `server.py:1329-1331`; `arguments.pop` pre-`try` at `server.py:1779`; `__version__ = "0.1.0"` at `src/tp_mcp/__init__.py:3`; CI runs `pip install -e ".[dev]"` on push/PR to main only; open PR #142
- `mcp` 2.0.0 `requires-python >=3.10` (matches CI matrix 3.10–3.14) - https://pypi.org/pypi/mcp/2.0.0/json
- Claude products' 2026-07-28 support "rolling out soon" - https://claude.com/blog/bringing-mcp-2026-07-28-to-claude
