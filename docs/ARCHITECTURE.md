# Architecture

## Overview

`rhizome-observability` is the shared observability backend for a four-service OTel migration. It runs as a standalone Docker Compose stack that any instrumented service ships signals to over OTLP. It is infrastructure only — no application code.

---

## Signal flow

```
[synapse-l4  (Python/FastAPI)]  ──┐
[sentinel-l7 (Laravel/PHP)   ]  ──┤  OTLP/gRPC :4317
[EventHorizon (TS/Fastify)   ]  ──┤  OTLP/HTTP :4318
[ledger-l5    (Ruby)         ]  ──┘
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

---

## Components

### OTel Collector

Central ingestion and fan-out hub. Receives all three signal types (traces, logs, metrics) on a single pair of OTLP endpoints and routes each to its dedicated backend. Config: `otel-collector-config.yaml`.

Pipelines:

| Pipeline | Receiver | Processors | Exporter |
|---|---|---|---|
| traces | otlp | memory_limiter → batch | otlp/tempo (tempo:4317) |
| logs | otlp | memory_limiter → batch | loki (http://loki:3100/loki/api/v1/push) |
| metrics | otlp | memory_limiter → batch | prometheus (scrape at :8889) |

The batch processor buffers spans before forwarding, so there is a short propagation delay (~1–2 s at default settings) between a `curl` to :4318 and the trace appearing in Tempo.

### Tempo

Distributed trace storage in monolithic mode. Receives traces from the Collector over gRPC (internal bridge only — port 4317 is not published to localhost). Query API on :3200 is the Grafana datasource endpoint. Config: `tempo.yaml`.

Block retention is set to `1h` for local dev — sufficient for iterative testing. Extend in `tempo.yaml` if longer retention is needed during a phase.

### Loki

Log aggregation. Schema v13/TSDB (the Loki 3.x default). Config: `loki-config.yaml`. Receives push from the Collector's loki exporter. Grafana datasource queries via :3100.

### Prometheus

Metrics storage. Scrapes the Collector's Prometheus exporter endpoint at `otel-collector:8889`. Config: `prometheus.yml`. Query UI on :9090.

### Grafana

Visualization. Datasources (Tempo, Loki, Prometheus) and the starter dashboard are provisioned from `grafana/provisioning/` on startup — no manual UI configuration required. Anonymous admin access; login form disabled.

Trace-to-log correlation (`tracesToLogsV2`) is wired in the Tempo datasource provisioning so that Explore → Tempo → span detail → "Logs for this span" works the moment services emit both signals.

---

## Docker network

All five services share the `observability` bridge network. Internal communication uses Docker service names:

| From | To | Address |
|---|---|---|
| Collector (traces exporter) | Tempo | `tempo:4317` |
| Collector (logs exporter) | Loki | `http://loki:3100/loki/api/v1/push` |
| Prometheus | Collector metrics | `otel-collector:8889` |
| Grafana | Tempo | `http://tempo:3200` |
| Grafana | Loki | `http://loki:3100` |
| Grafana | Prometheus | `http://prometheus:9090` |

Instrumented services running outside this Compose stack (on the host or in their own Compose network) reach the Collector via `localhost:4318` (HTTP) or `localhost:4317` (gRPC).

---

## Architectural posture

The pillar stack (Tempo + Loki + Prometheus) is deliberate — it maps to what most production teams and interviewers recognize. Instrumentation targets the wide-events model regardless: every span carries high-cardinality attributes (`source_id`, `customer_id`, `domain`, `anomaly_score`, etc.). If cardinality requirements grow, the migration path is Tempo → Clickhouse; application-level instrumentation does not change.

See `docs/OBSERVABILITY_MIGRATION_PLAN.md` for per-service phase sequencing and the full rationale.
