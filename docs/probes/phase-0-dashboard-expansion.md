# Probes — Phase 0 (cont.): EventHorizon Dashboard Expansion

Deck: `Rhizome::rhizome-lens` · See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, prometheus, docker]
---
To scrape RabbitMQ in a *separate* compose project, Prometheus targets
{{c1::host.docker.internal:15692}} with `extra_hosts:
["host.docker.internal:host-gateway"]` — reaching it {{c2::through the host
gateway}} rather than container DNS, which keeps the two stacks
lifecycle-independent.

Extra: rhizome-lens · Phase 0 · Pattern: Cross-compose-project scrape
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, docker, wsl2]
---
The `host.docker.internal` alias is injected automatically by
{{c1::Docker Desktop (Mac/Windows)}} but does not exist on native Linux/WSL2
unless you add the {{c2::host-gateway `extra_hosts`}} mapping yourself — same
compose file, different behaviour per engine.

Extra: rhizome-lens · Phase 0 · Pattern: host.docker.internal not automatic on Linux
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, grafana]
---
To put a count and a rate on one Grafana timeseries without one flattening the
other, add a field override `{{c1::byRegexp}}: /.*rate.*/` setting
`custom.axisPlacement: {{c2::right}}` — so {{c3::legend naming}} becomes
load-bearing, since the override matches on series name.

Extra: rhizome-lens · Phase 0 · Pattern: Dual-axis via byRegexp override
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, prometheus]
---
A freshly-added Prometheus scrape target legitimately shows {{c1::DOWN}} when
the scraped service lives in {{c2::a different compose project/repo}} that hasn't
yet exposed its metrics endpoint — the scrape config declares intent, the target
stays down until the other side ships.

Extra: rhizome-lens · Phase 0 · Challenge: target DOWN is expected
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, dashboard, git]
---
Reordering panels in a hand-curated dashboard JSON is done with
{{c1::targeted text edits}} (validated by a read-only `json.load`), not a
`json.dump` round-trip — because `json.dump(indent=2)` would {{c2::explode the
inline objects}}, turning a small move into a whole-file diff.

Extra: rhizome-lens · Phase 0 · Anti-Pattern Avoided: json.dump round-trip
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14

---
type: basic
deck: Rhizome::rhizome-lens
tags: [observability, phase-0, design]
---
Q: Why bridge the two stacks with `host.docker.internal:host-gateway` instead of
defining a shared external Docker network referenced by both compose files?

A: Both work, but a shared external network couples the two projects'
lifecycles — tearing down one breaks the other's network reference. The
host-gateway hop keeps the stacks independent; either can come up or down on its
own. The only cost is one Linux-specific `extra_hosts` line, documented inline —
a cheap price for lifecycle independence.

Extra: rhizome-lens · Phase 0 · Decision: Host-gateway over shared network
See: docs/journal.md#phase-0-cont--eventhorizon-dashboard-expansion-rabbitmq-scrape-throughput-async-failure-panels--2026-06-14
