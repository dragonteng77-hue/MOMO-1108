# app.py
# 執行方式:streamlit run app.py
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from curl_cffi import requests

API_URL = "https://apisearch.momoshop.com.tw/momoSearchCloud/moec/textSearch"
HOME_URL = "https://www.momoshop.com.tw/"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.momoshop.com.tw",
    "Referer": "https://www.momoshop.com.tw/",
}


def build_payload(keyword: str, page: int) -> dict:
    return {
        "host": "momoshop",
        "flag": "searchEngine",
        "data": {
            "searchValue": keyword,
            "searchType": "1",
            "cateLevel": "-1",
            "curPage": str(page),
            "priceS": "0",
            "priceE": "9999999",
            "showType": "chessboardType",
            "isFuzzy": "0",
            "rtnCateDatainfo": {
                "cateCode": "",
                "cateLv": "-1",
                "keyword": keyword,
                "curPage": str(page),
                "historyDoPush": "false",
                "timestamp": int(time.time() * 1000),
            },
            "flag": 2018,
            "serviceCode": "MT01",
            "addressSearchData": {},
        },
    }


@st.cache_data(ttl=600, show_spinner=False)
def fetch_momo(keyword: str, pages: int) -> tuple[pd.DataFrame, list[str]]:
    """爬取 MOMO 搜尋結果,回傳 (DataFrame, 錯誤訊息列表)"""
    rows, errors = [], []
    session = requests.Session(impersonate="chrome")  # 模擬 Chrome TLS 指紋
    try:
        session.get(HOME_URL, headers=HEADERS, timeout=15)  # 先取得 cookie
    except Exception as e:
        errors.append(f"取得首頁 cookie 失敗:{e}")

    for page in range(1, pages + 1):
        try:
            resp = session.post(
                API_URL, headers=HEADERS, json=build_payload(keyword, page), timeout=20
            )
            if resp.status_code != 200:
                errors.append(f"第 {page} 頁 HTTP {resp.status_code}:{resp.text[:100]}")
                continue
            goods = resp.json().get("rtnSearchData", {}).get("goodsInfoList", [])
            if not goods:
                errors.append(f"第 {page} 頁沒有資料,停止爬取")
                break
            for p in goods:
                rows.append(
                    {
                        "頁數": page,
                        "品名": p.get("goodsName", ""),
                        "價格": p.get("goodsPrice", ""),
                    }
                )
        except Exception as e:
            errors.append(f"第 {page} 頁發生錯誤:{e}")
        time.sleep(1)  # 避免請求過快被擋

    df = pd.DataFrame(rows, columns=["頁數", "品名", "價格"])
    if not df.empty:
        # 清理價格:移除 $、逗號與所有非數字字元
        df["價格"] = df["價格"].astype(str).str.replace(r"[^\d]", "", regex=True)
        df = df[df["價格"] != ""].copy()
        df["價格"] = df["價格"].astype(int)
        df = df.drop_duplicates(subset=["品名", "價格"]).reset_index(drop=True)
    return df, errors


def add_price_bins(df: pd.DataFrame, bin_size: int) -> pd.DataFrame:
    df = df.copy()
    lower = (df["價格"] // bin_size) * bin_size
    df["價格區間"] = lower.astype(str) + "~" + (lower + bin_size - 1).astype(str)
    df["_排序"] = lower
    return df


# ---------------------------- 介面 ----------------------------
st.set_page_config(page_title="MOMO 價格查詢", page_icon="🛒", layout="wide")
st.title("🛒 MOMO 購物網價格查詢與視覺化")

with st.sidebar:
    st.header("查詢條件")
    keyword = st.text_input("商品關鍵字", value="行動電源")
    pages = st.number_input("爬取頁數", min_value=1, max_value=20, value=3, step=1)
    chart_type = st.radio("圖表類型", ["圓餅圖", "折線圖", "旭日圖"])
    bin_size = st.slider("價格區間大小(元)", 100, 2000, 500, step=100)
    top_n = st.slider("折線圖顯示筆數", 10, 200, 70, step=10)
    run = st.button("🔍 查詢", type="primary", use_container_width=True)

if run:
    if not keyword.strip():
        st.warning("請輸入商品關鍵字")
        st.stop()
    with st.spinner(f"正在爬取「{keyword}」前 {pages} 頁..."):
        df, errors = fetch_momo(keyword.strip(), int(pages))
    st.session_state["result"] = (keyword.strip(), df, errors)

if "result" not in st.session_state:
    st.info("請在左側輸入商品與頁數,然後按「查詢」。")
    st.stop()

kw, df, errors = st.session_state["result"]

for msg in errors:
    st.warning(msg)

if df.empty:
    st.error("沒有取得任何資料,可能被網站擋下或關鍵字無結果。")
    st.stop()

# 統計數值
mean_price, max_price, min_price = df["價格"].mean(), df["價格"].max(), df["價格"].min()
c1, c2, c3, c4 = st.columns(4)
c1.metric("商品數", f"{len(df)}")
c2.metric("平均價格", f"${mean_price:,.0f}")
c3.metric("最高價格", f"${max_price:,}")
c4.metric("最低價格", f"${min_price:,}")

st.subheader(f"MOMO 電商網站上「{kw}」售價")

binned = add_price_bins(df, bin_size)

if chart_type == "圓餅圖":
    counts = (
        binned.groupby(["價格區間", "_排序"]).size().reset_index(name="商品數")
        .sort_values("_排序")
    )
    fig = px.pie(counts, names="價格區間", values="商品數", title=f"{kw} 價格區間占比")
    fig.update_traces(textposition="inside", textinfo="percent+label", sort=False)

elif chart_type == "折線圖":
    plot_df = df.head(top_n).reset_index()
    plot_df = plot_df.rename(columns={"index": "商品編號"})
    fig = px.line(
        plot_df, x="商品編號", y="價格", markers=True,
        hover_data=["品名"], title=f"{kw} 價格走勢(前 {len(plot_df)} 筆)",
    )
    fig.add_hline(
        y=mean_price, line_dash="dash", line_color="red",
        annotation_text=f"平均 {mean_price:,.0f}", annotation_position="top left",
    )

else:  # 旭日圖:價格區間 -> 商品
    sun_df = binned.copy()
    sun_df["商品"] = sun_df["品名"].str.slice(0, 18)
    # 每個價格區間最多取 15 筆,避免圖太擠
    sun_df = sun_df.groupby("價格區間", group_keys=False).head(15)
    fig = px.sunburst(
        sun_df, path=["價格區間", "商品"], values="價格",
        title=f"{kw} 價格區間 → 商品(每區間最多 15 筆)",
    )

fig.update_layout(height=650, font=dict(size=14))
st.plotly_chart(fig, use_container_width=True)

with st.expander("📋 查看原始資料"):
    st.dataframe(df, use_container_width=True)

csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "⬇️ 下載 CSV",
    data=csv_bytes,
    file_name=f"MOMO_{datetime.now():%Y%m%d}.csv",
    mime="text/csv",
)
