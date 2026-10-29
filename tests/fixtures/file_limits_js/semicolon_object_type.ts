const cache = new Map<string, { id: string; n: number }>(), oversized = () => {
  const a = 1;
  const b = 2;
  return a + b;
};
const other = new Map<{ id: string; n: number }, string>(), short = () => 1;
const make = new Foo<() => { a: string; b: number }, T>(), tiny = () => 1;
const also = () =>
  new Map<string, { id: string; n: number }>().get("x") &&
  true &&
  true &&
  true &&
  true &&
  true &&
  true;
export class Handler {
  onChange = () =>
    new Map<string, { id: string; n: number }>().get("x") &&
    true &&
    true &&
    true &&
    true &&
    true &&
    true;
}
