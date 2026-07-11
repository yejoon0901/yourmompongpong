import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import numpy as np

st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

# -----------------------------------------------------------
# 1. 사이드바 UI 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")
# 버튼 클릭 시 캐시를 지우고 새로고침 하도록 설정
if st.sidebar.button("🔄 실시간 데이터 새로고침"):
    st.cache_data.clear()

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지(Anomaly Detection) 설정")

z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값", min_value=-5.0, max_value=5.0, value=-3.0, step=0.1
)

# [개선] 캐싱 적용: 30초 동안은 동일한 데이터를 반환하여 API 차단 방지
@st.cache_data(ttl=30)
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("states", [])
        else:
            st.error(f"API 호출 실패 (상태 코드: {response.status_code}) - 잠시 후 다시 시도해주세요.")
            return []
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return []

raw_data = get_flight_data()

# -----------------------------------------------------------
# 2. 데이터 전처리 및 분류
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

    # [개선] Z-score뿐만 아니라 실제 하강 속도(예: -10m/s 이하) 조건 추가로 착륙 패턴 오탐지 방지
    df['status'] = np.where(
        (df['z_score'] <= z_threshold) & (df['vertical_rate'] < -10.0), 
        '위험(급강하)', 
        '정상'
    )

    def assign_color(status):
        return [255, 0, 0, 255] if status == '위험(급강하)' else [255, 200, 0, 180]
        
    df['color'] = df['status'].apply(assign_color)

    # -----------------------------------------------------------
    # 3. 사이드바 및 시각화
    # -----------------------------------------------------------
    diving_count = len(df[df['status'] == '위험(급강하)'])
    st.sidebar.success(f"현재 추적 비행기: {len(df)}대")
    if diving_count > 0:
        st.sidebar.error(f"⚠️ 급강하 감지: {diving_count}대!!")
    else:
        st.sidebar.info("✅ 현재 특이 이상 징후 없음")

    view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_radius=6000,
        get_fill_color="color",
        pickable=True
    )

    tooltip = {
        "html": """
        <b>콜사인:</b> {callsign} <br/>
        <b>상태:</b> {status} <br/>
        <b>수직 속도:</b> {vertical_rate} m/s <br/>
        <b>Z-score:</b> {z_score} <br/>
        <b>현재 고도:</b> {baro_altitude} m
        """,
        "style": {"backgroundColor": "black", "color": "white"}
    }

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="dark"))
    
    # -----------------------------------------------------------
    # 4. 데이터 테이블 (가독성 개선)
    # -----------------------------------------------------------
    st.subheader("📊 실시간 항공 통계 및 데이터")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
    with col2:
        st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")
        
    # [개선] 데이터프레임 소수점 포맷팅 적용
    formatted_df = df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']].copy()
    st.dataframe(formatted_df.style.format({
        'z_score': '{:.2f}', 
        'vertical_rate': '{:.2f}',
        'baro_altitude': '{:.0f}',
        'velocity': '{:.1f}'
    }))

else:
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없거나 API 호출 대기 중입니다. (잠시 후 새로고침 해보세요)")
