# Offline Delivery Checklist

DBLift is delivered to customers as standalone, per-operating-system release
packages built by `.github/workflows/build.yaml`.

## Release Artifacts

Every release should include these assets when the matching platform is supported:

- `dblift-<version>-linux-x86_64.tar.gz`
- `dblift-<version>-linux-x86_64-executable.tar.gz`
- `dblift-<version>-win32-x86_64.zip`
- `dblift-<version>-win32-x86_64-executable.zip`
- `dblift-<version>-darwin-arm64.tar.gz`
- `dblift-<version>-darwin-arm64-executable.tar.gz`
- `SHA256SUMS.txt`

Each archive contains `DISTRIBUTION-MANIFEST.json`. The manifest records the
DBLift version, target platform, architecture, build Python version, source
commit when built by GitHub Actions, and per-file SHA-256 checksums.

## Verification Before Delivery

Before sending an offline package to a customer:

1. Confirm the GitHub Release was produced by `.github/workflows/build.yaml`.
2. Download the target operating-system archive and `SHA256SUMS.txt`.
3. Verify the archive checksum:

   ```bash
   shasum -a 256 -c SHA256SUMS.txt
   ```

4. Extract the archive and inspect `DISTRIBUTION-MANIFEST.json`.
5. Confirm `README.md`, `LICENSE`, launcher files, `api`, `cli`, `config`,
   `core`, and `db` are present.
6. Run the package smoke test:

   ```bash
   ./dblift --version
   ```

   On Windows, use `dblift.bat` or `Dblift.exe` depending on the selected asset.

## Evidence To Retain

Retain these records with the release:

- GitHub Actions run URL for `Build Distribution Packages`.
- `SHA256SUMS.txt`.
- The extracted `DISTRIBUTION-MANIFEST.json` for each delivered archive.
- Release notes from `CHANGELOG.md`.
- License-token delivery record.

## Customer Installation Guidance

DBLift does not require a customer-side Python installation when using the
standalone executable assets. For archive assets that use the bundled launcher,
extract the package, keep the directory structure intact, and run the launcher
from the package root.

Do not edit bundled source files in place. Use a new DBLift release for product
updates, and keep customer migrations/configuration outside the extracted
application directory.
