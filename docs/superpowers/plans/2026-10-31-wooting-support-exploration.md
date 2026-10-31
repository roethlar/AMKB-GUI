# Wooting Support Exploration Plan

Status: **draft, exploration-only.** Authorized scope is read-only evidence
gathering and a go/no-go note. No code, test, packaging, or hardware-write work
is authorized. Pending owner ruling **W1** (below) decides what, if anything,
follows exploration. Until W1 is ruled, do not start an implementation slice.

## Goal

Determine whether the application can add read-only identification and,
later, configuration support for Wooting keyboards, and what protocol facts
and identity evidence that requires. The output is a recorded go/no-go
finding with its evidence, not a shipped feature.

## Context a cold agent needs

- The application is MIT-licensed (`.agents/decisions.md`, "License follows
  capability"). Establishing protocol facts by reading a binary or bundle is
  permitted. Copying vendor code or expression is not; record facts (IDs,
  magic words, packet sizes, command numbers, framing rules) in your own words.
- Existing device families are described in `.agents/decisions.md`
  ("AM Neon 80 supported at full parity or not at all" and "The device seam
  sits below the protocol encoding"). Neon 80 is a Vial/QMK raw-HID device
  identified by `05AC:024F` plus a `vial:` serial prefix, with a three-stage
  identity gate in `am_configurator/hid_transport.py`. The AM CDC-serial
  families live in `device.py` and `protocol.py`. Per-family limits are in
  `am_configurator/device_mapping.py` (`FamilySpec`, `_FAMILY_SPECS`).
- Unsupported keyboards are currently reported, not driven
  (`am_configurator/device_report.py`; commit `d2e0be3`). Any Wooting work must
  start from that classification, not bypass it.
- Hardware-write safety is absolute: writes are manual, GUI-initiated, gated on
  device/model match plus typed confirmation. Automated tests and smoke tests
  must never write to a keyboard (`.agents/repo-guidance.md`, Device Safety).

## Evidence already gathered (assumptions to re-verify)

Gathered 2026-10-31 on the machine recorded in `.agents/machines.md`.
Treat these as leads to confirm, not established facts.

- Wootility is an Electron app at the local Wootility install directory. Its
  logic is in `resources/app.asar`, an uncompressed-JS archive. The Wooting
  HID module contains a `WootingHidDevice` class and a `ProtocolRevision` enum
  (Legacy, V2, V2_SplitPackets, V3).
- Interface revisions are chosen by usage page and output-report size:
  V3 uses config usage page `ConfigInterfaceV3UsagePage` and report ID 1; the
  other revisions use packet sizes 128 (Legacy), 256 (V2), or 64 split (V2
  split). Analog interface revisions V1 (value max 255) and V2 (value max
  1023) exist as separate HID interfaces.
- Commands are sent with `sendFeatureReport`; responses arrive via
  `oninputreport` and are reassembled across split packets. Magic words differ
  per revision (`MAGICWORD`, `MAGICWORD_V3`).
- Vendor ID is `0x31E3` (appears in the bundle).
- The full-bundle REA analysis (`analyze_javascript_application`) failed twice:
  an unpacked `esbuild.exe` integrity mismatch (accept with
  `integrity_policy=record-and-continue`), then a 600 s per-source
  `provider_timeout` on the whole ~190 MB archive. REA's remediation is to
  select exact `source_paths`; that requires the inventory paths of the
  Wooting module first.

## Method

1. **Locate the Wooting module inside the archive.** Parse the asar header
   (a Chromium pickle followed by JSON) and list file entries whose names
   contain `wooting` (case-insensitive). Record the exact inventory paths.
   Assumption to verify: the names are not `wootingHid*` exactly.
2. **Extract only those sources**, then analyze them: either REA
   `analyze_javascript_application` with `source_paths` set to the exact
   inventory paths and `integrity_policy=record-and-continue` if needed, or
   plain text search over the extracted files. Prefer the extracted-file
   route if REA times out again; the goal is the facts, not the tool.
3. **Extract the protocol facts into a note** (see Deliverables). For each
   command, record: numeric ID, direction, request/response length, whether it
   is read-only or mutating, and how identity is established (model, serial,
   firmware, or nothing). Mark any inference not directly observed as an
   assumption.
4. **Cross-check the identity question.** Determine whether the device can
   self-identify with a read-only command equivalent to the Neon 80's stage-3
   check. If it cannot, record that as the central blocker: without a
   positive identity, no write is authorized by the existing gate design.
5. **Read-only hardware evidence, only if a physical board is available and
   the owner permits it.** Enumerate HID devices and record VID/PID, usage
   page, usage, and output/feature report sizes. Send no feature reports and
   no output reports to the device. Any command that could mutate state is
   out of scope for this plan regardless of safety of the specific command.
6. **Write the go/no-go note** (Deliverables) and close with a one-line
   recommendation for W1.

## Deliverables

- `docs/superpowers/notes/2026-10-31-wooting-protocol-observations.md`: the
  protocol facts from step 3 and the identity findings from step 4. Each fact
  carries its evidence source as a path inside the archive, not a copied code
  body. Include the asar inventory paths and the bundle's file hash.
- A dated entry in `.agents/machines.md` under the current machine's heading
  for the local Wootility and Wooting SDK install paths. Machine paths do not
  go in `state.md` or in the plan.
- The go/no-go note as a section at the end of the observations note: one
  recommendation, its evidence, and the main risk.

## Pending owner ruling

**W1 — first slice after exploration.** Problem: exploration can end with no
support, read-only identification, or full configuration. Change: W1 selects
the next plan. Options and cost:

- **Defer:** keep Wooting out of scope. Cost: none now.
- **Read-only identify:** add discovery and a support-report classification for
  Wooting VID/PID only, with no writes. Cost: small; this exercises the
  transport without any device risk.
- **Full configuration:** keymap, analog, and RGB writes behind the existing
  identity-and-confirmation gate. Cost: large, plus hardware validation on a
  physical board.

Recommendation: **read-only identify** if exploration shows a read-only identity
path; otherwise **defer**. Do not select full configuration before the
identity question is answered.

## Non-goals

- No code, test, packaging, or release change.
- No device write of any kind, including feature reports used for probing.
- No reuse of the Neon 80 lighting protocol for any Wooting device.
- No push, tag, or release, and no announcement.
- No copying of vendor code into the repository.
