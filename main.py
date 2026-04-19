import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from fastapi import FastAPI
import threading
import uvicorn
from datetime import datetime

# 1. Definirea aplicației FastAPI (Trebuie să fie la început)
app = FastAPI()

# --- CONFIGURARE API EXTENDED (DIN RENDER ENV) ---
API_KEY = os.getenv("EXTENDED_API_KEY")
STARK_PUBLIC = os.getenv("STARK_KEY_PUBLIC")
STARK_PRIVATE = os.getenv("STARK_KEY_PRIVATE")
VAULT_NUMBER = os.getenv("VAULT_NUMBER")
CLIENT_ID = os.getenv("CLIENT_ID")

SYMBOL = "HYPE-USDC"
TIMEFRAME = "15m"
LEVERAGE = 10
RISK_USD = 100.0
DAILY_LIMIT = 2

# Starea botului
trades_today = 0
last_trade_day = datetime.now().day

def get_market_data():
    """Obține datele de piață de la Extended."""
    url = f"https://api.extended.exchange/v1/candles?symbol={SYMBOL}&interval={TIMEFRAME}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception as e:
        print(f"Eroare la preluarea datelor: {e}")
        return pd.DataFrame()

def check_signals(df):
    """Sistemul Sniper: EMA 200 + ADX + BB Squeeze + Hull + Volume Spike."""
    if df.empty or len(df) < 200: return None

    df['ema200'] = ta.ema(df['close'], length=200)
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx'] = adx['ADX_14']
    bb = ta.bbands(df['close'], length=20, std=2)
    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
    df['hull'] = ta.hma(df['close'], length=14)
    df['vol_sma'] = ta.sma(df['volume'], length=20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    long_cond = (curr['close'] > curr['ema200'] and curr['adx'] > 25 and 
                 curr['hull'] > prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)
    
    short_cond = (curr['close'] < curr['ema200'] and curr['adx'] > 25 and 
                  curr['hull'] < prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)

    if long_cond: return "LONG"
    if short_cond: return "SHORT"
    return None

def execute_extended_trade(side, price):
    """Execută ordinul pe platforma Extended."""
    tp = price * 1.0105 if side == "LONG" else price * 0.9895
    sl = price * 0.9905 if side == "LONG" else price * 1.0095
    
    order_data = {
        "api_key": API_KEY,
        "stark_key": STARK_PUBLIC,
        "vault_id": VAULT_NUMBER,
        "client_id": CLIENT_ID,
        "symbol": SYMBOL,
        "side": side,
        "amount": (RISK_USD * LEVERAGE) / price,
        "price": price,
        "type": "LIMIT",
        "tp": tp,
        "sl": sl
    }
    
    try:
        requests.post("https://api.extended.exchange/v1/order", json=order_data, timeout=10)
        print(f"[{datetime.now()}] Poziție {side} deschisă la {price}. TP: {tp}, SL: {sl}")
    except Exception as e:
        print(f"Eroare la execuție: {e}")

def bot_loop():
    global trades_today, last_trade_day
    print("Loop-ul de trading a pornit...")
    while True:
        try:
            if datetime.now().day != last_trade_day:
                trades_today = 0
                last_trade_day = datetime.now().day

            if trades_today < DAILY_LIMIT:
                df = get_market_data()
                signal = check_signals(df)
                if signal:
                    execute_extended_trade(signal, df['close'].iloc[-1])
                    trades_today += 1
            
            time.sleep(60)
        except Exception as e:
            print(f"Eroare în loop: {e}")
            time.sleep(30)

@app.get("/")
def status():
    return {"bot": "HYPE-Sniper", "platform": "Extended", "trades_today": trades_today, "status": "online"}

# 2. Pornirea thread-ului de trading
threading.Thread(target=bot_loop, daemon=True).start()

# 3. Pornirea serverului (Singurul bloc de execuție final)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
