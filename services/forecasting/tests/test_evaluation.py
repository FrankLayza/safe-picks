import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.evaluation import EvaluationConfig, IsotonicCalibrator, evaluate_goals_walk_forward
from app.providers.identity import resolve_fixture_identity
from app.providers.models import FixtureRecord
from app.replay import ReplayedFixture


class EvaluationTests(unittest.TestCase):
    kickoff = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)

    def fixture(self, days: int, home: str, away: str, home_goals: int, away_goals: int) -> ReplayedFixture:
        start = self.kickoff + timedelta(days=days)
        retrieved = start + timedelta(hours=2)
        record = FixtureRecord(
            provider="football-data.co.uk",
            source_event_id=f"event-{days}-{home}-{away}",
            home_team=home,
            away_team=away,
            match_start_at=start,
            retrieved_at=retrieved,
            competition="E0",
            season="2526",
            home_goals=home_goals,
            away_goals=away_goals,
        )
        return ReplayedFixture(record, resolve_fixture_identity(record), f"manifest-{days}", retrieved, f"sha-{days}")

    def history(self) -> list[ReplayedFixture]:
        return [
            self.fixture(-10, "A", "B", 2, 0),
            self.fixture(-9, "B", "A", 1, 1),
            self.fixture(-8, "A", "B", 0, 1),
            self.fixture(-7, "B", "A", 2, 2),
            self.fixture(-6, "A", "B", 3, 1),
            self.fixture(-5, "B", "A", 0, 0),
            self.fixture(-4, "A", "B", 1, 2),
            self.fixture(-3, "B", "A", 2, 1),
            self.fixture(1, "A", "B", 2, 1),
            self.fixture(2, "B", "A", 0, 0),
            self.fixture(3, "A", "B", 0, 1),
            self.fixture(4, "B", "A", 3, 0),
        ]

    def test_walk_forward_produces_temporal_validation_and_test_observations(self):
        report = evaluate_goals_walk_forward(
            self.history(),
            EvaluationConfig(
                validation_start=self.kickoff,
                validation_end=self.kickoff + timedelta(days=4),
                test_end=self.kickoff + timedelta(days=5),
                min_training_matches=3,
                min_calibration_samples=2,
            ),
        )
        self.assertEqual(report.evaluation_version, "goals-walk-forward-v1")
        self.assertEqual({item.split for item in report.validation_observations}, {"validation"})
        self.assertEqual({item.split for item in report.test_observations}, {"test"})
        self.assertEqual(len(report.validation_observations), 18)
        self.assertEqual(len(report.test_observations), 6)
        self.assertEqual(report.validation_metrics["over_2_5"].sample_count, 3)
        self.assertGreaterEqual(report.validation_metrics["over_2_5"].brier_score, 0.0)
        self.assertEqual(set(report.calibrators), {"home_win", "draw", "away_win", "over_1_5", "over_2_5", "btts"})
        self.assertEqual(report.calibrated_test_metrics["btts"].sample_count, 1)
        self.assertTrue(
            all(
                item.training_as_of == item.kickoff
                for item in report.validation_observations + report.test_observations
            )
        )
        result_observations = [
            item
            for item in report.calibrated_test_observations()
            if item.market in {"home_win", "draw", "away_win"}
        ]
        self.assertAlmostEqual(sum(item.probability for item in result_observations), 1.0)

    def test_insufficient_training_is_recorded_as_abstention(self):
        report = evaluate_goals_walk_forward(
            self.history(),
            EvaluationConfig(
                validation_start=self.kickoff,
                validation_end=self.kickoff + timedelta(days=2),
                min_training_matches=20,
            ),
        )
        self.assertTrue(report.validation_observations)
        self.assertTrue(all(item.status == "abstained" for item in report.validation_observations))
        self.assertTrue(
            all(
                item.rejection_code == "INSUFFICIENT_TRAINING_MATCHES"
                for item in report.validation_observations
            )
        )
        self.assertEqual(report.validation_metrics["draw"].sample_count, 0)

    def test_missing_calibrators_are_reported_without_key_errors(self):
        report = evaluate_goals_walk_forward(
            self.history(),
            EvaluationConfig(
                validation_start=self.kickoff,
                validation_end=self.kickoff + timedelta(days=2),
                test_end=self.kickoff + timedelta(days=3),
            ),
        )
        self.assertEqual(report.calibrators, {})
        self.assertEqual(report.calibrated_test_probabilities(), {})
        self.assertEqual(report.calibrated_test_metrics["home_win"].sample_count, 0)

    def test_malformed_timestamps_fail_closed(self):
        malformed = self.history()
        malformed[0] = replace(
            malformed[0],
            record=replace(
                malformed[0].record,
                match_start_at=malformed[0].record.match_start_at.replace(tzinfo=None),
            ),
        )
        with self.assertRaisesRegex(ValueError, "fixture kickoff must include a timezone"):
            evaluate_goals_walk_forward(
                malformed,
                EvaluationConfig(
                    validation_start=self.kickoff,
                    validation_end=self.kickoff + timedelta(days=2),
                ),
            )

    def test_isotonic_calibrator_is_monotonic_and_bounded(self):
        calibrator = IsotonicCalibrator.fit([0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1])
        values = [calibrator.predict(value) for value in [0.0, 0.15, 0.25, 0.5, 1.0]]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in values))
        self.assertEqual(calibrator.predict(0.2), 0.5)
        self.assertEqual(calibrator.sample_count, 4)

    def test_calibrator_requires_two_binary_observations(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            IsotonicCalibrator.fit([0.5], [1])
        with self.assertRaisesRegex(ValueError, "zero or one"):
            IsotonicCalibrator.fit([0.2, 0.8], [0, 0.5])
        with self.assertRaisesRegex(ValueError, "equal length"):
            IsotonicCalibrator.fit([0.2, 0.8], [0])


if __name__ == "__main__":
    unittest.main()
