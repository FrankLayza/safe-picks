import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.providers.football_data import FootballDataCsvAdapter
from app.providers.models import parse_datetime
from app.providers.odds_api import OddsApiAdapter
from app.providers.raw_store import FileRawSnapshotStore
from app.providers.registry import default_registry


class ProviderTests(unittest.TestCase):
    retrieved = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

    def test_football_data_csv_normalizes_results_and_stats(self):
        csv_payload = b"Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HC,AC\n23/08/2026,Home FC,Away FC,2,1,H,1,0,H,14,8,6,3,7,4\n"

        records = FootballDataCsvAdapter().parse(csv_payload, self.retrieved, "test-league")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].home_team, "Home FC")
        self.assertEqual(records[0].home_corners, 7)
        self.assertEqual(records[0].retrieved_at, self.retrieved)
        self.assertEqual(records[0].source_event_id, "test-league:23/08/2026:Home FC:Away FC")

    def test_odds_api_normalizes_event_and_bookmaker_timestamps(self):
        payload = json.dumps([
            {
                "id": "event-1",
                "commence_time": "2026-08-23T18:00:00Z",
                "bookmakers": [{
                    "key": "book-a",
                    "last_update": "2026-08-23T12:05:00Z",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": [{"name": "Home FC", "price": 1.9}, {"name": "Away FC", "price": 3.8}],
                    }],
                }],
            }
        ]).encode()

        quotes = OddsApiAdapter("test-key").parse_odds(payload, self.retrieved)

        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0].source_event_id, "event-1")
        self.assertEqual(quotes[0].observed_at, parse_datetime("2026-08-23T12:05:00Z"))
        self.assertEqual(quotes[0].odds, 1.9)
        self.assertTrue(quotes[0].canonical_market_id.startswith("market:"))
        self.assertEqual(quotes[0].canonical_market, "match result")
        self.assertEqual(quotes[0].canonical_selection, "home fc")
        self.assertEqual(quotes[0].canonical_line, "none")

    def test_raw_store_writes_payload_and_metadata_with_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = FileRawSnapshotStore(directory).save("test-provider", "https://example.test/data", b"payload", "text/plain", self.retrieved)
            root = Path(directory) / "test-provider" / "2026-08-23"

            self.assertTrue((root / "120000-239f59ed55e737c7.bin").exists())
            self.assertTrue(snapshot.sha256.startswith("239f59ed55e737c7"))
            self.assertEqual(len(list(root.glob("*.json"))), 1)

    def test_default_registry_records_license_and_rate_limit_gates(self):
        registry = default_registry()

        football_data = registry.get("football-data.co.uk")
        odds_api = registry.get("the-odds-api")
        self.assertIn("commercial_redistribution_unverified", football_data.license_status)
        self.assertIn("quota", odds_api.rate_limit_policy)


if __name__ == "__main__":
    unittest.main()
