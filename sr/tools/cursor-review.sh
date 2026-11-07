#!/bin/sh
# cursor-review.sh <cursor model id> <prompt text | prompt file>: one reviewer turn on the Cursor CLI.
# Used as channels.cli for the reviewer entries. With "<prompt>" in the channel, specy-road passes
# the rendered prompt text; with "{prompt}" it passes the path of the file holding it, which keeps
# long prompts (an RCA after many rounds) under the command-line length limit: the agent is then
# told to read that file first. --force lets it run the verify commands.
# "--model <id> <prompt>" is the form the review gate can read (worker_models.command_model); "<id> <prompt>" still works.
if [ "$1" = --model ]; then shift; fi
model=$1 prompt=$2
. "$(dirname "$0")/env.sh"
if [ -z "${SR_PLAN_REVIEW:-}" ] && [ -f "$prompt" ] && [ -f "$(dirname "$0")/review-addendum.md" ]; then
  merged=$(mktemp "${TMPDIR:-/tmp}/review-prompt.XXXXXX") && cat "$prompt" "$(dirname "$0")/review-addendum.md" "$(dirname "$0")/../constraints/review-brief.md" > "$merged" && prompt=$merged
fi
if [ -f "$prompt" ]; then
  prompt="Your complete prompt is in the file $prompt. Read that file first, in full, then follow it exactly; it says what to review and where to write your record."
fi
mkdir -p "$REVIEWS/.transcripts"
side="$REVIEWS/.transcripts/cursor-$(date +%Y%m%dT%H%M%S)-$$.log"
# Since M8.3 the channel output must be one JSON object: keep the raw text in a side file and print only the
# last top-level JSON object of the answer (the model sometimes narrates before it).
agent -p --force --model "$model" --output-format text "$prompt" > "$side" 2>&1
rc=$?
python3 "$(dirname "$0")/last-json.py" < "$side"
exit $rc
