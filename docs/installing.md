# Installing AM Configurator

Download AM Configurator only from the
[GitHub Releases page](https://github.com/roethlar/AMKB-GUI/releases). A normal
release contains these five files:

- `AM-Configurator-0.1.68-macOS-arm64.dmg`
- `AM-Configurator-0.1.68-Windows-x64-Setup.exe`
- `AM-Configurator-0.1.68-Linux-x86_64.AppImage`
- `SHA256SUMS.txt`
- `release-manifest.json`

GitHub Actions artifacts are temporary maintainer candidates, not public
installer downloads.

## Verify the download

### SHA-256

Download `SHA256SUMS.txt` beside the installer and compare the listed digest.
On macOS or Linux:

```sh
shasum -a 256 AM-Configurator-0.1.68-macOS-arm64.dmg
```

Use the corresponding AppImage filename on Linux. On Windows PowerShell:

```powershell
Get-FileHash .\AM-Configurator-0.1.68-Windows-x64-Setup.exe -Algorithm SHA256
```

The resulting 64-character value must exactly match the row for that filename
in `SHA256SUMS.txt`. A mismatch means the bytes are not the published release;
do not open the file.

### Publisher signature

The macOS and Windows downloads are signed, and you can check that on the file
you just downloaded. On macOS, the disk image carries an Apple notarization
ticket and its own Developer ID signature:

```sh
xcrun stapler validate AM-Configurator-0.1.68-macOS-arm64.dmg
spctl --assess --type open --context context:primary-signature --verbose=4 AM-Configurator-0.1.68-macOS-arm64.dmg
```

After installing, the application itself reports the same publisher:

```sh
codesign -dv --verbose=4 "/Applications/AM Configurator.app"
```

On Windows PowerShell, the installer's signature status must be `Valid` and it
must carry a timestamp countersignature:

```powershell
Get-AuthenticodeSignature .\AM-Configurator-0.1.68-Windows-x64-Setup.exe | Format-List
```

The Linux AppImage is not signed. Its check is the SHA-256 digest.

### GitHub build provenance

Candidate builds published from `main` carry keyless attestations from the
repository's GitHub Actions workflow. With the GitHub CLI installed:

```text
gh attestation verify <downloaded-file> --repo roethlar/AMKB-GUI
```

A matching attestation binds those bytes to this repository, commit, and build
workflow. It detects substitution and establishes workflow provenance; it does
not replace platform code signing or suppress operating-system first-launch
checks.

Release downloads are different files: they are built and published by the
signed release workflow, which creates no attestation, so that command reports
no matching attestation for them. Verify a release download by its SHA-256
digest and its publisher signature.

## What the signatures cover

- The macOS application is signed with an Apple Developer ID Application
  certificate, and the disk image that carries it is signed and notarized by
  Apple with the notarization ticket stapled to it.
- The Windows application executable and the installer are signed through Azure
  Trusted Signing, each with a timestamp countersignature. Bundled runtime DLL
  and `.pyd` files inside the package are not separately signed.
- Microsoft Defender SmartScreen also weighs how widely a signing certificate
  has been seen, which is separate from whether the signature is valid. This
  certificate is newly in use, so SmartScreen may still show a caution prompt
  for a while.
- The Linux AppImage is unsigned. Linux has no publisher-signing equivalent to
  Developer ID or Authenticode.

Approve only the one application you verified; never turn off an operating
system's security checks globally.

## macOS arm64

1. Verify the DMG digest and signature.
2. Open the DMG and drag **AM Configurator** to **Applications**.
3. Launch **AM Configurator** from **Applications**. Because the application is
   notarized, macOS opens it without the Privacy & Security approval step older
   unsigned releases needed; it may still ask the ordinary confirmation that the
   file was downloaded from the internet.

Do not use commands that remove quarantine metadata or turn off Gatekeeper.

## Windows 11 x64

1. Verify the installer with `Get-FileHash` and `Get-AuthenticodeSignature`.
2. Open `AM-Configurator-0.1.68-Windows-x64-Setup.exe`.
3. If Microsoft Defender SmartScreen appears, choose **More info** and then
   **Run anyway** only after the displayed filename, publisher, and digest all
   match the release you verified.
4. Complete the per-user installation and launch **AM Configurator**.

Do not turn off SmartScreen, Microsoft Defender, or antivirus protection.

## Linux x86-64

1. Verify the AppImage digest.
2. If the browser removed its executable bit, restore it:

   ```sh
   chmod +x AM-Configurator-0.1.68-Linux-x86_64.AppImage
   ```

3. Launch it normally:

   ```sh
   ./AM-Configurator-0.1.68-Linux-x86_64.AppImage
   ```

4. For AM Neon 80 access, install the shipped udev rule by following
   [AM Neon 80 on Linux](neon-80-linux.md).
