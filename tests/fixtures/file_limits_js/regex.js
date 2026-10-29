export function strip(s) {
  const close = /\}+$/g;
  const open = /[{]/;
  return s.replace(close, "").split(open);
}

export function next() {
  return 1;
}
