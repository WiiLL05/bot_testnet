# === BOT CRYPTO TESTNET AUTOMATISÉ ===
import json
import time
import requests
import pandas as pd
from datetime import datetime
from binance.client import Client
from binance.enums import *
import math

# === CONFIGURATION ===
API_KEY = "TA_CLE_API"
API_SECRET = "TON_SECRET"
client = Client(API_KEY, API_SECRET, testnet=True)

TELEGRAM_TOKEN = "7614533197:AAHNhLPiAi7wajeu15LuOGnBseT31vr-so4"
CHAT_ID = "2105745536"
HISTORIQUE_CSV = "historique_test.csv"
PORTEFEUILLE_JSON = "portefeuille_test.json"

CRYPTOS = {
    "BTCUSDT": 10,
    "ETHUSDT": 10,
    "SOLUSDT": 10,
    "AVAXUSDT": 10,
    "LINKUSDT": 10
}

# === ENVOI MESSAGES TELEGRAM ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

def send_telegram_message_détail_achat(symbol, rsi, ma7, ma20, price, quantity):
    message = (
        f"\U0001F7E2 *Achat exécuté* — {symbol}\n"
        f"• Quantité : {quantity}\n"
        f"• Prix : {price} USD\n"
        f"• RSI = {round(rsi, 2)} (🔻 survendu)\n"
        f"• MA7 = {round(ma7, 2)} / MA20 = {round(ma20, 2)} (📉 tendance baissière)"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=data)

# === FICHIERS PORTFEUILLE ===
def load_portefeuille():
    try:
        with open(PORTEFEUILLE_JSON, "r") as f:
            data = json.load(f)
            for sym in CRYPTOS:
                if sym not in data:
                    data[sym] = {"investi": 0, "positions": [], "benefices": 0}
            return data
    except FileNotFoundError:
        return {sym: {"investi": 0, "positions": [], "benefices": 0} for sym in CRYPTOS}

def save_portefeuille(data):
    with open(PORTEFEUILLE_JSON, "w") as f:
        json.dump(data, f, indent=2)

# === GESTION DES ORDRES ===
def get_price(symbol):
    return float(client.get_symbol_ticker(symbol=symbol)["price"])

def get_lot_size(symbol):
    info = client.get_symbol_info(symbol)
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step_size = float(f['stepSize'])
            decimals = abs(int(round(-1 * math.log10(step_size))))
            return decimals
    return 6

def buy(symbol, amount_usdt, portefeuille, rsi, ma7, ma20):
    price = get_price(symbol)
    decimales = get_lot_size(symbol)
    quantity = amount_usdt / price
    quantity = f"{quantity:.{decimales}f}"
    try:
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        portefeuille[symbol]["positions"].append({"achat": price, "quantite": float(quantity)})
        portefeuille[symbol]["investi"] += amount_usdt
        send_telegram_message_détail_achat(symbol, rsi, ma7, ma20, price, quantity)
        return "✅ Achat effectué"
    except Exception as e:
        send_telegram_message(f"❌ Erreur achat {symbol} : {e}")
        return "❌ Erreur lors de l'achat"

def sell(symbol, position, portefeuille):
    price = get_price(symbol)
    achat = position["achat"]
    quantite = position["quantite"]
    gain = (price - achat) * quantite
    if gain > 0:
        try:
            client.order_market_sell(symbol=symbol, quantity=quantite)
            portefeuille[symbol]["benefices"] += gain
            portefeuille[symbol]["investi"] -= achat * quantite
            portefeuille[symbol]["positions"].remove(position)
            send_telegram_message(
                f"🔴 Vente {symbol} | {quantite} à {price} USD | Gain : {round(gain, 2)} USD")
        except Exception as e:
            send_telegram_message(f"❌ Erreur vente {symbol} : {e}")

# === STRATÉGIE DU BOT ===
def strategie(symbol, portefeuille):
    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=50)
    prices = [float(k[4]) for k in klines]
    df = pd.DataFrame(prices, columns=["close"])
    df["MA7"] = df["close"].rolling(window=7).mean()
    df["MA20"] = df["close"].rolling(window=20).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # Ajout MACD, Stoch RSI, BBands, Volume, EMA
    df["EMA12"] = df["close"].ewm(span=12).mean()
    df["EMA26"] = df["close"].ewm(span=26).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9).mean()
    df["UpperBB"] = df["close"].rolling(20).mean() + 2 * df["close"].rolling(20).std()
    df["LowerBB"] = df["close"].rolling(20).mean() - 2 * df["close"].rolling(20).std()
    df["%K"] = (df["close"] - df["close"].rolling(14).min()) / (df["close"].rolling(14).max() - df["close"].rolling(14).min()) * 100
    df["Volume"] = [float(k[5]) for k in klines]

    current = df.iloc[-1]
    rsi = current["RSI"]
    ma7 = current["MA7"]
    ma20 = current["MA20"]
    macd = current["MACD"]
    signal = current["Signal"]
    price = current["close"]
    upperbb = current["UpperBB"]
    lowerbb = current["LowerBB"]
    stochastic = current["%K"]
    volume = current["Volume"]

    decision = "❌ Pas d'achat"

    if rsi < 30 and ma7 < ma20 and macd < signal and price < ma20 and stochastic < 20:
        if portefeuille[symbol]["investi"] + 10 <= CRYPTOS[symbol]:
            decision = buy(symbol, 10, portefeuille, rsi, ma7, ma20)
        else:
            decision = "⛔️ A stoppé car tout le capital est déjà investi"
    elif rsi < 35:
        decision = "⏳ Conditions presque réunies pour un achat (RSI bas, tendance baissière proche)"

    for pos in portefeuille[symbol]["positions"][:]:
        if price > pos["achat"] * 1.02:
            sell(symbol, pos, portefeuille)

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "RSI": round(rsi, 2),
        "MA7": round(ma7, 2),
        "MA20": round(ma20, 2),
        "decision": decision
    }

# === BOUCLE PRINCIPALE ===
def main():
    portefeuille = load_portefeuille()
    resume = ["📊 Analyse & exécution du bot testnet"]
    for sym in CRYPTOS:
        result = strategie(sym, portefeuille)
        ligne = (
            f"{result['symbol']} | Prix: {result['price']} USD | RSI: {result['RSI']} | "
            f"MA7: {result['MA7']} | MA20: {result['MA20']}\n{result['decision']}"
        )
        resume.append(ligne)
        time.sleep(2)

    save_portefeuille(portefeuille)
    send_telegram_message("\n\n".join(resume))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORIQUE_CSV, "a") as f:
        for sym in CRYPTOS:
            p = get_price(sym)
            f.write(f"{now},{sym},{p}\n")

# === API FLASK POUR LANCER LE BOT À DISTANCE ===
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Crypto en ligne. Accède à /start-bot pour lancer l’analyse."

@app.route("/start-bot")
def start_bot():
    thread = threading.Thread(target=main)
    thread.start()
    return "🚀 Analyse lancée. Le bot s'exécute en arrière-plan."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)