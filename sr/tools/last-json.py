"""Print the last top-level JSON object in stdin (the reviewer's answer), or stdin unchanged if there is none.

Cursor's text output puts any narration the model writes before its answer in the same final message; since M8.3
specy-road parses that message as exactly one JSON object. Used by cursor-review.sh only."""
import json
import sys

text = sys.stdin.read()
dec, best, i = json.JSONDecoder(), None, 0
while True:
    i = text.find("{", i)
    if i < 0:
        break
    try:
        obj, end = dec.raw_decode(text, i)
    except ValueError:
        i += 1
        continue
    if isinstance(obj, dict):
        best = text[i:end]
    i = end
sys.stdout.write(best + "\n" if best is not None else text)
