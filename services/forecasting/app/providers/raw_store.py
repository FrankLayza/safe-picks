import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import RawSnapshot


class FileRawSnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, provider: str, source_uri: str, payload: bytes, content_type: str, retrieved_at: datetime | None = None) -> RawSnapshot:
        timestamp = retrieved_at or datetime.now(timezone.utc)
        digest = hashlib.sha256(payload).hexdigest()
        directory = self.root / provider / timestamp.strftime("%Y-%m-%d")
        directory.mkdir(parents=True, exist_ok=True)
        data_path = directory / f"{timestamp.strftime('%H%M%S')}-{digest[:16]}.bin"
        metadata_path = data_path.with_suffix(".json")
        data_path.write_bytes(payload)
        metadata_path.write_text(
            json.dumps(
                {
                    "provider": provider,
                    "source_uri": source_uri,
                    "retrieved_at": timestamp.isoformat(),
                    "content_type": content_type,
                    "sha256": digest,
                    "payload_path": str(data_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return RawSnapshot(provider, source_uri, timestamp, payload, content_type, digest, str(data_path), str(metadata_path))
