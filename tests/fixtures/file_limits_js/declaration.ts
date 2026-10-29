// function inComment() { a commented-out declaration is not measured }
export function overloaded(a: string): string;
export function overloaded(a: number): number;
export function overloaded(a: string | number): string | number {
  return a;
}

export async function load<T extends Record<string, unknown>>(
  url: string,
): Promise<{ data: T; status: number }> {
  const res = await fetch(url);
  return { data: (await res.json()) as T, status: res.status };
}

function* ids(): Generator<number> {
  let i = 0;
  while (true) yield i++;
}

function shape(): { a: number } | { b: string } {
  return { a: 1 };
}
