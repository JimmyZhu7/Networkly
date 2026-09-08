#!/usr/bin/env python3
"""Inventory runtime Python functions and attach measured line execution.

Coverage is evidence of execution, not proof of correctness. Test helpers,
migrations and dependencies are excluded. Run from any directory; no database
or provider access is made.
"""
import argparse
import ast
import csv
import json
from pathlib import Path


def inventory(root, coverage):
    for package in ("networkly_web", "networkly_domain", "networkly_connectors"):
        for path in sorted((root / package).rglob("*.py")):
            relative = path.relative_to(root)
            if any(part in {"tests", "e2e", "migrations", ".venv", "__pycache__"} for part in relative.parts):
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(), filename=str(relative))
            data = coverage.get(str(relative), {})
            executed = set(data.get("executed_lines", []))
            executable = executed | set(data.get("missing_lines", []))

            def visit(node, parents=()):
                named = isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                qualified = parents + (node.name,) if named else parents
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = list(node.body)
                    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                        body = body[1:]
                    start = body[0].lineno if body else node.end_lineno
                    lines = set(range(start, node.end_lineno + 1)) & executable
                    hit = len(lines & executed)
                    status = "Not measured" if not data else (
                        "No executable body lines" if not lines else
                        "Body not exercised" if not hit else
                        "All body lines exercised" if hit == len(lines) else "Some body lines exercised"
                    )
                    yield [str(relative), node.lineno, ".".join(qualified),
                           isinstance(node, ast.AsyncFunctionDef), len(lines), hit, status]
                for child in ast.iter_child_nodes(node):
                    yield from visit(child, qualified)

            yield from visit(tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    coverage = {}
    for name in args.coverage_json:
        for filename, data in json.loads(Path(name).read_text())["files"].items():
            key = str(Path(filename).relative_to(root)) if Path(filename).is_absolute() else filename
            previous = coverage.setdefault(key, {"executed_lines": [], "missing_lines": []})
            previous["executed_lines"] = sorted(set(previous["executed_lines"]) | set(data["executed_lines"]))
            previous["missing_lines"] = sorted((set(previous["missing_lines"]) | set(data["missing_lines"])) - set(previous["executed_lines"]))
    rows = list(inventory(root, coverage))
    with Path(args.output).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "line", "function", "async", "executable_body_lines", "executed_body_lines", "execution_evidence"])
        writer.writerows(rows)
    print(f"{len(rows)} functions across {len({row[0] for row in rows})} modules inventoried.")


if __name__ == "__main__":
    main()
