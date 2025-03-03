import os
from dotenv import load_dotenv
import pyupbit
import sqlite3
import time
import schedule
import logging
from datetime import datetime
import ta
from ta.utils import dropna

# .env 파일에서 API 키 로드
load_dotenv()
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
if not access or not secret:
    raise ValueError("Missing API keys. Please check your .env file.")
upbit = pyupbit.Upbit(access, secret)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect("bitcoin_trades.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  decision TEXT,
                  coin_balance REAL,
                  krw_balance REAL,
                  coin_avg_buy_price REAL,
                  coin_krw_price REAL,
                  reason TEXT)"""
    )
    conn.commit()
    return conn


# 매매 결정 함수
def decision_logic(current_coin_price, df, avg_buy_price):
    ema_5 = df["ema_5"].iloc[-1]
    ema_20 = df["ema_20"].iloc[-1]

    if avg_buy_price == 0:
        if current_coin_price > ema_5 and current_coin_price > ema_20:
            return (
                "buy",
                f"Coin_Price > EMA_20, EMA_5: {current_coin_price} > {ema_20}, {ema_5}",
            )
        else:
            return "hold", f"Holding position - Coin_Price < EMA_20"
    else:
        profit_loss_ratio = (
            (current_coin_price - avg_buy_price) / avg_buy_price * 100
            if avg_buy_price > 0
            else 0
        )

        if profit_loss_ratio <= -0.3 or profit_loss_ratio >= 0.3:
            return "sell", f"Profit/Loss Ratio Triggered: {profit_loss_ratio}%"
        else:
            return "hold", f"Holding position - Profit/Loss Ratio: {profit_loss_ratio}%"


# 트레이딩 실행 함수
def ai_trading(coin):
    current_price = pyupbit.get_current_price(coin)
    df_minute1 = pyupbit.get_ohlcv(coin, interval="minute1", count=60)
    df_minute1 = dropna(df_minute1)
    df_minute1["ema_5"] = ta.trend.EMAIndicator(
        close=df_minute1["close"], window=5
    ).ema_indicator()
    df_minute1["ema_20"] = ta.trend.EMAIndicator(
        close=df_minute1["close"], window=20
    ).ema_indicator()

    with sqlite3.connect("crypto_trades.db") as conn:
        coin_avg_buy_price = upbit.get_avg_buy_price(coin[4:])
        decision, reason = decision_logic(current_price, df_minute1, coin_avg_buy_price)
        order_executed = False

        if decision == "buy":
            my_krw = upbit.get_balance("KRW")
            if my_krw and my_krw > 5000:
                order = upbit.buy_market_order(coin, my_krw * 0.9995)
                order_executed = bool(order)
                logger.info(
                    f"BUY order executed: {my_krw * 0.9995} KRW worth of {coin} - Reason: {reason}"
                )

        elif decision == "sell":
            my_coin = upbit.get_balance(coin)
            if my_coin and my_coin * current_price > 5000:
                order = upbit.sell_market_order(coin, my_coin)
                order_executed = bool(order)
                logger.info(
                    f"SELL order executed: {my_coin} {coin} at {current_price} KRW - Reason: {reason}"
                )

        if order_executed:
            coin_balance = upbit.get_balance(coin[4:])
            krw_balance = upbit.get_balance("KRW")
            log_trade(
                conn,
                decision,
                coin_balance,
                krw_balance,
                coin_avg_buy_price,
                current_price,
                reason,
            )
        else:
            logger.info(
                f"HOLD position - Current price: {current_price} KRW - Reason: {reason}"
            )


# 거래 기록 저장 함수
def log_trade(
    conn,
    decision,
    coin_balance,
    krw_balance,
    coin_avg_buy_price,
    coin_krw_price,
    reason,
):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute(
        """INSERT INTO trades (timestamp, decision, coin_balance, krw_balance, coin_avg_buy_price, coin_krw_price, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp,
            decision,
            coin_balance,
            krw_balance,
            coin_avg_buy_price,
            coin_krw_price,
            reason,
        ),
    )
    conn.commit()
    logger.info(f"Trade recorded in database: {decision} at {coin_krw_price} KRW")


if __name__ == "__main__":
    coin = "KRW-XRP"
    init_db()

    def job():
        ai_trading(coin)

    schedule.every(10).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
