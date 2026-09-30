import re
from typing import Any, Dict, List, Tuple


def validate_user_row(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validates user row structure and email format."""
    errors = []
    if "user_id" not in row or not row["user_id"]:
        errors.append("Missing user_id")
    if "email" not in row or "@" not in row.get("email", ""):
        errors.append(f"Invalid email: {row.get('email')}")
    return len(errors) == 0, errors
