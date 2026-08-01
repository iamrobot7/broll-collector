import os
import re
import io
import json
import zipfile
import urllib.request
import urllib.parse
import streamlit as st

# Page setup
st.set_page_config(page_title="B-Roll Collector Pro", page_icon="🎬", layout="centered")

# Custom UI Styling
st.markdown("""
<style>
    .stApp { background-color: #FAF7F2; color: #222222; }
    .section-num { color: #D97706; font-weight: 800; font-size: 0.85rem; letter-spacing: 1px; }
    .stButton>button { background-color: #D97706; color: white; border-radius: 6px; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🎬 B-Roll Collector Pro")
st.caption("Paste script → Get ranked, numbered B-roll packs in a clean ZIP bundle.")

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    ai_provider = st.selectbox("Semantic Keyword Extraction", ["Rule-based (Free / Local)", "Gemini API"])
    ai_key = st.text_input("Gemini API Key", type="password") if "Gemini" in ai_provider else ""
    
    st.markdown("---")
    st.subheader("Media Sources")
    pexels_key = st.text_input("Pexels API Key", type="password", help="Get free key at pexels.com/api")
    pixabay_key = st.text_input("Pixabay API Key", type="password", help="Get free key at pixabay.com/api")

# --- SCRIPT INPUTS ---
st.markdown('<span class="section-num">01</span> **SCRIPT**', unsafe_allow_html=True)
script_text = st.text_area("Paste full script:", height=150, placeholder="The market crashed and investors panicked...")

sentences = [s.strip() for s in re.split(r'(?<=[.!?]) +', script_text) if s.strip()]
st.caption(f"📊 {len(script_text)} characters · {len(sentences)} sentences")

col1, col2 = st.columns(2)
with col1:
    st.markdown('<span class="section-num">02</span> **CATEGORY**', unsafe_allow_html=True)
    category = st.selectbox("Topic Category", ["Finance & Market", "Dark History / Mystery", "Technology", "Documentary"])
with col2:
    st.markdown('<span class="section-num">03</span> **ORIENTATION**', unsafe_allow_html=True)
    orientation = st.selectbox("Asset Orientation", ["Landscape (16:9)", "Portrait (9:16)"])

st.markdown('<span class="section-num">04</span> **B-ROLL DENSITY**', unsafe_allow_html=True)
density = st.radio("Group sentences by:", ["1 sentence", "2 sentences", "3 sentences"], horizontal=True)

# --- HELPER FUNCTIONS ---

def extract_keywords(text_chunk, category_name):
    """Generates clean visual search terms."""
    if "Gemini" in ai_provider and ai_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={ai_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": f"Context: {category_name}. Extract 2-3 visual stock footage search terms for this sentence: '{text_chunk}'. Output ONLY keywords."}]}]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                return data['candidates'][0]['content']['parts'][0]['text'].strip().replace('"', '')
        except Exception:
            pass
            
    # Simple fallback: filter long words
    words = [w for w in re.sub(r'[^\w\s]', '', text_chunk).split() if len(w) > 3]
    return " ".join(words[:3]) if words else "cinematic background"

def fetch_broll(query, ori):
    """Fetches stock media links."""
    ori_param = "landscape" if "Landscape" in ori else "portrait"
    
    # 1. Try Pexels
    if pexels_key:
        try:
            encoded_q = urllib.parse.quote(query)
            req = urllib.request.Request(
                f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=1&orientation={ori_param}",
                headers={"Authorization": pexels_key}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("videos"):
                    files = data["videos"][0].get("video_files", [])
                    link = next((f["link"] for f in files if f.get("height") in [720, 1080]), files[0]["link"] if files else None)
                    if link:
                        return {"url": link, "ext": ".mp4", "source": "Pexels"}
        except Exception:
            pass

    # 2. Try Pixabay Fallback
    if pixabay_key:
        try:
            encoded_q = urllib.parse.quote(query)
            req = urllib.request.Request(f"https://pixabay.com/api/videos/?key={pixabay_key}&q={encoded_q}&per_page=3")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("hits"):
                    link = data["hits"][0]["videos"].get("medium", {}).get("url")
                    if link:
                        return {"url": link, "ext": ".mp4", "source": "Pixabay"}
        except Exception:
            pass

    return None

# --- RUN BUTTON ---
if st.button("🚀 Collect B-Roll Pack", use_container_width=True):
    if not script_text.strip():
        st.error("Please enter a script first.")
    else:
        step = 1 if "1 sentence" in density else (2 if "2 sentences" in density else 3)
        groups = [" ".join(sentences[i:i+step]) for i in range(0, len(sentences), step)]
        
        st.info(f"Processing {len(groups)} timeline slots...")
        
        zip_buffer = io.BytesIO()
        script_mapping = []
        metadata = []
        
        progress_bar = st.progress(0)
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, chunk in enumerate(groups):
                slot_num = f"{idx+1:02d}"
                query = extract_keywords(chunk, category)
                media = fetch_broll(query, orientation)
                
                if media:
                    try:
                        req = urllib.request.Request(media["url"], headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            file_name = f"{slot_num}{media['ext']}"
                            zip_file.writestr(file_name, resp.read())
                            
                            script_mapping.append(f"{file_name} | Slot {slot_num} | Text: '{chunk}' | Query: '{query}' | Source: {media['source']}")
                            metadata.append({
                                "file": file_name,
                                "slot": idx + 1,
                                "script": chunk,
                                "query": query,
                                "source": media["source"]
                            })
                            st.write(f"✅ **Slot {slot_num}**: Matched `{query}` ({media['source']})")
                    except Exception:
                        st.warning(f"⚠️ Slot {slot_num}: Download timed out.")
                else:
                    st.warning(f"❌ Slot {slot_num}: Add Pexels/Pixabay key to download video clips for `{query}`.")
                
                progress_bar.progress((idx + 1) / len(groups))
            
            # Save mapping file in ZIP
            zip_file.writestr("Script_Mapping.txt", "\n".join(script_mapping))
            zip_file.writestr("Metadata.json", json.dumps(metadata, indent=2))
            
        zip_buffer.seek(0)
        
        st.success("🎉 B-Roll Pack ready!")
        st.download_button(
            label="📦 Download Complete B-Roll ZIP Pack",
            data=zip_buffer,
            file_name="broll_collection_pack.zip",
            mime="application/zip",
            use_container_width=True
                  )
          
