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
