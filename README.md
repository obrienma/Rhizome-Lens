# 📊 Rhizome Lens

A self-contained, local-runnable **observability backend** built on [OpenTelemetry](https://opentelemetry.io/) and the Grafana "pillar" stack: an OTel Collector that ingests traces, logs, and metrics over OTLP and fans them out to **Tempo** (traces), **Loki** (logs), and **Prometheus** (metrics), all visualized in **Grafana**. A single `docker compose up` brings up the whole stack — no cloud account, no managed service.

It's the shared telemetry backend for a four-service, four-language migration to OpenTelemetry (TypeScript, Python, PHP, and Ruby). The headline goal is **distributed tracing that follows a single request across both service boundaries and async boundaries** — Redis Streams and RabbitMQ — so you can see one trace span four codebases. This repo is infrastructure only; the services that emit to it live in their own repositories (see the [roadmap](#-status--roadmap)). A fifth, auxiliary consumer — `arbiter-l8` (a standalone Python eval harness, outside the core migration's scope) — also targets this Collector; see its row in the status table below.

```
[synapse-l4  (Python/FastAPI)]  ─────┐
[sentinel-l7 (Laravel/PHP)   ]  ─────┤  OTLP/gRPC :4317
[EventHorizon (TS/Fastify)   ]  ─────┤  OTLP/HTTP :4318
[Ledger-L5   (Python/FastAPI)]  ─────┘
                                    │
                           ┌────────▼──────────┐
                           │  otel-collector   │
                           │  (fan-out hub)    │
                           └──┬──────┬─────┬───┘
                              │      │     │
                           traces  logs  metrics
                              │      │     │
                      ┌───────▼┐  ┌──▼──┐ ┌▼───────────┐
                      │ Tempo  │  │Loki │ │ Prometheus │
                      │ :3200  │  │:3100│ │  :9090     │
                      └───┬────┘  └──┬──┘ └─┬──────────┘
                          │          │      │
                          └──────────▼──────┘
                                     │
                              ┌──────▼──────┐
                              │   Grafana   │
                              │   :3300     │
                              └─────────────┘
```
> [!TIP]
> EventHorizon telemetry with synthetic errors  — generated via fault injection for dashboard demo traffic.
<img width="750" alt="EventHorizon-Grafana" src="https://github.com/user-attachments/assets/1955b801-848e-4aed-acb1-6f5934252ad0" />

---

## 🗺️ Status & roadmap

**Where things stand:** Phase 0 (the backend) and instrumentation for three of the four services — Synapse, Sentinel, EventHorizon — are done. What's left is the fourth service (Ledger-L5) and the Grafana dashboards.

Each phase has three independent axes that land at different times, tracked as separate columns: **instrumentation** (traces + context propagation across async boundaries, verified in Tempo), **dashboard** (a Grafana view — see [Dashboards](#-dashboards)), and **logs** (shipped to Loki). A service can be fully instrumented yet have no dashboard and no logs.

Legend: ✅ done · 🟡 in progress · ⬜ not started · — n/a

| Phase | Component | Repo | Instrumentation | Dashboard | Logs → Loki |
|---|---|---|---|---|---|
| 0 | Observability backend (Collector + Tempo + Loki + Prometheus + Grafana) | `rhizome-observability` (this repo) | ✅ done | ✅ OTel Overview | ✅ sink ready |
| 1 | Synapse-L4 | `synapse-l4` (Python/FastAPI) | ✅ done | ⬜ none yet | ⬜ planned |
| 2 | Sentinel-L7 | `sentinel-l7` (Laravel/PHP) | ✅ done | ⬜ none yet | ⬜ planned |
| 3 | EventHorizon | `EventHorizon` (TypeScript/Fastify) | ✅ done | ✅ EventHorizon Service | ⬜ planned |
| 4 | Ledger-L5 (Ruby invoicer) | `Ledger-L5` (Ruby/Rails) | ⬜ not started | ⬜ none yet | ⬜ planned |
| 5 | Logs & dashboards polish | all | — | 🟡 early slices | ⬜ planned |
| — | arbiter-l8 (eval harness, auxiliary — outside core migration scope) | `arbiter-l8` (Python) | 🟡 coded, unconfirmed | ⬜ none yet | ⬜ planned |

> **Sequencing note:** the plan orders the per-service instrumentation Synapse → Sentinel → EventHorizon → invoicer (Synapse first because Logfire is already OTel; Sentinel next to prove the first cross-service link; EventHorizon was done out of order as the independent pipeline). **Instrumentation for Phases 1–3 is complete** — the headline Synapse → Sentinel cross-service trace and EventHorizon's four-stage trace are both live in Tempo. The remaining work is **Phase 4 (Ledger-L5 invoicer)** and **Phase 5 dashboards** — only Phase 0 and EventHorizon have a dedicated dashboard so far; Synapse and Sentinel emit signals but have no dashboard yet. See [`docs/OBSERVABILITY_MIGRATION_PLAN.md`](docs/OBSERVABILITY_MIGRATION_PLAN.md) for the full rationale and pause checkpoints.

### Phase 0 — Observability backend (this repo) ✅ — dashboard: OTel Overview

- [x] `docker-compose.yml` brings up Collector, Tempo, Loki, Prometheus, Grafana
- [x] Collector receives OTLP on `:4317` (gRPC) and `:4318` (HTTP), exports to Tempo/Loki/Prometheus
- [x] Grafana auto-provisions all three datasources + a starter **OTel Overview** dashboard
- [x] Synthetic-trace smoke test verified end-to-end (curl → Collector → Tempo → Grafana)
- [x] `.observability/phase-0-complete` committed

### Synapse-L4 (Phase 1) — `synapse-l4` ✅ instrumented · ⬜ no dashboard

- [x] Point Logfire's OTLP exporter at the local Collector (Logfire retained as optional secondary exporter)
- [x] Inject `traceparent` as a top-level field on the Redis Stream `XADD` to Sentinel
- [x] Widen the `emit` / `extract` spans with high-cardinality attributes (`source_id`, `anomaly_score`, `domain`, `axiom.emitted_at`, `extract.path`, `llm_model`)
- [x] Trace visible in Tempo as `synapse-l4`; `traceparent` confirmed on the stream entry
- [x] `.observability/phase-1-complete` committed
- [ ] Dashboard (Phase 5)

### Sentinel-L7 (Phase 2) — `sentinel-l7` ✅ instrumented · ✅ dashboard

- [x] OTel SDK + OTLP exporter installed (pure-PHP mode, no PECL)
- [x] SDK bootstrapped via `OtelServiceProvider`, OTLP → Collector on `:4318`
- [x] `traceparent` surfaced out of stream parsing as a separate value (not on `ComplianceEvent`); `TraceContextExtractor` in `app/Services/Compliance/`
- [x] `axiom.process` / `axiom.ai_analysis` / `axiom.sub_threshold` spans, started as children of the extracted context
- [x] End-to-end Synapse → Sentinel waterfall confirmed in Tempo (45 tests pass)
- [x] ADR-0024: "trace context is transport-layer, not domain-layer"
- [x] `.observability/phase-2-complete` committed
- [x] **Dashboard (Phase 5 slice) — "Sentinel-L7 Service".** 9 panels, every one a TraceQL query over the wide `axiom.process` / `axiom.ai_analysis` attributes (no Prometheus counters). Required bumping Tempo to 2.7.2 and `filter_server_spans: false` (INTERNAL spans). See the Phase-5 as-built notes in the migration plan.

### EventHorizon (Phase 3) — `EventHorizon` ✅ instrumented · ✅ dashboard

- [x] Node SDK bootstrapped (first import in both `server.ts` and `worker.ts` entry points)
- [x] RabbitMQ context propagation through message headers — four-stage trace (HTTP ingest → AMQP publish → AMQP consume → MongoDB write → WebSocket fanout) visible as one trace
- [x] Wide spans on all four stages; malformed-message silent-drop surfaced as a span event (`message.parse_failed` with exception type/message)
- [x] RabbitMQ queue/DLQ depth + throughput panels (scraped via `rabbitmq_prometheus` across the compose-project boundary)
- [x] Async-failure story: `events_failed_total{event_type, failure_reason}` counter (alertable rate) + TraceQL async-failure table (per-failure forensics)
- [x] Dedicated **EventHorizon Service** dashboard (RED + Node runtime + RabbitMQ + recent-traces); existing 44 tests pass
- [x] `.observability/phase-3-complete` committed
- [ ] Structured logs via OTLP/pino — `console.*` retained for now (deferred to Phase 5)

### Ledger-L5 — Ruby invoicer (Phase 4) — `Ledger-L5` ⬜

- [ ] Instrument from day one (`opentelemetry-sdk` + OTLP exporter + `use_all`)
- [ ] Confirm outbound HTTP to Sentinel auto-injects `traceparent` and links across services
- [ ] Manual wide spans on `invoice.generate` / `invoice.send` / `invoice.mark_paid` (`customer_id`, `amount_cents`, `billing.plan`, …)
- [ ] Commit `.observability/phase-4-complete`

### Arbiter-L8 — auxiliary consumer (eval harness, outside core scope) 🟡 coded, unconfirmed

- [x] OTel SDK + OTLP exporter wired as a plain import-time side effect (mirrors EventHorizon's Node SDK init-order pattern — instrumentation set up before any instrumented object is constructed, not deferred behind a lifecycle hook)
- [x] Verified against in-memory span/metric exporters in arbiter-l8's own test suite
- [ ] **Not yet confirmed against this repo's live Collector.** Docker wasn't reachable in the session that built it, so — unlike the four services above — there's no observed trace in Tempo for `arbiter-l8` yet. Recorded as "instrumented, not yet confirmed flowing" rather than "done," per this repo's own "verify a status claim against the artifact" convention. See `docs/journal.md` (Phase 0 cont. — arbiter-l8 joins the traced services) and `docs/probes/phase-0-arbiter-l8-otel-instrumentation.md`.

### Logs & dashboards polish (Phase 5) — all 🟡

This is where the visible deliverables live — instrumentation (Phases 1–3) is done, dashboards mostly are not.

- [x] Early slices: EventHorizon dashboard + RabbitMQ/async-failure operational panels
- [x] **Sentinel-L7 dashboard** — TraceQL-metrics off wide spans (the headline cross-service trace now has a home)
- [ ] **Synapse-L4 dashboard**
- [ ] Ship logs via Collector → Loki from every service (planned — services currently log to `console`/Monolog locally, so the dashboards' Loki panels stay empty until this lands)
- [ ] One "executive" dashboard for the full system (per-service dashboards driven by TraceQL over wide span attributes, not pre-aggregated PromQL)

---

## 🚀 Quickstart

```bash
docker compose up -d
```

Wait ~30 seconds for services to start, then verify:

```bash
docker compose ps
# tempo, loki, prometheus, grafana → "healthy"
# otel-collector → "Up" (no healthcheck — see note below)
```

> **Note:** `otel-collector-contrib` is a distroless image with no shell or `wget`. The `CMD-SHELL` healthcheck form cannot execute inside it. The collector's own `health_check` extension still runs on `:13133` inside the container and is confirmed healthy via its logs.

Open Grafana at [http://localhost:3300](http://localhost:3300) — no login required. Navigate to **Dashboards → OTel Overview** for the starter dashboard.

---

## 💨 Smoke test

Send a synthetic trace to verify the full pipeline:

```bash
curl -X POST http://localhost:4318/v1/traces \
  -H 'Content-Type: application/json' \
  -d @test/synthetic-trace.json
```

Expected response: `HTTP 200` with `{"partialSuccess":{}}` body. An empty `partialSuccess` object means all spans were accepted (non-empty would list rejections).

Then in Grafana: **Explore → Tempo → Search** — filter by service name `smoke-test`. The trace should appear within a few seconds.

---

## 📊 Dashboards

| Dashboard | UID | Shows |
|---|---|---|
| **OTel Overview** | `otel-overview` | Collector health — accepted spans/sec, Tempo spans ingested/sec, and a recent-logs panel (Loki). |
| **EventHorizon Service** | `eventhorizon-service` | Per-service RED metrics for `event-horizon` — request rate by status code, 5xx error rate, p50/p95/p99 latency — plus Node.js runtime health (event-loop lag, V8 heap, MongoDB connection pool), RabbitMQ queue & DLQ depth vs publish rate, per-type event throughput, MongoDB change-stream lag, async-failure rate (`events_failed_total`) plus an async-failure table (error spans the 5xx panel can't see — ingest returns 202 before worker/DLQ failures occur), a *Recent Logs* panel (Loki), and a recent-traces table (TraceQL search over HTTP status, method, and event type). |
| **Sentinel-L7 Service** | `sentinel-l7-service` | Compliance-worker view, **100% TraceQL metrics** over the wide `axiom.process` / `axiom.ai_analysis` span attributes (no Prometheus counters). Axiom throughput by `risk_level` / `domain` / `routed_to_ai` (`rate()`), processing latency p50/p95/p99 (`quantile_over_time(duration,…)`), anomaly-score and AI-confidence avg/max, AI throughput by driver, an AI-error table (filtered on the `exception` span event, since `recordException` doesn't set `status=error`), and a recent-Axioms table. **AI-by-driver and AI-confidence panels stay empty until a real AI key is configured** — see the migration plan's "Enabling the AI panels" steps. |

> **The Loki logs panels are wired but empty.** OTel Overview and EventHorizon include a Loki panel, but **shipping logs to Loki is planned (Phase 5) and not wired up yet** — services currently log to `console`/Monolog locally. Until that lands these panels show "No data," which is expected, not a misconfiguration. The live signals are traces (Tempo) and metrics (Prometheus). The Sentinel-L7 dashboard has no Loki panel for the same reason.

Three dashboards exist so far. **Synapse-L4 is fully instrumented but has no dashboard yet** — tracked as Phase 5 work in [Status & roadmap](#-status--roadmap) above. Until then, view its traces via Explore → Tempo (`{resource.service.name="synapse-l4"}`).

> **The Sentinel-L7 dashboard requires Tempo ≥ 2.7 and `filter_server_spans: false`.** Its TraceQL-metrics panels read from the `local-blocks` metrics-generator (`tempo.yaml`). Sentinel's spans are `SpanKind=INTERNAL`; Tempo 2.7's `local_blocks` defaults `filter_server_spans: true`, which drops them from metrics (search still works, but every metric query returns empty). `quantile_over_time` over span *attributes* isn't supported even on 2.7 — only over the `duration` intrinsic — so the anomaly-score and confidence panels use `avg`/`max`/`min_over_time`.

For a full distributed-trace view (HTTP ingest → AMQP publish → AMQP consume → processing span), use **Explore → Tempo → `{resource.service.name="event-horizon"}`** rather than a dashboard panel — trace waterfalls aren't dashboard-friendly.

> **The RabbitMQ panels read per-queue metrics from the broker's own exporter.** `RabbitMQ Queue Health` is scraped from EventHorizon's broker via the bundled `rabbitmq_prometheus` plugin on `:15692` (enabled by default in `rabbitmq:3-management-alpine`, verified returning HTTP 200). RabbitMQ runs in a *separate* compose project, so Prometheus reaches it through the host gateway (`host.docker.internal:15692`; see the `rabbitmq` job in `prometheus.yml` and `extra_hosts` on the prometheus service — required on Linux/WSL2).
>
> Two things to know:
> - The job scrapes **`/metrics/per-object`**, not the default `/metrics`. The default endpoint is *aggregated* — it sums all queues into label-less totals, so a `{queue="events.work"}` filter matches nothing. Per-object is what carries the per-queue labels.
> - The panels populate only once EventHorizon's worker is running and has declared the `events.work` / `events.dead` queues (`rabbitmq_queues` is `0` until then), and after Prometheus has loaded the job (`docker compose up -d --force-recreate prometheus` if it was already running when the job was added). Empty panels in that window are expected, not a misconfiguration.

---

## 🔌 Port reference

| Service | Port | Purpose |
|---|---|---|
| OTel Collector | 4317 | OTLP/gRPC ingest |
| OTel Collector | 4318 | OTLP/HTTP ingest |
| OTel Collector | 8888 | Collector self-telemetry (Prometheus scrape) |
| OTel Collector | 8889 | Forwarded app metrics (Prometheus scrape) |
| Tempo | 3200 | HTTP API (Grafana datasource) + self-metrics |
| Loki | 3100 | HTTP API |
| Prometheus | 9090 | UI + query API |
| Grafana | 3300 | UI |

---

## 🧹 Teardown

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and delete all stored data
```

---

## 📚 Docs

See the [`docs/`](docs/) folder for the full detail:

- [`OBSERVABILITY_MIGRATION_PLAN.md`](docs/OBSERVABILITY_MIGRATION_PLAN.md) — the phase-by-phase, cross-service migration plan (sequencing, per-service tasks, and as-built notes).
- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the backend fits together (signal pipelines, the Docker network, and the architectural posture behind the pillar-stack choice).
