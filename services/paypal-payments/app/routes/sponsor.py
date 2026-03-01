# app/routes/sponsor.py

from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from typing import List
from app.models.tier import Tier  # Pydantic model

router = APIRouter(prefix="/sponsors", tags=["Sponsors"])

TIERS_FILE = Path(__file__).parent.parent / "data" / "sponsor_tiers.json"


# -----------------------------
# Helper functions
# -----------------------------
def load_tiers() -> List[Tier]:
    """Always read from file to reflect live updates."""
    if not TIERS_FILE.exists():
        return []
    try:
        with open(TIERS_FILE, "r") as f:
            data = json.load(f)
            return [Tier(**t) for t in data]
    except Exception as e:
        print(f"[ERROR] Failed to load tiers: {e}")
        return []


def save_tiers(tiers: List[Tier]):
    """Persist tier list to JSON file."""
    try:
        with open(TIERS_FILE, "w") as f:
            json.dump([t.dict() for t in tiers], f, indent=4)
    except Exception as e:
        print(f"[ERROR] Failed to save tiers: {e}")


# -----------------------------
# Get all sponsor tiers
# -----------------------------
@router.get("/tiers", response_model=List[Tier])
async def get_sponsor_tiers():
    """Fetch all sponsor tiers — always reloads from disk."""
    return load_tiers()


# -----------------------------
# Create a new tier
# -----------------------------
@router.post("/tiers", response_model=Tier)
async def create_tier(tier: Tier):
    tiers = load_tiers()
    if any(t.id == tier.id for t in tiers):
        raise HTTPException(status_code=400, detail="Tier with this ID already exists")
    tiers.append(tier)
    save_tiers(tiers)
    return tier


# -----------------------------
# Update an existing tier
# -----------------------------
@router.put("/tiers/{tier_id}", response_model=Tier)
async def update_tier(tier_id: str, updates: Tier):
    tiers = load_tiers()
    for i, t in enumerate(tiers):
        if t.id == tier_id:
            tiers[i] = updates
            save_tiers(tiers)
            return updates
    raise HTTPException(status_code=404, detail="Tier not found")


# -----------------------------
# Delete a tier
# -----------------------------
@router.delete("/tiers/{tier_id}")
async def delete_tier(tier_id: str):
    tiers = load_tiers()
    for i, t in enumerate(tiers):
        if t.id == tier_id:
            removed = tiers.pop(i)
            save_tiers(tiers)
            return {"success": True, "removed": removed.dict()}
    raise HTTPException(status_code=404, detail="Tier not found")
