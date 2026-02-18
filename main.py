import os
from fastapi import FastAPI, Request
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

app = FastAPI()

# 1. Fetch credentials from Render Environment Variables
AGENT_KEY = os.getenv("AGENT_SECRET_KEY")
SUB_ACCOUNT_ADDR = os.getenv("SUB_ACCOUNT_ADDR")

# 2. Setup the Account object (The SDK requires this)
# This converts your private key string into a wallet object the SDK can use
agent_wallet = Account.from_key(AGENT_KEY)

# 3. Correct Exchange Initialization
# 'wallet' is the authorized agent, 'account_address' is the sub-account receiving the trade
exchange = Exchange(
    wallet=agent_wallet, 
    base_url=constants.MAINNET_API_URL, 
    account_address=SUB_ACCOUNT_ADDR
)

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        data = await request.json()
        coin = "HYPE" 
        is_buy = data["action"].lower() == "buy"
        
        # Execute Trade
        print(f"Executing {data['action']} on {coin}...")
        response = exchange.market_open(
            name=coin, 
            is_buy=is_buy, 
            sz=float(data["size"]), 
            px=float(data["price"]), 
            sl_px=float(data["sl"]), 
            tp_px=float(data["tp"])
        )
        return {"status": "success", "response": response}
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"status": "error", "message": str(e)}
