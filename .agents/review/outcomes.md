# Whole-change review outcomes

- 2026-07-25 — openreview codex, third pass (codex-cli 0.145.0, CLI transport
  with `--output-last-message`; codex's own configured model and effort) over
  `65a70c9bff19b8cff7313efdf10bb35c48484939..94a847a5805cf0a69b01c0a9f124217c36579c61`,
  the first pass over implementation rather than the plan: verdict `findings`,
  three raised, all three admitted at intake. Detail in
  `.agents/review/findings/or-1.md`, `or-2.md`, `or-3.md`; scoreboard in
  `.agents/review/index.md`.
  HIGH (or-1): N2's transport seam sits above the protocol encoding —
  `server.py:2049` plans AM 64-byte serial frames and `transport.py:68` receives
  only those bytes, so a raw-HID driver cannot construct `0xF0` or Vial writes
  from what the seam passes. Correcting it changes N2's architecture rather than
  repairing it, so it is referred to the owner before any work starts.
  HIGH (or-2): `blank_config` (`server.py:130-165`) keeps a second copy of the
  family rules — hardcoded 90 and 24 track lengths plus its own `AM21`
  normalization — which N1 made `device_mapping` the authority for. The
  observable failure is gated on N4. The stronger suspicion that
  `relic = product_id == "80"` misses the Relic's real `AM21` identifier was
  **disproved by execution**: line 131 normalizes first, and both identifiers
  produce the edge track.
  MEDIUM (or-3): `FamilySpec` models macro capacity as event counts with a
  `None` "device-reported" escape hatch, but Vial reports `GET_BUFFER_SIZE` in
  bytes, and the browser consumers written in the same change do not handle
  `None` — they would render "Up to null tracks" and a permanently tripped
  limit.
  Routing deviation, recorded deliberately and unchanged from the two prior
  passes: no `.agents/review/harnesses.local.json` exists on this machine, so
  both review playbooks would fail closed; the owner's standing "defaults, just
  codex" direction was applied, using codex's own configured model and effort
  rather than an owner-confirmed tier mapping. The reviewer ran under
  `--sandbox read-only`, which forbids the disposable worktree the playbook
  describes; openreview's verdict schema carries no `guard_confirmed` field, so
  the contract is satisfied without it, but the reviewer executed no tests and
  every finding was verified by this session instead.

- 2026-07-20T21:53:11Z — openreview grok (`grok-4.5-build` @ `high`,
  fallback) over
  `98abb138406093dacea97df2b49be91aa11fdf10..6c1f7337d162eb59015265690e88a5d02d7be962`:
  no material issue.
- 2026-07-22 — ultracode holistic multi-agent review (`claude-fable-5`;
  12 dimension reviewers + 6 gap finders + independent gate run, every
  non-nit finding adversarially verified by 3 refuter lenses) over
  `98abb138406093dacea97df2b49be91aa11fdf10..89d194d0100b88ada3e96382ecfea1c15d43762e`:
  61 confirmed findings (1 critical, 12 major, 47 minor, 1 downgraded to
  nit), 4 refuted, 22 polish nits; verification entry point green at head.
  Full report with failure scenarios and verifier evidence:
  `2026-07-22-holistic-branch-review.md`. At that review head, the findings
  had not yet passed codereview intake triage and none was fixed.
- 2026-07-25 — openreview codex, second pass (codex-cli 0.145.0, CLI transport
  with `--output-last-message`; `gpt-5.6-sol` @ `xhigh`, owner-configured
  default) over
  `65a70c9bff19b8cff7313efdf10bb35c48484939..ed805a5452ce036afb1a6f255ccce93a73ad53a0`,
  a fresh thread rather than a reply so the reviewer was not primed by its own
  prior findings: verdict `findings`, three raised, all three admitted after
  independent verification.
  HIGH: N4 planned to transcribe firmware `real_map`, `h_map`, and `s_map` into
  host-side position maps, but those are `{chip_index, x, y}` AW20216 driver
  coordinates that the firmware applies *after* receiving a frame. The host
  sends a linear payload — 89 axial values and 230 row-major head values — so
  transcribing them would map twice and scramble every LED. The same finding
  notes side must not be an authored `_LAYOUTS` entry, because
  `device_mapping.py:427` publishes every entry as independently selectable
  while the official driver derives side from head and pushes channels
  `slot`, `slot+3`, `slot+6` from one authored payload.
  HIGH: Neon geometry was scoped to `device_mapping.py` alone, but
  `server.py:490` validates hardcoded 200/90/24 track lengths, `app.js:1311`
  hardcodes the same, and `app.js:489` falls unknown models back to CyberBoard.
  A Neon profile could not be created, validated, edited, and written.
  HIGH: N7 left macro limits at the hardcoded 32 tracks and 200 events of
  `app.js:1121` and `app.js:1215` without preflighting the device-reported
  Vial `GET_COUNT` and `GET_BUFFER_SIZE`, risking a partial macro-buffer
  rewrite that the planned one-macro test would not catch.
  Consequence beyond the plan: because no GPL firmware table needs
  transcribing after all, the premise of the 2026-07-25 relicensing decision
  no longer holds and is referred back to the owner.
- 2026-07-25 — openreview codex (codex-cli 0.145.0, MCP transport;
  `gpt-5.6-sol` @ `xhigh`, owner-configured default) over
  `65a70c9bff19b8cff7313efdf10bb35c48484939..cacced2569d262241dd68fffb37c3c2970424e4a`:
  verdict `findings`, five raised, all five admitted at intake triage.
  Four concern the draft AM Neon 80 plan and one the canonical state file.
  HIGH: the plan wires no HID transport into `server.py`, whose
  `/api/devices`, `_read_device`, and `_write_device` routes are all keyed on
  a serial port string, so every new module would be unreachable from the GUI.
  HIGH: the plan's lossless keycode round-trip is impossible, because
  `web/app.js:1091` accepts any 32-bit `#`+8-hex raw code and `app.js:1084`
  advertises that passthrough, while QMK keycodes are 16-bit. HIGH: matching
  only VID/PID plus a `vial:` serial prefix identifies any Vial board, not a
  Neon 80, which is too weak to gate a hardware write under the device-safety
  rule. HIGH: relicensing was merely preferred before the GPL-derived table
  task rather than mandatory, so an intermediate published commit would carry
  GPL-derived tables under MIT metadata. LOW: `.agents/state.md` still queued
  drafting the plan that the same branch adds.
  Routing deviation, recorded deliberately: the owner directed "defaults, just
  codex", so this dispatch used codex's own configured model and effort
  instead of the playbook's owner-confirmed tier mapping. No
  `.agents/review/harnesses.local.json` exists on this machine, so both review
  playbooks would otherwise have failed closed. The verdict payload arrived
  truncated by this harness's output compression on both the initial dispatch
  and the single permitted re-emission; two findings were reconstructed from
  partial text, and every code citation was independently verified against the
  repository before admission rather than accepted on reviewer prose.
- 2026-07-23 — Codex goal-first self-review over
  `98abb138406093dacea97df2b49be91aa11fdf10..68ef6713f2cdfb8b4109776d4ee55e27c3dfc7ad`:
  no material implementation issue. The owner-approved remediation ledger
  closes every in-scope holistic finding one item per commit. The final
  repository gate, macOS `0.1.34` native build, frozen offline smoke, signed
  bundle and prohibited-runtime inspection, and no-provider/no-hardware UI
  matrix were green. The UI matrix found one first-open generation-dialog
  ordering regression; `68ef671` closed it with a red-proven executable test
  and a clean real-browser recheck.

- 2026-07-30 - codereview codex (gpt-5.6-sol @ high, standard, escalated: T1) over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3: verdict findings, capability_ok true; 5 admitted at intake (cx-1..cx-5, two MEDIUM three LOW), none declined. Verdict artifact: schema-enforced JSON via codex exec --output-schema.
