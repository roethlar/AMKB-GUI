"""Guards for package-manager stub generation (AUR first)."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from build_tools.package_managers import (
    AUR_PACKAGE_NAME,
    PackageManagerError,
    digests_from_manifest,
    digests_from_sums,
    generate_aur_package,
    linux_appimage_filename,
    release_download_url,
    render_pkgbuild,
    render_srcinfo,
    require_digest,
    validate_version,
)
from build_tools.package_managers.aur import build_inputs
from build_tools.package_managers.__main__ import main as package_managers_main
from build_tools.release_info import PROJECT_ROOT


FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "package_managers"
GOLDEN_AUR = FIXTURES / "aur"


class CommonHelpersTests(unittest.TestCase):
    def test_validate_version_accepts_canonical(self) -> None:
        self.assertEqual("0.1.68", validate_version("0.1.68"))

    def test_validate_version_rejects_non_canonical(self) -> None:
        for bad in ("1", "0.1", "v0.1.68", "0.1.68-1", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(PackageManagerError):
                    validate_version(bad)

    def test_linux_appimage_filename_matches_release_contract(self) -> None:
        self.assertEqual(
            "AM-Configurator-9.9.9-Linux-x86_64.AppImage",
            linux_appimage_filename("9.9.9"),
        )

    def test_release_download_url_default_and_template(self) -> None:
        self.assertEqual(
            "https://github.com/roethlar/AMKB-GUI/releases/download/v9.9.9/"
            "AM-Configurator-9.9.9-Linux-x86_64.AppImage",
            release_download_url(
                "9.9.9",
                "AM-Configurator-9.9.9-Linux-x86_64.AppImage",
            ),
        )
        self.assertEqual(
            "https://example.test/v9.9.9/AM-Configurator-9.9.9-Linux-x86_64.AppImage",
            release_download_url(
                "9.9.9",
                "AM-Configurator-9.9.9-Linux-x86_64.AppImage",
                asset_base="https://example.test/v{version}",
            ),
        )

    def test_digests_from_sums_and_require(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "SHA256SUMS.txt"
            path.write_text(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  "
                "AM-Configurator-9.9.9-Linux-x86_64.AppImage\n"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  "
                "AM-Configurator-9.9.9-macOS-arm64.dmg\n",
                encoding="utf-8",
            )
            digests = digests_from_sums(path)
            self.assertEqual(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                require_digest(
                    digests,
                    "AM-Configurator-9.9.9-Linux-x86_64.AppImage",
                ),
            )
            with self.assertRaises(PackageManagerError):
                require_digest(digests, "missing.bin")

    def test_digests_from_sums_rejects_bad_rows(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "SHA256SUMS.txt"
            path.write_text("not-a-digest  file\n", encoding="utf-8")
            with self.assertRaises(PackageManagerError):
                digests_from_sums(path)

    def test_digests_from_manifest(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "release-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "app_version": "9.9.9",
                        "artifacts": [
                            {
                                "filename": (
                                    "AM-Configurator-9.9.9-Linux-x86_64.AppImage"
                                ),
                                "sha256": "a" * 64,
                                "platform": "linux",
                                "architecture": "x86_64",
                                "byte_size": 1,
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            version, digests = digests_from_manifest(path)
            self.assertEqual("9.9.9", version)
            self.assertEqual(
                "a" * 64,
                digests["AM-Configurator-9.9.9-Linux-x86_64.AppImage"],
            )


class AurGeneratorTests(unittest.TestCase):
    VERSION = "9.9.9"
    APPIMAGE = "AM-Configurator-9.9.9-Linux-x86_64.AppImage"
    APPIMAGE_SHA256 = "a" * 64

    def _digests(self) -> dict[str, str]:
        return {self.APPIMAGE: self.APPIMAGE_SHA256}

    def test_pkgbuild_and_srcinfo_match_goldens(self) -> None:
        inputs = build_inputs(
            version=self.VERSION,
            digests=self._digests(),
            repo_root=PROJECT_ROOT,
        )
        pkgbuild = render_pkgbuild(inputs)
        srcinfo = render_srcinfo(inputs)

        golden_pkgbuild = (GOLDEN_AUR / "PKGBUILD").read_text(encoding="utf-8")
        golden_srcinfo = (GOLDEN_AUR / "SRCINFO").read_text(encoding="utf-8")
        self.assertEqual(golden_pkgbuild, pkgbuild)
        self.assertEqual(golden_srcinfo, srcinfo)

        self.assertIn(f"pkgname={AUR_PACKAGE_NAME}", pkgbuild)
        self.assertIn(f"pkgver={self.VERSION}", pkgbuild)
        self.assertIn("depends=()", pkgbuild)
        self.assertNotIn("fuse2", pkgbuild)
        self.assertNotIn("fuse3", pkgbuild)
        self.assertIn(self.APPIMAGE_SHA256, pkgbuild)
        self.assertIn(
            f"https://github.com/roethlar/AMKB-GUI/releases/download/v{self.VERSION}/"
            f"{self.APPIMAGE}",
            pkgbuild,
        )
        self.assertIn("/usr/lib/udev/rules.d/60-am-neon-80.rules", pkgbuild)
        self.assertIn("/usr/share/applications/am-configurator.desktop", pkgbuild)
        self.assertIn("pkgbase = am-configurator-bin", srcinfo)

    def test_golden_digest_guard_fails_when_appimage_hash_changes(self) -> None:
        """Red-prove: a wrong AppImage digest must not match the golden PKGBUILD."""

        inputs = build_inputs(
            version=self.VERSION,
            digests={self.APPIMAGE: "b" * 64},
            repo_root=PROJECT_ROOT,
        )
        pkgbuild = render_pkgbuild(inputs)
        golden_pkgbuild = (GOLDEN_AUR / "PKGBUILD").read_text(encoding="utf-8")
        self.assertNotEqual(golden_pkgbuild, pkgbuild)
        self.assertIn("b" * 64, pkgbuild)

    def test_missing_linux_digest_is_rejected(self) -> None:
        with self.assertRaises(PackageManagerError):
            build_inputs(
                version=self.VERSION,
                digests={"other.bin": "c" * 64},
                repo_root=PROJECT_ROOT,
            )

    def test_generate_aur_package_writes_tree(self) -> None:
        with TemporaryDirectory() as temporary:
            out = Path(temporary) / "am-configurator-bin"
            generate_aur_package(
                version=self.VERSION,
                digests=self._digests(),
                repo_root=PROJECT_ROOT,
                output_dir=out,
            )
            self.assertTrue((out / "PKGBUILD").is_file())
            self.assertTrue((out / ".SRCINFO").is_file())
            self.assertTrue((out / "am-configurator.desktop").is_file())
            self.assertTrue((out / "am-configurator.png").is_file())
            self.assertTrue((out / "60-am-neon-80.rules").is_file())
            self.assertTrue((out / "am-configurator.sh").is_file())
            self.assertTrue((out / "am-configurator-bin.install").is_file())

            pkgbuild = (out / "PKGBUILD").read_text(encoding="utf-8")
            self.assertEqual(
                (GOLDEN_AUR / "PKGBUILD").read_text(encoding="utf-8"),
                pkgbuild,
            )
            self.assertEqual(
                (GOLDEN_AUR / "SRCINFO").read_text(encoding="utf-8"),
                (out / ".SRCINFO").read_text(encoding="utf-8"),
            )

            wrapper = (out / "am-configurator.sh").read_text(encoding="utf-8")
            self.assertTrue(wrapper.startswith("#!/bin/sh\n"))
            self.assertIn(self.APPIMAGE, wrapper)
            self.assertEqual(
                hashlib.sha256(wrapper.encode("utf-8")).hexdigest(),
                build_inputs(
                    version=self.VERSION,
                    digests=self._digests(),
                    repo_root=PROJECT_ROOT,
                ).wrapper_sha256,
            )

    def test_generate_refuses_unrelated_nonempty_output(self) -> None:
        with TemporaryDirectory() as temporary:
            out = Path(temporary) / "out"
            out.mkdir()
            (out / "secret.txt").write_text("nope\n", encoding="utf-8")
            with self.assertRaises(PackageManagerError):
                generate_aur_package(
                    version=self.VERSION,
                    digests=self._digests(),
                    repo_root=PROJECT_ROOT,
                    output_dir=out,
                )

    def test_cli_from_sums(self) -> None:
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            sums = workspace / "SHA256SUMS.txt"
            sums.write_text(
                f"{self.APPIMAGE_SHA256}  {self.APPIMAGE}\n",
                encoding="utf-8",
            )
            out = workspace / "pkg"
            code = package_managers_main(
                [
                    "aur",
                    "--version",
                    self.VERSION,
                    "--sums",
                    str(sums),
                    "--out",
                    str(out),
                    "--repo-root",
                    str(PROJECT_ROOT),
                ]
            )
            self.assertEqual(0, code)
            self.assertTrue((out / "PKGBUILD").is_file())

    def test_cli_rejects_version_mismatch_with_manifest(self) -> None:
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            manifest = workspace / "release-manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "app_version": "9.9.9",
                        "artifacts": [
                            {
                                "filename": self.APPIMAGE,
                                "sha256": self.APPIMAGE_SHA256,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code = package_managers_main(
                [
                    "aur",
                    "--version",
                    "0.1.0",
                    "--manifest",
                    str(manifest),
                    "--out",
                    str(workspace / "pkg"),
                ]
            )
            self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
