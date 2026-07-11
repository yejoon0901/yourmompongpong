import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import numpy as np
import time

# 페이지 기본 설정
st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

# -----------------------------------------------------------
# 1. 사이드바 UI 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")

# 새로고침 버튼을 누르면 캐시를 비우고 API를 다시 호출하도록 설정
if st.sidebar.button("🔄 실시간 데이터 새로고침"):
    st.cache_data.clear()

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지(Anomaly Detection) 설정")

# Z-score 슬라이더
z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값", 
    min_value=-5.0, 
    max_value=5.0, 
    value=-3.0, 
    step=0.1,
    help="값이 낮을수록 더 극단적인 급강하만 위험으로 감지합니다."
)

# -----------------------------------------------------------
# 2. 데이터 수집 (재시도 로직 & 캐싱 적용)
# -----------------------------------------------------------
# API 호출 제한 방지를 위해 30초 동안 데이터를 캐싱(저장)합니다.
@st.cache_data(ttl=30, show_spinner="위성에서 실시간 비행 데이터를 수신 중입니다...")
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    # 한반도 좌표 범위
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    
    max_retries = 3  # 최대 3번까지 재시도
    
    for attempt in range(max_retries):
        try:
            # 타임아웃을 20초로 늘려 서버 지연에 대비
            response = requests.get(url, params=params, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("states", [])
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

# 데이터 불러오기 실행
raw_data = get_flight_data()

# -----------------------------------------------------------
# 3. 데이터 전처리 및 이상 탐지 (Pandas)
# -----------------------------------------------------------
if raw_data and len(raw_data) > 0:
    columns = [
        'icao24', 'callsign', 'origin_country', 'time_position', 'last_contact',
        'longitude', 'latitude', 'baro_altitude', 'on_ground', 'velocity',
        'true_track', 'vertical_rate', 'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    
    # 필요한 컬럼만 추출 및 결측치 제거
    df = df[['callsign', 'longitude', 'latitude', 'baro_altitude', 'velocity', 'vertical_rate']]
    df = df.dropna(subset=['longitude', 'latitude', 'vertical_rate'])
    df['callsign'] = df['callsign'].astype(str).str.strip().replace('', '알 수 없음')

    # 한반도 상공 전체 수직 속도의 평균과 표준편차 계산
    mean_vr = df['vertical_rate'].mean()
    std_vr = df['vertical_rate'].std()
    
    # Z-score 계산 (표준편차가 0일 경우 예외 처리)
    if std_vr > 0:
        df['z_score'] = (df['vertical_rate'] - mean_vr) / std_vr
    else:
        df['z_score'] = 0.0

    # [핵심] Z-score 기준을 충족하면서, 동시에 실제 하강 속도가 -10m/s 이하일 때만 '위험'으로 판정
    # (단순히 고도를 낮추는 정상 착륙 과정이 오탐지 되는 것을 방지)
    df['status'] = np.where(
        (df['z_score'] <= z_threshold) & (df['vertical_rate'] < -10.0), 
        '위험(급강하)', 
        '정상'
    )

    # 상태에 따른 색상 지정 (위험: 빨강, 정상: 노랑)
    def assign_color(status):
        return [255, 0, 0, 255] if status == '위험(급강하)' else [255, 200, 0, 180]
        
    df['color'] = df['status'].apply(assign_color)

    # -----------------------------------------------------------
    # 4. 현황판 및 3D 지도 시각화 (Pydeck)
    # -----------------------------------------------------------
    # 사이드바 현황 알림
    diving_count = len(df[df['status'] == '위험(급강하)'])
    st.sidebar.success(f"📡 현재 추적 중인 비행기: {len(df)}대")
    
    if diving_count > 0:
        st.sidebar.error(f"🚨 급강하 이상 징후 감지: {diving_count}대!!")
    else:
        st.sidebar.info("✅ 현재 급강하 이상 징후 없음")

    # 지도 설정
    view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)
    
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_radius=6000, # 점의 크기 (미터 단위)
        get_fill_color="color",
        pickable=True
    )

    # 지도 위 마우스 오버 툴팁
    tooltip = {
        "html": """
        <b>✈️ 콜사인:</b> {callsign} <br/>
        <b>🚨 상태:</b> <span style="color:{color}">{status}</span> <br/>
        <b>📉 수직 속도:</b> {vertical_rate} m/s <br/>
        <b>📊 Z-score:</b> {z_score} <br/>
        <b>🏔️ 현재 고도:</b> {baro_altitude} m
        """,
        "style": {"backgroundColor": "#222222", "color": "white", "borderRadius": "5px", "padding": "10px"}
    }

    # 지도 렌더링
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="dark"))
    
    # -----------------------------------------------------------
    # 5. 데이터 테이블 확인 (가독성 개선)
    # -----------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 실시간 항공 통계 및 데이터")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
    with col2:
        st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")
        
    # 데이터프레임 소수점 포맷팅
    formatted_df = df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']].copy()
    
    st.dataframe(
        formatted_df.style.format({
            'z_score': '{:.2f}', 
            'vertical_rate': '{:.2f}',
            'baro_altitude': '{:.0f}',
            'velocity': '{:.1f}'
        }).applymap(lambda x: "background-color: #ffcccc; color: red;" if x == "위험(급강하)" else "", subset=['status']),
        use_container_width=True
    )

else:
    # 데이터를 받아오지 못했을 때의 안내 화면
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없거나 서버 혼잡으로 데이터를 가져오지 못했습니다.")
    st.info("왼쪽 사이드바의 **[🔄 실시간 데이터 새로고침]** 버튼을 다시 눌러주세요.")
