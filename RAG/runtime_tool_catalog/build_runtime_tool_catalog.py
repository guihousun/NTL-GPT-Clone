"""Build a static, versioned catalog of the active NTL-GPT tool surface.

This builder intentionally reads Python source with :mod:`ast` instead of
importing ``tools``.  It therefore cannot execute tool module import-time code,
cannot touch a vector-store database, and remains usable when optional GIS
dependencies are unavailable.  The resulting files are *discovery material*
for a future, low-priority RAG collection; role Skills and registered runtime
tool allowlists remain authoritative for invocation and routing.

The manifest contains only repository-relative source references, sanitized
descriptions, and static input-schema summaries.  It never copies tool source
code, credentials, or machine-specific absolute paths.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


CATALOG_FORMAT = "ntl-gpt.runtime-tool-catalog.v1"
BUILDER_VERSION = "1.0.0"
_MISSING = object()

_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?:[A-Z]:[\\/][^\s`'\"<>]+)")
_UNIX_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_])/(?:home|users|mnt|tmp|var|private|opt)/[^\s`'\"<>]+",
    re.IGNORECASE,
)
_SECRET_LITERAL = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)
_LEGACY_COLLECTION_REFERENCE = re.compile(
    r"\b(?:Code_RAG|Solution_RAG|Literature_RAG)\b", re.IGNORECASE
)


class CatalogBuildError(RuntimeError):
    """Raised when the active runtime registration cannot be statically read."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _source_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_python(path: Path) -> ast.Module:
    try:
        return ast.parse(_source_text(path), filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - exact message is Python-version specific
        raise CatalogBuildError(f"Cannot parse {path.name}: {exc.msg}") from exc


def _scrub_text(value: str) -> str:
    """Keep useful interface prose while removing credentials and host paths."""

    value = _SECRET_LITERAL.sub(lambda match: f"{match.group(0).split(match.group(1))[0]}[REDACTED]", value)
    value = _WINDOWS_ABSOLUTE_PATH.sub("[REDACTED_ABSOLUTE_PATH]", value)
    value = _UNIX_ABSOLUTE_PATH.sub("[REDACTED_ABSOLUTE_PATH]", value)
    return _LEGACY_COLLECTION_REFERENCE.sub("[LEGACY_COLLECTION]", value)


def _node_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return _scrub_text(ast.unparse(node))
    except Exception:  # pragma: no cover - defensive for unusual AST nodes
        return None


def _literal_string(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return _scrub_text(value) if isinstance(value, str) else None


def _literal_value(node: ast.AST | None) -> Any:
    """Return only safe literal defaults; retain other defaults as an expression tag."""

    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        text = _node_text(node)
        return {"kind": "expression", "value": text or "<unavailable>"}
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, dict)):
        return _scrub_nested_literals(value)
    return {"kind": "literal", "value": repr(value)}


def _scrub_nested_literals(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, list):
        return [_scrub_nested_literals(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_nested_literals(item) for item in value]
    if isinstance(value, dict):
        return {
            _scrub_nested_literals(key): _scrub_nested_literals(item)
            for key, item in value.items()
        }
    return value


def _assignment_map(tree: ast.Module) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for statement in tree.body:
        targets: list[ast.expr] = []
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = statement.value
    return assignments


def _dict_items(node: ast.AST, *, label: str) -> list[tuple[ast.AST | None, ast.AST]]:
    if not isinstance(node, ast.Dict):
        raise CatalogBuildError(f"{label} must be a dictionary literal")
    return list(zip(node.keys, node.values, strict=True))


def _string_key(node: ast.AST | None, *, label: str) -> str:
    value = _literal_string(node)
    if value is None:
        raise CatalogBuildError(f"{label} has a non-string key")
    return value


def _parse_exports_and_groups(tools_init: Path) -> tuple[dict[str, tuple[str, str]], dict[str, list[str]]]:
    tree = _parse_python(tools_init)
    assignments = _assignment_map(tree)
    exports_node = assignments.get("_EXPORTS")
    role_groups_node = assignments.get("_ROLE_GROUPS")
    groups_node = assignments.get("_GROUPS")
    if exports_node is None or role_groups_node is None or groups_node is None:
        raise CatalogBuildError("tools/__init__.py is missing _EXPORTS, _ROLE_GROUPS, or _GROUPS")

    exports: dict[str, tuple[str, str]] = {}
    for key_node, value_node in _dict_items(exports_node, label="_EXPORTS"):
        key = _string_key(key_node, label="_EXPORTS")
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError) as exc:
            raise CatalogBuildError(f"_EXPORTS[{key!r}] is not static") from exc
        if not (
            isinstance(value, tuple)
            and len(value) == 2
            and all(isinstance(item, str) for item in value)
        ):
            raise CatalogBuildError(f"_EXPORTS[{key!r}] must be a pair of strings")
        exports[key] = value

    role_groups: dict[str, list[str]] = {}
    for key_node, value_node in _dict_items(role_groups_node, label="_ROLE_GROUPS"):
        key = _string_key(key_node, label="_ROLE_GROUPS")
        try:
            values = ast.literal_eval(value_node)
        except (ValueError, TypeError) as exc:
            raise CatalogBuildError(f"_ROLE_GROUPS[{key!r}] is not static") from exc
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise CatalogBuildError(f"_ROLE_GROUPS[{key!r}] must be a list of tool exports")
        role_groups[key] = values

    groups: dict[str, list[str]] = {}
    for key_node, value_node in _dict_items(groups_node, label="_GROUPS"):
        if key_node is None:
            if not isinstance(value_node, ast.Name) or value_node.id != "_ROLE_GROUPS":
                raise CatalogBuildError("_GROUPS has an unsupported dictionary expansion")
            groups.update({key: list(value) for key, value in role_groups.items()})
            continue
        key = _string_key(key_node, label="_GROUPS")
        if isinstance(value_node, ast.List):
            try:
                values = ast.literal_eval(value_node)
            except (ValueError, TypeError) as exc:
                raise CatalogBuildError(f"_GROUPS[{key!r}] is not static") from exc
        elif isinstance(value_node, ast.Call) and isinstance(value_node.func, ast.Name) and value_node.func.id == "_strict_union":
            values = []
            for argument in value_node.args:
                if not (
                    isinstance(argument, ast.Subscript)
                    and isinstance(argument.value, ast.Name)
                    and argument.value.id == "_ROLE_GROUPS"
                ):
                    raise CatalogBuildError("single_agent_tools must only union role groups")
                group_name = _literal_string(argument.slice)
                if group_name not in role_groups:
                    raise CatalogBuildError(f"Unknown role group {group_name!r} in single_agent_tools")
                values.extend(role_groups[group_name])
            values = list(dict.fromkeys(values))
        else:
            raise CatalogBuildError(f"Unsupported _GROUPS expression for {key!r}")
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise CatalogBuildError(f"_GROUPS[{key!r}] must resolve to a tool-export list")
        groups[key] = values

    for group_name, tool_names in groups.items():
        unknown = sorted(set(tool_names).difference(exports))
        if unknown:
            raise CatalogBuildError(f"{group_name} references unknown exports: {', '.join(unknown)}")
    return exports, groups


def _keyword_value(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _parse_role_specs(role_specs_path: Path) -> dict[str, dict[str, Any]]:
    tree = _parse_python(role_specs_path)
    role_specs_node = _assignment_map(tree).get("ROLE_SPECS")
    if role_specs_node is None:
        raise CatalogBuildError("agents/role_specs.py is missing ROLE_SPECS")

    role_specs: dict[str, dict[str, Any]] = {}
    for key_node, value_node in _dict_items(role_specs_node, label="ROLE_SPECS"):
        canonical_name = _string_key(key_node, label="ROLE_SPECS")
        if not (
            isinstance(value_node, ast.Call)
            and isinstance(value_node.func, ast.Name)
            and value_node.func.id == "RoleSpec"
        ):
            raise CatalogBuildError(f"ROLE_SPECS[{canonical_name!r}] must construct RoleSpec")
        values = {keyword.arg: keyword.value for keyword in value_node.keywords if keyword.arg}
        tool_group = _literal_string(values.get("tool_group"))
        package_type = _literal_string(values.get("expected_package_type"))
        description = _literal_string(values.get("description"))
        can_delegate_value = _literal_value(values.get("can_delegate"))
        if not tool_group or not package_type:
            raise CatalogBuildError(f"ROLE_SPECS[{canonical_name!r}] is missing a static tool group or package")
        skill_sources: list[str] = []
        skill_node = values.get("skill_sources")
        if (
            isinstance(skill_node, ast.Call)
            and isinstance(skill_node.func, ast.Name)
            and skill_node.func.id == "_role_skills"
            and len(skill_node.args) == 1
        ):
            namespace = _literal_string(skill_node.args[0])
            if namespace:
                skill_sources = ["/skills/common/", f"/skills/{namespace}/"]
        role_specs[canonical_name] = {
            "description": description or "",
            "tool_group": tool_group,
            "skill_sources": skill_sources,
            "expected_package_type": package_type,
            "can_delegate": bool(can_delegate_value) if isinstance(can_delegate_value, bool) else False,
        }
    return role_specs


def _module_source_path(repo_root: Path, module_name: str) -> Path:
    if not module_name.startswith("."):
        raise CatalogBuildError(f"Only relative tool modules are supported: {module_name!r}")
    relative_module = module_name.lstrip(".").replace(".", "/")
    candidate = repo_root / "tools" / f"{relative_module}.py"
    if candidate.exists():
        return candidate
    package_candidate = repo_root / "tools" / relative_module / "__init__.py"
    if package_candidate.exists():
        return package_candidate
    raise CatalogBuildError(f"Registered module does not exist: tools/{relative_module}")


def _function_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
    return functions


def _class_nodes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _is_required_default(default_node: ast.AST | None) -> bool:
    if default_node is None:
        return True
    if isinstance(default_node, ast.Constant) and default_node.value is Ellipsis:
        return True
    if isinstance(default_node, ast.Call) and isinstance(default_node.func, ast.Name) and default_node.func.id == "Field":
        if _keyword_value(default_node, "default_factory") is not None:
            return False
        if not default_node.args:
            return _keyword_value(default_node, "default") is None
        return isinstance(default_node.args[0], ast.Constant) and default_node.args[0].value is Ellipsis
    return False


def _field_description(default_node: ast.AST | None) -> str | None:
    if not (
        isinstance(default_node, ast.Call)
        and isinstance(default_node.func, ast.Name)
        and default_node.func.id == "Field"
    ):
        return None
    return _literal_string(_keyword_value(default_node, "description"))


def _field_default(default_node: ast.AST | None) -> Any:
    if not (
        isinstance(default_node, ast.Call)
        and isinstance(default_node.func, ast.Name)
        and default_node.func.id == "Field"
    ):
        return _literal_value(default_node)
    if default_node.args:
        return _literal_value(default_node.args[0])
    default_kw = _keyword_value(default_node, "default")
    if default_kw is not None:
        return _literal_value(default_kw)
    factory_kw = _keyword_value(default_node, "default_factory")
    if factory_kw is not None:
        return {"kind": "factory", "value": _node_text(factory_kw) or "<unavailable>"}
    return None


def _class_schema(class_node: ast.ClassDef) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for statement in class_node.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
            continue
        fields.append(
            {
                "name": statement.target.id,
                "annotation": _node_text(statement.annotation) or "Any",
                "required": _is_required_default(statement.value),
                "default": _field_default(statement.value),
                "description": _field_description(statement.value),
            }
        )
    return {
        "kind": "declared_model",
        "name": class_node.name,
        "description": _scrub_text(ast.get_docstring(class_node) or ""),
        "fields": fields,
    }


def _function_schema(function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    positional_defaults: list[ast.AST | object] = [_MISSING] * (
        len(function.args.posonlyargs) + len(function.args.args) - len(function.args.defaults)
    )
    positional_defaults.extend(function.args.defaults)
    defaults: list[ast.AST | object] = positional_defaults + [
        default if default is not None else _MISSING for default in function.args.kw_defaults
    ]
    fields: list[dict[str, Any]] = []
    for argument, default in zip(args, defaults, strict=True):
        if argument.arg in {"self", "cls"}:
            continue
        fields.append(
            {
                "name": argument.arg,
                "annotation": _node_text(argument.annotation) or "Any",
                "required": default is _MISSING,
                "default": _literal_value(default) if default is not _MISSING else None,
                "description": None,
            }
        )
    return {
        "kind": "function_signature",
        "name": function.name,
        "description": _scrub_text(ast.get_docstring(function) or ""),
        "fields": fields,
    }


def _reference_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _node_text(node)
    return None


def _is_structured_tool_factory(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "from_function"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "StructuredTool"
    )


def _tool_assignment(tree: ast.Module, export_symbol: str) -> ast.AST | None:
    result: ast.AST | None = None
    for statement in tree.body:
        targets: Iterable[ast.expr]
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == export_symbol for target in targets):
            result = statement.value
    return result


def _extract_tool_interface(module_path: Path, export_symbol: str) -> dict[str, Any]:
    tree = _parse_python(module_path)
    assignment = _tool_assignment(tree, export_symbol)
    functions = _function_nodes(tree)
    classes = _class_nodes(tree)
    default_result: dict[str, Any] = {
        "source_symbol": export_symbol,
        "runtime_name": export_symbol,
        "description": "",
        "factory": "unresolved",
        "return_direct": None,
        "input_schema": {
            "kind": "unresolved",
            "name": None,
            "description": "",
            "fields": [],
        },
        "parse_warning": "No static StructuredTool.from_function assignment was found.",
    }
    if not isinstance(assignment, ast.Call) or not _is_structured_tool_factory(assignment):
        return default_result

    function_name = _reference_name(_keyword_value(assignment, "func"))
    schema_name = _reference_name(_keyword_value(assignment, "args_schema"))
    if schema_name is None:
        schema_name = _reference_name(_keyword_value(assignment, "input_type"))
    runtime_name = _literal_string(_keyword_value(assignment, "name")) or export_symbol
    description = _literal_string(_keyword_value(assignment, "description"))
    return_direct = _literal_value(_keyword_value(assignment, "return_direct"))
    schema: dict[str, Any]
    if schema_name and schema_name in classes:
        schema = _class_schema(classes[schema_name])
    elif function_name and function_name in functions:
        schema = _function_schema(functions[function_name])
    else:
        schema = {
            "kind": "unresolved",
            "name": schema_name or function_name,
            "description": "",
            "fields": [],
        }

    if not description and function_name and function_name in functions:
        description = _scrub_text(ast.get_docstring(functions[function_name]) or "")
    result = {
        "source_symbol": export_symbol,
        "runtime_name": runtime_name,
        "description": description or "",
        "factory": "StructuredTool.from_function",
        "function": function_name,
        "return_direct": return_direct if isinstance(return_direct, bool) else None,
        "input_schema": schema,
    }
    if schema["kind"] == "unresolved":
        result["parse_warning"] = "Tool factory found, but its input schema could not be statically resolved."
    return result


def _git_head(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _role_membership(
    groups: Mapping[str, list[str]], role_specs: Mapping[str, Mapping[str, Any]]
) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = {}
    for role_name, role_spec in role_specs.items():
        group_name = str(role_spec["tool_group"])
        for export_name in groups.get(group_name, []):
            membership.setdefault(export_name, []).append(role_name)
    return membership


def _tool_card(tool: Mapping[str, Any], snapshot_id: str) -> dict[str, Any]:
    roles = tool["roles"] or ["not exposed to a current four-role allowlist"]
    fields = tool["input_schema"]["fields"]
    field_lines = [
        f"- {field['name']} ({field['annotation']}); {'required' if field['required'] else 'optional'}"
        for field in fields
    ] or ["- Static schema unavailable; obtain the live tool schema before calling."]
    content = "\n".join(
        [
            f"Runtime tool: {tool['runtime_name']}",
            f"Registered export: {tool['export_name']}",
            f"Allowed roles: {', '.join(roles)}",
            f"Description: {tool['description'] or 'No static description extracted.'}",
            "Inputs:",
            *field_lines,
            "Invocation rule: this catalog is supplementary discovery material. "
            "Use the active role Skill and live registered tool schema as the authority.",
        ]
    )
    return {
        "record_type": "runtime_tool_card",
        "catalog_format": CATALOG_FORMAT,
        "snapshot_id": snapshot_id,
        "tool_export": tool["export_name"],
        "runtime_name": tool["runtime_name"],
        "roles": tool["roles"],
        "source_file": tool["source_file"],
        "source_sha256": tool["source_sha256"],
        "content": content,
    }


def build_catalog(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return an in-memory manifest and one retrieval card per registered export."""

    repo_root = repo_root.resolve()
    tools_init = repo_root / "tools" / "__init__.py"
    role_specs_path = repo_root / "agents" / "role_specs.py"
    if not tools_init.exists() or not role_specs_path.exists():
        raise CatalogBuildError("repo root must contain tools/__init__.py and agents/role_specs.py")

    exports, groups = _parse_exports_and_groups(tools_init)
    role_specs = _parse_role_specs(role_specs_path)
    for role_name, role_spec in role_specs.items():
        if role_spec["tool_group"] not in groups:
            raise CatalogBuildError(f"{role_name} references unknown tool group {role_spec['tool_group']!r}")

    source_paths = {tools_init, role_specs_path}
    module_paths: dict[str, Path] = {}
    for export_name, (module_name, _) in exports.items():
        module_path = _module_source_path(repo_root, module_name)
        module_paths[export_name] = module_path
        source_paths.add(module_path)

    source_hashes = {
        path.relative_to(repo_root).as_posix(): _sha256_bytes(path.read_bytes())
        for path in sorted(source_paths)
    }
    source_bundle_sha256 = _sha256_bytes(_canonical_json(source_hashes).encode("utf-8"))
    git_head = _git_head(repo_root)
    head_label = (git_head or "no-git")[:12]
    snapshot_id = f"runtime-tool-catalog-v1-{head_label}-{source_bundle_sha256[:12]}"
    role_membership = _role_membership(groups, role_specs)

    tools: list[dict[str, Any]] = []
    for export_name, (module_name, symbol) in exports.items():
        module_path = module_paths[export_name]
        interface = _extract_tool_interface(module_path, symbol)
        relative_source = module_path.relative_to(repo_root).as_posix()
        tools.append(
            {
                "export_name": export_name,
                "module": module_name,
                "source_file": relative_source,
                "source_sha256": source_hashes[relative_source],
                "roles": role_membership.get(export_name, []),
                "runtime_exposure": (
                    "four_role_runtime" if role_membership.get(export_name) else "not_exposed_to_four_role_runtime"
                ),
                "groups": [group for group, names in groups.items() if export_name in names],
                **interface,
            }
        )

    manifest = {
        "catalog_format": CATALOG_FORMAT,
        "snapshot_id": snapshot_id,
        "catalog_priority": "low_priority_supplement",
        "authority": {
            "invocation": "Active role Skills, role allowlists, and live registered tool schemas are authoritative.",
            "catalog": "This static catalog is discovery-only RAG source material. It must not grant a role a tool, override an active Skill, or replace live argument validation.",
            "activation": "not_enabled_by_this_build",
        },
        "builder": {
            "version": BUILDER_VERSION,
            "path": "RAG/runtime_tool_catalog/build_runtime_tool_catalog.py",
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "import_free": True,
        },
        "runtime_source": {
            "git_head": git_head,
            "source_bundle_sha256": source_bundle_sha256,
            "source_files": source_hashes,
            "inputs": ["tools/__init__.py", "agents/role_specs.py", "registered tool modules"],
        },
        "roles": role_specs,
        "groups": groups,
        "tools": tools,
        "counts": {
            "registered_exports": len(exports),
            "four_role_exposed_exports": len(role_membership),
            "not_exposed_to_four_role_runtime": len(exports) - len(role_membership),
            "tool_cards": len(role_membership),
        },
    }
    # Cards are intentionally limited to the live four-role surface.  The
    # manifest retains all exports for auditability, including wrappers and
    # compatibility-only helpers that must not be suggested by retrieval.
    cards = [_tool_card(tool, snapshot_id) for tool in tools if tool["roles"]]
    return manifest, cards


def _atomic_write(path: Path, content: str) -> None:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return
        raise FileExistsError(
            f"Refusing to overwrite a different immutable catalog artifact: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def write_catalog(repo_root: Path, output_dir: Path) -> dict[str, Path]:
    """Build and write immutable manifest, cards, digest, and collection spec."""

    manifest, cards = build_catalog(repo_root)
    manifest_text = _canonical_json(manifest)
    digest = _sha256_bytes(manifest_text.encode("utf-8"))
    cards_text = "".join(
        json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n" for card in cards
    )
    collection_spec = {
        "catalog_format": CATALOG_FORMAT,
        "snapshot_id": manifest["snapshot_id"],
        "manifest_sha256": digest,
        "source_records": "tool_cards.ndjson",
        "suggested_collection_name": f"ntl_gpt_runtime_tools_{manifest['snapshot_id'].replace('-', '_')}",
        "status": "not_created",
        "priority": "low_priority_supplement",
        "binding_requirements": [
            "Create a new collection only; never reuse or mutate a legacy collection.",
            "Store this snapshot_id and manifest_sha256 with the collection metadata.",
            "Bind the collection only after its snapshot ID matches the runtime snapshot used by the graph.",
            "Query it only after active role Skills and the current role allowlist have been considered.",
            "At invocation time, re-check the live registered tool name and argument schema.",
        ],
    }
    paths = {
        "manifest": output_dir / "manifest.json",
        "cards": output_dir / "tool_cards.ndjson",
        "digest": output_dir / "manifest.sha256",
        "collection_spec": output_dir / "collection_spec.json",
    }
    _atomic_write(paths["manifest"], manifest_text)
    _atomic_write(paths["cards"], cards_text)
    _atomic_write(paths["digest"], digest + "\n")
    _atomic_write(paths["collection_spec"], _canonical_json(collection_spec))
    return paths


def _default_output_dir(repo_root: Path, snapshot_id: str) -> Path:
    return repo_root / "RAG" / "runtime_tool_catalog" / "v1" / "snapshots" / snapshot_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="NTL-GPT repository root (defaults to this builder's repository).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Immutable output directory. Defaults to v1/snapshots/<snapshot-id>.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build in memory and print the deterministic snapshot ID without writing files.",
    )
    arguments = parser.parse_args(argv)
    manifest, _ = build_catalog(arguments.repo_root)
    if arguments.check:
        print(manifest["snapshot_id"])
        return 0
    output_dir = arguments.output_dir or _default_output_dir(arguments.repo_root.resolve(), manifest["snapshot_id"])
    paths = write_catalog(arguments.repo_root, output_dir)
    print(json.dumps({key: value.as_posix() for key, value in paths.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
