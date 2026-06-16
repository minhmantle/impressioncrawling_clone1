import streamlit as st
import pandas as pd
import re
import requests
import time
import random
from urllib.parse import urlparse
from io import BytesIO

# ====================== CONTENT SCORING FUNCTION ======================
def score_content(text: str, criteria: list) -> dict:
    if not text or not criteria:
        return {"total_score": 0, "details": {}, "reasoning": "No content or criteria"}
    
    text_lower = text.lower()
    total_score = 0
    details = {}

    for crit in criteria:
        name = crit["name"]
        weight = crit.get("weight", 25)
        max_points = crit.get("max_points", 10)
        
        score = 0
        if len(text) > 30: score += 30
        if len(text) > 80: score += 20
        if any(kw in text_lower for kw in ["mantle", "altseason", "hype", "moon", "community", "join", "check", "link", "rseth", "xstocks"]):
            score += 30
        if any(emoji in text for emoji in ["🚀","🔥","💎","📈","❤️"]):
            score += 20
        
        final_score = min(max_points, round(score / 100 * max_points, 1))
        weighted = round(final_score * weight / 100, 1)
        
        details[name] = final_score
        total_score += weighted

    return {
        "total_score": round(total_score, 1),
        "details": details,
        "reasoning": "Heuristic scoring based on length, keywords & emojis"
    }


# ====================== MAIN APP ======================
st.set_page_config(page_title="Post Checker", layout="wide")
st.title("🔥 Post Checker")
st.markdown("**Mantle internal developed** • Multi-platform metrics + Content Scoring")

def get_platform(url):
    domain = urlparse(url.lower()).netloc
    if any(x in domain for x in ['x.com', 'twitter.com']):
        return "X/Twitter"
    elif 'youtube.com' in domain or 'youtu.be' in domain:
        return "YouTube"
    elif 'facebook.com' in domain:
        return "Facebook"
    elif 'tiktok.com' in domain:
        return "TikTok"
    elif 'instagram.com' in domain:
        return "Instagram"
    return "Other"

def extract_tweet_id(url):
    patterns = [r'/status/(\d+)', r'twitter\.com/[^/]+/status/(\d+)', r'x\.com/[^/]+/status/(\d+)']
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def fetch_x_metrics(tid):
    try:
        resp = requests.get(f"https://api.fxtwitter.com/status/{tid}", timeout=12)
        if resp.status_code == 200:
            data = resp.json().get("tweet", {})
            likes = data.get("likes", 0)
            retweets = data.get("retweets", 0)
            quotes = data.get("quotes", 0)
            bookmarks = data.get("bookmarks", 0)
            views = data.get("views", 0)
            engagement = likes + retweets + quotes + bookmarks
            return {
                "impressions": views,
                "likes": likes,
                "retweets": retweets,
                "quotes": quotes,
                "bookmarks": bookmarks,
                "replies": data.get("replies", 0),
                "engagement": engagement,
                "content": data.get("text", "")[:600],
                "error": ""
            }
    except:
        pass
    return {"impressions":0, "likes":0, "retweets":0, "quotes":0, "bookmarks":0, "replies":0, "engagement":0, "content":"", "error":"Failed"}

# Upload
uploaded_file = st.file_uploader("Upload file chứa link (CSV/Excel/TXT)", type=["csv", "xlsx", "xls", "txt"])

if uploaded_file:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        lines = [line.strip() for line in uploaded_file.getvalue().decode("utf-8").splitlines() if line.strip()]
        df = pd.DataFrame({"Link": lines})

    st.success(f"✅ Loaded {len(df)} links")

    link_col = st.selectbox("Select column containing links", df.columns)

    if st.button("🚀 Fetch Metrics & Calculate Engagement", type="primary"):
        with st.spinner("Fetching data..."):
            results = []
            progress_bar = st.progress(0)

            for idx, link in enumerate(df[link_col].astype(str)):
                platform = get_platform(link)
                row = {"Original_Link": link, "Platform": platform, "Impressions":0, "Engagement":0,
                       "Likes":0, "Retweets_Shares":0, "Quotes":0, "Bookmarks_Saves":0,
                       "Replies_Comments":0, "Content":"", "Error":""}

                if platform == "X/Twitter":
                    tid = extract_tweet_id(link)
                    if tid:
                        data = fetch_x_metrics(tid)
                        row.update({
                            "Impressions": data["impressions"],
                            "Likes": data["likes"],
                            "Retweets_Shares": data["retweets"],
                            "Quotes": data["quotes"],
                            "Bookmarks_Saves": data["bookmarks"],
                            "Replies_Comments": data["replies"],
                            "Engagement": data["engagement"],
                            "Content": data["content"],
                            "Error": data.get("error", "")
                        })

                results.append(row)
                progress_bar.progress(min(100, int((idx+1)/len(df)*100)))
                time.sleep(1.2)

            result_df = pd.DataFrame(results)
            st.subheader("📊 Results")
            st.dataframe(result_df, use_container_width=True)

            # ====================== CONTENT SCORING ======================
            st.markdown("---")
            st.markdown("### 📊 Content Scoring (Mantle Rubric)")

            with st.expander("⚙️ Define Scoring Criteria", expanded=True):
                num = st.number_input("Number of criteria", 1, 10, 4)
                criteria_list = []
                for i in range(int(num)):
                    cols = st.columns([3,5,2,2])
                    with cols[0]:
                        name = st.text_input("Criteria name", f"Criteria {i+1}", key=f"n{i}")
                    with cols[1]:
                        desc = st.text_area("Yêu cầu chấm điểm", key=f"d{i}", height=70)
                    with cols[2]:
                        w = st.number_input("Weight %", 10, 100, 25, key=f"w{i}")
                    with cols[3]:
                        mp = st.number_input("Max Points", 1, 100, 10, key=f"m{i}")
                    criteria_list.append({"name": name, "weight": w, "max_points": mp})

            if st.button("🔥 Apply Scoring", type="primary"):
                scored = []
                for _, r in result_df.iterrows():
                    res = score_content(str(r.get("Content", "")), criteria_list)
                    nr = r.copy()
                    nr["Content_Score"] = res["total_score"]
                    for n, p in res["details"].items():
                        nr[f"Score_{re.sub(r'[^a-zA-Z0-9]', '_', n)}"] = p
                    nr["Reason"] = res["reasoning"]
                    scored.append(nr)
                scored_df = pd.DataFrame(scored)
                st.session_state.scored_df = scored_df
                st.success("Scoring done!")

            if 'scored_df' in st.session_state:
                st.dataframe(st.session_state.scored_df, use_container_width=True)
                st.subheader("Top Content")
                st.dataframe(st.session_state.scored_df.nlargest(10, "Content_Score")[["Original_Link", "Content_Score", "Content"]])

            # Download
            csv = result_df.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, "metrics.csv")

st.caption("Mantle Squad Internal Tool")
