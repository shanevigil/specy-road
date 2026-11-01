export class Handler {
  onChange! = () => {
    const a = 1;
    const b = 2;
    return a + b;
  };
  onInput!: { a: string } = () => {
    const a = 1;
    const b = 2;
    return a + b;
  };
  onKey!: (x: number) => number = (x) => {
    const y = x + 1;
    const z = y + 1;
    return z;
  };
}
