"""Repository-local dependency ownership guards using only the standard library."""

from __future__ import annotations

import ast
from importlib import metadata
from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "am_configurator"
BUILD_TOOLS_ROOT = ROOT / "build_tools"

_OPTIONAL_DEPENDENCY_OWNERS = {
    "desktop": {"pywebview"},
    "build": {"pyinstaller"},
}
_OPTIONAL_IMPORT_ROOTS = {
    "pywebview": {"webview"},
}
_PLATFORM_IMPORT_OWNERS = {
    "AppKit": "pywebview",
}
_JAVASCRIPT_PACKAGE_FILES = {
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
}
_REPOSITORY_SCAN_EXCLUDES = {
    ".agents",
    ".git",
    ".serena",
    ".tokensave",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _project() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def _canonical_distribution(name: str) -> str:
    return "-".join(
        part
        for part in name.casefold().replace("_", "-").replace(".", "-").split("-")
        if part
    )


def _requirement_name(requirement: object) -> str:
    if not isinstance(requirement, str):
        raise ValueError("A direct dependency declaration is not a string.")
    value = requirement.strip()
    allowed = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    )
    end = 0
    while end < len(value) and value[end] in allowed:
        end += 1
    if end == 0:
        raise ValueError(f"Dependency declaration has no package name: {requirement!r}")
    return _canonical_distribution(value[:end])


def _requirement_names(requirements: object) -> set[str]:
    if not isinstance(requirements, list):
        raise ValueError("A dependency group is not a list.")
    return {_requirement_name(requirement) for requirement in requirements}


def _production_python_files() -> tuple[Path, ...]:
    paths = [
        *PACKAGE_ROOT.rglob("*.py"),
        *BUILD_TOOLS_ROOT.rglob("*.py"),
        ROOT / "build.py",
        ROOT / "packaging" / "launcher.py",
    ]
    return tuple(sorted(path for path in paths if path.is_file()))


def _parsed_imports(path: Path) -> tuple[ast.AST, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )


def _production_import_roots() -> tuple[set[str], dict[str, set[str]]]:
    roots: set[str] = set()
    owners: dict[str, set[str]] = {}
    for path in _production_python_files():
        relative = path.relative_to(ROOT).as_posix()
        for node in _parsed_imports(path):
            names: tuple[str, ...]
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif node.level == 0 and node.module:
                names = (node.module,)
            else:
                names = ()
            for name in names:
                root = name.split(".", 1)[0]
                roots.add(root)
                owners.setdefault(root, set()).add(relative)
    return roots, owners


def _internal_top_level_imports(path: Path) -> set[str]:
    imported: set[str] = set()
    inside_package = path.is_relative_to(PACKAGE_ROOT)
    for node in _parsed_imports(path):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) > 1 and parts[0] == "am_configurator":
                    imported.add(parts[1])
            continue
        if node.level == 0:
            if node.module:
                parts = node.module.split(".")
                if len(parts) > 1 and parts[0] == "am_configurator":
                    imported.add(parts[1])
            continue
        if not inside_package or node.level != 1:
            continue
        if node.module:
            imported.add(node.module.split(".", 1)[0])
        else:
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
    return imported


def _distribution_import_roots() -> dict[str, set[str]]:
    roots: dict[str, set[str]] = {}
    for import_root, distributions in metadata.packages_distributions().items():
        for distribution in distributions or ():
            roots.setdefault(_canonical_distribution(distribution), set()).add(
                import_root
            )
    return roots


def _entry_point_modules(project: dict) -> set[str]:
    modules = {"__main__"}
    project_table = project.get("project", {})
    for table_name in ("scripts", "gui-scripts"):
        table = project_table.get(table_name, {})
        if not isinstance(table, dict):
            raise ValueError(f"[project.{table_name}] is not a table.")
        for target in table.values():
            if not isinstance(target, str):
                raise ValueError(f"[project.{table_name}] has a non-string target.")
            module = target.split(":", 1)[0]
            parts = module.split(".")
            if len(parts) == 2 and parts[0] == "am_configurator":
                modules.add(parts[1])
    return modules


def _repository_files(directory: Path):
    for child in directory.iterdir():
        if child.name in _REPOSITORY_SCAN_EXCLUDES:
            continue
        if child.is_dir() and not child.is_symlink():
            yield from _repository_files(child)
        elif child.is_file():
            yield child


class DependencyOwnershipTests(unittest.TestCase):
    def test_runtime_dependencies_have_live_production_imports(self) -> None:
        project = _project()
        runtime_dependencies = _requirement_names(
            project.get("project", {}).get("dependencies")
        )
        import_roots, import_owners = _production_import_roots()
        distribution_roots = _distribution_import_roots()

        owned_runtime_roots: set[str] = set()
        for dependency in sorted(runtime_dependencies):
            roots = distribution_roots.get(dependency, set())
            if not roots:
                self.fail(
                    f"{dependency} exposes no import root in installed distribution metadata."
                )
            owners = {
                root
                for root in roots & import_roots
                if any(
                    path.startswith("am_configurator/")
                    for path in import_owners.get(root, set())
                )
            }
            if not owners:
                self.fail(
                    f"{dependency} owns no application import; metadata roots: "
                    f"{', '.join(sorted(roots))}."
                )
            owned_runtime_roots.update(roots)

        optional_roots = {
            root
            for roots in _OPTIONAL_IMPORT_ROOTS.values()
            for root in roots
        }
        allowed_platform_roots = set(_PLATFORM_IMPORT_OWNERS)
        third_party_roots = {
            root
            for root in import_roots
            if root not in sys.stdlib_module_names
            and root not in {"am_configurator", "build_tools"}
        }
        undeclared = (
            third_party_roots
            - owned_runtime_roots
            - optional_roots
            - allowed_platform_roots
        )
        self.assertFalse(
            undeclared,
            "Production imports undeclared third-party roots: "
            + ", ".join(
                f"{root} ({', '.join(sorted(import_owners[root]))})"
                for root in sorted(undeclared)
            ),
        )

    def test_optional_and_build_dependencies_have_executable_owners(self) -> None:
        project = _project()
        optional = project.get("project", {}).get("optional-dependencies")
        if not isinstance(optional, dict):
            self.fail("[project.optional-dependencies] is not a table.")
        actual = {
            group: _requirement_names(requirements)
            for group, requirements in optional.items()
        }
        self.assertEqual(_OPTIONAL_DEPENDENCY_OWNERS, actual)

        _, import_owners = _production_import_roots()
        for dependency, roots in _OPTIONAL_IMPORT_ROOTS.items():
            for root in roots:
                self.assertIn(
                    "am_configurator/desktop.py",
                    import_owners.get(root, set()),
                    f"{dependency} has no desktop import owner for {root}.",
                )
        declared_optional = {
            dependency for dependencies in actual.values() for dependency in dependencies
        }
        for import_root, dependency in _PLATFORM_IMPORT_OWNERS.items():
            self.assertIn(
                dependency,
                declared_optional,
                f"{import_root} has no declared optional owner.",
            )

        for relative in (
            "build.py",
            "packaging/am_configurator.spec",
            ".github/workflows/desktop.yml",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8").casefold()
            self.assertIn(
                "pyinstaller",
                source,
                f"pyinstaller has no executable owner in {relative}.",
            )

        build_system = project.get("build-system")
        if not isinstance(build_system, dict):
            self.fail("[build-system] is not a table.")
        self.assertEqual(
            {"hatchling"},
            _requirement_names(build_system.get("requires")),
        )
        self.assertEqual("hatchling.build", build_system.get("build-backend"))

    def test_locked_graph_covers_direct_dependencies_and_excludes_retired_tool(
        self,
    ) -> None:
        project = _project()
        optional = project.get("project", {}).get("optional-dependencies", {})
        if not isinstance(optional, dict):
            self.fail("[project.optional-dependencies] is not a table.")
        declared = _requirement_names(
            project.get("project", {}).get("dependencies")
        )
        for requirements in optional.values():
            declared.update(_requirement_names(requirements))

        with (ROOT / "uv.lock").open("rb") as stream:
            lock = tomllib.load(stream)
        packages = lock.get("package")
        if not isinstance(packages, list):
            self.fail("uv.lock has no package graph.")
        locked = {
            _canonical_distribution(package.get("name", ""))
            for package in packages
            if isinstance(package, dict)
        }
        self.assertFalse(
            declared - locked,
            "Direct dependencies are absent from uv.lock: "
            + ", ".join(sorted(declared - locked)),
        )

        retired_tool = "ff" + "mpeg"
        retired = sorted(name for name in locked if retired_tool in name)
        self.assertFalse(
            retired,
            "uv.lock contains retired media-tool packages: " + ", ".join(retired),
        )

    def test_every_top_level_module_is_imported_or_an_entry_point(self) -> None:
        modules = {
            path.stem: path
            for path in PACKAGE_ROOT.glob("*.py")
            if path.name != "__init__.py"
        }
        incoming = {module: set() for module in modules}
        for path in _production_python_files():
            relative = path.relative_to(ROOT).as_posix()
            for imported in _internal_top_level_imports(path):
                if imported in incoming and path != modules[imported]:
                    incoming[imported].add(relative)

        entry_points = _entry_point_modules(_project())
        orphans = sorted(
            module
            for module, owners in incoming.items()
            if not owners and module not in entry_points
        )
        self.assertFalse(
            orphans,
            "Top-level application modules have no production importer or entry "
            "point: " + ", ".join(orphans),
        )

    def test_no_javascript_package_manifest_or_lock_exists(self) -> None:
        found = sorted(
            path.relative_to(ROOT).as_posix()
            for path in _repository_files(ROOT)
            if path.name.casefold() in _JAVASCRIPT_PACKAGE_FILES
        )
        self.assertEqual(
            [],
            found,
            "JavaScript package metadata requires an approved dependency decision.",
        )


if __name__ == "__main__":
    unittest.main()
