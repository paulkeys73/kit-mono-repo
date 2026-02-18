import sys
import os

# Add s root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from service.db_service import clear_donations
from service.donation_stats_service import clear_donation_stats

if __name__ == "__main__":
    clear_donations()
    clear_donation_stats()
    print("✅ donations and donation_stats tables cleared")
