"""Surgical ``override_limits`` YAML appends for file-limits baselines (no re-serialisation)."""

from __future__ import annotations

import copy
import re

import yaml
from yaml import compose
from yaml.nodes import MappingNode, SequenceNode

_TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][\w.-]*\s*:")
_TRAILING_POLICY_KEYS = ("roadmap_manifest_max_lines", "roadmap_json_chunk_max_lines", "hard_alerts")


def yaml_quoted_scalar(value: str) -> str:
    return yaml.dump(value, default_style='"', width=2**16).strip()


def _override_limits_sequence(text: str) -> SequenceNode | None:
    try:
        root = compose(text)
    except yaml.YAMLError:
        return None
    if not isinstance(root, MappingNode):
        return None
    for key_node, val_node in root.value:
        if key_node.value == "override_limits" and isinstance(val_node, SequenceNode):
            return val_node
    return None


def _flow_sequence_close_bracket_index(seq_node: SequenceNode) -> int:
    """Index of the closing ``]`` for a flow-style sequence (composer end mark)."""
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
    new_rows = after.get("override_limits") or []
    if len(new_rows) != len(old_rows) + new_entries:
        return False
    return new_rows[: len(old_rows)] == old_rows


def _ends_override_limits_section(line: str) -> bool:
    if not line.strip():
        return False
    if line[0] in " \t":
        return False
    if line.lstrip().startswith("#"):
        return False
    return _TOP_LEVEL_KEY.match(line) is not None


def _override_limits_header_index(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if re.match(r"^override_limits\s*:", line):
            return i
    return None


def _insert_index_for_new_override_rows(lines: list[str]) -> tuple[int, bool]:
    header = _override_limits_header_index(lines)
    if header is not None:
        insert_at = len(lines)
        for i in range(header + 1, len(lines)):
            if _ends_override_limits_section(lines[i]):
                insert_at = i
                break
        return insert_at, False
    for i, line in enumerate(lines):
        key = line.split(":", 1)[0].strip()
        if key in _TRAILING_POLICY_KEYS:
            return i, True
    return len(lines), True


def _loads_file_limits_mapping(text: str) -> dict | None:
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return cfg if isinstance(cfg, dict) else None


def append_baseline_yaml_text(existing_text: str, block: str, *, cfg: dict | None = None) -> str:
    if not block.strip():
        return existing_text
    before_cfg = copy.deepcopy(cfg if cfg is not None else _loads_file_limits_mapping(existing_text) or {})
    block_body = block.rstrip("\n")
    new_count = _count_new_baseline_entries(block)
    seq = _override_limits_sequence(existing_text)
    if seq is None:
        lines = existing_text.splitlines()
        if _override_limits_header_index(lines) is not None:
            raise ValueError(
                "constraints/file-limits.yaml: override_limits is present but not a composable "
                "sequence; rewrite override_limits in block style and retry"
            )
        insert_at, need_header = _insert_index_for_new_override_rows(lines)
        new_lines = lines[:insert_at]
        if need_header:
            new_lines.append("override_limits:")
        new_lines.extend(block_body.splitlines())
        new_lines.extend(lines[insert_at:])
        result = "\n".join(new_lines)
    elif seq.flow_style is True:
        close = _flow_sequence_close_bracket_index(seq)
        flow_snip = _flow_baseline_snippet(block_body)
        insertion = flow_snip if not seq.value else f", {flow_snip}"
        result = existing_text[:close] + insertion + existing_text[close:]
    else:
        idx = seq.end_mark.index
        prefix = "" if idx > 0 and existing_text[idx - 1] == "\n" else "\n"
        result = existing_text[:idx] + prefix + block_body + "\n" + existing_text[idx:]
    if existing_text.endswith("\n") or not result.endswith("\n"):
        result += "\n"
    after_cfg = _loads_file_limits_mapping(result)
    if after_cfg is None or not _verify_append_preserves_parsed(before_cfg, after_cfg, new_count):
        raise ValueError("baseline append would change existing override_limits entries")
    return result
