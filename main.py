import os
from fastapi import FastAPI, Request
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

app = FastAPI()

AGENT_KEY = os.getenv("AGENT_SECRET_KEY")
SUB_ACCOUNT_ADDR = os.getenv("SUB_ACCOUNT_ADDR")
agent_wallet = Account.from_key(AGENT_KEY)

exchange = Exchange(agent_wallet, constants.MAINNET_API_URL, account_address=SUB_ACCOUNT_ADDR)
info = Info(constants.MAINNET_API_URL, skip_ws=True)

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        coin = "HYPE"
        action = data["action"].lower()
        px_price = round(float(data["price"]), 4)

        print(f"\n--- Signal Received: {action.upper()} {coin} ---")

        # ==========================================
        # PARACHUTE PROTOCOL: Sweep & Clear
        # ==========================================
        if action in ["close_long", "close_short"]:
            print("1. Sweeping pending SL/TP orders...")
            open_orders = info.open_orders(SUB_ACCOUNT_ADDR)
            for order in open_orders:
                if order["coin"] == coin:
                    exchange.cancel(coin, order["oid"])
            
            print("2. Closing active position...")
            user_state = info.user_state(SUB_ACCOUNT_ADDR)
            for pos in user_state["assetPositions"]:
                if pos["position"]["coin"] == coin:
                    pos_size = float(pos["position"]["szi"])
                    if (pos_size > 0 and action == "close_long") or (pos_size < 0 and action == "close_short"):
                        is_buy = pos_size < 0 
                        limit_px = round(px_price * 1.1 if is_buy else px_price * 0.9, 4)
                        
                        exchange.order(
                            name=coin, is_buy=is_buy, sz=abs(pos_size), limit_px=limit_px,
                            order_type={"limit": {"tif": "Ioc"}}, reduce_only=True
                        )
                        print("Position Parachuted Successfully.")
            return {"status": "success", "message": "Parachute executed"}

        # ==========================================
        # ENTRY PROTOCOL: Target & Stop Loss
        # ==========================================
        if action in ["buy", "sell"]:
            is_buy = (action == "buy")
            size = float(data["size"])
            sl_price = round(float(data["sl"]), 4)
            tp_price = round(float(data["tp"]), 4)
            sl_limit = round(sl_price * 0.9 if is_buy else sl_price * 1.1, 4)

            print("1. Placing Market Entry...")
            entry_resp = exchange.market_open(coin, is_buy, size, px_price)
            
            print("2. Placing Taker Stop Loss...")
            exchange.order(
                name=coin, is_buy=not is_buy, sz=size, limit_px=sl_limit,
                order_type={"trigger": {"isMarket": True, "triggerPx": sl_price, "tpsl": "sl"}},
                reduce_only=True
            )

            print("3. Placing Maker Take Profit (ALO)...")
            exchange.order(
                name=coin, is_buy=not is_buy, sz=size, limit_px=tp_price,
                order_type={"limit": {"tif": "Alo"}}, reduce_only=True
            )
            return {"status": "success", "message": "Trade Opened with SL/TP"}

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}
