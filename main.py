import os
from fastapi import FastAPI, Request
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

app = FastAPI()

# Credentials from Render Environment Variables
# Use the Agent Private Key you just saved!
AGENT_KEY = os.getenv("AGENT_SECRET_KEY") 
SUB_ACCOUNT_ADDR = os.getenv("SUB_ACCOUNT_ADDR")

# Initialize Agent
# We point the exchange to use the sub-account specifically
exchange = Exchange(SUB_ACCOUNT_ADDR, AGENT_KEY, base_url=constants.MAINNET_API_URL, account_address=SUB_ACCOUNT_ADDR)

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    coin = "HYPE" 
    is_buy = data["action"].lower() == "buy"
    
    # Execute Trade
    # This automatically opens the position and sets SL/TP as defined in your TradingView Message
    print(f"Executing {data['action']} on {coin}")
    response = exchange.market_open(
        name=coin, 
        is_buy=is_buy, 
        sz=float(data["size"]), 
        px=float(data["price"]), 
        sl_px=float(data["sl"]), 
        tp_px=float(data["tp"])
    )
    return {"status": "success", "response": response}
