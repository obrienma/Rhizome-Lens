# Probes — Docs: README roadmap & cross-service plan reconciliation

Deck: `Rhizome::observability` · See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: cloze
deck: Rhizome::observability
tags: [observability, docs, process]
---
Each phase's `phase-N-complete` marker is committed to {{c1::that service's own
repo}}, not the hub — so cross-service status is found by enumerating
{{c2::`ls ~/dev/*/.observability/`}}, not by reading the observability repo's own
directory (which holds only `phase-0-complete`).

Extra: rhizome-observability · Docs · Pattern: completion state owned by each repo
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: cloze
deck: Rhizome::observability
tags: [observability, docs, process]
---
Reconciling a downstream doc copy against a master is {{c1::not}} a blind `cp`:
the master listed the RabbitMQ scrape job as an *open* item this repo had already
shipped, so you {{c2::diff first}} and patch the spots where the destination has
moved past the source.

Extra: rhizome-observability · Docs · Anti-Pattern Avoided: blind-copy reintroduces a closed item
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: cloze
deck: Rhizome::observability
tags: [observability, docs, dashboard]
---
A provisioned dashboard panel is {{c1::not}} proof a signal flows: the "Recent
Logs" panel + configured Loki datasource only prove the query is wired. The
producing side shipped {{c2::no logs}} (`console.*` retained), so the panel is
"No data" until Phase 5 — verify the emitter before documenting a signal as live.

Extra: rhizome-observability · Docs · Challenge: a provisioned panel is not a flowing signal
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: cloze
deck: Rhizome::observability
tags: [observability, docs, process]
---
Editing a status table is half the job — the surrounding prose encodes a
{{c1::point-in-time assumption}} that goes stale without erroring. After
flipping a status cell, re-read the {{c2::narrative within a screen}} of it for
contradictions.

Extra: rhizome-observability · Docs · Challenge: roadmap prose drifted out of sync with its table
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: basic
deck: Rhizome::observability
tags: [observability, docs, process]
---
Q: Why split the roadmap into separate Instrumentation / Dashboard / Logs
columns instead of one "done" status per phase?

A: A single "done" conflates axes that land at different times. The plan's
"done" means the *instrumentation* DoD (cross-service trace in Tempo), but a
reader reads "done" as "there's a dashboard" — the most visible piece, which can
be absent (dashboards are Phase 5) even on a fully-instrumented service.
Separate columns make a fully-instrumented-but-undashboarded-and-unlogged
service legible at a glance instead of silently overclaiming.

Extra: rhizome-observability · Docs · Pattern: separate the deliverable axes
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16

---
type: basic
deck: Rhizome::observability
tags: [observability, docs, process]
---
Q: Which copy of the cross-service migration plan is canonical, and how do
changes propagate?

A: `rhizome-observability/docs/OBSERVABILITY_MIGRATION_PLAN.md` is canonical
(decided 2026-06-16). Service repos keep copies under `.observability/` that may
lag; changes are synced *up* into the canonical copy manually as work happens,
and service repos pull the plan *from* the hub. This reversed the earlier
treatment of EventHorizon's copy as master.

Extra: rhizome-observability · Docs · Decision: this repo's plan is canonical
See: docs/journal.md#docs--readme-roadmap--cross-service-plan-reconciliation--2026-06-16
