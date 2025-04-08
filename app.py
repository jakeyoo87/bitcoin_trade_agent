# -*- coding: utf-8 -*-

import streamlit as st
import requests
import time

# FastAPI 서버 주소
API_URL = "http://localhost:8000"  # FastAPI 백엔드 주소

st.title("📈 Upbit Trade Bot")

# 초기 잔고 및 수익률
if "initial_balance" not in st.session_state:
    st.session_state.initial_balance = 0
if "profit_rate" not in st.session_state:
    st.session_state.profit_rate = 0


# 잔고 조회 및 수익률 계산 함수
def fetch_balance():
    try:
        response = requests.get(f"{API_URL}/balance", timeout=5)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        balances = response.json().get("balances", [])
        total_balance = sum(
            float(balance["balance"]) * float(balance.get("avg_buy_price", 1))
            for balance in balances
            if balance["currency"] != "KRW"
        )

        # 초기 잔고 설정 (최초 실행 시)
        if st.session_state.initial_balance == 0:
            st.session_state.initial_balance = total_balance

        # 수익률 계산
        if st.session_state.initial_balance > 0:
            st.session_state.profit_rate = (
                (total_balance - st.session_state.initial_balance)
                / st.session_state.initial_balance
            ) * 100

        return balances, total_balance
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ 백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 요청 중 오류 발생: {e}")

    return [], 0


# 잔고 및 수익률 표시
st.header("💰 잔고 & 수익률")
balances, total_balance = fetch_balance()
st.write(f"### 총 자산: {total_balance:,.2f} KRW")
st.write(f"### 수익률: {st.session_state.profit_rate:.2f}%")

if st.button("🔄 수익률 초기화"):
    st.session_state.initial_balance = total_balance
    st.session_state.profit_rate = 0
    st.success("✅ 수익률이 초기화되었습니다!")

# 잔고 상세 정보
if balances:
    for balance in balances:
        st.write(
            f"- {balance['currency']}: {balance['balance']} 개 (평균 매수가: {balance.get('avg_buy_price', 'N/A')} KRW)"
        )

# 매수 주문 (one-click 버튼)
st.header("📥 매수 주문 (XRP)")

xrp_options = [
    ("XRP-0", 0),
    ("XRP-0.5", 0.5),
    ("XRP-1.0", 1.0),
    ("XRP-2.0", 2.0),
    ("XRP-3.0", 3.0),
]
amount_to_buy = total_balance * 0.1  # 현재 총 자산의 10%를 매수 금액으로 설정

cols = st.columns(len(xrp_options))
for col, (label, discount) in zip(cols, xrp_options):
    with col:
        if st.button(label):
            data = {
                "coin": "XRP",
                "amount": amount_to_buy,
                "discount_percent": discount,
            }
            try:
                response = requests.post(f"{API_URL}/buy", json=data, timeout=5)
                response.raise_for_status()
                st.success(f"✅ {label} 매수 주문 성공!")
            except requests.exceptions.ConnectionError:
                st.warning(
                    "⚠️ 백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요."
                )
            except requests.exceptions.RequestException as e:
                st.error(f"❌ 매수 주문 실패! 오류: {e}")

# 자동 매매 ON/OFF 섹션
st.header("⚡ 자동 매매 설정")
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 자동 매매 시작"):
        try:
            response = requests.post(f"{API_URL}/start_auto_trading", timeout=5)
            response.raise_for_status()
            st.success("✅ 자동 매매 시작됨!")
        except requests.exceptions.ConnectionError:
            st.warning(
                "⚠️ 백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요."
            )
        except requests.exceptions.RequestException as e:
            st.error(f"❌ 자동 매매 시작 실패! 오류: {e}")

with col2:
    if st.button("🛑 자동 매매 중지"):
        try:
            response = requests.post(f"{API_URL}/stop_auto_trading", timeout=5)
            response.raise_for_status()
            st.success("✅ 자동 매매 중지됨!")
        except requests.exceptions.ConnectionError:
            st.warning(
                "⚠️ 백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요."
            )
        except requests.exceptions.RequestException as e:
            st.error(f"❌ 자동 매매 중지 실패! 오류: {e}")

# 10초마다 잔고 자동 업데이트
while True:
    time.sleep(5)
    fetch_balance()
    st.rerun()
