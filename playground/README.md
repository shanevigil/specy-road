# Playground (local only)

Use this directory when you want to run **`specy-road init project`** (or exercise validate/export/brief) against a **throwaway consumer layout** without leaving untracked files all over the toolkit repository root.

From the repository root:

```bash
specy-road init project playground
specy-road validate --repo-root playground
```

**Git:** Everything under `playground/` is ignored except this file and [`.gitkeep`](.gitkeep). Remove contents when finished, or delete the whole folder; it is not part of the shipped package.
