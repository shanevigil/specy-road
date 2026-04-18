<!--
Post-release: replace this landing page with a short PyPI-focused README
(`pip install specy-road`) once v0.1.x is tagged and published.
-->

# specy-road

**One roadmap for the whole team**—priorities, specs, and implementation stay aligned. The CLI validates a **roadmap** in your repo, exports a readable index, and builds **briefs** so people and agents work from one plan.

## Pre-release

**Not on PyPI yet.** Development happens on branch **`dev`**. **`main`** is reserved for tagged releases.

**Install from source and day-to-day usage:** [docs/install-and-usage.md](docs/install-and-usage.md)  
**Contributors** (tests, pre-commit, releases): [docs/contributor-guide.md](docs/contributor-guide.md)

```bash
git clone https://github.com/shanevigil/specy-road.git
cd specy-road && git switch dev
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui-next]"
```

## More documentation

- [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md) — what the kit covers
- [docs/git-workflow.md](docs/git-workflow.md) — branches and registry (consumer repos use `roadmap/git-workflow.yaml`)
- [AGENTS.md](AGENTS.md) — quick entry for coding agents

## Contributing

Contact the repository owner to work on the toolkit. Setup: [docs/contributor-guide.md](docs/contributor-guide.md).

## License

MIT — see [LICENSE](LICENSE).
