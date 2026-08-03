from __future__ import annotations

import html as html_entities
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
from build_tools.release_info import artifact_filename, project_version


README_PATH = ROOT / "README.md"
WEB = ROOT / "am_configurator" / "web"

# Slice P5 guards: README.md is the user's entry point, so its order, links,
# labels, and vocabulary are held to the same contract as the interface
# (docs/superpowers/plans/2026-07-29-product-experience-remediation.md →
# "README and Screenshots").

# The plan's README order. Item 1 is the one-sentence product purpose, which
# sits above the first heading and is asserted separately.
SECTION_ORDER = (
    "## Download the latest release",
    "## Supported keyboards and operating systems",
    "## Five-minute quick start",
    "## What it looks like",
    "## What you can do",
    "## Before you write to a keyboard",
    "## Verify your download",
    "## For developers",
)

CAPABILITY_ORDER = (
    "### Keymap",
    "### Macros",
    "### Lighting",
    "### Library",
    "### Optional AI",
)

GALLERY = (
    "docs/images/board-cyberboard.png",
    "docs/images/board-relic80.png",
    "docs/images/board-afa.png",
    "docs/images/board-neon80.png",
)
SCREENSHOTS = (
    "docs/images/keymap.png",
    "docs/images/lighting.png",
    "docs/images/macros.png",
)

# Actions the README tells a user to take. Each one must exist verbatim in the
# interface it describes; a renamed control has to reach this file before the
# instructions can drift away from the application.
ACTION_LABELS = (
    "Connect a keyboard",
    "Open a JSON profile",
    "Read keymap & macros",
    "Devices",
    "Merge",
    "Save JSON",
    "Settings",
    "Write to keyboard",
    "Write full configuration",
    "Advanced keycode",
    "Show technical labels",
    "Type text",
    "Record keys",
    "Edit individual events",
    "Paint",
    "Import media",
    "Effects",
    "Apply",
    "Save to Library",
    "Ollama",
    "Direct API",
)

# The same table tests/web/plain_language.test.js enforces on the interface,
# expressed for Python. One contract, two surfaces; keep them in step.
BANNED = (
    (r"\bbank(?:s|ed|ing)?\b", "bank/banked/banking → save/saved/saving to Library"),
    (r"\bdurable\b", "durable job → generation continues in the background"),
    (r"\bdeterministic\b", "deterministic → preview / plain description"),
    (r"procedural recipe", "procedural recipe → lighting effect"),
    (r"\bprocedural effect\b", "procedural effect → lighting effect"),
    (r"exact LED frames?", "exact LED frames → lighting frames"),
    (r"\bexact frames\b", "exact frames → lighting frames"),
    (r"exact-raster", "exact-raster → lighting"),
    (r"\braster\b", "raster dimensions → keyboard or display size"),
    (r"model identity", "model identity changed → the model was updated"),
    (r"identity changed", "model identity changed → the model was updated"),
    (r"catalog identity", "catalog identity → saved Library item"),
    (r"asset identity", "asset identity → saved Library item"),
)

_FENCED_BLOCK = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


def readme_prose() -> str:
    """README copy a user reads, without the developer command blocks.

    Shell transcripts are developer surfaces and may name modules precisely;
    everything else in the file is user-facing copy.
    """

    return _FENCED_BLOCK.sub("", readme_text())


def interface_copy() -> str:
    """Every user-visible string the web interface can render.

    `index.html` is escaped markup, so entities are decoded before comparison:
    the app writes `Read keymap &amp; macros` for the label a user sees as
    `Read keymap & macros`.
    """

    parts = []
    for name in (
        "index.html",
        "app.js",
        "lighting_state.js",
        "lighting_workspace.js",
        "lighting_review.js",
        "lighting_targets.js",
        "lighting_composer.js",
        "library_state.js",
    ):
        text = (WEB / name).read_text(encoding="utf-8")
        if name.endswith(".html"):
            text = html_entities.unescape(text)
        parts.append(text)
    return "\n".join(parts)


class ReadmeStructureTest(unittest.TestCase):
    def test_readme_opens_with_the_product_purpose(self) -> None:
        readme = readme_text()
        purpose = (
            "Set up your Angry Miao keyboard — keymaps, macros, and lighting "
            "— from one app on your own computer."
        )
        self.assertIn(purpose, readme)
        self.assertLess(
            readme.index(purpose),
            readme.index(SECTION_ORDER[0]),
            "the product purpose must precede the download section",
        )

    def test_sections_follow_the_planned_order(self) -> None:
        readme = readme_text()
        positions = []
        for heading in SECTION_ORDER:
            with self.subTest(heading=heading):
                self.assertEqual(
                    1,
                    readme.count(f"\n{heading}\n"),
                    f"{heading} must appear exactly once as a section heading",
                )
            positions.append(readme.index(f"\n{heading}\n"))
        self.assertEqual(
            sorted(positions),
            positions,
            "README sections must follow the plan's order",
        )

    def test_capabilities_are_task_led_and_ordered(self) -> None:
        readme = readme_text()
        capabilities = readme.split("\n## What you can do\n", 1)[1].split(
            "\n## ", 1
        )[0]
        positions = []
        for heading in CAPABILITY_ORDER:
            with self.subTest(heading=heading):
                self.assertIn(heading, capabilities)
            positions.append(capabilities.index(heading))
        self.assertEqual(sorted(positions), positions)

    def test_screenshots_sit_between_the_quick_start_and_capabilities(
        self,
    ) -> None:
        readme = readme_text()
        for image in SCREENSHOTS:
            with self.subTest(image=image):
                self.assertEqual(1, readme.count(image))
                self.assertLess(
                    readme.index("\n## What it looks like\n"),
                    readme.index(image),
                )
                self.assertLess(
                    readme.index(image),
                    readme.index("\n## What you can do\n"),
                )
        # Exactly three markdown screenshots, each with alt text a screen
        # reader can use. The per-board gallery uses HTML <img> and is checked
        # separately, so it does not inflate this count.
        alts = re.findall(r"!\[([^\]]*)\]\(docs/images/[^)]+\)", readme)
        self.assertEqual(len(SCREENSHOTS), len(alts))
        for alt in alts:
            with self.subTest(alt=alt):
                self.assertGreaterEqual(len(alt.split()), 8, alt)

    def test_every_supported_board_appears_in_the_keyboard_gallery(self) -> None:
        # The owner asked for a screenshot of each connected keyboard; the
        # gallery must show all four supported boards, in the supported-
        # keyboards section (before the quick start), each with alt text.
        readme = readme_text()
        section = readme.index("\n## Supported keyboards")
        quick_start = readme.index("\n## Five-minute quick start\n")
        for image in GALLERY:
            with self.subTest(image=image):
                self.assertEqual(1, readme.count(image))
                position = readme.index(image)
                self.assertLess(section, position)
                self.assertLess(position, quick_start)
                self.assertTrue((ROOT / image).is_file(), image)
                alt = re.search(
                    rf'<img src="{re.escape(image)}" alt="([^"]*)"', readme
                )
                self.assertIsNotNone(alt, image)
                self.assertGreaterEqual(len(alt.group(1).split()), 6, alt)

    def test_developer_instructions_stay_collapsed(self) -> None:
        developers = readme_text().split("\n## For developers\n", 1)[1]
        self.assertIn("<details>", developers)
        self.assertIn("<summary>", developers)
        for command in (
            "uv sync --extra desktop",
            "python build.py",
            "uv run --frozen python -m unittest discover -s tests -v",
            "uv build",
        ):
            with self.subTest(command=command):
                self.assertIn(command, developers)


class ReadmeLinkTest(unittest.TestCase):
    def test_download_points_at_the_latest_release(self) -> None:
        download = readme_text().split("\n## Download the latest release\n", 1)[
            1
        ].split("\n## ", 1)[0]
        self.assertIn(
            "https://github.com/roethlar/AMKB-GUI/releases/latest",
            download,
        )

    def test_installer_names_match_what_the_build_publishes(self) -> None:
        download = readme_text().split("\n## Download the latest release\n", 1)[
            1
        ].split("\n## ", 1)[0]
        version = project_version()
        expected = (
            artifact_filename("macos", "aarch64"),
            artifact_filename("windows", "x86_64"),
            artifact_filename("linux", "x86_64"),
        )
        for name in expected:
            placeholder = name.replace(version, "<version>")
            with self.subTest(installer=name):
                self.assertIn(placeholder, download)

    def test_installation_verification_is_linked(self) -> None:
        readme = readme_text()
        verify = readme.split("\n## Verify your download\n", 1)[1].split(
            "\n## ", 1
        )[0]
        self.assertIn("docs/installing.md", verify)
        self.assertTrue((ROOT / "docs" / "installing.md").is_file())
        self.assertLess(
            readme.index("\n## Before you write to a keyboard\n"),
            readme.index("\n## Verify your download\n"),
        )


class ReadmeCopyTest(unittest.TestCase):
    def test_action_labels_match_the_application(self) -> None:
        readme = readme_text()
        interface = interface_copy()
        for label in ACTION_LABELS:
            with self.subTest(label=label):
                self.assertIn(
                    f"**{label}**",
                    readme,
                    f"the README must name the {label!r} action in bold",
                )
                self.assertIn(
                    label,
                    interface,
                    f"the interface no longer shows the label {label!r}",
                )

    def test_no_banned_implementation_vocabulary(self) -> None:
        prose = readme_prose()
        for pattern, replacement in BANNED:
            with self.subTest(pattern=pattern):
                hit = re.search(pattern, prose, re.IGNORECASE)
                self.assertIsNone(
                    hit,
                    f"README shows {hit and hit.group(0)!r} "
                    f"in user-facing copy ({replacement})",
                )

    def test_device_safety_states_the_write_and_backup_rules(self) -> None:
        safety = readme_text().split(
            "\n## Before you write to a keyboard\n", 1
        )[1].split("\n## ", 1)[0]
        collapsed = " ".join(safety.split())
        self.assertIn("never changes it", collapsed)
        self.assertIn(
            "full write replaces keymaps, macros, and LED data",
            collapsed,
        )
        self.assertIn("type the device ID", collapsed)
        self.assertIn("does not expose LED read-back", collapsed)


if __name__ == "__main__":
    unittest.main()
