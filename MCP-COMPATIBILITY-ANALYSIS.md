# Should the CLI adopt the MCP tool contract?

An analysis of whether aligning `scripts/devtools/`'s command-line surface with
the current Model Context Protocol specification is worth doing, using the
nine Jira commands as the case study. This project is explicitly not going to
be an MCP server (`ARCHITECTURE.md`); the question is whether MCP's *tool
contract* is a useful design target for a CLI that already claims three
audiences — humans, AI agents, and CI (`UX-DESIGN-PRINCIPLES.md`, opening
paragraph).

The specification revision referenced throughout is **2026-07-28**, the current
(non-draft) revision per
<https://modelcontextprotocol.io/specification/versioning>.

## Verdict

**Yes for the tool contract, no for the protocol.**

MCP's `Tool` type — a machine-readable name, description, `inputSchema`,
`outputSchema`, and behavior `annotations`, plus a single result per call that
carries either structured data or an actionable error — is a good, externally
maintained checklist for exactly the audience this CLI says it serves and
currently serves worst: a caller that cannot read a help box. Adopting it as a
*target shape* costs one new command and three bug-fix-sized changes, and every
one of those changes is defensible on this project's own principles 2, 4, 5, 18
and 19 with no reference to MCP at all.

MCP's *protocol* — JSON-RPC framing, `_meta` protocol-version negotiation,
`server/discover`, Streamable HTTP, `subscriptions/listen`, resources, prompts,
multi-round-trip input requests — has no place in a `just` recipe. Chasing it
would add ceremony that neither humans nor CI benefit from, and the parts that
look tempting (elicitation, resources) already have working CLI-native
equivalents.

The honest summary of the current state: an AI agent driving `just
read-jira-issue` today **can** get structured output (`--format json`), but
**cannot** discover the command's flags mechanically, **cannot** parse a
mutation's output as one JSON document, and **cannot** get a machine-readable
failure reason. Those three gaps are the whole finding; MCP is just the lens
that makes them obvious.

## What "MCP-compatible" can mean here

Three distinct readings, only the first of which is being recommended:

1. **Tool-contract compatible.** The CLI's machine-facing surface is
   *shaped* like MCP tool definitions and tool results, so a wrapper of a few
   dozen lines could expose it over MCP later, and so any agent — MCP or not —
   gets typed discovery and typed results today. Cost: small. Value: real,
   and independent of MCP's survival.
2. **Shim-ready.** Ship an actual `just-dev mcp-serve` that translates
   `tools/call` into in-process calls. This is a *consequence* of (1), not a
   prerequisite, and is out of scope by the project's own framing.
3. **Protocol-compatible.** Speak JSON-RPC over stdio/HTTP from the CLI.
   Not recommended, at any price.

## Why the 2026-07-28 revision makes this a better fit than it used to be

The revision moved MCP *toward* how a CLI already works, which is why this is
worth revisiting now rather than a year ago:

- **Sessions are gone.** The `initialize`/`notifications/initialized` handshake
  and `Mcp-Session-Id` were removed; every request carries its own version and
  capabilities. A CLI process has never had a session either.
- **State must be an explicit handle passed as an ordinary argument.** That is
  precisely what `search-jira-issues --next-page-token` already does, and what
  the broker session deliberately is *not* (see the boundary in F9).
- **Credentials are per-request input, not connection state**, and the tool set
  "MAY vary by the authorization presented on the request." That matches this
  CLI's per-invocation broker scope check exactly.
- **Deterministic ordering and cacheable tool lists** are now a SHOULD. A
  generated manifest is deterministic by construction.
- **Sampling, roots, and logging are deprecated** — three of the four features
  that would have had no CLI analogue anyway.

Conversely, one 2026-07-28 addition is a warning sign for over-adoption:
`InputRequiredResult` / multi-round-trip requests. That is MCP inventing a
protocol-level mechanism for "the tool needs a human to confirm something." The
CLI already solves that with `--dry-run`, `--yes`, and exit code 26. Do not
port the mechanism; the CLI's version is simpler and already tested
(`confirmation.py`).

## Case study: the Jira commands as MCP tools

MCP's `Tool` has five fields that matter here: `name`, `description`,
`inputSchema`, `outputSchema`, `annotations`. Mapping the nine Jira commands
onto them is what exposes the gaps.

### Name

No work needed. MCP tool names SHOULD be 1–128 characters of
`[A-Za-z0-9_.-]` with no spaces. Every flat alias already conforms verbatim:
`read-jira-issue`, `search-jira-issues`, `transition-jira-issue`. The
namespaced form (`jira read-jira-issue`) contains a space and would map to
`jira.read-jira-issue`, which is also legal and is the collision-avoidance
prefix MCP recommends. The verb-object convention from principle 8 turns out to
be exactly what MCP asks for.

### Description

Exists, as `help=` strings and docstrings, and principle 1 keeps them honest.
Two warts show up when they are read as machine-facing type documentation
rather than as prose:

- `--safe` is described as "Omit structural identity, URL, and attachment
  fields" on the root callback (`cli.py:144`) and "Filter structural identity
  and URL fields" on each command that declares it (e.g. `cli.py:520`). Same flag, two
  descriptions, one of which omits attachments.
- Several commands have no docstring at all (`read-jira-issue`,
  `search-jira-issues`, `update-jira-issue`, `assign-jira-issue`,
  `comment-jira-issue`, `attach-jira-issue`, `transition-jira-issue`,
  `delete-jira-issue`), so their `--help` leads with the option table and no
  sentence saying what the command does. `create-jira-issue` is in the same
  state. For a human the name carries it; for a tool-list entry, `description`
  would be empty.

### `inputSchema` — the largest gap

MCP requires a JSON Schema per tool. The CLI has no machine-readable input
description at any layer. See F4 and F8 below; this is where most of the value
is.

### `outputSchema` — partially achievable, honestly

`--format json` is the CLI's `structuredContent` and the Markdown default is
its `content` text block; the split MCP draws already exists. What does not
exist is a *declared* shape, and for two of the commands it cannot exist
without a decision (F5).

### `annotations` — free, and more informative than expected

MCP's four behavior hints (`readOnlyHint` default `false`, `destructiveHint`
default `true`, `idempotentHint` default `false`, `openWorldHint` default
`true`) are already knowable for every Jira command. Writing them down is a
half-hour of declaration, and the exercise surfaces two real hazards that are
currently invisible to a caller:

| Command | readOnly | destructive | idempotent | Note |
| --- | --- | --- | --- | --- |
| `read-jira-issue` | ✅ | — | — | |
| `search-jira-issues` | ✅ | — | — | Paginated; token is an explicit handle |
| `create-jira-issue` | ❌ | ❌ additive | **❌** | **No idempotency key: a retried agent call files a duplicate issue** |
| `update-jira-issue` | ❌ | ✅ | ✅ | `--labels` *replaces* all labels (`cli.py:616`) — an agent adding one label wipes the rest |
| `assign-jira-issue` | ❌ | ✅ overwrites | ✅ | |
| `comment-jira-issue` | ❌ | ❌ additive | **❌** | Retry duplicates the comment |
| `attach-jira-issue` | ❌ | ❌ additive | **❌** | Retry duplicates the attachment |
| `transition-jira-issue` | ❌ | ✅ | ✅ | Second identical call fails with "Allowed transitions" |
| `delete-jira-issue` | ❌ | ✅ | ✅ | Second call 404s |

The three bolded non-idempotent commands are the ones an agent will get wrong,
because retry-on-failure is an agent's default behavior and nothing in the
current interface warns against it. Note the interaction with F1: a mutation
that succeeded remotely but whose output the caller failed to parse looks
exactly like a failure.

## Findings

Each finding is reproducible from a clean checkout. `repro:` lines are literal.

### F1 — A confirmed mutation emits two JSON documents on stdout (severity: high)

`workflows.py:255` calls `announce(preview)` before `confirm_mutation`, on
every mutation path, including when `--yes` was passed. `cli.py:493` binds
`announce` to `_emit(context, {"preview": preview})`, which writes to stdout in
the selected format. The result is emitted afterwards, also to stdout.

Under `--format json` this means one invocation produces two concatenated JSON
objects. `json.loads(stdout)` raises `Extra data: line 2 column 1`. Nothing in
`README.md`, `ARCHITECTURE.md`, or any `--help` string says the output is
JSON Lines rather than JSON, and no other command behaves that way.

```text
repro: uv run just-dev --format json jira create-jira-issue bug "Summary" --yes
{"preview": {...}}
{"id": "10001", "key": "DEV-1", ...}
```

This is the single most consequential gap. MCP's rule is one result per call;
so is every reasonable CLI consumer's assumption. It is also a plain bug
against principle 4 ("one output contract"), fixable without any reference to
MCP: send the preview to **stderr** (it is progress commentary, not the
result), or return one envelope containing both.

### F2 — The preview has two different shapes depending on the flags (severity: medium)

The same `PreviewResult` is emitted bare when `--dry-run` is used
(`workflows.py:252-253` returns it as the result) but wrapped in
`{"preview": …}` when the mutation actually runs. An agent that plans with
`--dry-run` and then executes cannot use one parser for both.

```text
repro: --dry-run  → {"action": "create Jira issue", "details": {…}}
repro: --yes      → {"preview": {"action": "create Jira issue", "details": {…}}}
```

Fixing F1 by moving the preview to stderr resolves this too, if the stderr form
keeps the bare shape.

### F3 — Errors are never structured, in any format (severity: medium-high)

`_execute` (`cli.py:218`) prints `error: <text>` to stderr and exits with the
class's code, regardless of `--format`. The exit-code contract (principle 18,
`README.md` "Exit codes") is genuinely good and better than most MCP servers'
error handling — a caller can branch on 20–28 without parsing English.

But principle 13's entire achievement — surfacing Jira's own `errorMessages`
detail instead of a bare status — lands **only** in prose. The detail an agent
needs in order to self-correct (which field was too long, which transitions are
allowed, which preset names exist) is reachable only by parsing an English
sentence. MCP's equivalent is a tool result with `isError: true` whose content
the client is told to feed back to the model precisely so it can retry.

The CLI-native fix is small: under `--format json`, emit
`{"error": {"code": 25, "kind": "input_validation", "message": "…"}}` on
stderr. Text and Markdown keep today's line. Exit codes are unchanged.

One nuance worth recording: `_sdk_error` (`adapters.py:195-200`) maps every
remote 4xx to `InputValidationError` / exit 25, so a malformed key and a
nonexistent issue are indistinguishable by code. That is documented behavior
(the README row says "bad argument, value, or remote 4xx rejection") and not a
conformance break — but "fix your argument" and "that issue does not exist"
call for different agent retries, and only the message distinguishes them.

### F4 — There is no machine-readable command manifest, and the documented discovery path does not list flags (severity: high)

`OPEN_ISSUES.md` resolves U3 with "`just --list <namespace>` is the supported
discovery path for a recipe's flags." That is not what `just --list` prints:

```text
repro: just --list jira
    read-jira-issue [OPTIONS] $JUST_DEV_JIRA_ISSUE_ID_OR_KEY
```

`[OPTIONS]` is a literal placeholder. The flag names are not shown — to a
human or an agent. `just read-jira-issue --help` still fails at `just`'s
parser, as U3 documents. The only ways to learn that `--view` exists are
`just --show read-jira-issue` (which prints raw recipe attributes),
`just --dump --dump-format json`, reading the source, or invoking the Python
CLI directly with `--help`, which is not the interface the project documents.

Two related facts, verified against `just 1.58.0`, materially change U3's
cost-benefit:

1. **`just --dump --dump-format json` already emits a structured manifest** of
   every module, recipe, parameter, and `[arg]` attribute — a `tools/list`
   analogue that exists today for free.
2. **`[arg(…)]` accepts `help=` and `pattern=`, and the project uses neither.**
   Every `help` field in the dump is currently `null`.

```text
repro: [arg('X_VIEW', long='view', help='Issue view: summary or full.', pattern='summary|full')]
       just demo ABC-1 --view nope
       error: argument `nope` passed to recipe `demo` parameter `X_VIEW` does not match pattern `summary|full`
```

`pattern=` gives enum validation at the `just` layer with a clear message and
zero Python changes — principle 17 ("validate what's cheap and local first")
applied one layer further out than it currently is. `help=` populates the dump.
Neither requires the shebang-branching rewrite U3 rejected, and neither touches
a recipe body. (`min`/`max` on `[arg]` are repetition counts, not numeric
ranges — they cannot express `--limit`'s 1–100.)

The recommended addition is one command, `describe-commands`, emitting an array
of MCP-shaped tool descriptors built from Typer/Click introspection (Typer is
Click underneath; parameter names, types, defaults, and help are all
introspectable) plus a small hand-written table of annotations. That single
command satisfies principle 2 for the agent audience, closes U3 for machine
callers without reopening the recipe-syntax question for human ones, and is the
one artifact a future MCP shim would need.

### F5 — Output shape varies by flag, and `--safe` deletes fields silently (severity: medium)

`read-jira-issue --format json` returns `{id, key, fields:{…}}` under `--view
summary` and whatever Jira returned under `--view full`; `--fields` and
`--include` change the key set again. So one tool has at least four output
shapes. Declaring `outputSchema` is possible for the summary view and for
search (`{issues, nextPageToken?, isLast?, total?}` — a genuinely stable
shape), and is not possible for `--view full` without pinning Jira's own
representation. That is an acceptable answer: declare the schema for the stable
views, and say the full view is opaque passthrough.

`--safe` is the harder one. `filter_safe_output` (`rendering.py:27`) removes
matching keys entirely:

```text
repro: --format json                → fields include assignee, reporter
repro: --format json --safe --view full → assignee and reporter are simply absent
```

An agent cannot distinguish "redacted by policy" from "unset in Jira" — and if
an `outputSchema` declared `assignee` required, `--safe` output would violate
it. The docstring's honesty about `--safe` not being a PII classifier is good;
the machine-facing counterpart is to mark omission rather than perform it
(`"assignee": "[OMITTED]"`, or a sibling `omitted: ["assignee"]` list), so the
declared schema still holds.

### F6 — The `JUST_DEV_*` environment channel can silently disable confirmation (severity: medium, security-adjacent)

`_flag_or_environment` (`cli.py:229`) treats `JUST_DEV_YES=1` in the
environment as equivalent to `--yes`. Environment variables are inherited by
every child process, so a single `export JUST_DEV_YES=1` — plausible in an
agent harness, a CI shim, or a `.envrc` — removes the confirmation gate from
every mutation for the rest of that session, with no trace in the command line
that gets logged or reviewed.

```text
repro: JUST_DEV_YES=1 uv run just-dev --format json jira create-jira-issue bug "S"
       (creates the issue; no --yes anywhere on the command line)
```

MCP's position is that consent lives in the client and applies per call ("there
SHOULD always be a human in the loop with the ability to deny tool
invocations"). Principle 9's fail-closed design is the right instinct and is
undermined by an ambient variable. Worth considering: keep the env channel for
data-carrying values (which is what the recipes need it for) but require
`--yes` to be an actual argument, or at minimum echo "confirmation waived by
JUST_DEV_YES" to stderr so it is visible in a transcript.

### F7 — Non-idempotent mutations are unannotated (severity: medium)

See the annotation table. `create-jira-issue`, `comment-jira-issue`, and
`attach-jira-issue` duplicate on retry, and F1 makes a spurious retry more
likely, not less. This does not necessarily need an idempotency key — but it
needs to be *stated*, and `annotations.idempotentHint` is exactly the place the
tool contract puts it.

### F8 — `--fields` means two different types on sibling commands (severity: medium)

- `create-jira-issue --fields` — "Optional JSON object merged into 'fields'"
  (`cli.py:470`), parsed by `_json_object_or_environment`.
- `read-jira-issue --fields` — "Comma-separated field list" (`cli.py:504`).
- `search-jira-issues --fields` — comma-separated list again.

Three commands in one namespace; one flag name; two incompatible types. A human
reads the help and adapts. An agent generalizing from one call to the next
produces `--fields '{"customfield_10011":"x"}'` on a read and gets a Jira 4xx.
`recipes/jira.just` even routes them through three different environment
variables (`JUST_DEV_JIRA_FIELDS`, `JUST_DEV_JIRA_READ_FIELDS`,
`JUST_DEV_JIRA_SEARCH_FIELDS`), which is the same distinction the user-facing
name declines to make.

An `inputSchema` makes the collision undeniable (one is `type: object`, the
others `type: array`), which is an argument for generating the manifest even if
nothing else here is adopted. The cheaper fix is a rename —
`create-jira-issue --extra-fields` — which is a breaking change worth pricing
before the surface grows further.

Related but lower-severity: `--include`, `--view`, `--fields`, `--labels`, and
`--expand` are all comma-separated strings standing in for arrays and enums.
That is fine and normal for a CLI; the manifest should simply *declare* them as
`{"type": "array", "items": {"enum": […]}}` with the CSV encoding documented in
the description, rather than pretending they are opaque strings. No runtime
change needed.

### F9 — The auth lifecycle is not agent-drivable, and that is correct (severity: none — boundary, worth documenting)

`unlock-secrets` prompts for a KeePass master password on a local TTY. No agent
can drive it, and none should. The agent-usable surface is therefore the
operations, with the broker already unlocked by a human, or CI with injected
tokens. `show-auth-status` is the machine-readable check for which state
applies (and principle 16 already made it truthful under `CI=true`).

Under the 2026-07-28 model this is a clean story rather than a gap: credentials
are per-request input, and the broker session is not something a caller passes
around. It should be stated explicitly in whatever documents the agent-facing
surface, because "why can't I unlock this" is the first question an agent
harness will hit.

## Recommendation

### Do (each defensible on this project's own principles, MCP or not)

1. **One invocation, one machine-readable result** — F1, F2. Preview to stderr
   in the bare `PreviewResult` shape; stdout carries only the result. Size: S.
   Touches `cli.py`'s `announce` bindings and `test_cli.py`.
2. **Structured errors under `--format json`** — F3. `{"error": {"code",
   "kind", "message"}}` on stderr; exit codes unchanged. Size: S. Touches
   `_execute` and the error classes' names.
3. **`describe-commands`, emitting MCP-shaped tool descriptors** — F4, F7, F8.
   `name`, `title`, `description`, `inputSchema`, `outputSchema` (where stable),
   `annotations`. Generated from Click introspection so it cannot drift; a test
   asserting every command appears is the drift guard. Size: M. This is the
   keystone item — it is what makes the CLI describable to *any* agent, and it
   is the only artifact a future MCP shim needs.

### Do next

4. **Populate `[arg(…)]` `help=` and `pattern=`** — F4. Cheap, improves
   `just --dump` and adds `just`-layer enum validation. Also revisit U3's
   resolution text in `OPEN_ISSUES.md`, which currently claims `just --list`
   discloses flags. Size: S.
5. **Declare `outputSchema` for the stable views and mark `--safe`
   omissions** — F5. Size: M, and it needs the "full view is opaque" decision
   made explicitly.
6. **Price the `--fields` rename and the `JUST_DEV_YES` tightening** — F8, F6.
   Both are breaking-ish; both get worse the longer the surface grows.

### Don't

- JSON-RPC framing, `_meta`, `server/discover`, Streamable HTTP,
  `subscriptions/listen`. Wrong layer entirely.
- MCP `resources` and `prompts`. No CLI analogue worth inventing; Jira issues
  are not URI-addressable through this tool and nothing wants them to be.
- `InputRequiredResult` / multi-round-trip confirmation. `--dry-run`, `--yes`,
  and exit 26 already cover it, more simply and with tests.
- Restructuring CSV inputs into JSON arrays. Declare the encoding; don't change
  it. Humans type commas.
- Shipping an actual MCP server. Explicitly out of scope, and items 1–3 keep it
  a small, deferrable change if that ever reverses.

### What this is worth

The concrete payoff is not "MCP support." It is that after items 1–3, an agent
can (a) enumerate the commands and their typed parameters from one call, (b)
parse exactly one result document per invocation, and (c) read a failure's
reason without natural-language parsing — while humans see no change other than
previews moving to stderr. Every one of those is a restatement of principles 2,
4, 5, 18 and 19 for the audience the document names second and serves last.

The parts of MCP worth *not* copying are worth recording too: this CLI's
`--view`/`--fields`/`--include` filtering (principle 6) and its
answer-first default output (principle 19) are better result-size discipline
than most MCP servers manage, and its exit-code contract (principle 18) is a
finer-grained error taxonomy than `isError: true`. Compatibility here means
adopting the schema-and-annotations half, not trading down on the rest.

## Proposed additions to `UX-DESIGN-PRINCIPLES.md`

Offered in that document's format, if items 1–3 are accepted:

**20. One invocation, one machine-readable result.** Everything a command
prints to stdout under `--format json` must parse as exactly one JSON document.
Progress commentary, previews, and warnings go to stderr. A mutation's preview
is commentary, not a result: `--dry-run` returns it *as* the result, and a
confirmed run must not interleave it with the real one.

**21. Declare the machine contract; don't only document it.** Any fact an
automated caller needs — a parameter's type, an enum's members, whether a
command is read-only or destructive or safe to retry — must be available from a
command, not only from prose or a `help=` sentence. `describe-commands` is that
command; a new command is not finished until it appears there with its
annotations. Prose explains; the manifest is the contract.
