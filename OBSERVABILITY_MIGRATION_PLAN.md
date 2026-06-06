# Observability Migration Plan

Four-service migration to OpenTelemetry, using `rhizome-observability` as the shared backend.

---

## Services in scope

| Service | Language | Priority |
|---|---|---|
| synapse-l4 | TBD | Phase 1 |
| sentinel-l7 | TBD | Phase 2 |
| EventHorizon | TBD | Phase 3 |
| Ledger-L5 | TBD | Phase 4 |

---

## Phases

### Phase 0 — Observability Infrastructure (this repo)

Bootstrap the shared OTel backend:
- OTel Collector (receives OTLP on 4317/4318, routes to Tempo/Loki/Prometheus)
- Tempo (trace storage)
- Loki (log storage)
- Prometheus (metrics)
- Grafana (unified UI, auto-provisioned datasources + starter dashboard)

**Completion marker:** `.observability/phase-0-complete` committed after stack verified healthy.

### Phase 1 — synapse-l4 instrumentation

- Add OTel SDK dependency
- Instrument HTTP handlers, DB calls, outbound requests
- Configure OTLP exporter pointing at collector on 4317 or 4318
- Validate traces visible in Grafana → Tempo
- Validate logs visible in Grafana → Loki

### Phase 2 — sentinel-l7 instrumentation

Same pattern as Phase 1. Add trace propagation headers for cross-service correlation with synapse-l4.

### Phase 3 — EventHorizon instrumentation

Same pattern. Focus on event pipeline spans (producer/consumer span kinds).

### Phase 4 — Ledger-L5 instrumentation

Same pattern. Focus on DB transaction spans and financial operation duration metrics.

---

## Rollout strategy

Each service is instrumented independently. No service requires another to be instrumented first, but cross-service trace correlation only becomes visible once both sides propagate W3C `traceparent` headers.

Phases 1–4 can proceed in parallel if team capacity allows. Phase 0 is the only hard prerequisite.

---

## Rollback

OTel instrumentation is additive — removing it reverts the service to its pre-instrumentation state. No data migrations are required. The observability stack itself (Phase 0) is purely local infrastructure; tearing it down has no impact on services.

---

## Collector endpoint reference

| Protocol | Address | Use when |
|---|---|---|
| OTLP/gRPC | `localhost:4317` | Default for most OTel SDKs |
| OTLP/HTTP | `localhost:4318` | HTTP-only environments, browser SDKs |
