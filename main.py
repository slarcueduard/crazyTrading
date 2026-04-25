import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from fastapi import FastAPI
import threading
import uvicorn
from datetime import datetime

# 1. Inițializarea aplicației FastAPI pentru Render
app = FastAPI()

# --- CONFIGURARE DIN ENVIRONMENT VARIABLES ---
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

# Starea internă a botului
trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    """Preluare date prin Hyperliquid API (Sursa pentru Extended)."""
    url = "https://api.hyperliquid.xyz/info"
    payload = {
        "type": "candleSnapshot",
        "req": {"coin": SYMBOL, "interval": TIMEFRAME, "startTime": int((time.time() - 86400) * 1000)}
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        df = pd.DataFrame(r.json())
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"❌ [API ERROR]: {e}")
        return pd.DataFrame()

def execute_extended_trade(side, price):
    """Execuție cu gestionarea riscului și validare Status 200."""
    # Matematică: 100$ * 10x * 1.05% = 10.5$ Profit | 100$ * 10x * 0.95% = 9.5$ Loss
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
        # Endpoint-ul standard Extended pentru plasare ordine
        r = requests.post("https://api.extended.exchange/v1/orders", json=order_data, timeout=10)
        
        if r.status_code in [200, 201]:
            print(f"🚀 [EXECUTAT] {side} la {price}. TP: {tp} | SL: {sl}")
            return True
        else:
            print(f"⚠️ [REJECTED] Status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"❌ [CONN ERROR]: {e}")
        return False

def bot_loop():
    """Bucla principală cu protecție la Double-Firing."""
    global trades_today, last_trade_day
    print("🤖 Sistemul Grinder v2.0 Online. Miza: 100$ | Lev: 10x")
    
    while True:
        try:
            now = datetime.now()
            if now.day != last_trade_day:
                trades_today = 0
                last_trade_day = now.day
                print("📅 Reset zilnic efectuat.")

            if trades_today < DAILY_LIMIT:
                df = get_market_data()
                if not df.empty and len(df) > 50:
                    # Indicatori Airdrop Grinder
                    df['hull'] = ta.hma(df['close'], length=9)
                    adx = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14'].iloc[-1]
                    
                    curr_hull = df['hull'].iloc[-1]
                    prev_hull = df['hull'].iloc[-2]
                    
                    side = None
                    # Filtre optimizate pentru 2 trade-uri/zi
                    if curr_hull > prev_hull and adx > 15: side = "LONG"
                    elif curr_hull < prev_hull and adx > 15: side = "SHORT"

                    if side:
                        if execute_extended_trade(side, df['close'].iloc[-1]):
                            trades_today += 1
                            print(f"✅ Trade {trades_today}/{DAILY_LIMIT} confirmat. Cooldown 20 min.")
                            time.sleep(1200) # Prevenire dublă execuție pe același semnal
            
            time.sleep(60) # Scanare la fiecare minut
        except Exception as e:
            print(f"⚠️ [LOOP ERROR]: {e}")
            time.sleep(30)

@app.get("/")
def health_check():
    return {"status": "running", "trades_today": trades_today, "limit": DAILY_LIMIT}

# Pornire thread fundal
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
