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
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver


# =========================
# Cookie 登入
# =========================
def save_cookies(driver):
    with open(COOKIE_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)


def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False

    driver.get("https://www.threads.net/")
    time.sleep(3)

    with open(COOKIE_FILE, "rb") as f:
        cookies = pickle.load(f)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass

    driver.refresh()
    time.sleep(5)
    return True


def login_threads_once():
    driver = setup_driver(headless=False)

    driver.get("https://www.threads.net/")
    time.sleep(5)

    print("請在 Chrome 視窗手動登入 Threads")
    input("登入完成後按 Enter...")

    save_cookies(driver)
    driver.quit()


# =========================
# 清理文字
# =========================
def clean_text(text):
    text = text.strip()
    text = re.sub(r"\s+", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def is_ui_text(text):
    if len(text) < 6 or len(text) > 1000:
        return True
    if text.count("\n") > 18:
        return True
    return False


def is_duplicate_or_subset(text, seen):
    for old in seen[:]:
        if text == old:
            return True
        if text in old:
            return True
        if old in text:
            seen.remove(old)
    return False


# =========================
# 搜尋 Threads
# =========================
def search_threads_by_keyword(keyword, max_posts=10, scroll_times=15, headless=False):
    driver = setup_driver(headless=headless)

    has_cookie = load_cookies(driver)

    driver.get(f"https://www.threads.net/search?q={keyword}")
    time.sleep(8)

    posts = []
    seen = []

    try:
        for _ in range(scroll_times):
            elements = driver.find_elements(
                By.XPATH,
                "//article | //*[@role='article'] | //div[string-length(normalize-space()) > 15]"
            )

            for el in elements:
                try:
                    text = clean_text(el.text)
                except:
                    continue

                if not text or keyword not in text:
                    continue

                if is_ui_text(text):
                    continue

                if is_duplicate_or_subset(text, seen):
                    continue

                seen.append(text)

                posts.append({
                    "source": "Threads_Login" if has_cookie else "Threads_NoLogin",
                    "keyword": keyword,
                    "text": text
                })

                if len(posts) >= max_posts:
                    break

            if len(posts) >= max_posts:
                break

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

    finally:
        driver.quit()

    return posts


# =========================
# 規則版
# =========================
def rule_based_summary(posts):
    texts = [p["text"] for p in posts]
    text = "\n".join(texts)

    return {
        "摘要": f"抓到 {len(posts)} 筆貼文",
        "關鍵內容": texts[:3]
    }


# =========================
# 🔥 Groq Summary
# =========================
def groq_summary(posts):
    if not GROQ_API_KEY:
        return rule_based_summary(posts)

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

        texts = "\n\n".join([p["text"] for p in posts])

        prompt = f"""
請整理以下貼文的災情摘要（JSON）：
{texts}
"""

        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        return res.choices[0].message.content

    except Exception as e:
        return {"error": str(e), "fallback": rule_based_summary(posts)}


# =========================
# UI
# =========================
st.title("🌐 Threads 災情分析系統（Groq版）")

if st.button("登入 Threads"):
    login_threads_once()
    st.success("登入成功")

keyword = st.text_input("關鍵字", "颱風")
use_ai = st.checkbox("使用 AI（Groq）", True)

if st.button("開始"):
    posts = search_threads_by_keyword(keyword)

    st.write(posts)

    if use_ai:
        result = groq_summary(posts)
    else:
        result = rule_based_summary(posts)

    st.write(result)
