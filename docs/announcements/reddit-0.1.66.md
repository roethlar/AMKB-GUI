# Reddit draft

> **Unposted draft.** Do not submit, edit, comment, or cross-post without a
> separate approval for the exact title, body, destination, and links.

## Destination

r/AngryMiao

## Title

[Release] AM Configurator — a local, open-source editor for Angry Miao keyboards

## Body

**AM Configurator 0.1.66** is out — the first public release of a free,
open-source desktop editor for Angry Miao keyboards: keymaps, macros, and
lighting for CyberBoard, AM Relic 80, AM AFA/AFA 2, and AM Neon 80. It's a
community project, not affiliated with or endorsed by Angry Miao.

Why it exists: the vendor tooling is a web app, and I wanted an editor that
lives on my own computer. Profiles are plain JSON you can keep and diff,
nothing needs an account, everything works offline, and the code is right
there to read. I couldn't find that, so I wrote it.

What you can do with it:

- edit keymaps on a keyboard-shaped layout, with every layer in reach;
- build macros three ways:
  - **Text entry** — type the text, with Fast (10 ms), Slow (100 ms), or
    Natural timing (a WPM target or your own captured cadence);
  - **Flow** — edit every event's key, down/up, and pause in place; combos
    like Ctrl+Alt+Del are ordinary rows; and
  - **Repeat** — a key press N times at an interval, with the capacity cost
    quoted up front;
- paint lighting frame by frame, import GIF, PNG, BMP, or JPEG media, or use
  local effects;
- preview before applying a lighting slot;
- keep reusable profiles, keymaps, macros, media, and lighting in a local
  Library; and
- read or write a connected board — reading never changes anything on it.

Where it honestly stands: it runs on macOS, Windows, and Linux, and the
installers are built and smoke-tested on all three. My own Neon 80 gets daily
use with it; the other families are implemented against protocol fixtures and
geometry tests, not hardware-tested boards. You'd be among the first people
outside my desk to run it — expect rough edges.

AI is optional and off by default, and nothing above needs it. With your own
Ollama server or a Direct API provider it produces validated procedural LED
settings, rendered locally — one Generate click, one request, no retries.
Remote provider paths are experimental.

### Downloads

- `AM-Configurator-0.1.66-macOS-arm64.dmg`
- `AM-Configurator-0.1.66-Windows-x64-Setup.exe`
- `AM-Configurator-0.1.66-Linux-x86_64.AppImage`
- `SHA256SUMS.txt`
- `release-manifest.json`

The installers aren't signed with a paid Apple or Microsoft publisher
certificate. The installation guide explains hash and GitHub attestation
checks plus the narrow per-application first-launch steps for unsigned apps;
do not disable Gatekeeper or SmartScreen globally. A full write replaces
keymaps, macros, and LED data together, so keep a saved profile before
writing to a board you have not used before.

**The ask:** if you have one of these boards, try it and tell me what breaks,
what's missing, and what's confusing. Bug reports and feature ideas both
help — links below.

Download:
https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.66

Release notes:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/releases/0.1.66.md

Installation and verification:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/installing.md

Bug reports:
https://github.com/roethlar/AMKB-GUI/issues/new/choose
