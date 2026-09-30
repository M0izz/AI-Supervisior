from dataclasses import dataclass
from typing import Optional


@dataclass
class UserRecord:
    user_id: str
    email: str
    name: str
    role: str = "member"
    active: bool = True
