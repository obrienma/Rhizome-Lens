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
