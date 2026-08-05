# AM Configurator 0.1.66 Public Release

**Status:** Published 2026-08-04. Tag `v0.1.66` targets
`f19a806a0df298b2b461ef867ffb3d128d17baa1`; CI run `30969081189` built all
three supported installers plus both experimental ARM64 targets green; all
five public assets passed SHA-256, GitHub attestation, and anonymous-download
verification. Local macOS qualification (frozen smoke, ad-hoc deep/strict
signature, `hdiutil verify`) passed. The owner authorized tag and Release
publication directly. The Reddit announcement was stopped by the owner and
never posted. The withdrawn `v0.1.65` draft's disposition remains an open
owner decision.

## Objective

Publish one normal, reproducible AM Configurator `0.1.66` GitHub Release for
macOS arm64, Windows x64, and Linux x86-64, succeeding the withdrawn `v0.1.65`
draft. The release carries the three-mode macro editor, the recaptured README
screenshots, and — per the 2026-08-02 owner decision — JPEG media import and
best-effort experimental native ARM64 CI builds.

## Authority and supersession

- `.agents/decisions.md` owns: canonical version `0.1.66` (2026-08-03);
  withdrawn-`0.1.65` frozen at `ebd0d043e70c31c0342a73b088f84d28357196e4`;
  permanent unsigned installers; change-triggered trust-warning qualification
  (2026-08-03: no reenactment while signing, identity, and OS baselines are
  unchanged); JPEG import plus experimental ARM CI mandated for this plan
  (2026-08-02); procedural-only AI; FFmpeg prohibition.
- `docs/superpowers/plans/2026-08-03-macro-sequence-visibility.md` owns the
  macro editor rework that this release ships.
- `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md` is the
  historical model for the publication mechanics and remains the record of
  the withdrawn release. This plan supersedes it for `0.1.66` work.
- `.agents/push-policy.md` owns ordinary canonical-`origin` pushes only.

## Already landed (no authorization needed beyond the owner's go of 2026-08-03)

- Three-mode macro editor: `4c1884d`, `92aad3c`, `b7f1c39`, `b3b22c3`,
  review fixes `b9f226e`, `829b5b1`.
- README screenshots recaptured with a synthetic profile, suite green:
  `9e714de`.
- Canonical version `0.1.66` and all pinned references: `777da50`.
- Full verification entry point green (731/731 Python, 193/193 web, build).

## Remaining tasks

### R66-1 — JPEG media import (owner decision 2026-08-02)

- Accept `.jpg`/`.jpeg` (`image/jpeg`) anywhere PNG/BMP stills are accepted:
  native file dialog filter, web import path, server-side validation.
- Pillow already bundles JPEG decode; no new native dependency is expected.
  Prove it: the transitive native audit shows no FFmpeg/libav content and no
  new unowned dependency, exactly as the standing audits require.
- Tests: JPEG still import produces the same single-frame result as an
  identical PNG; malformed JPEG rejected with task language; the file-dialog
  filter and README wording match.
- Commit as one slice with verification.

### R66-2 — Experimental ARM64 CI (owner decision 2026-08-02)

- Best-effort native Windows ARM64 and Linux ARM64 jobs in the desktop
  workflow: quick architecture, native-tree, policy, frozen-smoke, and
  package-smoke verification.
- Experimental and non-blocking: `continue-on-error`, kept out of candidate
  metadata, provenance, supported-platform documentation, and public release
  assets. No support claim is added for either architecture.

### R66-3 — Release packet

- `docs/releases/0.1.66.md` release notes and an unposted
  `docs/announcements/reddit-0.1.66.md` draft, both accurate to the shipped
  content: three-mode macro editor (Text entry, Flow, Repeat), recaptured
  screenshots, JPEG import, same platform set and unsigned status as 0.1.65.
- Extend the packet consistency test to the `0.1.66` packet (filenames,
  install docs, claims) mirroring the `0.1.65` historical test.

### R66-4 — Qualification

- Full repository verification entry point on the final commit.
- macOS native build via `python build.py --skip-sync`, frozen `--smoke-test`,
  signature-state, integrity, provenance, package, install, and launch
  checks. Trust-warning flows are **not** reenacted: signing, notarization,
  installer format, identity, download path, OS generation, and security
  mechanism are unchanged (2026-08-03 decision).
- CI produces the Windows x64 and Linux x86-64 candidates; all five public
  assets plus `SHA256SUMS.txt` and `release-manifest.json` are verified by
  hash and GitHub attestation before publication.
- No new hardware write: the macro rework is UI-only over unchanged protocol
  paths, and JPEG import touches no device boundary. Existing Neon 80
  validation and sustained owner use remain the hardware baseline.

### R66-5 — Publication (each action needs its own explicit owner go)

1. Tag `v0.1.66` on the qualified final commit and publish the GitHub
   Release as normal/latest with the five assets.
2. Disposition of the withdrawn `v0.1.65` draft: delete it, or retain it as
   a draft. Recommended: delete — a permanently stalled draft only misleads.
3. Reddit announcement (`docs/announcements/reddit-0.1.66.md`) — separate
   outward-message gate, posted only on explicit owner approval.

## Non-goals

- No hardware writes beyond existing qualification, no provider requests, no
  security-setting changes, no ARM support claims, no history rewrites, and
  no movement of the `v0.1.65` tag or assets.

## Rollback

If a blocking defect is found after publication: withdraw the `v0.1.66`
Release to draft (never delete the tag), record the defect in
`.agents/state.md`, and repair on a new commit. The `0.1.65` line is not a
rollback target — it was already withdrawn.
