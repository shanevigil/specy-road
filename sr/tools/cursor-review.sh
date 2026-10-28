#!/bin/sh
# cursor-review.sh <cursor model id> <prompt text>: one reviewer turn on the Cursor CLI.
# Used as channels.cli for the reviewer entries; `specy-road prompt --channel cli` passes the
# rendered reviewer prompt as the second argument. --force lets it run the verify commands.
model=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road-agent-guidance/sr/tools:$PATH
export PATH
exec agent -p --force --model "$model" --output-format text "$prompt"
