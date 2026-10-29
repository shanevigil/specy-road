export function layout(width, height, sizes) {
  const box = { w: width / 2 }; const r = height / 3;
  const s = (width) / sizes[0] / 4;
  return box.w + r + s;
}

export function next() {
  return 1;
}
