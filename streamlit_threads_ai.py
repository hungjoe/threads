import os
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# =========================
# Selenium 設定
# =========================
def setup_driver(headless=False):
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--start-maximized")
    options.add_argument("--lang=zh-TW")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver


# =========================
# Threads 搜尋
# =========================
def search_threads_by_keyword(keyword, max_posts=10, scroll_times=5):
    """
    用 Selenium 開 Threads 搜尋頁，抓公開可見文字。
    注意：Threads 頁面結構會變，此版適合 MVP demo。
    """

    search_url = f"https://www.threads.net/search?q={keyword}"

    driver = setup_driver(headless=False)
    driver.get(search_url)

    time.sleep(6)

    posts = []
    seen = set()

    for _ in range(scroll_times):
        elements = driver.find_elements(By.XPATH, "//span | //div")

        for el in elements:
            try:
                text = el.text.strip()
            except:
                continue

            if not text:
                continue

            if len(text) < 8:
                continue

            if text in seen:
                continue

            # 必須包含關鍵字，避免抓到大量介面文字
            if keyword not in text:
                continue

            skip_words = [
                "登入",
                "註冊",
                "Threads",
                "Instagram",
                "搜尋",
                "查看更多",
                "回覆",
                "轉發",
                "分享",
                "隱私",
                "使用條款"
            ]

            if any(word == text for word in skip_words):
                continue

            seen.add(text)

            posts.append({
                "source": "Threads_Selenium",
                "keyword": keyword,
                "text": text,
                "url": search_url
            })

            if len(posts) >= max_posts:
                break

        if len(posts) >= max_posts:
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

    driver.quit()
    return posts


# =========================
# 規則版 AI Summary
# =========================
def rule_based_summary(posts):
    texts = [p["text"] for p in posts]
    joined_text = "\n".join(texts)

    disaster_keywords = {
        "淹水": ["淹水", "積水", "水位", "抽水"],
        "停電": ["停電", "斷電", "電力"],
        "道路中斷": ["道路", "封路", "交通", "無法通行", "坍方"],
        "救援需求": ["受困", "救援", "物資", "砂包", "撤離"],
        "土石流": ["土石流", "坍方", "落石"]
    }

    detected_types = []

    for disaster_type, keywords in disaster_keywords.items():
        if any(k in joined_text for k in keywords):
            detected_types.append(disaster_type)

    if not detected_types:
        detected_types = ["未明確判斷"]

    needs = []

    if "砂包" in joined_text:
        needs.append("砂包")
    if "抽水" in joined_text:
        needs.append("抽水設備")
    if "受困" in joined_text or "救援" in joined_text:
        needs.append("救援人力")
    if "物資" in joined_text:
        needs.append("物資支援")
    if "封路" in joined_text or "無法通行" in joined_text:
        needs.append("交通管制")

    if not needs:
        needs = ["尚未明確偵測"]

    confidence = min(1.0, 0.45 + 0.05 * len(posts))

    summary = {
        "災害類型": detected_types,
        "摘要": f"系統共擷取 {len(posts)} 筆 Threads 相關貼文。多筆內容可能涉及 {', '.join(detected_types)}，建議進一步比對官方資料與感測器資訊。",
        "可能需求": needs,
        "可信度": round(confidence, 2),
        "資料來源": ["Threads_Selenium"],
        "限制說明": "此結果根據公開貼文文字初步整理，尚需官方資料或現場回報交叉驗證。"
    }

    return summary


# =========================
# GPT Summary，可選
# =========================
def gpt_summary(posts):
    if not OPENAI_API_KEY:
        return rule_based_summary(posts)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

        texts = "\n\n".join(
            [f"{i+1}. {p['text']}" for i, p in enumerate(posts)]
        )

        prompt = f"""
你是一個防災資訊分析助理。
請根據以下 Threads 公開貼文，整理成災情情報摘要。

請用 JSON 格式輸出，欄位包含：
- 災害類型
- 主要地點
- 摘要
- 可能需求
- 重複事件判斷
- 可信度分數 0 到 1
- 判斷依據
- 限制說明

Threads 貼文如下：
{texts}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是防災資料融合與災情摘要分析專家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        return response.choices[0].message.content

    except Exception as e:
        return {
            "錯誤": str(e),
            "fallback": rule_based_summary(posts)
        }


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="Threads 災情 AI 摘要", layout="wide")

st.title("🌐 Threads 災情貼文搜尋 + AI 統整 MVP")

st.write("輸入關鍵字後，系統會嘗試搜尋 Threads 公開貼文，先顯示前 10 筆，再由 AI 整理摘要。")

keyword = st.text_input("請輸入搜尋關鍵字", value="颱風")
max_posts = st.number_input("顯示貼文數量", min_value=1, max_value=30, value=10)

use_gpt = st.checkbox("使用 GPT 做摘要（需要 OPENAI_API_KEY）", value=False)

if st.button("開始搜尋並統整"):
    if not keyword.strip():
        st.error("請輸入關鍵字")
    else:
        with st.spinner("正在搜尋 Threads 公開貼文..."):
            posts = search_threads_by_keyword(keyword.strip(), max_posts=max_posts)

        if not posts:
            st.warning("沒有抓到貼文。可能原因：Threads 搜尋頁限制、需要登入、或公開資料不足。")
        else:
            st.success(f"成功取得 {len(posts)} 筆貼文")

            df = pd.DataFrame(posts)

            st.subheader("📌 搜尋到的貼文")
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="下載 CSV",
                data=csv,
                file_name=f"threads_{keyword}.csv",
                mime="text/csv"
            )

            st.subheader("🧠 AI 統整結果")

            with st.spinner("AI 正在整理摘要..."):
                if use_gpt:
                    result = gpt_summary(posts)
                else:
                    result = rule_based_summary(posts)

            st.write(result)
