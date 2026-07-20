# AM Configurator

AM Configurator is a standalone, local desktop app for configuring Angry Miao
keyboards without AM Master or Angry Miao's web app. It edits the same JSON
profile format and talks directly to the keyboard over USB serial.

The app manages:

- physical keymaps with seven layers, a QWERTY assignment palette, macros, and
  Angry Miao-specific controls;
- macros as editable key-down/key-up events, recorded input, imported macro
  definitions, or deterministic text converted to keystrokes;
- model-specific LED animation slots, painting, playback, GIF import,
  brightness, and firmware-supported frame timing;
- guarded full-device writes with model matching, typed confirmation, keymap
  and macro read-back, and a local snapshot after verification.

## Supported keyboards

The app recognizes these firmware identities:

| Keyboard family | USB identity | LED editor |
|---|---|---|
| CyberBoard | `CB…` | sparse per-key layout and 40×5 display |
| AM Relic 80 | `AM21` / JSON `80` | physical per-key layout and seven edge LEDs |
| AM AFA / AFA 2 | `ALICE` | physical Alice key/body-light layout |

Relic 80 identity, keymap reads, and macro reads have been exercised on real
hardware. Keep an official JSON backup when testing another model or firmware
revision.

## Run from source

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required for the
development commands:

```sh
uv sync --extra desktop
uv run --extra desktop am-configurator
```

You can open one or more existing official exports at launch. Relic key and LED
exports are often separate, so pass both and the app will merge them:

```sh
uv run --extra desktop am-configurator AM-80Relic.json AM-80Relic-KEY.json
```

The interface runs in a native window backed by a token-authenticated loopback
server. It has no cloud backend, account, or dependency on the reference
`cyberboard-cli` repository.

## Normal workflow

1. Connect a keyboard by USB and open **Devices**.
2. Select it and choose **Read keymap & macros**, or open its full JSON profile.
3. Edit keymaps, macros, and LED slots.
4. Save a portable JSON backup.
5. Use the always-visible **Write to keyboard** button and type the displayed
   device ID to confirm the full write.

Device selection never writes by itself. A write replaces the complete device
configuration, including LEDs, keymaps, and macros.

### LED state and multiple computers

The firmware protocol exposes keymap and macro reads but does not expose LED
frame reads. After a verified write, AM Configurator stores the full profile on
that computer so later macro or keymap edits can retain the known LED data.
That local record does not follow the keyboard to another computer: use **Save
JSON** and open that portable profile on the other machine.

Relic edge lights remain a separate editable track. A per-key GIF can also
derive the edge track, or preserve a separate edge animation. **Static color**,
**Pulse color**, and **Hold painted frame** generate all required edge frames
automatically to match the key animation; there is no need to paint hundreds
of identical frames manually.

GIF frames are resized through the selected model's physical-to-firmware LED
map. Variable GIF delays are resampled onto one of the 16 timing steps supported
by the keyboard firmware, and animations are capped at 256 frames.

### Macros

The device limit is 32 macro definitions and 200 key events total across the
profile. The text composer accepts the US keyboard layout's letters, numbers,
punctuation, spaces, Tab, and Enter, adds Shift automatically, and uses a fixed
inter-key delay instead of recorded pauses.

## Build standalone apps

PyInstaller must run on the target operating system; it is not a
cross-compiler. First build the native application on macOS, Windows, or Linux:

```sh
uv sync --locked --extra desktop --extra build
uv run --frozen --extra desktop --extra build pyinstaller --noconfirm --clean packaging/am_configurator.spec
```

Then package the platform-native installer:

```sh
# macOS: versioned DMG, mounted and smoke-tested automatically
packaging/macos/build_dmg.sh

# Linux: versioned AppImage, executed in extract mode for its smoke test
packaging/linux/build_appimage.sh

# Windows PowerShell: versioned per-user Inno Setup installer
./packaging/windows/build_installer.ps1
```

The result is written to `dist/` as a macOS `.dmg`, Windows `Setup.exe`, or
Linux `.AppImage`. Artifact filenames include the version and architecture. The
`Desktop installers` GitHub Actions workflow builds and executes the installed
artifact on each operating system before uploading it.

The installers are currently unsigned. macOS Gatekeeper and Windows SmartScreen
may therefore warn until release signing is configured.

Local macOS smoke test:

```sh
"dist/AM Configurator.app/Contents/MacOS/AM Configurator" --smoke-test
```

## Development verification

```sh
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q am_configurator packaging build_tools
node --check am_configurator/web/app.js
uv build
```

The protocol implementation was derived from the MIT-licensed
`GeneralD/cyberboard-cli` project; see `THIRD_PARTY_NOTICES`. AM Configurator is
not affiliated with or endorsed by Angry Miao.
