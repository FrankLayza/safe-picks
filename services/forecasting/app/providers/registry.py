from .models import ProviderMetadata


class ProviderRegistry:
    def __init__(self, providers: tuple[ProviderMetadata, ...]):
        self._providers = {provider.provider: provider for provider in providers}

    def get(self, provider: str) -> ProviderMetadata:
        try:
            return self._providers[provider]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {provider}") from exc

    def all(self) -> tuple[ProviderMetadata, ...]:
        return tuple(self._providers.values())


def default_registry() -> ProviderRegistry:
    return ProviderRegistry(
        (
            ProviderMetadata(
                provider="football-data.co.uk",
                role="historical_backfill",
                coverage=("results", "match_stats", "historical_odds"),
                license_status="free_download; commercial_redistribution_unverified",
                rate_limit_policy="no_public_api_quota; scheduled_download_and_cache",
                retention_policy="retain_private_raw_snapshots_until_license_review",
            ),
            ProviderMetadata(
                provider="the-odds-api",
                role="current_odds_snapshot",
                coverage=("fixtures", "bookmaker_odds"),
                license_status="account_terms_required",
                rate_limit_policy="quota_headers_and_plan_limits",
                retention_policy="retain_private_raw_snapshots_per_plan_terms",
            ),
        )
    )
