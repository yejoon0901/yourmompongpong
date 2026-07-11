import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import numpy as np
import time
import random

# -----------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------
st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터(또는 가상 데이터)에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

# -----------------------------------------------------------
# 2. 사이드바 UI 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")

if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지 설정")

z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값", 
    min_value=-5.0, 
    max_value=5.0, 
    value=-3.0, 
    step=0.1
)

# -----------------------------------------------------------
# -----------------------------------------------------------
# 3. 데이터 수집 (빠른 응답을 위해 대기 시간 최소화)
# -----------------------------------------------------------
@st.cache_data(ttl=30, show_spinner="위성 통신 중...")
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # 렉 방지 핵심: 최대 1번만 시도하고, 5초 안에 답이 없으면 바로 끊어버립니다.
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            states = data.get("states", [])
            if states:
                st.sidebar.success("🟢 실시간 API 연동 성공")
            return states
        elif response.status_code == 429:
            st.sidebar.error("⚠️ API 호출 한도 초과. 잠시 후 새로고침 하세요.")
            return []
            
    except requests.exceptions.Timeout:
        # 지연 시 기다리지 않고 즉각적으로 에러 처리
        st.sidebar.error("❌ 서버 응답 지연: 데이터를 빠르게 불러오지 못했습니다.")
        return []
    except Exception as e:
        st.sidebar.error(f"❌ 데이터 통신 오류 발생: {e}")
        return []
        
    return []
