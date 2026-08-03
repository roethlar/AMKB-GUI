# Repository State

## Now

- AM Configurator `0.1.65` is public as the normal/latest GitHub Release:
  <https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.65>.
- Tag `v0.1.65` is fixed at qualified candidate
  `ebd0d043e70c31c0342a73b088f84d28357196e4`. Exact CI run `30780237489`
  and Desktop installers run `30780237509` passed for that commit.
- The Release contains exactly five assets. Installer SHA-256 values are Linux
  `9d949da1b3149e5caddbecdf0cb85fbd35e2f7436916066bd4391f56d5923892`,
  Windows `3b2f9572f241f1aa191f0f38cf219e3f6333ffa08a5a1b8a68a40dda56cc34a5`,
  and macOS `a075cbc54b09376494567387083252409035524f0fdc1c4bc7aea63b0649de89`.
  Anonymous downloads of all five assets match their qualified byte sizes and
  contents, and all five GitHub build attestations verify.
- Windows remains Authenticode-unsigned. macOS remains ad-hoc signed and not
  notarized. The owner ruled their warning UX an established,
  change-triggered baseline rather than a per-build qualification ritual, and
  ruled a separate Windows About launch non-blocking for this release.
- Existing Neon 80 physical evidence and sustained owner use were accepted for
  `0.1.65`; no final-candidate hardware write occurred. Read-only final
  preflight identified one writable `NEON80` and proved the supplied restore
  profile matched the live four-layer keymap and four macros.
- Public scope remains macOS arm64, Windows x64, and Linux x86-64. JPEG import
  and best-effort experimental Windows/Linux ARM CI are deferred to the next
  release plan.
- No live provider request, paid credential use, security bypass, asset
  overwrite, tag move, or announcement occurred during publication.
- The known load-only cancellation-status intermittent remains an unresolved
  maintenance risk. The Macro-page visibility finding and the read-only
  retired-job exposure from accepted review `cl-2` remain queued, unapproved
  implementation work.

## Next

- The r/AngryMiao announcement is prepared at
  `docs/announcements/reddit-0.1.65.md` but remains a separate outward-message
  gate. Do not post, edit, comment, or cross-post without exact authorization.
- Begin ordinary post-release watch for installation, download, and device
  reports. Do not mutate the published tag or assets.
- The next release plan must include JPEG media import and best-effort native
  Windows ARM64 and Linux ARM64 CI builds, still experimental and non-blocking
  unless a later owner decision changes that status.
- `.agents/machines.md` remains the canonical host-capability record. Detailed
  preparation, rejected-candidate history, qualification evidence, and
  publication outcome live in
  `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md`.

## Blockers

- No blocker remains for `0.1.65` publication; the Release is public and
  verified. Announcement authority remains pending by design and does not
  affect release availability.
