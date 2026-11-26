import { describe, expect, it } from "vitest";

import {
  GROUP_NONE_CHECKED_MESSAGE,
  GROUP_TITLE_MESSAGE,
  groupBody,
  groupDialogState,
} from "./outlineGroup";

// The outline of tests/move_node_helpers.py's wide_fixture, which the server
// contract test in tests/test_gui_outline_contract.py posts to.
const ORDERED = ["M1", "M1.1", "M1.2", "M1.2.1", "M1.2.2", "M1.2.4", "M1.3", "M2", "M2.1", "M2.4"];
const BY_ID: Record<string, { parent_id?: string | null }> = Object.fromEntries(
  ORDERED.map((id) => [id, { parent_id: id.includes(".") ? id.slice(0, id.lastIndexOf(".")) : null }]),
);

describe("groupDialogState", () => {
  it.each([
    ["a leaf under a phase", "M1.3", ["M1.1", "M1.2", "M1.3"], "M1.4"],
    ["a leaf whose siblings have a gap", "M1.2.2", ["M1.2.1", "M1.2.2", "M1.2.4"], "M1.2.5"],
    ["a phase at the root", "M2", ["M1", "M2"], "M3"],
  ])("%s", (_label, rowId, siblingIds, intoNew) => {
    expect(groupDialogState(ORDERED, BY_ID, rowId)).toEqual({
      siblingIds,
      checked: new Set([rowId]),
      intoNew,
      title: "",
      type: "milestone",
      rewriteRefs: false,
    });
  });

  it("ignores a sibling whose id an edge-only re-parent kept", () => {
    const byId = { ...BY_ID, "M1.3": { parent_id: "M2" } };
    const ordered = ["M1", "M1.1", "M1.2", "M2", "M2.1", "M1.3"];
    const state = groupDialogState(ordered, byId, "M2.1");
    expect(state.siblingIds).toEqual(["M2.1", "M1.3"]);
    expect(state.intoNew).toBe("M2.2");
  });
});

describe("groupBody", () => {
  const opened = groupDialogState(ORDERED, BY_ID, "M1.3");

  it("sends the checked rows in outline order", () => {
    // The body test_outline_group_posts_the_dialogs_body posts to the server.
    const state = { ...opened, checked: new Set(["M1.3", "M1.1"]), title: " Grouped " };
    expect(groupBody(state)).toEqual({
      ok: true,
      body: {
        into_new: "M1.4",
        title: "Grouped",
        node_ids: ["M1.1", "M1.3"],
        type: "milestone",
        rewrite_refs: false,
      },
    });
  });

  it("sends the edited id, type and rewrite_refs", () => {
    const state = { ...opened, intoNew: "M1.9", title: "G", type: "phase", rewriteRefs: true };
    expect(groupBody(state)).toEqual({
      ok: true,
      body: { into_new: "M1.9", title: "G", node_ids: ["M1.3"], type: "phase", rewrite_refs: true },
    });
  });

  it.each([
    ["an empty title", { title: "" }, GROUP_TITLE_MESSAGE],
    ["a whitespace title", { title: "  " }, GROUP_TITLE_MESSAGE],
    ["no row checked", { title: "G", checked: new Set<string>() }, GROUP_NONE_CHECKED_MESSAGE],
  ])("refuses %s", (_label, edit, message) => {
    expect(groupBody({ ...opened, ...edit })).toEqual({ ok: false, message });
  });
});
