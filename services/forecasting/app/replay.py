import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .providers.identity import FixtureIdentity, resolve_fixture_identity
from .providers.models import FixtureRecord


@dataclass(frozen=True)
class ReplayedFixture:
    record: FixtureRecord
    identity: FixtureIdentity
    manifest_path: str
    manifest_retrieved_at: datetime
    raw_snapshot_sha256: str


@dataclass(frozen=True)
class ReplayResult:
    as_of: datetime
    fixtures: tuple[ReplayedFixture, ...]
    manifest_paths: tuple[str, ...]


class HistoricalManifestReplay:
    def __init__(
        self,
        root: str | Path,
        provider: str = "football-data.co.uk",
        league: str | None = None,
        season: str | None = None,
    ):
        self.root = Path(root)
        self.provider = provider
        self.league = league
        self.season = season

    def replay(self, as_of: datetime) -> ReplayResult:
        if as_of.tzinfo is None:
            raise ValueError("as_of timestamp must include a timezone")
        selected: dict[str, ReplayedFixture] = {}
        manifest_paths: list[str] = []
        for path in self._manifest_paths():
            payload = self._read_manifest(path)
            if payload.get("provider") != self.provider:
                continue
            if self.league is not None and payload.get("league") != self.league:
                continue
            if self.season is not None and payload.get("season") != self.season:
                continue
            manifest_retrieved_at = self._timestamp(payload.get("retrieved_at"), "retrieved_at", path)
            if manifest_retrieved_at > as_of:
                continue
            manifest_paths.append(str(path))
            raw_snapshot_sha256 = str(payload.get("raw_snapshot_sha256", ""))
            for value in payload.get("fixtures", []):
                record = self._record_from_manifest(value)
                identity = resolve_fixture_identity(record, self.season or record.season)
                candidate = ReplayedFixture(
                    record=record,
                    identity=identity,
                    manifest_path=str(path),
                    manifest_retrieved_at=manifest_retrieved_at,
                    raw_snapshot_sha256=raw_snapshot_sha256,
                )
                existing = selected.get(identity.canonical_fixture_id)
                if existing is None or candidate.manifest_retrieved_at > existing.manifest_retrieved_at:
                    selected[identity.canonical_fixture_id] = candidate
        fixtures = tuple(sorted(selected.values(), key=lambda item: item.identity.canonical_fixture_id))
        return ReplayResult(as_of, fixtures, tuple(sorted(manifest_paths)))

    def _manifest_paths(self) -> list[Path]:
        directory = self.root / "normalized" / self.provider
        if not directory.exists():
            return []
        return sorted(directory.rglob("*.json"))

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"Unable to read normalized manifest: {path}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("fixtures", []), list):
            raise ValueError(f"Invalid normalized manifest shape: {path}")
        return value

    @staticmethod
    def _timestamp(value: object, field: str, path: Path) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"Manifest {path} is missing {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Manifest {path} has invalid {field}") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"Manifest {path} {field} must include a timezone")
        return parsed

    def _record_from_manifest(self, value: object) -> FixtureRecord:
        if not isinstance(value, dict):
            raise ValueError("Manifest fixture must be an object")
        try:
            return FixtureRecord(
                provider=str(value["provider"]),
                source_event_id=str(value["source_event_id"]),
                home_team=str(value["home_team"]),
                away_team=str(value["away_team"]),
                match_start_at=self._timestamp(value.get("match_start_at"), "match_start_at", Path("manifest")),
                retrieved_at=self._timestamp(value.get("retrieved_at"), "retrieved_at", Path("manifest")),
                observed_at=self._optional_timestamp(value.get("observed_at")),
                competition=value.get("competition"),
                season=value.get("season"),
                home_goals=value.get("home_goals"),
                away_goals=value.get("away_goals"),
                half_time_home_goals=value.get("half_time_home_goals"),
                half_time_away_goals=value.get("half_time_away_goals"),
                home_corners=value.get("home_corners"),
                away_corners=value.get("away_corners"),
                home_shots=value.get("home_shots"),
                away_shots=value.get("away_shots"),
                home_shots_on_target=value.get("home_shots_on_target"),
                away_shots_on_target=value.get("away_shots_on_target"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid fixture in normalized manifest") from exc

    @staticmethod
    def _optional_timestamp(value: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Optional timestamp must be a string")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("Optional timestamp must include a timezone")
        return parsed
