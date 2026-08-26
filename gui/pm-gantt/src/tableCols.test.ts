import { describe, expect, it } from "vitest";
import outlineSource from "./components/OutlineTable.tsx?raw";

/**
 * TABLE_COLS is the colSpan for the root drop zone and every drag-drop gap
 * row. When a column is added and this is not, those rows render short of the
 * table width and the drop targets stop lining up — silently, since nothing
 * else references the constant.
 */
describe("outline TABLE_COLS", () => {
  it("matches the number of header columns actually rendered", () => {
    const declared = Number(
      /const TABLE_COLS = (\d+);/.exec(outlineSource)?.[1],
    );
    const headerBlock = /<thead>[\s\S]*?<\/thead>/.exec(outlineSource)?.[0] ?? "";
    // RootDropZone is a component reference, not a literal <th>, so every <th>
    // inside <thead> is a real data column.
    const rendered = (headerBlock.match(/<th[\s>]/g) ?? []).length;

    expect(rendered).toBeGreaterThan(0);
    expect(declared).toBe(rendered);
  });
});
