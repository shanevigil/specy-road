# Claude Code limit fixtures

Verbatim shapes of the messages `specy-road grind-session` must recognise when
`--implement-cmd` is the Claude CLI. They exist so that a change to Claude Code's
wording fails a test here instead of silently stalling an unattended grind.

If Anthropic changes the format, add the new shape as a file and update
`specy_road/claude_code_limits.py` — do not loosen the parser until it guesses.
