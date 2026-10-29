const cache = new Map<{ id: string }, number>(), oversized = () => {
  const a = 1;
  const b = 2;
  return a + b;
};
const other = new Foo<string, { a: number }>(), short = () => 1;
