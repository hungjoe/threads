import os
import time
import re
import pickle
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
COOKIE_FILE = "threads_cookies.pkl"

# =========================
# Selenium & Cookie 設定
# =========================
def setup_driver(headless=False):
    options = Options()
    if headless: options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=zh-TW")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE): return False
    driver.get("https://www.threads.net/")
    time.sleep(3)
    with open(COOKIE_FILE, "rb") as f:
        for cookie in pickle.load(f):
            try: driver.add_cookie(cookie)
            except: pass
    driver.refresh()
    time.sleep(4)
    return True

# =========================
# 文字清理與寬鬆過濾
# =========================
def clean_text(text):
    text = re.sub(r"\s+", "\n", text.strip())
    return re.sub(r"\n{2,}", "\n", text).strip()

def is_ui_text(text):
    if len(text) < 4 or len(text) > 2000: return True
    if text.count("\n") > 30: return True
    return False

# =========================
# 🚀 第一層：廣泛主題探測器 (JS 穿透爬蟲 - 主題深潛版)
# =========================
def search_threads_broadly(keyword, max_posts=40, headless=False):
    driver = setup_driver(headless=headless)
    load_cookies(driver)

    extended_keywords = [
        keyword.lower(), 
        f"#{keyword.lower()}", 
        "災", "回報", "現場", "停"
    ]

    # 💡 終極進化：多階段 URL 探索策略
    # 先去「標籤主題頁面 (Tag Page)」找，如果找不滿，再去「一般搜尋頁面」找
    urls_to_try = [
        f"https://www.threads.net/search?q={keyword}&serp_tab=recent", # 一般搜尋最新
        f"https://www.threads.net/search?q=%23{keyword}&serp_tab=recent" # 強制搜尋帶有 Hashtag 的主題
    ]

    posts = []
    seen = set()
    no_new_content_count = 0
    drift_allowance = 20

    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)

        for current_url in urls_to_try:
            if len(posts) >= max_posts:
                break
                
            print(f"🌍 正在深入探測主題網域: {current_url}")
            driver.get(current_url)
            time.sleep(8)
            no_new_content_count = 0 # 換網址時重置計數器

            while len(posts) < max_posts:
                # 雙重鎖定 JS 抓取法
                js_script = """
                let containers = document.querySelectorAll('div[data-pressable-container="true"]');
                let results = [];
                if (containers.length > 0) {
                    containers.forEach(container => {
                        let spans = container.querySelectorAll('span[dir="auto"]');
                        let text = Array.from(spans).map(s => s.innerText).join('\\n');
                        if (text && text.trim().length > 0) results.push(text);
                    });
                } else {
                    let spans = document.querySelectorAll('span[dir="auto"]');
                    spans.forEach(s => {
                        if (s.innerText && s.innerText.trim().length > 0) results.push(s.innerText.trim());
                    });
                }
                return results;
                """
                
                raw_texts = driver.execute_script(js_script)
                current_post_count = len(posts)
                
                for full_text in raw_texts:
                    try:
                        text = clean_text(full_text)
                        text = re.sub(r'(\d+\s*/\s*\d+|\d+\.\d+\s*萬|\d+\s*萬)', '', text).strip()
                    except: continue

                    if not text or is_ui_text(text) or text in seen: 
                        continue

                    # 寬鬆初篩
                    text_clean = text.replace(" ", "").replace("\n", "").lower()
                    is_relevant = any(k in text_clean for k in extended_keywords)
                    
                    if not is_relevant:
                        continue

                    seen.add(text)
                    posts.append({
                        "source": "Threads_Broad_Scraper", 
                        "keyword": keyword, 
                        "text": text
                    })

                    if len(posts) >= max_posts: break

                if len(posts) >= max_posts: break

                if len(posts) == current_post_count:
                    no_new_content_count += 1
                    print(f"⏳ 該主題深度探索中... ({no_new_content_count}/{drift_allowance})")
                else:
                    no_new_content_count = 0
                    print(f"✅ 發現主題新進度：{len(posts)} / {max_posts}")

                if no_new_content_count >= drift_allowance:
                    print("🛑 該主題區塊已見底，準備切換下一個探測網域...")
                    break

                # 變速滾動，觸發 Threads 演算法載入更多主題內容
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(4)

    finally:
        driver.quit()
        
    return posts[:max_posts]

# =========================
# 🧠 第二層：AI 深度淨化與摘要 (Groq)
# =========================
def groq_filter_and_summarize(posts, keyword):
    if not posts: return '{"error": "沒有資料可供分析"}'
    if not GROQ_API_KEY: return '{"error": "未設定 GROQ_API_KEY"}'

    try:
        from openai import OpenAI
        client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
        
        texts = "\n---\n".join([f"貼文 {i+1}: {p['text']}" for i, p in enumerate(posts)])
        
        # 💡 核心指令：賦予 AI「過濾演算法雜訊」的職責
        prompt = f"""
你是一個專業的防災情資分析官。以下是從 Threads 抓取的原始資料。
請注意：社群平台演算法會混入大量與「{keyword}」無關的雜訊（如迷因、政治口水、廣告、日常閒聊）。

請執行以下嚴格任務：
1. 【深度淨化】：剔除所有與「{keyword} 實體災情或現況」無關的貼文。
2. 【情資萃取】：從剩餘的真實災情貼文中，整理出有用資訊。
3. 【結構化輸出】：請嚴格只輸出以下 JSON 格式，不要有任何 Markdown 標記 (如 ```json) 或其他說明文字。

{{
  "analysis_report": {{
    "total_scraped": {len(posts)},
    "valid_disaster_posts": "過濾後剩下的有效貼文數量",
    "noise_ratio": "雜訊比例預估 (例如 30%)",
    "overall_summary": "一句話總結有效災情",
    "locations_mentioned": ["地點A", "地點B"],
    "emergency_needs": ["需求A", "需求B"],
    "verified_alerts": [
      "擷取最關鍵的災情原文 1",
      "擷取最關鍵的災情原文 2"
    ]
  }}
}}

以下為原始抓取資料：
{texts}
"""
        
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1 # 降低溫度，確保 JSON 格式穩定
        )
        return res.choices[0].message.content
    except Exception as e:
        return f'{{"error": "{str(e)}" }}'

# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="韌性臺灣災情雷達 (AI 淨化版)", layout="wide")
st.title("🌐 韌性臺灣災情雷達 (AI 雙層濾網架構)")
st.markdown("本系統採用**廣泛主題探測**結合 **Llama-3 深度淨化**，自動剃除社群演算法雜訊。")

keyword = st.text_input("輸入探測主題 (如：淹水、停電)", "淹水")
max_posts_input = st.number_input("廣泛抓取數量上限", min_value=10, max_value=200, value=40)

if st.button("🚀 啟動情資探測與 AI 淨化"):
    with st.spinner("第一層：正在穿透 Threads 演算法廣泛擷取主題資料..."):
        posts = search_threads_broadly(keyword, max_posts=max_posts_input)

    if posts:
        st.success(f"✅ 第一層探測完畢：共抓取 {len(posts)} 筆潛在關聯貼文。")
        with st.expander("查看未過濾的原始廣泛資料"):
            st.dataframe(pd.DataFrame(posts), width='stretch')

        st.subheader("🧠 第二層：AI 深度淨化與災情萃取")
        with st.spinner("Groq AI 正在剔除演算法雜訊，萃取真實災情..."):
            result = groq_filter_and_summarize(posts, keyword)
        
        st.code(result, language="json")
    else:
        st.warning("⚠️ 範圍內無相關災情。")
