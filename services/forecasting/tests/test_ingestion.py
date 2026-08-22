import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion import FootballDataIngestionJob, football_data_url


CSV_PAYLOAD = b"Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HC,AC\n23/08/2025,Home FC,Away FC,2,1,H,1,0,H,14,8,6,3,7,4\n"


class IngestionTests(unittest.TestCase):
    retrieved = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

    def test_builds_league_url(self):
        self.assertEqual(
            football_data_url("https://example.test/", "e0", "2526"),
            "https://example.test/mmz2526/2526/E0.csv",
        )

    def test_run_once_downloads_snapshots_and_writes_normalized_manifest(self):
        requested_urls: list[str] = []

        def downloader(url: str) -> tuple[bytes, str]:
            requested_urls.append(url)
            return CSV_PAYLOAD, "text/csv"

        with tempfile.TemporaryDirectory() as directory:
            job = FootballDataIngestionJob(
                directory,
                base_url="https://example.test",
                league="E0",
                season="2526",
                downloader=downloader,
                clock=lambda: self.retrieved,
            )
            manifest_path = job.run_once()
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

            self.assertEqual(requested_urls, ["https://example.test/mmz2526/2526/E0.csv"])
            self.assertEqual(manifest["record_count"], 1)
            self.assertEqual(manifest["fixtures"][0]["home_team"], "Home FC")
            self.assertEqual(manifest["fixtures"][0]["home_corners"], 7)
            self.assertTrue(manifest["fixtures"][0]["canonical_fixture_id"].startswith("fixture:"))
            self.assertTrue(manifest["fixtures"][0]["canonical_home_team_id"].startswith("team:"))
            self.assertEqual(manifest["fixtures"][0]["canonical_home_team"], "home fc")
            self.assertEqual(manifest["fixtures"][0]["canonical_competition"], "england premier league")
            self.assertEqual(manifest["identity_validation"]["duplicate_count"], 0)
            self.assertTrue(Path(manifest["raw_snapshot_path"]).exists())
            self.assertEqual(len(list(Path(directory).rglob("*.bin"))), 1)
            self.assertEqual(len(list(Path(directory).rglob("*.json"))), 2)

    def test_run_once_rejects_empty_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            job = FootballDataIngestionJob(directory, downloader=lambda _: (b"", "text/csv"), clock=lambda: self.retrieved)

            with self.assertRaisesRegex(ValueError, "empty CSV payload"):
                job.run_once()

    def test_run_once_rejects_conflicting_correction_from_previous_manifest(self):
        payloads = [
            CSV_PAYLOAD,
            b"Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HC,AC\n23/08/2025,Home FC,Away FC,3,1,H,1,0,H,14,8,6,3,7,4\n",
        ]
        calls = 0

        def downloader(_: str) -> tuple[bytes, str]:
            nonlocal calls
            payload = payloads[calls]
            calls += 1
            return payload, "text/csv"

        with tempfile.TemporaryDirectory() as directory:
            clock_values = iter((self.retrieved, self.retrieved.replace(hour=13)))
            job = FootballDataIngestionJob(
                directory,
                base_url="https://example.test",
                league="E0",
                season="2526",
                downloader=downloader,
                clock=lambda: next(clock_values),
            )
            job.run_once()
            with self.assertRaisesRegex(ValueError, "conflicts with a previously ingested fixture"):
                job.run_once()

    def test_repeated_snapshot_is_audited_as_previous_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            clock_values = iter((self.retrieved, self.retrieved.replace(hour=13)))
            job = FootballDataIngestionJob(
                directory,
                base_url="https://example.test",
                league="E0",
                season="2526",
                downloader=lambda _: (CSV_PAYLOAD, "text/csv"),
                clock=lambda: next(clock_values),
            )
            job.run_once()
            second_manifest_path = job.run_once()
            manifest = json.loads(Path(second_manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["identity_validation"]["previous_snapshot_duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
