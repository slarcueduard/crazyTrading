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

# 2. Add this "Welcome Mat" for UptimeRobot to fix the 405 Error
@app.get("/")
def root():
    return {"status": "Bot is awake and running!"}

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        coin = "HYPE" 
        is_buy = data["action"].lower() == "buy"
        
        # --- FIX 1: Defined 'size' correctly ---
        size = float(data["size"])
        
        # --- FIX 2: Fixed Indentation & Rounding ---
        sl_price = round(float(data["sl"]), 4)
        tp_price = round(float(data["tp"]), 4)
        px_price = round(float(data["price"]), 4)

        print(f"--- Signal Received: {data['action']} {coin} ---")

        # STEP 1: Execute Market Entry
        print(f"1. Placing Entry Order...")
        entry_resp = exchange.market_open(
            name=coin,
            is_buy=is_buy,
            sz=size,
            px=px_price # Uses rounded price
        )
        print("Entry Sent.")

        # STEP 2: Place Stop Loss (Reduce-Only Trigger)
        print(f"2. Placing SL at {sl_price}")
        sl_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, # Opposite of entry
            sz=size,
            limit_px=sl_price, 
            order_type={"trigger": {"isMarket": True, "triggerPx": sl_price, "tpsl": "sl"}},
            reduce_only=True
        )

        # STEP 3: Place Take Profit (Reduce-Only Trigger)
        print(f"3. Placing TP at {tp_price}")
        tp_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, # Opposite of entry
            sz=size,
            limit_px=tp_price,
            order_type={"trigger": {"isMarket": True, "triggerPx": tp_price, "tpsl": "tp"}},
            reduce_only=True
        )

        return {"status": "success", "entry": entry_resp, "sl": sl_resp, "tp": tp_resp}

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}
