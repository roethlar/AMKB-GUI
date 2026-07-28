# Installing AM Configurator

Download AM Configurator only from the
[GitHub Releases page](https://github.com/roethlar/AMKB-GUI/releases). A normal
release contains these five files:

- `AM-Configurator-0.1.64-macOS-arm64.dmg`
- `AM-Configurator-0.1.64-Windows-x64-Setup.exe`
- `AM-Configurator-0.1.64-Linux-x86_64.AppImage`
- `SHA256SUMS.txt`
- `release-manifest.json`

GitHub Actions artifacts are temporary maintainer candidates, not public
installer downloads.

## Verify the download

### SHA-256

Download `SHA256SUMS.txt` beside the installer and compare the listed digest.
On macOS or Linux:

```sh
shasum -a 256 AM-Configurator-0.1.64-macOS-arm64.dmg
```

Use the corresponding AppImage filename on Linux. On Windows PowerShell:

```powershell
Get-FileHash .\AM-Configurator-0.1.64-Windows-x64-Setup.exe -Algorithm SHA256
```

The resulting 64-character value must exactly match the row for that filename
in `SHA256SUMS.txt`. A mismatch means the bytes are not the published release;
do not open the file.

### GitHub build provenance

Public release files also have keyless attestations from the repository's
GitHub Actions workflow. With the GitHub CLI installed:

```text
gh attestation verify <downloaded-file> --repo roethlar/AMKB-GUI
```

Run that command for the installer you downloaded and, if desired,
`SHA256SUMS.txt` or `release-manifest.json`. A matching attestation binds those
bytes to this repository, commit, and build workflow. It detects substitution
and establishes workflow provenance; it does not replace platform code signing
or suppress operating-system first-launch checks. If GitHub reports no matching
attestation, the file is unattested and should not be assumed to come from the
release workflow.

## What the platform warnings mean

- The macOS app bundle has an ad-hoc signature for bundle-integrity checks. It
  has no Apple Developer ID signature and no notarization ticket.
- The Windows installer has no Authenticode publisher signature or SmartScreen
  reputation.
- SHA-256 proves that a file matches the published digest. GitHub attestation
  additionally ties that digest to this repository's workflow. Neither gives
  the package a platform-trusted publisher identity.

These are expected properties of the published packages. Approve only the one
verified application; never turn off an operating system's security checks
globally.

## macOS arm64

1. Verify the DMG hash and GitHub attestation.
2. Open the DMG and drag **AM Configurator** to **Applications**.
3. Attempt to open **AM Configurator** once. macOS may block that first attempt
   because the app is not notarized.
4. Open **System Settings → Privacy & Security**, find the message for **AM
   Configurator**, and choose **Open Anyway**.
5. Confirm the per-application prompt, then launch it from **Applications**.

Do not use commands that remove quarantine metadata or turn off Gatekeeper.

## Windows 11 x64

1. Verify the installer with `Get-FileHash` and GitHub attestation.
2. Open `AM-Configurator-0.1.64-Windows-x64-Setup.exe`.
3. If Microsoft Defender SmartScreen appears, choose **More info** and then
   **Run anyway** only after the displayed filename, hash, and repository all
   match the release you verified.
4. Complete the per-user installation and launch **AM Configurator**.

Do not turn off SmartScreen, Microsoft Defender, or antivirus protection.

## Linux x86-64

1. Verify the AppImage hash and GitHub attestation.
2. If the browser removed its executable bit, restore it:

   ```sh
   chmod +x AM-Configurator-0.1.64-Linux-x86_64.AppImage
   ```

3. Launch it normally:

   ```sh
   ./AM-Configurator-0.1.64-Linux-x86_64.AppImage
   ```

4. For AM Neon 80 access, install the shipped udev rule by following
   [AM Neon 80 on Linux](neon-80-linux.md).
