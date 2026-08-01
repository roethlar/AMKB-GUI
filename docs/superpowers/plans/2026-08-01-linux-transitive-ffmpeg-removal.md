# Linux Transitive FFmpeg Removal

**Status:** Approved by the owner on 2026-08-01. Initial implementation slice
LXF-1 landed at `aea6b254ea1610ba9cd9d6b937d792ec802ab09b`; Linux qualification
reopened it after the custom dynamic-GI hooks did not execute. The owner then
clarified that incidental FFmpeg-name references in a required non-FFmpeg
library are permitted, while every actual FFmpeg/libav implementation,
library, package, plugin, and path remains prohibited. The corrective commit
must be new; do not rewrite the initial landing.

## Objective

Remove every transitively bundled FFmpeg implementation from the Linux native
application while preserving the Linux x86-64 AppImage, the native desktop
window, the existing application behavior, and the unconditional product
contract in `.agents/decisions.md`.

Completion requires both dependency-level and byte-level proof. A package name
or source-tree scan is insufficient: the produced AppImage must be extracted
and its regular-file paths and bytes audited.

## Authority and release consequence

- `.agents/decisions.md` unconditionally prohibits FFmpeg in runtime, build,
  test, CI, packaging, recovery, and optional dependency paths.
- `docs/superpowers/plans/2026-07-30-ffmpeg-removal-and-dependency-audit.md`
  owns the app-owned removal and now records that its native-artifact proof is
  reopened.
- `docs/superpowers/plans/2026-07-31-public-release-0.1.65.md` records rejected
  candidate attempt 1 and requires a completely new candidate after any fix.
- `0.1.65` remains unchanged because no `0.1.65` tag or Release exists.
- No release, provider, security-setting, Open Anyway, or hardware-write gate
  is part of this correction.

## Reproduced defect

Candidate attempt 1 froze
`2685a9832e0982d8b52ea45a4becd8a75eb48d01`. Exact Desktop run
`30683516302` attempt 1 produced the rejected Linux AppImage. Extraction found:

- `libQt6WebEngineCore.so.6` with `FFmpegAudioDecoder`, `FFmpegDemuxer`,
  Chromium FFmpeg source paths, and related implementation strings; and
- `libQt6Multimedia.so.6` with FFmpeg hardware-pixel-format and dynamic-stub
  symbols.

The dependency chain is:

```text
pyproject desktop extra
  -> pywebview[qt]
    -> PyQt6-WebEngine / PyQt6
      -> Qt WebEngine / Qt Multimedia native libraries
        -> bundled FFmpeg implementation code
```

The existing guards reject named FFmpeg packages and app-owned source paths,
but they do not inspect third-party native-library bytes. The previous
cross-platform proof therefore did not exercise the failure mode.

Post-landing qualification found two additional gaps. PyInstaller requires
pre-safe-import registration for dynamic WebKit2, Soup, and JavaScriptCore GI
namespaces; without it, the hook files exist but do not execute. Once those
namespaces were collected, stock WebKitGTK directly required
`libgstpbutils-1.0.so.0`. That non-FFmpeg library contains three incidental
FFmpeg-name references and no libav marker. The owner-approved clarification
requires structural implementation detection instead of treating the name
alone in arbitrary binary content as prohibited code.

## Qualified replacement

PyWebView 6.2.1 supports a GTK 3 / WebKit2 backend without Qt. A dependency-only
probe on `gabrielle` passed with:

- CPython 3.12.13;
- `pywebview[gtk]==6.2.1`, including its pinned PyGObject 3.50.0 dependency;
- GTK 3.24.52, WebKitGTK 2.52.5, and Soup 3.6.6;
- renderer identity `gtkwebkit2`; and
- PyInstaller `get_gi_typelibs` resolution for Gtk 3.0, WebKit2 4.1, and Soup
  3.0.

WebKitGTK is the Linux native-window responsibility. Generic web-engine media
capability is not a product AI-video path; the artifact must nevertheless
contain no FFmpeg implementation, FFmpeg/libav library, retired app video
adapter, or retired fixture.

## Scope

Expected implementation surfaces:

- `pyproject.toml` and `uv.lock`;
- `am_configurator/desktop.py`;
- `packaging/am_configurator.spec` and new repository-owned PyInstaller GI
  hooks under `packaging/hooks/`;
- `build_tools/` for the native-tree audit;
- `build.py`, `packaging/linux/build_appimage.sh`, and
  `.github/workflows/desktop.yml`;
- dependency, desktop, and packaging tests; and
- completion records only after implementation and qualification pass.

Out of scope:

- changing macOS Cocoa/WKWebView or Windows Edge WebView2;
- replacing PyWebView as the application window abstraction;
- removing the Linux release or changing its architecture/name without a new
  owner decision;
- any AI/provider behavior, device protocol, UI feature, or application
  version change; and
- release publication or any separately gated action.

## Implementation slice LXF-1 — Replace Qt and close the artifact gap

Land this as one atomic implementation finding. A partial commit that wires the
new audit while the known-bad Qt bundle is still produced would intentionally
leave Desktop CI red and must not land on `main`.

### 1. Replace the Linux backend dependency

In `pyproject.toml`, replace the Linux-only `pywebview[qt]` requirement with
`pywebview[gtk]` at the same supported PyWebView floor. Regenerate `uv.lock`
normally; do not hand-edit it.

Require the locked Linux desktop graph to contain the GTK binding chain and to
exclude at least:

- `PyQt6`;
- `PyQt6-Qt6`;
- `PyQt6-WebEngine`;
- `PyQt6-WebEngine-Qt6`; and
- `QtPy`.

Keep the dependency-owner model unchanged: `pywebview` owns the desktop extra;
PyGObject and pycairo are its Linux backend closure, not speculative direct
dependencies.

### 2. Pin the production renderer policy

Change the Linux entry in `_NATIVE_WEBVIEW_POLICIES` to:

```python
("webview.platforms.gtk", "gtk", "gtkwebkit2")
```

Keep Darwin on Cocoa/WKWebView and Windows on WinForms/Edge Chromium. Update
the existing native-policy tests so GTK is not a fallback: the exact backend,
forced GUI choice, and observed renderer must all be asserted.

### 3. Freeze the GI namespaces deliberately

In `packaging/am_configurator.spec`:

- replace the Linux hidden import `webview.platforms.qt` with
  `webview.platforms.gtk`;
- explicitly include the GI namespaces used by PyWebView's GTK backend;
- add a repository hook directory to `hookspath`; and
- add focused hooks using `PyInstaller.utils.hooks.gi.get_gi_typelibs` for
  WebKit2 4.1 and Soup 3.0. Use PyInstaller's existing Gtk/Gdk/Gio/GLib hooks
  rather than copying them.

Do not add Qt as a fallback hidden import. A frozen application that cannot
load GTK/WebKitGTK must fail the native-policy smoke instead of silently
loading another renderer.

### 4. Replace Linux CI prerequisites

Remove the Qt/XCB/XKB prerequisite list from the Linux installer job. Install
the Ubuntu packages needed to build PyGObject/pycairo and run GTK 3/WebKit2 4.1
under Xvfb, including:

- `gcc` and `pkg-config`;
- `libcairo2-dev` and `libgirepository1.0-dev` (the latter supplies the
  `gobject-introspection-1.0` build contract required by pinned PyGObject
  3.50.0 on Ubuntu 24.04);
- `gir1.2-gtk-3.0`;
- `gir1.2-webkit2-4.1` and `libwebkit2gtk-4.1-dev`;
- `xauth`; and
- `xvfb`.

Keep dependency synchronization locked. Do not install a Qt package, GStreamer
libav plugin, FFmpeg package, or general multimedia bundle. The focused
packaging test must pin the required set and reject the retired Qt prerequisite
set.

### 5. Add a streaming native-tree audit

Add a standard-library-only `build_tools` CLI that recursively audits a supplied
native tree without following symlinks. It must stream regular-file bytes with
marker-length overlap so a marker split across chunks is still detected.

Reject case-insensitive path hits for the retired FFmpeg name and GStreamer
libav plugin, and reject content hits for:

- embedded FFmpeg decoder, demuxer, and source fingerprints (construct source
  literals in split pieces so the audit does not match itself);
- `libavcodec`, `libavformat`, `libavutil`, `libswscale`, and `libswresample`;
- retired app adapters such as `process_video_frames`; and
- the retired MP4 fixture name.

An incidental FFmpeg-name reference inside a required non-FFmpeg library is
not a finding by itself. Do not implement this as a filename allowlist: the
same path and implementation checks apply uniformly to every file.

Also reject any PyQt6/Qt WebEngine/Qt Multimedia path in the Linux bundle. Do
not use generic PEM header strings as a credential heuristic: third-party TLS
libraries contain embedded test vectors, which candidate attempt 1 proved
would create false positives. Existing release checks continue to inspect for
actual project-local paths, credentials, profiles, and firmware data.

The audit output must identify only safe relative paths and marker categories,
never dump matched binary content.

Run the audit:

1. after PyInstaller and before platform packaging on every OS, so local
   `build.py` and the Desktop workflow have the same guard; and
2. on the extracted final Linux AppImage in
   `packaging/linux/build_appimage.sh` before its smoke test succeeds.

The AppImage extraction directory must be created with `mktemp`, verified as
the owned cleanup target, and removed by the existing shell end-to-end.

### 6. Add non-vacuous guards

Add tests that require:

- the GTK dependency and absence of the Qt lock closure;
- the exact Linux production renderer policy;
- GTK hidden imports and repository GI hooks with no Qt fallback;
- the GTK/WebKit CI prerequisite contract and absence of Qt/libav packages;
- native audit invocation in local and CI packaging paths;
- clean synthetic trees to pass;
- marker hits in filenames, file contents, mixed case, and across a chunk
  boundary to fail; and
- symlink targets not to be traversed.

Use split literals in tests where the existing source-level retired-tool guard
requires it.

## Verification

### Red proof

Before accepting the correction, run the new native-tree audit against the
preserved rejected Linux preflight output for `2685a98` on `gabrielle`. It must
fail on the Qt WebEngine/Multimedia files named in this plan. Preserve only the
sanitized relative paths and marker categories.

For every new unit guard, temporarily restore the pre-change dependency,
policy, spec, workflow, or audit behavior as applicable and prove the focused
test fails. Restore the correction and prove it passes. Do not rewrite existing
commits to capture this proof.

### Automated gate

Run the canonical repository verification from `.agents/repo-guidance.md` in a
CI-shaped no-extra environment. Then prepare the desktop/build environment and
run the current-platform Windows native build/smoke to prove the unaffected
backend still packages.

### Linux native proof

On a fresh exact commit on `gabrielle`:

1. resolve the locked Python 3.12 GTK desktop/build graph;
2. build the PyInstaller tree and AppImage;
3. require the frozen smoke and `--print-udev-rule` checks;
4. extract the AppImage and run the new audit;
5. require GTK/WebKit notices/licenses and the existing project/upstream
   notices and udev rule;
6. require zero Qt or actual FFmpeg/libav implementation, library, plugin, or
   path hits under the clarified structural audit; and
7. record that no physical keyboard test occurred.

Require the exact implementation push's CI and Desktop workflows to pass on
all maintained platforms. Download the exact Linux artifact, match its
manifest, hash, and attestation, extract it independently, and rerun the audit.
Do not rely only on the workflow step that produced it.

## Commit and release sequence

1. Commit the LXF-1 qualification correction only after the focused red/green
   proof, canonical local gate, and Linux native proof pass. Use a new commit;
   never amend or rewrite `aea6b25`.
2. Push normally to canonical `origin`; no tag or Release.
3. Qualify the exact implementation push's CI/Desktop Linux artifact as above.
4. Commit sanitized completion/state records only after qualification passes.
5. Restart public-release Slice R65-2 on the resulting clean remote `main` and
   freeze a new candidate SHA. Candidate attempt 1 must never be reused.

## Failure policy

- If GTK/WebKitGTK cannot produce a functional frozen AppImage without an
  actual bundled FFmpeg/libav implementation, library, plugin, or Qt, stop. Do
  not add a binary allowlist or relabel a dependency.
- If keeping Linux would require an FFmpeg-bearing browser engine, request a
  new owner decision to remove Linux from the release; do not change the
  three-platform contract silently.
- A failing native-policy smoke, missing notice/license, unavailable udev rule,
  unexpected system dependency, or artifact mismatch blocks the correction.
- Any source correction after a new candidate is frozen rejects that candidate
  and restarts R65-2 again.
