from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / 'app'


def _iter_python_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in APP_ROOT.rglob('*.py'):
        rel = path.relative_to(BACKEND_ROOT)
        parts = rel.with_suffix('').parts
        module_name = '.'.join(parts)
        modules[module_name] = path
        if parts[-1] == '__init__':
            modules['.'.join(parts[:-1])] = path
    return modules


MODULE_PATHS = _iter_python_modules()


def _parse_module(module_name: str) -> ast.Module:
    path = MODULE_PATHS[module_name]
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _resolve_import_target(*, current_module: str, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package_parts = current_module.split('.')[:-1]
    up_levels = node.level - 1
    if up_levels > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - up_levels]
    if node.module:
        base_parts.extend(node.module.split('.'))
    return '.'.join(base_parts)


@lru_cache(maxsize=None)
def _exported_names(module_name: str) -> frozenset[str]:
    if module_name not in MODULE_PATHS:
        return frozenset()
    tree = _parse_module(module_name)
    names: set[str] = set()
    explicit_all: list[str] | None = None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                    if target.id == '__all__':
                        try:
                            value = ast.literal_eval(node.value)
                        except Exception:
                            value = None
                        if isinstance(value, list) and all(isinstance(item, str) for item in value):
                            explicit_all = value
            continue
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        target_module = _resolve_import_target(current_module=module_name, node=node)
        if not target_module or not target_module.startswith('app.'):
            continue

        if target_module in MODULE_PATHS:
            target_exports = _exported_names(target_module)
        else:
            # Package-level import like: from app.services import openai_story_engine
            package_prefix = f'{target_module}.'
            target_exports = {
                submodule[len(package_prefix) :].split('.')[0]
                for submodule in MODULE_PATHS
                if submodule.startswith(package_prefix)
            }

        if any(alias.name == '*' for alias in node.names):
            names.update(target_exports)
            continue

        for alias in node.names:
            names.add(alias.asname or alias.name)

    if explicit_all is not None:
        names.update(explicit_all)
    return frozenset(names)


def test_local_from_imports_reference_existing_symbols() -> None:
    problems: list[str] = []

    for module_name in sorted(MODULE_PATHS):
        tree = _parse_module(module_name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue

            target_module = _resolve_import_target(current_module=module_name, node=node)
            if not target_module or not target_module.startswith('app.'):
                continue
            if any(alias.name == '*' for alias in node.names):
                continue

            package_prefix = f'{target_module}.'
            package_submodules = {
                submodule[len(package_prefix) :].split('.')[0]
                for submodule in MODULE_PATHS
                if submodule.startswith(package_prefix)
            }
            exported = set(package_submodules)
            if target_module in MODULE_PATHS:
                exported.update(_exported_names(target_module))

            for alias in node.names:
                if alias.name not in exported:
                    problems.append(
                        f'{module_name}:{node.lineno} imports {alias.name!r} from {target_module!r}, '
                        'but that symbol is not exported there.'
                    )

    assert not problems, '\n'.join(problems)
