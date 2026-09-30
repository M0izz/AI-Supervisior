import csv
import io
from typing import Any, Dict, List

def parse_csv_data(raw_content: str) -> List[Dict[str, Any]]:
    """Parses CSV data into list of dictionaries (naive implementation)."""
    cleaned = raw_content.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(cleaned))
    return [row for row in reader]
