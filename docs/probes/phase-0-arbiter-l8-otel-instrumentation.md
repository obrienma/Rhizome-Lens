---
type: cloze
deck: Rhizome::observability
tags: [observability, sentinel-eval, root-span-fragmentation]
---
Synapse-L4's suspected trace-fragmentation bug traces to calling
`instrument_fastapi(app)` inside {{c1::lifespan()}} — by which point the
FastAPI app and its routes were already constructed at {{c2::import time}},
and Starlette had already built and cached its middleware stack on the
first ASGI event.

Extra: observability · Anti-Pattern Avoided: Deferred SDK Initialization
See: docs/journal.md (Phase 0 cont. — sentinel-eval joins the traced services)

---
type: basic
deck: Rhizome::observability
tags: [observability, sentinel-eval]
---
Q: Why is sentinel-eval's OTel status recorded as "instrumented, not yet
confirmed flowing" rather than "done" like the other four services?

A: Its instrumentation logic was verified with in-memory span/metric
exporters in its own test suite, but never against a live Collector —
Docker wasn't reachable in the session that built it. The other services'
journal entries cite a trace actually observed in Tempo; this one doesn't,
per this repo's own "verify a status claim against the artifact" pattern.

Extra: observability · Challenge: No live verification against this hub's own Collector
See: docs/journal.md (Phase 0 cont. — sentinel-eval joins the traced services)
