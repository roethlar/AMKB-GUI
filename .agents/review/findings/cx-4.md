# cx-4: The layout-audit command is hardwired to a Windows-only webview renderer

**Severity**: LOW — breaks the documented developer audit tool on macOS/Linux; shipped runtime unaffected.
**Status**: Open
**Branch**: —
**Commit**: (pending)

## Evidence
`build_tools/layout_audit.py:10-13` documents an unrestricted desktop-extra command, but `webview.start(... gui="edgechromium" ...)` at lines ~219-221 pins the Windows backend. Linux installs Qt-backed pywebview (`pyproject.toml:22`); `am_configurator/desktop.py:25-29` maps platform renderers. Trigger: run the documented audit command on macOS or Linux.

## Predicted observable failure
pywebview fails to initialize EdgeChromium on non-Windows hosts; the audit exits without producing a report.

## What
The audit tool copies the Windows renderer literal instead of the application's platform renderer policy.

## Approach
(pending)

## Files changed
(pending)

## Guard proof
(pending)

## Coder dispute (if any)

## Known gaps

## Reviewer comments
Raised by: Reviewer: codex / gpt-5.6-sol / high / standard, escalated: T1 — generation pass over 0271213487979a50641d41e614a63f9f3ed38076..3830e8489ef10c0259ac6925bf1e0ecdf75bb0d3.
