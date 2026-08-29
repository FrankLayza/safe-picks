import asyncio
import json
import unittest

from app.main import IngestionQualityRequest, app, ingestion_quality, ingestion_validation_error_handler, today_candidates
from app.providers.quality import IngestionValidationError


VALID_RECORD = {
    "provider": "football-data.co.uk",
    "source_event_id": "E0:23/08/2025:Home FC:Away FC",
    "home_team": "Home FC",
    "away_team": "Away FC",
    "match_start_at": "2025-08-23T00:00:00Z",
    "retrieved_at": "2026-08-23T12:00:00Z",
    "competition": "E0",
    "season": "2525",
    "home_goals": 2,
    "away_goals": 1,
}


class ForecastingApiTests(unittest.TestCase):
    def test_ingestion_quality_returns_audit_when_payload_passes(self):
        response = ingestion_quality(
            IngestionQualityRequest.model_validate(
                {
                "snapshot_retrieved_at": "2026-08-23T12:00:00Z",
                "reference_at": "2026-08-23T12:01:00Z",
                "records": [VALID_RECORD],
                }
            )
        )

        self.assertEqual(response.status, "pass")
        self.assertEqual(response.audit["freshness"]["age_seconds"], 60.0)

    def test_ingestion_quality_exposes_machine_readable_rejection(self):
        request = IngestionQualityRequest.model_validate(
            {
                "snapshot_retrieved_at": "2026-08-23T12:00:00Z",
                "reference_at": "2026-08-31T12:00:00Z",
                "max_snapshot_age_seconds": 604800,
                "records": [VALID_RECORD],
            }
        )
        with self.assertRaises(IngestionValidationError) as context:
            ingestion_quality(request)

        response = asyncio.run(ingestion_validation_error_handler(None, context.exception))
        error = json.loads(response.body)["error"]
        self.assertEqual(response.status_code, 422)
        self.assertEqual(error["code"], "ingestion_quality_rejected")
        self.assertEqual(error["reasons"][0]["code"], "stale_snapshot")
        self.assertEqual(error["audit"]["status"], "rejected")

    def test_ingestion_quality_converts_malformed_timestamp_to_rejection_reason(self):
        request = IngestionQualityRequest.model_validate(
            {
                "snapshot_retrieved_at": "not-a-timestamp",
                "records": [{**VALID_RECORD, "home_team": ""}],
            }
        )
        with self.assertRaises(IngestionValidationError) as context:
            ingestion_quality(request)

        response = asyncio.run(ingestion_validation_error_handler(None, context.exception))
        reason_codes = {reason["code"] for reason in json.loads(response.body)["error"]["reasons"]}
        self.assertIn("invalid_timestamp", reason_codes)
        self.assertIn("missing_required_field", reason_codes)

    def test_ingestion_quality_route_is_registered(self):
        routes = {getattr(route, "path", None) for route in app.routes}
        self.assertIn("/v1/ingestion/quality", routes)

    def test_today_candidates_uses_model_backed_generator_and_diagnostics(self):
        response = today_candidates()

        self.assertEqual(response.source, "forecasting-service")
        self.assertEqual(response.status, "abstain")
        self.assertEqual(response.abstentionCode, "NO_ELIGIBLE_CANDIDATES")
        self.assertTrue(response.diagnostics)
        self.assertNotEqual(response.source, "development-mock")


if __name__ == "__main__":
    unittest.main()
