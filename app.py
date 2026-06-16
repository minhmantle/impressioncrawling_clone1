import streamlit as st
import pandas as pd
import re
import requests
import time
import random
from urllib.parse import urlparse
from io import BytesIO

# ... (giữ nguyên phần config, CSS, FUNNY_MESSAGES, get_platform, extract_tweet_id, fetch_x_metrics của mày) ...

# ====================== NEW: CONTENT SCORING ======================
def score_content(text: str, criteria: list) -> dict:
    """Chấm điểm content dựa trên tiêu chí người dùng nhập"""
    if not text or not criteria:
        return {"total_score": 0, "details": {}, "reasoning": "No content or criteria"}
    
    text_lower = text.lower()
    details = {}
    total = 0
    max_score = 0

    for crit in criteria:
        name = crit["name"]
        keywords = [k.strip().lower() for k in crit["keywords"].split(",")]
        weight = crit["weight"]
        max_score += weight
        
        matches = sum(1 for kw in keywords if kw in text_lower)
        score = min(100, (matches / max(1, len(keywords))) * 100) if keywords else 0
        weighted = round(score * weight / 100, 1)
        
        details[name] = {
            "score": round(score, 1),
            "weighted": weighted,
            "keywords_matched": matches
        }
        total += weighted

    return {
        "total_score": round((total / max_score * 100) if max_score > 0 else 0, 1),
        "details": details,
        "reasoning": f"Matched keywords across {len([d for d in details.values() if d['keywords_matched'] > 0])} criteria"
    }

# ====================== MAIN APP ======================
# ... (giữ nguyên phần upload, fetch metrics như cũ) ...

# Sau khi có result_df, thêm scoring
if "result_df" in st.session_state:
    result_df = st.session_state["result_df"]
    
    st.markdown("### 📝 Content Scoring (Mantle Rubric)")
    
    # Sidebar hoặc expander để nhập criteria
    with st.expander("⚙️ Define Scoring Criteria (click to edit)", expanded=True):
        num_criteria = st.number_input("Number of criteria", 1, 10, 3)
        criteria = []
        
        for i in range(num_criteria):
            col1, col2, col3 = st.columns([3, 4, 1])
            with col1:
                name = st.text_input(f"Criteria {i+1} name", value=f"Criteria {i+1}", key=f"name_{i}")
            with col2:
                keywords = st.text_input("Keywords (comma separated)", "hype,altseason,mantle,community", key=f"kw_{i}")
            with col3:
                weight = st.number_input("Weight", 1, 100, 30, key=f"w_{i}")
            criteria.append({"name": name, "keywords": keywords, "weight": weight})
    
    if st.button("🔥 Apply Scoring to All Posts", type="primary"):
        scored_rows = []
        for _, row in result_df.iterrows():
            content = str(row.get("Content", ""))
            score_data = score_content(content, criteria)
            
            new_row = row.copy()
            new_row["Content_Score"] = score_data["total_score"]
            for name, data in score_data["details"].items():
                new_row[f"Score_{name}"] = data["weighted"]
            new_row["Scoring_Reason"] = score_data["reasoning"]
            scored_rows.append(new_row)
        
        scored_df = pd.DataFrame(scored_rows)
        st.session_state["scored_df"] = scored_df
        st.success("✅ Scoring completed!")

    # Hiển thị kết quả có score
    if "scored_df" in st.session_state:
        scored_df = st.session_state["scored_df"]
        st.dataframe(scored_df, use_container_width=True)
        
        # Top posts
        if "Content_Score" in scored_df.columns:
            top_posts = scored_df.nlargest(10, "Content_Score")
            st.subheader("🏆 Top Scored Posts")
            st.dataframe(top_posts[["Original_Link", "Content_Score", "Content"]])

# ... (giữ nguyên download và footer) ...
