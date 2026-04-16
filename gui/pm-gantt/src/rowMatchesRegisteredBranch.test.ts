import { describe, expect, it } from "vitest";
import {
  devColumnDetailTitle,
  devColumnLabel,
  displayStatusAllowsCheckoutBar,
  isDisplayStatusInProgress,
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
  it("includes branch and started; omits registry hint when redundant with Branch/Started", () => {
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
    expect(t).toContain("Started: bar");
    expect(t).not.toContain("feature/rm-foo · bar");
  });
});

describe("devColumnLabel", () => {
  const reg = {
    N1: {
      branch: "feature/rm-foo",
      node_id: "N1",
      codename: "foo",
      touch_zones: ["z"],
    },
  };

  it("shows em dash for registry-only enrichment when not on that branch", () => {
    expect(
      devColumnLabel(
        "N1",
        reg,
        {
          N1: {
            kind: "registry",
            branch: "feature/rm-foo",
            hint_line: "feature/rm-foo",
          },
        },
        "main",
        "Local Dev",
      ),
    ).toBe("—");
  });

  it("never puts the branch string in the cell", () => {
    expect(
      devColumnLabel(
        "N1",
        reg,
        {
          N1: {
            kind: "registry",
            branch: "feature/rm-foo",
            hint_line: "feature/rm-foo · x",
          },
        },
        "main",
        null,
      ),
    ).not.toBe("feature/rm-foo");
  });

  it("shows remote tip author", () => {
    expect(
      devColumnLabel(
        "N1",
        reg,
        {
          N1: {
            kind: "remote_tip",
            author: "Pat",
            branch: "feature/rm-foo",
            hint_line: "feature/rm-foo · Pat",
          },
        },
        "main",
        null,
      ),
    ).toBe("Pat");
  });

  it("shows local git user when current branch matches registered branch", () => {
    expect(
      devColumnLabel(
        "N1",
        reg,
        {},
        "feature/rm-foo",
        "Jamie",
      ),
    ).toBe("Jamie");
  });
});

describe("displayStatusAllowsCheckoutBar", () => {
  it("is false for terminal states", () => {
    expect(displayStatusAllowsCheckoutBar("Complete")).toBe(false);
    expect(displayStatusAllowsCheckoutBar("Blocked")).toBe(false);
  });

  it("is true for in progress and not started", () => {
    expect(displayStatusAllowsCheckoutBar("In Progress")).toBe(true);
    expect(displayStatusAllowsCheckoutBar("Not Started")).toBe(true);
  });
});

describe("isDisplayStatusInProgress", () => {
  it("detects in progress label", () => {
    expect(isDisplayStatusInProgress("In Progress")).toBe(true);
    expect(isDisplayStatusInProgress("in progress")).toBe(true);
    expect(isDisplayStatusInProgress("Not Started")).toBe(false);
  });
});
