# Bundled FFmpeg 8.1.2

AM Configurator native distributions prepare a constrained, network-disabled
FFmpeg 8.1.2 executable from the official release source. The executable
remains a separate program and is built with LGPL-only settings: the recipe
explicitly disables GPL, nonfree, and version-3-only code.

## Pinned source and signature

- Source: https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz
- Detached signature: https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz.asc
- Source SHA-256: `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`
- FFmpeg release-key fingerprint: `FCF986EA15E6E293A5644F10B4322F04D67658D8`

The source hash and release-key fingerprint were verified once when this recipe
was recorded. `ffmpeg-devel.asc` is the pinned public key used for release
verification. `build_tools/ffmpeg_bundle.py` rechecks the source hash and the
detached signature with an isolated GnuPG home; it disables automatic key
retrieval and never downloads anything.

## Reproducing the native executable

`manifest.json` is the canonical recipe. The build helper verifies the signed
source, safely extracts that archive into a fresh private directory, enables the
required codecs, containers, protocol, and filters, sets
`SOURCE_DATE_EPOCH=1781664417`, applies the manifest-owned build-path prefix maps,
and emits an `ffmpeg-runtime.json` attestation beside the executable. The cache
recipe hash covers the complete configure, compiler/linker, tool-role, target,
and make recipe. FFmpeg may enable the internal dependency closure needed by
the requested capabilities; the helper does not claim that the capability
listing is exhaustive. Built outputs belong in the ignored `build/ffmpeg/`
cache and are not committed.

Supported toolchains are Xcode Command Line Tools on macOS, Ubuntu build tools
plus zlib on Linux x86-64, and MSYS2 MinGW64 on Windows x86-64. See the approved
Lighting Studio implementation plan for the prerequisite package names.

The macOS arm64 helper invocation shape is:

```sh
uv run --frozen python -m build_tools.ffmpeg_bundle build \
  --archive build/ffmpeg/sources/ffmpeg-8.1.2.tar.xz \
  --signature build/ffmpeg/sources/ffmpeg-8.1.2.tar.xz.asc \
  --extract-dir /private/tmp/am-configurator-ffmpeg-8.1.2 \
  --output-dir build/ffmpeg/ffmpeg-8.1.2-macos-arm64-464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c-ca1c02899491f88d4869fedf790b4c1fb99c95641292f46d24d5c626311d6504 \
  --platform macos --architecture arm64 --jobs N \
  --cc /usr/bin/cc --ar /usr/bin/ar --ranlib /usr/bin/ranlib --strip /usr/bin/strip
```

Native builds normally run the current-host wrapper after staging the archive
and signature under `build/ffmpeg/sources/`:

```sh
uv run --frozen python -m build_tools.prepare_ffmpeg
```

The wrapper verifies and reuses a matching attested cache entry. On a cache
miss it imports only the committed release key into a temporary GnuPG home,
verifies the staged files, builds the constrained executable, and writes the
attestation expected by the application bundle.

`--extract-dir` must not exist, must contain no whitespace, and must live outside
the repository workspace.
The helper verifies the archive hash and detached signature, rejects unsafe tar
members, extracts the verified source itself, and removes the extraction after
the build attempt. There is no option to compile a caller-supplied source tree.
Configure uses the constant non-workspace prefix
`/usr/local/am-configurator-ffmpeg`; the helper runs `make -jN ffmpeg` and then
copies only that executable into the prepared cache before inspection.

## LGPL source/build offer

`LGPL-2.1.txt` contains the applicable license. Each native distribution ships
this directory, including the exact manifest and build instructions. The
official source and detached signature above are the complete corresponding
FFmpeg source used by the recipe. As a written offer, for at least three years
after a native distribution is provided, the AM Configurator maintainers will
also provide the same corresponding source and build recipe on request, for no
more than the reasonable cost of physical transfer.
