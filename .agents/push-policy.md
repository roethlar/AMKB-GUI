# Push Policy

Referenced by `AGENTS.md` (Prime Invariants): "Push policy: see
`.agents/push-policy.md`."

## Rule

**Ask before every push.** Pushing to any remote requires an explicit owner go
for that push. Approval to commit is never approval to push, and a go for one
push does not carry to the next.

Committing locally needs no push approval — the standing rule to commit each
slice as it lands is unchanged. Work accumulates on the local branch until the
owner says to push.

## Provenance

Owner ruling, 2026-07-25: "push policy: ask".
