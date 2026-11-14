# Where orchestration modules moved

Each row is a module that moved into `specy_road/orchestration/` with `git mv` and keeps its module
name. A roadmap leaf that names one of these paths in its touch zones or acceptance reads the new
path from this table.

## Roster, model profiles, harness facts, orchestrate plan and assign

| Before | After |
| --- | --- |
| `specy_road/roster_generate.py` | `specy_road/orchestration/roster_generate.py` |
| `specy_road/roster_local.py` | `specy_road/orchestration/roster_local.py` |
| `specy_road/roster_profile_check.py` | `specy_road/orchestration/roster_profile_check.py` |
| `specy_road/model_names.py` | `specy_road/orchestration/model_names.py` |
| `specy_road/model_profiles.py` | `specy_road/orchestration/model_profiles.py` |
| `specy_road/harness_facts.py` | `specy_road/orchestration/harness/harness_facts.py` |
| `specy_road/harness_binary.py` | `specy_road/orchestration/harness/harness_binary.py` |
| `specy_road/orchestrate_assign.py` | `specy_road/orchestration/orchestrate_assign.py` |
| `specy_road/orchestrate_plan.py` | `specy_road/orchestration/orchestrate_plan.py` |

## Role-prompt library

| Before | After |
| --- | --- |
| `specy_road/role_prompt_cli.py` | `specy_road/orchestration/role_prompt_cli.py` |
| `specy_road/role_prompt_rework.py` | `specy_road/orchestration/role_prompt_rework.py` |
| `specy_road/bundled_scripts/role_prompt_rca.py` | `specy_road/orchestration/role_prompt_rca.py` |

## Folded

| Before | After |
| --- | --- |
| `specy_road/bundled_scripts/role_prompt_stream.py` | folded into `specy_road/bundled_scripts/role_prompt.py` |

## Not moved

- `specy_road/bundled_scripts/role_prompt.py`, `models_cli.py` and `orchestrate_cli.py` are the
  `prompt`, `models` and `orchestrate` command entry points; `specy_road.cli` runs each from
  `bundled_scripts/`, so they stay there.
- `specy_road/harness_instruction_files.py` lists the instruction files each harness reads for the
  `validate` context meter (agent-file management), not orchestration.

