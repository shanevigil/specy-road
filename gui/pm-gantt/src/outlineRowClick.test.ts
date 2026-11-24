import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DOUBLE_CLICK_MS,
  createOutlineRowClick,
  rowDragAttributes,
} from "./outlineRowClick";

describe("createOutlineRowClick", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("selects on the click, before the double-click window ends", () => {
    const row = createOutlineRowClick();
    expect(row.click("M1")).toBe("select");
    expect(row.selectedId()).toBe("M1");
    vi.advanceTimersByTime(DOUBLE_CLICK_MS);
    expect(row.selectedId()).toBe("M1");
  });

  it("a second click inside the window opens the modal and does not select again", () => {
    const row = createOutlineRowClick();
    expect(row.click("M1")).toBe("select");
    vi.advanceTimersByTime(DOUBLE_CLICK_MS - 1);
    expect(row.click("M1")).toBe("open");
    expect(row.selectedId()).toBe("M1");
  });

  it("a click after the window is another select", () => {
    const row = createOutlineRowClick();
    expect(row.click("M1")).toBe("select");
    vi.advanceTimersByTime(DOUBLE_CLICK_MS);
    expect(row.click("M1")).toBe("select");
  });

  it("a click while a title is being edited does not select", () => {
    const row = createOutlineRowClick();
    row.click("M1");
    expect(row.click("M2", { titleEditing: true })).toBe("ignore");
    vi.advanceTimersByTime(DOUBLE_CLICK_MS);
    expect(row.selectedId()).toBe("M1");
    expect(row.toolbarTarget()).toBe("M1");
  });

  it("a toolbar action immediately after a click targets the clicked row", () => {
    const row = createOutlineRowClick();
    row.click("M1");
    row.click("M2");
    expect(row.toolbarTarget()).toBe("M2");
  });
});

describe("rowDragAttributes", () => {
  it("does not mark a row aria-disabled when only drag is disabled", () => {
    const marked = { role: "button", tabIndex: 0, "aria-disabled": true };
    const stripped = rowDragAttributes(marked, true);
    expect(stripped).toEqual({ role: "button", tabIndex: 0 });
    expect(Object.hasOwn(stripped, "aria-disabled")).toBe(false);
    expect(rowDragAttributes(marked, false)).toEqual(marked);
  });
});
