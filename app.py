import time

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="MOMO 商品價格查詢", page_icon="🛒", layout="wide")

URL = "https://apisearch.momoshop.com.tw/momoSearchCloud/moec/textSearch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    )
}


def build_payload(keyword: str, page: int) -> dict:
    return {
        "host": "momoshop",
        "flag": "searchEngine",
        "data": {
            "specialGoodsType": "",
            "isBrandSeriesPage": "false",
            "authorNo": "",
            "originalCateCode": "",
            "cateType": "",
            "searchValue": keyword,
            "cateCode": "",
            "cateLevel": "-1",
            "cp": "N",
            "NAM": "N",
            "first": "N",
            "freeze": "N",
            "superstore": "N",
            "tvshop": "N",
            "china": "N",
            "tomorrow": "N",
            "stockYN": "N",
            "prefere": "N",
            "threeHours": "N",
            "video": "N",
            "cycle": "N",
            "cod": "N",
            "superstorePay": "N",
            "showType": "chessboardType",
            "curPage": str(page),
            "priceS": "0",
            "priceE": "9999999",
            "searchType": "1",
            "reduceKeyword": "",
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
            "adSource": "tenmax",
        },
    }


@st.cache_data(show_spinner=False, ttl=600)
def fetch_momo(keyword: str, pages: int) -> pd.DataFrame:
    rows = []
    for page in range(1, pages + 1):
        resp = requests.post(
            URL, headers=HEADERS, json=build_payload(keyword, page), timeout=15
        )
        if resp.status_code != 200:
            st.warning(f"第 {page} 頁請求失敗,狀態碼:{resp.status_code}")
            break
        goods = resp.json().get("rtnSearchData", {}).get("goodsInfoList", [])
        if not goods:
            break
        for g in goods:
            rows.append(
                {
                    "頁數": page,
                    "品名": g.get("goodsName", ""),
                    "價格": g.get("goodsPrice", ""),
                }
            )
        time.sleep(0.5)  # 避免請求過快

    df = pd.DataFrame(rows, columns=["頁數", "品名", "價格"])
    if df.empty:
        return df
    # 價格清理:移除 $、逗號與其他非數字字元
    df["價格"] = df["價格"].astype(str).str.replace(r"[^\d]", "", regex=True)
    df = df[df["價格"] != ""].copy()
    df["價格"] = df["價格"].astype(int)
    return df.reset_index(drop=True)


def add_price_range(df: pd.DataFrame, bins: int = 6) -> pd.DataFrame:
    df = df.copy()
    try:
        cats = pd.qcut(df["價格"], q=bins, duplicates="drop")
    except ValueError:
        cats = pd.cut(df["價格"], bins=1)
    df["價格區間"] = cats.apply(lambda i: f"{int(i.left)}~{int(i.right)}")
    return df


# ---------------- UI ----------------
st.title("🛒 MOMO 商品價格查詢與視覺化")

with st.sidebar:
    st.header("查詢條件")
    keyword = st.text_input("商品關鍵字", value="行動電源")
    pages = st.number_input("爬取頁數", min_value=1, max_value=20, value=2, step=1)
    chart_type = st.radio("圖表類型", ["圓餅圖", "折線圖", "旭日圖"])
    run = st.button("開始查詢", type="primary")

if run:
    if not keyword.strip():
        st.error("請輸入商品關鍵字")
        st.stop()
    with st.spinner("爬取中..."):
        try:
            st.session_state["df"] = fetch_momo(keyword.strip(), int(pages))
            st.session_state["kw"] = keyword.strip()
        except requests.RequestException as e:
            st.error(f"連線失敗:{e}")
            st.stop()

df = st.session_state.get("df")
kw = st.session_state.get("kw", "")

if df is None:
    st.info("請在左側輸入商品與頁數,再按「開始查詢」。")
elif df.empty:
    st.warning("查無資料,請換個關鍵字或稍後再試。")
else:
    mean_p, max_p, min_p = df["價格"].mean(), df["價格"].max(), df["價格"].min()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("商品數", len(df))
    c2.metric("平均價格", f"${mean_p:,.0f}")
    c3.metric("最高價格", f"${max_p:,}")
    c4.metric("最低價格", f"${min_p:,}")

    if chart_type == "圓餅圖":
        d = add_price_range(df)
        cnt = d["價格區間"].value_counts().reset_index()
        cnt.columns = ["價格區間", "商品數"]
        fig = px.pie(cnt, names="價格區間", values="商品數", hole=0.3,
                     title=f"MOMO「{kw}」價格區間分布")
    elif chart_type == "折線圖":
        d = df.reset_index().rename(columns={"index": "商品編號"})
        fig = px.line(d, x="商品編號", y="價格", hover_data=["品名", "頁數"],
                      markers=True, title=f"MOMO「{kw}」售價")
        fig.add_hline(y=mean_p, line_dash="dash", line_color="red",
                      annotation_text=f"平均 {mean_p:,.0f}")
    else:
        d = add_price_range(df)
        d["商品"] = d["品名"].str.slice(0, 20) + " #" + d.index.astype(str)
        fig = px.sunburst(d, path=["價格區間", "商品"], values="價格",
                          title=f"MOMO「{kw}」價格區間 → 商品")

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("原始資料", expanded=False):
        st.dataframe(df, use_container_width=True)
    st.download_button(
        "下載 CSV",
        df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name=f"MOMO_{kw}_{time.strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
