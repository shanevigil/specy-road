const limit = 10, clamp = (x: number) => {
  if (x < 0) return 0;
  if (x > limit) return limit;
  return x;
};

let pending, twice: (n: number) => number = (n) => n * 2, { size } = opts, reset = () => {
  pending = undefined;
};
