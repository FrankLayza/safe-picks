import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.odds_ingestion import OddsApiIngestionJob, OddsIngestionPolicy
from app.providers.identity import resolve_fixture_identity
from app.providers.models import FixtureRecord
from app.replay import ReplayedFixture


class OddsIngestionTests(unittest.TestCase):
    retrieved = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    kickoff = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)

    def history_fixture(
        self,
        days: int,
        home: str,
        away: str,
    ) -> ReplayedFixture:
        kickoff = self.retrieved - timedelta(days=days)
        record = FixtureRecord(
            provider="football-data.co.uk",
            source_event_id=f"history-{days}-{home}-{away}",
            home_team=home,
            away_team=away,
            match_start_at=kickoff,
            retrieved_at=kickoff + timedelta(hours=2),
            competition="E0",
            season="2526",
            home_goals=2,
            away_goals=1,
        )
        return ReplayedFixture(
            record,
            resolve_fixture_identity(record),
            f"manifest-{days}",
            record.retrieved_at,
            f"sha-{days}",
        )

    def history(self) -> list[ReplayedFixture]:
        return [
            self.history_fixture(30, "Man United", "Arsenal"),
            self.history_fixture(20, "Spurs", "Chelsea"),
        ]

    def payload(
        self,
        *,
        event_id: str = "event-1",
        home_team: str = "Manchester United",
        away_team: str = "Tottenham Hotspur",
        last_update: str = "2026-08-29T11:55:00Z",
        h2h_outcomes: list[dict[str, object]] | None = None,
    ) -> bytes:
        result_outcomes = h2h_outcomes or [
            {"name": home_team, "price": 2.1},
            {"name": "Draw", "price": 3.4},
            {"name": away_team, "price": 3.6},
        ]
        return json.dumps(
            [
                {
                    "id": event_id,
                    "sport_key": "soccer_epl",
                    "sport_title": "EPL",
                    "commence_time": self.kickoff.isoformat(),
                    "home_team": home_team,
                    "away_team": away_team,
                    "bookmakers": [
                        {
                            "key": "book-a",
                            "last_update": last_update,
                            "markets": [
                                {"key": "h2h", "outcomes": result_outcomes},
                                {
                                    "key": "totals",
                                    "outcomes": [
                                        {"name": "Over", "price": 1.8, "point": 2.5},
                                        {"name": "Under", "price": 2.0, "point": 2.5},
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        ).encode()

    def run_job(
        self,
        directory: str,
        payload: bytes,
        history: list[ReplayedFixture] | None = None,
    ) -> dict[str, object]:
        job = OddsApiIngestionJob(
            directory,
            api_key="secret-key",
            season="2627",
            base_url="https://example.test/v4",
            fetcher=lambda: (
                payload,
                {
                    "x-requests-remaining": "498",
                    "x-requests-used": "2",
                },
            ),
            clock=lambda: self.retrieved,
            history_loader=lambda _: history if history is not None else self.history(),
        )
        path = job.run_once()
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_run_once_stores_raw_snapshot_and_normalizes_matched_events(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(directory, self.payload())

            self.assertEqual(manifest["status"], "pass")
            self.assertEqual(manifest["event_count"], 1)
            self.assertEqual(manifest["quote_count"], 5)
            self.assertEqual(
                manifest["events"][0]["canonical_home_team"],
                "manchester united",
            )
            self.assertEqual(
                manifest["events"][0]["canonical_away_team"],
                "tottenham hotspur",
            )
            self.assertEqual(manifest["events"][0]["historical_home_matches"], 1)
            self.assertEqual(manifest["events"][0]["historical_away_matches"], 1)
            self.assertEqual(manifest["request_usage"]["x-requests-remaining"], "498")
            self.assertNotIn("secret-key", manifest["source_url"])
            self.assertTrue(Path(manifest["raw_snapshot_path"]).exists())

    def test_stale_quotes_reject_event_with_machine_readable_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(
                directory,
                self.payload(last_update="2026-08-29T10:00:00Z"),
            )

            codes = {item["code"] for item in manifest["rejections"]}
            self.assertEqual(manifest["status"], "rejected")
            self.assertEqual(manifest["event_count"], 0)
            self.assertIn("stale_odds_quote", codes)
            self.assertIn("no_complete_current_market", codes)

    def test_unknown_historical_team_rejects_event(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(
                directory,
                self.payload(away_team="Unknown FC"),
            )

            reason = next(
                item
                for item in manifest["rejections"]
                if item["code"] == "historical_team_not_found"
            )
            self.assertEqual(reason["details"]["missing_sides"], ["away"])

    def test_incomplete_market_group_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(
                directory,
                self.payload(
                    h2h_outcomes=[
                        {"name": "Manchester United", "price": 2.1},
                        {"name": "Tottenham Hotspur", "price": 3.6},
                    ]
                ),
            )

            codes = {item["code"] for item in manifest["rejections"]}
            self.assertEqual(manifest["status"], "partial")
            self.assertEqual(manifest["quote_count"], 2)
            self.assertIn("incomplete_market_group", codes)

    def test_wrong_result_selections_are_rejected_even_with_three_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(
                directory,
                self.payload(
                    h2h_outcomes=[
                        {"name": "Manchester United", "price": 2.1},
                        {"name": "Draw", "price": 3.4},
                        {"name": "Unknown FC", "price": 3.6},
                    ]
                ),
            )

            incomplete = next(
                item
                for item in manifest["rejections"]
                if item["code"] == "incomplete_market_group"
            )
            self.assertFalse(incomplete["details"]["selections_valid"])
            self.assertEqual(manifest["quote_count"], 2)

    def test_duplicate_canonical_fixture_is_rejected_as_ambiguous(self):
        values = json.loads(self.payload().decode())
        duplicate = dict(values[0])
        duplicate["id"] = "event-2"
        values.append(duplicate)
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(directory, json.dumps(values).encode())

            codes = [item["code"] for item in manifest["rejections"]]
            self.assertEqual(manifest["event_count"], 0)
            self.assertEqual(codes.count("ambiguous_canonical_fixture"), 2)

    def test_duplicate_source_event_id_is_rejected(self):
        values = json.loads(self.payload().decode())
        values.append(dict(values[0]))
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(directory, json.dumps(values).encode())

            codes = [item["code"] for item in manifest["rejections"]]
            self.assertEqual(manifest["event_count"], 0)
            self.assertEqual(codes.count("duplicate_source_event_id"), 2)

    def test_malformed_event_writes_rejected_diagnostic_manifest(self):
        malformed = json.dumps(
            [
                {
                    "id": "event-1",
                    "sport_key": "soccer_epl",
                    "sport_title": "EPL",
                    "commence_time": self.kickoff.isoformat(),
                    "away_team": "Tottenham Hotspur",
                }
            ]
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.run_job(directory, malformed)

            self.assertEqual(manifest["status"], "rejected")
            self.assertEqual(manifest["event_count"], 0)
            self.assertEqual(
                manifest["rejections"][0]["code"],
                "odds_event_missing_required_field",
            )

    def test_snapshot_freshness_policy_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            job = OddsApiIngestionJob(
                directory,
                api_key="secret-key",
                season="2627",
                fetcher=lambda: (self.payload(), {}),
                clock=lambda: self.retrieved,
                quality_reference_clock=lambda: self.retrieved + timedelta(minutes=16),
                history_loader=lambda _: self.history(),
                policy=OddsIngestionPolicy(
                    max_snapshot_age=timedelta(minutes=15),
                    max_quote_age=timedelta(minutes=30),
                ),
            )
            with self.assertRaisesRegex(ValueError, "ingestion quality checks failed"):
                job.run_once()

    def test_naive_job_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            job = OddsApiIngestionJob(
                directory,
                api_key="secret-key",
                season="2627",
                fetcher=lambda: (self.payload(), {}),
                clock=lambda: self.retrieved.replace(tzinfo=None),
                history_loader=lambda _: self.history(),
            )
            with self.assertRaisesRegex(ValueError, "must include a timezone"):
                job.run_once()


if __name__ == "__main__":
    unittest.main()
