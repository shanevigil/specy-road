const banner = `{ ${"}"} ${ { nested: `${1}` }.nested } }`;
const quote = '}';
const dq = "{";
/* } } } */
export function render(items) {
  // a stray } in a comment
  const html = `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;
  return html + '}' + "{";
}
export const after = () => {
  return banner + quote + dq;
};
