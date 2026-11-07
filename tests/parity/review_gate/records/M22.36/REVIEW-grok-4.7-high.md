---
node_id: M22.36
model: grok-4.7-high
model_version: '4.7'
date: '2026-11-07'
verdict: approve
commit: a69a19e9b9fbfc8c4bb546125e493306713df4a4
acceptance:
  A1: pass
  A2: pass
  A3: pass
findings:
  correctness:
  - The release-notes step writes the hosted wheel URL not a defect because that URL
    matched the published PyPI file for version 0.2.3.
  - The TestPyPI host uses the same blake2b-256 path not a defect because that URL
    matched the published file for version 0.3.1rc4.
  regression:
  - Release-harness checks still pass not a defect because `github-release` still
    runs only after a `pypi` or `testpypi` publish.
  boundary:
  - '`sr/work/implementation-summary-M22.36.md` is outside the listed touch zones
    not a defect because the brief requires the summary at that path.'
  test_integrity:
  - No behavioural test was deleted not a defect because the diff only adds notes-step
    checks.
commands_rerun:
- PYTHONDONTWRITEBYTECODE=1 python -m pytest -n 4 -p no:cacheprovider -q tests/test_release_harness.py
  tests/test_post_release_readme_cleanup.py tests/test_docs_install_extras.py tests/test_docs_rc_install_recipe.py
  exited 0 with 33 passed in 37.36s.
- 'Probe input unused by the diff tests: target testpypi, wheel specy_road-9.9.9-py3-none-any.whl,
  bytes probe-bytes-not-in-tests, sidecar extra.txt, notes text ''section tail  ''
  with no trailing newline. Returned exit 0, sha256 3450cc0aea7cc0e98a41b74ee33784dd26a5308c1c1ab2d1dae09dd43f13fc09,
  one install line for https://test-files.pythonhosted.org/packages/d1/42/be873cd78d4493c4e7928af54e90e97595665d476a929e3b566f296864e8/specy_road-9.9.9-py3-none-any.whl#sha256=3450cc0aea7cc0e98a41b74ee33784dd26a5308c1c1ab2d1dae09dd43f13fc09.'
- Published specy_road-0.2.3-py3-none-any.whl bytes hash to the live URL https://files.pythonhosted.org/packages/4d/58/83efdb147eeb3623bee42e05515286bc2e6e83a6d1e9f91cef67885c1a72/specy_road-0.2.3-py3-none-any.whl
  with sha256 3a4fcc30326d3ba5821e9f63e594a22e32c232e0d700265c9528df508b9aebc8.
- Published specy_road-0.3.1rc4-py3-none-any.whl bytes hash to the live URL https://test-files.pythonhosted.org/packages/3a/7a/cbc8b003b620dd1658f89d384dd81bff9253133303d8c661d59dfd31bba8/specy_road-0.3.1rc4-py3-none-any.whl
  with sha256 5268016465b4abe4135f0cbade8a95f6f3431d15127d879118bd877b9ecc79b8.
- README markdown link scan found 52 links. Zero targets sit outside https or an in-page
  anchor.
- git diff 26e7bf1b1302335d2c179413a28a5d3ae652eed9 a69a19e9b9fbfc8c4bb546125e493306713df4a4
  -- pyproject.toml contains no version line. Declared project.version remains 0.3.1rc2.
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: 8718a5f003706a97acc73e560fc07847f6fa1d4f770e75de213ab1b0fe611d2e
launch_mode: full
toolkit_version: 0.3.1rc2+15b0a66901f8.dirty
family: xai
independence: distinct-family
---

## Acceptance
A1: pass
A2: pass
A3: pass
## Correctness
The release-notes step writes the hosted wheel URL not a defect because that URL matched the published PyPI file for version 0.2.3.
The TestPyPI host uses the same blake2b-256 path not a defect because that URL matched the published file for version 0.3.1rc4.
## Regression
Release-harness checks still pass not a defect because `github-release` still runs only after a `pypi` or `testpypi` publish.
## Boundary
`sr/work/implementation-summary-M22.36.md` is outside the listed touch zones not a defect because the brief requires the summary at that path.
## Test integrity
No behavioural test was deleted not a defect because the diff only adds notes-step checks.
## Excess
The summary has an Added inventory not a defect because the new helpers only execute the workflow script.