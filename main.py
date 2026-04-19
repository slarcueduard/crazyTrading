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

SYMBOL = "HYPE" # Folosit pentru Hyperliquid API
TIMEFRAME = "15m"
LEVERAGE = 10
RISK_USD = 100.0
DAILY_LIMIT = 2

# Starea botului
trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    """Obține datele de piață direct de la Hyperliquid (Sursa Extended)."""
    url = "https://api.hyperliquid.xyz/info"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": SYMBOL,
            "interval": TIMEFRAME,
            "startTime": int((time.time() - 86400 * 2) * 1000)
        }
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()
            
        data = r.json()
        df = pd.DataFrame(data)
        # Mapare coloane: t=timestamp, o=open, h=high, l=low, c=close, v=volume
        df.rename(columns={'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
        
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        return df
    except Exception as e:
        print(f"Eroare la preluarea datelor: {e}")
        return pd.DataFrame()

def check_signals(df):
    """Sistemul Sniper: EMA 200 + ADX + BB Squeeze + Hull + Volume Spike."""
    if df.empty or len(df) < 200:
        return None

    # Calcule tehnice
    df['ema200'] = ta.ema(df['close'], length=200)
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx'] = adx_df['ADX_14']
    bb = ta.bbands(df['close'], length=20, std=2)
    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
    df['hull'] = ta.hma(df['close'], length=14)
    df['vol_sma'] = ta.sma(df['volume'], length=20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # Logica de intrare
    long_cond = (curr['close'] > curr['ema200'] and curr['adx'] > 25 and 
                 curr['hull'] > prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)
    
    short_cond = (curr['close'] < curr['ema200'] and curr['adx'] > 25 and 
                  curr['hull'] < prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)

    if long_cond: return "LONG"
    if short_cond: return "SHORT"
    return None

def execute_extended_trade(side, price):
    """Trimite comanda de execuție către API-ul Extended."""
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
        print(f"[{datetime.now()}] Poziție {side} trimisă. Status: {r.status_code}")
    except Exception as e:
        print(f"Eroare la execuție: {e}")

def bot_loop():
    """Bucla principală care rulează în fundal."""
    global trades_today, last_trade_day
    print("Loop-ul de trading a pornit...")
    
    while True:
        try:
            # Resetare contor zilnic la miezul nopții
            if datetime.now().day != last_trade_day:
                trades_today = 0
                last_trade_day = datetime.now().day

            if trades_today < DAILY_LIMIT:
                df = get_market_data()
                signal = check_signals(df)
                
                if signal:
                    execute_extended_trade(signal, df['close'].iloc[-1])
                    trades_today += 1
                    print(f"Tranzacția {trades_today}/{DAILY_LIMIT} efectuată.")
            
            time.sleep(60) # Verifică în fiecare minut
        except Exception as e:
            print(f"Eroare în loop: {e}")
            time.sleep(30)

# Rute pentru monitorizare (UptimeRobot / Cron-job)
@app.head("/")
@app.get("/")
def status():
    return {
        "bot": "HYPE-Sniper",
        "status": "online",
        "trades_today": trades_today,
        "last_check": datetime.now().isoformat()
    }

# Pornirea thread-ului de trading
threading.Thread(target=bot_loop, daemon=True).start()

# Pornirea serverului web pe portul Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
