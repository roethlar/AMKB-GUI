# Whole-change review outcomes

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
