import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.goals import PoissonGoalsModel, PoissonModelConfig
from app.providers.identity import resolve_fixture_identity
from app.providers.models import FixtureRecord
from app.replay import ReplayedFixture


class GoalsModelTests(unittest.TestCase):
    kickoff = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)

    def fixture(self, days: int, home: str, away: str, home_goals: int | None, away_goals: int | None, retrieved_hours: int = 0) -> ReplayedFixture:
        match_start = self.kickoff + timedelta(days=days)
        retrieved = (
            match_start + timedelta(hours=2) + timedelta(hours=retrieved_hours)
            if home_goals is not None and away_goals is not None
            else match_start - timedelta(hours=2) + timedelta(hours=retrieved_hours)
        )
        record = FixtureRecord(
            provider="football-data.co.uk",
            source_event_id=f"event-{days}-{home}-{away}",
            home_team=home,
            away_team=away,
            match_start_at=match_start,
            retrieved_at=retrieved,
            competition="E0",
            season="2526",
            home_goals=home_goals,
            away_goals=away_goals,
        )
        return ReplayedFixture(record, resolve_fixture_identity(record), f"manifest-{days}", retrieved, f"sha-{days}")

    def test_model_excludes_future_and_incomplete_matches(self):
        history = [
            self.fixture(-10, "Home FC", "North FC", 2, 0),
            self.fixture(-20, "South FC", "Away FC", 1, 1),
            self.fixture(0, "Home FC", "Leak FC", 9, 0),
            self.fixture(-15, "Home FC", "Missing FC", None, 0),
        ]
        model = PoissonGoalsModel.fit(history, as_of=self.kickoff)

        self.assertEqual(model.training_matches, 2)
        prediction = model.predict("Home FC", "Away FC")
        self.assertGreater(prediction.expected_home_goals, 0)
        self.assertGreater(prediction.expected_away_goals, 0)

    def test_prediction_markets_are_probabilities(self):
        history = [
            self.fixture(-10, "Home FC", "North FC", 2, 0),
            self.fixture(-20, "South FC", "Away FC", 1, 1),
            self.fixture(-30, "Home FC", "Away FC", 1, 0),
        ]
        prediction = PoissonGoalsModel.fit(history, as_of=self.kickoff).predict("Home FC", "Away FC")

        self.assertAlmostEqual(prediction.home_win_probability + prediction.draw_probability + prediction.away_win_probability, 1.0, places=6)
        self.assertGreaterEqual(prediction.over_1_5_probability, prediction.over_2_5_probability)
        self.assertGreaterEqual(prediction.btts_probability, 0.0)
        self.assertLessEqual(prediction.btts_probability, 1.0)

    def test_dixon_coles_correction_changes_low_score_mass(self):
        history = [
            self.fixture(-10, "Home FC", "North FC", 0, 0),
            self.fixture(-20, "South FC", "Away FC", 0, 1),
            self.fixture(-30, "Home FC", "Away FC", 1, 0),
        ]
        poisson = PoissonGoalsModel.fit(history, as_of=self.kickoff, config=PoissonModelConfig(dixon_coles_rho=0.0)).predict("Home FC", "Away FC")
        dixon_coles = PoissonGoalsModel.fit(history, as_of=self.kickoff, config=PoissonModelConfig(dixon_coles_rho=-0.15)).predict("Home FC", "Away FC")

        self.assertNotEqual(poisson.score_probability(0, 0), dixon_coles.score_probability(0, 0))
        self.assertAlmostEqual(sum(sum(row) for row in dixon_coles.score_matrix), 1.0, places=6)

    def test_prediction_carries_model_version_and_training_as_of(self):
        history = [self.fixture(-10, "Home FC", "North FC", 2, 0)]
        model = PoissonGoalsModel.fit(history, as_of=self.kickoff)
        prediction = model.predict("Home FC", "North FC")

        self.assertEqual(prediction.model_version, "poisson-dixon-coles-v1")
        self.assertEqual(prediction.training_as_of, self.kickoff)
        self.assertEqual(prediction.source_manifest_paths, ("manifest--10",))
        self.assertEqual(prediction.raw_snapshot_shas, ("sha--10",))

    def test_late_record_and_manifest_are_excluded(self):
        history = [
            self.fixture(-10, "Home FC", "North FC", 2, 0, retrieved_hours=300),
            self.fixture(-20, "South FC", "Away FC", 1, 1),
        ]
        model = PoissonGoalsModel.fit(history, as_of=self.kickoff)
        self.assertEqual(model.training_matches, 1)
        self.assertEqual(model.source_manifest_paths, ("manifest--20",))

    def test_naive_timestamp_is_rejected_before_comparison(self):
        naive = self.fixture(-10, "Home FC", "North FC", 2, 0)
        naive = replace(naive, record=replace(naive.record, match_start_at=naive.record.match_start_at.replace(tzinfo=None)))
        with self.assertRaisesRegex(ValueError, "fixture kickoff must include a timezone"):
            PoissonGoalsModel.fit([naive], as_of=self.kickoff)

    def test_fitted_rho_stays_within_configured_range(self):
        history = [
            self.fixture(-10, "Home FC", "North FC", 0, 0),
            self.fixture(-20, "South FC", "Away FC", 1, 0),
            self.fixture(-30, "Home FC", "Away FC", 1, 1),
        ]
        model = PoissonGoalsModel.fit(history, as_of=self.kickoff)
        self.assertGreaterEqual(model.rho, -0.2)
        self.assertLessEqual(model.rho, 0.2)


if __name__ == "__main__":
    unittest.main()
