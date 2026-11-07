# M22.17 implementation summary

`brainstorm verify` records `blocked` when a page returns 404 or 410 and that origin's root is not 200 or cannot be fetched. A root of 200 keeps `not-found`. The root is requested once per origin per run. An IPv6 literal is written in brackets, and port 443 is omitted, so the root URL is one origin key.

## What changed

- `specy_road/bundled_scripts/brainstorm_verify.py`: `_root_url` spells the origin once. `host_answers` fetches that URL through the same fetcher and caches whether it returned 200. `_non_200` is the status table: 404 and 410 follow the root, 401, 403 and 429 are `blocked`, anything else non-200 is `not-found`. `verify_session` passes one cache for the run. `check_source` calls `_non_200` and is no more complex than at the merge base.
- `tests/test_brainstorm_verify.py`: the 404 row in `test_check_source_states` gains a root-200 response. Rows cover root outcomes, a public IPv6 literal (bare, with a non-default port, and with explicit `:443`), one root fetch per origin without pinning cross-source order, and a root redirect to a private address through `default_fetch`.
- `docs/brainstorming.md`: `blocked` includes a host that answers verify with 404 at its root. `CHANGELOG.md`: [Unreleased] Fixed, including IPv6 brackets.

## Touch zones

Confirmed: `specy_road/bundled_scripts/brainstorm_verify.py`, `tests/test_brainstorm_verify.py`, `docs/brainstorming.md`, `CHANGELOG.md`. The importers outside the zones (`brainstorm_cli_args_v2.py`, `brainstorm_cli_v2.py`, `test_brainstorm_repo_evidence.py`, `test_brainstorm_v2.py`, `test_review_round4_sol_b.py`) call `check_source` without the new cache. 401, 403, 429, other non-200 statuses and a 200 page are unchanged, so those files stay outside the zones.

## Probes

- Class: a URL rebuilt from `urlsplit().hostname` drops the brackets an IPv6 literal needs, so the root is not a URL (bare `https://2606:4700:4700::1111/` does not parse; with a port it becomes `https://2606:4700:4700::1111:8443/`). `_root_url` is the only place this change builds a URL. Brackets and a non-default port are one rule there. Result: fixed, and the same function omits port 443.
- `check_source` passes the caller's page URL to `fetch` unchanged. Result: no second reconstruction; a bracketed page URL stays bracketed.
- `verify_session` does not build URLs; it shares one `roots` dict. Result: two sources on one origin, including explicit `:443` versus none, use the root string `_root_url` returns.
- `default_fetch` follows redirects with `urljoin` of the Location value. Result: that string is not rebuilt from a hostname; left as it was.
- `_fetch_once` uses `urlsplit().hostname` unbracketed for `getaddrinfo`, SNI and the Host header. Result: not a URL; DNS and SNI must stay unbracketed. This is the pre-existing connection path for every fetch, including a bracketed root. Left as it was.
- `_allowed` uses the hostname only for the public-host check. Result: not a URL. Left as it was.
- Class: `test_two_missing_pages_on_one_origin_probe_the_root_once` compared the full fetch sequence and pinned order across sources. Result: it now asserts the two verification states and one root fetch per origin, with no order.
- `test_a_missing_page_follows_its_origin_root` still expects `[page, root]` for one source. Result: the second URL is the root spelling, not a cross-source order. Kept.
- `test_check_source_states` counts `https://example.com/` once. Result: already order-insensitive. Kept.
- `test_a_root_that_redirects_to_a_private_address_is_blocked` expects two connections to the public address. Result: that is one page then its root, and it shows the private address was not connected. Kept.
- Class: prose about the root spelling stated a limit the function does not have. `_root_url`'s docstring and this summary's Added line both said a zone id is not kept. Result: `_root_url("https://[fe80::1%25eth0]/a")` returns `https://[fe80::1%25eth0]/`, and both sentences now say a zone id in the hostname is retained. The code copies the hostname and was not changed.
- The module docstring, `host_answers`'s docstring, `CHANGELOG.md` and `docs/brainstorming.md`. Result: none of them say a zone id is dropped, so they were left as they are.

## Added

- `_root_url`: the one origin spelling. IPv6 literals are bracketed; any other host is not. Port 443 is omitted. Userinfo, query and fragment are dropped. A zone id in the hostname is retained (`https://[fe80::1%25eth0]/a` has root `https://[fe80::1%25eth0]/`).
- `host_answers`: one fetch of `_root_url` per origin; True only when that fetch returns 200.
- `if root not in roots` in `host_answers`: a second source on an origin already probed does not fetch again.
- `except Exception` in `host_answers`: a root that fails to fetch is cached as not answering, so the source is `blocked`. The transport-error rows reach it.
- `_ASK_ROOT` and `_BLOCKED_STATUS`: the non-200 table (404 and 410 ask the root; 401, 403 and 429 are `blocked`).
- `_non_200`: applies that table. A direct call with no cache still probes; a verify run shares one dict.
- `roots` dict in `verify_session`: one cache for the run.
- `test_a_missing_page_follows_its_origin_root`: 404 or 410 with root 404, 200 or a transport error; a non-default port whose root drops userinfo, query and fragment; a public IPv6 literal bare, with port 8443 (userinfo, query and fragment dropped) and with explicit `:443`; a 200 page and a 500 make no root request.
- `test_a_zone_id_stays_in_the_origin_root`: `https://[fe80::1%25eth0]/a` is answered only at `https://[fe80::1%25eth0]/`, so a zone id in the hostname is retained.
- `test_two_missing_pages_on_one_origin_probe_the_root_once`: two 404s on one origin are both `blocked` after one root fetch; a different port is a separate origin. Counts, not fetch order.
- `test_check_source_states` (extended): the 404 fixture's root answers 200 and stays `not-found`; the other rows make no root request.
- `Sock`, `connect` and `wrap` in `test_a_root_that_redirects_to_a_private_address_is_blocked`: fake DNS and transport around `default_fetch`, so the root's redirect to a private address is `blocked` and that address is never connected.
- `test_a_root_that_redirects_to_a_private_address_is_blocked`: that redirect case, through `default_fetch`.
- `_example_com_is_public` (extended): the public IPv6 literal resolves to itself, so the allow-list accepts it offline.
