---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8, mcp-jsonrpc]
---
Laravel MCP tool names are derived via {{c1::Str::kebab}}(class_basename($this))
by default — `AnalyzeTransaction` becomes the JSON-RPC tool name
{{c2::analyze-transaction}}, not the snake_case that appears only in the
server's human-readable instructions text.

Extra: observability · Pattern: Verify the Wire Protocol Against the Framework's Source, Not the Spec
See: docs/journal.md (Phase 0 cont. — Sentinel-L7 MCP adapter)

---
type: cloze
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8, mcp-jsonrpc]
---
A Laravel MCP tool's JSON-RPC result content is `Response::json($result)`,
itself a JSON-encoded string wrapped in a text block — so
`result.content[0].text` must be {{c1::JSON-decoded a second time}} to
reach the real payload.

Extra: observability · Pattern: Verify the Wire Protocol Against the Framework's Source, Not the Spec
See: docs/journal.md (Phase 0 cont. — Sentinel-L7 MCP adapter)

---
type: basic
deck: Rhizome::rhizome-lens
tags: [observability, arbiter-l8]
---
Q: Why was this mirror entry backfilled on 2026-07-06 instead of when it
was originally written on 2026-07-04?

A: The source entry in arbiter-l8 carried `cross_ref: observability`
in its frontmatter from the day it was written, marking it for mirroring
— but the mirror was never actually created. The gap went unnoticed until
a punch-list review of a stale local `skills/journal-anki.md` copy in
this repo surfaced it: that copy predated the `cross_ref_id` field
entirely, so there was no mechanical way to detect the miss until the
skill copy itself was re-synced.

Extra: observability · re-sync gap
See: docs/journal.md (Phase 0 cont. — Sentinel-L7 MCP adapter)
