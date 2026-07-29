# Push Policy

Referenced by `AGENTS.md` (Prime Invariants): "Push policy: see
`.agents/push-policy.md`."

## Rule

Ordinary, non-force pushes of committed and verified in-scope work to this
repository's canonical `origin` are pre-authorized. Push when needed to continue
an owner-approved workflow; do not stop for a per-push approval.

Explicit owner authorization is still required for:

- force-pushing or any other remote history rewrite;
- pushing to a remote other than the canonical `origin`;
- creating or pushing tags, publishing a release, or publishing an
  announcement;
- deleting a remote branch or other remote ref; and
- pushing work outside the scope the owner approved.

Never push uncommitted or knowingly failing work.

## Provenance

Owner ruling, 2026-07-28: make this repository's push policy non-blocking and
repo-local. This supersedes the 2026-07-25 per-push approval rule.
