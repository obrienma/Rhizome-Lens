# Probes — Phase 0 (cont.): Verifying RabbitMQ Panels Against the Live Exporter

Deck: `Rhizome::observability` · See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, rabbitmq, prometheus]
---
`rabbitmq_prometheus`'s default `/metrics` endpoint is {{c1::aggregated}} —
summing all queues into a label-less total with zero `queue=` labels — so a
`{queue="events.work"}` filter matches nothing. Per-queue series live on
{{c2::/metrics/per-object}}.

Extra: rhizome-observability · Phase 0 · Anti-Pattern Avoided: aggregated /metrics for per-queue series
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, rabbitmq]
---
There is no `rabbitmq_queue_messages_delivered_total`: the queue-level family has
`_published_total` but delivery is counted {{c1::per channel}}
(`rabbitmq_channel_messages_delivered_total`), not per queue. The deliver series
was {{c2::dropped}}, not shipped as a permanent "No data" line.

Extra: rhizome-observability · Phase 0 · Anti-Pattern Avoided: charting a non-existent metric
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, promql]
---
`or vector(0)` renders a never-incremented counter as a flat {{c1::0}} instead of
"No data" — but only worth it *before the first increment*, because a counter
series {{c2::persists once exposed}}, after which the grouped query is never
empty and the baseline is permanent clutter.

Extra: rhizome-observability · Phase 0 · Pattern: or vector(0) and its lifecycle limit
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, promql]
---
The uninformative `event_type="unknown"` grouping was fixed with a {{c1::query
change}}, not new instrumentation — regrouping `by ({{c2::failure_reason}})`, a
second label the counter already carried. When a grouping label is
uniform-and-useless, enumerate the series' other labels first.

Extra: rhizome-observability · Phase 0 · Pattern: enumerate other labels before new instrumentation
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, promql, grafana]
---
A ghost {{c1::value}} series appears in a `by (label)` panel when the label was
added {{c2::partway through}} the window: pre-label samples bucket into an
empty-labeled series. Exclude it with a `{label!=""}` matcher, since an absent
label is equivalent to {{c3::""}} in PromQL.

Extra: rhizome-observability · Phase 0 · Challenge: ghost value series after retroactive label
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, rabbitmq]
---
You cannot verify per-queue series against an idle broker: RabbitMQ exposes
per-object series only for objects that {{c1::currently exist}}, so with
`rabbitmq_queues` at {{c2::0}} (worker disconnected) no per-queue series are
emitted. Verify label *values* against a running producer.

Extra: rhizome-observability · Phase 0 · Challenge: can't verify against an idle broker
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, prometheus, wsl2]
---
Editing `prometheus.yml` does {{c1::not}} hot-apply — the on-disk config and the
in-memory config are independent. A newly-added job missing from
`/api/v1/targets` is reloaded by {{c2::docker compose up -d --force-recreate
prometheus}} (or `/-/reload`).

Extra: rhizome-observability · Phase 0 · Challenge: Prometheus serving a stale config
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: cloze
deck: Rhizome::observability
tags: [observability, phase-0, rabbitmq, promql]
---
Per-object RabbitMQ counters carry {{c1::channel/exchange/queue_vhost}} labels
beyond `queue`, so multiple producer channels yield multiple series; wrap in
{{c2::sum(rate(...))}} to collapse them to one per-queue throughput line.

Extra: rhizome-observability · Phase 0 · Pattern: sum() to collapse per-object counters
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15

---
type: basic
deck: Rhizome::observability
tags: [observability, phase-0, design]
---
Q: The async-failure signal exists as both a TraceQL table (over `status=error`
spans) and a Prometheus `events_failed_total` panel. Why keep both rather than
pick one?

A: They answer different questions and the plan's discipline is "Prometheus for
alerts, spans for detail." The counter gives a sampling-independent, alertable
*rate* — you can't reconstruct a true failure rate from sampled traces. The
TraceQL table gives per-failure *forensics* — the specific spans, attributes, and
exception detail an aggregate counter can't carry. The rate drives alerting; the
spans drive debugging.

Extra: rhizome-observability · Phase 0 · Decision: events_failed_total panel added (supersedes deferral)
See: docs/journal.md#phase-0-cont--verifying-the-rabbitmq-panels-against-the-live-exporter--2026-06-15
