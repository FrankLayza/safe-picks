import csv
import io
from datetime import datetime, timezone
from typing import Iterable

from .models import FixtureRecord, to_int


class FootballDataCsvAdapter:
    provider = "football-data.co.uk"

    def parse(self, payload: bytes, retrieved_at: datetime, competition: str | None = None) -> list[FixtureRecord]:
        text = payload.decode("utf-8-sig")
        rows: Iterable[dict[str, str]] = csv.DictReader(io.StringIO(text))
        records: list[FixtureRecord] = []
        for row_number, row in enumerate(rows, start=2):
            date = (row.get("Date") or "").strip()
            if not date:
                continue
            try:
                match_date = datetime.strptime(date, "%d/%m/%Y").replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError(f"Invalid match date on CSV row {row_number}: {date}") from exc
            records.append(
                FixtureRecord(
                    provider=self.provider,
                    source_event_id=f"{competition or 'unknown'}:{date}:{row.get('HomeTeam')}:{row.get('AwayTeam')}",
                    home_team=(row.get("HomeTeam") or "").strip(),
                    away_team=(row.get("AwayTeam") or "").strip(),
                    match_start_at=match_date,
                    retrieved_at=retrieved_at,
                    competition=competition,
                    home_goals=to_int(row.get("FTHG")),
                    away_goals=to_int(row.get("FTAG")),
                    half_time_home_goals=to_int(row.get("HTHG")),
                    half_time_away_goals=to_int(row.get("HTAG")),
                    home_corners=to_int(row.get("HC")),
                    away_corners=to_int(row.get("AC")),
                    home_shots=to_int(row.get("HS")),
                    away_shots=to_int(row.get("AS")),
                    home_shots_on_target=to_int(row.get("HST")),
                    away_shots_on_target=to_int(row.get("AST")),
                )
            )
        return records

