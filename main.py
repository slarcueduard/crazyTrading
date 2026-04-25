import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from fastapi import FastAPI
import threading
import uvicorn
from datetime import datetime

# 1. Inițializarea aplicației
app = FastAPI()

# --- CONFIGURARE DIN ENVIRONMENT VARIABLES (RENDER) ---
API_KEY = os.getenv("EXTENDED_API_KEY")
STARK_PUBLIC = os.getenv("STARK_KEY_PUBLIC")
STARK_PRIVATE = os.getenv("STARK_KEY_PRIVATE")
VAULT_NUMBER = os.getenv("VAULT_NUMBER")
CLIENT_ID = os.getenv("CLIENT_ID")

SYMBOL = "HYPE" # Activul principal pentru volum
TIMEFRAME = "15m"
LEVERAGE = 10
RISK_USD = 100.0
DAILY_LIMIT = 2

# Starea botului
trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    """Obține datele de piață direct de la Hyperliquid API."""
    url = "https://api.hyperliquid.xyz/info"
    headers = {"User-Agent": "Mozilla/5.0"}
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": SYMBOL,
            "interval": TIMEFRAME,
            "startTime": int((time.time() - 86400) * 1000)
        }
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()
            
        data = r.json()
        df = pd.DataFrame(data)
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
        
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        return df
    except Exception as e:
        print(f"❌ [API ERROR]: {e}")
        return pd.DataFrame()

def check_signals(df):
    """Logica 'Airdrop Grinder': Prioritate pe Execuție și Volum."""
    if df.empty or len(df) < 50:
        return None

    # Indicatori optimizați pentru frecvență (Hull 9 + ADX 15)
    df['hull'] = ta.hma(df['close'], length=9)
    adx_series = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
    df['vol_sma'] = ta.sma(df['volume'], length=10)

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    current_adx = adx_series.iloc[-1]

    # Heartbeat Log - Să știi exact ce vede botul în fiecare minut
    print(f"🔍 [SCAN] Price: {curr['close']} | ADX: {round(current_adx, 1)} | Hull: {'UP' if curr['hull'] > prev['hull'] else 'DOWN'} | Vol: {round(curr['volume']/curr['vol_sma'], 2)}x")

    # Condiții relaxate pentru a asigura cele 2 trade-uri/zi
    long_cond = (curr['hull'] > prev['hull'] and current_adx > 15 and curr['volume'] > curr['vol_sma'] * 1.1)
    short_cond = (curr['hull'] < prev['hull'] and current_adx > 15 and curr['volume'] > curr['vol_sma'] * 1.1)

    if long_cond: return "LONG"
    if short_cond: return "SHORT"
    return None

def execute_extended_trade(side, price):
    """Execută ordinul LIMIT pe Extended pentru a fi Maker (Puncte Airdrop)."""
    # Calcul profit net țintă: $10 (aprox 1% mișcare)
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
        r = requests.post("https://api.extended.exchange/v1/order", json=order_data, timeout=10)
        print(f"🚀 [TRADE] {side} trimis la {price}. Status: {r.status_code}")
    except Exception as e:
        print(f"❌ [EXECUTION ERROR]: {e}")

def bot_loop():
    """Motorul principal de trading."""
    global trades_today, last_trade_day
    print("🤖 Sistemul Sniper Airdrop este ONLINE.")
    
    while True:
        try:
            # Reset zilnic la miezul nopții
            now = datetime.now()
            if now.day != last_trade_day:
                print(f"📅 Zi nouă. Resetăm contorul de trade-uri.")
                trades_today = 0
                last_trade_day = now.day

            if trades_today < DAILY_LIMIT:
                df = get_market_data()
                signal = check_signals(df)
                
                if signal:
                    execute_extended_trade(signal, df['close'].iloc[-1])
                    trades_today += 1
                    print(f"✅ Tranzacție finalizată ({trades_today}/{DAILY_LIMIT}).")
            
            time.sleep(60)
        except Exception as e:
            print(f"⚠️ [LOOP ERROR]: {e}")
            time.sleep(30)

# Rute obligatorii pentru UptimeRobot (Evită 405/503)
@app.head("/")
@app.get("/")
def health_check():
    return {
        "status": "online",
        "bot": "HYPE-Grinder",
        "trades_completed": trades_today,
        "limit_remaining": DAILY_LIMIT - trades_today
    }

# Pornire procese
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
