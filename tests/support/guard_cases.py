"""The shared-checkout guard's classify-only case tables, and the wrapper spellings they draw from.

``tests/unit/test_tool_call_guard.py`` and ``tests/cli/test_session_guard.py`` parametrize or loop
their classify-only tests over these tables, and ``tests/property/test_guard_wrappers.py`` wraps
every row. They live here because a test module is never imported by another test file. Each table
keeps the rows and order its test had, so the test ids are unchanged.
"""

from __future__ import annotations

ENV_ALIAS = "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='!git stash' git x"

# --- tests/unit/test_tool_call_guard.py ------------------------------------------

#: ``(command, fragment of the reason)`` for commands the guard refuses.
DESTRUCTIVE = [
    ("git stash", "stash stack is shared"),
    ("git stash push -u -m x", "stash stack is shared"),
    ("git reset --hard HEAD~1", "discards other sessions"),
    ("git checkout main", "switching branches"),
    ("git checkout -b feature/x", "switching branches"),
    ("git switch dev", "switching branches"),
    ("git checkout -- .", "discards working-tree changes"),
    ("git checkout -- src/a.py", "discards working-tree changes"),
    ("git restore .", "discards other sessions"),
    ("git restore --staged .", "discards other sessions"),
    ("git clean -fd", "deletes untracked files"),
    ("git clean --force", "deletes untracked files"),
    ("git rebase -i HEAD~3", "rewrites history"),
    ("git commit --amend --no-edit", "rewrites a commit"),
    ("git commit -a -m x", "sweeps every session"),
    ("git commit -am x", "sweeps every session"),
    ("git commit --all -m x", "sweeps every session"),
    ("git add -A", "stages other sessions"),
    ("git add .", "stages other sessions"),
    ("git add -u", "stages other sessions"),
    ("git add --all", "stages other sessions"),
    ("git push --force origin main", "rewrites the remote"),
    ("git push -f", "rewrites the remote"),
    ("git push --force-with-lease", "rewrites the remote"),
    ("git push origin +main", "rewrites the remote"),
    ("make test && git stash", "stash stack is shared"),
    ("cd x; git reset --hard", "discards other sessions"),
    ("git -C /tmp/repo checkout main", "switching branches"),
    ("GIT_DIR=.git git rebase main", "rewrites history"),
    ("echo x\ngit stash", "stash stack is shared"),
    ("git reset --hard  # don't", "discards other sessions"),
    ('git commit -m "a; b" -a', "sweeps every session"),
    ("sh -c 'git stash'", "stash stack is shared"),
    ("bash -lc 'cd x && git rebase main'", "rewrites history"),
    ("(git stash)", "stash stack is shared"),
    ("make test & git stash", "stash stack is shared"),
    ("/usr/bin/git stash", "stash stack is shared"),
    ("command git stash", "stash stack is shared"),
    ("env GIT_TRACE=1 git stash", "stash stack is shared"),
    ("sudo -u bob git clean -f", "deletes untracked files"),
    ("git -c alias.s=stash s", "stash stack is shared"),
    ("git -c alias.rh='reset --hard' rh", "discards other sessions"),
    ("git -c alias.x='!git stash' x", "stash stack is shared"),
    ("git commit -m 'x'", "commits whatever another session staged"),
    ("git commit -m 'a; b' --no-verify", "commits whatever another session staged"),
    ("git -c alias.x='!cd /tmp && git reset --hard' x", "discards other sessions"),
    ("if true; then git stash; fi", "stash stack is shared"),
    ("! git stash", "stash stack is shared"),
    ("while ! git diff --quiet; do git reset --hard; done", "discards other sessions"),
    ("if true; then sh -c 'git stash'; fi", "stash stack is shared"),
    ("case x in a) git stash;; esac", "stash stack is shared"),
    ("find . -name '*.py' -exec git rm -f {} +", "git rm -f"),
    ("git rm -f src/a.py", "git rm -f"),
    ("git rm -rf src", "git rm -f"),
    ("git rm --force src/a.py", "git rm -f"),
    ("if true; then git${IFS}stash; fi", "shell expansion"),
    ("git${IFS}stash", "shell expansion"),
    ("$(echo git) stash", "shell expansion"),
    ("`echo git` stash", "shell expansion"),
    ("{git,stash}", "shell expansion"),
    ("gi? stash", "shell expansion"),
    ("case x in a) git${IFS}stash;; esac", "shell expansion could build `git`"),
    ("$X stash", "shell expansion"),
    ("g{i,}t stash", "shell expansion"),
    ("G=git; case x in x) ${G} stash;; esac", "stash stack is shared"),
    ("X=i; g${X}t stash", "shell expansion"),
    ("! (git stash)", "stash stack is shared"),
    ("{ (git stash); }", "stash stack is shared"),
    ("if true; then (git stash); fi", "stash stack is shared"),
    ('(env -S "git stash")', "stash stack is shared"),
    ('sudo env -S "git stash"', "stash stack is shared"),
    ('FOO=1 env -S "git stash"', "stash stack is shared"),
    ('env -vS "git stash"', "stash stack is shared"),
    ('env -iS "git stash"', "stash stack is shared"),
    ('env -S"git stash"', "stash stack is shared"),
    ('env -vS"git stash"', "stash stack is shared"),
    ('(env -vS "git stash")', "stash stack is shared"),
    ('sudo env -iS "git stash"', "stash stack is shared"),
    ('FOO=1 env -S"git stash"', "stash stack is shared"),
    ('FOO=1 env -vS"git stash"', "stash stack is shared"),
    ("env -S 'git\\_stash'", "stash stack is shared"),
    ("(GIT_CONFIG_GLOBAL=/tmp/c git x)", "GIT_CONFIG*"),
    ("(git --config-env=alias.x=BODY x)", "--config-env=alias"),
    ("env --u HOME git stash", "stash stack is shared"),
    ("env --ch /tmp git stash", "stash stack is shared"),
    ("env --unset=HOME git stash", "stash stack is shared"),
    ("env --chdir=/tmp git switch dev", "switching branches"),
    ("env --default-signal git stash", "stash stack is shared"),
    ("env --default-signal=PIPE git stash", "stash stack is shared"),
    ("env --debug git stash", "stash stack is shared"),
]

#: Commands the guard allows.
ORDINARY = [
    "git add src/a.py docs/x.md",
    "git commit -m 'x' src/a.py",
    "git commit --only src/a.py -m x",
    "git push origin feature/rm-thing",
    "git worktree add ../wt -b feature/x main",
    "git status --porcelain",
    "git diff --cached",
    "git log --oneline -3",
    "git fetch origin",
    "git merge --no-ff feature/x",
    "git restore --staged src/a.py",
    "git reset src/a.py",
    "git checkout",
    "git add -p src/a.py",
    "make test && python -m pytest",
    "echo 'git stash' > notes.txt",
    "gitk",
    "grep -rn git src",
    "echo $HOME",
    "ls ${DIR}",
    "[ -f x ] && ls src/*.py",
    "git commit -m 'git: bump $V' src/a.py",
    "$HOME/bin/pytest -q",
    "${PYTHON:-python} -m pytest",
    "env -i git status",
    "env -u HOME ls",
    "env -uHOME ls",
    "env --u=HOME ls",
    "env --unset git stash",
    "env --chdir git stash",
    "env --ch git status",
]

#: Shapes the guard cannot follow when they mention git, and bare commits: refused.
OPAQUE_REFUSED = [
    "f(){ git stash; }; f", "sh -c 'f(){ git reset --hard; }; f'", "gitcmd=git; $gitcmd stash",
    "python -c 'import subprocess; subprocess.run([\"git\",\"stash\"])'", "git commit -m x",
]

#: The same shapes without git: allowed.
OPAQUE_WITHOUT_GIT = ["f(){ echo hi; }; f", "python -c 'print(1)'", "git commit -m x src/a.py"]

#: Wrapper shapes the guard follows to a refused command.
MORE_WRAPPER_SHAPES = [
    'env -S "git stash"', "echo $(git reset --hard $(echo HEAD))", "sudo --user root git stash",
    "env --unset HOME git stash", "nice --adjustment 5 git stash", "timeout 10 git stash",
    "printf 'stash\\n' | xargs git",
]

#: More refused shapes: forced checkouts, path restores, brace groups, ``eval`` and substitutions.
MORE_DESTRUCTIVE_SHAPES = [
    "git checkout -f", "git checkout --force", "git restore src/a.py", "git restore -W src/a.py",
    "{ git stash; }", "eval git stash", "echo $(git reset --hard)", "x=`git stash`",
]


# --- tests/cli/test_session_guard.py ---------------------------------------------

#: Git config supplied through the environment: refused as opaque.
ENV_CONFIG_REFUSED = [
    ENV_ALIAS,
    "GIT_CONFIG_PARAMETERS=\"'alias.x=!git stash'\" git x",
    "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0=stash git x",
    "GIT_CONFIG=/tmp/c git x",
    "GIT_CONFIG_GLOBAL=/tmp/c git x",
    "GIT_CONFIG_SYSTEM=/tmp/c git x",
    "git --config-env=alias.x=BODY x",
    "git --config-env alias.x=BODY x",
    "sh -c 'GIT_CONFIG_GLOBAL=/tmp/c git x'",
]

#: Commands the env-config check leaves alone.
ENV_CONFIG_ORDINARY = [
    "GIT_TRACE=1 git log",
    "git --config-env=user.name=NAME log",
    "git commit -m 'GIT_CONFIG=x' src/a.py",       # the name inside an argument is not an assignment
    "GIT_CONFIG_GLOBAL=/tmp/c make test",            # no git in the segment
]

#: ``(command, fragment)``: process substitution and dynamic git verbs.
DYNAMIC_SHELL_FORMS = [
    ("cat <(git stash)", "stash stack is shared"),
    ("cat >(git stash)", "stash stack is shared"),
    ("diff <(git log) <(git reset --hard)", "discards other sessions"),
    ("git $(printf stash)", "shell expansion"),
    ("git ${x:-stash}", "shell expansion"),
    ('git "$x"', "shell expansion"),
    ("git $x", "shell expansion"),
    ("git `printf stash`", "shell expansion"),
    ("cat <(git stash", "unbalanced"),
]

#: Broad commit and add pathspecs: refused.
BROAD_PATHSPECS = [
    "git commit --only . -m swept",
    "git commit --only ./ -m swept",
    "git commit --only :/ -m swept",
    "git commit --only ':(glob)**' -m swept",
    "git commit --only '*' -m x",
    "git commit --only 'src/*.py' -m x",
    "git commit --only .. -m x",
    "git commit --only ../other -m x",
    "git commit --only /abs/path/a.py -m x",
    "git commit -m x -- .",
    "git commit --only --pathspec-from-file=paths.txt -m x",
    "git add 'src/*.py'",
    "git add ..",
    "git add ':(top)src'",
    "git rm -r .",
]

#: Explicit pathspecs: allowed.
EXPLICIT_PATHSPECS = [
    "git commit --only src/a.py -m x",
    "git commit -m x src/a.py docs/b.md",
    "git commit --only src/ -m x",          # a plain directory is scoped: the caller vouches for it
    "git commit -m 'a * b' src/a.py",       # a glob inside -m is a message, not a pathspec
    "git add src/a.py",
    "git add src/",
    "git rm src/a.py",                      # refuses a file with uncommitted changes; stages a deletion like `git add`
]

#: ``(command, fragment)``: ``eval`` is judged by what it runs.
EVAL_FORMS = [
    ('eval "git stash"', "stash stack is shared"),
    ("eval 'git reset --hard'", "discards other sessions"),
    ("eval git stash", "stash stack is shared"),
    ("eval \"$(printf 'git stash')\"", "cannot see"),
    ("sudo eval 'git clean -f'", "deletes untracked files"),
]

# --- tests/unit/test_tool_call_guard.py, classify-only tests that loop over literals ----------

# test_env_split_escapes_and_pre_leaf_refusals
#: ``env -S`` escapes that read as ``git stash``: the stash refusal.
ENV_SPLIT_SAME = (
    "env -S 'git\\_stash'", "env -vS 'git\\_stash'", "env -S'git\\_stash'",
    "env --split 'git\\_stash'", "env --s 'git\\_stash'", "env --spl='git\\_stash'",
    "env -S 'git\\tstash'", "env -S 'git\\nstash'", "env -S 'git\\fstash'",
    "env -S 'git\\vstash'", "env -S 'git\\rstash'", "env -S 'git\tstash'",
    "env -S 'git stash\\c --hard'",
)

#: ``env -S`` strings that keep the escape literal, end early or comment it out: allowed.
ENV_SPLIT_LITERAL = (
    "env -S \"git'\\_stash'\"", "env -S '\"git\\_stash\"'", "env -S 'git\\\\_stash'",
    "env -S 'gi\\ct stash'", "env -S '# git stash'",
)

#: ``env -S`` strings with an unknown escape or runtime state: refused as opaque.
ENV_SPLIT_UNKNOWN_ESCAPE = (
    "env -S 'git\\x20stash'", "env -S '\\gitstash'",
    "env -S -S '${CMD} stash'", "env -S --split '${CMD} stash'",
    "env --split -S '${CMD} stash'", "env -vS -S '${DIR}'",
    "env -S -S 'git\\x20stash'", "sudo env -S -S '${CMD} stash'",
    "(env -S -S 'git\\x20stash')", "env -S -S -S '${CMD} stash'",
    "env -i -S -S '${CMD} stash'",
)

#: ``env -S`` forms the pre-leaf guard refused: still refused.
ENV_SPLIT_REFUSED_BEFORE = (
    'env -S "git stash"', '(env -S "git stash")', 'sudo env -S "git stash"',
    'FOO=1 env -S "git stash"', 'env -vS "git stash"', 'env -iS "git stash"',
    'env -S"git stash"', 'env -vS"git stash"', '(env -vS "git stash")',
    'sudo env -iS "git stash"', 'FOO=1 env -S"git stash"', 'FOO=1 env -vS"git stash"',
    "env -S 'git\\_stash'", "env -S 'git\\x20stash'", "env -S 'git\\tstash'",
    "env -S 'git\\nstash'",
)

# test_unlisted_wrapper_option_is_opaque
#: An option a wrapper does not list, before a word that could be git: refused.
UNLISTED_OPTION_HIDDEN = (
    "sudo --not-a-sudo-option git stash",
    "sudo -Q git stash",
    "command -x git stash",
    "doas -Q git stash",
    "nohup -x git stash",
    "exec -x git stash",
    "time --not-time git stash",
    "nice --not-nice git stash",
    "ionice -Q git stash",
    "xargs -Q git stash",
    "timeout --not-timeout 10 git stash",
    "env --not-an-env-option git stash",
    "/usr/bin/sudo -Q git reset --hard",
    "( sudo -Q git stash )",
    "sudo -n --not-a-sudo-option git stash",
    "sudo -Q $X",
    "(sudo -Q $X)",
    "( sudo -Q $X)",
    '(sudo -Q "$X")',
    "(sudo -Q ${X})",
    "(sudo -Q g$X)",
    "(env -Q $X)",
    "(nohup -x $X)",
    "(doas -Q $CMD)",
    "(nice -5 $X)",
    "x=1; (sudo -Q $X)",
    "(sudo -Q $X); ls",
    "! (sudo -Q $X)",
    "{ (sudo -Q $X); }",
)

#: The same options before a word that cannot be git: allowed.
UNLISTED_OPTION_ALLOWED = (
    "sudo --not-a-sudo-option ls /tmp", "command -x echo hi", "nice --not-nice ls",
    "(sudo -Q ls)", "(sudo -Q ls )", "( (sudo -Q ls ))",
)

# test_split_string_options_are_parsed_before_the_command
#: An option inside ``-S`` consumes its value, so ``git`` is not the command: allowed.
SPLIT_OPTION_CONSUMED = (
    "env -S '--unset git stash'", "env -S '--chdir git stash'", "env -S '-u git stash'",
    "env -S '--un git stash'", "env -S '--ch git stash'", "env -S '-C git status'",
    "sudo env -S '--unset git stash'", "(env -S '--chdir git stash')",
    "FOO=1 env -S '-u git stash'", "env --split '--unset git stash'",
    "env -S --unset git stash",
)

#: Options inside ``-S`` that leave ``git stash`` as the command: the stash refusal.
SPLIT_OPTION_RUNS = (
    "env -S '-u HOME git stash'", "env -S '--unset=HOME git stash'",
    "env -S '--debug git stash'", "env -S '--default-signal git stash'",
    "env -S '-- git stash'", "env -S '--ch /tmp git stash'",
    "env -S '-uHOME git stash'", "env -S 'FOO=1 git stash'",
)

#: A ``GIT_CONFIG*`` word after an env option, directly and inside ``-S``: the env-config refusal.
SPLIT_OPTION_CONFIG_HELD = (
    "env -i GIT_CONFIG_GLOBAL=/tmp/c git x",
    "env -v GIT_CONFIG_PARAMETERS=x git status",
    "env -- GIT_CONFIG_GLOBAL=/tmp/c git x",
    "env -u HOME GIT_CONFIG_GLOBAL=/tmp/c git x",
    "env --unset=HOME GIT_CONFIG_PARAMETERS=x git status",
    "env -C /tmp GIT_CONFIG_GLOBAL=/tmp/c git x",
    "env -iv GIT_CONFIG_GLOBAL=/tmp/c git x",
    "env --ignore-environment GIT_CONFIG_PARAMETERS=x git status",
    "env -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
    'env -S "-i GIT_CONFIG_GLOBAL=/tmp/c git x"',
    "env -S '-v GIT_CONFIG_PARAMETERS=x git status'",
    "env -S '-- GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "env -S '-u HOME GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "env -S '--unset=HOME GIT_CONFIG_PARAMETERS=x git status'",
    "env -S '-C /tmp GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "env -S '-iv GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "env -S '--ignore-environment GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "env -vS '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
    'env --split-string="-i GIT_CONFIG_GLOBAL=/tmp/c git x"',
    "sudo env -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
    "(env -S '-C /tmp GIT_CONFIG_PARAMETERS=x git status')",
    "env -S -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
)

#: The inputs of the single-input classify tests in those two files (unparseable shell,
#: harmless process substitution, a staged path restore, harmless ``eval``).
SINGLE_INPUT_CASES = (
    "git stash 'unterminated",
    "echo 'unterminated",
    "diff <(git log -3) <(git log -3 origin/main)",
    "git restore --staged src/a.py",
    'eval "echo hi"',
    "eval make test",
)

#: Every classify-only case of the two guard test files.
CLASSIFY_CASES = tuple(
    row[0] if isinstance(row, tuple) else row
    for table in (
        DESTRUCTIVE, ORDINARY, OPAQUE_REFUSED, OPAQUE_WITHOUT_GIT, MORE_WRAPPER_SHAPES,
        MORE_DESTRUCTIVE_SHAPES, ENV_CONFIG_REFUSED, ENV_CONFIG_ORDINARY, DYNAMIC_SHELL_FORMS,
        BROAD_PATHSPECS, EXPLICIT_PATHSPECS, EVAL_FORMS, SINGLE_INPUT_CASES,
        ENV_SPLIT_SAME, ENV_SPLIT_LITERAL, ENV_SPLIT_UNKNOWN_ESCAPE, ENV_SPLIT_REFUSED_BEFORE,
        UNLISTED_OPTION_HIDDEN, UNLISTED_OPTION_ALLOWED,
        SPLIT_OPTION_CONSUMED, SPLIT_OPTION_RUNS, SPLIT_OPTION_CONFIG_HELD,
    )
    for row in table
)

#: The directories a wrapper is path-qualified with: ``/usr/bin/sudo`` is ``sudo``.
PATH_PREFIXES = ("/usr/bin/", "/bin/", "./")

# One spelling per documented option (a value where the option takes one). ``timeout``'s
# duration stays in the gap, after the option. ``env -S`` is not here: the split string is
# the command, covered by ``env_split_forms``.
WRAPPER_SPELLINGS = (
    ("command", "", ("-p", "-v", "-V")),
    ("sudo", "", (
        "-A", "-B", "-b", "-C bob", "-D bob", "-E", "--preserve-env", "--preserve-env=bob",
        "-e", "-g bob", "-H", "--help", "-h bob", "-i", "-K", "-k", "-l", "-N", "-n",
        "-P", "-p bob", "-R bob", "-r bob", "-S", "-s", "-t bob", "-T bob", "-U bob",
        "-u bob", "-V", "-v",
    )),
    ("doas", "", ("-a bob", "-C bob", "-L", "-n", "-s", "-u bob")),
    ("nohup", "", ("--help", "--version")),
    ("exec", "", ("-a bob", "-c", "-l")),
    ("time", "", ("-a", "-f bob", "-o bob", "-p", "-q", "-v", "-V", "-h", "--help")),
    ("nice", "", ("-n bob", "--help", "--version")),
    ("ionice", "", ("-c bob", "-n bob", "-p bob", "-P bob", "-t", "-u bob", "-h", "-V")),
    ("xargs", "", (
        "-0", "-a bob", "-d bob", "-E bob", "-e", "--eof=bob", "-I bob", "-i", "--replace=bob",
        "-L bob", "-l", "--max-lines=bob", "-n bob", "-P bob", "-o", "-p",
        "--process-slot-var=bob", "-r", "-s bob", "--show-limits", "-t", "-x", "--help", "--version",
    )),
    ("timeout", "10 ", (
        "--preserve-status", "--foreground", "-k bob", "-s bob", "-v", "--help", "--version",
    )),
    ("env", "", (
        "-i", "-0", "-u bob", "-C /tmp", "-v", "--block-signal", "--block-signal=INT",
        "--default-signal", "--default-signal=INT", "--ignore-signal", "--ignore-signal=INT",
        "--list-signal-handling", "--help", "--version",
    )),
)
