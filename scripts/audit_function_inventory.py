#!/usr/bin/env python3
"""Inventory runtime Python functions and attach measured line execution.

Coverage is evidence of line execution, not proof of correctness or branch
coverage. Nested function/class bodies are excluded from their enclosing
function; their declaration/decorator lines stay attributed to the enclosing
function. Shared declaration/body lines and stub bodies cannot establish
function entry and are marked indeterminate, never counted as exercised.
Test helpers, migrations and dependencies are excluded. Run from any directory;
no database or provider access is made.
"""
import argparse
import ast
import csv
import json
from pathlib import Path


SCOPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _without_docstring(body):
    body = list(body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


def _start_line(node):
    """Include decorators, which execute before a nested declaration."""
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def _shares_declaration_line(statement, source_lines):
    # AST columns are UTF-8 byte offsets. Normal suites have only indentation
    # before their first statement; inline suites have the signature's colon.
    return bool(source_lines[statement.lineno - 1].encode("utf-8")[:statement.col_offset].strip())


def _nested_scopes(node):
    """Yield direct nested scopes, including scopes inside control flow."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPES):
            yield child
        else:
            yield from _nested_scopes(child)


def _body_lines(node, source_lines):
    """Return independently attributable body lines and an ambiguity reason."""
    body = _without_docstring(node.body)
    if not body or all(isinstance(stmt, ast.Pass) or (
        isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    ) for stmt in body):
        return set(), "stub body"

    shared = _shares_declaration_line(body[0], source_lines)
    start = _start_line(body[0])
    lines = set(range(start, node.end_lineno + 1))
    if shared:
        # The coverage hit may be the declaration alone. Do not put it in the
        # executed-body total even if coverage.py reports this line as hit.
        lines.discard(body[0].lineno)

    for nested in _nested_scopes(node):
        nested_start = _start_line(nested.body[0])
        if _shares_declaration_line(nested.body[0], source_lines):
            # The shared line still proves the parent's declaration executed.
            nested_start += 1
        lines.difference_update(range(nested_start, nested.end_lineno + 1))
    return lines, "declaration shares a body line" if shared else None


def inventory(root, coverage):
    for package in ("networkly_web", "networkly_domain", "networkly_connectors"):
        for path in sorted((root / package).rglob("*.py")):
            relative = path.relative_to(root)
            if any(part in {"tests", "e2e", "migrations", ".venv", "__pycache__"} for part in relative.parts):
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            source = path.read_text()
            source_lines = source.splitlines()
            tree = ast.parse(source, filename=str(relative))
            data = coverage.get(str(relative), {})
            executed = set(data.get("executed_lines", []))
            executable = executed | set(data.get("missing_lines", []))

            def visit(node, parents=()):
                named = isinstance(node, SCOPES)
                qualified = parents + (node.name,) if named else parents
                if isinstance(node, FUNCTIONS):
                    candidates, ambiguity = _body_lines(node, source_lines)
                    lines = candidates & executable
                    hit = len(lines & executed)
                    status = "Not measured" if not data else (
                        f"Body entry indeterminate ({ambiguity})" if ambiguity else
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
