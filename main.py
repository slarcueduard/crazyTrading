import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from fastapi import FastAPI
import threading
import uvicorn
from datetime import datetime

app = FastAPI()

# --- CONFIGURARE ---
API_KEY = os.getenv("EXTENDED_API_KEY")
STARK_PUBLIC = os.getenv("STARK_KEY_PUBLIC")
STARK_PRIVATE = os.getenv("STARK_KEY_PRIVATE")
VAULT_NUMBER = os.getenv("VAULT_NUMBER")
CLIENT_ID = os.getenv("CLIENT_ID")

SYMBOL = "HYPE"
TIMEFRAME = "15m"
LEVERAGE = 10
RISK_USD = 100.0
DAILY_LIMIT = 2

trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "candleSnapshot", "req": {"coin": SYMBOL, "interval": TIMEFRAME, "startTime": int((time.time() - 86400) * 1000)}}
    try:
        r = requests.post(url, json=payload, timeout=10)
        df = pd.DataFrame(r.json())
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except: return pd.DataFrame()

def execute_extended_trade(side, price):
    # Target Profit: $10.5 | Stop Loss: $9.5
    tp = price * 1.0105 if side == "LONG" else price * 0.9895
    sl = price * 0.9905 if side == "LONG" else price * 1.0095
    
    headers = {
        "X-API-KEY": API_KEY,
        "X-STARK-KEY-PUBLIC": STARK_PUBLIC,
        "Content-Type": "application/json"
    }

    order_data = {
        "vault_id": int(VAULT_NUMBER),
        "client_id": int(CLIENT_ID),
        "symbol": f"{SYMBOL}-USDC",
        "side": side,
        "amount": str(round((RISK_USD * LEVERAGE) / price, 4)),
        "price": str(price),
        "type": "LIMIT",
        "tp": str(round(tp, 4)),
        "sl": str(round(sl, 4))
    }
    
    try:
        # CORECȚIE ENDPOINT: Multe platforme noi folosesc /v1/private/order pentru trade-uri cu API Key
        # Încercăm varianta cea mai stabilă conform documentației lor actualizate
        url = "https://api.extended.exchange/v1/order"
        r = requests.post(url, json=order_data, headers=headers, timeout=10)
        
        if r.status_code in [200, 201]:
            print(f"🚀 [EXECUTAT] {side} la {price}. Status: {r.status_code}")
            return True
        else:
            # Dacă dă tot 404, botul se va opri 5 minute ca să nu facă spam
            print(f"⚠️ [REJECTED] Status {r.status_code}: {r.text}")
            if r.status_code == 404:
                time.sleep(300) 
            return False
    except Exception as e:
        print(f"❌ [API ERR]: {e}")
        return False

def bot_loop():
    global trades_today, last_trade_day
    print(f"🤖 Grinder ONLINE. Target: {DAILY_LIMIT} trade-uri/zi.")
    
    while True:
        try:
            if datetime.now().day != last_trade_day:
                trades_today = 0
                last_trade_day = datetime.now().day

            if trades_today < DAILY_LIMIT:
                df = get_market_data()
                if not df.empty:
                    df['hull'] = ta.hma(df['close'], length=9)
                    adx = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14'].iloc[-1]
                    
                    print(f"🔍 [SCAN] Price: {df['close'].iloc[-1]} | ADX: {round(adx, 1)}")

                    if adx > 15:
                        side = "LONG" if df['hull'].iloc[-1] > df['hull'].iloc[-2] else "SHORT"
                        if execute_extended_trade(side, df['close'].iloc[-1]):
                            trades_today += 1
                            print(f"✅ Succes {trades_today}/{DAILY_LIMIT}. Cooldown 20 min.")
                            time.sleep(1200)
            
            time.sleep(60) # Scanăm la fiecare minut
        except Exception as e: 
            print(f"⚠️ Eroare: {e}")
            time.sleep(30)

@app.api_route("/", methods=["GET", "HEAD"])
def status():
    return {"status": "online", "trades": trades_today, "limit": DAILY_LIMIT}

threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
