# Install a release candidate (TestPyPI)

## Agent quickstart

**Use this doc when:** you install or evaluate a specy-road release candidate (`X.Y.ZrcN`), with or without an extra such as `[gui]`.
**Not for:** installing a final release from PyPI ([`install-and-usage.md`](install-and-usage.md#install)) or publishing an RC ([`release-runbook.md`](release-runbook.md), A.3).

**Must know without reading on:**
- An RC is one exact wheel from TestPyPI, sha256-checked against the RC announcement, with its dependencies and extras from PyPI only.
- TestPyPI is never an index for extras or dependencies, whatever the flag or index strategy.
- With an extra, install the checked local wheel (`"rc/<wheel>[gui]"`) or its direct URL (`"specy-road[gui] @ https://test-files.pythonhosted.org/.../<wheel>"`); uv tool does not check a `#sha256=` fragment, pip and pipx do.

**Read further for:**
- why TestPyPI is never an index → "Never an index"
- pip and uv pip in a virtualenv → "Download and check the wheel"
- pipx and uv tool, with `[gui]` → "Isolated CLI with an extra"
- installing from the wheel's URL and checking its sha256 → "Direct wheel URL"
- version pins and going back to a final → "After installing"

**Related:** [`install-and-usage.md`](install-and-usage.md), [`supply-chain-security.md`](supply-chain-security.md#release-candidates-from-testpypi), [`upgrading.md`](upgrading.md).

---

Prereleases (`X.Y.ZrcN`) publish to **TestPyPI**, not PyPI. The examples use `0.3.1rc1` and the `[gui]` extra; put in the version, wheel URL and sha256 from the RC announcement, and any extra from [Install](install-and-usage.md#install) (`[gui]`, `[gui-next]`, `[review]`).

## Never an index

TestPyPI is never an index for extras or dependencies, in any form: not as `--index-url`, not as `--extra-index-url`, not as uv's `--index` or `--extra-index-url`, and with no index strategy (`unsafe-best-match`, `first-index` or any other). Anyone can register a name on TestPyPI, so once it is an index a dependency name squatted there can be installed in place of the real one on PyPI, and installing a squatted sdist runs its build code on your machine. How depends on the form: `--index-url` makes TestPyPI the only index; pip's `--extra-index-url` and uv's `unsafe-best-match` take the highest version from either index; uv's default `first-index` takes each name from the first index that has it, and an index passed with `--index` or `--extra-index-url` is searched before PyPI, so TestPyPI wins every name it has. Listing PyPI first instead does not reach the RC: `first-index` then takes `specy-road` from PyPI, which has no RC, and the exact pin fails. Fetch only the pinned `specy-road` wheel from TestPyPI and let PyPI supply everything else ([supply-chain-security.md](supply-chain-security.md#release-candidates-from-testpypi)).

## Download and check the wheel

```bash
pip download --no-deps --only-binary :all: -d rc/ \
    --index-url https://test.pypi.org/simple/ "specy-road==0.3.1rc1"
sha256sum rc/specy_road-0.3.1rc1-py3-none-any.whl   # must equal the announced sha256
pip install --no-deps rc/specy_road-0.3.1rc1-py3-none-any.whl
pip install "rc/specy_road-0.3.1rc1-py3-none-any.whl[gui]"   # dependencies and the extra, from PyPI only
```

With uv (no pip needed in the virtualenv; `uv venv` and `uv sync` install none):

```bash
uvx pip download --no-deps --only-binary :all: -d rc/ \
    --index-url https://test.pypi.org/simple/ "specy-road==0.3.1rc1"
sha256sum rc/specy_road-0.3.1rc1-py3-none-any.whl   # must equal the announced sha256
uv pip install "rc/specy_road-0.3.1rc1-py3-none-any.whl[gui]"   # PyPI, uv's default index
```

Drop `[gui]` for the bare package. These steps assume PyPI is your only configured index (no `PIP_EXTRA_INDEX_URL`, `UV_INDEX` or `UV_EXTRA_INDEX_URL`). An exact pin needs no `--pre`.

## Isolated CLI with an extra

From the wheel checked above:

```bash
pipx install --force "rc/specy_road-0.3.1rc1-py3-none-any.whl[gui]"
uv tool install --force "rc/specy_road-0.3.1rc1-py3-none-any.whl[gui]"
```

uv tool records that local path in its receipt, and the receipt breaks once `rc/` is deleted; the direct URL below avoids that.

## Direct wheel URL

The announcement and TestPyPI's file listing (`https://test.pypi.org/project/specy-road/0.3.1rc1/#files`) give the wheel's full URL under `https://test-files.pythonhosted.org/`. Install that URL as a direct reference; only the wheel comes from TestPyPI and every dependency comes from PyPI:

```bash
URL="https://test-files.pythonhosted.org/.../specy_road-0.3.1rc1-py3-none-any.whl"   # full URL from the announcement
SHA="<announced sha256>"

# pipx (and pip) check a #sha256= fragment and refuse a wheel that does not match
pipx install --force "specy-road[gui] @ $URL#sha256=$SHA"

# uv tool ignores the fragment: check the URL's bytes first, then install
curl -fsSL "$URL" | sha256sum                       # must equal $SHA
uv tool install --force "specy-road[gui] @ $URL"
```

TestPyPI does not let a file be replaced under the same name, so the bytes you checked are the bytes uv installs. uv tool keeps the URL in its receipt, unlike a local wheel path that later disappears, so the receipt keeps pointing at a file that exists. Checked with pipx 1.18 and uv 0.13.7; a wrong fragment made pipx fail with a hash mismatch, while uv tool installed anyway.

## After installing

Confirm the result with `specy-road --version` ([Which install is running](install-and-usage.md#which-install-is-running)). Go back to a final release with `pipx install --force "specy-road[gui]"` or `uv tool install --force "specy-road[gui]"`.

RCs are for evaluation: pin a final release for day-to-day work. `specy-road validate` warns once when the running version is not the one your repo pins (`"pin": "<version>"` in `.specyrd/manifest.json`, else the first `specy-road==<version>` line in a `requirements*.txt` at the checkout root), so an accidental upgrade is not mistaken for a deliberate one. Expect an RC to warn too that IDE stubs and JSON schemas were written by an older version: once your team accepts the new version, update the pin and run `specy-road upgrade`.
