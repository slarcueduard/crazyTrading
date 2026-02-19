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

        # 10% bumper ONLY applies to the Stop Loss now, since it is a Market Trigger
        sl_limit = round(sl_price * 0.9 if is_buy else sl_price * 1.1, 4)

        print(f"\n--- Signal Received: {data['action'].upper()} {size} {coin} ---")

        # STEP 1: Execute Market Entry (Taker)
        print(f"1. Placing Entry Order...")
        entry_resp = exchange.market_open(
            name=coin,
            is_buy=is_buy,
            sz=size,
            px=px_price
        )
        print(f"Entry Response: {entry_resp}")

        # STEP 2: Place Stop Loss (Taker Market Trigger - Safety First)
        print(f"2. Placing SL Trigger at {sl_price}...")
        sl_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, 
            sz=size,
            limit_px=sl_limit, 
            order_type={"trigger": {"isMarket": True, "triggerPx": sl_price, "tpsl": "sl"}},
            reduce_only=True
        )
        print(f"SL Response: {sl_resp}")

        # STEP 3: Place Take Profit (Resting Limit Order - Maker Fees)
        print(f"3. Placing TP Maker Limit at {tp_price}...")
        tp_resp = exchange.order(
            name=coin,
            is_buy=not is_buy, 
            sz=size,
            limit_px=tp_price, # Rests exactly at your target price
            order_type={"limit": {"tif": "Alo"}}, # ALO strictly enforces Maker execution
            reduce_only=True
        )
        print(f"TP Response: {tp_resp}")
        print("--- Trade Execution Complete ---\n")

        return {"status": "success", "entry": entry_resp, "sl": sl_resp, "tp": tp_resp}

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}
