const cache = new Map<string, number>(), oversized = () => {
  const a = 1;
  const b = 2;
  return a + b;
};
const limit = a < b, after = () => 1;
const make = new Foo<() => void, T>(), short = () => 1;
