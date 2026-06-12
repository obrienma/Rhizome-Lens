# rhizome-observability

Shared OTel backend for the four-service observability migration. Provides a single `docker compose up` that brings up the full collection, storage, and visualization stack.

```
Services (future phases)
        │
        ▼ OTLP/gRPC :4317  or  OTLP/HTTP :4318
┌─────────────────────┐
│   otel-collector    │   (exposes metrics → Prometheus :8889)
└──────┬──────┬───────┘
       │      │
   traces   logs     metrics
       │      │         │
       ▼      ▼         ▼
   Tempo    Loki   Prometheus
   :3200   :3100     :9090
       │      │         │
       └──────┴────┬────┘
                   ▼
              Grafana :3000
         (auto-provisioned datasources)
```

---

## Quickstart

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

Open Grafana at [http://localhost:3000](http://localhost:3000) — no login required. Navigate to **Dashboards → OTel Overview** for the starter dashboard.

---

## Smoke test

Send a synthetic trace to verify the full pipeline:

```bash
curl -X POST http://localhost:4318/v1/traces \
  -H 'Content-Type: application/json' \
  -d @test/synthetic-trace.json
```

Expected response: `HTTP 200` with `{"partialSuccess":{}}` body. An empty `partialSuccess` object means all spans were accepted (non-empty would list rejections).

Then in Grafana: **Explore → Tempo → Search** — filter by service name `smoke-test`. The trace should appear within a few seconds.

---

## Port reference

| Service | Port | Purpose |
|---|---|---|
| OTel Collector | 4317 | OTLP/gRPC ingest |
| OTel Collector | 4318 | OTLP/HTTP ingest |
| OTel Collector | 8889 | Prometheus metrics scrape |
| Tempo | 3200 | HTTP API (Grafana datasource) |
| Loki | 3100 | HTTP API |
| Prometheus | 9090 | UI + query API |
| Grafana | 3000 | UI |

---

## Teardown

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and delete all stored data
```

---

See `docs/` for phase plans and architecture decisions.
