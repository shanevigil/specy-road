const wrapped = ((x) => x + 1) as Foo, after = () => {
  const a = 1;
  const b = 2;
  return a + b;
};
const checked = ((x) => x * 2) satisfies Fn<number, number>, also = () => 1;
