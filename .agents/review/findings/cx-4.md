# cx-4: The layout-audit command is hardwired to a Windows-only webview renderer

**Severity**: LOW — breaks the documented developer audit tool on macOS/Linux; shipped runtime unaffected.
**Status**: Verified
**Branch**: —
**Commit**: `09de26b`

## Evidence
`build_tools/layout_audit.py:10-13` documents an unrestricted desktop-extra command, but `webview.start(... gui="edgechromium" ...)` pinned the Windows backend. Linux installs Qt-backed pywebview (`pyproject.toml:22`); `am_configurator/desktop.py:25-29` maps platform renderers. Trigger: run the documented audit command on macOS or Linux.

## Predicted observable failure
pywebview fails to initialize EdgeChromium on non-Windows hosts; the audit exits without producing a report.

## What
The audit tool copied the Windows renderer literal instead of the application's platform renderer policy.

## Approach
`main()` now resolves the renderer through the application's own `_native_webview_policy()` (the same mapping the desktop shell uses) and passes it to `webview.start(gui=renderer, ...)`.

## Files changed
- `build_tools/layout_audit.py` — renderer from `_native_webview_policy()`
- `tests/test_app.py` — source guard: no `gui="edgechromium"`, policy import present

## Guard proof
- `tests/test_app.py::DesktopServerTests::test_layout_audit_uses_the_platform_webview_policy` — reverting `gui=renderer` to `gui="edgechromium"` FAILS; restoring PASSES. Full suite green (704 tests).

## Coder dispute (if any)

## Known gaps
Non-Windows execution of the audit tool is not exercised on this host; the guard is source-level plus a parse check.

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.

Reviewer: codex / gpt-5.6-sol / high / standard
codex-cli 0.146.0; reviewed 09de26b255844c36822cc07f3668bf92f33c8b9b base e3d46dd7a8070d0386f4a2420adf10fd51a38e36; guard_confirmed=true; verdict=accepted; 2026-07-30T05:42:28Z; comments: none.
