# # app/models/requests.py
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from decimal import Decimal

class CreateOrderRequest(BaseModel):
    amount: str
    currency: str = "USD"

class CaptureWithCardRequest(BaseModel):
    card_number: str
    card_expiry: str  # MM/YY or MM/YYYY
    card_cvv: str
    full_name: str
    user_name: Optional[str] = None        # <-- added
    user_email: Optional[EmailStr] = None  # <-- added

class CaptureOrderResponse(BaseModel):
    success: bool
    order_id: str
    original_amount: Decimal
    fee_deducted: Decimal
    net_amount: Decimal
    status: str                         # <-- new field
    capture_response: Optional[Dict[str, Any]] = None
    donation_info: Optional[Dict[str, Any]] = None