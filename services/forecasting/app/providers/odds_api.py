import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .identity import resolve_market_quotes
from .models import OddsQuote, parse_datetime


class OddsApiAdapter:
    provider = "the-odds-api"

    def __init__(self, api_key: str, base_url: str = "https://api.the-odds-api.com/v4"):
        if not api_key:
            raise ValueError("The Odds API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def fetch_sports(self) -> tuple[bytes, dict[str, str]]:
        return self._get("/sports", {})

    def fetch_odds(self, sport: str, regions: str = "eu", markets: str = "h2h,totals", odds_format: str = "decimal") -> tuple[bytes, dict[str, str]]:
        return self._get(
            f"/sports/{sport}/odds",
            {"regions": regions, "markets": markets, "oddsFormat": odds_format},
        )

    def parse_odds(self, payload: bytes, retrieved_at: datetime | None = None) -> list[OddsQuote]:
        retrieved = retrieved_at or datetime.now(timezone.utc)
        events = json.loads(payload.decode("utf-8"))
        quotes: list[OddsQuote] = []
        for event in events:
            match_start = parse_datetime(event["commence_time"])
            for bookmaker in event.get("bookmakers", []):
                observed = parse_datetime(bookmaker["last_update"]) if bookmaker.get("last_update") else None
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        quote = OddsQuote(
                            provider=self.provider,
                            source_event_id=str(event["id"]),
                            bookmaker=bookmaker["key"],
                            market=market["key"],
                            selection=outcome["name"],
                            odds=float(outcome["price"]),
                            match_start_at=match_start,
                            retrieved_at=retrieved,
                            observed_at=observed,
                            line=float(outcome["point"]) if outcome.get("point") is not None else None,
                        )
                        quotes.append(quote)
        normalized_quotes, _ = resolve_market_quotes(quotes)
        return normalized_quotes

    def _get(self, path: str, params: dict[str, str]) -> tuple[bytes, dict[str, str]]:
        query = urlencode({**params, "apiKey": self.api_key})
        request = Request(f"{self.base_url}{path}?{query}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.read(), headers
