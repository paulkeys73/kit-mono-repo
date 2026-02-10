# app/services/db_service.py

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
    JSON,
    Numeric,
    func,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
import uuid

# -----------------------------
# Database setup
# -----------------------------
DATABASE_URL = "postgresql+psycopg2://kit:admin123Pw@localhost:5432/knightindustrytech"

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------
# Models
# -----------------------------
class Donation(Base):
    __tablename__ = "Payments"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    status = Column(String(32), nullable=False, default="PENDING")

    full_name = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)

    card_last4 = Column(String(4), nullable=True)
    card_brand = Column(String(32), nullable=True)
    card_type = Column(String(16), nullable=True)
    network = Column(String(64), nullable=True)
    network_reference_id = Column(String, nullable=True)

    paypal_fee = Column(Numeric(12, 2), nullable=True)
    net_amount = Column(Numeric(12, 2), nullable=True)

    tier_id = Column(String, nullable=True)

    order_id = Column(String, nullable=True, index=True)
    source = Column(String(32), nullable=True)
    method = Column(String(32), nullable=True)
    billing_full_name = Column(String, nullable=True)
    billing_country = Column(String(64), nullable=True)
    payment_type = Column(String(16), nullable=True)

    extra_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

# -----------------------------
# Initialize DB
# -----------------------------
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

# -----------------------------
# CRUD / Utility Functions
# -----------------------------
def insert_donation(donation_data: Dict) -> Donation:
    """Insert a new donation."""
    session = SessionLocal()
    try:
        donation = Donation(**donation_data)
        session.add(donation)
        session.commit()
        session.refresh(donation)
        return donation
    finally:
        session.close()

def get_donations(filter_dict: Optional[Dict] = None) -> List[Donation]:
    """Fetch donations, optionally filtered."""
    session = SessionLocal()
    try:
        query = session.query(Donation)
        if filter_dict:
            for k, v in filter_dict.items():
                query = query.filter(getattr(Donation, k) == v)
        return query.all()
    finally:
        session.close()

def get_donation_by_id(donation_id: str) -> Optional[Donation]:
    """Fetch donation by primary key ID."""
    session = SessionLocal()
    try:
        return session.query(Donation).filter(Donation.id == donation_id).first()
    finally:
        session.close()

def get_donation_by_order_id(order_id: str) -> Optional[Donation]:
    """Fetch donation by order_id."""
    session = SessionLocal()
    try:
        return session.query(Donation).filter(Donation.order_id == order_id).first()
    finally:
        session.close()

def update_donation(donation_id: str, updates: Dict) -> Optional[Donation]:
    """Update donation by ID."""
    session = SessionLocal()
    try:
        donation = session.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return None
        for k, v in updates.items():
            if hasattr(donation, k):
                setattr(donation, k, v)
        session.commit()
        session.refresh(donation)
        return donation
    finally:
        session.close()

def update_donation_by_order_id(order_id: str, updates: Dict) -> Optional[Donation]:
    """Update donation by order_id or create if not exists (replay-safe)."""
    session = SessionLocal()
    try:
        donation = session.query(Donation).filter(Donation.order_id == order_id).first()

        # Replay-safe inserted
        if not donation:
            donation = Donation(
                id=str(uuid.uuid4()),
                order_id=order_id,
                **updates,
            )
            if "status" in updates:
                sanitize_donation_fields(donation, updates["status"])
            session.add(donation)
            session.commit()
            session.refresh(donation)
            return donation

        # Normal updates
        status_before = donation.status
        for k, v in updates.items():
            if hasattr(donation, k):
                setattr(donation, k, v)
        if "status" in updates and updates["status"] != status_before:
            sanitize_donation_fields(donation, updates["status"])
        session.commit()
        session.refresh(donation)
        return donation
    finally:
        session.close()

def sanitize_donation_fields(donation: Donation, new_status: str) -> None:
    """
    Clears fields that are invalid for the given status.
    Guarantees replay safety and prevents stale data.
    """
    if new_status != "COMPLETED":
        for field in (
            "paypal_fee",
            "net_amount",
            "card_last4",
            "card_brand",
            "card_type",
            "network",
            "network_reference_id",
            "payment_type",
            "billing_full_name",
            "billing_country",
        ):
            setattr(donation, field, None)
    if new_status in ("FAILED", "CANCELLED"):
        donation.extra_metadata = None

def sum_donations(filter_dict: Optional[Dict] = None) -> Tuple[float, int]:
    """Return total amount and count of donations."""
    session = SessionLocal()
    try:
        query = session.query(
            func.coalesce(func.sum(Donation.amount), 0).label("total"),
            func.count(Donation.id).label("count"),
        )
        if filter_dict:
            for k, v in filter_dict.items():
                query = query.filter(getattr(Donation, k) == v)
        total, count = query.first()
        return float(total), int(count)
    finally:
        session.close()

def clear_donations() -> None:
    """Delete all donations safely."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE donations RESTART IDENTITY CASCADE"))

# -----------------------------
# Stats-ready (upsert)
# -----------------------------
class DonationStats(Base):
    __tablename__ = "Payment_stats"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    currency = Column(String(8), nullable=False, default="USD")
    today_date = Column(DateTime(timezone=True), nullable=False)
    today_total = Column(Numeric(12,2), nullable=False)
    today_count = Column(Integer, nullable=False)
    month = Column(String(7), nullable=False)  # YYYY-MM
    monthly_target = Column(Numeric(12,2), nullable=False)
    monthly_total = Column(Numeric(12,2), nullable=False)
    monthly_count = Column(Integer, nullable=False)
    percent = Column(Numeric(5,2), nullable=False)
    remaining = Column(Numeric(12,2), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

def upsert_stats(stats_data: Dict) -> DonationStats:
    """Insert or update donation statistics."""
    session = SessionLocal()
    try:
        existing = session.query(DonationStats).filter(
            DonationStats.currency == stats_data["currency"],
            DonationStats.month == stats_data["month"]
        ).first()
        if existing:
            for k, v in stats_data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            session.commit()
            session.refresh(existing)
            return existing

        new_stat = DonationStats(**stats_data)
        session.add(new_stat)
        session.commit()
        session.refresh(new_stat)
        return new_stat
    finally:
        session.close()
