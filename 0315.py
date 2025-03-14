import streamlit as st
import random
import time


def main():
    st.markdown(
        "<h1 style='text-align: center; font-size: 50px;'>돌잔치 선물 추첨 🎉</h1>",
        unsafe_allow_html=True,
    )

    # 사용자가 최대 숫자를 설정할 수 있도록 UI 추가
    max_number = st.number_input(
        "최대 숫자 선택", min_value=10, max_value=100, value=30, step=1
    )

    if "selected_numbers" not in st.session_state:
        st.session_state.selected_numbers = []
    if "selected_gifts" not in st.session_state:
        st.session_state.selected_gifts = []
    if "attempt_count" not in st.session_state:
        st.session_state.attempt_count = 0

    available_gifts = ["와인", "텀블러", "버즈", "꽝"]

    st.markdown(
        f"<h2 style='text-align: center; font-size: 30px;'>현재 진행 횟수: {st.session_state.attempt_count} / 4</h2>",
        unsafe_allow_html=True,
    )

    # 이전 당첨 내역 표시
    if st.session_state.selected_numbers or st.session_state.selected_gifts:
        st.markdown(
            "<h2 style='font-size: 30px;'>🎯 당첨 내역</h2>", unsafe_allow_html=True
        )
        for i, (num, gift) in enumerate(
            zip(st.session_state.selected_numbers, st.session_state.selected_gifts), 1
        ):
            st.markdown(
                f"<p style='font-size: 25px;'>{i}번째 - 숫자: {num}, 선물: {gift}</p>",
                unsafe_allow_html=True,
            )

    if st.button("숫자 추첨 시작!"):
        if st.session_state.attempt_count < 4:
            placeholder = st.empty()

            # 중복되지 않는 숫자 목록 가져오기
            available_numbers = [
                num
                for num in range(1, max_number + 1)
                if num not in st.session_state.selected_numbers
            ]

            if available_numbers:
                # 최종 선택될 숫자 미리 정하기
                final_number = random.choice(available_numbers)

                # 숫자 애니메이션 효과 (2배로 증가)
                for _ in range(40):
                    temp_number = random.choice(
                        available_numbers
                    )  # 실제 가능한 숫자 중에서 애니메이션 출력
                    placeholder.markdown(
                        f"<p style='font-size: 40px; text-align: center;'>🎲 랜덤 숫자: {temp_number}</p>",
                        unsafe_allow_html=True,
                    )
                    time.sleep(0.1)

                # 최종 당첨 숫자 표시
                st.session_state.selected_numbers.append(final_number)
                placeholder.success(f"🎉 당첨 숫자: {final_number}")
            else:
                placeholder.error("⚠️ 모든 숫자가 이미 선택되었습니다!")

    if st.button("선물 추첨 시작!"):
        if len(st.session_state.selected_numbers) > len(
            st.session_state.selected_gifts
        ):
            gift_placeholder = st.empty()

            # 선물 애니메이션 효과 (2배로 증가)
            for _ in range(20):
                gift_placeholder.markdown(
                    f"<p style='font-size: 40px; text-align: center;'>🎁 선물: {random.choice(available_gifts)}</p>",
                    unsafe_allow_html=True,
                )
                time.sleep(0.2)

            # 중복되지 않는 선물 선택
            available_gifts = [
                gift
                for gift in ["와인", "텀블러", "버즈", "꽝"]
                if gift not in st.session_state.selected_gifts
            ]
            if available_gifts:
                final_gift = random.choice(available_gifts)
                st.session_state.selected_gifts.append(final_gift)
                gift_placeholder.success(f"🎁 당첨 선물: {final_gift}")
                st.session_state.attempt_count += 1
                st.rerun()
            else:
                gift_placeholder.error("⚠️ 모든 선물이 이미 선택되었습니다!")

    if st.button("🔄 리셋하기"):
        st.session_state.selected_numbers = []
        st.session_state.selected_gifts = []
        st.session_state.attempt_count = 0
        st.success("데이터가 초기화되었습니다!")
        st.rerun()


if __name__ == "__main__":
    main()
