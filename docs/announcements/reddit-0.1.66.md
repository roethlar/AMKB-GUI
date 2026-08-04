# Reddit draft

> **Unposted draft.** Do not submit, edit, comment, or cross-post without a
> separate approval for the exact title, body, destination, and links.

## Destination

r/AngryMiao

## Title

[Release] AM Configurator 0.1.66 — keymaps, macros, and lighting for four Angry Miao keyboards

## Body

I have released **AM Configurator 0.1.66**, an independent open-source desktop
editor for Angry Miao keyboard profiles. It is a community project and is not
affiliated with or endorsed by Angry Miao.

You can:

- edit Keymap assignments on a keyboard-shaped layout;
- type, record, import, or edit Macros;
- paint Lighting frame by frame, import media, or use local effects;
- preview before applying a lighting slot;
- save reusable profiles, keymaps, macros, media, and lighting to the Library;
  and
- read or write a connected board — reading never changes anything on it.

Changes in 0.1.66:

- the macro editor now has three modes: **Text entry** (type the text, with
  Fast 10 ms, Slow 100 ms, or Natural timing from a WPM target or your own
  captured cadence), **Flow** (edit every event's key, down/up, and pause in
  place; combos like Ctrl+Alt+Del as ordinary rows), and **Repeat** (a key
  press N times at an interval, with the capacity cost quoted up front); and
- lighting media import accepts JPEG alongside GIF, PNG, and BMP.

The supported families are CyberBoard, AM Relic 80, AM AFA/AFA 2, and AM Neon
80. CyberBoard uses its physical key geometry for switch LEDs while keeping
the 40×5 top display as its own rectangular canvas.

AI is optional and off by default. If you enable it and configure your own
Ollama server or Direct API provider, it produces validated procedural LED
settings that are rendered locally. Every Generate action makes one request
without an automatic retry. Remote provider paths are experimental; manual
configuration does not require AI or an account.

### Downloads

- `AM-Configurator-0.1.66-macOS-arm64.dmg`
- `AM-Configurator-0.1.66-Windows-x64-Setup.exe`
- `AM-Configurator-0.1.66-Linux-x86_64.AppImage`
- `SHA256SUMS.txt`
- `release-manifest.json`

The installers aren't signed with a paid Apple or Microsoft publisher
certificate. The installation guide explains hash and GitHub attestation
checks plus the narrow per-application first-launch steps for unsigned apps;
do not disable Gatekeeper or SmartScreen globally.

A full write replaces keymaps, macros, and LED data together, so keep a saved
profile before writing to a board you have not used before.

Download:
https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.66

Release notes:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/releases/0.1.66.md

Installation and verification:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/installing.md

Bug reports:
https://github.com/roethlar/AMKB-GUI/issues/new/choose
