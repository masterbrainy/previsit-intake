"""Static checks over src/previsit using the AST (no imports, so it works before the code runs)."""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
PACKAGE = "previsit"


def module_path(dotted: str) -> Path:
    base = SRC_ROOT.joinpath(*dotted.split("."))
    package_init = base / "__init__.py"
    return package_init if package_init.exists() else base.with_suffix(".py")


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def all_modules() -> list[str]:
    return sorted(module_name(p) for p in (SRC_ROOT / PACKAGE).rglob("*.py"))


@lru_cache(maxsize=None)
def parse(dotted: str) -> ast.Module:
    return ast.parse(module_path(dotted).read_text(), filename=str(module_path(dotted)))


def direct_imports(dotted: str) -> set[str]:
    """Absolute names imported by a module, relative imports resolved. 'from a import b' yields a and a.b."""
    is_package = module_path(dotted).name == "__init__.py"
    package = dotted if is_package else dotted.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(parse(dotted)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                base_parts = base_parts[: len(base_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _internal(name: str) -> str | None:
    """Map an imported name to an existing previsit module, if it is one."""
    if not (name == PACKAGE or name.startswith(PACKAGE + ".")):
        return None
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if module_path(candidate).exists():
            return candidate
        parts.pop()
    return None


def transitive_imports(dotted: str) -> set[str]:
    """Every name imported by the module and, recursively, by the previsit modules it imports."""
    seen_modules: set[str] = set()
    names: set[str] = set()
    stack = [dotted]
    while stack:
        current = stack.pop()
        if current in seen_modules:
            continue
        seen_modules.add(current)
        for name in direct_imports(current):
            names.add(name)
            internal = _internal(name)
            if internal and internal not in seen_modules:
                stack.append(internal)
    return names


def imports_any(names: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(n for n in names if any(n == p or n.startswith(p + ".") for p in prefixes))


def enum_member_refs(tree: ast.AST, enum_name: str, members: set[str]) -> list[ast.Attribute]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in members
        and isinstance(node.value, ast.Name) and node.value.id == enum_name
    ]


def assignments_of_enum(dotted: str, enum_name: str, members: set[str]) -> list[int]:
    """Line numbers where Enum.MEMBER is assigned or passed as a keyword (not merely compared)."""
    lines: list[int] = []
    for node in ast.walk(parse(dotted)):
        values: list[ast.AST] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            values.append(node.value)
        elif isinstance(node, ast.keyword):
            values.append(node.value)
        elif isinstance(node, ast.Dict):
            values.extend(v for v in node.values if v is not None)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr":
            values.extend(node.args[2:3])
        for value in values:
            lines.extend(ref.lineno for ref in enum_member_refs(value, enum_name, members))
    return sorted(set(lines))


def constructor_calls(dotted: str, class_name: str) -> list[int]:
    lines = []
    for node in ast.walk(parse(dotted)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name == class_name:
                lines.append(node.lineno)
    return lines
