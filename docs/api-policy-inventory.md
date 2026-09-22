# API policy inventory

`security/operation-policy-registry.json` is the generated inventory of the
ERMS authorization boundary. It contains FastAPI operations and their intended
global privilege or resource permission. It is defence-in-depth: the API and
database remain responsible for enforcing every decision.

## What belongs in the registry

- HTTP method and route;
- public, authenticated, globally privileged, or resource-scoped policy class;
- required global privilege and resource permission; and
- implementation-phase enforcement markers used by regression tests.

The registry deliberately excludes buttons, links, menus, screens, and mobile
widgets. Client code is not an authorization boundary, and line- or widget-based
entries create noisy diffs without proving that access is protected.

The generator has no default classification for a new API route. Generation
fails until the operation is deliberately classified as public, authenticated,
globally privileged, resource scoped, or another approved policy class. This
turns the inventory into a useful review gate instead of silently assigning a
weak fallback.

## Review rule

Explicit security review is required when an API operation is added, removed,
or reclassified, or when its privilege or permission changes. Regeneration is
mechanical and is not itself review:

```bash
PYTHONPATH=. backend/services/api/.venv/bin/python tools/generate_policy_inventory.py
```

The reviewer must inspect the resulting API-policy diff and the corresponding
runtime authorization dependency or resource authorization call. Ordinary
client layout, wording, and control changes do not require this registry to be
regenerated.

## Multiple clients

NiceGUI, Flutter, and future clients share this single API registry. Each client
should consume authoritative capability responses, tolerate permissions being
revoked after rendering, and handle denial and conflict responses accessibly.

A client team may create a separate action inventory for navigation or UX test
coverage. Such an inventory is optional, belongs with that client, and must not
be described as authorization enforcement or duplicated into the API policy
registry.
