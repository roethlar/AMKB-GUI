# Reddit draft

> **Unposted draft.** Do not submit, edit, comment, or cross-post without a
> separate approval for the exact title, body, destination, and links.

## Destination

r/AngryMiao

## Title

[Release] AM Configurator 0.1.65 — keymaps, macros, and lighting for four Angry Miao keyboards

## Body

I have released **AM Configurator 0.1.65**, an independent open-source desktop
editor for Angry Miao keyboard profiles. It is a community project and is not
affiliated with or endorsed by Angry Miao.

The manual workflow comes first:

- edit Keymap assignments on a keyboard-shaped layout;
- type, record, import, or edit Macros;
- paint Lighting frame by frame, import GIF/PNG/BMP media, or use local effects;
- preview before applying a lighting slot;
- save reusable profiles, keymaps, macros, media, and lighting to the Library;
  and
- read or write a connected board through an explicit identity and confirmation
  boundary.

The supported families are CyberBoard, AM Relic 80, AM AFA/AFA 2, and AM Neon
80. CyberBoard now uses its physical key geometry for switch LEDs while keeping
the 40×5 top display as its own rectangular canvas.

AI is optional and off by default. If you enable it and configure your own
Ollama server or Direct API provider, it produces validated procedural LED
settings that are rendered locally. Every Generate action makes one request
without an automatic retry. Remote provider paths are experimental; manual
configuration does not require AI or an account.

### Downloads

- `AM-Configurator-0.1.65-macOS-arm64.dmg`
- `AM-Configurator-0.1.65-Windows-x64-Setup.exe`
- `AM-Configurator-0.1.65-Linux-x86_64.AppImage`
- `SHA256SUMS.txt`
- `release-manifest.json`

The packages have no paid Apple or Microsoft publisher identity. The
installation guide explains hash and GitHub attestation checks plus the narrow
per-application first-launch steps; it never asks you to turn off system
security globally.

### Testing disclosure

Native packages are built and smoke-tested on macOS arm64, Windows x64, and
Linux x86-64. Release publication is gated on exact-candidate platform, UI, and
physical Neon checks. The Neon device path has prior physical validation on one
AM Neon 80; its firmware does not expose LED read-back, so lighting is verified
visually and a device read is not a lighting backup. CyberBoard, Relic 80, and
AFA/AFA 2 have implementation, fixture, protocol, geometry, and regression
coverage rather than a claim of physical testing for this release.

Before any full write, save a complete portable JSON and keep the original
lighting source. A full write replaces keymaps, macros, and LEDs together. Neon
also requires its physical **Esc+F2** unlock, and other configurators must be
closed so they do not hold the HID interface.

Download:
https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.65

Release notes:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/releases/0.1.65.md

Installation and verification:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/installing.md

Bug reports:
https://github.com/roethlar/AMKB-GUI/issues/new/choose
