import requests

# -----------------------------
# Step 1: Create PayPal orders
# -----------------------------
create_url = "http://localhost:8800/orders/create-order"
payload = {
    "amount": 25.50,
    "currency": "USD",
    "user_id": 3,
    "username": "jamalbinda",
    "first_name": "Test",
    "last_name": "User",
    "email": "hello_jamal@mail.com"
}

try:
    resp = requests.post(create_url, json=payload)
    print("Create Order Response:")
    print(resp.status_code)
    order_data = resp.json()
    print(order_data)
except Exception as e:
    print("Failed to create order:", e)
    order_data = None

# -----------------------------
# Step 2: Fetch donation stats
# -----------------------------
stats_url = "http://localhost:8011/donation-stats"  # Update port/path if needed

try:
    stats_resp = requests.get(stats_url)
    print("\nDonation Stats Response:")
    print(stats_resp.status_code)
    print(stats_resp.json())
except Exception as e:
    print("Failed to fetch donation stats:", e)
