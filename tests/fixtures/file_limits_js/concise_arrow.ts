export const total = async (items: Item[]): Promise<number> =>
  (await Promise.all(items.map(price)))
    .filter((p) => p > 0)
    .map((p) => p * rate)
    .map(Math.round)
    .reduce((sum, p) => sum + p, 0);

export const curried = (a: number) => (b: number) =>
  a +
  b;
const label = (n: number) => `#${n}`
export function after() {
  return label(1);
}
