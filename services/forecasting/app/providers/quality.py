from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from .models import FixtureRecord

OPTIONAL_FIXTURE_FIELDS = (
    "home_goals",
    "away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "home_corners",
    "away_corners",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
)

REQUIRED_FIXTURE_FIELDS = (
    "provider",
    "source_event_id",
    "home_team",
    "away_team",
    "match_start_at",
    "retrieved_at",
    "competition",
    "season",
)


@dataclass(frozen=True)
class IngestionQualityPolicy:
    max_snapshot_age: timedelta | None = timedelta(days=7)
    max_optional_missing_fraction: float | None = None

    def __post_init__(self) -> None:
        if self.max_snapshot_age is not None and self.max_snapshot_age.total_seconds() < 0:
            raise ValueError("max_snapshot_age cannot be negative")
        if self.max_optional_missing_fraction is not None and not 0 <= self.max_optional_missing_fraction <= 1:
            raise ValueError("max_optional_missing_fraction must be between zero and one")


class IngestionValidationError(ValueError):
    def __init__(self, code: str, message: str, reasons: list[dict[str, Any]], audit: dict[str, Any]):
        super().__init__(message)
        self.code = code
        self.reasons = reasons
        self.audit = audit


def validate_ingestion_quality(
    records: Iterable[FixtureRecord],
    snapshot_retrieved_at: datetime,
    reference_at: datetime | None = None,
    policy: IngestionQualityPolicy | None = None,
) -> dict[str, Any]:
    active_policy = policy or IngestionQualityPolicy()
    reference = reference_at or snapshot_retrieved_at
    reasons: list[dict[str, Any]] = []
    records_list = list(records)
    _validate_timestamp(snapshot_retrieved_at, "snapshot_retrieved_at", reasons)
    _validate_timestamp(reference, "reference_at", reasons)

    age_seconds = None
    if _timestamp_is_aware(snapshot_retrieved_at) and _timestamp_is_aware(reference):
        age_seconds = (reference - snapshot_retrieved_at).total_seconds()
    freshness = {
        "snapshot_retrieved_at": snapshot_retrieved_at.isoformat(),
        "reference_at": reference.isoformat(),
        "age_seconds": age_seconds,
        "max_age_seconds": active_policy.max_snapshot_age.total_seconds() if active_policy.max_snapshot_age else None,
        "stale": False,
    }
    if age_seconds is not None and age_seconds < 0:
        reasons.append(_reason("snapshot_timestamp_in_future", {"snapshot_retrieved_at": snapshot_retrieved_at.isoformat(), "reference_at": reference.isoformat()}))
    elif age_seconds is not None and active_policy.max_snapshot_age is not None and age_seconds > active_policy.max_snapshot_age.total_seconds():
        freshness["stale"] = True
        reasons.append(
            _reason(
                "stale_snapshot",
                {
                    "age_seconds": age_seconds,
                    "max_age_seconds": active_policy.max_snapshot_age.total_seconds(),
                },
            )
        )

    if not records_list:
        reasons.append(_reason("empty_payload", {"record_count": 0}))

    for index, record in enumerate(records_list):
        for field in REQUIRED_FIXTURE_FIELDS:
            value = getattr(record, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                reasons.append(_reason("missing_required_field", {"record_index": index, "field": field}))
        for field in ("match_start_at", "retrieved_at"):
            value = getattr(record, field, None)
            if not isinstance(value, datetime):
                reasons.append(_reason("invalid_timestamp", {"record_index": index, "field": field}))
            elif value.tzinfo is None:
                reasons.append(_reason("timestamp_without_timezone", {"record_index": index, "field": field}))
        if (
            _timestamp_is_aware(record.retrieved_at)
            and _timestamp_is_aware(snapshot_retrieved_at)
            and record.retrieved_at > snapshot_retrieved_at
        ):
            reasons.append(
                _reason(
                    "record_timestamp_after_snapshot",
                    {
                        "record_index": index,
                        "record_retrieved_at": record.retrieved_at.isoformat(),
                        "snapshot_retrieved_at": snapshot_retrieved_at.isoformat(),
                    },
                )
            )

    missingness: dict[str, Any] = {"record_count": len(records_list), "fields": {}}
    for field in OPTIONAL_FIXTURE_FIELDS:
        missing_count = sum(getattr(record, field, None) is None for record in records_list)
        fraction = missing_count / len(records_list) if records_list else 1.0
        missingness["fields"][field] = {
            "missing_count": missing_count,
            "missing_fraction": fraction,
        }
        if active_policy.max_optional_missing_fraction is not None and fraction > active_policy.max_optional_missing_fraction:
            reasons.append(
                _reason(
                    "optional_missingness_exceeded",
                    {
                        "field": field,
                        "missing_count": missing_count,
                        "record_count": len(records_list),
                        "missing_fraction": fraction,
                        "max_missing_fraction": active_policy.max_optional_missing_fraction,
                    },
                )
            )

    audit = {
        "status": "rejected" if reasons else "pass",
        "freshness": freshness,
        "missingness": missingness,
        "reasons": reasons,
    }
    if reasons:
        raise IngestionValidationError("ingestion_quality_rejected", "ingestion quality checks failed", reasons, audit)
    return audit


def _validate_timestamp(value: datetime, field: str, reasons: list[dict[str, Any]]) -> None:
    if not isinstance(value, datetime):
        reasons.append(_reason("invalid_timestamp", {"field": field}))
    elif value.tzinfo is None:
        reasons.append(_reason("timestamp_without_timezone", {"field": field}))


def _timestamp_is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _reason(code: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "details": details}
