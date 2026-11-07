# M22.17 implementation summary

`brainstorm verify` records `blocked` when a page returns 404 or 410 and that origin's root is not 200 or cannot be fetched. A root of 200 keeps `not-found`. The root is requested once per origin per run.

## What changed

- `specy_road/bundled_scripts/brainstorm_verify.py`: `host_answers` fetches `https://host[:port]/` (no userinfo, query or fragment; port 443 omitted) through the same fetcher and caches whether it returned 200. `check_source` calls it only for 404 and 410. `verify_session` passes one cache for the run.
- `tests/test_brainstorm_verify.py`: the 404 row in `test_check_source_states` gains a root-200 response; new rows cover the root outcomes, one fetch per origin, and a root redirect to a private address through `default_fetch`.
- `docs/brainstorming.md`: `blocked` includes a host that answers verify with 404 at its root. `CHANGELOG.md`: [Unreleased] Fixed.

## Touch zones

Confirmed: `specy_road/bundled_scripts/brainstorm_verify.py`, `tests/test_brainstorm_verify.py`, `docs/brainstorming.md`, `CHANGELOG.md`. The importers outside the zones (`brainstorm_cli_args_v2.py`, `brainstorm_cli_v2.py`, `test_brainstorm_repo_evidence.py`, `test_brainstorm_v2.py`, `test_review_round4_sol_b.py`) call `check_source` without the new cache. 401, 403, 429, other non-200 statuses and a 200 page are unchanged, so those files stay outside the zones.

## Added

- `host_answers`: one root fetch per origin; True only when that fetch returns 200.
- `port == 443` in `host_answers`: the default port is omitted from the root URL; any other port is part of the origin.
- `if root not in roots` in `host_answers`: a second source on an origin already probed does not fetch again.
- `except Exception` in `host_answers`: a root that fails to fetch is cached as not answering, so the source is `blocked`. The transport-error rows reach it.
- `if status in (404, 410)` in `check_source`: only those statuses probe the root; 401, 403 and 429 stay `blocked`, and any other non-200 stays `not-found`.
- `cache = {} if roots is None else roots` in `check_source`: a direct call still probes; a verify run shares one dict.
- `return "not-found" if host_answers(...) else "blocked"` in `check_source`: a 200 root keeps `not-found`; anything else is `blocked`.
- `roots` dict in `verify_session`: one cache for the run.
- `test_a_missing_page_follows_its_origin_root`: 404 or 410 with root 404, 200 or a transport error; a non-default port whose root URL drops userinfo, query and fragment; a 200 page and a 500 make no root request.
- `test_two_missing_pages_on_one_origin_probe_the_root_once`: two 404s on one origin are both `blocked` after one root fetch; a different port is a separate origin.
- `test_check_source_states` (extended): the 404 fixture's root answers 200 and stays `not-found`; a call list asserts the other rows make no root request.
- `Sock`, `connect` and `wrap` in `test_a_root_that_redirects_to_a_private_address_is_blocked`: fake DNS and transport around `default_fetch`, so the root's redirect to a private address is `blocked` and that address is never connected.
- `test_a_root_that_redirects_to_a_private_address_is_blocked`: that redirect case, through `default_fetch`.
