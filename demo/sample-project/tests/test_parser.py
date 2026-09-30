import pytest
from src.parser import parse_csv_data
from src.validator import validate_user_row


def test_standard_csv_parsing():
    raw = "user_id,email,name\nusr_01,alice@example.com,Alice\nusr_02,bob@example.com,Bob"
    rows = parse_csv_data(raw)
    assert len(rows) == 2
    assert rows[0]["user_id"] == "usr_01"
    assert rows[0]["email"] == "alice@example.com"


def test_utf8_bom_csv_parsing():
    """Validates that UTF-8 BOM encoding does not corrupt header names."""
    raw = "\ufeffuser_id,email,name\nusr_99,bom@example.com,BomUser"
    rows = parse_csv_data(raw)
    assert len(rows) == 1
    # If BOM is not handled, the key will be '\ufeffuser_id' instead of 'user_id'
    assert "user_id" in rows[0], f"Expected 'user_id' header, but found keys: {list(rows[0].keys())}"
    valid, errors = validate_user_row(rows[0])
    assert valid is True, f"Validation failed with errors: {errors}"
