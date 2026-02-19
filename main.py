import os
from fastapi import FastAPI, Request
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

app = FastAPI()

# 1. Setup Account
AGENT_KEY = os.getenv("AGENT_SECRET_KEY")
SUB_ACCOUNT_ADDR = os.getenv("SUB_ACCOUNT_ADDR")
agent_wallet = Account.from_key(AGENT_KEY)

exchange = Exchange(
    wallet=agent_wallet, 
    base_url=constants.MAINNET_API_URL, 
    account_address=SUB_ACCOUNT_ADDR
)

@app.get("/")
def root():
    return {"status": "Bot is awake and running!"}

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        coin = "HYPE" 
        is_buy = data["action"].lower() == "buy"
        
        size = float(data["size"])
        sl_price = round(float(data["sl"]), 4)
        tp_price = round(float(data["tp"]), 4)
        px_price = round(float(data["price"]), 4)

        # Calculate a 10% slippage bumper for trigger orders to guarantee API acceptance
        # If buying, limit must be higher. If selling, limit must be lower.
        sl_limit = round(sl_price * 0.9 if is_buy else sl_price * 1.1, 4)
        tp_limit = round(tp_price * 0.9 if is_buy else tp_price * 1.1, 4)

        print(f"\n--- Signal Received: {data['action'].upper()} {size} {coin} ---")

        # STEP 1: Execute Market Entry
        print(f"1. Placing Entry Order...")
        entry_resp = exchange.market_open(
            name=coin,
            is_buy=is_buy,
            sz=size,
            px=px_price
        )
        print(f"Entry Response: {entry_resp}")

        # STEP 2: Place Stop Loss (Reduce-Only Trigger)
        print(f"2. Placing SL Trigger at {sl_price} (API Limit: {sl_limit})")
        sl_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, 
            sz=size,
            limit_px=sl_limit, # Uses the 10% bumper 
            order_type={"trigger": {"isMarket": True, "triggerPx": sl_price, "tpsl": "sl"}},
            reduce_only=True
        )
        print(f"SL Response: {sl_resp}")

        # STEP 3: Place Take Profit (Reduce-Only Trigger)
        print(f"3. Placing TP Trigger at {tp_price} (API Limit: {tp_limit})")
        tp_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, 
            sz=size,
            limit_px=tp_limit, # Uses the 10% bumper
            order_type={"trigger": {"isMarket": True, "triggerPx": tp_price, "tpsl": "tp"}},
            reduce_only=True
        )
        print(f"TP Response: {tp_resp}")
        print("--- Trade Execution Complete ---\n")

        return {"status": "success", "entry": entry_resp, "sl": sl_resp, "tp": tp_resp}

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}
