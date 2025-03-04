import os
import pyupbit
import time
import schedule
import logging
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


# 📌 자동 매도 로직 (수익률 -1% 이하 or 3% 이상)
def auto_sell():
    logger.debug("\n🔍 현재 보유한 코인들의 수익률 확인 중...")

    balances = upbit.get_balances()

    for balance in balances:
        time.sleep(1)
        coin = balance["currency"]
        if coin == "KRW":
            continue  # 원화 패스

        amount = float(balance["balance"])
        avg_buy_price = float(balance["avg_buy_price"])

        if amount <= 0:
            continue

        # 현재 시장 가격 가져오기
        market_code = f"KRW-{coin}"
        current_price = pyupbit.get_current_price(market_code)

        if not current_price:
            logger.warning(f"⚠️ {coin}의 현재 가격을 가져오지 못했습니다.")
            continue

        # 수익률 계산
        profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100

        # 수익률 로그 출력
        logger.debug(
            f"{coin} | 평균 매수가: {avg_buy_price:,.0f} KRW | 현재가: {current_price:,.0f} KRW | 수익률: {profit_percent:.2f}%"
        )

        # 매도 조건 (-1% 이하 or 3% 이상)
        if profit_percent <= -1:
            reason = f"❌ 손실 제한 (-1% 이하) 초과: {profit_percent:.2f}%"
        elif profit_percent >= 3:
            reason = f"✅ 목표 수익 (3% 이상) 달성: {profit_percent:.2f}%"
        else:
            continue  # 📌 매도 조건이 아니면 패스 (여기서 수익률만 출력하고 넘어감)

        # 매도 실행
        try:
            logger.info(f"📉 {coin} 매도 진행 중... 이유: {reason}")
            sell_order = upbit.sell_market_order(market_code, amount)
            if sell_order:
                logger.info(f"✅ {coin} 매도 성공: {sell_order}")
            else:
                logger.error(f"❌ {coin} 매도 실패")
        except Exception as e:
            logger.error(f"❌ {coin} 매도 중 오류 발생: {e}")


# 10초마다 자동 실행
schedule.every(5).seconds.do(auto_sell)

logger.info("🚀 자동 매도 시스템 시작...")
while True:
    schedule.run_pending()
    time.sleep(1)
