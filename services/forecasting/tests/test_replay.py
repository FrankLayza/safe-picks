import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.replay import HistoricalManifestReplay


def write_manifest(root: str, name: str, retrieved_at: datetime, fixtures: list[dict[str, object]], sha: str) -> Path:
    path = Path(root) / "normalized" / "football-data.co.uk" / retrieved_at.strftime("%Y-%m-%d") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "provider": "football-data.co.uk",
                "league": "E0",
                "season": "2526",
                "retrieved_at": retrieved_at.isoformat(),
                "raw_snapshot_sha256": sha,
                "fixtures": fixtures,
            }
        ),
        encoding="utf-8",
    )
    return path


def fixture(retrieved_at: datetime, home_goals: int | None, away_goals: int | None) -> dict[str, object]:
    return {
        "provider": "football-data.co.uk",
        "source_event_id": "E0:24/08/2026:Home FC:Away FC",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "match_start_at": "2026-08-24T18:00:00+00:00",
        "retrieved_at": retrieved_at.isoformat(),
        "observed_at": None,
        "competition": "E0",
        "season": "2526",
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


class HistoricalReplayTests(unittest.TestCase):
    before_kickoff = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    after_kickoff = datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)

    def test_as_of_excludes_manifests_retrieved_in_the_future(self):
        with tempfile.TemporaryDirectory() as directory:
            write_manifest(
                directory,
                "120000-before.json",
                self.before_kickoff,
                [fixture(self.before_kickoff, None, None)],
                "before-sha",
            )
            write_manifest(
                directory,
                "200000-after.json",
                self.after_kickoff,
                [fixture(self.after_kickoff, 2, 1)],
                "after-sha",
            )

            result = HistoricalManifestReplay(directory).replay(self.before_kickoff)

            self.assertEqual(len(result.fixtures), 1)
            self.assertIsNone(result.fixtures[0].record.home_goals)
            self.assertEqual(result.fixtures[0].raw_snapshot_sha256, "before-sha")

    def test_replay_uses_latest_observation_available_at_as_of(self):
        first = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
        second = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            write_manifest(directory, "120000-first.json", first, [fixture(first, None, None)], "first-sha")
            write_manifest(directory, "100000-second.json", second, [fixture(second, 2, 1)], "second-sha")

            result = HistoricalManifestReplay(directory).replay(self.before_kickoff)

            self.assertEqual(result.fixtures[0].record.home_goals, 2)
            self.assertEqual(result.fixtures[0].manifest_retrieved_at, second)
            self.assertEqual(result.manifest_paths, tuple(sorted(result.manifest_paths)))

    def test_replay_requires_timezone_aware_as_of(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "timezone"):
                HistoricalManifestReplay(directory).replay(datetime(2026, 8, 24, 12, 0))

    def test_replay_filters_provider_league_and_season(self):
        retrieved = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = write_manifest(directory, "120000.json", retrieved, [fixture(retrieved, 2, 1)], "sha")
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["league"] = "D1"
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = HistoricalManifestReplay(directory, league="E0").replay(self.before_kickoff)

            self.assertEqual(result.fixtures, ())


if __name__ == "__main__":
    unittest.main()
