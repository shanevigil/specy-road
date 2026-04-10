/** Mirrors ``title_to_codename`` in ``scripts/roadmap_edit_fields.py`` (kebab-case codename). */

const CODENAME_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function titleToCodename(title: string): string {
  let s = (title || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-");
  s = s.replace(/-+/g, "-").replace(/^-|-$/g, "");
  if (!s || !CODENAME_PATTERN.test(s)) return "";
  return s;
}
