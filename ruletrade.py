import os
from dotenv import load_dotenv
import pyupbit
import pandas as pd
import json
from openai import OpenAI
import ta
from ta.utils import dropna
import time
import requests
import logging
import sqlite3
from datetime import datetime, timedelta
import re
import schedule
import numpy as np

# .env 파일에 저장된 환경 변수를 불러오기 (API 키 등)
load_dotenv()

# 로깅 설정 - 로그 레벨을 INFO로 설정하여 중요 정보 출력
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Upbit 객체 생성
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
if not access or not secret:
    logger.error("API keys not found. Please check your .env file.")
    raise ValueError("Missing API keys. Please check your .env file.")
upbit = pyupbit.Upbit(access, secret)


# SQLite 데이터베이스 초기화 함수 - 거래 내역을 저장할 테이블을 생성
def init_db():
    conn = sqlite3.connect("bitcoin_trades.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  decision TEXT,
                  percentage INTEGER,
                  btc_balance REAL,
                  krw_balance REAL,
                  btc_avg_buy_price REAL,
                  btc_krw_price REAL,
                  reason TEXT)"""
    )
    conn.commit()
    return conn


# 거래 기록을 DB에 저장하는 함수
def log_trade(
    conn,
    decision,
    percentage,
    btc_balance,
    krw_balance,
    btc_avg_buy_price,
    btc_krw_price,
    reason,
):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute(
        """INSERT INTO trades 
                 (timestamp, decision, percentage, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reason) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp,
            decision,
            percentage,
            btc_balance,
            krw_balance,
            btc_avg_buy_price,
            btc_krw_price,
            reason,
        ),
    )
    conn.commit()


# 최근 투자 기록 조회
def get_recent_trades(conn, days=7):
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
    c.execute(
        "SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC",
        (seven_days_ago,),
    )
    columns = [column[0] for column in c.description]
    return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)


# 최근 투자 기록을 기반으로 퍼포먼스 계산 (초기 잔고 대비 최종 잔고)
def calculate_performance(trades_df):
    if trades_df.empty:
        return 0  # 기록이 없을 경우 0%로 설정
    # 초기 잔고 계산 (KRW + BTC * 현재 가격)
    initial_balance = (
        trades_df.iloc[-1]["krw_balance"]
        + trades_df.iloc[-1]["btc_balance"] * trades_df.iloc[-1]["btc_krw_price"]
    )
    # 최종 잔고 계산
    final_balance = (
        trades_df.iloc[0]["krw_balance"]
        + trades_df.iloc[0]["btc_balance"] * trades_df.iloc[0]["btc_krw_price"]
    )
    return (final_balance - initial_balance) / initial_balance * 100


# 데이터프레임에 보조 지표를 추가하는 함수
def add_indicators(df):
    # 이동평균선 (단기, 장기)
    df["sma_10"] = ta.trend.SMAIndicator(close=df["close"], window=10).sma_indicator()
    df["sma_30"] = ta.trend.SMAIndicator(close=df["close"], window=30).sma_indicator()
    df["sma_60"] = ta.trend.SMAIndicator(close=df["close"], window=60).sma_indicator()
    df["sma_120"] = ta.trend.SMAIndicator(close=df["close"], window=120).sma_indicator()
    df["sma_180"] = ta.trend.SMAIndicator(close=df["close"], window=180).sma_indicator()

    df["ema_10"] = ta.trend.EMAIndicator(close=df["close"], window=10).ema_indicator()
    df["ema_30"] = ta.trend.EMAIndicator(close=df["close"], window=30).ema_indicator()
    df["ema_60"] = ta.trend.EMAIndicator(close=df["close"], window=60).ema_indicator()
    df["ema_120"] = ta.trend.EMAIndicator(close=df["close"], window=120).ema_indicator()
    df["ema_180"] = ta.trend.EMAIndicator(close=df["close"], window=180).ema_indicator()

    return df


def decision_logic(current_btc_price, df, ma="ema_30"):
    """
    결정 로직 함수: BTC를 매수할지 매도할지와 퍼센트를 결정합니다.

    Parameters:
    - current_btc_price (float): 현재 BTC 가격
    - df (pd.DataFrame): EMA 데이터를 포함한 데이터프레임

    Returns:
    - decision (str): "buy" 또는 "sell"
    - percentage (float): 매수/매도 퍼센트 (0~100)
    """
    # EMA 값을 가져오기
    ema = df[ma].iloc[-1]  # 데이터프레임에서 가장 최근 값 사용

    # 결정 로직
    ema_buy = ema * 1.005
    ema_sell = ema * 0.99
    if current_btc_price >= ema_buy:
        decision = "buy"
        percentage = 25.0
        reason = f"BTC_Price >= {ma}: {current_btc_price} >= {ema_buy}"
        logger.info(reason)
    elif current_btc_price < ema_sell:
        decision = "sell"
        percentage = 50.0
        reason = f"BTC_Price < {ma}*0.99: {current_btc_price} < {ema_sell}"
        logger.info(reason)
    else:
        decision = "hold"
        percentage = 0
        reason = f"BTC_Price is on hold: {current_btc_price} vs {ema}"
        logger.info(reason)

    logger.info(f"Decision: {decision.upper()}")
    logger.info(f"Percentage: {percentage}")
    logger.info(f"Reason: {reason}")

    return decision, percentage, reason


### 메인 AI 트레이딩 로직
def ai_trading(coin):
    global upbit
    ### 데이터 가져오기
    # 1. 현재 투자 상태 조회
    # all_balances = upbit.get_balances()
    # filtered_balances = [
    #     balance for balance in all_balances if balance["currency"] in ["BTC", "KRW"]
    # ]

    # 2. 오더북(호가 데이터) 조회
    current_price = pyupbit.get_current_price(coin)

    # 3. 차트 데이터 조회 및 보조지표 추가
    df_minute10 = pyupbit.get_ohlcv(
        coin, interval="minute10", count=180
    )  # 7 days of hourly data
    df_minute10 = dropna(df_minute10)
    df_minute10 = add_indicators(df_minute10)

    try:
        # 데이터베이스 연결
        with sqlite3.connect("bitcoin_trades.db") as conn:
            # 최근 거래 내역 가져오기
            # recent_trades = get_recent_trades(conn)

            # 알고리즘
            decision, percentage, reason = decision_logic(current_price, df_minute10)
            order_executed = False

            if decision == "buy":
                my_krw = upbit.get_balance("KRW")
                if my_krw is None:
                    logger.error("Failed to retrieve KRW balance.")
                    return
                buy_amount = my_krw * (percentage / 100) * 0.9995  # 수수료 고려
                if buy_amount > 5000:
                    logger.info(f"Buy Order Executed: {percentage}% of available KRW")
                    try:
                        order = upbit.buy_market_order(coin, buy_amount)
                        if order:
                            logger.info(f"Buy order executed successfully: {order}")
                            order_executed = True
                        else:
                            logger.error("Buy order failed.")
                    except Exception as e:
                        logger.error(f"Error executing buy order: {e}")
                else:
                    logger.warning(
                        "Buy Order Failed: Insufficient KRW (less than 5000 KRW)"
                    )
            elif decision == "sell":
                my_coin = upbit.get_balance(coin)
                if my_coin is None:
                    logger.error("Failed to retrieve BTC balance.")
                    return
                sell_amount = my_coin * (percentage / 100)
                current_price = pyupbit.get_current_price(coin)
                if sell_amount * current_price > 5000:
                    logger.info(f"Sell Order Executed: {percentage}% of held {coin}")
                    try:
                        order = upbit.sell_market_order(coin, sell_amount)
                        if order:
                            order_executed = True
                        else:
                            logger.error("Sell order failed.")
                    except Exception as e:
                        logger.error(f"Error executing sell order: {e}")
                else:
                    logger.warning(
                        "Sell Order Failed: Insufficient COIN (less than 5000 KRW worth)"
                    )
            else:
                logger.info("Decision is to hold. No action taken.")

            # 거래 실행 여부와 관계없이 현재 잔고 조회
            time.sleep(2)  # API 호출 제한을 고려하여 잠시 대기
            balances = upbit.get_balances()
            btc_balance = next(
                (
                    float(balance["balance"])
                    for balance in balances
                    if balance["currency"] == coin[4:]
                ),
                0,
            )
            krw_balance = next(
                (
                    float(balance["balance"])
                    for balance in balances
                    if balance["currency"] == "KRW"
                ),
                0,
            )
            btc_avg_buy_price = next(
                (
                    float(balance["avg_buy_price"])
                    for balance in balances
                    if balance["currency"] == coin[4:]
                ),
                0,
            )
            current_price = pyupbit.get_current_price(coin)

            # 거래 기록을 DB에 저장하기
            log_trade(
                conn,
                decision,
                percentage if order_executed else 0,
                btc_balance,
                krw_balance,
                btc_avg_buy_price,
                current_price,
                reason,
            )
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return


if __name__ == "__main__":

    # 코인
    coin = "KRW-XRP"

    # 데이터베이스 초기화
    init_db()

    # 중복 실행 방지를 위한 변수
    trading_in_progress = False

    # 트레이딩 작업을 수행하는 함수
    def job():
        global trading_in_progress
        if trading_in_progress:
            logger.warning("Trading job is already in progress, skipping this run.")
            return
        try:
            trading_in_progress = True
            ai_trading(coin)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        finally:
            trading_in_progress = False

    # 테스트
    job()
    schedule.every(10).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)
