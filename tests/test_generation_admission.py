from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GenerationAdmissionArchitectureTests(unittest.TestCase):
    def test_live_admission_has_no_dependency_on_historical_recovery(self) -> None:
        from am_configurator import generation_admission, procedural_generation

        admission_source = Path(generation_admission.__file__).read_text("utf-8")
        procedural_source = Path(procedural_generation.__file__).read_text("utf-8")
        self.assertNotIn("from .generation import", procedural_source)
        self.assertNotIn("import generation", admission_source)
        self.assertNotIn("procedural_generation", admission_source)

    def test_admission_and_procedural_modules_import_in_any_order(self) -> None:
        orders = (
            ("generation_admission", "procedural_generation"),
            ("procedural_generation", "generation_admission"),
        )
        for order in orders:
            imports = ";".join(
                f"import am_configurator.{module}" for module in order
            )
            script = (
                f"{imports};"
                "from am_configurator import generation_admission as a;"
                "from am_configurator import procedural_generation as p;"
                "assert a.OperationGate is p.OperationGate;"
                "assert a.GenerationBusyError is p.GenerationBusyError"
            )
            with self.subTest(order=order):
                completed = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    0,
                    completed.returncode,
                    completed.stdout + completed.stderr,
                )

    def test_retired_video_generation_module_is_absent(self) -> None:
        self.assertIsNone(importlib.util.find_spec("am_configurator.generation"))


if __name__ == "__main__":
    unittest.main()
