import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .identity import resolve_market_quotes
from .models import OddsEvent, OddsQuote, parse_datetime


class OddsApiPayloadError(ValueError):
    def __init__(self, message: str, reasons: list[dict[str, object]]):
        super().__init__(message)
        self.code = "odds_payload_rejected"
        self.reasons = reasons


@dataclass(frozen=True)
class ParsedOddsSnapshot:
    events: tuple[OddsEvent, ...]
    quotes: tuple[OddsQuote, ...]
    rejections: tuple[dict[str, object], ...]
    identity_audit: dict[str, object]


class OddsApiAdapter:
    provider = "the-odds-api"

    def __init__(self, api_key: str, base_url: str = "https://api.the-odds-api.com/v4"):
        if not api_key:
            raise ValueError("The Odds API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def fetch_sports(self) -> tuple[bytes, dict[str, str]]:
        return self._get("/sports", {})

    def fetch_odds(
        self,
        sport: str,
        regions: str = "eu",
        markets: str = "h2h,totals",
        odds_format: str = "decimal",
    ) -> tuple[bytes, dict[str, str]]:
        return self._get(
            f"/sports/{sport}/odds",
            {"regions": regions, "markets": markets, "oddsFormat": odds_format},
        )

    def odds_source_url(
        self,
        sport: str,
        regions: str = "eu",
        markets: str = "h2h,totals",
        odds_format: str = "decimal",
    ) -> str:
        query = urlencode(
            {
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            }
        )
        return f"{self.base_url}/sports/{sport}/odds?{query}"

    def parse_snapshot(
        self,
        payload: bytes,
        retrieved_at: datetime,
        season: str,
        competition_fallback: str | None = None,
    ) -> ParsedOddsSnapshot:
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OddsApiPayloadError(
                "The Odds API payload is not valid JSON",
                [_reason("invalid_json_payload", {})],
            ) from exc
        if not isinstance(decoded, list):
            raise OddsApiPayloadError(
                "The Odds API payload must be a list of events",
                [_reason("invalid_payload_shape", {"expected": "event_list"})],
            )
        if not decoded:
            raise OddsApiPayloadError(
                "The Odds API payload contains no events",
                [_reason("empty_payload", {"event_count": 0})],
            )

        events: list[OddsEvent] = []
        quotes: list[OddsQuote] = []
        rejections: list[dict[str, object]] = []
        for event_index, value in enumerate(decoded):
            if not isinstance(value, dict):
                rejections.append(
                    _reason("invalid_event_shape", {"event_index": event_index})
                )
                continue
            event_id = _required_text(value.get("id"))
            home_team = _required_text(value.get("home_team"))
            away_team = _required_text(value.get("away_team"))
            sport_key = _required_text(value.get("sport_key"))
            competition = _required_text(value.get("sport_title")) or competition_fallback
            missing = [
                field
                for field, field_value in (
                    ("id", event_id),
                    ("home_team", home_team),
                    ("away_team", away_team),
                    ("sport_key", sport_key),
                    ("competition", competition),
                    ("season", season),
                )
                if not field_value
            ]
            if missing:
                rejections.append(
                    _reason(
                        "odds_event_missing_required_field",
                        {"event_index": event_index, "fields": missing},
                    )
                )
                continue
            try:
                match_start = parse_datetime(str(value.get("commence_time", "")))
            except (AttributeError, TypeError, ValueError):
                rejections.append(
                    _reason(
                        "odds_event_invalid_kickoff",
                        {"event_index": event_index, "source_event_id": event_id},
                    )
                )
                continue

            event = OddsEvent(
                provider=self.provider,
                source_event_id=event_id,
                sport_key=sport_key,
                competition=str(competition),
                season=season,
                home_team=home_team,
                away_team=away_team,
                match_start_at=match_start,
                retrieved_at=retrieved_at,
            )
            events.append(event)
            bookmakers = value.get("bookmakers", [])
            if not isinstance(bookmakers, list):
                rejections.append(
                    _reason(
                        "invalid_bookmaker_collection",
                        {"source_event_id": event_id},
                    )
                )
                continue
            for bookmaker_index, bookmaker in enumerate(bookmakers):
                if not isinstance(bookmaker, dict):
                    rejections.append(
                        _reason(
                            "invalid_bookmaker_shape",
                            {
                                "source_event_id": event_id,
                                "bookmaker_index": bookmaker_index,
                            },
                        )
                    )
                    continue
                bookmaker_key = _required_text(bookmaker.get("key"))
                try:
                    observed = (
                        parse_datetime(str(bookmaker["last_update"]))
                        if bookmaker.get("last_update")
                        else None
                    )
                except (AttributeError, TypeError, ValueError):
                    rejections.append(
                        _reason(
                            "odds_quote_invalid_timestamp",
                            {
                                "source_event_id": event_id,
                                "bookmaker": bookmaker_key,
                            },
                        )
                    )
                    continue
                markets = bookmaker.get("markets", [])
                if not bookmaker_key or not isinstance(markets, list):
                    rejections.append(
                        _reason(
                            "invalid_bookmaker_payload",
                            {
                                "source_event_id": event_id,
                                "bookmaker_index": bookmaker_index,
                            },
                        )
                    )
                    continue
                for market_index, market in enumerate(markets):
                    if not isinstance(market, dict):
                        rejections.append(
                            _reason(
                                "invalid_market_shape",
                                {
                                    "source_event_id": event_id,
                                    "bookmaker": bookmaker_key,
                                    "market_index": market_index,
                                },
                            )
                        )
                        continue
                    market_key = _required_text(market.get("key"))
                    outcomes = market.get("outcomes", [])
                    if not market_key or not isinstance(outcomes, list):
                        rejections.append(
                            _reason(
                                "invalid_market_payload",
                                {
                                    "source_event_id": event_id,
                                    "bookmaker": bookmaker_key,
                                    "market_index": market_index,
                                },
                            )
                        )
                        continue
                    for outcome_index, outcome in enumerate(outcomes):
                        quote = self._parse_quote(
                            outcome,
                            event,
                            bookmaker_key,
                            market_key,
                            observed,
                            outcome_index,
                            rejections,
                        )
                        if quote is not None:
                            quotes.append(quote)
        normalized, audit = resolve_market_quotes(quotes)
        return ParsedOddsSnapshot(
            tuple(events),
            tuple(normalized),
            tuple(rejections),
            audit,
        )

    def _parse_quote(
        self,
        outcome: object,
        event: OddsEvent,
        bookmaker: str,
        market: str,
        observed_at: datetime | None,
        outcome_index: int,
        rejections: list[dict[str, object]],
    ) -> OddsQuote | None:
        if not isinstance(outcome, dict):
            rejections.append(
                _reason(
                    "invalid_outcome_shape",
                    {
                        "source_event_id": event.source_event_id,
                        "bookmaker": bookmaker,
                        "market": market,
                        "outcome_index": outcome_index,
                    },
                )
            )
            return None
        selection = _required_text(outcome.get("name"))
        try:
            odds = float(outcome["price"])
            line = float(outcome["point"]) if outcome.get("point") is not None else None
        except (KeyError, TypeError, ValueError):
            odds = 0.0
            line = None
        if not selection or odds <= 1:
            rejections.append(
                _reason(
                    "invalid_odds_quote",
                    {
                        "source_event_id": event.source_event_id,
                        "bookmaker": bookmaker,
                        "market": market,
                        "outcome_index": outcome_index,
                    },
                )
            )
            return None
        return OddsQuote(
            provider=self.provider,
            source_event_id=event.source_event_id,
            bookmaker=bookmaker,
            market=market,
            selection=selection,
            odds=odds,
            match_start_at=event.match_start_at,
            retrieved_at=event.retrieved_at,
            observed_at=observed_at,
            line=line,
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


def _required_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _reason(code: str, details: dict[str, object]) -> dict[str, object]:
    return {"code": code, "details": details}
