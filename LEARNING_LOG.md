# Learning Log

---

## Phase 0 — Observability Infrastructure

### Patterns

**OTel Collector as central fan-out hub**
Q: How do you route a single OTLP stream to Tempo, Loki, and Prometheus simultaneously?
A: Define one pipeline per signal type in the Collector's `service.pipelines` block. Each pipeline shares the same `otlp` receiver but has its own exporter. The receiver feeds all three pipelines; the Collector handles the fan-out.

**Grafana auto-provisioning via filesystem provider**
Q: How do you avoid re-configuring datasources every time the Grafana container is recreated?
A: Mount YAML files into `/etc/grafana/provisioning/datasources/` and `/etc/grafana/provisioning/dashboards/`. Grafana reads them on startup and hot-reloads on change (`updateIntervalSeconds: 30`). No manual UI steps required.

**OTel Collector `health_check` extension**
Q: How do you verify the OTel Collector is ready inside the container?
A: Enable the `health_check` extension (`endpoint: 0.0.0.0:13133`) in the Collector config and list it under `service.extensions`. The extension logs `"Health Check state change" status: ready` when all pipelines are up. You can probe it from a sidecar or from the host — but NOT via Docker's `CMD-SHELL` healthcheck, because `otel-collector-contrib` is a distroless image with no shell (see Anti-Patterns).

**Tempo monolithic mode for local dev**
Q: When is Tempo monolithic mode appropriate vs. distributed?
A: Always for local dev. Monolithic runs distributor, ingester, querier, and compactor in a single process. Distributed mode is only justified for horizontal scaling in production.

**Named Docker volumes for signal storage**
Q: How do you persist Tempo WAL/blocks and Loki chunks across container restarts without bind-mounting into the working directory?
A: Use named volumes (`tempo-data`, `loki-data`). Data survives `docker compose restart` but is cleanly wiped by `docker compose down -v` — the right lifecycle for a dev stack.

**`tracesToLogsV2` wired on day zero**
Q: When should you configure trace-to-log correlation in Grafana?
A: At stack bootstrap, before any services are instrumented. Setting `tracesToLogsV2.datasourceUid` in the Tempo datasource provisioning YAML means one-click trace→log jump works the moment Phase 1 services ship both signals — no Grafana UI editing needed later.

**Optional chaining short-circuits its entire argument tree, not just the call**
Q: If `span` is `undefined`, does `span?.setAttributes({ key: expr() })` evaluate `expr()`?
A: No. Optional chaining short-circuits the whole chained expression from that point — including arguments to the optional call. A throwing or expensive `expr()` inside `span?.setAttributes(...)` never runs when there's no active span (e.g. in `app.inject()` tests), but runs every time under real OTel auto-instrumentation.

**Collector self-telemetry and the forwarded-metrics exporter are different endpoints**
Q: Is the OTel Collector's own operational metrics (e.g. `otelcol_receiver_accepted_spans`) available on the same `:8889` Prometheus exporter that carries app-sent OTLP metrics?
A: No. `:8889` (the `prometheus` exporter) only carries metrics applications send via OTLP. The collector's self-telemetry is a separate server (`service.telemetry.metrics.address`, default `localhost:8888`) and needs `0.0.0.0:8888` plus its own Prometheus scrape job.

**`sdk-node` + `auto-instrumentations-node` ships trace-correlated logs with zero logging code**
Q: EventHorizon has no log exporter package and no logging module, yet Loki has a live `event-horizon` stream with `traceid`/`spanid` on every line — how?
A: `@opentelemetry/sdk-node` 0.218.x with `auto-instrumentations-node` wires the Logs Bridge into Fastify's built-in pino logger and exports via OTLP automatically. Phase 3's task to "replace console.* with structured logging" was effectively delivered by the SDK version alone.

**Opt-in fault injection behind a default-zero rate**
Q: How do you make a dashboard's error-rate panels show realistic non-zero values without changing behavior for normal dev runs and tests?
A: Gate the fault behind an env var/CLI flag that defaults to `0` and is checked with `Math.random() < rate` *after* normal validation succeeds. At `rate = 0`, `Math.random() < 0` is always false, so the code path is provably inert by default — `npm test` and `npm run dev` are unaffected unless the flag is set. Pair a server-side 5xx knob (throw after validation) with a client-side 4xx knob (send a payload that fails schema validation) to get a realistic mixed-status traffic shape from one seed run.

---

### Anti-Patterns Avoided

**Using `otel/opentelemetry-collector` (core) instead of `contrib`**
Q: Why use the `contrib` collector image over `core`?
A: The `loki` exporter lives in contrib, not core. Using core silently omits the logs pipeline with no error at startup — the pipeline just doesn't exist. Always use `contrib` for any multi-backend setup.

**Loki schema v11 / BoltDB**
Q: Which Loki schema version should you use in Loki 3.x?
A: v13 with TSDB. v11 (BoltDB-Shipper) is deprecated in Loki 3.x and produces startup warnings that obscure real errors. v13/TSDB is the current default and the only forward-compatible choice.

**Setting Loki's schema `from` date to today or a future date**
Q: What happens if the Loki schema `from` date is today or in the future?
A: Loki refuses to ingest any data until that date is reached — the schema isn't yet "active." Always use a fixed past date (e.g., `2024-01-01`) so the schema is active on first boot.

**Exposing Tempo's internal OTLP port (4317) on localhost**
Q: Does Tempo's OTLP receiver port need to be mapped to localhost?
A: No. The Collector reaches Tempo via the Docker bridge (`tempo:4317`). Only port 3200 (Tempo HTTP API) needs localhost exposure for Grafana datasource queries. Publishing 4317 from Tempo would create a confusing second OTLP endpoint on localhost alongside the Collector's.

**`CMD-SHELL` healthcheck in a distroless image**
Q: What breaks when you use `CMD-SHELL` as the Docker healthcheck test form for a distroless container?
A: Docker injects `/bin/sh -c` to run the shell string. Distroless images have no `/bin/sh` — the exec fails immediately with `OCI runtime exec failed: exec: "/bin/sh": stat /bin/sh: no such file or directory` and Docker marks the container permanently unhealthy even when the process inside is fully running. Use `disable: true` if no probe binary is available in the image, or use `CMD` with a binary known to exist in the image.

**Anon Grafana auth without disabling the login form**
Q: `GF_AUTH_ANONYMOUS_ENABLED=true` is set — is that enough for frictionless local access?
A: It grants access but leaves the login button visible, which is confusing. Also add `GF_AUTH_DISABLE_LOGIN_FORM=true` to make the intent explicit.

**A "shared infra" port that collides with the most common per-project dev-server default**
Q: Grafana's compose default is `3000:3000`; many app dev servers (including EventHorizon) also default to `PORT=3000`. What breaks, and how visibly?
A: Whichever process binds the host port "wins" silently — `docker compose ps` still shows the container healthy (its healthcheck runs against its own internal localhost). `curl localhost:3000` can hit the wrong service entirely with no error. Shared cross-project infra should claim a distinctive port (`3300`), not the most commonly squatted one.

**Assuming a metric name's `_total` suffix without checking what's actually exported**
Q: A dashboard panel queries `rate(otelcol_receiver_accepted_spans_total[1m])` and shows "No data" with no error — why?
A: The metric is actually named `otelcol_receiver_accepted_spans` (no `_total`). Prometheus returns a valid empty result for a nonexistent metric, not an error — a panel can look fully configured and just permanently show nothing. Check `/api/v1/label/__name__/values` rather than assuming naming conventions.

**Reverse-engineering a running container's bundled frontend JS on a memory-constrained WSL2 host**
Q: Why did `docker compose exec grafana sh -c 'find ... | strings ...'`, a `docker compose cp` of a 368KB JS bundle, and a background `python3` regex scan — run together — crash the whole machine?
A: WSL2 runs as a single VM with a fixed memory ceiling (7.6Gi here). Several heavyweight container-introspection operations stacked concurrently exhausted it, crashing the VM and killing every Docker container across every project, not just the one being inspected. When the question is "what query shape does this datasource expect," query the datasource's own documented API directly (e.g. Tempo's `/api/search` on `:3200`) instead of disassembling the frontend that calls it.

---

### Challenges

**Commit signing server returned 400 when no git remote was configured**
The remote execution container was initialized as a fresh repo (not a clone), so no `origin` remote existed. Every `git commit` attempt failed with `signing server returned status 400` — the platform's signing server (`/tmp/code-sign`) requires a remote URL to authorize a signature. Discovered only after the commit was attempted; `git remote -v` should be the first check in any remote session.

Resolution: `git remote add origin <url>` before any commit.

Q: Why might git commit signing fail with HTTP 400 in a Claude Code remote session?
A: The platform signing server needs a configured remote origin to authorize the signature. A fresh `git init` repo with no remote will be rejected. Add the remote first.

**`otel-collector-contrib` is distroless — no shell, no wget**
During the first live smoke test, `docker compose ps` showed `otel-collector` as `unhealthy` despite the container emitting `"Everything is ready"` in its logs. `docker inspect` revealed the healthcheck was failing with `exec: "/bin/sh": stat /bin/sh: no such file or directory` — the image is based on scratch/distroless, not Alpine. The prior LL entry (now corrected) incorrectly assumed it was Alpine with `wget`. Fix: `healthcheck.disable: true` in `docker-compose.yml`.

Q: How do you diagnose a container that is `unhealthy` but its process logs show it's fully running?
A: Run `docker inspect <container> --format '{{json .State.Health}}'` and read the `Log[].Output` field. The exit code and message will pinpoint whether it's the probe itself that failed rather than the service.

**`docker info` succeeded but `docker compose up` failed — socket absent**
`docker info` returned valid output (Engine 29.3.1), suggesting Docker was available. But `/var/run/docker.sock` did not exist and Compose failed immediately with "no such file or directory." The CLI was connecting to a remote Docker daemon via TCP; Compose defaults to the socket path and doesn't inherit the TCP context. Stack verification had to be deferred to local.

Q: Can you trust `docker info` succeeding as proof that `docker compose up` will work?
A: No. The CLI may be connected to a remote daemon via TCP while Compose looks for the local socket. Always check `ls /var/run/docker.sock` explicitly.

**SSH and `gh` unavailable for `git push` in remote environment**
No `ssh` binary, no `gh` CLI, no `GITHUB_TOKEN` in environment. The SSH remote URL could not be used to push. Workaround was `git format-patch HEAD~1 --stdout` to produce a portable patch file for local application with `git am`.

Q: What's the fallback when SSH and gh CLI are both unavailable in a remote environment?
A: `git format-patch HEAD~1 --stdout > changes.patch` produces a self-contained patch. The recipient applies it with `git am changes.patch`, which replays the exact commit including message and authorship.

**`docker compose ps` showed Grafana healthy on `:3000`, but `curl localhost:3000` hit a different service entirely**
`ss -tlnp` showed the host's port 3000 listener belonged to EventHorizon's Fastify dev server, not docker-proxy — `curl localhost:3000/api/health` returned EventHorizon's 404 JSON. The container's healthcheck runs against its own internal localhost and is blind to host-level port conflicts.

Q: Does a container showing `healthy` with port `X:X` mapped in `docker compose ps` guarantee the host port actually routes to it?
A: No — verify with `ss -tlnp` (or inspect the actual response body) before trusting the `PORTS` column.

**`docker compose restart` failed after editing a bind-mounted config file (WSL2/Docker Desktop)**
After editing `prometheus.yml`, `restart` failed with `error mounting ".../docker-desktop-bind-mounts/Ubuntu/<hash>" ... no such file or directory` — Docker Desktop's cached bind-mount reference went stale once the underlying WSL2 file changed.

Q: What's the fix when `docker compose restart` fails on a stale `docker-desktop-bind-mounts` path after editing a mounted config file?
A: `docker compose up -d --force-recreate <service>` — re-resolves the bind mount instead of reusing `restart`'s cached reference.

**`curl -s` returned zero bytes for a PromQL query with `[5m]` in it, with no visible error**
`curl -s '.../api/v1/query?query=rate(metric[5m])'` produced empty output, which then failed JSON parsing downstream. Cause: curl's URL-globbing tries to interpret `[5m]` as a range expression and errors before sending the request — `-s` suppressed the error message.

Q: A `curl -s` to a JSON API returns completely empty output with no error — what's a non-obvious cause?
A: Unescaped `[...]`/`{...}` in the URL triggers curl's globbing parser, which can fail pre-request. Use `-g`/`--globoff`, or `-G --data-urlencode`, for PromQL/TraceQL range-vector queries.

**Phase 3's "44 tests pass" coexisted with a 500 on every real request**
`event.routes.ts` called `Buffer.byteLength(request.body as string)` inside `span?.setAttributes({...})`. `app.inject()` tests have no active span, so the optional chain short-circuits and the throwing expression never runs — 44/44 pass. Under `npm run dev` with real HTTP auto-instrumentation, every `POST /events` hit the active-span branch and threw `ERR_INVALID_ARG_TYPE`, 500-ing 100% of seeded traffic.

Q: Why can a fully-passing test suite coexist with code that 500s on every real request?
A: `obj?.method(arg)` skips evaluating `arg` too when `obj` is nullish. If tests never produce a non-null `obj` (here, no active span without real OTel instrumentation), a buggy `arg` is structurally unreachable in tests but fully reachable in production.

**Grafana 11.2.0's bundled Tempo plugin rejects `queryType: "traceqlSearch"` via `/api/ds/query`**
Q: A Tempo datasource query body with `queryType: "traceqlSearch"` (or `"traceql"`, or `""`) sent to `/api/ds/query` returns "unsupported query type" from the `tsdb.tempo` logger — what query types does this endpoint actually support?
A: Only `"traceId"` (look up a single trace by hex ID) was confirmed working via `/api/ds/query` on this version. TraceQL *search* queries (`tableType: "spans"` / `"traces"`) are issued by Grafana's frontend via a separate `CallResource` route (`/api/datasources/uid/tempo/resources/search`), not the `QueryData` endpoint. To validate a TraceQL search query without a browser session, hit Tempo's own `/api/search` directly — same TraceQL syntax (`q=<query>&limit=N`), no Grafana auth/session involved.

---

### Decisions

**Collector `contrib` image over `core`**
`otel/opentelemetry-collector-contrib:0.105.0`. The loki exporter is contrib-only; core silently drops the logs pipeline. Contrib is the safe default for any multi-backend setup.

**Tempo monolithic mode**
Single-process monolithic over distributed. Local dev has no horizontal scaling requirement; monolithic is faster to start and has a simpler config surface.

**Loki schema v13 / TSDB over v11 / BoltDB**
v13/TSDB is the Loki 3.x default. v11 works but emits deprecation warnings at startup that would mask real errors during Phase 1 instrumentation debugging.

**`block_retention: 1h` in Tempo**
Short retention keeps disk usage negligible during iterative local testing. Easy to extend per-service in Phase 1+ if needed.

**Local block storage only — no S3/GCS**
All trace and log data lives in named Docker volumes. Appropriate for local dev; production config in a later phase would introduce object storage.

**Loki `from: 2024-01-01` (fixed past date)**
A future or current date causes Loki to silently refuse ingestion. A fixed historical date guarantees the schema is always active on first boot with no configuration drift over time.

**`GF_AUTH_DISABLE_LOGIN_FORM=true` alongside anon auth**
Anon auth alone leaves the login UI visible. Disabling the form makes the local-only intent explicit and avoids confusion for anyone opening the stack for the first time.

**`tracesToLogsV2` provisioned at stack bootstrap**
Wired the Tempo→Loki correlation link on day zero. The plumbing is in place before Phase 1 services exist; no Grafana UI editing needed when traces and logs start flowing.

**`healthcheck.disable: true` for otel-collector-contrib**
Rather than switching to a different base image or adding a sidecar probe, the healthcheck was disabled. Rationale: the `health_check` extension inside the container still reports readiness via its own endpoint; Docker's healthcheck status is only cosmetic for local dev. If a real liveness gate is needed (e.g. `depends_on: condition: service_healthy`), the correct fix is to build a thin wrapper image or switch to the non-distroless variant — not to paper over it with a bogus probe.

**`{"partialSuccess":{}}` is the correct OTLP success response**
OTLP HTTP exporters return `{"partialSuccess":{}}` on full success, not `{}`. A non-empty `partialSuccess` object (with `rejectedSpans` + `errorMessage`) indicates partial rejection. Documented in README smoke-test section.

**Grafana → host port `3300`**
Rejected `3001` (the obvious fallback, also commonly squatted) for a more distinctive port. EventHorizon and other services keep their existing default ports unchanged — shared infra moves, not the per-project services.

**Collector self-telemetry on `0.0.0.0:8888` as a separate Prometheus job (`otel-collector-internal`)**
Kept the existing `otel-collector` job (`:8889`, forwarded app metrics) untouched and added a second job, since the two endpoints have different metric namespaces and different operational meaning (collector health vs. application signal).

**Added Tempo (`tempo:3200/metrics`) as its own Prometheus scrape job**
The Phase 0 dashboard's "Tempo Spans Ingested/sec" panel already had the correct query (`tempo_distributor_spans_received_total`) — the only gap was the missing scrape target. No dashboard change needed for that panel, only `prometheus.yml`.

**Fixed the EventHorizon `Buffer.byteLength` bug on discovery rather than deferring**
Found during live smoke-testing of the Phase 0 stack against Phase 3, not during Phase 0 work itself — but it blocked every ingest request. Fixed directly in EventHorizon (`a9e2e4a`) rather than just logged, since a non-functional system under test isn't useful for validating the observability stack.

**Built the "EventHorizon Service" dashboard as an early, narrow slice of Phase 5**
The migration plan defers Phase 5 (dashboards) "until you have a concrete need (e.g. dashboard screenshots for portfolio site)" — that need arrived. Rather than pulling forward all of Phase 5, only a per-service RED + Node.js runtime-health dashboard (`grafana/provisioning/dashboards/eventhorizon-service.json`) was built, using metrics `auto-instrumentations-node` already exports via OTLP (`http_server_duration_milliseconds_*`, `db_client_connections_usage`, `nodejs_eventloop_delay_*`, `v8js_memory_heap_used_bytes`). The plan's TraceQL/wide-span business dashboards (queries over `event.type`/`classification`) remain deferred — this slice answers "is the service healthy," which is a different question from "what is the service doing."

**"Recent Traces" panel written from direct-Tempo-API validation; rendering verification deferred to the browser**
After the WSL crash ruled out further Grafana-internals investigation, panel id 8 ("Recent Traces", `eventhorizon-service.json`) was written using the `queryType: "traceqlSearch"` / `tableType: "spans"` shape Grafana's own Tempo query editor produces for a search query — but the TraceQL itself (`{resource.service.name="event-horizon" && kind=server} | select(.http.status_code, .http.method, .event.type, status)`) was validated by querying Tempo's `/api/search` directly, confirming it returns per-span `http.status_code`, `http.method`, `event.type`, and OTel `status` for every recent request, including the live-injected 422s and 500s. Whether Grafana's frontend renders this panel as expected is left for the user to confirm at `http://localhost:3300`; if it shows "No data", the documented fallback is `tableType: "traces"` with the simpler query `{resource.service.name="event-horizon"}`.

---

## Phase 0 (cont.) — EventHorizon dashboard expansion: RabbitMQ scrape, throughput, async-failure panels

### Patterns

**Cross-compose-project scrape via the host gateway**
Q: Prometheus runs in this stack's `observability` network; RabbitMQ runs in EventHorizon's separate compose project. How does one scrape the other without merging the two stacks?
A: Reach it through the host, not container DNS. Target `host.docker.internal:15692` and add `extra_hosts: ["host.docker.internal:host-gateway"]` to the Prometheus service. `host-gateway` is a Docker-reserved alias resolving to the host's gateway IP. The alternative — a shared external Docker network referenced by both compose files — couples the two projects' lifecycles; the host-gateway hop keeps them independent.

**`host.docker.internal` is not automatic on Linux/WSL2**
Q: The same `host.docker.internal:15692` target "just works" on a teammate's Mac but resolves to nothing on WSL2 — why?
A: Docker Desktop (Mac/Windows) injects the `host.docker.internal` alias into every container automatically. Native Linux / WSL2 engines do not — it does not exist unless you add the `host-gateway` `extra_hosts` mapping yourself. Same compose file, different behaviour per engine.

**One panel, two units: dual-axis via a `byRegexp` field override**
Q: Queue depth is a count; publish/deliver throughput is a rate (msg/s). How do you show both on a single timeseries panel without one flattening the other?
A: Default the panel unit to `short` (counts), then add a field override matching the rate series (`byRegexp: /.*rate.*/`) that sets `custom.axisPlacement: right` and `unit: cps`. Grafana renders a second Y axis for just those series. Legend naming is load-bearing — the override matches on series name.

### Anti-Patterns Avoided

**Unlabelled `rate()` on a per-queue counter**
Q: Why scope `rate(rabbitmq_queue_messages_published_total{queue="events.work"}[1m])` to one queue instead of the bare `rate(rabbitmq_queue_messages_published_total[1m])`?
A: `rabbitmq_prometheus` exports the counter per queue, so the unlabelled form returns one series per queue (work, dead, any others) — cluttering the right axis with DLQ/throwaway series that don't speak to worker backlog. Backlog detection only cares about the work queue's publish-vs-deliver gap.

**`json.dump` round-trip to reorder panels**
Q: The panels needed reordering so array order matches on-screen order — why not load the JSON, sort `panels` by `gridPos`, and re-dump?
A: The dashboard file uses hand-curated inline objects (`{ "type": "loki", "uid": "loki" }`) that `json.dump(indent=2)` would explode into multi-line form, turning a two-panel move into a whole-file diff. Moved the blocks with targeted text edits and validated with a read-only `json.load` instead — minimal diff, formatting preserved.

### Challenges

**The new RabbitMQ scrape target legitimately shows `DOWN` from this repo alone**
The `rabbitmq` job can only go `UP` once the EventHorizon repo (a) enables the bundled `rabbitmq_prometheus` plugin on its broker and (b) publishes `15692` on the host. Both live in the other repo, so committing this change leaves a red target in Prometheus until that side is wired — expected, not a misconfiguration. Documented in the README so a future reader doesn't "fix" a working config.

Q: A freshly-added Prometheus scrape target shows `DOWN` immediately after deploy — when is that expected rather than a bug?
A: When the scraped service lives in a different compose project/repo that hasn't yet exposed the metrics endpoint. The scrape config declares intent; the target stays down until the other side ships the port + exporter.

### Decisions

**Host-gateway bridge over a shared external Docker network**
Chose `extra_hosts: host.docker.internal:host-gateway` + a host-port target over defining a shared external network referenced by both compose files. Rationale: the two stacks stay lifecycle-independent (either can be torn down without breaking the other's network reference); the cost is the Linux-specific `extra_hosts` line, documented inline.

**Dual-axis RabbitMQ panel to hold at four new panels**
The spec listed four metric groups but six queries across two unit families (counts vs rates). Rather than spawn a fifth panel, folded queue/DLQ depth (left) and publish/deliver rate (right) into one dual-axis "RabbitMQ Queue Health" panel — which also reads as a single question ("is the queue backing up?"). Kept the total to exactly four additive panels.

**Async failures as a TraceQL panel, not a new metric (yet)**
Closed the "HTTP 5xx panel can't see post-202 worker/DLQ failures" gap with a Tempo table over `status=error` spans — no new instrumentation. Deferred the optional `events_failed_total{event_type}` counter until there's a concrete alerting need, consistent with the plan's "reserve Prometheus counters for alerts" posture and "wait until it hurts."

**Left panel `id`s non-sequential after the array reorder**
Panel ids read 1–6, 9–12, 7–8 after moving logs/traces below the new panels. Ids are stable identifiers nothing references by number; resequencing would add churn for zero functional gain, so they were left as-is — array order and `gridPos` (the rendering source of truth) both match the on-screen layout.

---

## Phase 0 (cont.) — verifying the RabbitMQ panels against the live exporter

Once EventHorizon's Phase 18 brought the `rabbitmq_prometheus` source live (`:15692` → HTTP 200), the panels written blind in the previous step could finally be checked against reality. Two of the queries were wrong — verification caught what the "don't assume a metric name" anti-pattern predicts.

### Patterns

**`or vector(0)` to render a counter's "never incremented" state as 0 instead of "No data"**
Q: An `events_failed_total` rate panel shows "No data" when there have been zero failures — healthy, but ambiguous (looks identical to a broken query). How do you make it read a flat 0?
A: Append `or vector(0)` so an empty result falls back to a 0-valued series — the same idiom the 5xx panel uses (`OR on() vector(0)`). Caveat for *grouped* queries: `vector(0)` has an empty label set, so when the left side is non-empty, `or` appends the 0-series *alongside* the real per-label lines. Grafana renders that empty-label series in the legend as **`unknown`** (not blank), which reads like a real failure type and is misleading; `or label_replace(vector(0), "<label>", "none", "", "")` labels it `none` instead.

**But the baseline is only worth it before the counter's first increment.** A Prometheus counter series persists once it has been exposed at least once — so after the first failure, `sum(rate(events_failed_total[1m])) by (event_type)` is *never* empty again (it reports the real type at 0 when quiet, not "No data"). At that point the `or vector(0)` baseline is pure clutter: a permanent extra line beside the real data. Lifecycle rule: use the baseline only for counters that may never have incremented in a given environment; drop it once the metric is reliably present. We added it, watched `events_failed_total{event_type="unknown"}` start incrementing for real, then removed it — the panel now shows just the live series.

**A real signal hid inside the "unknown" legend entry.** The yellow `unknown` line was not the empty-label baseline — `events_failed_total` genuinely carries `event_type="unknown"` (146 and climbing), because EventHorizon's dead-letter path can't classify a message that failed *before* it could be parsed. Lesson: don't reflexively "fix" an `unknown`/`none` legend entry as a cosmetic artifact — query the raw series first (`curl .../api/v1/query?query=<metric>`) to tell a rendering artifact apart from real data wearing an ugly label.

**The fix for an uninformative grouping label was a query change, not a code change.** `event_type="unknown"` is *truthful* for pre-parse poison messages — the worker genuinely doesn't know the type. The useful dimension was a second label the counter already carried: `failure_reason="parse_error"`. So the panel was regrouped `sum(rate(events_failed_total[5m])) by (failure_reason)` with legend `{{failure_reason}}` — no EventHorizon change. Lesson: when a series' obvious grouping label is uniform-and-useless, enumerate its *other* labels before requesting an instrumentation change; the dimension you want may already be there. (`event_type` is still the right group for *processed* events, where it's populated — only the *failure* path is type-blind.)

**Adding a label retroactively leaves a ghost "value" series in `by`-grouped panels**
Q: After regrouping the panel `by (failure_reason)`, the legend showed two lines — a green **value** for older data and `parse_error` for newer. Same query the whole range; why two series?
A: The `failure_reason` label was *added* partway through the visible window. Samples from before it existed have no `failure_reason`, so `by (failure_reason)` buckets them into an empty-labeled series; `{{failure_reason}}` resolves to empty, and Grafana names a nameless series **`value`** (its default value-column label). It's not a bug — it's the metric's own history at the label-introduction boundary, confirmed with a `query_range`: the `<ABSENT>` series ends exactly where `parse_error` begins. It scrolls off on its own as the window advances, or filter it immediately with a `{failure_reason!=""}` matcher (which excludes label-absent series, since absent ≡ `""` in PromQL). Kept the matcher permanently so the panel only ever charts reasoned failures.

**`sum()` to collapse per-object RabbitMQ counters to one line**
Q: `rate(rabbitmq_queue_messages_published_total{queue="events.work"}[1m])` on the per-object endpoint can return several series — why, and how do you get one line?
A: Per-object counters carry `channel`, `exchange`, and `queue_vhost` labels beyond `queue`, so multiple producer channels yield multiple series. Wrap in `sum(rate(...))` to aggregate them into a single publish-rate line, since the panel only cares about per-queue throughput, not per-channel.

### Anti-Patterns Avoided

**Scraping `rabbitmq_prometheus`'s default `/metrics` when you need per-queue series**
Q: A `RabbitMQ Queue Health` panel filters `rabbitmq_queue_messages{queue="events.work"}` but shows nothing even though the exporter is live and returning data — why?
A: The default `/metrics` endpoint is **aggregated**: it sums every queue into a single label-less `rabbitmq_queue_messages` total, carrying zero `queue=` labels (verified: `grep -c 'queue=' → 0`). Per-queue series live only on `/metrics/per-object` (or require `prometheus.return_per_object_metrics = true` broker-side). A `{queue="..."}` filter against the aggregated endpoint matches nothing, silently. Set `metrics_path: /metrics/per-object` on the scrape job.

**Charting `rabbitmq_queue_messages_delivered_total` — a metric that does not exist**
Q: The spec paired `rate(...published_total)` with `rate(...delivered_total)` for a publish-vs-deliver view. Why does the deliver series never render?
A: There is no `rabbitmq_queue_messages_delivered_total`. The `rabbitmq_queue_messages*` family has `_published_total` but no queue-level delivered counter — delivery is tracked per *channel* (`rabbitmq_channel_messages_delivered_total`), not per queue. Confirmed by enumerating `# TYPE rabbitmq_queue_messages*`. The series was dropped rather than shipped as a permanent "No data" line; backlog is read from depth trend + publish rate + the app-side `events_processed_total`.

### Challenges

**Couldn't fully verify per-queue series because no queues existed yet**
`rabbitmq_queues 0` / `rabbitmq_connections 0` — EventHorizon's worker wasn't connected, so `events.work` / `events.dead` weren't declared and no per-queue series existed to inspect. The `queue` label *name* is RabbitMQ-documented (high confidence); the label *values* can only be confirmed once the worker runs. Same root cause left the collector's `:8889` with no `events_processed_total` / `events_failed_total` / `eventhorizon_change_stream_lag_milliseconds`: the pipeline is healthy, but nothing emits while the app is down.

Q: The exporter is up and returns 200, but the per-queue series you want aren't there — bug or expected?
A: Expected if `rabbitmq_queues` is `0`. RabbitMQ only exposes per-object series for objects that currently exist; an idle broker with no declared queues has nothing per-queue to report. Verify label *values* against a running producer, not an idle broker.

**The running Prometheus was serving a stale config**
After committing the `rabbitmq` scrape job, `/api/v1/targets` listed only `otel-collector`, `otel-collector-internal`, `tempo` — no `rabbitmq`. The job was on disk but the already-running Prometheus had not reloaded it. Editing `prometheus.yml` does not hot-apply; the process needs `--force-recreate` (the documented WSL2-safe reload) or a `/-/reload`. A scrape config can be correct on disk and absent from the live instance simultaneously.

Q: You added a scrape job and the target isn't in `/api/v1/targets` — first thing to check?
A: Whether the running Prometheus actually reloaded the file. The config on disk and the config in memory are independent; `docker compose up -d --force-recreate prometheus` re-reads it.

### Decisions

**Scrape `/metrics/per-object` over enabling `return_per_object_metrics` broker-side**
Both expose per-queue labels. Chose the scrape-path option because it keeps the entire change in *this* repo (`prometheus.yml`) with no edit to EventHorizon's broker config — and per-object's cost (it's heavier with thousands of objects) is irrelevant for a two-queue pipeline.

**Dropped the deliver-rate series instead of shipping a non-existent metric**
Rather than leave a permanently-empty "deliver rate" line (or invent a channel-level substitute that can't be filtered to `events.work`), the series was removed and the panel description now states plainly that RabbitMQ has no per-queue deliver counter. Backlog is legible from depth + publish rate without it.

**Added the `events_failed_total` Prometheus panel now that the counter is real (supersedes the earlier deferral)**
The prior step deferred this counter "until an alert needs it." EventHorizon's Phase 18 shipped it anyway as an always-on dead-letter-path counter, so the deferral is moot — added an "Async Failure Rate" timeseries (`sum(rate(events_failed_total[1m])) by (event_type)`) beside the TraceQL detail table. The Prometheus panel carries the alertable rate; the TraceQL table carries the per-failure forensics. This is the intended end state of the plan's "Prometheus for alerts, spans for detail" split.

---

## Docs reconciliation — README roadmap + cross-service plan sync

Added a Status & roadmap section to the README and reconciled this repo's copy of the migration plan against the master copy in EventHorizon. No code changed; the value was in getting the *recorded* status to match reality across four repos.

### Patterns

**Per-service completion state lives in each service's own repo, not centrally**
Q: This is the shared observability repo. To report which services are instrumented, why is reading this repo's own `.observability/` directory the wrong move?
A: Because each phase's completion marker (`phase-N-complete`) is committed to *that phase's service repo*, by design — the plan says "write `.observability/phase-N-complete` in the repo you just finished." This repo only holds `phase-0-complete` (its own phase). Inferring status from the central repo undercounted: it showed Synapse (Phase 1) and Sentinel (Phase 2) as "not started" when both had markers + shipped code in `synapse-l4/` and `sentinel-l7/`. To report cross-service status, enumerate the *other* repos' markers (`ls ~/dev/*/.observability/`), don't read the hub.

**Verify a status claim against the artifact, not against the most convenient nearby file**
Q: What concretely flipped Synapse and Sentinel from ⬜ to ✅ in the roadmap?
A: Reading the actual evidence: the `phase-1-complete` / `phase-2-complete` markers, the `traceparent` injection in `synapse-l4/src/clients/sentinel.py`, the `TraceContextExtractor` + spans in Sentinel, commit `2af565f`, and 45/44 passing tests recorded in the marker text. Each "done" box maps to an inspected artifact, not to an assumption.

**Separate the deliverable axes that a single "done" silently conflates**
Q: Marking Sentinel "✅ done" was technically true per the plan yet misleading. Why, and what was the fix?
A: "Done" meant the *instrumentation* Definition of Done (cross-service trace live in Tempo) — but a reader reasonably reads "done" as "there's a dashboard," the most visible piece, which Sentinel lacks (dashboards are Phase 5). The fix was to split the roadmap table into two independent columns — **Instrumentation** and **Dashboard** — so a fully-instrumented-but-undashboarded service is legible at a glance, and to state the definition of "done" explicitly above the table.

### Anti-Patterns Avoided

**Blind-copying the master plan and reintroducing a resolved item**
Q: EventHorizon holds the most-updated plan (a strict superset with as-built notes for Phases 0–3). Why not just `cp` it over this repo's copy and stop?
A: Because the master copy described a "Cross-repo open item (belongs in rhizome-observability): the Prometheus scrape job for `rabbitmq_prometheus` is the one remaining step" — which *this* repo had already shipped (the `rabbitmq` job is in `prometheus.yml`, host-gateway, `/metrics/per-object`). A blind copy would have re-opened a closed item. Reconciliation ≠ overwrite: adopt the superset, then patch the spots where the destination repo has moved past the source's knowledge. Diffed the two copies first (`diff`) to see exactly which regions differed before deciding what to keep.

### Challenges

**The "is Sentinel actually done?" question couldn't be answered from inside this repo**
The EventHorizon master plan asserted Phase 2 complete with very specific as-built notes (ADR-0024, SDK 1.14.0, 45 tests). Plausible, but asserting it in this repo's README on the strength of another repo's doc would be repeating a claim, not verifying it. Resolved by checking `sentinel-l7/.observability/` directly — the `phase-2-complete` marker (dated Jun 6) was there, so the claim held.

Q: A doc in repo A says a phase in repo B is complete. Before propagating that into repo C's README, what's the minimum check?
A: Look at repo B's own completion marker / code, not just repo A's claim about it. Docs about other repos are second-hand until the artifact is confirmed.

### Decisions

**Adopted the architecture-doc signal-flow diagram as the README's top diagram**
The README's original diagram showed a generic "Services (future phases)" box; the architecture doc's version names all four source services (synapse-l4, sentinel-l7, EventHorizon, invoicer) feeding the collector. Replaced the README's with the named-service version — the four-language story is the headline, and the diagram should show it. The collector-port detail it dropped (`:8889` forwarding) is still covered in the Port reference table.

**Reconciled by adopting EventHorizon's plan as canonical, then patching one stale cross-repo item**
EventHorizon's copy is the working master (it accreted as-built notes phase by phase). This repo's `docs/` copy is a downstream mirror. Decision: bring the mirror in line with the master wholesale, with a single edit flipping the RabbitMQ-scrape "open item" to "resolved here" — because that's the one fact this repo owns more authoritatively than EventHorizon does.

### Challenges (cont.) — the roadmap prose drifted out of sync with its own table, and a dashboard claimed a signal it never received

Two accuracy bugs surfaced after the roadmap table was edited but the surrounding prose wasn't.

**The intro text contradicted the table it introduced.** The "Status & roadmap" lead-in still read "the backend (Phase 0) is done; the per-service instrumentation lands one repo at a time" — written when nothing else was done — while the table directly below now marked Phases 1–3 instrumentation ✅. Editing a status table is only half the job; the narrative framing around it encodes a point-in-time assumption that silently goes stale. Lesson: when you flip a status cell, re-read the prose within a screen of it for tense/framing that assumed the old state.

Q: You update a status table to mark several rows done. What's the easy-to-miss follow-up?
A: The prose around the table. Intro sentences and sequencing notes often say "X is the upcoming work" — true when written, false once X ships. They don't error or fail a test; they just quietly contradict the table.

**A dashboard panel existed, so the docs claimed the signal — but nothing fed it.** The EventHorizon dashboard JSON has a "Recent Logs" panel querying `{service_name="event-horizon"}` against Loki, and the README's dashboard table listed "trace-correlated logs" as a feature. But EventHorizon ships **no** logs to Loki: `grep -rli "exporter-logs-otlp\|LoggerProvider" EventHorizon/src` → nothing; the phase-3 marker explicitly kept `console.*` and deferred pino. The panel is wired-but-empty — it renders "No data" forever until Phase 5 log export lands. A provisioned panel is a *claim about intent*, not evidence the signal flows. Same trap as the earlier "don't assume a metric name exists" anti-pattern, one level up: don't assume a panel has data just because it's on the board.

Q: A dashboard has a logs panel and the datasource is configured. Is it safe to document "trace-correlated logs" as a working feature?
A: No — verify something actually *emits* those logs into the datasource. A panel + a datasource proves the query is wired, not that any series exists. Check the producing side (`grep` the service for a logs exporter / SDK logs pipeline), or query the datasource directly, before describing it as live.

### Decisions (cont.)

**Documented the empty Loki panels as a stated caveat rather than deleting them**
The "Recent Logs" panels (OTel Overview + EventHorizon) feed from Loki, which no service writes to yet. Options were: remove the panels, or keep them and disclose. Kept them with an explicit "wired but empty — log export is Phase 5, 'No data' is expected" note next to the dashboard table, and softened the feature description from "trace-correlated logs" to "a *Recent Logs* panel (Loki)." Rationale: the panels are correct scaffolding for Phase 5 and removing/re-adding them is churn; the honest fix is to label the gap, not hide it. Mirrors the existing RabbitMQ "empty panels in that window are expected" note — same disclose-the-gap posture.

**Named the early dashboards as pulled-ahead in the prose**
Rather than let the table's two ✅ dashboard cells (Phase 0, Phase 3) silently contradict "dashboards are Phase 5," the intro now says both were *pulled forward ahead of Phase 5*, EventHorizon's built out of order alongside its instrumentation. Keeps the "instrumentation ≠ dashboard, dashboards lag" model intact while accounting for the two that landed early.
