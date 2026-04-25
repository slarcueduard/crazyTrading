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

SYMBOL = "HYPE" # Pe Extended, simbolul este adesea doar HYPE
LEVERAGE = 10
RISK_USD = 100.0
DAILY_LIMIT = 2

trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "candleSnapshot", "req": {"coin": SYMBOL, "interval": "15m", "startTime": int((time.time() - 86400) * 1000)}}
    try:
        r = requests.post(url, json=payload, timeout=10)
        df = pd.DataFrame(r.json())
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except: return pd.DataFrame()

def execute_extended_trade(side, price):
    # MATEMATICĂ: 100$ * 10x * 1.05% = 10.5$ Profit | 100$ * 10x * 0.95% = 9.5$ Loss
    tp = price * 1.0105 if side == "LONG" else price * 0.9895
    sl = price * 0.9905 if side == "LONG" else price * 1.0095
    
    order_data = {
        "api_key": API_KEY,
        "stark_key": STARK_PUBLIC,
        "vault_id": VAULT_NUMBER,
        "client_id": CLIENT_ID,
        "symbol": SYMBOL, # Încercăm formatul simplu
        "side": side,
        "amount": (RISK_USD * LEVERAGE) / price,
        "price": price,
        "type": "LIMIT",
        "tp": tp,
        "sl": sl
    }
    
    try:
        # CORECȚIE URL: Endpoint-ul corect pentru plasare ordine REST
        r = requests.post("https://api.extended.exchange/v1/order", json=order_data, timeout=10)
        
        if r.status_code in [200, 201]:
            print(f"🚀 [EXECUTAT] {side} la {price}. Status: {r.status_code}")
            return True
        else:
            # DEBUG: Ne arată EXACT de ce dă 404 sau altă eroare
            print(f"⚠️ [REJECTED] Status {r.status_code}: {r.text}")
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
                    
                    # Log-ul de scanare să știm că e treaz
                    print(f"🔍 [SCAN] Price: {df['close'].iloc[-1]} | ADX: {round(adx, 1)}")

                    if adx > 15:
                        side = "LONG" if df['hull'].iloc[-1] > df['hull'].iloc[-2] else "SHORT"
                        if execute_extended_trade(side, df['close'].iloc[-1]):
                            trades_today += 1
                            print(f"✅ Succes {trades_today}/{DAILY_LIMIT}. Cooldown 15 min.")
                            time.sleep(900)
            
            time.sleep(60)
        except Exception as e: time.sleep(30)

# REPARARE EROARE 405: Suport complet pentru UptimeRobot (HEAD & GET)
@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "online", "trades": trades_today}

threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
