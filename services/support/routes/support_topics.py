# routes/support_topics.py
from fastapi import APIRouter

router = APIRouter(
    prefix="/support-topics",
    tags=["SupportTopics"]
)

# Predefined support topic
SUPPORT_TOPICS = {
    "Development Task": [
        "Build me a website",
        "Migrate my site",
        "Deploy my website",
        "Custom development"
    ],
    "Donations and Payment": [
        "Donation issues",
        "Alternative payment methods",
        "More information how to donate",
        "Why should we donate"
    ],
    "Websites and Service Maintenance": [
        "Debug and fix my website",
        "Fix Bug on my server",
        "Server updates and Maintenance"
    ],
    
}

@router.get("/", summary="Get all support topics", description="Retrieve all predefined support topics.")
async def get_support_topics():
    return SUPPORT_TOPICS
