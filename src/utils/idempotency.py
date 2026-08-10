import hashlib
import json
from typing import Any


def generate_idempotency_key(
    operation: str,
    **values: Any,
) -> str:
    payload = {
        "operation": operation,
        **values,
    }

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()