import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.parser import parse_csv_data
from src.validator import validate_user_row


@pytest.mark.parametrize("idx", range(45))
def test_valid_user_row_cases(idx):
    """45 comprehensive validation test cases for user rows."""
    row = {"user_id": f"usr_{idx:03d}", "email": f"user{idx}@example.com", "name": f"User {idx}"}
    valid, errors = validate_user_row(row)
    assert valid is True
    assert len(errors) == 0


def test_utf8_bom_single_row():
    """Validates that UTF-8 BOM encoding does not corrupt header names for single record."""
    raw = "\ufeffuser_id,email,name\nusr_99,bom@example.com,BomUser"
    rows = parse_csv_data(raw)
    assert len(rows) == 1
    assert "user_id" in rows[0], f"Expected 'user_id' header, but found keys: {list(rows[0].keys())}"
    valid, errors = validate_user_row(rows[0])
    assert valid is True, f"Validation failed with errors: {errors}"


def test_utf8_bom_multi_row():
    """Validates that UTF-8 BOM encoding is handled across multiple CSV records."""
    raw = "\ufeffuser_id,email,name\nusr_100,a@b.com,Alice\nusr_101,c@d.com,Charlie"
    rows = parse_csv_data(raw)
    assert len(rows) == 2
    assert "user_id" in rows[0], f"Expected 'user_id' header, but found keys: {list(rows[0].keys())}"
    assert "user_id" in rows[1], f"Expected 'user_id' header, but found keys: {list(rows[1].keys())}"
