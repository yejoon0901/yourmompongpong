import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import numpy as np
import time

# -----------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------
st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

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
# 3. 데이터 수집 (가상 데이터 제거, 실제 API 재시도 로직만 적용)
# -----------------------------------------------------------
@st.cache_data(ttl=30, show_spinner="데이터를 수신 중입니다...")
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    # 웹 브라우저로 위장하여 차단 확률 낮추기
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                states = data.get("states", [])
                if states:
                    st.sidebar.success("🟢 실시간 OpenSky API 연동 성공")
                return states
            elif response.status_code == 429:
                st.sidebar.error("⚠️ API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
                return []
                
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                st.sidebar.warning(f"서버 응답 지연 (시도 {attempt + 1}/{max_retries})... 2초 후 재연결합니다.")
                time.sleep(2)
            else:
                st.sidebar.error("❌ 연결 시간 초과: OpenSky 서버가 혼잡합니다. 잠시 후 새로고침을 눌러주세요.")
                return []
        except Exception as e:
            st.sidebar.error(f"❌ 데이터 통신 오류 발생: {e}")
            return []
            
    return []

raw_data = get_flight_data()

# -----------------------------------------------------------
# 4. 데이터 전처리 및 이상 탐지
# -----------------------------------------------------------
if raw_data and len(raw_data) > 0:
    columns = [
        'icao24', 'callsign', 'origin_country', 'time_position', 'last_contact',
        'longitude', 'latitude', 'baro_altitude', 'on_ground', 'velocity',
        'true_track', 'vertical_rate', 'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    
    df = df[['callsign', 'longitude', 'latitude', 'baro_altitude', 'velocity', 'vertical_rate']]
    df = df.dropna(subset=['longitude', 'latitude', 'vertical_rate'])
    df['callsign'] = df['callsign'].astype(str).str.strip().replace('', '알 수 없음')

    # Z-score 계산
    mean_vr = df['vertical_rate'].mean()
    std_vr = df['vertical_rate'].std()
    
    if std_vr > 0:
        df['z_score'] = (df['vertical_rate'] - mean_vr) / std_vr
    else:
        df['z_score'] = 0.0

    # 위험(급강하) 판정 로직
    df['status'] = np.where(
        (df['z_score'] <= z_threshold) & (df['vertical_rate'] < -10.0), 
        '위험(급강하)', 
        '정상'
    )

    def assign_color(status):
        return [255, 0, 0, 255] if status == '위험(급강하)' else [255, 200, 0, 180]
        
    df['color'] = df['status'].apply(assign_color)

    # -----------------------------------------------------------
    # 5. 현황판 및 3D 지도 시각화
    # -----------------------------------------------------------
    diving_count = len(df[df['status'] == '위험(급강하)'])
    
    if diving_count > 0:
        st.error(f"🚨 주의: 현재 한반도 상공에 급강하 중인 비행기가 {diving_count}대 감지되었습니다!")
    else:
        st.info("✅ 현재 급강하 이상 징후 없음")

    view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)
    
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_radius=8000, 
        get_fill_color="color",
        pickable=True
    )

    tooltip = {
        "html": """
        <b>✈️ 콜사인:</b> {callsign} <br/>
        <b>🚨 상태:</b> {status} <br/>
        <b>📉 수직 속도:</b> {vertical_rate} m/s <br/>
        <b>📊 Z-score:</b> {z_score} <br/>
        <b>🏔️ 현재 고도:</b> {baro_altitude} m
        """,
        "style": {"backgroundColor": "#222", "color": "white"}
    }

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="dark"))
    
    # -----------------------------------------------------------
    # 6. 데이터 테이블
    # -----------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 실시간 항공 통계 데이터")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
    with col2:
        st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")
        
    formatted_df = df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']].copy()
    
    st.dataframe(
        formatted_df.style.format({
            'z_score': '{:.2f}', 
            'vertical_rate': '{:.2f}',
            'baro_altitude': '{:.0f}',
            'velocity': '{:.1f}'
        }),
        use_container_width=True
    )

else:
    # 데이터 수신 실패 또는 빈 데이터일 경우 처리
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없거나 서버 혼잡으로 데이터를 가져오지 못했습니다.")
    st.info("왼쪽 사이드바의 **[🔄 데이터 새로고침]** 버튼을 다시 눌러주세요.")
