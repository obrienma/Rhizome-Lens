# Engineering Journal — rhizome-lens

Per-repo engineering journal (typed, vocabulary-enforced). Paired Anki probes
live in `docs/probes/`. Migrated from `LEARNING_LOG.md` on 2026-06-16.

---

## Phase 0 — Observability Infrastructure — 2026-06-05
Files: docker-compose.yml, otel-collector-config.yaml, tempo.yaml, loki-config.yaml, prometheus.yml, grafana/provisioning/datasources/, grafana/provisioning/dashboards/, README.md

### Pattern: Fan-Out Pipeline (Collector multiplexing)
The OTel Collector is the single ingestion point that demultiplexes one OTLP
stream into three signal-specific backends. The mechanism is one pipeline per
signal type under `service.pipelines` — `traces`, `logs`, `metrics` — each
sharing the same `otlp` receiver but terminating in its own exporter
(`otlp/tempo`, `loki`, `prometheus`). The receiver feeds all three; the
Collector owns the fan-out, so a service emits once and the backend topology is
invisible to it.

### Pattern: Declarative Provisioning (filesystem provider)
Grafana datasources and dashboards are provisioned from YAML/JSON mounted into
`/etc/grafana/provisioning/...`, read on startup and hot-reloaded
(`updateIntervalSeconds: 30`). The container is cattle, not a pet: recreating
it loses no configuration because none of it was ever entered through the UI.

### Pattern: Provision-Ahead Correlation (`tracesToLogsV2` on day zero)
Trace-to-log correlation was wired at stack bootstrap, before any service
emitted a signal. Setting `tracesToLogsV2.datasourceUid` in the Tempo
datasource provisioning means the one-click trace→log jump works the instant a
Phase 1 service ships both signals — the plumbing precedes the traffic, so
there is no "go back and configure Grafana" step later.

### Pattern: Auto-Instrumentation Logs Bridge
`@opentelemetry/sdk-node` (0.218.x) with `auto-instrumentations-node` wires the
OTel Logs Bridge into Fastify's built-in pino logger and exports it over OTLP
with zero logging code. Observed downstream: a live `event-horizon` Loki stream
carrying `traceid`/`spanid` on every line, despite the service having no log
exporter package. The SDK *version* alone delivered what was scoped as manual
work. (Note: this is environment-dependent and was later found NOT to be active
in the current EventHorizon build — see the README logging caveat; treated as a
capability of the SDK, not a confirmed live state of every service.)

### Pattern: Default-Inert Feature Flag (opt-in fault injection)
Realistic non-zero error panels without perturbing normal runs: gate the fault
behind an env/CLI flag defaulting to `0`, checked as `Math.random() < rate`
*after* validation. At `rate = 0` the predicate is provably always false, so the
path is inert under `npm test`/`npm run dev`. Pairing a server-side 5xx knob
(throw post-validation) with a client-side 4xx knob (schema-invalid payload)
yields a realistic mixed-status traffic shape from a single seed run.

### Anti-Pattern Avoided: Core Collector image for a multi-backend setup
The `loki` exporter ships only in `otel/opentelemetry-collector-contrib`, not
`core`. Using core omits the logs pipeline *silently* — no startup error, the
pipeline simply does not exist. `contrib` is the only safe default for any
multi-backend Collector.

### Anti-Pattern Avoided: Deprecated Loki schema / future-dated `from`
Two adjacent traps in Loki 3.x config. (1) Schema v11/BoltDB-Shipper is
deprecated; v13/TSDB is the current default and only forward-compatible choice —
v11 emits startup warnings that mask real errors. (2) A schema `from:` set to
today or a future date makes Loki silently refuse ingestion until that date
arrives; a fixed past date (`2024-01-01`) guarantees the schema is active on
first boot.

### Anti-Pattern Avoided: `CMD-SHELL` healthcheck in a distroless image
`otel-collector-contrib` is distroless — no `/bin/sh`. Docker's `CMD-SHELL`
form injects `/bin/sh -c`, which fails immediately
(`stat /bin/sh: no such file or directory`) and marks the container
permanently unhealthy even while the process runs correctly. Use `disable:
true` when the image has no probe binary, or `CMD` with a binary known to exist.

### Anti-Pattern Avoided: Squatting the most-collided shared-infra port
Grafana's compose default is `3000:3000`, which collides with the common
per-project dev-server default (EventHorizon also wants `PORT=3000`). Whichever
process binds the host port wins *silently* — `docker compose ps` still shows
the container healthy because its healthcheck probes its own internal
localhost, blind to the host conflict. Shared cross-project infra should claim a
distinctive port (`3300`), never the most commonly squatted one.

### Anti-Pattern Avoided: Trusting a metric name's `_total` suffix
A panel querying `rate(otelcol_receiver_accepted_spans_total[1m])` shows "No
data" with no error — the real metric is `otelcol_receiver_accepted_spans`,
no `_total`. Prometheus returns a valid empty result for a nonexistent metric,
so a fully-configured panel can render nothing permanently. Verify against
`/api/v1/label/__name__/values`, don't assume naming conventions.

### Anti-Pattern Avoided: Disassembling a container's frontend on a 2 GB WSL2 host
Stacking heavyweight container-introspection ops concurrently (`exec` +
`strings`, a 368 KB bundle `cp`, a background `python3` regex scan) exhausted
the WSL2 VM's fixed memory ceiling, crashing the VM and killing every Docker
container across every project. When the question is "what query shape does
this datasource expect," query the datasource's documented API directly (Tempo
`/api/search` on `:3200`) instead of disassembling the frontend that calls it.

### Challenge: Distroless collector reported unhealthy while fully running
`docker compose ps` showed `otel-collector` unhealthy despite
`"Everything is ready"` in its logs. `docker inspect --format '{{json
.State.Health}}'` exposed the probe failing on the missing `/bin/sh`, not the
service. Fix: `healthcheck.disable: true`. Diagnostic rule: read
`State.Health.Log[].Output` to separate a failing probe from a failing process.

### Challenge: `docker info` succeeds but `docker compose up` cannot find the socket
`docker info` returned a valid engine version, yet Compose failed with "no such
file or directory" — the CLI was talking to a remote daemon over TCP while
Compose looked for `/var/run/docker.sock`, which did not exist. `docker info`
succeeding is not proof Compose will work; check `ls /var/run/docker.sock`.

### Challenge: Host port 3000 routed to the wrong service
`docker compose ps` showed Grafana healthy on `3000:3000`, but `curl
localhost:3000` returned EventHorizon's Fastify 404 JSON. `ss -tlnp` revealed
the host listener belonged to EventHorizon, not docker-proxy. A healthy
container with a mapped port does not guarantee the host port routes to it —
verify with `ss -tlnp` or the response body. (Root cause of the port-3300
decision.)

### Challenge: `curl -s` to a PromQL range-vector returned zero bytes
`curl -s '.../query?query=rate(metric[5m])'` produced empty output that then
failed JSON parsing. curl's URL globbing tries to interpret `[5m]` as a range
and errors pre-request; `-s` swallowed the message. Use `-g`/`--globoff` or
`-G --data-urlencode` for PromQL/TraceQL range-vector queries.

### Challenge: 44 passing tests coexisting with a 500 on every real request
`event.routes.ts` evaluated `Buffer.byteLength(request.body as string)` inside
`span?.setAttributes({...})`. Optional chaining short-circuits its *entire
argument tree*: `app.inject()` tests have no active span, so the throwing
expression is structurally unreachable and 44/44 pass; under real HTTP
auto-instrumentation every `POST /events` took the active-span branch and threw
`ERR_INVALID_ARG_TYPE`, 500-ing 100% of seeded traffic. A green suite can hide
a bug that is unreachable only because tests never produce the non-null
receiver.

### Challenge: Grafana 11.2's `/api/ds/query` rejects TraceQL *search*
A Tempo query body with `queryType: "traceqlSearch"` (or `"traceql"`/`""`) to
`/api/ds/query` returns "unsupported query type". Only `"traceId"` (single-trace
lookup) works on that endpoint; TraceQL *search* is issued by Grafana's frontend
via a separate `CallResource` route
(`/api/datasources/uid/tempo/resources/search`). To validate TraceQL search
headlessly, hit Tempo's own `/api/search` directly (`q=<query>&limit=N`) — same
syntax, no Grafana session.

### Decision: Tempo monolithic mode, local block storage, 1 h retention
Single-process monolithic over distributed (no horizontal-scaling need locally;
faster start, smaller config surface). All trace/log data in named Docker
volumes (`tempo-data`, `loki-data`) — surviving `restart`, wiped by `down -v`,
the correct dev lifecycle — with no S3/GCS. `block_retention: 1h` keeps disk
negligible during iteration, trivially extendable per-service later.

### Decision: Two Prometheus jobs for two distinct Collector endpoints
The Collector's self-telemetry (`otelcol_*`, e.g. `..._receiver_accepted_spans`)
lives on `service.telemetry.metrics.address` (`:8888`), a different server from
the `prometheus` exporter (`:8889`) that carries app-sent OTLP metrics. Kept the
existing `otel-collector` job (`:8889`) untouched and added a second
`otel-collector-internal` job (`:8888`) — different namespaces, different
operational meaning (collector health vs. application signal). Added Tempo
(`tempo:3200/metrics`) as a third job so the existing "Tempo Spans Ingested/sec"
panel had a scrape target.

### Decision: Frictionless local Grafana auth
`GF_AUTH_ANONYMOUS_ENABLED=true` grants access but leaves the login form
visible and confusing; pairing it with `GF_AUTH_DISABLE_LOGIN_FORM=true` makes
the local-only intent explicit.

### Decision: Disable the collector healthcheck rather than fake a probe
With no probe binary in the distroless image, `healthcheck.disable: true` over
adding a bogus probe. The in-container `health_check` extension still reports
readiness on its own endpoint; Docker's status is cosmetic for local dev. If a
real liveness gate is ever needed (`depends_on: service_healthy`), the correct
fix is a thin wrapper image or the non-distroless variant — not papering over it.

### Decision: Fix the EventHorizon `Buffer.byteLength` bug on discovery
Found while smoke-testing the Phase 0 stack against EventHorizon (not Phase 0
work), but it blocked every ingest. Fixed directly in EventHorizon (`a9e2e4a`)
rather than merely logged — a non-functional system under test is useless for
validating the observability stack.

### Decision: Build "EventHorizon Service" as a narrow early slice of Phase 5
The plan defers dashboards (Phase 5) until a concrete need; the need (portfolio
screenshots) arrived. Pulled forward only a per-service RED + Node-runtime-health
dashboard built entirely from metrics `auto-instrumentations-node` already
exports (`http_server_duration_milliseconds_*`, `db_client_connections_usage`,
`nodejs_eventloop_delay_*`, `v8js_memory_heap_used_bytes`) — no new
instrumentation. The plan's TraceQL/wide-span *business* dashboards stay
deferred: this slice answers "is the service healthy," not "what is it doing."

### Decision: `{"partialSuccess":{}}` documented as the OTLP success response
OTLP/HTTP returns `{"partialSuccess":{}}` on *full* success, not `{}`; a
non-empty `partialSuccess` (with `rejectedSpans` + `errorMessage`) means partial
rejection. Documented in the README smoke test so an empty object isn't read as
a failure.

---

## Phase 0 (cont.) — EventHorizon Dashboard Expansion: RabbitMQ scrape, throughput, async-failure panels — 2026-06-14
Files: prometheus.yml, grafana/provisioning/dashboards/eventhorizon-service.json, README.md

### Pattern: Cross-Compose-Project Scrape via the Host Gateway
Prometheus (this stack's `observability` network) scrapes RabbitMQ (EventHorizon's
separate compose project) without merging the stacks by reaching it through the
host: target `host.docker.internal:15692` plus `extra_hosts:
["host.docker.internal:host-gateway"]` on the Prometheus service. `host-gateway`
is a Docker-reserved alias for the host's gateway IP. The alternative — a shared
external Docker network referenced by both compose files — couples the two
projects' lifecycles; the host-gateway hop keeps them independent.

### Pattern: Dual-Axis Panel via `byRegexp` field override
Queue depth (a count) and publish/deliver throughput (a rate) coexist on one
timeseries without either flattening the other: default the panel to `short`,
then add a field override `byRegexp: /.*rate.*/` setting `custom.axisPlacement:
right` and `unit: cps`. Grafana renders a second Y-axis for just the matched
series. Legend naming is load-bearing — the override matches on series name.

### Anti-Pattern Avoided: Unlabelled `rate()` on a per-queue counter
`rabbitmq_prometheus` exports counters per queue, so a bare
`rate(rabbitmq_queue_messages_published_total[1m])` returns one series per queue
(work, dead, others), cluttering the axis with DLQ/throwaway lines irrelevant to
worker backlog. Scope to `{queue="events.work"}` — backlog detection cares only
about the work queue's publish-vs-deliver gap.

### Anti-Pattern Avoided: `json.dump` round-trip to reorder dashboard panels
The dashboard JSON uses hand-curated inline objects (`{ "type": "loki", "uid":
"loki" }`) that `json.dump(indent=2)` would explode into multi-line form,
turning a two-panel move into a whole-file diff. Reorder with targeted text
edits and validate with a read-only `json.load` — minimal diff, formatting
preserved.

### Challenge: A freshly-added scrape target legitimately shows `DOWN`
The `rabbitmq` job can only go `UP` once the *other* repo (EventHorizon) enables
its `rabbitmq_prometheus` plugin and publishes `15692` on the host. Committing
this change leaves a red target until that side ships — expected, not a
misconfiguration, and documented in the README so no future reader "fixes" a
correct config. A scrape config declares intent; the target stays down until the
other side exposes the endpoint.

### Decision: Host-gateway bridge over a shared external network
Chose `extra_hosts: host.docker.internal:host-gateway` + a host-port target over
a shared external network referenced by both compose files. Rationale: the two
stacks stay lifecycle-independent (either tears down without breaking the
other's network reference); the cost is one Linux-specific `extra_hosts` line,
documented inline.

### Decision: One dual-axis RabbitMQ panel to cap additive panels at four
The spec listed four metric groups but six queries across two unit families.
Rather than a fifth panel, folded queue/DLQ depth (left axis) and publish/deliver
rate (right axis) into a single "RabbitMQ Queue Health" panel that also reads as
one question — "is the queue backing up?" — holding the total at exactly four new
panels. Left panel `id`s non-sequential (1–6, 9–12, 7–8) after the reorder; ids
are stable identifiers nothing references by number, so resequencing would be
churn for zero gain — `gridPos` and array order (the rendering sources of truth)
both match the layout.

### Decision: Async failures as a TraceQL panel, not a new metric (at first)
Closed the "HTTP 5xx panel can't see post-202 worker/DLQ failures" gap with a
Tempo table over `status=error` spans — no new instrumentation — and deferred the
optional `events_failed_total{event_type}` counter until a concrete alerting
need, consistent with the plan's "reserve Prometheus counters for alerts" and
"wait until it hurts." (Superseded the next session — see below.)

---

## Phase 0 (cont.) — Verifying the RabbitMQ panels against the live exporter — 2026-06-15
Files: grafana/provisioning/dashboards/eventhorizon-service.json, prometheus.yml, README.md

Once EventHorizon's Phase 18 brought `rabbitmq_prometheus` live (`:15692` → HTTP
200), the panels written blind in the previous step could be checked against
reality. Two queries were wrong — verification caught exactly what the "don't
assume a metric name" anti-pattern predicts.

### Pattern: `or vector(0)` baseline — and its lifecycle limit
A zero-failure `events_failed_total` rate panel reads "No data," ambiguous
against a broken query. `or vector(0)` falls back to a flat-0 series. Two
caveats. (1) For *grouped* queries `vector(0)` has an empty label set, so when
the left side is non-empty `or` appends a 0-series that Grafana legends as
`unknown` — misleading; `or label_replace(vector(0), "<label>", "none", "", "")`
labels it `none`. (2) The baseline is only worth it *before* the counter's first
increment: a Prometheus counter series persists once exposed, so after the first
real sample the grouped query is never empty again and the baseline becomes
permanent clutter. Add it only for counters that may never have incremented in a
given environment; drop it once the metric is reliably present.

### Pattern: Enumerate a series' other labels before asking for new instrumentation
`event_type="unknown"` is *truthful* for pre-parse poison messages — the
dead-letter path genuinely can't classify a message that failed before parsing
(146 and climbing, a real signal, not a rendering artifact). The useful
dimension was a second label the counter already carried: `failure_reason`.
Regrouping `by (failure_reason)` with legend `{{failure_reason}}` fixed the
uninformative grouping with a query change and zero EventHorizon edit. When a
series' obvious grouping label is uniform-and-useless, enumerate its other
labels first — the dimension you want may already be there.

### Pattern: `sum()` to collapse per-object counters to one line
Per-object RabbitMQ counters carry `channel`/`exchange`/`queue_vhost` beyond
`queue`, so multiple producer channels yield multiple series.
`sum(rate(...))` aggregates them into a single per-queue throughput line.

### Anti-Pattern Avoided: Scraping the aggregated `/metrics` for per-queue series
`rabbitmq_prometheus`'s default `/metrics` is *aggregated* — it sums all queues
into a single label-less total carrying zero `queue=` labels (verified `grep -c
'queue=' → 0`). A `{queue="..."}` filter matches nothing, silently. Per-queue
series live on `/metrics/per-object`; set `metrics_path: /metrics/per-object`
on the scrape job.

### Anti-Pattern Avoided: Charting `rabbitmq_queue_messages_delivered_total`
That metric does not exist. The `rabbitmq_queue_messages*` family has
`_published_total` but no queue-level delivered counter — delivery is tracked
per *channel* (`rabbitmq_channel_messages_delivered_total`). Confirmed by
enumerating `# TYPE rabbitmq_queue_messages*`. The series was dropped, not
shipped as a permanent "No data" line; backlog reads from depth trend + publish
rate + app-side `events_processed_total`.

### Challenge: Ghost `value` series after adding a label retroactively
After regrouping `by (failure_reason)`, the legend showed two lines — a green
`value` for older data and `parse_error` for newer. The label was *added*
partway through the window; pre-label samples have no `failure_reason`, so
`by (failure_reason)` buckets them into an empty-labeled series Grafana names
`value` (its default value-column label). Not a bug — the metric's own history
at the label-introduction boundary, confirmed by a `query_range` showing the
`<ABSENT>` series ending exactly where `parse_error` begins. Filter with a
`{failure_reason!=""}` matcher (absent ≡ `""` in PromQL); kept permanently.

### Challenge: Can't verify per-queue series against an idle broker
`rabbitmq_queues 0` / `rabbitmq_connections 0` — the worker wasn't connected, so
`events.work`/`events.dead` weren't declared and no per-queue series existed.
RabbitMQ only exposes per-object series for objects that currently exist. The
`queue` label *name* is documented (high confidence); label *values* can only be
confirmed against a running producer. Same root cause left `:8889` with no
`events_processed_total`/`events_failed_total`/`..._change_stream_lag` — healthy
pipeline, nothing emitting while the app is down.

### Challenge: Prometheus serving a stale on-disk config
After committing the `rabbitmq` job, `/api/v1/targets` listed only the three old
jobs. The job was on disk but the running Prometheus hadn't reloaded it —
editing `prometheus.yml` does not hot-apply. The config on disk and the config
in memory are independent; `docker compose up -d --force-recreate prometheus`
(the WSL2-safe reload) or `/-/reload` re-reads it.

### Decision: Scrape `/metrics/per-object` over broker-side `return_per_object_metrics`
Both expose per-queue labels. Chose the scrape-path option: it keeps the whole
change in this repo's `prometheus.yml` with no edit to EventHorizon's broker
config, and per-object's heavier cost is irrelevant for a two-queue pipeline.

### Decision: Drop the deliver-rate series rather than ship a non-existent metric
Rather than a permanently-empty "deliver rate" line (or a channel-level
substitute that can't filter to `events.work`), removed the series and stated
plainly in the panel description that RabbitMQ has no per-queue deliver counter.
Backlog is legible from depth + publish rate alone.

### Decision: Add the `events_failed_total` panel now (supersedes the deferral)
The prior session deferred this counter "until an alert needs it"; EventHorizon's
Phase 18 shipped it anyway as an always-on dead-letter-path counter, mooting the
deferral. Added an "Async Failure Rate" timeseries
(`sum(rate(events_failed_total[1m])) by (event_type)`) beside the TraceQL detail
table — the Prometheus panel carries the alertable rate, the TraceQL table the
per-failure forensics. The intended end state of the plan's "Prometheus for
alerts, spans for detail" split.

---

## Docs — README roadmap & cross-service plan reconciliation — 2026-06-16
Files: README.md, docs/OBSERVABILITY_MIGRATION_PLAN.md

Added a Status & roadmap section to the README and reconciled this repo's copy
of the migration plan against the (then) master copy in EventHorizon. No code
changed; the value was getting the *recorded* status to match reality across
four repos.

### Pattern: Completion state is owned by each service's own repo
Each phase's `phase-N-complete` marker is committed to *that* service's repo
(`<repo>/.observability/`); this hub repo holds only `phase-0-complete`.
Inferring cross-service status from the hub's own directory undercounted —
Synapse (Phase 1) and Sentinel (Phase 2) showed "not started" while both had
markers and shipped code. To report cross-service status, enumerate the *other*
repos' markers (`ls ~/dev/*/.observability/`), don't read the hub.

### Pattern: Verify a status claim against the artifact, not the convenient file
What flipped Synapse/Sentinel to done was reading the evidence — the
`phase-{1,2}-complete` markers, the `traceparent` injection in
`synapse-l4/src/clients/sentinel.py`, Sentinel's `TraceContextExtractor` +
spans, commit `2af565f`, the passing-test counts in the marker text. Each "done"
box maps to an inspected artifact, not an assumption.

### Pattern: Separate the deliverable axes a single "done" conflates
"Done" per the plan meant *instrumentation* DoD (cross-service trace in Tempo),
but a reader reads "done" as "there's a dashboard" — the most visible piece,
which Sentinel lacks (dashboards are Phase 5). Splitting the roadmap table into
independent **Instrumentation / Dashboard / Logs** columns makes a
fully-instrumented-but-undashboarded service legible at a glance.

### Anti-Pattern Avoided: Blind-copying a master doc and reintroducing a closed item
EventHorizon's copy was the most-updated (a superset with as-built notes for
Phases 0–3), but it still described the Prometheus RabbitMQ scrape job as an
*open* "belongs in observability" item — which this repo had already shipped.
A blind `cp` would re-open a closed item. Reconciliation ≠ overwrite: adopt the
superset, then patch the spots where the destination repo has moved past the
source. `diff` the two copies first to see exactly what differs.

### Challenge: A provisioned panel is not a flowing signal
The dashboard JSON has a "Recent Logs" panel querying
`{service_name="event-horizon"}` against Loki, and the README listed
"trace-correlated logs" as a feature — but EventHorizon ships *no* logs to Loki
(`grep -rli "exporter-logs-otlp\|LoggerProvider" EventHorizon/src` → nothing; the
marker kept `console.*`). The panel is wired-but-empty, "No data" until Phase 5
log export lands. A provisioned panel + a configured datasource proves the query
is wired, not that any series exists; verify the producing side before
documenting a signal as live.

### Challenge: Roadmap prose drifted out of sync with its own table
After the status table was edited to mark Phases 1–3 done, the intro lead-in
still read "the per-service instrumentation lands one repo at a time" — true when
written, now contradicting the table directly below it. Editing a status cell is
half the job; the surrounding narrative encodes a point-in-time assumption that
goes stale without erroring. Re-read the prose within a screen of any flipped
status.

### Decision: This repo's plan is canonical; sync up from services manually
The user designated `rhizome-lens/docs/OBSERVABILITY_MIGRATION_PLAN.md`
as canonical (2026-06-16). Service repos keep copies that may lag; changes are
synced *up* into the canonical copy manually as work happens, and services pull
the plan *from* here. Reverses the earlier treatment of EventHorizon's copy as
master.

### Decision: Document the empty Loki panels rather than delete them
The "Recent Logs" panels are correct Phase 5 scaffolding feeding a datasource no
service writes to yet. Kept them with an explicit "wired but empty — log export
is Phase 5, 'No data' expected" note and softened the feature description, rather
than removing and re-adding them later. Mirrors the existing RabbitMQ
"empty-in-this-window is expected" disclosure — same disclose-the-gap posture.

---

## Phase 0 (cont.) — arbiter-l8 joins the traced services (via cross-repo mirror) — 2026-07-03
Files: arbiter-l8/src/arbiter_l8/observability/, arbiter-l8/src/arbiter_l8/online/pipeline.py, arbiter-l8/src/arbiter_l8/online/judge.py

Mirrored from `arbiter-l8/docs/journal/arbiter-l8-2026-07-03T1916-otel-instrumentation.md`
(`cross_ref_id: arbiter-l8-2026-07-03T1916-otel-instrumentation`) — that
repo uses the newer per-entry `docs/journal/` directory format; this hub
keeps its own flat-file convention per this repo's local
`skills/journal-anki.md` copy, so the framing below is hub-shaped rather
than a verbatim copy.

arbiter-l8 (the standalone eval harness scoring Sentinel-L7 and
Synapse-L4 outputs) is now the fifth OTel-instrumented service in the
suite, following the same OTLP/HTTP-to-Collector convention as the other
four: `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4318`) with
`/v1/traces` and `/v1/metrics` suffixes, `OTEL_SERVICE_NAME` defaulting to
`arbiter-l8`.

### Anti-Pattern Avoided: Deferred SDK Initialization (Root-Span Fragmentation)
Before wiring arbiter-l8's tracer, checked whether Synapse-L4's suspected
"three traces instead of one" bug is a general Python-SDK-init-order
problem rather than a FastAPI-only quirk — relevant to this hub because any
future Python service in the suite would be at risk of the same bug.
Diagnosis: `synapse-l4/main.py` constructs the FastAPI app and registers
routes at import time, but defers `configure_logfire()` /
`instrument_fastapi(app)` into the `lifespan()` handler, which only runs
once Uvicorn starts serving. Starlette lazily builds and caches its ASGI
middleware stack on the first ASGI event it receives — including the
lifespan-startup event itself, which flows through the same top-level
`app.__call__` before instrumentation has run. The OTel/Logfire ASGI
middleware ends up attached after other middleware ordering has already
latched in, producing inconsistent root-span parenting. Same discipline
already documented for EventHorizon's Node SDK ("must come before any
instrumented module is imported") — generalizes across languages, not
Python-specific either, just easier to hit in a deferred-lifecycle-hook
framework pattern. arbiter-l8's `observability/tracing.py` /
`metrics.py` configure their providers as a plain import-time module-level
side effect instead of behind a lifecycle hook, avoiding the same trap.
**Not yet applied back to synapse-l4 itself** — flagged as a candidate fix
for that repo, not made in this session (out of scope for the arbiter-l8
task that produced this finding).

### Challenge: No live verification against this hub's own Collector
Unlike the other services' entries above, arbiter-l8's OTLP wiring was
**not** verified against a running Collector in the session that produced
it — Docker wasn't reachable from that WSL session. The instrumentation
logic itself (span names, parent/child nesting, exception status, counter
emission across the judge fallback chain) was verified with in-memory
span/metric exporters in arbiter-l8's own test suite, which is a
weaker claim than "trace confirmed visible in Tempo" for the other four
services. Per this repo's own "verify a status claim against the artifact"
pattern (above): treat arbiter-l8 as *instrumented, not yet confirmed
flowing* until someone runs the stack and checks Tempo/Prometheus for real.

---

## Phase 0 (cont.) — Sentinel-L7 MCP adapter: a reverse-engineered integration boundary — 2026-07-04
cross-ref: observability
cross_ref_id: arbiter-l8-2026-07-04T0819-sentinel-l7-adapter
Files: arbiter-l8/src/arbiter_l8/adapters/sentinel_l7.py, arbiter-l8/tests/test_sentinel_l7_adapter.py, arbiter-l8/README.md

Mirrored from `arbiter-l8/docs/journal/arbiter-l8-2026-07-04T0819-sentinel-l7-adapter.md`
(`cross_ref_id: arbiter-l8-2026-07-04T0819-sentinel-l7-adapter`) — that
repo uses the newer per-entry `docs/journal/` directory format; this hub
keeps its own flat-file convention, so the framing below is hub-shaped
rather than a verbatim copy. **Backfilled 2026-07-06**: this entry carried
`cross_ref: observability` in its source frontmatter from the day it was
written, but was never actually mirrored here until a punch-list review
caught the gap — see this hub's own `skills/journal-anki.md` re-sync note
for how the gap was found (a stale local skill copy, discovered while
looking for exactly this kind of drift).

Sentinel-L7 exposes no plain HTTP route for its compliance-analysis
integration boundary — only an MCP server (`Mcp::web('/mcp',
SentinelServer::class)`). Building arbiter-l8's adapter for it required
reading `vendor/laravel/mcp` source directly rather than assuming the MCP
spec in general, since Laravel's specific implementation choices aren't
guaranteed by the spec itself.

### Pattern: Verify the Wire Protocol Against the Framework's Source, Not the Spec
Three concrete, non-obvious findings from reading `vendor/laravel/mcp`
directly: tool names are kebab-case via `Str::kebab(class_basename(...))`
(`AnalyzeTransaction` → `analyze-transaction`), not the snake_case the
server's own human-readable instructions text uses; `tools/call` requires
no prior `initialize` handshake in this implementation —
`Server::handle()` dispatches directly to whichever method arrives, no
session state enforced; and `Response::json($result)` double-encodes, so
`result.content[0].text` must be JSON-decoded a second time to reach the
real payload. Every one of these would have produced a plausible-looking
but wrong client if assumed from the general MCP spec instead of the
actual framework code handling requests on the other side of this
integration boundary.

### Decision: Widen the Boundary's Output Instead of Scoring a Collapsed Boolean
The MCP tool on the other side of this boundary (`AnalyzeTransaction`)
only exposed `{source, is_threat, message, elapsed_ms}` —
`TransactionProcessorService::process()` computed a full `risk_level`/
`narrative`/`confidence`/`policy_refs` grading internally but discarded
all but a collapsed boolean before it reached this integration point.
Widened the boundary's own output (additive-only — new keys, existing
four untouched, backward-compatible with an already-warm production
cache via `??` fallbacks) rather than accepting a permanent measurement
ceiling on the arbiter-l8 side of the integration. Full Sentinel-L7
suite (312 tests) green before and after.

---

## Phase 0 (cont.) — arbiter-l8 confirmed flowing against a live Collector; Arbiter-L8 Service dashboard — 2026-07-23
Files: grafana/provisioning/dashboards/arbiter-l8-service.json, README.md

### Pattern: Verify a Status Claim Against the Artifact
Continuing this repo's own established discipline (see the Sentinel-L7 and
EventHorizon dashboard entries above): `arbiter-l8`'s OTel wiring had been
recorded as "instrumented, not yet confirmed flowing" since Docker wasn't
reachable in the session that built it. With the stack up
(`docker compose up -d`), that claim was checked directly rather than
upgraded on faith — queried Tempo's `/api/search` for
`resource.service.name="arbiter-l8"` and Prometheus's
`/api/v1/query` for `arbiter_l8_judge_outcome_total` /
`arbiter_l8_layer_latency_milliseconds_bucket` after generating real
traffic. Both returned populated series, so the status graduates from
🟡 to ✅ — a claim now backed by an observed artifact, not just code review.

### Decision: Drive the Real `evaluate_item` Pipeline, Not Synthetic Spans
`arbiter-l8`'s CLI (`arbiter_l8.cli:main`) only wires the offline
`run_eval()` harness — `online.pipeline.evaluate_item` has no CLI surface
by design, since it's meant to be called from a caller's own sampling
loop, not run standalone (per `docs/adr/0001-standalone-module.md`). Rather
than writing a throwaway script that emits spans directly via
`tracer.start_as_current_span(...)`, which would only prove the OTLP
transport works, a small driver script constructed real `EvalPrediction`
objects and called `evaluate_item(..., judge=JudgeCircuitBreaker())`
against the live stack — exercising the actual `heuristics_check` →
`judge_call` → (`ollama_attempt` / `flash_attempt` / `heuristics_fallback`)
fallback chain. This is a stronger verification: it confirmed both wire
delivery and that the instrumented code paths themselves fire as designed
(the run produced a genuine mix of `ollama` successes and
`heuristics_fallback` outcomes, not a fabricated single value).

### Decision: New Arbiter-L8 Service Dashboard, Not an Overview Addition
Followed the existing per-service dashboard convention (`sentinel-l7-
service.json`, `eventhorizon-service.json`) rather than folding panels into
the shared `overview.json`: a `arbiter-l8-service.json` with three
Prometheus panels (judge outcome rate by source, `%` scored by judge vs.
fallback, per-layer p95 latency from `arbiter_l8.layer.latency`) and two
Tempo TraceQL panels plus two Tempo tables (evaluation throughput/latency,
judge-chain exception events, recent evaluations) — mixing datasources
within one dashboard mirrors EventHorizon's own panel layout. Grafana's
file-provisioning watcher (`updateIntervalSeconds: 30` in
`grafana/provisioning/dashboards/dashboards.yaml`) picked it up with no
container restart needed.

### Challenge: No CLI Surface Meant Writing a One-Off Driver Script
`evaluate_item` isn't reachable from `arbiter-l8`'s own console script, so
confirming delivery required importing it directly against the repo's
`.venv` from an ad hoc script (kept outside both repos, in the session
scratchpad) rather than a documented, reusable command. Acceptable for a
one-time verification; a proper "smoke-test the online pipeline against a
live Collector" entrypoint is not something either repo currently exposes.
