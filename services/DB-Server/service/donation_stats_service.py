# app/services/donation_stats_service.py

from sqlalchemy import text
from datetime import datetime, timezone
import logging

from service.db_service import engine

logger = logging.getLogger("db-server")


def upsert_stats(stats: dict) -> dict:
    """
    Upsert monthly donation statistics.
    One row per (month, currency).
    Returns the updated row.
    """
    # Ensure all required keys exist
    required_keys = {
        "currency",
        "today_date",
        "today_total",
        "today_count",
        "month",
        "monthly_target",
        "monthly_total",
        "monthly_count",
        "percent",
        "remaining",
    }

    # Fill default for missing field
    normalized = {k: stats.get(k, 0 if "total" in k or "count" in k or k in ["percent", "remaining"] else None)
                  for k in required_keys}

    # Truncate month to first 7 chars YYYY-MM
    if normalized["month"]:
        normalized["month"] = str(normalized["month"])[:7]

    # Ensure currency is a string and truncated to 7 chars max (Postgres VARCHAR(7))
    normalized["currency"] = str(normalized.get("currency", "USD"))[:7]

    # Add/updates timestamp
    normalized["updated_at"] = datetime.now(timezone.utc)

    sql = text(
        """
        INSERT INTO donation_stats (
            currency,
            today_date,
            today_total,
            today_count,
            month,
            monthly_target,
            monthly_total,
            monthly_count,
            percent,
            remaining,
            updated_at
        )
        VALUES (
            :currency,
            :today_date,
            :today_total,
            :today_count,
            :month,
            :monthly_target,
            :monthly_total,
            :monthly_count,
            :percent,
            :remaining,
            :updated_at
        )
        ON CONFLICT (month, currency)
        DO UPDATE SET
            today_date      = EXCLUDED.today_date,
            today_total     = EXCLUDED.today_total,
            today_count     = EXCLUDED.today_count,
            monthly_target  = EXCLUDED.monthly_target,
            monthly_total   = EXCLUDED.monthly_total,
            monthly_count   = EXCLUDED.monthly_count,
            percent         = EXCLUDED.percent,
            remaining       = EXCLUDED.remaining,
            updated_at      = EXCLUDED.updated_at
        RETURNING *
        """
    )

    with engine.begin() as conn:
        row = conn.execute(sql, normalized).mappings().first()

    if not row:
        raise RuntimeError("Stats upsert failed with no returned row")

    stats_row = dict(row)

    logger.info(
        "📊 Donation stats upserted | month=%s | currency=%s | total=%s | percent=%s",
        stats_row["month"],
        stats_row["currency"],
        stats_row["monthly_total"],
        stats_row["percent"],
    )

    return stats_row


def clear_donation_stats() -> None:
    """Clear all donation stats, restart identity, cascade to dependent tables."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE donation_stats RESTART IDENTITY CASCADE"))
    logger.info("🧹 Donation stats cleared")


def get_current_stats(currency: str = "USD") -> dict:
    """Fetch the most recent donation stats for the given currency."""
    sql = text(
        """
        SELECT *
        FROM donation_stats
        WHERE currency = :currency
        ORDER BY month DESC
        LIMIT 1
        """
    )

    with engine.begin() as conn:
        row = conn.execute(sql, {"currency": currency[:7]}).mappings().first()

    if not row:
        raise ValueError(f"No donation stats found for currency '{currency}'")

    return dict(row)
