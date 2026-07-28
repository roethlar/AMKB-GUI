# Installing AM Configurator

## Verify GitHub build provenance

Public release files have keyless build attestations from the repository's
GitHub Actions workflow. With the GitHub CLI installed, verify any downloaded
release file before opening it:

```text
gh attestation verify <downloaded-file> --repo roethlar/AMKB-GUI
```

An attestation binds the downloaded bytes to this repository and its build
workflow. It detects substitution and establishes workflow provenance; it does
not replace platform code signing or suppress operating-system first-launch
checks.
