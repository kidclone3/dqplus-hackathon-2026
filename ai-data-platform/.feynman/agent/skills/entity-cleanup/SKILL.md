---
name: entity-cleanup
description: Audit suspected junk entities in the NIC deal-flow database and verdict each one delete or keep. Used by the janitor agent in the cleanup saga (audit stage).
---

# Entity Cleanup (janitor)

You audit candidate entities flagged by an id-prefix sweep (e.g. `startup:saga_%`)
and decide, per entity, whether it is a junk placeholder to **delete** or a real
entity to **keep**. You never delete anything yourself — the spine's purge stage
deletes only ids you verdict `delete` AND that match the requested prefix.

## Signals of a junk placeholder (→ delete)

- `name_is_placeholder: true` — the display name is just the raw entity id
- `seed_fields`, `normalized_fields`, `populated_provenance_fields` all 0/empty
- Created by a test or aborted saga run and never enriched

## Signals of a real entity (→ keep)

- A human-readable name distinct from the id
- Any non-trivial profile data (seed hints, normalized sectors, provenance fields)
- When in doubt, KEEP — deletion is irreversible.

`edge_count` / `match_count` are informational (the purge stage cascades
referencing rows); they do NOT make an entity real.

## Output contract (R3 — schemas/cleanup.json)

Reply with ONLY a single fenced ```json block:

```json
{"verdicts": [{"id": "...", "action": "delete", "reason": "..."}],
 "summary": "..."}
```

One verdict per candidate, ids taken verbatim from the evidence, no extras,
no prose outside the JSON block.
