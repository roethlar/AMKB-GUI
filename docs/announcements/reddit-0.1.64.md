# Reddit draft

> **Rejected unpublished 0.1.64 candidate.** This historical draft was never
> posted and must not be reused for the `0.1.65` candidate.

## Title

[Release] AM Configurator 0.1.64 — open-source Neon 80 keymaps, macros, and Lighting Studio

## Body

I have released **AM Configurator 0.1.64**, an independent open-source desktop
editor for Angry Miao keyboard profiles.

The main pieces:

- keyboard-shaped Keymap editing;
- macro recording, event editing, import, and text-to-keystrokes;
- one Lighting Studio for per-LED painting, GIF/PNG/BMP import, pan/zoom/stretch,
  and local animation effects;
- a mixed Library for media, lighting, and compatible keyboard profiles;
- optional local Ollama or remote API generation, completely hidden when AI is
  switched off; and
- native macOS arm64, Windows x64, and Linux x86-64 packages with SHA-256
  checksums and free GitHub build attestations.

### Testing disclosure

The USB read/write path was **live-tested on one AM Neon 80** connected to
macOS. Keymaps and macros have transport verification after a complete write.
Neon firmware does not expose LED read-back, so lighting verification is visual.
The CyberBoard, Relic 80, and AFA/AFA 2 adapters have automated and fixture
coverage but were not tested on physical examples for this release.

Windows and Linux installers receive automated native smoke tests in their own
GitHub-hosted operating systems. They are not manually qualified on Windows or
Linux by me for this release.

Remote API adapters are experimental and are not live-qualified with paid
credentials. Local/manual Lighting does not require AI.

### Before writing

A complete write replaces keymaps, macros, and LEDs together. Save a portable
JSON or keep the original lighting source first. Neon also needs its physical
**Esc+F2** unlock, and **AM Master**, Vial, VIA, or another configurator must be
closed so it is not holding the HID interface.

The installers do not have paid Apple or Microsoft publisher signatures, so
macOS or Windows may request per-application approval on first launch. The
installation guide gives the narrow approval steps and hash/provenance checks;
it does not ask anyone to disable system security.

Download:
https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.64

Release notes:
https://github.com/roethlar/AMKB-GUI/blob/main/docs/releases/0.1.64.md

Bug reports:
https://github.com/roethlar/AMKB-GUI/issues/new/choose

AM Configurator is an independent community project and is not affiliated with
or endorsed by Angry Miao.
