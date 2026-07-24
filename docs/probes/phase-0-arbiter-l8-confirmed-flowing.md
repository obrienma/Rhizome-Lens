---
type: basic
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8, verification]
---
Q: How was arbiter-l8's OTel status upgraded from "instrumented, not yet
confirmed flowing" to confirmed, and why wasn't a synthetic test span used?

A: Queried Tempo's `/api/search` for `resource.service.name="arbiter-l8"`
and Prometheus's `/api/v1/query` for `arbiter_l8_judge_outcome_total` /
`arbiter_l8_layer_latency_milliseconds_bucket` after driving real traffic
through it. Traffic came from calling the actual `online.pipeline
.evaluate_item()` with a real `JudgeCircuitBreaker`, not synthetic spans —
proving the instrumented code paths fire as designed (a genuine mix of
`ollama` and `heuristics_fallback` outcomes), not just that OTLP transport
works.

Extra: observability · Pattern: Verify a Status Claim Against the Artifact
See: docs/journal.md (Phase 0 cont. — arbiter-l8 confirmed flowing against a live Collector)

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8]
---
arbiter-l8's `online.pipeline.evaluate_item` has no CLI surface by design —
it's meant to be called from a caller's {{c1::own sampling/production
loop}}, per {{c2::docs/adr/0001-standalone-module.md}} — so confirming live
delivery required a one-off script importing it directly rather than a
documented command.

Extra: observability · Challenge: No CLI Surface Meant Writing a One-Off Driver Script
See: docs/journal.md (Phase 0 cont. — arbiter-l8 confirmed flowing against a live Collector)

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8, grafana]
---
The new `arbiter-l8-service.json` dashboard mixes datasources in one
dashboard — {{c1::Prometheus}} panels for judge-outcome rate and per-layer
latency, {{c2::Tempo TraceQL}} panels/tables for evaluation throughput,
latency, and recent traces — mirroring EventHorizon's own panel layout
rather than each dashboard being single-datasource.

Extra: observability · Decision: New Arbiter-L8 Service Dashboard, Not an Overview Addition
See: docs/journal.md (Phase 0 cont. — arbiter-l8 confirmed flowing against a live Collector)
