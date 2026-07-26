# AM Neon 80 on Linux

The AM Neon 80 is reached over raw HID rather than a serial port. On Linux the
kernel exposes that interface as a `hidraw` node owned by root, so AM
Configurator cannot open it as a normal desktop user until a udev rule grants
access. macOS and Windows need no equivalent step.

If the application reports *"Permission denied opening the keyboard"*, this page
is the fix.

## Install the rule

The rule ships with the application at `packaging/linux/60-am-neon-80.rules`.

```sh
sudo cp packaging/linux/60-am-neon-80.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then **unplug and replug the keyboard** — udev applies rules when a device
appears, so a board that was already connected keeps its old permissions.

## What the rule does

```
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{serial}=="*vial:f64c2b3c*", MODE="0660", TAG+="uaccess"
```

`TAG+="uaccess"` gives the device to whoever holds the active local login
session, which is what a desktop application needs and is preferable to a
world-writable node. `MODE="0660"` is the fallback for systems without logind.

The rule matches Vial keyboards by serial number, and it covers every Vial
board rather than only the Neon 80. That is Vial's own published rule.
`vial:f64c2b3c` is **not** this keyboard's individual identifier: every Vial
keyboard reports that exact string, which is precisely why a single rule can
serve all of them. Do not narrow it to a specific board's identifier — the
application distinguishes individual boards internally, using a per-device UID
the keyboard reports over its own protocol, not the USB serial.

## Verifying

With the keyboard connected:

```sh
ls -l /dev/hidraw*
```

At least one node should be readable and writable by your user. If every node is
still `root root` with `0600` permissions, the rule did not apply — confirm the
file landed in `/etc/udev/rules.d/`, that the reload and trigger ran without
error, and that the keyboard was replugged afterwards.

## If it still fails

- **Another application holds the device.** Vial, VIA, QMK Toolbox, or a second
  copy of AM Configurator will claim the raw HID interface exclusively. Close it
  and retry; the application reports this case separately from a permission
  problem.
- **Flatpak or Snap sandboxing.** A confined package may not see `/dev/hidraw*`
  regardless of udev. Grant the sandbox raw-device access, or run the
  unconfined build.
