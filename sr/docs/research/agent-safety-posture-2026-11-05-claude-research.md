<!-- Claude Research run of sr/research/prompts/agent-safety-posture.md (v2), pasted by the maintainer 2026-11-05. Verbatim. -->
# Agent safety and governance posture for a spec-driven agent toolkit: research findings (November 2026)

Keep the prior runs' architecture: a posture contract stored as data, an advisor prompt, human confirmation, and a deterministic `doctor`. Two changes are needed. First, harness sandboxes are a weaker boundary than both runs assumed. All three harnesses have shipped sandbox escapes in 2026, and the default read policies of Claude Code and Codex still expose `~/.ssh` and `~/.aws`.\[1\]\[2\]\[3\]\[4\]\[5\] Second, "delegate to the harness" has to become "compile to the harness, then verify from inside the executor." The most useful thing to build first is a canary-probe `doctor` that tests the boundary from inside the executor instead of reading config. Signed reviews should be neither globally ON nor OFF. Make them a recommended-ON default only when unattended executors run at internal posture or above, and count them only when a verifier outside the executor's reach checks them.

## TL;DR

- **Harness settings are necessary but not sufficient.** Compile one policy into Claude Code permissions plus sandbox, Codex sandbox plus execpolicy rules, and Cursor `cli-config.json` plus `sandbox.json` plus hooks. Then verify the result with probes run inside the executor. Require an outer OS boundary (separate user, container or VM) for unattended production and sensitive work. Every harness had sandbox-escape CVEs in 2025–2026, and the config-file-injection class recurs across all three.\[1\]\[3\]\[6\]
- **Signed reviews: conditional default.** Recommend them ON when executors run unattended at internal posture or above, with keys on a FIDO2 token (touch + PIN) or under a separate OS user. Verification must happen on the forge (branch protection plus a required check), not in the executor's own process. SLSA v1.2 and OpenSSF Scorecard reward platform-enforced review and do not require signed review records.\[7\]\[8\] A small team pays little extra for signing only when the threat is a forging executor.
- **Build the core in-house; adopt nothing as a mandatory dependency.** The in-house core is the stdlib posture contract, the harness compiler, `doctor`, and artifact checks on Terraform plan JSON and migrations. Detect and use Squawk, gitleaks, bubblewrap, devcontainers and Anthropic's sandbox-runtime if installed. Recommend gVisor, Firecracker, pg_safeupdate and TruffleHog to the platform owner. LLM-based guardrails (LlamaFirewall, Invariant) are incompatible as toolkit components.\[9\]\[10\]

## Executive summary and recommended first slice

The incident pattern the prior runs found still holds: credential reach, auto-approve, and backups inside the blast radius. The 2026 CVE record adds a second pattern. Sandboxes are being escaped through files the agent writes that something trusted runs later.\[3\] Examples are harness settings files and hooks, git hooks and fsmonitor, shell startup files, Python virtualenv interpreters, and symlinks the unsandboxed parent process follows.\[2\]\[11\]\[12\]\[13\] A toolkit that drives harnesses unattended in git worktrees is exposed to exactly this class. The toolkit's own files (worktrees, the review roster, the record writer, harness configs) must therefore be treated as part of the trust boundary.

Recommended first slice:

1. **Harness compiler plus version floor.** Write one YAML policy that emits Claude Code `settings.json`, a Codex config or permission profile plus `.rules`, and Cursor `cli-config.json`, `sandbox.json` and `hooks.json`. Each output denies credential paths at both the tool layer and the sandbox layer. `doctor` refuses to report "configured" below known-fixed versions: Claude Code ≥ 2.1.179, Codex ≥ 0.39.0, and Cursor ≥ 3.1.2 (desktop) or a CLI build at or after the April 2026 headless `sandbox.json` fix.\[2\]\[14\]\[15\]\[16\]
2. **Executor-side canary probe.** This is a generated task the executor runs through its normal tool path. It tries to read a canary file placed in a fake `~/.ssh`, write outside the worktree, write to the harness config directory, and connect to a local listener. The toolkit then checks the results. This is the only way to move a boundary from "configured" to "verified."
3. **Protect the steering files.** Make harness config, hooks, `.git/hooks`, and the toolkit's roster and record writer unwritable by the executor. Keep them outside the worktree, read-only, or owned by another user. Then diff them before and after every run. This closes the CVE-2026-25725, CVE-2026-48124 and CVE-2025-61260 class and the prior replay's roster-forging path.\[3\]\[6\]\[11\]
4. **Conditional signed reviews.** Use git SSH signing with an `ed25519-sk` key (touch + PIN) or a separate-OS-user signer.\[17\]\[18\] Branch protection with a required status check verifies the signatures on the forge. Signing is a recommended default only when unattended executors are present at internal posture or above.
5. **Artifact checks instead of more command patterns.** Use a stdlib parser of `terraform show -json` output to flag `delete` actions, run Squawk on SQL migrations if installed, and run a stdlib check for unbounded `UPDATE`/`DELETE` in migration files. Recommend server-side force-push and deletion protection to the platform owner.

## Capability matrix: compiling one policy to each harness

Versions: Claude Code checked against v2.1.280 (September 22, 2026), via a third-party summary of the changelog.\[5\] Codex CLI is the 2026 documentation. Cursor agent CLI is the 2026 documentation.

| Capability | Claude Code | Codex CLI | Cursor agent CLI | Is an OS-level boundary needed anyway? |
|---|---|---|---|---|
| Shell command allow/deny | `permissions.allow/ask/deny` with `Bash(...)` patterns. Deny rules block "in every mode, including bypassPermissions."\[5\]\[19\] | `.rules` `prefix_rule` with `allow` / `prompt` / `forbidden`; the strictest match wins. Marked "experimental." Rules decide whether a command may run *outside* the sandbox.\[20\] | `permissions.allow/deny` tokens such as `Shell(rm)` in `~/.cursor/cli-config.json` or `.cursor/cli.json`. Deny wins.\[21\]\[22\] Cursor calls its allowlist "best-effort — bypasses are possible."\[23\] | Yes. All three are bypassable by wrappers, scripts, env poisoning and builtins.\[24\]\[25\] |
| File-tool read deny | `Read(...)` deny rules cover the built-in Read tool only, not `cat` in Bash.\[26\] | `sandbox_mode` alone allows reading everywhere. Per-path read deny exists only through permission profiles (`default_permissions`, beta) or admin `requirements.toml` `deny_read`.\[4\]\[27\] | `Read(...)` deny tokens in `cli-config.json`. | Yes, for credential stores. |
| Sandbox read deny for shell (`~/.ssh`, `~/.aws`) | The sandbox is opt-in, and its default read policy *allows* `~/.ssh` and `~/.aws`.\[5\] You must add `sandbox.filesystem.denyRead` (and mirror it in `permissions.deny`). `permissions.blockReadsOutsideWorkingDirectories` exists from v2.1.257.\[5\] | Seatbelt profile is `(deny default)` plus `(allow file-read*)`. Linux bubblewrap uses `--ro-bind / /`. Reads are allowed unless a deny-read profile is set.\[28\]\[29\]\[30\] | Sandbox is Seatbelt on macOS, Landlock + seccomp on Linux kernel ≥ 6.2 with a bubblewrap fallback, and Windows only via WSL2.\[31\]\[32\] Default read scope outside the workspace is inconsistently documented by third parties, so verify with a canary. | Yes. Verify with a canary every time. |
| Write scope | `Edit(...)` rules plus sandbox `allowWrite`. Bypass mode skips protected-path prompts (`.git`, `.claude`, `.bashrc`…) since v2.1.126.\[5\] | `workspace-write` limits writes to cwd plus `writable_roots`.\[33\] | Workspace read/write. `.cursor/*.json`, `.vscode/**`, `.git/hooks/**` and `.cursorignore` are always write-blocked.\[32\]\[34\] | Recommended for production and above. |
| Network | Sandbox egress goes through a proxy allowlist. | Off by default in `workspace-write`; enabled with `sandbox_workspace_write.network_access = true`.\[35\]\[36\] | Denied by default.\[21\] The `sandbox.json` `networkPolicy` sets it. The "Allow All" mode ignores `sandbox.json`.\[34\]\[37\] | Only for sensitive work. |
| Pre-execution hook | `PreToolUse` hook; exit code 2 blocks in any mode.\[5\] | No equivalent general pre-tool hook was verified in this research; use `.rules`. | `beforeShellExecution`, `beforeMCPExecution`, `preToolUse` (`ask` is accepted but not enforced on `preToolUse`); exit 2 means deny.\[32\]\[38\] | No. Hooks are a good place for the toolkit's guard. |
| Unattended mode | `-p` with `--permission-prompts none` (v2.1.259) turns any would-be prompt into a denial. Bypass refuses root unless `IS_SANDBOX=1` (undocumented).\[5\] | `codex exec` is read-only by default and cannot ask for approval.\[39\]\[40\] | `-p --force` allows everything not denied. Headless `-p` was reported to ignore `sandbox.json` until roughly CLI v2026.04.29.\[14\] | — |
| Escape hatch to disable | `sandbox.allowUnsandboxedCommands` must be `false`. Otherwise failing commands retry unsandboxed, with no prompt in bypass mode.\[19\] | `danger-full-access`.\[41\] | Sandboxed commands that fail may rerun outside the sandbox after classifier review.\[42\] | — |
| Tamper-resistant layer | `managed-settings.json`; since v2.1.257 project settings cannot enable bypass.\[5\] | `/etc/codex/requirements.toml`.\[43\] | Enterprise MDM, team hooks, and `permissions.json`.\[32\]\[44\] | Only available on managed machines. |
| Config gotchas for the compiler | Deny entries merge across scopes and cannot be removed.\[5\] | `approval_policy = "untrusted"` is retired and "can prevent either client from starting." Setting `sandbox_mode` makes Codex ignore `default_permissions` (third-party claim). Profiles moved to separate files in 0.134.0 (third-party claim).\[40\]\[45\]\[46\] | No documented per-run switch to disable subagents, plugins or hooks in CLI workers (forum feature request).\[47\] | — |

**Known bypasses and escapes, 2025–2026 (minimum fixed versions)**
- **Claude Code**
  - CVE-2026-25725: a missing `settings.json` let the sandbox write persistent hooks. Fixed in 2.1.2; advisory February 2026.\[11\]\[48\]
  - CVE-2026-39861: symlink following let a write land outside the workspace. CVSS 10.0, fixed in 2.1.64; GHSA-vp62-r36r-9xqp, April 21, 2026.\[12\]\[49\]
  - CVE-2026-55607: git-worktree path confusion plus fsmonitor and `.zshenv` led to unsandboxed execution. Fixed in 2.1.163; GitLab advisory dated July 24, 2026.\[50\] The PoC reportedly worked "with sandbox enabled, Bash not auto-approved." That claim comes from a secondary blog and is weak.\[51\]
  - CVE-2026-25724: deny-rule bypass through symlinks (low).\[15\]
  - CVE-2026-86063: plugin hash-pin bypass, fixed in 2.1.179, October 15, 2026. The source is an aggregator and is weak.\[15\]
- **Codex**
  - CVE-2025-59532: a model-generated cwd became the writable root. Fixed in 0.39.0; GHSA-w5fx-fh39-j5rw, September 2025.\[16\]\[52\]
  - CVE-2025-61260: a repo `.env` set `CODEX_HOME=./.codex`, and that config ran MCP commands. Reported December 2025 via GBHackers (news, secondary).\[6\]
- **Cursor**
  - CVE-2026-22708: shell builtins (`export`, `typeset`) bypassed an empty allowlist and poisoned `PAGER`. Fixed in 2.3; Pillar Security, January 14, 2026 (vendor research).\[24\]\[25\]\[42\]
  - CVE-2026-50548 and CVE-2026-50549: agent-controlled `working_directory` and a symlink canonicalization fallback. Fixed in 3.0; Cato Networks via CSO Online, mid-2026.\[53\]\[54\]
  - CVE-2026-48124: a Claude-hooks config file ran outside the sandbox. Fixed in 3.0, per Techzine.\[3\]
  - CVE-2026-73217: an agent-modified venv Python was run by the editor's Python extension on macOS. Fixed in 3.1.2, August 2026; SentinelOne database.\[2\]
- **Cross-harness:** a privileged Docker daemon reachable from inside the sandbox allowed host execution in Cursor, Codex and Gemini CLI (Techzine, 2026).\[3\]

**What this means for the compiler.** Every harness splits enforcement between a tool-permission layer and a shell-sandbox layer, and they do not cover each other:
- Claude Code: `Read()` deny does not stop `cat`.\[26\]
- Claude Code: `sandbox.denyRead` does not stop the Read tool.\[55\]
- Codex: execpolicy covers commands only, not file tools or MCP.\[20\]

The compiler therefore has to emit every credential-path deny twice, and `doctor` has to probe both paths. Three things need an OS boundary regardless of harness config:
- Credential stores the executor's user can read.
- Windows-native runs.
- Any long-lived host service reachable from the sandbox: the Docker socket, ssh-agent, and the gpg-agent socket.

## Scored buy-vs-build table

Weights: fit 3, coverage 2, supply-chain 2, license 2, maturity 1, dependency weight 1, offline 1, integration 1. Maximum 39. Licenses marked † come from background knowledge and were not re-verified in this run; check before bundling anything.

| Candidate | Fit ×3 | Cov ×2 | Supply ×2 | Lic ×2 | Mat | Dep | Off | Int | Total | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| In-house: posture contract, harness compiler, `doctor`, probes, artifact checks (stdlib) | 3 | 2 | 3 | 3 | 1 | 3 | 3 | 3 | **35** | **Build in-house** |
| Squawk (Postgres migration linter; Rust; `pip install squawk-cli`)\[56\]\[57\] | 3 | 2 | 2 | 3 | 3 | 2 | 3 | 3 | **34** | **Integrate optionally** |
| bubblewrap (LGPL†, distro binary) | 3 | 2 | 3 | 2 | 3 | 2 | 3 | 2 | **33** | **Integrate optionally** (detect it; never bundle) |
| gitleaks (MIT, Go)\[58\] | 3 | 2 | 2 | 3 | 2 | 1 | 3 | 3 | **32** | **Integrate optionally** |
| gVisor (Apache-2.0†) | 2 | 2 | 3 | 3 | 3 | 1 | 3 | 1 | **30** | **Recommend only** (detect `runsc` to verify) |
| OPA/Conftest (Apache-2.0†, CNCF) | 2 | 1 | 3 | 3 | 3 | 1 | 3 | 2 | **29** | **Integrate optionally** for Terraform-plan policy. The stdlib check covers the basic case. |
| devcontainers CLI (MIT†, Node) | 2 | 2 | 2 | 3 | 3 | 1 | 2 | 2 | **28** | **Integrate optionally** |
| Anthropic sandbox-runtime `srt` (Apache-2.0, npm, 0.0.x "research preview")\[59\]\[60\]\[61\] | 2 | 2 | 2 | 3 | 1 | 1 | 3 | 2 | **27** | **Integrate optionally**: an outer wrapper for harness processes that lack read-deny |
| Firecracker (Apache-2.0†; Linux + KVM only) | 1 | 3 | 3 | 3 | 3 | 0 | 2 | 0 | **26** | **Recommend only** |
| TruffleHog (AGPL-3.0; live verification uses the network)\[58\]\[62\] | 2 | 3 | 2 | 1 | 3 | 1 | 1 | 2 | **25** | **Recommend only** (CI, run with `--no-verification` offline) |
| pg_safeupdate (ISC; Postgres server extension)\[63\] | 2 | 1 | 2 | 3 | 2 | 1 | 3 | 0 | **24** | **Recommend only** (to the platform owner) |
| container-use (Dagger; Apache-2.0; Go; MCP)\[64\] | 1 | 2 | 2 | 3 | 1 | 0 | 2 | 1 | **21** | **Recommend only** |
| nono (Landlock/Seatbelt sandbox with Sigstore-signed instruction bundles; weakly sourced)\[65\] | 2 | 2 | 1 | 1 | 1 | 1 | 3 | 2 | **21** | **Recommend only** pending verification |
| Docker Sandboxes (microVM per agent; Docker Desktop feature; weakly sourced)\[66\] | 1 | 3 | 2 | 1 | 1 | 0 | 1 | 1 | **18** | **Recommend only** |
| LlamaFirewall (Meta; PromptGuard model under the Llama Community License; AlignmentCheck needs an LLM)\[67\]\[68\] | 0 | 2 | 2 | 1 | 2 | 0 | 1 | 1 | **14** | **Incompatible** (constraint 1) |
| Invariant Guardrails (acquired by Snyk 2025-06-24; LLM/proxy-based)\[9\]\[69\] | 0 | 2 | 1 | 1 | 1 | 0 | 1 | 1 | **11** | **Incompatible** (constraints 1 and 4) |

Notes on scores:
- **Squawk.** Relicensed from GPL-3.0 to Apache-2.0 OR MIT in v2.12.0 (2025-06-09, changelog entry "Relicensed: gpl3 -> apache or mit (#534)").\[70\] The latest release is v2.70.0 (2026-10-15).\[70\] Older PyPI listings still show GPL-3.0.\[71\] Pin to ≥ 2.12.0 and check the license file of the pinned version.
- **gitleaks.** The gitleaks README on GitHub states: "Gitleaks is feature complete. I'm not merging new features into Gitleaks. Future releases will be security patches only. I'm shifting my focus to Betterleaks" (latest v8.30.1, 2026-03-21). Its original author now maintains Betterleaks (MIT). Watch whether detection rules go stale.
- **TruffleHog.** AGPL-3.0 rules out bundling. Its strength, live credential verification, sends found secrets to provider APIs.\[72\] That conflicts with offline use and may itself be undesirable.
- **pg_safeupdate.** v1.7 (2026-07-13) supports PostgreSQL 19.\[73\] The trivial `WHERE 1=1` bypass shows it guards against accidents, not adversaries.\[63\] It is a database setting, so it belongs to the platform owner.
- **container-use.** One profile (tomrochette.com, 2026-10-12; weak) reports no release since 2025-08-19 and an "experimental" badge.\[64\] It also changes the execution model, because the agent works through MCP tools instead of its own shell, which strains constraint 2.\[74\]
- **LlamaFirewall and Invariant Guardrails.** They are incompatible as toolkit components because the toolkit would have to run models. A user may still put them in front of their own harness, outside the toolkit.

## Answers to the open questions

### 1. Signed reviews by default?

**Evidence.**
- **SLSA v1.2** was approved and tagged 2025-11-24. It adds a Source track: L1 version controlled, L2 history and provenance, L3 continuous technical controls, L4 two-party review. L4 reads "changes in protected branches MUST be agreed to by two or more trusted persons prior to submission."\[8\]\[75\]\[76\]
- **SLSA's own sprint recap** (slsa.dev, April 2025) says two-party review "can be very difficult for small projects to enable" and that such projects "can advance as far as possible without adopting two-party review."\[77\]
- **SLSA ties source integrity to the platform.** L2 requires force-push blocking and immutable history. L3 requires continuous enforcement recorded in attestations.\[76\]\[78\] Neither requires signed approval records.
- **The only reference tool,** slsa-framework/source-tool, calls itself a proof of concept. This comes from a GitHub issue quoting its README, a secondary source.\[79\]
- **Secondary sources disagree on L4.** One wiki claims L4 "does not exist," which is wrong for v1.2. Another notes that the VSA `verifiedLevels` field enumerates only Source L0–L3.\[8\]\[76\] Read the spec at slsa.dev/spec/v1.2 rather than summaries.
- **OpenSSF Scorecard's Code-Review check** looks at roughly the last 30 commits for an approval, or a merger different from the committer. Scorecard's check documentation states that "Review by bots, including bots powered by artificial intelligence / machine learning (AI/ML), do not count as code review." Its Signed-Releases check looks for signature files on the last five releases. Neither checks signed review records.

**Interpretation.** The frameworks reward *platform-enforced* review (branch protection plus required approvals) and signed *artifacts*, not locally signed review records. Signing review records does something specific for this toolkit: it stops an unattended executor on the same machine from minting approvals, which the prior replay demonstrated. That threat exists only when an executor runs unattended with write access to the record store. A single developer with no unattended executors gets nothing from signing.

**Position.** Neither prior run is quite right.
- **Default:** recommend ON when posture is internal or above *and* any executor runs unattended. Otherwise OFF with a warning.
- **Sensitive posture:** recommend ON always.
- **Human confirmation:** a human confirms the default, as constraint 3 requires.
- **What counts:** signing counts toward "verified" only if verification runs where the executor cannot tamper with it. That means a required status check on the forge, or a verifier running as a different OS user. A signature checked by code the executor can edit is theater.

**Key-management patterns on one developer machine, strongest first:**
1. **FIDO2 hardware key for git SSH signing** (`ssh-keygen -t ed25519-sk -O resident -O verify-required`; Git ≥ 2.34, OpenSSH ≥ 8.2, per Yubico documentation). The private key never leaves the token, and each signature needs a physical touch plus PIN.\[17\]\[18\] An `expect` script cannot press a button. Cost: a token and a touch per approval.
2. **Separate OS user for the reviewer signer.** Linux: a `reviewer` account with its key in its own home directory. macOS: a second account. The human invokes the signer through `sudo -u reviewer` with a password prompt; there must be no NOPASSWD rule, or the executor can call it too. Also deny the executor's sandbox access to `SSH_AUTH_SOCK`.
3. **ssh-agent with per-use confirmation** (`ssh-add -c`). The agent asks through its own `SSH_ASKPASS` program, set when the agent starts, so the executor cannot swap it.\[80\] Weakness: an agent running as the same user can read an unencrypted key file unless the key is on hardware or the sandbox denies `~/.ssh`.
4. **OS keychain (macOS Keychain, libsecret).** Access-control prompts help, but other processes of the same user can request items. This is the weakest option and fine only as a convenience layer.

In every case, the harness sandbox must deny reads of the key directory *and* access to the agent socket. Otherwise the executor can sign through the agent without ever touching the key.

### 2. Compiling one policy to each harness

See the matrix. Compiler rules that follow from the evidence:
- Emit credential-path denies at both layers in every harness: Claude Code `permissions.deny Read(...)` plus `sandbox.filesystem.denyRead`; Codex deny-read permission profile; Cursor `Read()` deny plus hook.
- For Claude Code, emit `sandbox.allowUnsandboxedCommands: false` and use `--permission-prompts none` for unattended runs.
- For Codex, never emit `approval_policy = "untrusted"`. Choose between `sandbox_mode` and permission profiles deliberately, because setting `sandbox_mode` reportedly disables `default_permissions`.\[45\]\[46\]
- For Cursor, replace `--force` with `--sandbox enabled` plus explicit `permissions.allow`, and check that the network mode is not "Allow All."
- Put the toolkit's deterministic guard in hooks: Claude Code `PreToolUse` and Cursor `beforeShellExecution` / `preToolUse`. Hooks fire even in bypass modes.\[5\] They are a tripwire, not a boundary.
- Do not treat Claude Code's auto mode (an LLM classifier; Anthropic announced on August 7, 2026 that "Starting on August 14, new sessions on Pro, Max, and Team plans will run in auto mode," while it "remains opt-in for now" for Enterprise and Claude API users) or Cursor's classifier as controls in `doctor`. They are probabilistic.

### 3. Destructive-operation protection without model calls

**Command filters.** There is no published false-positive rate for agent command filters. The closest evidence is Anthropic's engineering post "How we built Claude Code auto mode" (March 25, 2026), which says of manual permission prompts that "in practice users accept 93% of them anyway." That is evidence of prompt fatigue, not filter accuracy. The bypass evidence, by contrast, is strong and recurring:
- builtins and env poisoning (CVE-2026-22708)\[25\]
- wrappers and compound scripts (Codex's own rules evaluate complex `bash -lc` scripts as one opaque string)\[20\]
- symlinks (CVE-2026-25724)\[15\]
- writing a script and running it later.

**Worth building (deterministic, stdlib, cheap):**
- **Git:** a hook-level tripwire for `push --force`/`-f`/`+refspec`, `push --delete`, `branch -D` on protected names, and `update-ref -d`. The real control is forge-side force-push and deletion protection, which is also SLSA Source L2.\[76\] Recommend that to the platform owner and have `doctor` attest it, or verify it through the forge API if a token is available.
- **Terraform/Pulumi:** check the *plan artifact*, not the command. Parse `terraform show -json` and flag `resource_changes[].change.actions` containing `delete`. For Pulumi, use `pulumi preview --json`. Conftest is optional for richer policy.
- **SQL migrations:** a stdlib scan for `DROP`, `TRUNCATE`, and `UPDATE`/`DELETE` without `WHERE` in changed migration files. Use Squawk if installed for lock and DDL hazards.
- **kubectl and cloud CLIs:** a tripwire only (`kubectl delete`, `aws … delete-*`/`terminate-*`, `gcloud … delete`, `az … delete`). A guard cannot reliably stop these, so the protection is that executors hold no production credentials.

**Belongs to platform controls:**
- database roles without DDL rights, plus pg_safeupdate\[63\]
- cloud IAM deny on delete, deletion protection, and backups in a separate account or project (the DataTalks.Club lesson)
- branch protection
- Kubernetes RBAC and admission policy.

### 4. Isolation options for a local developer (weakest/least friction → strongest)

| Option | Strength | Friction | Linux | macOS | How doctor verifies vs. attests |
|---|---|---|---|---|---|
| Harness sandbox (Seatbelt/Landlock/bwrap) | Medium; shares the kernel; 2026 escapes\[81\] | Lowest | Yes (Cursor needs kernel ≥ 6.2)\[37\] | Yes | Verify: env vars `CURSOR_SANDBOX` and `CURSOR_SANDBOX_LANDLOCK_STATUS` (`fully_enforced` vs. `bubblewrap`), plus canary probes\[31\] |
| `srt` / bubblewrap wrapping the whole harness process\[59\] | Medium; covers the harness's file tools too | Low | Yes | Yes (Seatbelt) | Verify: canary probe |
| Separate OS user for executors | Medium-high against credential theft | Low-medium | Yes | Yes | Verify: probe reports uid ≠ the human's uid |
| Devcontainer / rootless container (Podman, rootless Docker) | Medium-high; no Docker socket mounted | Medium | Yes | Through a VM (Docker Desktop, Colima) | Verify: `/.dockerenv`, cgroup, probe that the socket is absent |
| gVisor (`runsc`) | High (user-space kernel) | Medium-high | Yes | No | Verify: `dmesg` banner or runtime name |
| MicroVM (Firecracker; Docker Sandboxes)\[66\] | High | High (KVM, images) | Yes | Docker Sandboxes only (weakly sourced) | Verify: `systemd-detect-virt`, DMI; otherwise attest |
| Separate VM reached over MCP/SSH | Highest practical | High | Yes | Yes | Attest, plus a probe that host canaries are unreachable |

Realistic advice for one developer:
- **Linux:** harness sandbox plus a separate executor user, or rootless Podman, for internal work. gVisor or a VM for production and sensitive work.
- **macOS:** harness Seatbelt plus a separate user, or a Colima or Docker Desktop VM, for production and above.
- **Detection:** probes run by the toolkit's own Python process verify nothing about the executor. The probe has to run *through the executor's tool path*.

### 5. Posture model

Define posture as max(data sensitivity, autonomy, blast radius), each scored low/medium/high, and map the result to four named levels so humans can reason about it:
- **prototype:** no real data, no production credentials, attended or unattended.
- **internal:** company code, no production reach.
- **production:** deploys to, or has credentials for, production.
- **sensitive:** regulated or personal data, or keys to signing or release infrastructure.

Store the three inputs as well as the level, so `doctor` can explain itself.

Framework mapping (concrete protections):
- **OWASP Top 10 for Agentic Applications 2026** (published December 9, 2025):\[82\]\[83\]
  - ASI01 Agent Goal Hijack → advisor injection resistance; executor least agency
  - ASI02 Tool Misuse → harness deny rules and hooks
  - ASI03 Identity & Privilege Abuse → no production credentials in executor reach; reviewer keys outside reach
  - ASI04 Supply Chain → pinned harness versions; plugin and MCP pinning (cf. CVE-2026-86063)
  - ASI05 Unexpected Code Execution → OS sandbox; steering-file protection
  - ASI07 Insecure Inter-Agent Communication → signed reviews; distinct-family reviewers
  - ASI09 Human-Agent Trust Exploitation → human confirmation shows evidence, not just a verdict
- **SLSA v1.2 Source track:**
  - L2 → force-push and deletion protection
  - L3 → `doctor` records which controls were enforced, with dates
  - L4 → the two-reviewer rule, which needs two *persons*.\[8\] Model reviewers do not satisfy SLSA L4, so do not claim it.
- **NIST AI RMF** (Govern/Map/Measure/Manage) → the posture contract (Govern), the advisor's evidence map (Map), `doctor` states (Measure), and human-confirmed changes (Manage). It supplies process language, not controls.
- **CIS Benchmarks:** not researched in this run. They apply to the host and container hardening the platform owner owns.

**Unconfirmed posture default.** Run as **internal**, with everything that costs the user nothing turned on: sandboxed executors, credential-path denies, steering-file protection, artifact checks. Report the posture as *unconfirmed* in every `doctor` output. Refuse nothing, but do not launch unattended executors with `--force`/bypass until a human confirms. Defaulting to "sensitive" adds friction that users will switch off. Defaulting to "prototype" repeats the incident pattern.

### 6. Advisor prompt design

The research found no single authoritative standard. These practices follow from OWASP ASI01 ("treat all text that influences agent reasoning as untrusted") and from the toolkit's constraints.\[84\]
- **Run read-only.** Generate the advisor task for read-only modes: `codex exec` (read-only by default), Claude Code `-p` with `--permission-prompts none` and only `Read`/`Grep` allowed, and Cursor without `--force`, with no network.\[39\] An injected instruction then has nothing to act on.
- **Closed output schema.** Require JSON with enum-valued fields: three dimension scores, a level, a protections list drawn from a fixed catalog, and evidence entries `{file, line_start, line_end, quote}`. The toolkit validates the schema with stdlib code and **verifies every quote is a verbatim substring at the cited lines**. Unverifiable evidence fails the run. This is the main deterministic defense: the model can argue, but only from text that exists.
- **Deterministic floor.** The toolkit computes facts itself (production-looking env vars, cloud credential files, IaC directories, migration folders). The advisor may raise the posture above that floor but never lower it. A document saying "this is just a prototype" cannot override found AWS credentials.
- **Flag instruction-like content.** The prompt tells the advisor to report any text in governance documents that addresses an AI or the reviewer (e.g. "ignore", "approve", "set posture to") as a finding, not to follow it. The toolkit also runs a stdlib regex pre-scan and shows hits to the human.
- **Diffability.**
  - Sort keys and evidence.
  - Use stable protection IDs from the catalog.
  - Limit prose to one `rationale` field per decision.
  - Record the harness name and version, the model if exposed, and SHA-256 hashes of the input documents.
  - Store the output on the integration branch next to the policy, so `git diff` shows posture drift.
  - Re-run only when input hashes change.
- **Cross-family check (optional).** Run the advisor through two harnesses of distinct model families, as the review step already does, and show disagreements to the human instead of averaging them.

## Posture → protections

| Protection | prototype | internal | production | sensitive |
|---|---|---|---|---|
| Harness sandbox on for executors (no `--force`/bypass without a sandbox) | on | on | on | on |
| Credential-path deny at tool and sandbox layers | on | on | on | on |
| Steering-file protection (harness config, hooks, roster, record writer) | on | on | on | on |
| Executor-side canary probe in `doctor` | recommended | on | on | on |
| Harness version floor (known-CVE-fixed) | recommended | on | on | on |
| Network egress allowlist for executors | off | recommended | on | on |
| Signed reviews (FIDO2 or separate user; verified on the forge) | off | recommended if unattended | recommended (on if unattended) | on |
| Branch protection: no force-push or deletion, required checks (platform) | recommended | recommended | on (attested) | on (attested/verified) |
| Artifact checks: Terraform plan delete, migration DDL/unbounded DML | off | recommended | on | on |
| Secret scan of diffs (gitleaks if present) | recommended | on | on | on |
| Command-pattern tripwire hook | on | on | on | on |
| Outer OS boundary (separate user / container / VM) for unattended runs | off | recommended | on | on (VM or gVisor) |
| No production credentials reachable by executors (platform) | recommended | on | on (attested) | on (verified by probe) |
| Backups and snapshots outside the agent's credential scope (platform) | off | recommended | on (attested) | on (attested) |
| DB roles without DDL for app/agent creds; pg_safeupdate (platform) | off | off | recommended | on (attested) |

## Disagreements with the prior runs

1. **"Delegate execution boundaries to harness settings" is too trusting as stated.** In 2025–2026 there were at least five sandbox escapes across the three harnesses, plus the config-injection class.\[1\]\[2\]\[3\]\[53\] Claude Code's and Codex's default sandboxes also leave `~/.ssh` and `~/.aws` readable.\[4\]\[5\] The delegation should stay, but `doctor` must verify the boundary from inside the executor. Production and sensitive postures need an outer boundary.
2. **The toolkit is itself in the attack path.** The CVE pattern (agent-written files run later by trusted code) matches the prior replay's forgery paths.\[3\] Protecting steering files is a first-slice item, not an afterthought.
3. **Signed reviews.** Neither "ON for internal and above" nor "OFF with a warning" fits the evidence. Make signing conditional on unattended executors, and count it only with off-machine or other-user verification. Do not market model-reviewer signatures as SLSA Source L4; it requires trusted persons.\[8\]
4. **Deterministic checks belong on artifacts more than commands.** Both runs dismissed command blocking, correctly. Plan and migration checks, however, are deterministic, cheap, low in false positives, and cover the Terraform-destroy incident class better than any filter.
5. **The Cursor sandboxed default needs a version gate.** Headless `-p` was reported to ignore `sandbox.json` before roughly CLI v2026.04.29.\[14\] Cursor also has no per-run switch to disable subagents, plugins or hooks.\[47\] Switching from `--force` to `--sandbox enabled` is necessary but not verified by itself.

## Caveats

- Sources fall into three tiers:
  - **Vendor primary:** Cursor docs, OpenAI Codex docs, Anthropic/GitHub security advisories, slsa.dev.
  - **Vendor research (interested parties):** Pillar Security, Cato Networks, Cymulate.
  - **Third-party blogs and aggregators (weak):** Morph, AgentsCamp, blakecrosley, inventivehq, howtoharden, agenticcontrolplane, cheatref, tomrochette, appsecsanta.
- Version numbers marked as third-party claims (Codex 0.134.0 and 0.149.0, Claude Code changelog entries via Morph) should be checked against the official changelogs before the compiler hard-codes them.
- Several official Codex doc pages were read only as search excerpts.
- Licenses marked † and the Docker Sandboxes and nono entries were not verified in this run.
- No quantitative false-positive data for agent command filters was found.
- Harness settings change monthly. Treat the matrix as accurate as of early November 2026 and have `doctor` read harness versions at runtime.

## Sources

1. [AI Coding Assistant CVEs 2026: Nine Records, One Pattern](https://www.stingrai.io/blog/ai-coding-assistant-cves-2026)
2. [CVE-2026-73217: Cursor IDE for macOS RCE Vulnerability](https://www.sentinelone.com/vulnerability-database/cve-2026-73217/)
3. [Researchers bypass sandbox security in Cursor, Codex, and Gemini CLI - Techzine Global](https://www.techzine.eu/news/security/143038/researchers-bypass-sandbox-security-in-cursor-codex-and-gemini-cli/)
4. [Codex Sandbox: Modes, Limits, Safe Setups (2026)](https://www.agent37.com/blog/codex-sandbox)
5. [claude --dangerously-skip-permissions (2026): What It Does, 5 Safer Setups & the New Auto Mode](https://www.morphllm.com/claude-code-dangerously-skip-permissions)
6. [OpenAI Codex CLI Flaw Allows Attackers to Run Arbitrary Commands](https://gbhackers.com/openai-codex-cli-flaw/)
7. [OpenSSF Scorecard — Security Reference Architecture](https://www.nocomplexity.com/documents/securityarchitecture/prevention/openSSF-scorecard.html)
8. [SLSA and Build Provenance Guide: Levels and Verification](https://nhimg.org/slsa-and-build-provenance-guide)
9. [Snyk acquires Invariant Labs for AI security - Techzine Global](https://www.techzine.eu/news/security/132501/snyk-acquires-invariant-labs-for-ai-security/)
10. [LlamaFirewall: An open source guardrail system for building secure AI agents](https://www.alphaxiv.org/abs/2505.03574)
11. [CVE-2026-25725: Claude Code Sandbox Escape RCE](https://www.miggo.io/vulnerability-database/cve/CVE-2026-25725)
12. [Claude Code: Sandbox Escape via Symlink Following Allows Arbitrary File Write Outside Workspace](https://advisories.gitlab.com/npm/@anthropic-ai/claude-code/CVE-2026-39861/)
13. [CVE-2026-55607: Claude Code Git Worktree Confusion and Sandbox Escape](https://www.penligent.ai/hackinglabs/cve-2026-55607/)
14. [Headless agent -p ignores sandbox.json and generates helper policy with disableTmpWrite:false - Bug Reports - Cursor - Community Forum](https://forum.cursor.com/t/headless-agent-p-ignores-sandbox-json-and-generates-helper-policy-with-disabletmpwrite-false/157095)
15. [Claude Code vulnerabilities and CVEs](https://agentbeam.com/cve/tool/claude-code)
16. [Advisory Database](https://advisories.gitlab.com/pkg/npm/@openai/codex/CVE-2025-59532/)
17. [Git Commit Signing with YubiKey and SSH/FIDO2](https://developers.yubico.com/SSH/Securing_git_with_SSH_and_FIDO2.html)
18. [Securing SSH with FIDO2](https://developers.yubico.com/SSH/Securing_SSH_with_FIDO2.html)
19. [Claude Dangerously Skip Permissions: How to Run It Safely](https://www.cybedefend.com/en/blog/claude-code-dangerously-skip-permissions-explained)
20. [Rules](https://developers.openai.com/codex/rules)
21. [cursor cli Permissions & Sandbox — CheatRef](https://cheatref.com/cursor-cli/permissions-sandbox)
22. [Cursor Dangerously Skip Permissions: --force and YOLO](https://pushary.com/cursor-dangerously-skip-permissions)
23. [Cursor Allowlist Bypass (CVE-2026-22708)](https://danusminimus.github.io/posts/The-Agent-Security-Paradox-When-Trusted-Commands-In-Cursor-Become-Attack-Vectors/)
24. [The Agent Security Paradox: When Trusted Commands in Cursor Become Attack Vectors](https://www.pillar.security/blog/the-agent-security-paradox-when-trusted-commands-in-cursor-become-attack-vectors)
25. [CVE 2026 22708](https://api.osv.dev/v1/vulns/CVE-2026-22708)
26. [Lock Down Claude Code With 5 Permission Patterns - DEV Community](https://dev.to/klement_gunndu/lock-down-claude-code-with-5-permission-patterns-4gcn)
27. [Managed configuration](https://developers.openai.com/codex/enterprise/managed-configuration)
28. [How Do I Sandbox Codex on Linux? (2026)](https://yeet.cx/topical-takes/sandbox-codex-linux)
29. [Codex CLI sandbox modes: read-only, workspace-write, and when each is right](https://backgrind.com/blog/codex-cli-sandbox-modes/)
30. [\[Feature\]: Say when an agent's sandbox is what stopped trace\_processor or adb · Issue #190 · grishan0v/echolot · GitHub](https://github.com/grishan0v/echolot/issues/190)
31. [Run Modes](https://cursor.com/docs/agent/security/run-modes)
32. [Cursor Permissions & Control Model — permissions.json Schema, Run Modes, Hooks](https://agenticcontrolplane.com/controls/cursor)
33. [codex/codex-rs/prompts/templates/permissions/sandbox\_mode/workspace\_write.md at main · openai/codex · GitHub](https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/permissions/sandbox_mode/workspace_write.md)
34. [Cursor CLI: install, agent commands, and headless use](https://continuumcode.ai/guides/cursor-cli/)
35. [Codex Sandbox Modes: Set Up Auto Mode in 3 Ways](https://inventivehq.com/knowledge-base/openai/how-to-configure-sandbox-modes)
36. [sandbox\_workspace\_write.network\_access — Codex config — Codex Insider](https://codexinsider.com/config/sandbox-workspace-write-network-access/)
37. [Cursor Hardening Guide](https://howtoharden.com/guides/cursor/)
38. [Hooks](https://cursor.com/docs/hooks)
39. [Codex exec: execute Codex non-interactively in scripts and CI - DEV Community](https://dev.to/vibeidedev/codex-exec-execute-codex-non-interactively-in-scripts-and-ci-4g50)
40. [Codex CLI Sandbox & Approvals (2026): Auto-Approve, Web Access — AgentsCamp](https://agentscamp.com/guides/configuration/codex-sandbox-and-approvals)
41. [Sandbox](https://learn.chatgpt.com/docs/sandboxing)
42. [Cursor CVE-2026-22708 RCE: Shell Built-ins Beat the Allowlist](https://www.matthewswong.com/en/blog/cursor-cve-2026-22708-shell-builtins-allowlist-bypass/)
43. [Codex CLI Smart Approvals: How Adaptive Command Policies and Prefix Rules Eliminate Approval Fatigue](https://codex.danielvaughan.com/2026/05/04/codex-cli-smart-approvals-adaptive-command-policies-prefix-rules/)
44. [Cursor security risks: the defaults, the CVEs, and what to lock down](https://quintai.dev/blog/cursor-security-risks)
45. [Codex permissions and sandbox modes, explained](https://www.codeilab.com/tutorials/permissions-sandbox)
46. [Agent approvals & security](https://www.codex-docs.com/en/docs/agent-approvals-security)
47. [Cursor CLI: a locked-down headless mode (file tools only, no hooks/MCP/plugins, enforced tool allowlist) - Feature Requests - Cursor - Community Forum](https://forum.cursor.com/t/cursor-cli-a-locked-down-headless-mode-file-tools-only-no-hooks-mcp-plugins-enforced-tool-allowlist/173496)
48. [Configuration-Based Sandbox Escape (CBSE) in AI Coding Tools](https://cymulate.com/blog/the-race-to-ship-ai-tools-left-security-behind-part-1-sandbox-escape/)
49. [CVE-2026-39861: Claude Code Sandbox Escape via Symlink — CVSS 10.0 Arbitrary File Write — adyog](https://pulse.adyog.com/insights/claude-code-symlink-sandbox-escape-cve-2026-39861)
50. [Claude Code: Sandbox Escape via Git Worktree Path Confusion Allows Unsandboxed Code Execution](https://advisories.gitlab.com/npm/@anthropic-ai/claude-code/CVE-2026-55607/)
51. [Beware: Claude Code CVE-2026-55607 — A Malici — TerminalBlog](https://terminalblog.com/blog/beware-cve-2026-55607-claude-code-worktree-sandbox-escape/)
52. [CVE-2025-59532 Impact, Exploitability, and Mitigation Steps](https://www.wiz.io/vulnerability-database/cve/cve-2025-59532)
53. [Sandbox bypass flaws in Cursor IDE highlight prompt injection as an RCE vector](https://www.csoonline.com/article/4191923/sandbox-bypass-flaws-in-cursor-ide-highlight-prompt-injection-as-an-rce-vector.html)
54. [CVE-2026-50548 - Vulnerability Details - OpenCVE](https://app.opencve.io/cve/CVE-2026-50548)
55. [Claude Code Sandbox: How /sandbox Works (and What It Doesn't Protect)](https://www.claudecodecamp.com/p/claude-code-sandboxing-how-sandbox-works-and-what-it-doesn-t-protect)
56. [Squawk vs MigrationPilot: PostgreSQL Migration Linters Compared - DEV Community](https://dev.to/mickelsamuel/squawk-vs-migrationpilot-postgresql-migration-linters-compared-13e4)
57. [github.com](https://github.com/sbdchd/squawk)
58. [Gitleaks vs TruffleHog 2026: Secret Scanner Benchmarks](https://appsecsanta.com/secret-scanning-tools/gitleaks-vs-trufflehog)
59. [GitHub - anthropics/sandbox-runtime: A lightweight sandboxing tool for enforcing filesystem and network restrictions on arbitrary processes at the OS level, without requiring a container. · GitHub](https://github.com/anthropics/sandbox-runtime)
60. [Anthropic Open-Sources Claude Code Sandbox Under Apache 2.0](https://aiweekly.co/alerts/anthropic-open-sources-claude-code-sandbox-under-apache-20)
61. [Sandboxing agents at the OS level: notes on Anthropic's sandbox-runtime - DEV Community](https://dev.to/devinios/sandboxing-agents-at-the-os-level-notes-on-anthropics-sandbox-runtime-pp3)
62. [Best Secret Scanning Tools 2026: 11 Reviewed Picks](https://appsecsanta.com/secret-scanning-tools)
63. [safeupdate](https://pigsty.io/ext/e/safeupdate/)
64. [Container Use · tomrochette.com](https://tomrochette.com/agents/sandboxing/container-use/)
65. [AgentKernel: The Trust-Native Agentic Operating System](https://arxiv.org/pdf/2609.29647)
66. [List of coding agent sandboxes 2026-05 · GitHub](https://gist.github.com/wincent/2752d8d97727577050c043e4ff9e386e)
67. [GitHub - meta-llama/PurpleLlama: Set of tools to assess and improve LLM security. · GitHub](https://github.com/meta-llama/PurpleLlama)
68. [LlamaFirewall: An open source guardrail system for building secure AI agents](https://arxiv.org/html/2505.03574v1)
69. [Lifecycle for the intake acquisitions: Guardrails AI, Pangea, Lunar, Prompt Security, Smithery, Invariant by MrPeppersDev · Pull Request #348 · MrPeppersDev/agent-infrastructure-landscape · GitHub](https://github.com/MrPeppersDev/agent-infrastructure-landscape/pull/348)
70. [squawk/CHANGELOG.md at master · sbdchd/squawk · GitHub](https://github.com/sbdchd/squawk/blob/master/CHANGELOG.md)
71. [squawk-cli · PyPI](https://pypi.org/project/squawk-cli/2.5.0/)
72. [Secret Scanning Tools: TruffleHog vs Gitleaks vs GitGuardian (2026)](https://nurbak.com/en/blog/secret-scanning-tools/)
73. [= Release History == 1.7: July 13, 2026 - Support PostgreSQL 19](https://raw.githubusercontent.com/eradman/pg-safeupdate/master/NEWS)
74. [GitHub - dagger/container-use: Development environments for coding agents. Enable multiple agents to work safely and independently with your preferred stack. · GitHub](https://github.com/dagger/container-use)
75. [What is the SLSA framework? A guide to SLSA levels and supply chain security](https://cloudsmith.com/blog/slsa-a-route-to-tamper-proof-builds-and-secure-software-provenance)
76. [Hivebook - The Knowledge Base for AI Agents](https://hivebook.wiki/wiki/slsa-v1-2-supply-chain-levels-for-software-artifacts)
77. [SLSA • Source Track Sprint Recap](https://slsa.dev/blog/2025/04/slsa-source-sprint)
78. [SLSA v1.2 Source Track: What Changed in November 2025](https://safeguard.sh/resources/blog/slsa-v1-2-source-track-deep-dive-2025)
79. [Supply chain: SLSA 1.2: Build Level 3, and protect the source (Source track) · Issue #220 · Dzobash/apptrol · GitHub](https://github.com/Dzobash/apptrol/issues/220)
80. [Ssh-agent](https://en.wikipedia.org/wiki/Ssh-agent)
81. [Cursor AI Agent Sandboxing Explained: How It Works in 2026](https://www.adwaitx.com/cursor-ai-agent-sandboxing-explained/)
82. [OWASP Top 10 for Agentic Applications 2026](https://cycode.com/blog/owasp-top-10-agentic-applications/)
83. [OWASP Agentic Top 10 for 2026 Explained With a Control for Each Risk](https://futureagi.com/blog/owasp-agentic-top-10-2026/)
84. [OWASP Top 10 for Agentic Applications 2026: Key Takeaways & How to Take Action](https://goteleport.com/blog/owasp-top-10-agentic-applications/)
