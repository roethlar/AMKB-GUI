# Unsupported-board detection and support report

**Status:** Approved in principle (owner 2026-08-03, state.md). Implementation
started 2026-08-08 with slice UB-1. AUR work is parked independently.

## Objective

When a USB keyboard is present but not a supported Angry Miao family, the app
says so clearly and can package a **read-only, sanitized device report** for
GitHub issue submission — without writing to the keyboard and without leaking
host paths or user identity.

Known limit (standing): serial-protocol LED geometry is not probeable; lighting
support for new serial families still needs a physical board or vendor source.

## Current behaviour (evidence)

- `/api/devices` returns whatever transports discover (`transport.discover`).
- UI (`app.js`) filters `device.is_keyboard` and labels the empty list
  “No supported keyboard found” — it does not distinguish “nothing plugged in”
  from “something plugged in we do not drive.”
- `device_mapping.led_model` / `spec_for_product` define supported families;
  unknown product IDs fall through to `_UNKNOWN_FAMILY_SPEC`.

## Non-goals

- Auto-supporting a new board’s lighting or keymap.
- Writing firmware or probing destructive commands.
- Broad USB enumeration of every HID device on the bus (unless a later slice
  expands discovery deliberately).
- Posting to GitHub from the app (user copies the report).

## Slices

### UB-1 — Sanitized report builder (this slice)

Pure library + unit tests:

- Classify a scanned device payload as supported vs unsupported using
  `device_mapping.led_model` (supported iff it resolves to a known family).
- Build a JSON report: app version, OS, list of devices with redacted fields
  (no OS paths, no home directories, no raw `address`/`path` that encode host
  topology; keep product_id, transport kind, firmware version, pages, USB
  vid/pid when present, is_keyboard).
- Title/summary strings for “new keyboard model detected” when any unsupported
  keyboard is present.

### UB-2 — API

- `GET` or `POST /api/devices/support-report` that runs the same discovery as
  `/api/devices` and returns the report. Read-only. No device write.

### UB-3 — UI

- Device list empty state: if scan found non-keyboard or unsupported
  keyboards, show that distinction.
- “Copy support report” / “Save report” for GitHub when unsupported devices
  exist.

### UB-4 — Docs

- One line in README or troubleshooting only if user-facing; keep install docs
  options-only (decision 2026-08-08).
