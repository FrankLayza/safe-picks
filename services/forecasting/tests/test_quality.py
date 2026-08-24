import unittest
from datetime import datetime, timedelta, timezone

from app.providers.models import FixtureRecord
from app.providers.quality import IngestionQualityPolicy, IngestionValidationError, validate_ingestion_quality


class QualityValidationTests(unittest.TestCase):
    retrieved = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

    def fixture(self, **changes: object) -> FixtureRecord:
        values = {
            "provider": "football-data.co.uk",
            "source_event_id": "E0:23/08/2025:Home FC:Away FC",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "match_start_at": datetime(2025, 8, 23, tzinfo=timezone.utc),
            "retrieved_at": self.retrieved,
            "competition": "E0",
            "season": "2525",
            "home_goals": 2,
            "away_goals": 1,
            "home_corners": 7,
            "away_corners": 4,
        }
        values.update(changes)
        return FixtureRecord(**values)

    def test_fresh_snapshot_and_missingness_audit_pass(self):
        audit = validate_ingestion_quality(
            [self.fixture()],
            snapshot_retrieved_at=self.retrieved,
            reference_at=self.retrieved + timedelta(minutes=1),
        )

        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["freshness"]["age_seconds"], 60.0)
        self.assertEqual(audit["missingness"]["record_count"], 1)
        self.assertEqual(audit["missingness"]["fields"]["home_shots"]["missing_count"], 1)

    def test_stale_snapshot_has_machine_readable_rejection_reason(self):
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                [self.fixture()],
                snapshot_retrieved_at=self.retrieved,
                reference_at=self.retrieved + timedelta(days=8),
                policy=IngestionQualityPolicy(max_snapshot_age=timedelta(days=7)),
            )

        self.assertEqual(context.exception.code, "ingestion_quality_rejected")
        self.assertEqual(context.exception.reasons[0]["code"], "stale_snapshot")
        self.assertEqual(context.exception.reasons[0]["details"]["max_age_seconds"], 604800.0)

    def test_future_snapshot_is_rejected(self):
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                [self.fixture()],
                snapshot_retrieved_at=self.retrieved + timedelta(minutes=1),
                reference_at=self.retrieved,
            )

        self.assertEqual(context.exception.reasons[0]["code"], "snapshot_timestamp_in_future")

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                [self.fixture(home_team="")],
                snapshot_retrieved_at=self.retrieved,
                reference_at=self.retrieved,
            )

        reasons = context.exception.reasons
        self.assertTrue(any(reason["code"] == "missing_required_field" and reason["details"]["field"] == "home_team" for reason in reasons))

    def test_optional_missingness_threshold_is_rejected(self):
        records = [self.fixture(home_shots=None), self.fixture(source_event_id="second", home_shots=10)]
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                records,
                snapshot_retrieved_at=self.retrieved,
                reference_at=self.retrieved,
                policy=IngestionQualityPolicy(max_optional_missing_fraction=0.25),
            )

        self.assertTrue(any(reason["code"] == "optional_missingness_exceeded" for reason in context.exception.reasons))

    def test_record_retrieved_after_snapshot_is_rejected(self):
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                [self.fixture(retrieved_at=self.retrieved + timedelta(seconds=1))],
                snapshot_retrieved_at=self.retrieved,
                reference_at=self.retrieved,
            )

        self.assertTrue(any(reason["code"] == "record_timestamp_after_snapshot" for reason in context.exception.reasons))

    def test_malformed_timestamps_are_rejected_without_comparison_errors(self):
        with self.assertRaises(IngestionValidationError) as context:
            validate_ingestion_quality(
                [self.fixture(match_start_at="2025-08-23", retrieved_at="2026-08-23")],  # type: ignore[arg-type]
                snapshot_retrieved_at=self.retrieved,
                reference_at=self.retrieved,
            )

        self.assertTrue(any(reason["code"] == "invalid_timestamp" for reason in context.exception.reasons))


if __name__ == "__main__":
    unittest.main()
