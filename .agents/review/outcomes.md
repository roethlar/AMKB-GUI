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
- 2026-07-30 - cx loop closed: all five findings fixed one-commit-each (cx-1 1bb4a21, cx-2 e3d46dd, cx-4 09de26b, cx-3 6636be7 + guard repair 63bc853, cx-5 b360d77) and verified by codex/gpt-5.6-sol@high per-finding dispatches with independent guard proofs (guard_confirmed=true on every accepted verdict). cx-3 round 1 reopened correctly: the guard was vacuous for the success path, and that round's worktree proof was blocked by a sandbox denial on .git/worktrees - later rounds carry a local-clone fallback. Environment notes: reviewer children's shell calls were intercepted by the ptk hook (recorded, not invalidating); ptk inline shaping mangled one verdict payload (PowerShell-Token-Killer#14), all verdicts read from the --output-last-message files.
- 2026-07-30 — codereview claude (claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `1448f9135956f31cee3f45dd8fcbaf8de066074a..e4e32f9a4a5f2797552a956a27735be5471d8949`:
  verdict `findings`, `capability_ok=true`; three raised and all three admitted
  after independent intake verification (`cl-1` HIGH, `cl-2` MEDIUM, `cl-3`
  LOW), none declined. The CLI exited zero with a schema-enforced envelope,
  exact pinned SHAs, and transcript model key `claude-opus-5`. Intake reproduced
  both Library failures in isolated temporary roots and checked the plan finding
  against the current workflow and packaging guard. Environment note: a Claude
  hook rewrote one git command through `rtk`, which the launch allowlist denied;
  the reviewer recovered with allowed git inspection and completed the
  capability proof. The coder tree remained clean during the dispatch.
- 2026-07-31 — `cl-1` closed: implementation commit
  `36338cbc91520436bbc97fabf3761106bd538f0a` accepted by
  claude/claude-opus-5/xhigh/frontier (`escalated: T2`) against parent
  `6f7865e8bc9cf6f8b77d2b7f0eb1c1a9b530c67b`;
  `guard_confirmed=true`, `capability_ok=true`. The reviewer independently
  proved the focused guard red with the base `library.py` and green with the
  reviewed file, reran 640 Python tests successfully with 5 expected skips,
  removed its disposable worktree, and left the coder tree clean. Hook-rewritten
  git and one Grep call were denied and recovered through allowed operations;
  recorded as environment notes, not invalidation.
- 2026-07-31 — codereview claude (claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `43eae714b80322b5424efaced46a1826dfd67753..7586bf7daab187a158a5c929cafcb80f9af97d10`:
  verdict `findings`, `capability_ok=true`; two raised and both admitted after
  independent intake verification (`cl-4` MEDIUM, `cl-5` LOW), none declined.
  No workflow or test defect was reported; both findings are durable-record
  drift left after A1 landed. The CLI exited zero with a schema-enforced
  envelope, exact pinned SHAs, and transcript model key `claude-opus-5`.
  Environment note: the repository hook rewrote the reviewer's first git
  command through `rtk`, and an attempted upstream WebFetch was outside the
  launch allowlist; both were denied. The reviewer recovered with allowed
  repository reads and git inspection, completed the capability proof, and
  left the coder tree clean.
- 2026-07-31 — A1 record-drift loop closed: `cl-4` repair
  `c443f03605e93e0f288a6d9e0f8ff5d5d1b4d487` and `cl-5` repair
  `227019705bacfe89862a24bbbe4349176b487818` were each accepted by
  claude/claude-opus-5/high/standard against their pinned parents, with
  `guard_confirmed=true` and `capability_ok=true`. Both reviewers independently
  reproduced the false base record and corrected head record, ran the focused
  Node 24 guard (`cl-5` ran all 51 packaging tests), removed their disposable
  worktrees, and left the shared tree clean. Hook-rewritten `rtk git` spellings
  were denied and recovered through permitted operations.
- 2026-07-31 — codereview claude (`claude-opus-5` @ `high`, standard) over
  `791ca06d9012235f9f6af842275e568004bbe418..2e92b62ac0736376a37045b88c8ba043dab8b9dc`:
  infrastructure failure, not a verdict. The single `fable-review` dispatch
  used explicit model and effort flags and a 900-second PTK execution budget,
  but the outer MCP caller disconnected at 300 seconds. PTK kept the child
  alive; it later completed with exit code 0, but the schema-enforced envelope
  and its `ptk_output` handle were no longer discoverable. Capability proof,
  clean/findings verdict, and finding data are therefore unknown. Per owner
  direction the paid review was not rerun. The recovery defect is recorded at
  PowerShell-Token-Killer#16; this failed pass admits no findings and must not
  be represented as a clean review.
- 2026-07-31 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `6a06f3beb93cb1887b85ed7f0da1171d12ad8c31..c01357e90e38b71c9af0303522c104226a68888b`:
  verdict `findings`, `capability_ok=true`, exact pinned SHAs, exit 0, and no
  stderr. One LOW candidate was admitted as `cl-6`: the implementation keeps
  the CyberBoard switch layout and 40×5 display correctly separated, but the
  new dual-map model lacked a guard on that target gate. The focused guard was
  proven red against the predicted 83-for-200 regression and green after
  restoration; the full repository gate passes. The reviewer's hook-rewritten
  `rtk git` spelling and two temporary-file Grep attempts were denied, but it
  recovered with allowed repository reads, git inspection, and all 127 web
  tests. The paid result was persisted locally before parsing and was not
  rerun or reformatted.
- 2026-07-31 — `cl-6` closed at repair commit
  `0b6778f28482a664047df4ee0d830f9da1524a6f`. The owner explicitly skipped a
  second paid Claude verification call and accepted the deterministic
  red/green mutation proof plus the full repository gate as closure evidence.
  No additional reviewer request was made.
- 2026-07-31 — openreview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-fable-5` @ `max`, owner-selected one-shot, frontier grade not
  pre-recorded) over
  `0c91a6d62485cf8e49efad70f7188a3d37f18de6..031e5ffc5eda1214970f4bbe676683fc590ebe3e`:
  substantive verdict `best_approach`, `capability_ok=true`, exact pinned SHAs,
  exit 0, transcript model key `claude-fable-5`, and no findings. The reviewer
  independently judged the successor-plan structure, exact identity contract,
  and R65-G1 pre-freeze readiness gate to be the approach it would take. It
  reported one non-blocking wording nit: `4a3c6eb` is the P6 closure-record
  commit rather than an implementation commit, although the exact-head
  qualification claim remains true. The schema-enforced payload violated the
  playbook's semantic contract by putting a three-file changed-path inventory
  in `material_changes` while returning `best_approach`; those entries did not
  request changes, and the comparison explicitly endorsed the reviewed state.
  Per the owner's standing direction, the usable judgment was recorded with
  that deviation instead of discarded or resubmitted. Exactly one Claude
  review request was made. Raw output was persisted locally before parsing.
- 2026-08-01 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `c2f6fcedb98e33d7406eace3c3af4ed53d59ffb7..8b411abfab7cb5966d4c7e4ff413f14a4cc5fc57`:
  verdict `findings`, `capability_ok=true`, exact pinned SHAs, exit 0, and
  no stderr. Direct source verification qualified all three candidates.
  `cl-7` HIGH (synthetic WebView2 pointer capture) was admitted and verified
  first. `cl-8` MEDIUM (geometry bounds can exceed the version-1 ±8 schema)
  was then admitted and independently verified. `cl-9` LOW (the volatile
  `nagatha` address is duplicated outside `.agents/machines.md`) was admitted
  last and independently verified. The outer PTK caller timed out at 300
  seconds, but
  the original child remained alive and its persisted schema-enforced result
  completed after 8 minutes 21 seconds with transcript model key
  `claude-opus-5`. The data was recovered from that same invocation; no
  review was discarded, reformatted, rerun, or resubmitted. Hook-rewritten
  `rtk git` and several Grep/rg forms were denied, but allowed repository
  reads and git inspection completed the capability proof.
- 2026-08-01 — owner salvage ruling: the `cl-8` and `cl-9` verification
  requests were mistakenly dispatched to `claude-opus-5` at `high` after the
  owner had directed `claude-fable-5` at `xhigh`. Both completed once with
  schema-valid `accepted` verdicts, exact pins, independent guards, exit 0,
  and no stderr. The owner directed that those completed reviews be salvaged.
  Their actual Opus provenance is retained in the finding records; neither
  review was discarded, replaced, rerun, or resubmitted. All remaining repair
  slices use the owner-directed Fable pair.
- 2026-08-01 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-fable-5` @ `xhigh`, standard, inline/session-only) over
  `6bf41b9a0a04b03e84cfbc5ea16794d7eb5fe4b3..4a9e6b89233e9549a4b9b05ca14613a2f2115eb6`:
  verdict `clean`, `capability_ok=true`, exact pinned SHAs, no findings, exit
  0, and no stderr. The schema-enforced first result was persisted locally and
  used as returned; it was not discarded, reformatted, retried, replaced, or
  resubmitted. A hook-rewritten `rtk git` spelling and two inspection forms
  were denied, but the reviewer recovered through allowed repository reads
  and git inspection and completed the capability proof.
- 2026-08-01 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-fable-5` @ `xhigh`, standard, inline/session-only) over
  `042f55003c9e56e14ce023cc201bb0d62fd89c98..041c26fe2c069b1a237464aedd8fb150c1cb89c1`:
  verdict `clean`, `capability_ok=true`, exact pinned SHAs, no findings, exit
  0, and no stderr. The schema-enforced first result was persisted locally and
  used as returned; it was not discarded, reformatted, retried, replaced, or
  resubmitted. A hook-rewritten `rtk git` spelling, one temporary-file read,
  and one temporary-file Grep were denied, but the reviewer recovered through
  allowed repository reads and git inspection and completed the capability
  proof.
- 2026-08-01 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-fable-5` @ `xhigh`, standard, inline/session-only) over
  `a96aa35979e896c6077a61b6894ac8c8e9296ab7..25c58d5abed2e1dd8f289be350cbbb85a1f9187c`:
  verdict `clean`, `capability_ok=true`, exact pinned SHAs, no findings, exit
  0, and no stderr. The schema-enforced first result was persisted locally and
  used as returned; it was not discarded, reformatted, retried, replaced, or
  resubmitted. Two hook-rewritten `rtk git` forms and one Grep form were denied,
  but the reviewer recovered through allowed repository reads and git
  inspection and completed the capability proof.
- 2026-08-02 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `cbf1346070fb908bd932028508f3c43923fe0057..1ee73a81182c8f401b1942776d3df7c005541f33`:
  verdict `findings`, `capability_ok=true`, exact pinned SHAs, one HIGH
  candidate, exit 0, and no stderr. Direct source verification admitted it as
  `cl-10`: backend-valid lowercase profile colors are rejected before Board
  projection and can blank the Lighting Studio. PTK's outer caller timed out
  at 300 seconds, but the original child stayed alive and its persisted first
  substantive result completed after 16 minutes 6 seconds. That same result
  was used as returned; it was not discarded, retried, replaced, reformatted,
  or resubmitted. The transcript model key was `claude-opus-5`.
- 2026-08-02 — `cl-10` per-finding verification through codereview claude (job
  `fable-review`; claude-cli 2.1.220; `claude-opus-5` @ `xhigh`, frontier,
  escalated T2, inline/session-only) over
  `1ee73a81182c8f401b1942776d3df7c005541f33..95795845b6eeabd1c572b82244fef26a975183dd`:
  verdict `accepted`, `guard_confirmed=true`, `capability_ok=true`, exact pins,
  exit 0, and no stderr. A disposable worktree independently proved 9/9 green,
  8/9 with only the canonicalization guard red after restoring the base
  implementation, and 9/9 after restoration; all 144 browser tests also passed.
  Malformed-color probes remained rejected, the full 677-Python/144-browser
  persisted gate was confirmed, and the disposable worktree was removed and
  pruned without changing the shared tree. Exactly one verification invocation
  was made; it completed through the background wrapper without PTK timeout,
  retry, re-emission, replacement, or resubmission. The transcript model key was
  `claude-opus-5`.
- 2026-08-02 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `4bdb75f802dec338821ea827d397a7ebc091d8bd..65c9fbfc22c2b24c3b868218512b00039756e6e1`:
  verdict `findings`, `capability_ok=true`, exact pinned SHAs, two candidates,
  exit 0, and no stderr. Both reproduced and were admitted: `cl-11` MEDIUM,
  because repeated sessionless full renders consume the bounded LRU and evict
  an unrelated explicit preview session; `cl-12` LOW, because superseded
  sessionless renders receive no decode work check and only abort after full
  decode. The persisted first substantive result completed after 16 minutes 24
  seconds and was used as returned. It was not discarded, retried, re-emitted,
  replaced, reformatted, or resubmitted. The transcript model key was
  `claude-opus-5`.
- 2026-08-02 — `cl-11` per-finding verification through codereview claude (job
  `fable-review`; claude-cli 2.1.220; `claude-opus-5` @ `high`, standard,
  inline/session-only) over
  `bedd9b52c428fdc1cd9fb03c23a03816c7078a5c..9015d422d97d3be0ba9aa04a0ebeeec81c934335`:
  verdict `accepted`, `guard_confirmed=true`, `capability_ok=true`, exact pins,
  exit 0, and no stderr. A disposable worktree independently passed both
  focused guards, restored only the production module from the base and
  reproduced the unavailable retained session plus incorrectly superseded
  independent render, then restored the repair and returned both guards green.
  All 687 Python, 245 affected, and 144 browser tests passed. The worktree was
  removed and pruned without changing the shared tree. Exactly one verification
  invocation was made; it was not retried, re-emitted, replaced, reformatted,
  or resubmitted. The transcript model key was `claude-opus-5`.
- 2026-08-02 — `cl-12` per-finding verification through codereview claude (job
  `fable-review`; claude-cli 2.1.220; `claude-opus-5` @ `high`, standard,
  inline/session-only) over
  `1d5b992e2f4cbd742a4434ef966c88d6fa8dddd2..3865c1008a9798f4d882b2f81c445e7fc2e3261f`:
  verdict `accepted`, `guard_confirmed=true`, `capability_ok=true`, exact pins,
  exit 0, and no stderr. A disposable worktree independently proved the guard
  green, restored the production module from the base and showed epoch 1
  received no decoder check and completed decode, then restored the repair and
  returned green. All 688 Python, 246 affected, and 144 browser tests plus
  compile, syntax, and package gates passed. An auxiliary probe briefly wrote
  one line to the shared test file because a relative .NET path resolved against
  the repo; the reviewer detected and reverted it immediately, redid the proof
  in the disposable worktree, and left the shared tree clean. This session
  independently confirmed the restoration. Exactly one verification invocation
  was made; it was not retried, re-emitted, replaced, reformatted, or
  resubmitted. The transcript model key was `claude-opus-5`.
- 2026-08-02 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `b5d46d9402df4d47429b17aaf50326d1307024d8..92949d92ca6751073ce47fa2b5182c01ed247009`:
  verdict `clean`, `capability_ok=true`, exact pinned SHAs, no findings, exit
  0, and no stderr. The persisted first substantive result completed after 12
  minutes 35 seconds and was used exactly as returned; it was not discarded,
  retried, re-emitted, replaced, reformatted, or resubmitted. One hook-rewritten
  `rtk git log` form was denied, but the reviewer completed its repo inspection
  and capability proof through allowed commands. The transcript model key was
  `claude-opus-5`.
- 2026-08-02 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `e97b40280a494ff5446fb2954fe01ed84f565924..7052212445c269752a094217b1ab4813741b2ef7`:
  verdict `findings`, `capability_ok=true`, exact pinned SHAs, three MEDIUM
  candidates, exit 0, and no stderr. Direct source and dependency-backend
  verification admitted all three as `cl-14` through `cl-16`: queued media
  work can mutate playback after Source loses ownership; GTK's case-sensitive
  filter hides valid uppercase-extension media; and the plan-required
  selected-frame fast render tier has no browser caller. The persisted first
  substantive result completed after 16 minutes 37 seconds and was used as
  returned. It was not discarded, retried, re-emitted, replaced, reformatted,
  or resubmitted. One hook-rewritten `rtk git` command and one temporary-file
  Grep were denied; the reviewer recovered through allowed repository reads and
  git inspection and completed the capability proof. The transcript model key
  was `claude-opus-5`.
- 2026-08-02 — codereview claude (job `fable-review`; claude-cli 2.1.220;
  `claude-opus-5` @ `high`, standard, inline/session-only) over
  `ff7576a3912940829bf282c7e15d654017307358..1a8632b6b1b2dc4926f848235d10dadd4066e6e5`:
  verdict `accepted`, `guard_confirmed=true`, `capability_ok=true`, exact pinned
  SHAs, exit 0, and no stderr. PTK's outer MCP call ended at its 300-second
  transport ceiling despite a larger requested budget, but the original child
  remained alive and persisted the schema-enforced result after 5 minutes 32
  seconds. A provisional record at `5127f8a` was written during the short gap
  before those artifacts appeared; this entry corrects that lower-authority
  observation with the completed status and result. The first substantive
  result was used unchanged and was not discarded, retried, re-emitted,
  replaced, reformatted, or resubmitted. The reviewer independently reproduced
  the native `queued_render_stopped_playback` mutation failure, restored all
  six format/viewport cases green, passed 63 focused and all 158 browser tests,
  and removed its detached worktree without changing the primary tree. One
  hook-rewritten `rtk git diff` command was denied; allowed reads and git
  commands completed the capability proof. The transcript model key was
  `claude-opus-5`; the immutable result SHA-256 is
  `01C3136D8DD4F8F20175DC32ED2A05E0533A2C03BC777E1C5C4E288C22CC70BF`.
- 2026-08-02 — per-finding codereview claude (job `fable-review`; claude-cli
  2.1.220; `claude-opus-5` @ `high`, standard, inline/session-only) over
  `904f45c4b27ad4b3fdb9e55d31efc3c9610a17e9..027f2eb18cedd88974ae5a965de2176c0690f801`:
  verdict `accepted`, `guard_confirmed=true`, `capability_ok=true`, exact pinned
  SHAs, exit 0, and no stderr. The first substantive result was used unchanged
  and was not discarded, retried, re-emitted, replaced, reformatted, or
  resubmitted. In a disposable detached worktree the reviewer passed all 19
  desktop tests, replaced only `desktop.py` with the base version and
  reproduced the exact missing-`*.GIF` failure, restored the reviewed file to
  green, confirmed cross-backend parsing and unchanged signature-based decoder
  scope, and removed the worktree without changing the primary tree. Two
  hook-rewritten `rtk git diff` spellings were denied; allowed reads and git
  commands completed the inspection and capability proof. The transcript model
  key was `claude-opus-5`; immutable result SHA-256 is
  `217876161BA4856B24BFBE826E7A97BEA53337296290262DD8BC6455350B5775`.
