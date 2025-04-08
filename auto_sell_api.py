import os
import pyupbit
import logging
import math
import time
import threading
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

# .env 파일에서 API 키 로드
load_dotenv()
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")

# Upbit 객체 생성
upbit = pyupbit.Upbit(access, secret)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("trading.log"),  # 로그를 파일로 저장
        logging.StreamHandler(),  # 콘솔에도 출력
    ],
)
logger = logging.getLogger(__name__)

# FastAPI 인스턴스 생성
app = FastAPI()

# 자동 매매 활성화 플래그
auto_trading = True


def get_tick_size_from_orderbook(bid_prices):
    """주문장의 bid_price 리스트를 기반으로 호가 단위 계산"""
    tick_sizes = [
        abs(bid_prices[i] - bid_prices[i + 1]) for i in range(len(bid_prices) - 1)
    ]
    return min(tick_sizes) if tick_sizes else 1


def reformat_price_from_orderbook(market_code, target_price):
    """주문장을 기반으로 최적의 매수가 조정"""
    try:
        orderbook = pyupbit.get_orderbook(market_code)
        if not orderbook:
            return target_price

        bid_prices = [order["bid_price"] for order in orderbook["orderbook_units"]]
        if not bid_prices:
            return target_price

        nearest_price = min(bid_prices, key=lambda x: abs(x - target_price))
        tick_size = get_tick_size_from_orderbook(bid_prices)

        if isinstance(nearest_price, int) or nearest_price.is_integer():
            return math.floor(target_price / tick_size) * tick_size
        else:
            decimal_places = len(str(nearest_price).split(".")[1])
            return round(target_price, decimal_places)
    except Exception as e:
        logger.error(f"Error fetching orderbook: {e}")
        return target_price


def calculate_buy_price(market_code, current_price, discount_percent):
    """할인된 매수가 계산 후 주문장 반영"""
    discounted_price = current_price * (1 - discount_percent / 100)
    return reformat_price_from_orderbook(market_code, discounted_price)


def auto_sell():
    global auto_trading
    while auto_trading:
        logger.debug("🔍 자동 매도 시스템 실행 중...")
        balances = upbit.get_balances()
        for balance in balances:
            time.sleep(1)
            coin = balance["currency"]
            if coin == "KRW":
                continue
            amount = float(balance["balance"])
            avg_buy_price = float(balance["avg_buy_price"])
            if amount <= 0:
                continue
            market_code = f"KRW-{coin}"
            current_price = pyupbit.get_current_price(market_code)
            if not current_price:
                continue
            profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100
            if profit_percent <= -1 or profit_percent >= 3:
                logger.info(f"📉 {coin} 매도 진행 중... 수익률: {profit_percent:.2f}%")
                upbit.sell_market_order(market_code, amount)
        time.sleep(5)


@app.post("/buy")
def place_buy_order(coin: str, amount: float, discount_percent: float):
    """매수 주문 API"""
    market_code = f"KRW-{coin}"
    current_price = pyupbit.get_current_price(market_code)
    if not current_price:
        raise HTTPException(status_code=400, detail="Failed to get current price")
    buy_price = calculate_buy_price(market_code, current_price, discount_percent)
    buy_order = upbit.buy_limit_order(market_code, buy_price, amount)
    if buy_order:
        return {"status": "success", "message": "Buy order placed", "order": buy_order}
    else:
        raise HTTPException(status_code=500, detail="Failed to place buy order")


@app.post("/sell")
def place_sell_order(coin: str):
    """매도 주문 API"""
    market_code = f"KRW-{coin}"
    balances = upbit.get_balances()
    balance_info = next((b for b in balances if b["currency"] == coin), None)
    if not balance_info or float(balance_info["balance"]) <= 0:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    amount = float(balance_info["balance"])
    sell_order = upbit.sell_market_order(market_code, amount)
    if sell_order:
        return {
            "status": "success",
            "message": "Sell order placed",
            "order": sell_order,
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to place sell order")


@app.get("/balance")
def get_balance():
    """잔고 조회 API"""
    balances = upbit.get_balances()
    return {"balances": balances}


@app.post("/start_auto_trading")
def start_auto_trading():
    """자동 매매 시작 API"""
    global auto_trading
    if not auto_trading:
        auto_trading = True
        threading.Thread(target=auto_sell, daemon=True).start()
    return {"status": "success", "message": "Auto trading started"}


@app.post("/stop_auto_trading")
def stop_auto_trading():
    """자동 매매 중지 API"""
    global auto_trading
    auto_trading = False
    return {"status": "success", "message": "Auto trading stopped"}


# 자동 매매 스레드 시작
threading.Thread(target=auto_sell, daemon=True).start()
