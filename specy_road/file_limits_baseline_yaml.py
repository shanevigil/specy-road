"""Surgical ``override_limits`` YAML appends for file-limits baselines (no re-serialisation)."""

from __future__ import annotations

import copy
import json
import re

import yaml
from yaml import compose
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

_TRAILING_POLICY_KEYS = ("roadmap_manifest_max_lines", "roadmap_json_chunk_max_lines", "hard_alerts")


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


def _flow_sequence_close_bracket_index(seq_node: SequenceNode) -> int:
    return seq_node.end_mark.index - 1


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


def _loads_file_limits_mapping(text: str) -> dict | None:
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return cfg if isinstance(cfg, dict) else None


def _line_start_index(text: str, index: int) -> int:
    line_start = text.rfind("\n", 0, index)
    return 0 if line_start == -1 else line_start + 1


def _insert_index_for_new_override_section(text: str, root: MappingNode) -> int:
    for key_node, _ in root.value:
        if key_node.value in _TRAILING_POLICY_KEYS:
            return _line_start_index(text, key_node.start_mark.index)
    return root.end_mark.index


def _insert_new_override_limits_section(text: str, root: MappingNode, block_body: str) -> str:
    at = _insert_index_for_new_override_section(text, root)
    prefix = text[:at]
    suffix = text[at:]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    chunk = "override_limits:\n" + block_body + "\n"
    return prefix + chunk + suffix


def _scalar_is_empty_override(val_node: ScalarNode) -> bool:
    if val_node.value is None:
        return True
    if val_node.value == "":
        return True
    return str(val_node.value).lower() == "null"


def _replace_empty_override_value(text: str, val_node: yaml.nodes.Node, block_body: str) -> str:
    start = val_node.start_mark.index
    end = val_node.end_mark.index
    insertion = "\n" + block_body
    if start == end and start > 0 and text[start - 1] != "\n":
        insertion = "\n" + block_body
    return text[:start] + insertion + text[end:]


def _append_to_existing_override_limits(existing_text: str, val_node: yaml.nodes.Node, block_body: str) -> str:
    if isinstance(val_node, SequenceNode):
        if val_node.flow_style is True:
            close = _flow_sequence_close_bracket_index(val_node)
            flow_snip = _flow_baseline_snippet(block_body)
            insertion = flow_snip if not val_node.value else f", {flow_snip}"
            return existing_text[:close] + insertion + existing_text[close:]
        if val_node.value:
            idx = val_node.end_mark.index
            prefix = "" if idx > 0 and existing_text[idx - 1] == "\n" else "\n"
            return existing_text[:idx] + prefix + block_body + "\n" + existing_text[idx:]
        return _replace_empty_override_value(existing_text, val_node, block_body)
    if isinstance(val_node, MappingNode):
        if val_node.value:
            raise ValueError(
                "constraints/file-limits.yaml: override_limits mapping is not empty; "
                "rewrite override_limits as a sequence in block style and retry"
            )
        return _replace_empty_override_value(existing_text, val_node, block_body)
    if isinstance(val_node, ScalarNode):
        if not _scalar_is_empty_override(val_node):
            raise ValueError(
                "constraints/file-limits.yaml: override_limits is not a sequence; "
                "rewrite override_limits in block style and retry"
            )
        return _replace_empty_override_value(existing_text, val_node, block_body)
    raise ValueError(
        "constraints/file-limits.yaml: override_limits has an unsupported shape; "
        "rewrite override_limits as a block sequence and retry"
    )


def append_baseline_yaml_text(existing_text: str, block: str, *, cfg: dict | None = None) -> str:
    if not block.strip():
        return existing_text
    root = _compose_mapping(existing_text)
    if root is None:
        raise ValueError(
            "constraints/file-limits.yaml: could not compose YAML; fix syntax or use block-style override_limits"
        )
    before_cfg = copy.deepcopy(cfg if cfg is not None else _loads_file_limits_mapping(existing_text) or {})
    block_body = block.rstrip("\n")
    new_count = _count_new_baseline_entries(block)
    nodes = _override_limits_nodes(root)
    if nodes is None:
        result = _insert_new_override_limits_section(existing_text, root, block_body)
    else:
        _key_node, val_node = nodes
        result = _append_to_existing_override_limits(existing_text, val_node, block_body)
    if existing_text.endswith("\n") or not result.endswith("\n"):
        result += "\n"
    after_cfg = _loads_file_limits_mapping(result)
    if after_cfg is None or not _verify_append_preserves_parsed(before_cfg, after_cfg, new_count):
        raise ValueError("baseline append would change existing override_limits entries")
    return result
