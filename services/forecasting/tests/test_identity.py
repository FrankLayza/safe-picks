import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.providers.identity import (
    IdentityResolutionError,
    ManifestValidationError,
    resolve_competition_id,
    resolve_fixture_identity,
    resolve_fixture_records,
    resolve_market_identity,
    resolve_market_quotes,
    resolve_team_id,
)
from app.providers.models import FixtureRecord, OddsQuote


class IdentityTests(unittest.TestCase):
    retrieved = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    kickoff = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)

    def fixture(self, **changes: object) -> FixtureRecord:
        record = FixtureRecord(
            provider="football-data.co.uk",
            source_event_id="E0:24/08/2026:Home FC:Away FC",
            home_team="Home FC",
            away_team="Away FC",
            match_start_at=self.kickoff,
            retrieved_at=self.retrieved,
            competition="E0",
            season="2526",
            home_goals=2,
            away_goals=1,
        )
        return replace(record, **changes)

    def test_team_and_competition_aliases_resolve_to_same_ids(self):
        self.assertEqual(resolve_team_id("provider", "Man Utd"), resolve_team_id("provider", "Manchester United"))
        self.assertEqual(resolve_team_id("provider", "Home F.C."), resolve_team_id("provider", "home fc"))
        self.assertEqual(resolve_competition_id("provider", "E0"), resolve_competition_id("provider", "Premier League"))

    def test_reversed_home_and_away_have_different_fixture_ids(self):
        first = resolve_fixture_identity(self.fixture())
        reversed_fixture = resolve_fixture_identity(
            self.fixture(home_team="Away FC", away_team="Home FC")
        )
        self.assertNotEqual(first.canonical_fixture_id, reversed_fixture.canonical_fixture_id)
        self.assertNotEqual(first.canonical_home_team_id, first.canonical_away_team_id)

    def test_market_identity_includes_line_and_normalizes_market_alias(self):
        quote = OddsQuote(
            provider="the-odds-api",
            source_event_id="event-1",
            bookmaker="Book A",
            market="h2h",
            selection="Home FC",
            odds=1.9,
            match_start_at=self.kickoff,
            retrieved_at=self.retrieved,
        )
        equivalent = replace(quote, market="match result")
        total = replace(quote, market="totals", selection="Over", line=2.5)
        equivalent_total = replace(total, market="over-under", line=2.50)
        different_line = replace(total, line=3.5)
        self.assertEqual(resolve_market_identity(quote), resolve_market_identity(equivalent))
        self.assertEqual(resolve_market_identity(total), resolve_market_identity(equivalent_total))
        self.assertNotEqual(resolve_market_identity(total), resolve_market_identity(different_line))

    def test_duplicate_rows_are_collapsed_and_audited(self):
        duplicate = self.fixture(
            source_event_id="same-event-with-another-provider-key",
            home_team="Home F.C.",
            retrieved_at=self.retrieved + timedelta(minutes=5),
        )
        records, audit, identities = resolve_fixture_records([self.fixture(), duplicate], season="2526")
        self.assertEqual(len(records), 1)
        self.assertEqual(audit["duplicate_count"], 1)
        self.assertEqual(audit["correction_count"], 0)
        self.assertEqual(len(identities), 1)

    def test_conflicting_duplicate_is_rejected_as_correction(self):
        with self.assertRaises(ManifestValidationError) as context:
            resolve_fixture_records([self.fixture(), self.fixture(home_goals=3)], season="2526")
        self.assertEqual(context.exception.code, "conflicting_correction")
        self.assertEqual(context.exception.details[0]["fields"], ["home_goals"])

    def test_missing_values_can_be_completed_but_missing_identity_fails_closed(self):
        incomplete = self.fixture(home_goals=None, away_goals=None)
        records, audit, _ = resolve_fixture_records([incomplete, self.fixture()], season="2526")
        self.assertEqual(records[0].home_goals, 2)
        self.assertEqual(audit["completion_count"], 1)

        with self.assertRaises(IdentityResolutionError) as context:
            resolve_fixture_identity(self.fixture(home_team=""))
        self.assertEqual(context.exception.code, "missing_identity_field")

    def test_market_missing_identity_fields_fail_closed(self):
        quote = OddsQuote(
            provider="the-odds-api",
            source_event_id="event-1",
            bookmaker="",
            market="h2h",
            selection="Home FC",
            odds=1.9,
            match_start_at=self.kickoff,
            retrieved_at=self.retrieved,
        )
        with self.assertRaises(IdentityResolutionError) as context:
            resolve_market_identity(quote)
        self.assertEqual(context.exception.code, "missing_identity_field")

    def test_market_duplicates_collapse_and_conflicting_prices_are_rejected(self):
        quote = OddsQuote(
            provider="the-odds-api",
            source_event_id="event-1",
            bookmaker="Book A",
            market="h2h",
            selection="Home FC",
            odds=1.9,
            match_start_at=self.kickoff,
            retrieved_at=self.retrieved,
        )
        normalized, audit = resolve_market_quotes([quote, replace(quote, retrieved_at=self.retrieved + timedelta(minutes=1))])
        self.assertEqual(len(normalized), 1)
        self.assertEqual(audit["duplicate_count"], 1)
        with self.assertRaises(ManifestValidationError) as context:
            resolve_market_quotes([quote, replace(quote, odds=2.0)])
        self.assertEqual(context.exception.code, "conflicting_correction")


if __name__ == "__main__":
    unittest.main()
