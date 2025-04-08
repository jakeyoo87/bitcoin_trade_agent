import os
import pyupbit
import time
import schedule
import logging
import math
from dotenv import load_dotenv

# .env 파일에서 API 키 로드
load_dotenv()
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")

# Upbit 객체 생성
upbit = pyupbit.Upbit(access, secret)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_tick_size_from_orderbook(bid_prices):
    """
    주문장의 bid_price 리스트를 기반으로 호가 단위를 계산
    """
    # 호가 단위는 인접한 가격 차이 중 가장 작은 값으로 결정
    tick_sizes = [
        abs(bid_prices[i] - bid_prices[i + 1]) for i in range(len(bid_prices) - 1)
    ]
    return min(tick_sizes) if tick_sizes else 1


def reformat_price_from_orderbook(market_code, target_price):
    """
    업비트 주문장에서 매수 가격을 확인하고,
    - 주문장의 bid_price가 정수이면 target_price를 해당 호가 단위로 변환
    - 주문장의 bid_price가 소수이면 해당 소수점 자릿수에 맞춤
    """
    try:
        orderbook = pyupbit.get_orderbook(market_code)
        if not orderbook:
            logger.warning(f"⚠️ {market_code}의 주문장 데이터를 가져오지 못했습니다.")
            return target_price  # 주문장 데이터가 없으면 원래 가격 사용

        bid_prices = [order["bid_price"] for order in orderbook["orderbook_units"]]
        if not bid_prices:
            return target_price

        # 가장 가까운 주문장 가격 찾기
        nearest_price = min(bid_prices, key=lambda x: abs(x - target_price))

        # 주문장 기반으로 호가 단위 계산
        tick_size = get_tick_size_from_orderbook(bid_prices)

        # 주문장의 가격 형태 확인 (정수인지 소수인지)
        if isinstance(nearest_price, int) or nearest_price.is_integer():
            return (
                math.floor(target_price / tick_size) * tick_size
            )  # 호가 단위에 맞춰 변환
        else:
            decimal_places = len(
                str(nearest_price).split(".")[1]
            )  # 소수점 자릿수 가져오기
            return round(target_price, decimal_places)  # 소수점 자릿수 맞춰 변환

    except Exception as e:
        logger.error(f"❌ 주문장 가격 조회 오류: {e}")
        return target_price  # 오류 발생 시 원래 가격 사용


# 📌 할인된 매수 가격 계산 함수
def calculate_buy_price(market_code, current_price, discount_percent):
    """
    - 현재 가격(current_price)에 대해 discount_percent만큼 할인된 가격을 계산.
    - 현재 가격의 소수점 자릿수를 유지함.
    - 주문장에서 적절한 매수 가격을 찾아 최종 결정.
    """
    discounted_price = current_price * (1 - discount_percent / 100)

    # 주문장에서 적절한 가격 찾기
    return reformat_price_from_orderbook(market_code, discounted_price)


# 📌 지정 매수 주문 함수 (매도 후 특정 가격에 매수 주문)
def place_buy_order(coin, current_price, amount, discount_percent):
    try:
        market_code = f"KRW-{coin}"
        buy_price = calculate_buy_price(
            market_code, current_price, discount_percent
        )  # 할인된 가격 계산 후 주문장 반영
        logger.info(f"📥 {coin} 지정 매수 주문 시도: {buy_price} KRW, 수량: {amount}")

        buy_order = upbit.buy_limit_order(market_code, buy_price, amount)
        if buy_order:
            logger.info(f"✅ {coin} 지정 매수 주문 성공: {buy_order}")
        else:
            logger.error(f"❌ {coin} 지정 매수 주문 실패")

    except Exception as e:
        logger.error(f"❌ {coin} 지정 매수 주문 중 오류 발생: {e}")


# 📌 자동 매도 로직
def auto_sell():
    logger.debug("\n🔍 현재 보유한 코인들의 수익률 확인 중...")

    balances = upbit.get_balances()

    for balance in balances:
        time.sleep(1)
        sell_coin = None
        coin = balance["currency"]
        if coin == "KRW":
            continue  # 원화 패스

        amount = float(balance["balance"])
        avg_buy_price = float(balance["avg_buy_price"])

        if amount * avg_buy_price <= 5000:
            continue

        # 현재 시장 가격 가져오기
        market_code = f"KRW-{coin}"
        current_price = pyupbit.get_current_price(market_code)

        if not current_price:
            logger.info(f"⚠️ {coin}의 현재 가격을 가져오지 못했습니다.")
            continue

        # 수익률 계산
        profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100

        # 수익률 로그 출력
        logger.info(
            f"{coin} | 평균 매수가: {avg_buy_price} KRW | 현재가: {current_price} KRW | 수익률: {profit_percent:.2f}%"
        )

        if market_code == "KRW-BTC":
            if profit_percent <= -2.5:
                sell_coin = True
        else:
            if profit_percent <= -0.5 or profit_percent >= 1.0:
                sell_coin = True

        # 매도 실행
        if sell_coin == True:
            try:
                sell_order = upbit.sell_market_order(market_code, amount)
                if sell_order:
                    logger.info(f"✅ {coin} 매도 성공: {sell_order}")
                else:
                    logger.info(f"❌ {coin} 매도 실패")
            except Exception as e:
                logger.info(f"❌ {coin} 매도 중 오류 발생: {e}")


# 10초마다 자동 실행
schedule.every(5).seconds.do(auto_sell)

logger.info("🚀 자동 매도 시스템 시작...")
while True:
    schedule.run_pending()
    time.sleep(1)
