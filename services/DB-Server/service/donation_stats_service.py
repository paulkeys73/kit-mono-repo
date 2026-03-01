# app/services/donation_stats_service.py

from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import os

from service.db_service import engine

logger = logging.getLogger("db-server")

DEFAULT_MONTHLY_TARGET_USD = Decimal(os.getenv("DONATION_MONTHLY_TARGET_USD", "7000"))


def _default_monthly_target(currency: str) -> Decimal:
    return DEFAULT_MONTHLY_TARGET_USD if str(currency or "").upper() == "USD" else Decimal("0")


def _normalized_monthly_target(currency: str, raw_target) -> Decimal:
    target = Decimal(str(raw_target or 0))
    fallback = _default_monthly_target(currency)
    if target <= 0 and fallback > 0:
        return fallback
    return target


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
    normalized["monthly_target"] = _normalized_monthly_target(
        normalized["currency"],
        normalized.get("monthly_target"),
    )
    monthly_total = Decimal(str(normalized.get("monthly_total", 0) or 0))
    monthly_target = Decimal(str(normalized.get("monthly_target", 0) or 0))
    normalized["remaining"] = max(monthly_target - monthly_total, Decimal("0"))
    normalized["percent"] = round(float((monthly_total / monthly_target) * 100), 2) if monthly_target > 0 else 0.0

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
    """
    Fetch the most recent donation stats for the given currency.
    If none exist, automatically bootstrap a default monthly row.
    """

    normalized_currency = str(currency or "USD")[:7]

    sql = text(
        """
        SELECT *
        FROM donation_stats
        WHERE currency = :currency
        ORDER BY month DESC
        LIMIT 1
        """
    )

    # READ ONLY — no need for begin()
    with engine.connect() as conn:
        row = conn.execute(sql, {"currency": normalized_currency}).mappings().first()

    if row:
        stats = dict(row)
        monthly_total = Decimal(str(stats.get("monthly_total", 0) or 0))
        target = _normalized_monthly_target(stats.get("currency", normalized_currency), stats.get("monthly_target"))

        if Decimal(str(stats.get("monthly_target", 0) or 0)) != target:
            stats["monthly_target"] = target
            stats["remaining"] = max(target - monthly_total, Decimal("0"))
            stats["percent"] = float((monthly_total / target) * 100) if target > 0 else 0.0
            stats = upsert_stats(stats)

        return stats

    # 🔥 BOOTSTRAP LOGIC (self-healing system)
    logger.warning(
        "No donation stats found for currency '%s' — creating bootstrap entry",
        normalized_currency,
    )

    now = datetime.now(timezone.utc)

    default_stats = {
        "currency": normalized_currency,
        "today_date": now.date(),
        "today_total": 0,
        "today_count": 0,
        "month": now.strftime("%Y-%m"),
        "monthly_target": _default_monthly_target(normalized_currency),
        "monthly_total": 0,
        "monthly_count": 0,
        "percent": 0,
        "remaining": 0,
    }

    # Use your existing upsert logic
    return upsert_stats(default_stats)


def recalculate_current_stats(currency: str = "USD") -> dict:
    """
    Recalculate stats directly from the payments table and upsert donation_stats.
    This keeps donation_stats in sync with live payment events.
    """
    normalized_currency = str(currency or "USD")[:7]
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")

    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    with engine.connect() as conn:
        today_row = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total,
                    COUNT(*) AS count
                FROM payments
                WHERE status = 'COMPLETED'
                  AND currency = :currency
                  AND created_at >= :day_start
                  AND created_at < :day_end
                """
            ),
            {
                "currency": normalized_currency,
                "day_start": day_start,
                "day_end": day_end,
            },
        ).mappings().first()

        month_row = conn.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total,
                    COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS net_total,
                    COUNT(*) AS count
                FROM payments
                WHERE status = 'COMPLETED'
                  AND currency = :currency
                  AND created_at >= :month_start
                  AND created_at < :month_end
                """
            ),
            {
                "currency": normalized_currency,
                "month_start": month_start,
                "month_end": month_end,
            },
        ).mappings().first()

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
            {"currency": normalized_currency},
        ).mappings().first()

        current_month_row = conn.execute(
            text(
                """
                SELECT *
                FROM donation_stats
                WHERE currency = :currency
                  AND month = :month
                LIMIT 1
                """
            ),
            {"currency": normalized_currency, "month": month_key},
        ).mappings().first()

    monthly_target = _normalized_monthly_target(
        normalized_currency,
        (target_row or {}).get("monthly_target", 0),
    )
    monthly_total = Decimal(str((month_row or {}).get("total", 0) or 0))
    remaining = max(monthly_target - monthly_total, Decimal("0"))
    percent = float((monthly_total / monthly_target) * 100) if monthly_target > 0 else 0.0

    normalized = {
        "currency": normalized_currency,
        "today_date": now.date(),
        "today_total": Decimal(str((today_row or {}).get("total", 0) or 0)),
        "today_count": int((today_row or {}).get("count", 0) or 0),
        "month": month_key,
        "monthly_target": monthly_target,
        "monthly_total": monthly_total,
        "monthly_count": int((month_row or {}).get("count", 0) or 0),
        "percent": round(percent, 2),
        "remaining": remaining,
    }

    def _same(existing: dict | None, expected: dict) -> bool:
        if not existing:
            return False
        return (
            str(existing.get("currency", ""))[:7] == expected["currency"]
            and str(existing.get("month", ""))[:7] == expected["month"]
            and str(existing.get("today_date")) == str(expected["today_date"])
            and Decimal(str(existing.get("today_total", 0) or 0)) == Decimal(str(expected["today_total"] or 0))
            and int(existing.get("today_count", 0) or 0) == int(expected["today_count"] or 0)
            and Decimal(str(existing.get("monthly_target", 0) or 0)) == Decimal(str(expected["monthly_target"] or 0))
            and Decimal(str(existing.get("monthly_total", 0) or 0)) == Decimal(str(expected["monthly_total"] or 0))
            and int(existing.get("monthly_count", 0) or 0) == int(expected["monthly_count"] or 0)
            and round(float(existing.get("percent", 0) or 0), 2) == round(float(expected["percent"] or 0), 2)
            and Decimal(str(existing.get("remaining", 0) or 0)) == Decimal(str(expected["remaining"] or 0))
        )

    if _same(dict(current_month_row) if current_month_row else None, normalized):
        stats_row = dict(current_month_row)
        stats_row["net_raised"] = Decimal(str((month_row or {}).get("net_total", 0) or 0))
        return stats_row

    stats_row = upsert_stats(normalized)
    stats_row["net_raised"] = Decimal(str((month_row or {}).get("net_total", 0) or 0))

    logger.info(
        "📡 Donation stats recalculated from payments | currency=%s | monthly_total=%s | monthly_count=%s",
        normalized_currency,
        stats_row.get("monthly_total"),
        stats_row.get("monthly_count"),
    )

    return stats_row

