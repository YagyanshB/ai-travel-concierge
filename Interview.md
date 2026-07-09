# ATHENA — AI Engineer Interview Prep Guide

Your complete study companion for the NHS AI Research Assistant assessment. Read this
end to end once, then use the Q&A bank and the "change it at will" cookbook to drill.

> **Golden rule for the interview:** you didn't build "an LLM wrapper." You built a
> **governed tool-execution platform** where an LLM is the *planner* and an MCP server
> is the *enforcer*. Everything below reinforces that one sentence.

---

## 0. 60-Second Elevator Pitch (memorise this)

> "ATHENA lets NHS researchers ask questions in plain English and get traceable,
> governed answers. It's three layers: a REST API takes the question; an AI agent
> (GPT-4o with a ReAct-style function-calling loop) decides *which* tools to call and
> in what order; and an MCP server actually *executes* those tools and *enforces*
> governance — rate limits, tiered access, PII blocking, small-number suppression, and
> a full audit trail. The key design principle is that **governance lives in the MCP
> server, not the agent** — so even a client that bypasses the AI still can't break the
> rules. Every response also ships with full observability: token cost, timings,
> per-tool telemetry, the decision chain, and an anti-hallucination grounding check."

If you say only that, you've already covered ~40% of what they'll ask.

---

## 1. The Mental Model — how a request actually flows

Trace a single request: `POST /query {"question": "What datasets exist for diabetes?", "researcher_id": "diana"}`

1. **`agent/src/api.ts`** receives the POST. Validates the `question`, generates an
   8-char `trace_id`, and looks up the researcher profile from `researchers.json`
   (`lookupResearcher`). Calls `agent.ask(question, researcher)`.

2. **`agent/src/agent.ts` → `ResearchAgent.ask()`** runs the **ReAct loop**:
   - Builds a system prompt (+ optional researcher personalisation).
   - Calls OpenAI Chat Completions with the full tool catalogue and `tool_choice: "auto"`.
   - If the model returns `tool_calls`, the agent executes each one against the MCP
     server, appends the results to the message history, and **loops again**.
   - If the model returns plain content (no tool calls), that's the final answer and
     the loop exits.
   - Hard cap: `MAX_ITERATIONS` (default 10) to prevent infinite loops.

3. **`agent/src/mcp-client.ts`** is how the agent talks to tools. On startup it spawns
   the MCP server as a **child process** over **stdio** and calls `listTools()`. Each
   `callTool(name, args)` is a JSON-RPC round trip to that child process.

4. **`mcp-server/src/index.ts`** is the MCP server. It registered all 14 tools
   (`registerAllTools`) against a hardcoded `currentSession` (Diana, Tier 2). Each tool
   runs **governance checks first**, then the business logic, then writes an
   **audit entry**, then returns human-readable text.

5. Back in the agent: after the final answer, two post-processing passes run:
   - **`groundAnswer()`** — regex-checks that numbers/IDs in the answer actually appear
     in the tool outputs (anti-hallucination).
   - **`extractSourcesFromResults()`** — pulls `DS###`/`PRJ###` IDs out of the tool
     result text to populate the `sources` array.

6. **`api.ts`** assembles the JSON response (`answer`, `sources`, `trace_id`,
   `grounding`, `researcher`, `observability`) and stores an in-memory `AuditRecord`
   (last 100) retrievable via `GET /audit/:traceId`.

**The one diagram to draw on a whiteboard:**

```
Researcher → [REST API] → [Agent: ReAct loop w/ GPT-4o] ⇄ [MCP Client]
                                                              ↕ stdio (child process)
                                                          [MCP Server]
                                                              ├─ Governance checks
                                                              ├─ Tool business logic
                                                              └─ Audit log
```

---

## 2. File-by-File Map (so you can navigate and change at will)

### `agent/` — the AI orchestration layer (the "brain")

| File | What it does | When you'd touch it |
| --- | --- | --- |
| `src/api.ts` | Express REST API. Endpoints, researcher lookup, audit store, response shaping. | Add endpoints, add auth, change response format. |
| `src/agent.ts` | **The core.** ReAct loop, system prompt, cost estimation, grounding, source extraction, observability assembly. | Change agent behaviour, prompt, model, telemetry. |
| `src/mcp-client.ts` | Wraps the MCP SDK client. Spawns the server over stdio, `listTools`/`callTool`. | Swap transport, change how tools are discovered. |
| `src/index.ts` | Interactive CLI (REPL) + single-question mode. | Local debugging without HTTP. |
| `src/run.ts` | One-shot runner that prints JSON. Good for CI/scripting. | Automated testing hooks. |

### `mcp-server/` — the tool + governance layer (the "hands + rules")

| File | What it does | When you'd touch it |
| --- | --- | --- |
| `src/index.ts` | MCP server entry (stdio). Registers tools + resources, defines the hardcoded session. | Change the "logged-in user", add resources. |
| `src/http-server.ts` | Alternative MCP entry over HTTP/SSE. Not used by the agent by default. | Expose MCP to external/web clients. |
| `src/tools/research.ts` | `searchProjects`, `searchDatasets`, `getProjectDetails`, `submitQuery`, `getQueryStatus`. | Add discovery/query tools. |
| `src/tools/data-exploration.ts` | `previewDataset`, `listColumns`, `explainDataset`, `validateQuery`. | Add data-inspection tools. |
| `src/tools/governance.ts` | `getAuditTrail`, `getRateLimit`, `listGovernancePolicies`, `listResearchers`, `getResearcher`. | Add governance-visibility tools. |
| `src/tools/index.ts` | The registry — wires all tool groups onto a server. | Register a new tool module. |
| `src/governance.ts` | **Policy registry + enforcement functions**: rate limit, access tier, classification, PII patterns, suppression, approval, audit logging. | Add/modify a governance rule. |
| `src/validation.ts` | Deep query validation (PII regex, column checks, aggregation heuristics). Powers `validateQuery`. | Improve query safety checks. |
| `src/data.ts` | Loads JSON, transforms raw → domain types, seeds audit log + analytical queries, **fuzzy ID/name resolution**. | Change data model, add resolution logic. |
| `src/data-access.ts` | Schema/column metadata engine (`COLUMN_METADATA`), preview rows, `explainDataset`. | Add columns, enrich schema. |
| `src/types.ts` | Domain types (`ResearchProject`, `ResearchDataset`, `UserSession`, etc.). | Shared type changes. |
| `data/*.json` | 20 datasets, 20 projects, 15 researchers, sample query results. | Change the demo data. |

### Root — deployment

| File | Purpose |
| --- | --- |
| `Dockerfile` | Single image: installs both packages, runs `tsx agent/src/api.ts` (which spawns the MCP server internally). |
| `docker-compose.yml` | One-command run with env passthrough + healthcheck. |
| `env.example` | Documents env vars. |
| `README.md` | The public architecture doc. |

---

## 3. Design Decisions — the "why", the alternatives, the trade-offs

This is the meat of the interview. For each decision, know **(a) what you chose, (b) what
you rejected, (c) the trade-off you accepted.**

### 3.1 Why MCP instead of hardcoding tool logic into the agent?

- **Chose:** Model Context Protocol — a standard client/server tool interface.
- **Rejected:** Putting `if question mentions datasets → query the array` logic directly in the agent.
- **Why it wins:**
  - **Separation of concerns** — the agent *reasons*, the server *executes and enforces*.
  - **Governance can't be bypassed.** Rules live server-side, so any MCP client (Claude
    Desktop, Cursor, a script) is still governed. This is the security-critical point for NHS.
  - **Independently testable** — test tools with no LLM; test the agent with mock tools.
  - **Swappable LLM** — change GPT-4o → Claude → local model without touching the server.
  - **Standardisation** — MCP is becoming the industry-standard tool protocol, so tools are reusable.
- **Trade-off accepted:** an extra process + protocol layer and some latency vs. a monolith.

### 3.2 Why native OpenAI function calling instead of LangChain / LangGraph / CrewAI?

- **Chose:** ~80 lines of hand-written ReAct loop over the OpenAI SDK.
- **Rejected:** an agent framework.
- **Why it wins:**
  - **MCP already *is* the tool abstraction** — a framework would be a redundant layer over it.
  - **Full observability** — because *we* own the loop, we capture every token, timing, and decision. Frameworks hide this.
  - **Tiny dependency surface** — 2 core deps vs. 50+. Easier for NHS security to audit.
  - **No lock-in / no magic** — you can explain every line, which matters in a regulated setting.
- **Trade-off accepted:** you re-implement things frameworks give free (retries, streaming, memory). Fine at this scale; you'd reconsider for complex multi-agent graphs.
- **Great line:** *"Frameworks are worth it when orchestration is the hard part. Here the hard part was governance and traceability, and a framework would have obscured both."*

### 3.3 Why stdio transport between agent and server (not HTTP)?

- **Chose:** stdio — the agent spawns the server as a child process.
- **Why:** zero network config, single-container deploy, lower latency (no HTTP overhead), process-isolated.
- **Trade-off:** one server per agent process → doesn't scale horizontally as-is. The
  `http-server.ts` (SSE) exists as the path to a networked/multi-client deployment.

### 3.4 Why in-memory JSON data (not a database)?

- **Chose:** load JSON into memory at startup.
- **Why:** assessment/demo context; JSON is transparent and auditable; the data layer is
  one file (`data.ts`) so swapping in Postgres is a localised change.
- **Trade-off:** no persistence (audit lost on restart), no concurrency, no real query engine.

### 3.5 Why enforce governance in the *server*, not the agent?

Single most important design choice. **The LLM is non-deterministic and promptable — you
can never trust it to enforce security.** So the agent may *mention* rules, but the server
*enforces* them deterministically, before any data is returned, and logs every attempt.
The agent's governance tracking (in `agent.ts`) is just **observability** (it string-matches
tool output to *report* what happened) — it is not the enforcement point.

### 3.6 Answer Grounding (anti-hallucination)

After the final answer, `groundAnswer()` cross-checks the answer against tool outputs:
extracts numeric claims and `DS###`/`PRJ###` IDs and confirms they appear in the tool
result text. Returns `grounded: true/false` with verified vs. unverified lists.
**Purpose:** catch fabrication the prompt didn't prevent. **Honest limitation:** it's
regex heuristics — it can't verify semantic correctness, only surface-level presence.

### 3.7 Fuzzy ID/Name resolution

`resolveDatasetId` / `resolveProjectId` accept exact ID → exact name → substring match.
**Why:** LLMs frequently pass `"Diabetes Cohort"` instead of `"DS001"`. Without this the
tool would 404 and the agent would flail. It's a **robustness layer for LLM imprecision**.

### 3.8 Researcher identity injection

If `researcher_id` is supplied, the profile is injected into the **system prompt** so the
agent can personalise ("based on your projects PRJ001/PRJ006..."). **Know the gap:** see §5.1 — this affects *personalisation only*, not enforcement.

---

## 4. Deep Dives (be ready to go one level below the README)

### 4.1 The ReAct loop, concretely
ReAct = *Reason + Act*. Each iteration: the model reasons about what it needs, optionally
acts (tool call), observes the result, and repeats until it can answer. In code
(`agent.ts` ~L331): a `while (iterations < maxIterations)` loop; presence of
`assistantMessage.tool_calls` = "act again", absence = "final answer". Tool results are
fed back as `role: "tool"` messages keyed by `tool_call_id`. If the cap is hit, it makes
one final `tool_choice: "none"` call forcing a summary.

### 4.2 Observability — what's captured and where
Per request: `total_duration_ms`; a timing split (`llm_thinking_ms` / `tool_execution_ms`
/ `overhead_ms`); token usage + **estimated USD cost** (`MODEL_COSTS` table × tokens);
per-tool telemetry (args, duration, success, iteration); a human-readable
`decision_chain`; `governance_applied`; and `errors`. The API persists a trimmed
`AuditRecord` (ring buffer of 100) queryable by `trace_id`.

### 4.3 Governance mechanisms (know each one cold)

| Policy | Where enforced | How |
| --- | --- | --- |
| GOV-001 Rate limit (50/day) | `checkRateLimit` | In-memory `Map` per userId, resets on date change. Called at the top of most tools. |
| GOV-002 Tiered access | `checkAccessControl` | `TIER_HIERARCHY` numeric compare; filters projects. |
| GOV-003 Classification | `checkClassification` | "Official - Sensitive" needs Tier 2+; filters datasets. |
| GOV-004 PII detection | `validateQueryContent` / `validation.ts` | Regex list (NHS number, DoB, postcode, name+patient, destructive SQL). |
| GOV-005 Small-number suppression | `applySmallNumberSuppression` | Suppresses if count < 5. |
| GOV-006 Aggregate-only | `validation.ts` (heuristic) | Warns if no aggregation function present. |
| GOV-007 Read-only | PII/prohibited patterns | Blocks DELETE/DROP/UPDATE/INSERT/TRUNCATE. |
| GOV-008 Approval workflow | `determineApprovalRequirement` | Complex + sensitive → "pending review". |
| GOV-009 Audit trail | `createAuditEntry` | Every tool writes an entry. |

### 4.4 The two `validateQuery` layers
There's a lightweight PII check inside `submitQuery` (`validateQueryContent`) **and** a
richer `validateQuery` tool (`validation.ts`) that also checks columns, aggregation,
GROUP BY suitability, and gives suggestions. The system prompt tells the agent to call
`validateQuery` *before* `submitQuery`.

---

## 5. Known Weaknesses & How to Defend Them (interviewers WILL dig here)

Being able to critique your own system honestly is a senior signal. For each: **name it,
explain the impact, give the fix.**

### 5.1 ⭐ Identity is injected into the prompt but NOT into governance enforcement
**The single most important thing to know about this codebase.** When the API gets
`researcher_id`, it only adds that person to the *system prompt*. The **MCP server session
is hardcoded to Diana** (`index.ts` `currentSession`, spawned once by `mcp-client.ts` with
`MCP_USER_ID ?? "diana"` and never changed per-request). So tier checks, classification
checks, and the restricted-dataset authorization in `submitQuery` **always evaluate against
Diana**, no matter who the API says is asking.

- **Impact:** a security-critical gap — the enforcement identity and the claimed identity can diverge. Also, one global session + global rate-limit map means no real per-user isolation.
- **Why it's like this:** stdio spawns one long-lived server process; passing per-request identity would need either per-request server spawns or a session-passing mechanism the current MCP wiring doesn't have.
- **The fix (say this):** *"Pass the authenticated identity into every `callTool` (e.g. an auth context argument or a per-request session the server reads), or move to the HTTP/SSE transport with a session per request. The agent should never be the source of identity — a JWT at the API should map to the server session."*

### 5.2 Governance in the agent is string-matching, not enforcement
`agent.ts` detects governance by searching tool output for `"Access Denied"`, `"Rate
Limit"`, etc. Brittle: reword a message and the telemetry misses it. **Fix:** have tools
return structured metadata (`{ governance: {...} }`) instead of parsing prose.

### 5.3 Some policies are "declared" more strongly than they're enforced
GOV-006 (aggregate-only) and GOV-008 (approval) are partly heuristic/simulated.
`submitQuery` doesn't run the full `validation.ts` pipeline — it only does the PII pass.
**Fix:** route `submitQuery` through the same deep validator and make aggregate-only a
hard block, not a warning.

### 5.4 No automated tests
README touts testability but there's no test suite. **Fix:** unit-test governance
functions (pure, easy), integration-test the MCP tools without the LLM, and add a mocked
end-to-end agent test. Great thing to volunteer as "first thing I'd add."

### 5.5 No persistence
Audit records and rate-limit state are in memory → lost on restart, not shared across
instances. **Fix:** Postgres for data + audit, Redis for rate limits/sessions.

### 5.6 No auth on the REST API
Anyone who can reach the port can query. Relies on network security. **Fix:** JWT/OAuth
mapping a token → researcher → MCP session.

### 5.7 Data-model coupling
`projectId = "PRJ" + datasetId.slice(2)` assumes a rigid 1:1 dataset↔project mapping by
number, and project access tier is taken from `datasets[0]` only. `getDomainForProject`
is defined but unused (domain actually comes from `organisation`). Fine for a demo,
fragile for real data. **Fix:** explicit relationships in the data.

### 5.8 Cost/latency
Every query is 1–4+ LLM calls (3–10s, ~$0.01–0.05). No caching, no streaming. **Fix:**
prompt caching, `gpt-4o-mini` for simple lookups, SSE streaming for perceived latency.

---

## 6. "How do I change X" Cookbook (be ready to do these live)

### Add a new MCP tool
1. In the right module (`mcp-server/src/tools/*.ts`) call `server.tool(name, description, zodSchema, handler)`.
2. Start the handler with `const session = getSession();` then `checkRateLimit`, etc.
3. Call `createAuditEntry(...)` before returning.
4. Return `{ content: [{ type: "text", text }] }` (add `isError: true` on failure).
5. That's it — the agent **auto-discovers** it via `listTools()`; no agent change needed.
   (Optionally add it to the static list in `api.ts` `GET /tools`.)

### Add a governance policy
1. Append to `GOVERNANCE_POLICIES` in `governance.ts` (id, name, category, enforcement).
2. Write its enforcement function and call it inside the relevant tool(s).
3. Optionally add detection in `agent.ts` for telemetry. New policy = append + wire in.

### Swap the LLM (e.g. to Claude)
- The agent depends on the OpenAI Chat Completions shape. Swap `this.openai...create()`
  for the Anthropic SDK (or an OpenAI-compatible endpoint), map tool schemas to Anthropic's
  `tools` format, and add its pricing to `MODEL_COSTS`. **The MCP server is untouched** —
  that's the whole point of the split.

### Add a dataset
- Add an entry to `data/datasets.json` (+ optional `sample_query_results.json`). Column
  metadata is inferred from `COLUMN_METADATA` in `data-access.ts`; add entries there for
  rich descriptions/example values. `restricted: true` makes it Tier-2-only.

### Add real authentication
- Add JWT middleware in `api.ts`, decode → researcher, and (the important part) propagate
  that identity to the MCP session (see §5.1 fix).

### Change the "logged-in" user for a demo
- Set `MCP_USER_ID` / `MCP_USERNAME` / `MCP_DISPLAY_NAME` env vars (read in
  `index.ts`/`mcp-client.ts`). E.g. run as a Tier-1 user to demo an access denial.

---

## 7. Interview Q&A Bank (with model answers)

### Conceptual / "explain it"
**Q: What is MCP and why use it here?**
A: A standardised protocol for exposing tools/resources to LLM clients over a transport
(stdio/HTTP). It decouples *reasoning* (agent) from *execution + governance* (server), so
tools are reusable, independently testable, and — crucially for NHS — governed regardless
of which client calls them.

**Q: What's the ReAct pattern?**
A: Reason-then-Act in a loop: the model decides an action (tool call), observes the result,
and iterates until it can answer. Here it's the `while` loop in `agent.ts` driven by
whether the model returned `tool_calls`.

**Q: Walk me through a request end to end.**
A: (Use §1 — API → agent loop → MCP client over stdio → server governance+tool+audit →
grounding+sources → JSON + audit record.)

### Architecture / trade-offs
**Q: Why no framework like LangChain?**
A: (§3.2 — MCP is already the tool layer; owning the loop gives full observability; tiny
auditable dependency surface; no lock-in. Frameworks pay off when orchestration is the hard
problem; here it was governance and traceability.)

**Q: Why stdio and what does it cost you?**
A: (§3.3 — zero config, single container, low latency; costs horizontal scalability, hence
the SSE server as the growth path.)

**Q: Where would this break at 1000 concurrent users?**
A: One MCP child process + one in-memory session + process-global rate-limit map. I'd move
to the HTTP/SSE transport with a session per request, externalise state to Redis/Postgres,
and run the API stateless behind a load balancer.

### LLM / agents
**Q: How do you stop the LLM hallucinating data?**
A: Three layers: (1) a strict system prompt — "every fact must come from a tool result";
(2) grounding — regex-verify numbers/IDs against tool outputs post-hoc; (3) the data itself
only comes from tools, and unresolved IDs return explicit "not found". I'm honest that
grounding is heuristic, not semantic.

**Q: How do you prevent infinite tool-calling loops?**
A: `MAX_ITERATIONS` cap; on hitting it, one final forced call with `tool_choice: "none"` to
summarise.

**Q: How do you control cost?**
A: Track tokens/cost per request in observability; could route simple lookups to
`gpt-4o-mini`, cache, and cap iterations. The `MODEL_COSTS` table makes cost visible per query.

**Q: How does the model know which tool to call?**
A: Tool `description` fields are written as *routing instructions* (e.g. "use searchDatasets
NOT submitQuery to list datasets"). Good descriptions are prompt engineering.

### Governance / security (they'll push hard here — it's NHS)
**Q: Why enforce governance in the server, not the agent?**
A: The LLM is non-deterministic and promptable; you can't trust it to enforce security.
The server enforces deterministically before returning data and logs every attempt, so even
a non-AI client is governed.

**Q: A user asks "list all patient NHS numbers with high HbA1c" — what happens?**
A: `validateQueryContent` regex matches the NHS-number pattern → hard block with a
governance reason, and an audit entry with outcome "Rejected". (There's a seeded example of
exactly this: query `q-005`.)

**Q: How does small-number suppression work and why?**
A: If a result group has < 5 records it's suppressed, to prevent re-identification of
individuals — standard NHS statistical disclosure control. Implemented in
`applySmallNumberSuppression`.

**Q: ⭐ If I pass `researcher_id: "charlie"`, does Charlie's access actually apply?**
A: (Be honest — this is the killer question.) No. Today `researcher_id` only personalises
the prompt; the MCP server session is hardcoded to Diana, so enforcement runs against Diana.
It's a gap I can identify precisely: identity should flow from a JWT at the API into the MCP
session per request, and the agent should never be the source of identity. (§5.1)

### Debugging / operations
**Q: A query returns a wrong answer — how do you debug?**
A: Pull `GET /audit/:trace_id`: inspect `decision_chain` (what the agent decided), each
tool's args/result/success, the grounding result, and errors. The full loop is traceable.

**Q: How would you test this?**
A: Unit-test pure governance functions; integration-test each MCP tool with a mock session
(no LLM); mock the OpenAI client for a deterministic end-to-end agent test. (§5.4)

### Behavioural / senior signal
**Q: What would you do differently / first?**
A: Fix the identity-propagation gap (§5.1), add a test suite (§5.4), and replace prose-based
governance detection with structured tool metadata (§5.2). I'd also gate `submitQuery` on
the full validator.

**Q: What are you most proud of?**
A: The clean separation that makes governance unbypassable and every request fully
traceable — and doing it in ~80 lines of orchestration instead of a heavyweight framework.

---

## 8. Likely live tasks (rehearse the motions)
- **"Add a tool that returns the top-N largest datasets."** → new `server.tool` in
  `research.ts`, sort `researchDatasets` by `recordCount`, audit, return text. (§6)
- **"Add a policy that blocks queries outside business hours."** → append to
  `GOVERNANCE_POLICIES`, write a check, call it in `submitQuery`. (§6)
- **"Make `researcher_id` actually enforce access."** → discuss/implement §5.1: thread an
  auth context through `callTool` → `getSession`.
- **"Swap to Claude."** → §6; show you know only the agent changes.

---

## 9. One-Liners to Memorise
- "The LLM plans; the MCP server enforces. Governance can't be prompted away."
- "80 lines of loop we fully own beats 50 dependencies we don't."
- "stdio for one-container simplicity; SSE is the path to scale."
- "Grounding is a safety net, not a proof — it checks presence, not truth."
- "Fuzzy resolution exists because LLMs pass names where the API wants IDs."
- "Today identity personalises the prompt; it should also drive enforcement — that's my #1 fix."
- "Every request has a trace_id and a full decision chain — nothing is a black box."

---

## 10. Fast Facts (rapid-fire)
- **Stack:** TypeScript (ESM), Node 20+, `tsx` to run TS directly, Express, OpenAI SDK, MCP SDK, Zod.
- **Default model:** `gpt-4o` (`OPENAI_MODEL` to change). **Port:** 3002. **Max iterations:** 10.
- **Counts:** 14 MCP tools, 9 governance policies, 20 datasets, 20 projects, 15 researchers.
- **Tiers:** Tier 1 < 2 < 3; "Official - Sensitive" needs Tier 2+.
- **Default session:** Diana Fitzgerald, Clinical Research Fellow, Tier 2, projects PRJ001/PRJ006.
- **Transports:** agent↔server = **stdio** (default). `http-server.ts` = SSE alternative (not the default path).
- **Endpoints:** `POST /query`, `GET /health`, `GET /tools`, `GET /audit`, `GET /audit/:traceId`.
- **Deploy:** single Docker image; `CMD tsx agent/src/api.ts` spawns the MCP server internally.

Good luck — you've got this. Read §1, §3, and §5 the morning of.
