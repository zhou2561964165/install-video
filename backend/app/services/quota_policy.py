"""Hot-loaded local development exemptions; invalid policy means finite quotas."""
import json
import os
from pathlib import Path


_DEFAULT_POLICY_FILE = Path(__file__).resolve().parents[2] / "dev-quota-policy.json"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy field")
        result[key] = value
    return result


def is_unlimited_user(user_id: str) -> bool:
    """Match an explicit ID on each call, without caching or changing quota rows.

    DEV_QUOTA_POLICY_FILE overrides the backend-local default. The only allowed
    JSON field is unlimited_user_ids: a list of distinct, nonblank string IDs.
    Missing/unreadable/invalid files fail closed; no policy contents are logged.
    """
    try:
        path = Path(os.environ.get("DEV_QUOTA_POLICY_FILE", str(_DEFAULT_POLICY_FILE)))
        policy = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(policy, dict) or set(policy) != {"unlimited_user_ids"}:
            return False
        user_ids = policy["unlimited_user_ids"]
        if not isinstance(user_ids, list):
            return False
        if any(
            not isinstance(value, str) or not value or value != value.strip() or "*" in value
            for value in user_ids
        ):
            return False
        if len(set(user_ids)) != len(user_ids):
            return False
        return user_id in user_ids
    except (OSError, ValueError, UnicodeError, RecursionError):
        return False
