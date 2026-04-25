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

# --- CONFIGURARE DIN ENVIRONMENT (VALORI DIN IMAGINEA 0c58a3) ---
API_KEY = os.getenv("EXTENDED_API_KEY")
STARK_PUBLIC = os.getenv("STARK_KEY_PUBLIC")
STARK_PRIVATE = os.getenv("STARK_KEY_PRIVATE")
VAULT_NUMBER = os.getenv("VAULT_NUMBER")
CLIENT_ID = os.getenv("CLIENT_ID")

SYMBOL = "HYPE"
TIMEFRAME = "15m"
LEVERAGE = 10
RISK_USD = 100.0  # All-in
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
    # CALCULE MATEMATICE RISC/PROFIT
    # Profit Target: +1.05% (~$10.5) | Stop Loss: -0.95% (~$9.5)
    tp = price * 1.0105 if side == "LONG" else price * 0.9895
    sl = price * 0.9905 if side == "LONG" else price * 1.0095
    
    order_data = {
        "api_key": API_KEY,
        "stark_key": STARK_PUBLIC,
        "vault_id": VAULT_NUMBER,
        "client_id": CLIENT_ID,
        "symbol": f"{SYMBOL}-USDC",
        "side": side,
        "amount": (RISK_USD * LEVERAGE) / price,
        "price": price,
        "type": "LIMIT",
        "tp": tp,
        "sl": sl
    }
    
    try:
        # Folosim endpoint-ul verificat pentru Extended
        r = requests.post("https://api.extended.exchange/v1/order", json=order_data, timeout=10)
        if r.status_code in [200, 201]:
            print(f"🚀 [EXECUTAT] {side} la {price}. TP: {tp} | SL: {sl}")
            return True
        else:
            print(f"⚠️ [REJECTED] Status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"❌ [API ERR]: {e}")
        return False

def bot_loop():
    global trades_today, last_trade_day
    print(f"🤖 Grinder ONLINE. Miza: ${RISK_USD} | Lev: {LEVERAGE}x")
    
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
                    
                    side = None
                    if df['hull'].iloc[-1] > df['hull'].iloc[-2] and adx > 15: side = "LONG"
                    elif df['hull'].iloc[-1] < df['hull'].iloc[-2] and adx > 15: side = "SHORT"

                    if side:
                        if execute_extended_trade(side, df['close'].iloc[-1]):
                            trades_today += 1
                            print(f"✅ Trade {trades_today}/{DAILY_LIMIT} confirmat. Cooldown 20 min.")
                            time.sleep(1200)
            
            time.sleep(60)
        except Exception as e: time.sleep(30)

@app.api_route("/", methods=["GET", "HEAD"])
def status():
    return {"status": "online", "trades": trades_today, "limit": DAILY_LIMIT}

threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
