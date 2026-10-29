export class Handler {
  onChange: (x: number) => number = (x) => {
    const y = x + 1;
    const z = y + 1;
    return z;
  };
}
