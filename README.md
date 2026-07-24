<p align="center">
  <img width="200" alt="Rhizome Lens" src="docs/assets/Rhizome-Lens-logo.png" />
</p>

A self-contained, local-runnable **observability backend** built on [OpenTelemetry](https://opentelemetry.io/) and the Grafana "pillar" stack: an OTel Collector that ingests traces, logs, and metrics over OTLP and fans them out to **Tempo** (traces), **Loki** (logs), and **Prometheus** (metrics), all visualized in **Grafana**. A single `docker compose up` brings up the whole stack — no cloud account, no managed service.

It's the shared telemetry backend for a five-service, three-language migration to OpenTelemetry (Python, TypeScript, PHP). The headline goal is **distributed tracing that follows a single request across both service boundaries and async boundaries** — Redis Streams and RabbitMQ — so you can see one trace span four codebases. This repo is infrastructure only; the services that emit to it live in their own repositories (see [Current Status](#-current-status)).

```
[Synapse-L4  (Python/FastAPI)]  ─────┐
[Sentinel-L7 (Laravel/PHP)   ]  ─────┤  OTLP/gRPC :4317
[EventHorizon (TS/Fastify)   ]  ─────┤  OTLP/HTTP :4318
[Ledger-L5   (Python/FastAPI)]  ─────┤
[Arbiter-L8  (Python)        ]  ─────┘
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
> [!NOTE]
> EventHorizon telemetry with synthetic errors  — generated via fault injection for dashboard demo traffic.
<img width="400" alt="EventHorizon-Grafana" src="https://github.com/user-attachments/assets/1955b801-848e-4aed-acb1-6f5934252ad0" />

---

## 📍 Current Status

| Component | Repo | Instrumentation | Dashboard | Logs → Loki |
|---|---|---|---|---|
| Arbiter-L8 (auxiliary, outside core migration) | `Arbiter-L8` (Python) | ✅ confirmed flowing | ✅ Arbiter-L8 Service | ⬜ planned |
| EventHorizon | `EventHorizon` (TypeScript/Fastify) | ✅ done | ✅ EventHorizon Service | ⬜ planned |
| Ledger-L5 | `Ledger-L5` (Python/FastAPI) | ⬜ not started | ⬜ none yet | ⬜ planned |
| Observability backend | `rhizome-lens` (this repo) | ✅ done | ✅ OTel Overview | ✅ sink ready |
| Sentinel-L7 | `Sentinel-L7` (Laravel/PHP) | ✅ done | ✅ Sentinel-L7 Service | ⬜ planned |
| Synapse-L4 | `Synapse-L4` (Python/FastAPI) | ✅ done | ⬜ none yet | ⬜ planned |

**What's left:** instrumenting Ledger-L5, a Synapse-L4 dashboard, and shipping logs to Loki from every service. Every service currently logs locally (`console`/Monolog) — the Loki panels in the dashboards below exist but stay empty until that lands.

### Implementation notes

A few decisions worth knowing before you go looking for them in code:

- **Arbiter-L8** — OTel SDK initializes at import time, mirroring EventHorizon's Node SDK init-order pattern (instrumentation set up before any instrumented object is constructed). Confirmed flowing against a live Collector by querying Tempo's `/api/search` and Prometheus's `/api/v1/query` directly, not just by eyeballing the dashboard.
- **EventHorizon** — RabbitMQ context propagation runs through message headers, so one trace covers HTTP ingest → AMQP publish → AMQP consume → MongoDB write → WebSocket fanout. A malformed message that gets silently dropped still surfaces as a span event (`message.parse_failed`) rather than disappearing.
- **Ledger-L5** — not started; will be a retrofit, same as Synapse-L4/Sentinel-L7/EventHorizon.
- **Sentinel-L7** — trace context is treated as transport-layer, not domain-layer (ADR-0024): `traceparent` is extracted out of stream parsing as a separate value rather than living on `ComplianceEvent`. Its dashboard is 100% TraceQL over wide `axiom.process`/`axiom.ai_analysis` span attributes, no Prometheus counters — this needed Tempo ≥ 2.7.2 and `filter_server_spans: false`, since Sentinel's spans are `SpanKind=INTERNAL` and get dropped from metrics-generation otherwise.
- **Synapse-L4** — Logfire is retained as an optional secondary exporter alongside the OTLP path; `traceparent` is injected as a top-level field on the Redis Stream `XADD` to Sentinel so the trace survives the async hop.

For the full phase-by-phase rationale, sequencing decisions, and as-built notes, see [`docs/OBSERVABILITY_MIGRATION_PLAN.md`](docs/OBSERVABILITY_MIGRATION_PLAN.md).

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
| **Arbiter-L8 Service** | `arbiter-l8-service` | Judge outcome rate/cumulative by source (`ollama`/`gemini_flash`/`heuristics_fallback`), % scored by judge vs. fallback, per-layer p95 latency, evaluation throughput/latency, judge-chain exception events, and a recent-evaluations table. Auxiliary consumer, outside the core four-service migration — see [Current Status](#-current-status) above. |

<!-- todo: cleanup this section -->
> **Loki panels show "No data" — expected, not a bug.** Log shipping to Loki isn't wired up yet; every service still logs locally (`console`/Monolog). OTel Overview and EventHorizon include Loki panels that will populate once that lands; Sentinel-L7 and Arbiter-L8 skip the panel entirely for the same reason. Traces (Tempo) and metrics (Prometheus) are the live signals today.

Four dashboards exist so far. **Synapse-L4 is fully instrumented but has no dashboard yet** — tracked in [Current Status](#-current-status) above. Until then, view its traces via Explore → Tempo (`{resource.service.name="synapse-l4"}`).

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