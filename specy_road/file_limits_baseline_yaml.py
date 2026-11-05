"""Surgical ``override_limits`` YAML appends for file-limits baselines (no re-serialisation)."""

from __future__ import annotations

import copy
import json
import re

import yaml
from yaml import compose
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

_TRAILING_POLICY_KEYS = ("roadmap_manifest_max_lines", "roadmap_json_chunk_max_lines", "hard_alerts")
_APPEND_REFUSE = (
    "constraints/file-limits.yaml: could not append baseline; "
    "fix override_limits or use a block-style sequence"
)


def yaml_quoted_scalar(value: str) -> str:
    return json.dumps(value)


def _compose_mapping(text: str) -> MappingNode | None:
    try:
        root = compose(text)
    except yaml.YAMLError:
        return None
    return root if isinstance(root, MappingNode) else None


def _override_limits_nodes(root: MappingNode) -> tuple[yaml.nodes.Node, yaml.nodes.Node] | None:
    for key_node, val_node in root.value:
        if key_node.value == "override_limits":
            return key_node, val_node
    return None


def _loads_file_limits_mapping(text: str) -> dict | None:
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return cfg if isinstance(cfg, dict) else None


def _count_new_baseline_entries(block: str) -> int:
    return sum(1 for line in block.splitlines() if re.match(r"\s*- name: baseline-", line))


def _verify_append_preserves_parsed(before: dict, after: dict, new_entries: int) -> bool:
    for key, val in before.items():
        if key != "override_limits" and after.get(key) != val:
            return False
    old_rows = before.get("override_limits") or []
    if not isinstance(old_rows, list):
        old_rows = []
    new_rows = after.get("override_limits") or []
    if not isinstance(new_rows, list):
        return False
    if len(new_rows) != len(old_rows) + new_entries:
        return False
    return new_rows[: len(old_rows)] == old_rows


def _flow_baseline_snippet(block_body: str) -> str:
    fragment = yaml.safe_load("override_limits:\n" + block_body) or {}
    parts: list[str] = []
    for ov in fragment.get("override_limits") or []:
        if not isinstance(ov, dict):
            continue
        name = ov.get("name")
        globs = ov.get("file_globs") or []
        gparts = ", ".join(yaml_quoted_scalar(str(g)) for g in globs)
        fields = [f"name: {name}", f"file_globs: [{gparts}]", f"max_lines_per_file: {ov['max_lines_per_file']}"]
        if ov.get("max_lines_per_function"):
            fields.append(f"max_lines_per_function: {ov['max_lines_per_function']}")
        parts.append("{" + ", ".join(fields) + "}")
    return ", ".join(parts)


def _line_start_index(text: str, index: int) -> int:
    line_start = text.rfind("\n", 0, index)
    return 0 if line_start == -1 else line_start + 1


def _insert_new_override_limits_section(text: str, root: MappingNode, block_body: str) -> str:
    for key_node, _ in root.value:
        if key_node.value in _TRAILING_POLICY_KEYS:
            at = _line_start_index(text, key_node.start_mark.index)
            break
    else:
        at = root.end_mark.index
    prefix = text[:at]
    suffix = text[at:]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + "override_limits:\n" + block_body + "\n" + suffix


def _replace_value_with_block(text: str, val_node: yaml.nodes.Node, block_body: str) -> str:
    start = val_node.start_mark.index
    end = val_node.end_mark.index
    return text[:start] + "\n" + block_body + text[end:]


def _splice_flow_sequence(text: str, seq_node: SequenceNode, block_body: str) -> str:
    close = seq_node.end_mark.index - 1
    flow_snip = _flow_baseline_snippet(block_body)
    insertion = flow_snip if not seq_node.value else f", {flow_snip}"
    return text[:close] + insertion + text[close:]


def _splice_block_sequence(text: str, seq_node: SequenceNode, block_body: str) -> str:
    if not seq_node.value:
        return _replace_value_with_block(text, seq_node, block_body)
    idx = seq_node.end_mark.index
    prefix = "" if idx > 0 and text[idx - 1] == "\n" else "\n"
    return text[:idx] + prefix + block_body + "\n" + text[idx:]


def _scalar_is_empty_override(val_node: ScalarNode) -> bool:
    if val_node.value is None or val_node.value == "":
        return True
    return str(val_node.value).lower() == "null"


def _splice_existing_override_limits(text: str, val_node: yaml.nodes.Node, block_body: str) -> str:
    if isinstance(val_node, SequenceNode):
        if val_node.flow_style is True:
            return _splice_flow_sequence(text, val_node, block_body)
        return _splice_block_sequence(text, val_node, block_body)
    if isinstance(val_node, MappingNode):
        if val_node.value:
            raise ValueError(_APPEND_REFUSE)
        return _replace_value_with_block(text, val_node, block_body)
    if isinstance(val_node, ScalarNode):
        if not _scalar_is_empty_override(val_node):
            raise ValueError(_APPEND_REFUSE)
        return _replace_value_with_block(text, val_node, block_body)
    raise ValueError(_APPEND_REFUSE)


def _splice_baseline_block(text: str, root: MappingNode, block_body: str) -> str:
    nodes = _override_limits_nodes(root)
    if nodes is None:
        return _insert_new_override_limits_section(text, root, block_body)
    _key_node, val_node = nodes
    return _splice_existing_override_limits(text, val_node, block_body)


def _ensure_trailing_newline(existing_text: str, result: str) -> str:
    if existing_text.endswith("\n") or not result.endswith("\n"):
        return result + "\n"
    return result


def _verify_appended_text(before_cfg: dict, result: str, new_count: int) -> None:
    after_cfg = _loads_file_limits_mapping(result)
    if after_cfg is None or not _verify_append_preserves_parsed(before_cfg, after_cfg, new_count):
        raise ValueError("baseline append would change existing override_limits entries")


def append_baseline_yaml_text(existing_text: str, block: str, *, cfg: dict | None = None) -> str:
    if not block.strip():
        return existing_text
    root = _compose_mapping(existing_text)
    if root is None:
        raise ValueError(_APPEND_REFUSE)
    before_cfg = copy.deepcopy(cfg if cfg is not None else _loads_file_limits_mapping(existing_text) or {})
    block_body = block.rstrip("\n")
    new_count = _count_new_baseline_entries(block)
    result = _ensure_trailing_newline(existing_text, _splice_baseline_block(existing_text, root, block_body))
    _verify_appended_text(before_cfg, result, new_count)
    return result
