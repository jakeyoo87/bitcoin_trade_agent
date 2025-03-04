import os
from dotenv import load_dotenv
import pyupbit
import sqlite3
import time
import schedule
import logging
from datetime import datetime
import ta
from collections import deque
import numpy as np
import pandas as pd  # EMA 계산을 위한 pandas 추가

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

# 가격 저장을 위한 deque (최대 100개 유지)
price_queue = deque(maxlen=100)


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


# 이동 평균 계산 함수
def calculate_moving_averages(min_n):
    if len(price_queue) < min_n + 1:
        logger.info("Waiting for enough data to calculate EMA and EMA Diff...")
        return None, None, None  # 데이터가 부족하면 None 반환

    prices = np.array(price_queue)

    # prices에서 차이 벡터 계산
    price_diff_series = pd.Series(prices).diff().dropna()

    # EMA를 벡터 형태로 계산
    ema_buy_series = ta.trend.EMAIndicator(
        close=pd.Series(prices), window=int(min_n / 2)
    ).ema_indicator()

    # EMA를 벡터 형태로 계산
    ema_sell_series = ta.trend.EMAIndicator(
        close=pd.Series(prices), window=min_n
    ).ema_indicator()

    # EMA 차이를 벡터로 계산
    ema_buy_series_diff = (
        ema_buy_series.diff().dropna()
    )  # 현재 EMA와 이전 EMA 값의 차이 (벡터)
    ema_sell_series_diff = (
        ema_sell_series.diff().dropna()
    )  # 현재 EMA와 이전 EMA 값의 차이 (벡터)

    return (
        price_diff_series.iloc[-1],
        ema_buy_series_diff.iloc[-1],
        ema_sell_series_diff.iloc[-1],
    )


# 매매 결정 함수
def decision_logic(
    current_coin_price, price_diff, ema_buy_diff, ema_sell_diff, avg_buy_price
):
    if price_diff is None:
        return "hold", "Not enough data to make a decision."

    if avg_buy_price == 0:
        if price_diff >= 8.0 and ema_buy_diff >= 4.0:
            return (
                "buy",
                f"Price: {current_coin_price}, Price Diff: {price_diff}, EMA Buy Diff: {ema_buy_diff}",
            )
        else:
            return (
                "hold",
                f"Buy Holding - Price Diff: {price_diff}, EMA Buy Diff: {ema_buy_diff}",
            )
    else:
        profit_loss_ratio = (
            ((current_coin_price - avg_buy_price) / avg_buy_price) * 100
            if avg_buy_price > 0
            else 0
        )

        if profit_loss_ratio <= -1.0:
            return "sell", f"Loss Ratio Triggered: {profit_loss_ratio}%"
        elif ema_sell_diff <= -0.0:
            return (
                "sell",
                f"Loss: {profit_loss_ratio}% - Price Diff: {price_diff}, EMA Sell Diff: {ema_sell_diff}",
            )
        else:
            return (
                "hold",
                f"Profit/Loss: {profit_loss_ratio}%, Price Diff: {price_diff}, EMA Sell Diff: {ema_sell_diff}",
            )


# 트레이딩 실행 함수
def ai_trading(coin):
    global price_queue

    current_price = pyupbit.get_current_price(coin)
    if current_price is None:
        logger.warning("Failed to fetch current price.")
        return

    price_queue.append(current_price)  # 가격 리스트에 추가
    price_diff, ema_buy_diff, ema_sell_diff = calculate_moving_averages(
        min_n=6
    )  # 이동 평균 계산

    if price_diff is None:
        return  # 데이터 부족으로 매매 중단

    with sqlite3.connect("bitcoin_trades.db") as conn:
        coin_avg_buy_price = upbit.get_avg_buy_price(coin[4:])
        decision, reason = decision_logic(
            current_price, price_diff, ema_buy_diff, ema_sell_diff, coin_avg_buy_price
        )
        order_executed = False

        if decision == "buy":
            my_krw = upbit.get_balance("KRW")
            if my_krw and my_krw > 5000:
                order = upbit.buy_market_order(coin, my_krw * 0.9995)
                order_executed = bool(order)
                logger.info(
                    f"BUY executed: {my_krw * 0.9995} KRW worth of {coin} - Reason: {reason}"
                )

        elif decision == "sell":
            my_coin = upbit.get_balance(coin)
            if my_coin and my_coin * current_price > 5000:
                order = upbit.sell_market_order(coin, my_coin)
                order_executed = bool(order)
                logger.info(
                    f"SELL executed: {my_coin} {coin} at {current_price} KRW - Reason: {reason}"
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
            logger.info(f"HOLD - Current Price: {current_price} KRW - Reason: {reason}")


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


if __name__ == "__main__":
    coin = "KRW-XRP"
    init_db()

    def job():
        ai_trading(coin)

    schedule.every(3).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
