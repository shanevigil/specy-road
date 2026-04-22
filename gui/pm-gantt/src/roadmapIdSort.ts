/** Sort key segments: numeric runs (0) vs literal runs (1), matching Python ``natural_id_sort_key``. */
export type NaturalIdSeg = readonly [tag: 0, value: number] | readonly [tag: 1, value: string];

/** ASCII digit runs vs other runs (roadmap display ids use ``[0-9]`` only). */
const RE_PARTS = /\d+|\D+/g;
const RE_ASCII_DIGITS = /^[0-9]+$/;

/** Lexical fallback as a single string segment (mirrors Python ``((1, nid),)``). */
function lexicalFallback(nid: string): NaturalIdSeg[] {
  return [[1, nid]];
}

export function naturalIdSortKey(nid: string): NaturalIdSeg[] {
  if (typeof nid !== "string" || nid.length === 0) {
    return lexicalFallback(nid);
  }
  const parts = nid.match(RE_PARTS);
  if (!parts?.length) {
    return lexicalFallback(nid);
  }
  const out: NaturalIdSeg[] = [];
  for (const p of parts) {
    if (RE_ASCII_DIGITS.test(p)) {
      const n = Number.parseInt(p, 10);
      if (Number.isNaN(n)) {
        return lexicalFallback(nid);
      }
      out.push([0, n]);
    } else {
      out.push([1, p]);
    }
  }
  return out;
}

export function compareRoadmapIds(a: string, b: string): number {
  const ka = naturalIdSortKey(a);
  const kb = naturalIdSortKey(b);
  const n = Math.max(ka.length, kb.length);
  for (let i = 0; i < n; i++) {
    const x = ka[i];
    const y = kb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    if (x[0] !== y[0]) {
      return x[0] - y[0];
    }
    if (x[0] === 0) {
      const xv = x[1];
      const yv = (y as readonly [0, number])[1];
      if (xv !== yv) return xv < yv ? -1 : 1;
    } else {
      const xv = x[1];
      const yv = (y as readonly [1, string])[1];
      if (xv !== yv) return xv < yv ? -1 : xv > yv ? 1 : 0;
    }
  }
  return 0;
}
