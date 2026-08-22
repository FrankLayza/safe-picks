# Phase 3 Football Data Provider Research

Status: Recommendation for paper-trading MVP
Date: 2026-08-23

## Decision Summary

Use a two-source arrangement for the first paper-trading pilot:

1. **Football-Data.co.uk** for historical results, match statistics, and historical pre-closing/closing odds files used for backfills and baseline model development.
2. **The Odds API** for current fixtures and bookmaker odds at prediction time, subject to accepting its current plan terms and confirming that the selected bookmakers/markets are available in the account.

This is an engineering recommendation, not a claim that either provider grants unrestricted commercial redistribution. Before a public or paid launch, obtain written confirmation of the applicable licence and redistribution rights. Keep raw snapshots private and expose only derived predictions in the MVP.

For a single-vendor alternative, evaluate API-Football (fixtures/results/statistics/injuries/lineups/odds) after account access is available. Its public pages were protected by Cloudflare during this review, so price, quota, and licence terms are intentionally **not** stated here without an authenticated account. Sportradar/Opta are enterprise alternatives, not an MVP default.

## Provider Comparison

| Provider | Coverage and useful fields | Timestamp / historical semantics | API availability | Cost and rate limits | Licence and operational risk | MVP assessment |
|---|---|---|---|---|---|---|
| [Football-Data.co.uk](https://www.football-data.co.uk/) | Downloadable CSVs for many domestic leagues. The [England page](https://www.football-data.co.uk/englandm.php) lists full-time and half-time results, match statistics, match/total-goals/Asian-handicap odds. The [data key](https://www.football-data.co.uk/notes.txt) documents goals, shots, shots on target, corners, cards, fouls and bookmaker/average/max odds columns. | Files are season/league downloads, not an event-level odds feed. The notes state weekend odds are collected Friday afternoon and midweek odds Tuesday afternoon. This is useful for historical replay but not exact intraday availability. Preserve file retrieval time and the source's stated collection window. | Public HTTPS/CSV downloads. No documented JSON API or webhook in the reviewed public material; the site links to a separate paid partner API. | Historical files are advertised as free downloads. No public API quota or rate-limit policy was found. Do not assume unlimited automated polling; download on a scheduled, low-frequency job and cache files. | [Disclaimer](https://www.football-data.co.uk/disclaimer.php) disclaims correctness/liability and says data is informational. The site acknowledges third-party result/statistics/odds sources. Public pages do not provide a clear commercial redistribution licence; request permission before republishing raw data or using it in a commercial service. | **Use for historical backfill/baselines only.** Strong coverage for common leagues and corners, but timestamp granularity and licence ambiguity make it unsuitable as the sole live source. |
| [The Odds API](https://the-odds-api.com/) | Aggregates bookmaker odds for many sports; its [v4 guide](https://the-odds-api.com/liveapi/guides/v4/) documents sports, events, bookmakers, markets, regions, decimal odds, event `commence_time`, and bookmaker `last_update`. Football market coverage must be checked per sport/league and account. | Provides event kickoff time plus per-bookmaker market update timestamps. Current endpoints are snapshots at request time. Historical odds access is plan-dependent; confirm that the subscribed plan exposes the historical endpoint/window needed for replay. Store request time and every bookmaker `last_update`. | REST API with API key. Official docs describe response quota headers and request parameters such as sport, regions, markets, odds format and event filters. | Plan pricing/quotas change; do not hard-code a price in project docs. The API exposes remaining/used request quota in response headers; implement a request budget, cache responses, exponential backoff for 429s, and stop polling when quota is exhausted. | Aggregated odds are licensed under the provider's terms and may restrict redistribution, bookmaker branding, or commercial use. Review current [terms](https://the-odds-api.com/terms) and plan agreement before publishing odds or SportyBet codes. | **Preferred live odds source for paper trading**, provided the account has the required football leagues/markets and historical access (if needed). It is separate from the results/statistics source, which is deliberate. |
| [API-Football](https://www.api-football.com/) | Broad football API advertised around fixtures, results, standings, teams, player data, injuries, lineups, statistics and odds. Exact league/event coverage should be checked in its [documentation](https://www.api-football.com/documentation-v3) using the account's coverage endpoint. | API responses include fixture dates/status and provider update fields; exact odds history and snapshot retention depend on endpoint/plan. Confirm whether odds are point-in-time snapshots or current-only before using for backtests. Record retrieval time and all provider timestamps. | REST API with API key, commonly accessed through API-Sports dashboard/host. Documentation and pricing pages were Cloudflare-protected in this review, so no unverified quota or price is recorded. | Pricing, daily request allowance and endpoint limits require authenticated dashboard review. Treat all values as **unknown pending account verification**. | Commercial use and redistribution are governed by subscription terms. Do not assume that displaying provider data, training a model, or reselling picks is permitted without written confirmation. | **Best single-vendor candidate if verified**, especially for injuries/lineups/statistics. Do not make it Phase 3 default until coverage, historical odds, quota, and licence are confirmed. |
| [Sportradar](https://developer.sportradar.com/) / Opta | Enterprise-grade football and betting feeds with broad global coverage, official competition feeds and detailed event/statistics products. The developer portal provides a [coverage matrix](https://developer.sportradar.com/getting-started/) and product-specific API docs. | Product-specific feeds can provide scheduled, live and historical data with provider timestamps, but retention and replay rights depend on contract. | Authenticated REST/other APIs via developer portal; trial/marketplace access is product-specific. | Public documentation does not publish a universal price or rate limit. Commercial quote and contract required. | Strongest data/licensing controls, but contract restrictions, cost, and integration overhead are substantial. | **Enterprise fallback**, not suitable as first MVP provider unless funding/partnership requires it. |

## Coverage and Market Scope

The initial MVP should restrict itself to leagues that both sources cover consistently. Start with a small league allow-list (for example, one or two top European leagues plus the English pyramid available in Football-Data.co.uk) and expand only after identity and timestamp checks pass.

For the first release, ingest:

- Fixtures and kickoff times
- Full-time results and, where available, half-time results
- 1X2, totals and Asian-handicap odds
- Match shots, shots on target and corners only where Football-Data definitions are present and stable

Do not publish corner selections until the odds provider supplies the same line definition and the historical source has enough complete observations. Do not infer lineups, injuries or xG from a provider that has not been licensed for those fields.

## Timestamp Contract

Every stored record must include:

- `source_provider`
- `source_event_id` (or deterministic file/row key for CSV data)
- `retrieved_at` (UTC)
- `observed_at` or provider `last_update` when supplied
- `published_at` when supplied
- `match_start_at` (UTC)
- `data_as_of` used by the feature/model job

For Football-Data.co.uk CSVs, `retrieved_at` is the time Safe Picks downloaded the file; the file's odds are not assumed to be available continuously. For The Odds API, `retrieved_at` is the request time and bookmaker `last_update` is the quote timestamp. Predictions must use only rows whose availability timestamp is at or before the prediction timestamp.

## Rate-Limit and Ingestion Policy

Implement provider-specific adapters with a shared budget interface:

- Cache by provider, endpoint, parameters and date window.
- Poll fixtures once or twice daily; poll odds on a bounded schedule (for example, every 15-30 minutes) only for upcoming matches.
- Read quota headers when available and maintain a local request ledger.
- Back off on HTTP 429/5xx and stop when the budget is exhausted.
- Save immutable raw response snapshots before normalization.
- Never use a scraping loop against provider web pages to bypass an API limit.

The exact interval is an engineering default, not a provider guarantee; tune it after observing the account's documented quota.

## Licensing Gate

Phase 3 cannot be considered complete until the project records, per provider:

1. Account/plan name and effective date.
2. Leagues and markets included.
3. Historical retention and replay rights.
4. Whether model training and derived predictions are allowed.
5. Whether raw odds/statistics may be shown to Telegram users.
6. Whether commercial use, paid subscriptions, and bookmaker code generation are allowed.
7. Attribution and caching requirements.
8. Data deletion/retention obligations.

Until those fields are confirmed, the bot should remain a private paper-trading tool and should not redistribute raw provider payloads.

## Recommendation for Phase 3 Implementation

Create these adapters first:

```text
FootballDataCsvAdapter     historical results/stats/odds files
OddsApiAdapter             current bookmaker snapshots
ProviderRegistry           coverage/licence/quota metadata
RawSnapshotStore           immutable payload/file storage
IdentityResolver           teams, competitions, fixtures, markets
```

Build and replay one league before adding more. Validate that a historical fixture can be reconstructed exactly from the saved CSV and odds snapshots. If The Odds API historical endpoint is unavailable on the chosen plan, use Football-Data.co.uk historical odds only for baseline research and mark current-period paper trades as having no historical odds replay; do not backfill timestamps that were not actually observed.

## Sources

- Football-Data.co.uk home and downloads: https://www.football-data.co.uk/
- League download example: https://www.football-data.co.uk/englandm.php
- Data dictionary and source acknowledgements: https://www.football-data.co.uk/notes.txt
- Disclaimer: https://www.football-data.co.uk/disclaimer.php
- The Odds API home: https://the-odds-api.com/
- The Odds API v4 documentation: https://the-odds-api.com/liveapi/guides/v4/
- The Odds API terms: https://the-odds-api.com/terms
- API-Football home: https://www.api-football.com/
- API-Football v3 documentation: https://www.api-football.com/documentation-v3
- Sportradar developer portal and coverage entry point: https://developer.sportradar.com/getting-started/

## Evidence Notes

The review was conducted against publicly accessible provider pages. API-Football documentation/pricing and The Odds API pages may require JavaScript, an account, or may be rate-limited. Where an official page did not expose a stable public price/quota/licence statement, this document records the value as unknown and makes account verification a release gate. No provider price, quota, coverage figure, or licensing right is fabricated.
