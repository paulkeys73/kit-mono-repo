# app/models/tier.py

from pydantic import BaseModel
from typing import List

class Tier(BaseModel):
    id: str
    name: str
    price: str
    currency: str
    benefits: List[str]
