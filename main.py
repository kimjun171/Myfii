from datetime import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import pytz

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide"
)


# KOBIS API에서 박스오피스 데이터를 가져오는 함수 (1시간 캐싱)
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(api_key, target_date):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


# 한국 시간(KST) 기준 어제 날짜 구하기 (달력 선택의 최대 가능 일자)
kst = pytz.timezone("Asia/Seoul")
now_kst = datetime.now(kst)
yesterday = (now_kst - pd.Timedelta(days=1)).date()

st.title("🎬 일별 박스오피스 조회")

# 1. 달력(date_input)으로 날짜 선택 기능
# 최신 집계 가능일인 '어제'를 기본값 및 최대 선택 가능 날짜(max_value)로 지정
selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday,
    max_value=yesterday,
    help="오늘 날짜는 아직 집계 전이므로 어제 일자까지만 선택할 수 있습니다.",
)

target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"선택한 조회 기준일: **{display_date}**")

# Streamlit Secrets(비밀 금고)에서 API 키 불러오기
if "KOBIS_KEY" not in st.secrets:
    st.error(
        "🔐 **KOBIS_KEY가 설정되지 않았습니다.**\n\n"
        "Streamlit Cloud의 **App Settings > Secrets** 메뉴에서 `KOBIS_KEY = '발급받은_키'` 형태로 키를 등록해 주세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# API 데이터 불러오기
data, error_msg = fetch_daily_boxoffice(api_key, target_dt)

# 네트워크/요청 오류 처리
if error_msg:
    st.error(
        f"🚨 **데이터를 가져오지 못했습니다.**\n\n"
        f"- 상세 내용: {error_msg}\n"
        "- 인터넷 연결 상태 및 KOBIS 서버 상태를 확인해 주세요."
    )
    st.stop()

# KOBIS API 내부 오류(faultInfo) 처리
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error(
        f"🚨 **API 오류가 발생했습니다.**\n\n"
        f"- **오류 메시지:** {fault.get('message', '알 수 없는 오류')}\n"
        f"- **오류 코드:** {fault.get('errorCode', 'N/A')}\n\n"
        "💡 **확인 사항:** KOBIS_KEY가 올바르게 입력되었는지 확인해 주세요."
    )
    st.stop()

# 영화 목록 데이터 존재 여부 확인
box_office_result = data.get("boxOfficeResult", {})
movie_list = box_office_result.get("dailyBoxOfficeList", [])

# 2. 비어있을 때 안내 문구
if not movie_list:
    st.warning("⚠️ **그날은 아직 집계 전입니다.**")
    st.stop()

# pandas DataFrame으로 변환 및 숫자 데이터 정제
df = pd.DataFrame(movie_list)

# 문자열로 온 숫자 데이터들을 정수(int)형으로 변환
numeric_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 순위 기준으로 정렬
df = df.sort_values(by="rank", ascending=True).reset_index(drop=True)


# 3. 전날 대비 순위 증감(rankInten)에 따라 화살표 기호 붙이기
def format_rank_change(inten):
    if inten > 0:
        return f"🔺 {inten}"  # 순위 상승 (빨간 위 화살표)
    elif inten < 0:
        return f"🔹 {abs(inten)}"  # 순위 하락 (파란 아래 화살표)
    else:
        return "-"  # 변동 없음


df["rank_change"] = df["rankInten"].apply(format_rank_change)


# 4. 누적 관객수가 100만 명(1,000,000명) 이상인 영화명에 트로피 이모지 추가
def format_movie_title(row):
    title = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        return f"🏆 {title}"
    return title


df["display_movieNm"] = df.apply(format_movie_title, axis=1)

# 🏆 1위 영화 주요 지표 카드 표시
top_movie = df.iloc[0]

st.markdown("---")
st.subheader(f"🥇 선택한 날짜의 1위 영화: **{top_movie['display_movieNm']}**")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="일별 관객수", value=f"{top_movie['audiCnt']:,} 명"
    )
with col2:
    st.metric(
        label="누적 관객수", value=f"{top_movie['audiAcc']:,} 명"
    )
with col3:
    st.metric(
        label="스크린 수", value=f"{top_movie['scrnCnt']:,} 개"
    )

st.markdown("---")

# 📊 관객수 상위 5편 막대그래프 (그래프 x축에는 트로피 없는 원본 영화명 사용)
st.subheader("📊 관객수 상위 5개 영화")
top_5_df = df.head(5).copy()

fig = px.bar(
    top_5_df,
    x="movieNm",
    y="audiCnt",
    labels={"movieNm": "영화명", "audiCnt": "당일 관객수 (명)"},
    text_auto=",",
)
fig.update_traces(
    textposition="outside", marker_color="#1f77b4"
)
fig.update_layout(xaxis_title="", yaxis_title="관객수(명)", height=400)

st.plotly_chart(fig, use_container_width=True)

# 📋 전체 순위표 구성
st.subheader("📋 전체 박스오피스 순위")

# 표에 표시할 항목 구성
display_df = df[
    [
        "rank",
        "rank_change",
        "display_movieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

# 열 이름을 한국어로 변경
display_df.columns = [
    "순위",
    "순위증감",
    "영화명",
    "개봉일",
    "관객수(명)",
    "누적관객(명)",
    "스크린수",
]

# 숫자에 천 단위 콤마(,) 서식 적용하여 표 출력
st.dataframe(
    display_df.style.format(
        {"관객수(명)": "{:,}", "누적관객(명)": "{:,}", "스크린수": "{:,}"}
    ),
    use_container_width=True,
    hide_index=True,
)
