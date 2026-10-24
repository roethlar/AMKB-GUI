# Unsupported-board detection and support report

**Status:** Complete on `main` as of `d2e0be3` (2026-08-22), after the 0.1.68
release. No fifth keyboard family is implemented; this plan completes the safe
intake path for identifying the next candidate.

## Objective

When a USB keyboard is present but not a supported Angry Miao family, the app
says so clearly and can package a **read-only, sanitized device report** for
GitHub issue submission — without writing to the keyboard and without leaking
host paths or user identity.

Known limit (standing): serial-protocol LED geometry is not probeable; lighting
support for new serial families still needs a physical board or vendor source.

## Landed behaviour (evidence)

- `/api/devices` marks every discovered device with the server-owned
  `supported` classification derived from `device_mapping`.
- The Devices dialog keeps unsupported keyboards out of normal read/write
  selection and distinguishes them from an empty scan or a dongle/non-keyboard
  device.
- **Copy support report** and **Save report** fetch the read-only
  `/api/devices/support-report` result. Nothing is posted automatically.
- The JSON report removes host paths, serial numbers, and other local device
  topology while retaining model/protocol evidence useful for a GitHub issue.
- README tells users how to export and submit the report.

## Non-goals

- Auto-supporting a new board’s lighting or keymap.
- Writing firmware or probing destructive commands.
- Broad USB enumeration of every HID device on the bus (unless a later slice
  expands discovery deliberately).
- Posting to GitHub from the app (user copies the report).

## Slices

### UB-1 — Sanitized report builder (landed `59967d1`)

Pure library + unit tests:

- Classify a scanned device payload as supported vs unsupported using
  `device_mapping.led_model` (supported iff it resolves to a known family).
- Build a JSON report: app version, OS, list of devices with redacted fields
  (no OS paths, no home directories, no raw `address`/`path` that encode host
  topology; keep product_id, transport kind, firmware version, pages, USB
  vid/pid when present, is_keyboard).
- Title/summary strings for “new keyboard model detected” when any unsupported
  keyboard is present.

### UB-2 — API (landed `59967d1`)

- `GET /api/devices/support-report` runs the same discovery as
  `/api/devices` and returns the report. Read-only. No device write.

### UB-3 — UI (landed `d2e0be3`)

- Device list empty state: if scan found non-keyboard or unsupported
  keyboards, show that distinction.
- “Copy support report” / “Save report” for GitHub when unsupported devices
  exist.

### UB-4 — Docs (complete with this closeout)

- Add a brief README note once the UI is user-facing; keep install docs
  options-only (decision 2026-08-08).
