#!/bin/sh
# cursor-review.sh <cursor model id> <prompt text | prompt file>: one reviewer turn on the Cursor CLI.
# Used as channels.cli for the reviewer entries. With "<prompt>" in the channel, specy-road passes
# the rendered prompt text; with "{prompt}" it passes the path of the file holding it, which keeps
# long prompts (an RCA after many rounds) under the command-line length limit: the agent is then
# told to read that file first. --force lets it run the verify commands.
model=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road/sr/tools:/Users/savigil/WORKSPACE/specy-road/.conda/bin:$PATH
export PATH
if [ -f "$prompt" ]; then
  prompt="Your complete prompt is in the file $prompt. Read that file first, in full, then follow it exactly; it says what to review and where to write your record."
fi
exec agent -p --force --model "$model" --output-format text "$prompt"
