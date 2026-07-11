# 기존 get_flight_data 함수를 이 코드로 덮어쓰기 하세요.

@st.cache_data(ttl=30, show_spinner="위성에서 실시간 비행 데이터를 수신 중입니다...")
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    
    # [우회 핵심 1] 크롬 브라우저인 것처럼 위장하는 User-Agent 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # [우회 핵심 2] OpenSky 무료 계정 정보 입력
    # 주의: https://opensky-network.org/ 에서 1분 만에 가입 가능합니다.
    # 가입 후 아래에 본인의 아이디와 비밀번호를 넣어주세요.
    opensky_auth = ('본인의_아이디를_여기에_입력', '본인의_비밀번호를_여기에_입력')
    
    max_retries = 3 
    
    for attempt in range(max_retries):
        try:
            # headers와 auth 파라미터를 추가하여 API 요청
            response = requests.get(url, params=params, headers=headers, auth=opensky_auth, timeout=20)
            
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
