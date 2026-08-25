import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.features import FeatureConfig, build_fixture_features
from app.providers.identity import resolve_fixture_identity
from app.providers.models import FixtureRecord
from app.replay import ReplayedFixture


class FeaturePipelineTests(unittest.TestCase):
    kickoff = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)

    def replayed(self, offset_days: int, home: str, away: str, home_goals: int | None, away_goals: int | None, retrieved_offset: int = 0) -> ReplayedFixture:
        match_start = self.kickoff + timedelta(days=offset_days)
        retrieved = (
            match_start + timedelta(hours=2) + timedelta(hours=retrieved_offset)
            if home_goals is not None and away_goals is not None
            else match_start - timedelta(hours=2) + timedelta(hours=retrieved_offset)
        )
        record = FixtureRecord(
            provider="football-data.co.uk",
            source_event_id=f"event-{offset_days}-{home}-{away}",
            home_team=home,
            away_team=away,
            match_start_at=match_start,
            retrieved_at=retrieved,
            competition="E0",
            season="2526",
            home_goals=home_goals,
            away_goals=away_goals,
        )
        identity = resolve_fixture_identity(record)
        return ReplayedFixture(record, identity, f"manifest-{offset_days}", retrieved, f"sha-{offset_days}")

    def test_features_use_only_completed_matches_known_before_forecast(self):
        target = self.replayed(0, "Home FC", "Away FC", None, None)
        history = [
            self.replayed(-10, "Home FC", "North FC", 2, 0),
            self.replayed(-20, "South FC", "Away FC", 3, 1),
            self.replayed(0, "Home FC", "Leak FC", 9, 9),
            self.replayed(1, "Away FC", "Future FC", 7, 0),
            self.replayed(-30, "Home FC", "Old FC", None, None),
            self.replayed(-15, "Home FC", "Late FC", 4, 0, retrieved_offset=20 * 24),
            self.replayed(-12, "Home FC", "Record Late FC", 6, 0, retrieved_offset=24 * 13),
        ]

        features = build_fixture_features(target, history, forecast_at=self.kickoff)

        self.assertEqual(features.matches_used, 2)
        self.assertEqual(features.home_matches_used, 1)
        self.assertEqual(features.away_matches_used, 1)
        self.assertEqual(features.home_goals_for_average, 2.0)
        self.assertEqual(features.home_goals_against_average, 0.0)
        self.assertEqual(features.away_goals_for_average, 1.0)
        self.assertEqual(features.away_goals_against_average, 3.0)
        self.assertIsNotNone(features.home_attack_strength)
        self.assertIsNotNone(features.home_defense_strength)
        self.assertIsNotNone(features.away_attack_strength)
        self.assertIsNotNone(features.away_defense_strength)
        self.assertEqual(features.source_manifest_paths, ("manifest--10", "manifest--20", "manifest-0"))
        self.assertEqual(features.raw_snapshot_shas, ("sha--10", "sha--20", "sha-0"))

    def test_recent_window_and_rest_are_explicit(self):
        target = self.replayed(0, "Home FC", "Away FC", None, None)
        history = [self.replayed(-2, "Home FC", "North FC", 1, 0), self.replayed(-20, "Home FC", "Old FC", 4, 0)]

        features = build_fixture_features(target, history, forecast_at=self.kickoff, config=FeatureConfig(recent_matches=1))

        self.assertEqual(features.home_matches_used, 1)
        self.assertEqual(features.home_goals_for_average, 1.0)
        self.assertEqual(features.home_rest_days, 2.0)
        self.assertIsNone(features.away_rest_days)

    def test_forecast_after_kickoff_is_rejected(self):
        target = self.replayed(0, "Home FC", "Away FC", None, None)
        with self.assertRaisesRegex(ValueError, "before kickoff"):
            build_fixture_features(target, [], forecast_at=self.kickoff + timedelta(minutes=1))

    def test_naive_history_timestamp_is_rejected_before_comparison(self):
        target = self.replayed(0, "Home FC", "Away FC", None, None)
        naive = self.replayed(-2, "Home FC", "North FC", 1, 0)
        naive = replace(naive, record=replace(naive.record, match_start_at=naive.record.match_start_at.replace(tzinfo=None)))
        with self.assertRaisesRegex(ValueError, "historical kickoff must include a timezone"):
            build_fixture_features(target, [naive], forecast_at=self.kickoff)


if __name__ == "__main__":
    unittest.main()
