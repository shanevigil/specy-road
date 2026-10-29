type Props = { label: string; onPick: (id: string) => void };

export const Badge = ({ label }: Props) => (
  <span className="badge">
    {label}
  </span>
);

export const usePick: (p: Props) => () => void = (p) => {
  return () => p.onPick(p.label);
};

const parse = async <T,>(raw: string): Promise<T> => {
  return JSON.parse(raw) as T;
};

let twice = (n: number): number => n * 2;
const notAFunction = compute(1, 2);
