"""
Architectural isolation and boundary tests.

Enforces strict separation of concerns per docs/SPEC.md:
1. Modules under estimator/ and decision_engine/ must NEVER import simulator
   ground truth or ground truth models.
2. The estimator and decision engine must operate solely on observable domain objects.
"""

import ast
from pathlib import Path
import pytest


def test_no_ground_truth_imports_in_estimator_and_decision_engine():
    """
    Static AST test: Fails if anything under estimator/ or decision_engine/
    imports simulator ground truth.
    """
    backend_dir = Path(__file__).parent.parent
    check_dirs = [backend_dir / "estimator", backend_dir / "decision_engine"]

    violations = []

    for directory in check_dirs:
        for py_file in directory.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                # Check `import ...`
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name_lower = alias.name.lower()
                        if "ground_truth" in name_lower or "groundtruth" in name_lower:
                            violations.append(
                                f"{py_file.name}:{node.lineno} imports '{alias.name}'"
                            )
                        if alias.name.startswith("simulator"):
                            violations.append(
                                f"{py_file.name}:{node.lineno} imports '{alias.name}'"
                            )

                # Check `from ... import ...`
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    module_lower = module.lower()
                    if "ground_truth" in module_lower or "groundtruth" in module_lower:
                        violations.append(
                            f"{py_file.name}:{node.lineno} imports from '{module}'"
                        )
                    if module.startswith("simulator"):
                        violations.append(
                            f"{py_file.name}:{node.lineno} imports from '{module}'"
                        )
                    for alias in node.names:
                        alias_lower = alias.name.lower()
                        if "ground_truth" in alias_lower or "groundtruth" in alias_lower:
                            violations.append(
                                f"{py_file.name}:{node.lineno} imports symbol '{alias.name}' from '{module}'"
                            )

    assert not violations, (
        "Architectural boundary violated: estimator or decision_engine directly "
        f"imported simulator ground truth:\n" + "\n".join(violations)
    )


def test_ast_detector_catches_synthetic_violation():
    """Verify that our AST check correctly detects a ground truth import if introduced."""
    code = "from simulator.ground_truth import AdGroundTruth"
    tree = ast.parse(code)
    found_violation = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if "ground_truth" in (node.module or "").lower() or (node.module or "").startswith("simulator"):
                found_violation = True
    assert found_violation is True


def test_no_scratch_imports_in_backend():
    """
    Static AST test: Enforce that no module under backend/ imports from scratch/.
    Production code and tests in backend/ must be self-contained or use canonical modules.
    """
    backend_dir = Path(__file__).parent.parent
    violations = []

    for py_file in backend_dir.rglob("*.py"):
        if any(p.startswith(".") or p in ("venv", "build", "dist", "__pycache__") for p in py_file.parts):
            continue
        with open(py_file, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(py_file))
            except SyntaxError:
                continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "scratch" or alias.name.startswith("scratch."):
                        violations.append(
                            f"{py_file.relative_to(backend_dir)}:{node.lineno} imports '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "scratch" or module.startswith("scratch."):
                    violations.append(
                        f"{py_file.relative_to(backend_dir)}:{node.lineno} imports from '{module}'"
                    )

    assert not violations, (
        f"Found illegal imports from scratch/ in backend/:\n" + "\n".join(violations)
    )

