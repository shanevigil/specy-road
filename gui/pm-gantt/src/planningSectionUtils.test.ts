import { describe, expect, it } from "vitest";
import {
  assignDiffRowSectionIndices,
  groupContiguousSectionRanges,
  mergeBySectionChoices,
  splitByH2,
} from "./planningSectionUtils";
import { buildPlanningSideBySideRows } from "./planningDiffUtils";

describe("splitByH2", () => {
  it("splits preamble and two h2 sections", () => {
    const s = "Intro\n\n## Tasks\n- a\n\n## Notes\nb";
    const x = splitByH2(s);
    expect(x.length).toBe(3);
    expect(x[0].raw).toBe("Intro\n");
    expect(x[1].raw).toBe("## Tasks\n- a\n");
    expect(x[2].raw).toBe("## Notes\nb");
  });

  it("treats leading ## as second slice after empty preamble", () => {
    const x = splitByH2("## Only\nbody");
    expect(x.length).toBe(2);
    expect(x[0].raw).toBe("");
    expect(x[1].raw).toBe("## Only\nbody");
  });

  it("returns one empty section for empty input", () => {
    expect(splitByH2("")).toEqual([{ raw: "" }]);
  });
});

describe("mergeBySectionChoices", () => {
  it("merges by index when headings differ", () => {
    const orig = "## Old title\nx";
    const prop = "## Tasks / checklist\ny";
    const merged = mergeBySectionChoices(orig, prop, ["before", "proposed"]);
    expect(merged).toBe("\n\n## Tasks / checklist\ny");
  });

  it("uses choices length to cap merged sections", () => {
    const o = "pre\n\n## A\n1";
    const p = "pre\n\n## A\nx";
    expect(mergeBySectionChoices(o, p, ["before"])).toBe("pre\n");
  });
});

describe("diff row section indices", () => {
  it("aligns with splitByH2 segment boundaries", () => {
    const a = "preamble\n\n## A\na";
    const b = "preamble\n\n## A\nb";
    const rows = buildPlanningSideBySideRows(a, b);
    const idx = assignDiffRowSectionIndices(rows);
    const groups = groupContiguousSectionRanges(idx);
    expect(groups.length).toBeGreaterThan(0);
    expect(idx.every((n) => n >= 0)).toBe(true);
    const maxSeg = Math.max(...idx);
    expect(maxSeg).toBeLessThanOrEqual(splitByH2(a).length);
  });
});
