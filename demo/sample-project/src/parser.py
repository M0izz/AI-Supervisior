import csv
import io
from typing import Any, Dict, List

def parse_csv_data(raw_content: str) -> List[Dict[str, Any]]:
    """Parses CSV data into list of dictionaries (naive implementation without BOM handling)."""
    reader = csv.DictReader(io.StringIO(raw_content))
    return [row for row in reader]
