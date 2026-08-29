import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.candidates import generate_candidates
from app.providers.identity import resolve_fixture_identity
from app.providers.models import FixtureRecord


class CandidateGenerationTests(unittest.TestCase):
    as_of = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    kickoff = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)

    def _history_manifest(self, root: str) -> None:
        fixtures = []
        for index in range(6):
            match_start = self.as_of - timedelta(days=index + 1)
            home, away = ("Man United", "Spurs") if index % 2 == 0 else ("Spurs", "Man United")
            record = FixtureRecord(
                provider="football-data.co.uk",
                source_event_id=f"history-{index}",
                home_team=home,
                away_team=away,
                match_start_at=match_start,
                retrieved_at=match_start + timedelta(hours=2),
                competition="E0",
                season="2526",
                home_goals=2 if index % 2 == 0 else 1,
                away_goals=1,
            )
            identity = resolve_fixture_identity(record)
            value = {
                **record.__dict__,
                "match_start_at": record.match_start_at.isoformat(),
                "retrieved_at": record.retrieved_at.isoformat(),
                "observed_at": None,
                "canonical_competition_id": identity.canonical_competition_id,
                "canonical_home_team_id": identity.canonical_home_team_id,
                "canonical_home_team": identity.canonical_home_team,
                "canonical_away_team_id": identity.canonical_away_team_id,
                "canonical_away_team": identity.canonical_away_team,
                "canonical_fixture_id": identity.canonical_fixture_id,
                "provider": record.provider,
            }
            fixtures.append(value)
        directory = Path(root) / "normalized" / "football-data.co.uk" / "2026-08-29"
        directory.mkdir(parents=True)
        (directory / "120000-history.json").write_text(
            json.dumps(
                {
                    "provider": "football-data.co.uk",
                    "league": "E0",
                    "season": "2526",
                    "retrieved_at": self.as_of.isoformat(),
                    "raw_snapshot_sha256": "history-sha",
                    "fixtures": fixtures,
                }
            ),
            encoding="utf-8",
        )

    def _odds_manifest(self, root: str) -> None:
        event_record = FixtureRecord(
            provider="the-odds-api",
            source_event_id="event-1",
            home_team="Manchester United",
            away_team="Tottenham Hotspur",
            match_start_at=self.kickoff,
            retrieved_at=self.as_of,
            competition="EPL",
            season="2627",
        )
        identity = resolve_fixture_identity(event_record)
        quotes = [
            ("Manchester United", 2.1, None),
            ("Draw", 3.4, None),
            ("Tottenham Hotspur", 3.6, None),
            ("Over", 1.8, 1.5),
            ("Under", 2.0, 1.5),
        ]
        quote_values = []
        for selection, odds, line in quotes:
            quote_values.append(
                {
                    "provider": "the-odds-api",
                    "source_event_id": "event-1",
                    "bookmaker": "book-a",
                    "market": "h2h" if line is None else "totals",
                    "canonical_market": "match result" if line is None else "total",
                    "canonical_selection": selection.casefold(),
                    "selection": selection,
                    "odds": odds,
                    "line": line,
                    "canonical_line": "none" if line is None else str(line),
                    "match_start_at": self.kickoff.isoformat(),
                    "retrieved_at": self.as_of.isoformat(),
                    "observed_at": (self.as_of - timedelta(minutes=2)).isoformat(),
                }
            )
        directory = Path(root) / "normalized" / "the-odds-api" / "2026-08-29"
        directory.mkdir(parents=True)
        (directory / "120000-odds.json").write_text(
            json.dumps(
                {
                    "provider": "the-odds-api",
                    "retrieved_at": self.as_of.isoformat(),
                    "status": "pass",
                    "event_count": 1,
                    "quote_count": len(quote_values),
                    "events": [
                        {
                            "source_event_id": "event-1",
                            "home_team": "Manchester United",
                            "away_team": "Tottenham Hotspur",
                            "match_start_at": self.kickoff.isoformat(),
                            **{
                                "canonical_competition_id": identity.canonical_competition_id,
                                "canonical_home_team_id": identity.canonical_home_team_id,
                                "canonical_home_team": identity.canonical_home_team,
                                "canonical_away_team_id": identity.canonical_away_team_id,
                                "canonical_away_team": identity.canonical_away_team,
                                "canonical_fixture_id": identity.canonical_fixture_id,
                            },
                            "historical_home_matches": 6,
                            "historical_away_matches": 6,
                        }
                    ],
                    "quotes": quote_values,
                }
            ),
            encoding="utf-8",
        )

    def _calibration(self, root: str) -> str:
        path = Path(root) / "calibration.json"
        markets = {
            key: {"thresholds": [0.0, 1.0], "values": [0.01, 0.99], "calibration_error": 0.04}
            for key in ("home_win", "draw", "away_win", "over_1.5")
        }
        path.write_text(json.dumps({"version": "isotonic-v1", "markets": markets}), encoding="utf-8")
        return str(path)

    def test_generates_model_backed_result_and_totals_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            self._history_manifest(root)
            self._odds_manifest(root)
            result = generate_candidates(root, now=self.as_of, min_training_matches=2, calibration_artifact=self._calibration(root))

            self.assertEqual(result.source_manifest.endswith("120000-odds.json"), True)
            self.assertEqual(len(result.candidates), 5)
            self.assertTrue(all(item["status"] == "eligible" for item in result.candidates))
            self.assertTrue(all(item["modelVersion"].endswith("+calibrated") for item in result.candidates))
            self.assertTrue(all(item["fairProbability"] > 0 for item in result.candidates))
            self.assertTrue(all(item["expectedValue"] == item["modelProbability"] * item["odds"] - 1 for item in result.candidates))
            self.assertTrue(all(item["rankingScore"] <= max(0, item["estimatedEdge"]) for item in result.candidates))
            self.assertEqual(
                [item["rankingScore"] for item in result.candidates],
                sorted((item["rankingScore"] for item in result.candidates), reverse=True),
            )
            result_probabilities = [item["modelProbability"] for item in result.candidates if item["market"] == "match_result"]
            total_probabilities = [item["modelProbability"] for item in result.candidates if item["market"] == "goals_over_under"]
            self.assertAlmostEqual(sum(result_probabilities), 1.0)
            self.assertAlmostEqual(sum(total_probabilities), 1.0)
            self.assertIn("goals_over_under", {item["market"] for item in result.candidates})
            self.assertIn("match_result", {item["market"] for item in result.candidates})

    def test_missing_calibration_abstains_without_mock_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            self._history_manifest(root)
            self._odds_manifest(root)
            result = generate_candidates(root, now=self.as_of, min_training_matches=2)

            self.assertEqual(len(result.candidates), 5)
            self.assertTrue(all(item["status"] == "abstain" for item in result.candidates))
            self.assertTrue(all(item["rankingScore"] == 0 for item in result.candidates))
            self.assertIn("calibration_artifact_unavailable", {item["code"] for item in result.diagnostics})

    def test_missing_manifest_returns_machine_readable_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            result = generate_candidates(root, now=self.as_of)

            self.assertEqual(result.candidates, ())
            self.assertIn("odds_manifest_directory_missing", {item["code"] for item in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
