import { describe, expect, it } from "vitest";
import {
  devColumnDetailTitle,
  displayStatusAllowsCheckoutBar,
  rowMatchesRegisteredBranch,
} from "./rowMatchesRegisteredBranch";

describe("rowMatchesRegisteredBranch", () => {
  it("is true when current branch equals registry branch", () => {
    expect(
      rowMatchesRegisteredBranch(
        "M1.2",
        {
          "M1.2": {
            branch: "feature/rm-x",
            node_id: "M1.2",
            codename: "x",
            touch_zones: ["a"],
          },
        },
        "feature/rm-x",
      ),
    ).toBe(true);
  });

  it("is false when branches differ", () => {
    expect(
      rowMatchesRegisteredBranch(
        "M1.2",
        {
          "M1.2": {
            branch: "feature/rm-x",
            node_id: "M1.2",
            codename: "x",
            touch_zones: ["a"],
          },
        },
        "main",
      ),
    ).toBe(false);
  });

  it("is false when current branch is empty", () => {
    expect(
      rowMatchesRegisteredBranch(
        "M1.2",
        {
          "M1.2": {
            branch: "feature/rm-x",
            node_id: "M1.2",
            codename: "x",
            touch_zones: ["a"],
          },
        },
        "",
      ),
    ).toBe(false);
  });
});

describe("devColumnDetailTitle", () => {
  it("includes branch and registry hint line", () => {
    const t = devColumnDetailTitle(
      "N1",
      {
        N1: {
          branch: "feature/rm-foo",
          started: "bar",
          node_id: "N1",
          codename: "foo",
          touch_zones: ["z"],
        },
      },
      {
        N1: {
          kind: "registry",
          branch: "feature/rm-foo",
          hint_line: "feature/rm-foo · bar",
        },
      },
      {},
    );
    expect(t).toContain("Branch: feature/rm-foo");
    expect(t).toContain("feature/rm-foo · bar");
  });
});

describe("displayStatusAllowsCheckoutBar", () => {
  it("is false for terminal states", () => {
    expect(displayStatusAllowsCheckoutBar("Complete")).toBe(false);
    expect(displayStatusAllowsCheckoutBar("Cancelled")).toBe(false);
    expect(displayStatusAllowsCheckoutBar("Blocked")).toBe(false);
  });

  it("is true for in progress and not started", () => {
    expect(displayStatusAllowsCheckoutBar("In Progress")).toBe(true);
    expect(displayStatusAllowsCheckoutBar("Not Started")).toBe(true);
  });
});
