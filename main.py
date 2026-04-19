import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from fastapi import FastAPI
import threading
from datetime import datetime

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
    """Obține datele de piață de la Extended/Hyperliquid."""
    # Înlocuiește cu URL-ul de API al platformei Extended
    url = f"https://api.extended.exchange/v1/candles?symbol={SYMBOL}&interval={TIMEFRAME}"
    try:
        r = requests.get(url)
        data = r.json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except:
        return pd.DataFrame()

def check_signals(df):
    """Sistemul Sniper: EMA 200 + ADX + BB Squeeze + Hull + Volume Spike."""
    if df.empty or len(df) < 200: return None

    # 1. EMA 200 (Zidul)
    df['ema200'] = ta.ema(df['close'], length=200)
    # 2. ADX (Puterea > 25)
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    df['adx'] = adx['ADX_14']
    # 3. Bollinger Bands (Squeeze)
    bb = ta.bbands(df['close'], length=20, std=2)
    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
    # 4. Hull Suite (Trigger)
    df['hull'] = ta.hma(df['close'], length=14)
    # 5. Volume Spike (1.5x)
    df['vol_sma'] = ta.sma(df['volume'], length=20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # LOGICA DE INTRARE (Target 1%)
    long_cond = (curr['close'] > curr['ema200'] and curr['adx'] > 25 and 
                 curr['hull'] > prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)
    
    short_cond = (curr['close'] < curr['ema200'] and curr['adx'] > 25 and 
                  curr['hull'] < prev['hull'] and curr['volume'] > curr['vol_sma'] * 1.5)

    if long_cond: return "LONG"
    if short_cond: return "SHORT"
    return None

def execute_extended_trade(side, price):
    """Execută ordinul pe platforma Extended folosind Stark Keys."""
    tp = price * 1.0105 if side == "LONG" else price * 0.9895
    sl = price * 0.9905 if side == "LONG" else price * 1.0095
    
    # Payload-ul specific pentru Extended (Starknet L2)
    order_data = {
        "api_key": API_KEY,
        "stark_key": STARK_PUBLIC,
        "vault_id": VAULT_NUMBER,
        "client_id": CLIENT_ID,
        "symbol": SYMBOL,
        "side": side,
        "amount": (RISK_USD * LEVERAGE) / price,
        "price": price,
        "type": "LIMIT", # Maker points
        "tp": tp,
        "sl": sl
    }
    
    # Trimite către endpoint-ul de execuție Extended sau UltimateRobot Bridge
    requests.post("https://api.extended.exchange/v1/order", json=order_data)
    print(f"[{datetime.now()}] Poziție {side} deschisă la {price}. TP: {tp}, SL: {sl}")

def bot_loop():
    global trades_today, last_trade_day
    while True:
        if datetime.now().day != last_trade_day:
            trades_today = 0
            last_trade_day = datetime.now().day

        if trades_today < DAILY_LIMIT:
            df = get_market_data()
            signal = check_signals(df)
            if signal:
                execute_extended_trade(signal, df['close'].iloc[-1])
                trades_today += 1
        
        time.sleep(60) # Verifică în fiecare minut

@app.get("/")
def status():
    return {"bot": "HYPE-Sniper", "platform": "Extended", "trades_today": trades_today}

threading.Thread(target=bot_loop, daemon=True).start()
