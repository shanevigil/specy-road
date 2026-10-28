import { describe, expect, it } from "vitest";
import drawerSource from "./components/BrainstormDrawer.tsx?raw";
import typesSource from "./types.ts?raw";

/**
 * Review round 6, F3 and F7. The drawer has no DOM test harness, so these
 * pin the source the way `tableCols.test.ts` does: the session type carries
 * the planned round count the server now sends, the mode strip shows
 * "round N of M", and the converge help says it is advisory and points at
 * the CLI's `revise` — `docs/pm-gui-brainstorm.md` promises exactly that.
 */
describe("brainstorm drawer copy", () => {
  it("declares the planned round count on the session type", () => {
    const block = /export type BrainstormSession = \{[\s\S]*?\n\};/.exec(typesSource)?.[0] ?? "";
    expect(block).toMatch(/\n\s+round: number;/);
    expect(block).toMatch(/\n\s+rounds: number;/);
  });

  it("shows the round as N of M next to the mode help", () => {
    expect(drawerSource).toMatch(/`round \$\{String\(s\.round\)\} of \$\{String\(s\.rounds\)\}`/);
    expect(drawerSource).toMatch(/\{roundLabel\(session\)\} · \{MODE_HELP\[session\.mode\]\}/);
  });

  it("tells the PM that converge is advisory and routes verdicts to the CLI", () => {
    const roadmapHelp = /roadmap:\n([\s\S]*?),\n\};/.exec(drawerSource)?.[1] ?? "";
    expect(roadmapHelp).toContain("Advisory only");
    expect(roadmapHelp).toContain("specy-road brainstorm revise");
  });
});
