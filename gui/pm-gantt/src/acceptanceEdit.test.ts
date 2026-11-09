import { describe, expect, it } from "vitest";

import { ACCEPTANCE_NEWLINE_MESSAGE, acceptanceEdit } from "./acceptanceEdit";

describe("acceptanceEdit", () => {
  const saved = ["First", "Second"];

  it.each([
    ["unchanged (same value as saved: the queue sends no PATCH)", saved, "First\nSecond"],
    ["added", [...saved, "Third"], "First\nSecond\nThird"],
    ["removed", ["Second"], "Second"],
    ["reordered", ["Second", "First"], "Second\nFirst"],
    ["emptied (removes the field)", [], ""],
    ["whitespace trimmed, whitespace-only dropped", ["  First ", "   ", "", "Second\t"], "First\nSecond"],
  ])("%s", (_label, draft, value) => {
    expect(acceptanceEdit(draft)).toEqual({ ok: true, value });
  });

  // Every boundary Python's str.splitlines() splits on (the server's edit-node parser).
  it.each(["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])(
    "refuses a criterion containing the line boundary %j",
    (sep) => {
      const bad = `two${sep}lines`;
      expect(acceptanceEdit(["First", bad])).toEqual({
        ok: false,
        message: ACCEPTANCE_NEWLINE_MESSAGE,
      });
    },
  );
});
