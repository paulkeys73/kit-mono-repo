# E:\DB-Server\stat_calculator.py

from datetime import datetime, date, timezone
from decimal import Decimal
import logging

from sqlalchemy import text

from service.db_service import engine
from service.donation_stats_service import (
    insert_or_update_donation_stats,
)

logger = logging.getLogger("stat-calculator")
logger.setLevel(logging.INFO)


# -----------------------------------------------
# Helpers
# -------------------------------------------------

def _today_range():
    today = date.today()
    return (
        datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc),
    )


def _month_range():
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    return start, end


# -------------------------------------------------
# Core calculator
# -------------------------------------------------

def calculate_and_update_stats(currency: str = "USD") -> dict:
    """
    Recalculate donation statistics and persist via donation_stats_service.
    """

    today_start, today_end = _today_range()
    month_start, month_end = _month_range()

    with engine.begin() as conn:
        # -----------------------------
        # Today stats
        # -----------------------------
        today = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total,
                    COUNT(*) AS count
                FROM donations
                WHERE status = 'COMPLETED'
                  AND currency = :currency
                  AND created_at BETWEEN :start AND :end
                """
            ),
            {
                "currency": currency,
                "start": today_start,
                "end": today_end,
            },
        ).mappings().first()

        # -----------------------------
        # Monthly stats
        # -----------------------------
        month = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total,
                    COUNT(*) AS count
                FROM donations
                WHERE status = 'COMPLETED'
                  AND currency = :currency
                  AND created_at >= :start
                  AND created_at < :end
                """
            ),
            {
                "currency": currency,
                "start": month_start,
                "end": month_end,
            },
        ).mappings().first()

        # -----------------------------
        # Monthly target (existing row)
        # -----------------------------
        target_row = conn.execute(
            text(
                """
                SELECT monthly_target
                FROM donation_stats
                WHERE currency = :currency
                ORDER BY month DESC
                LIMIT 1
                """
            ),
            {"currency": currency},
        ).mappings().first()

    monthly_target = (
        Decimal(target_row["monthly_target"]) if target_row else Decimal("0")
    )
    monthly_total = Decimal(month["total"])
    remaining = max(monthly_target - monthly_total, Decimal("0"))

    percent = (
        float((monthly_total / monthly_target) * 100)
        if monthly_target > 0
        else 0.0
    )

    stats_payload = {
        "currency": currency,
        "today_date": date.today().isoformat(),
        "today_total": Decimal(today["total"]),
        "today_count": today["count"],
        "month": month_start.strftime("%Y-%m"),
        "monthly_target": monthly_target,
        "monthly_total": monthly_total,
        "monthly_count": month["count"],
        "percent": round(percent, 2),
        "remaining": remaining,
    }

    # -----------------------------
    # Persist via service
    # -----------------------------
    insert_or_update_donation_stats(stats_payload)

    logger.info(
        "📊 Stats recalculated | currency=%s | month=%s | total=%s",
        currency,
        stats_payload["month"],
        stats_payload["monthly_total"],
    )

    return stats_payload


# -------------------------------------------------
# TEST BLOCK
# -------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("🔄 Recalculating donation stats...")
    stats = calculate_and_update_stats(currency="USD")

    print("✅ Stats updated:")
    for k, v in stats.items():
        print(f"{k}: {v}")
