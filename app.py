import os
import re
import io
import json
import zipfile
import urllib.request
import urllib.parse
import streamlit as st

st.set_page_config(page_title="B-Roll's Collector", page_icon="🎬", layout="wide")

# Custom Styling
st.markdown("""
<style>
    .stApp { background-color: #FAF7F2; color: #1F2937; }
    .slot-box { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-left: 5px solid #D97706; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
    .badge-score { background-color: #FEF3C7; color: #92400E; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 0.8rem; }
    .stButton>button { background-color: #D97706; color: white; border-radius: 6px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🎬 B-Roll's Collector")
st.caption("Auto-match stock clips/images, preview relevance reasons, tweak slots manually, and export a complete editor pack.")

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Setup & API Keys")
    st.caption("Enter free API keys to enable automatic fetching:")
    pexels_key = st.text_input("Pexels API Key", type="password", help="Get key from pexels.com/api")
    pixabay_key = st.text_input("Pixabay API Key", type="password", help="Get key from pixabay.com/api")
    
    st.markdown("---")
    st.header("🤖 AI Context Engine")
    ai_provider = st.selectbox("Keyword Engine", ["Smart Heuristic (Free / Local)", "Gemini AI"])
    ai_key = st.text_input("Gemini API Key", type="password") if "Gemini" in ai_provider else ""

# --- SCRIPT & CONFIG INPUTS ---
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1. Script Input")
    script_text = st.text_area("Paste full script here:", height=220, placeholder="The market crashed suddenly in 1929. Investors panicked across New York...")

with col2:
    st.subheader("2. Context & Pacing")
    category = st.selectbox("Topic Category", ["Finance & Market", "Dark History / Mystery", "Technology", "Health & Lifestyle", "General Documentary"])
    
    # Auto Target Audience Detection
    detected_aud = "Global"
    if script_text:
        low_text = script_text.lower()
        if any(w in low_text for w in ["pakistan", "rupee", "lahore", "karachi", "islamabad"]):
            detected_aud = "Pakistan"
        elif any(w in low_text for w in ["india", "delhi", "mumbai", "crore"]):
            detected_aud = "India"
        elif any(w in low_text for w in ["dollar", "usa", "wall street", "america"]):
            detected_aud = "USA / Global"
            
    audience = st.selectbox("Target Audience / Regional Context", ["Auto-Detect", "Global", "Pakistan", "India", "USA / Western"], index=0)
    final_audience = detected_aud if audience == "Auto-Detect" else audience
    st.caption(f"🎯 **Detected Context:** `{final_audience}`")

    density = st.radio("B-Roll Pacing (Group sentences by):", ["1 sentence", "2 sentences", "3 sentences"], horizontal=True)
    asset_pref = st.radio("Media Preference:", ["Both (Video Priority, Image Fallback)", "Videos Only", "Images Only"], index=0)

# --- PROCESSING & KEYWORD EXTRACTION ---
def extract_smart_query(text_chunk, cat, aud):
    if "Gemini" in ai_provider and ai_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={ai_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": f"Context: Category={cat}, Audience={aud}. Extract 2 concise visual search terms for stock media for this line: '{text_chunk}'. Output ONLY keywords."}]}]
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                return data['candidates'][0]['content']['parts'][0]['text'].strip().replace('"', '')
        except Exception:
            pass
            
    # Heuristic fallback: Extract high-value nouns/verbs
    words = [w for w in re.sub(r'[^\w\s]', '', text_chunk).split() if len(w) > 3]
    return " ".join(words[:2]) if words else f"{cat.lower()} background"

def search_media(query, pref):
    encoded_q = urllib.parse.quote(query)
    
    # 1. PEXELS VIDEO
    if pref != "Images Only" and pexels_key:
        try:
            req = urllib.request.Request(
                f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=1",
                headers={"Authorization": pexels_key}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                if data.get("videos"):
                    files = data["videos"][0].get("video_files", [])
                    link = next((f["link"] for f in files if f.get("height") in [720, 1080]), files[0]["link"] if files else None)
                    if link:
                        return {"url": link, "ext": ".mp4", "source": "Pexels (Video)", "score": "92%", "reason": f"Direct visual match for query '{query}'"}
        except Exception:
            pass

    # 2. PIXABAY VIDEO
    if pref != "Images Only" and pixabay_key:
        try:
            req = urllib.request.Request(f"https://pixabay.com/api/videos/?key={pixabay_key}&q={encoded_q}&per_page=1")
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                if data.get("hits"):
                    link = data["hits"][0]["videos"].get("medium", {}).get("url")
                    if link:
                        return {"url": link, "ext": ".mp4", "source": "Pixabay (Video)", "score": "88%", "reason": f"Topic match for query '{query}'"}
        except Exception:
            pass

    # 3. PEXELS IMAGE (Fallback)
    if pref != "Videos Only" and pexels_key:
        try:
            req = urllib.request.Request(
                f"https://api.pexels.com/v1/search?query={encoded_q}&per_page=1",
                headers={"Authorization": pexels_key}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                if data.get("photos"):
                    return {"url": data["photos"][0]["src"]["large2x"], "ext": ".jpg", "source": "Pexels (Photo)", "score": "81%", "reason": f"High-res image fallback for '{query}'"}
        except Exception:
            pass

    # 4. WIKIMEDIA COMMONS (Free Image Fallback)
    if pref != "Videos Only":
        try:
            wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={encoded_q}&gsrlimit=1&prop=imageinfo&iiprop=url&format=json"
            req = urllib.request.Request(wiki_url, headers={'User-Agent': 'BRollCollector/1.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                pages = data.get("query", {}).get("pages", {})
                for k, v in pages.items():
                    img_url = v["imageinfo"][0]["url"]
                    ext = ".png" if img_url.endswith(".png") else ".jpg"
                    return {"url": img_url, "ext": ext, "source": "Wikimedia (Photo)", "score": "75%", "reason": f"Historical/Documentary image archive for '{query}'"}
        except Exception:
            pass

    return None

# --- MAIN WORKFLOW ---
if script_text.strip():
    sentences = [s.strip() for s in re.split(r'(?<=[.!?]) +', script_text) if s.strip()]
    step = 1 if "1 sentence" in density else (2 if "2 sentences" in density else 3)
    chunks = [" ".join(sentences[i:i+step]) for i in range(0, len(sentences), step)]

    st.write("---")
    st.subheader(f"📊 Visual Timeline ({len(chunks)} Slots)")

    # Store results across rerenders
    if 'slot_results' not in st.session_state:
        st.session_state.slot_results = {}

    for idx, chunk in enumerate(chunks):
        slot_key = f"slot_{idx+1:02d}"
        
        # Initial search initialization
        if slot_key not in st.session_state.slot_results:
            auto_query = extract_smart_query(chunk, category, final_audience)
            asset = search_media(auto_query, asset_pref)
            st.session_state.slot_results[slot_key] = {
                "script": chunk,
                "query": auto_query,
                "asset": asset
            }

        slot_data = st.session_state.slot_results[slot_key]
        asset = slot_data["asset"]

        # Slot Preview Card
        with st.container():
            st.markdown(f"""
            <div class="slot-card">
                <strong>Slot {slot_key.upper()}</strong> | Line: <em>"{chunk}"</em>
            </div>
            """, unsafe_allow_html=True)

            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                st.write(f"🔍 **Keyword:** `{slot_data['query']}`")
                if asset:
                    st.write(f"📌 **Source:** {asset['source']}")
                    st.markdown(f"⭐ **Relevance Score:** <span class='badge-score'>{asset['score']}</span>", unsafe_allow_html=True)
                else:
                    st.warning("No media found.")

            with c2:
                if asset:
                    st.write(f"💡 **Why Matched:** {asset['reason']}")

            with c3:
                # Manual Query Override per Slot
                new_query = st.text_input(f"Tweak Keyword (Slot {slot_key})", value=slot_data['query'], key=f"input_{slot_key}")
                if st.button(f"🔄 Search New Match", key=f"btn_{slot_key}"):
                    new_asset = search_media(new_query, asset_pref)
                    st.session_state.slot_results[slot_key]["query"] = new_query
                    st.session_state.slot_results[slot_key]["asset"] = new_asset
                    st.rerun()

    # --- ZIP BUNDLE EXPORT ---
    st.write("---")
    if st.button("📦 Export Complete B-Roll ZIP Pack", use_container_width=True):
        zip_buffer = io.BytesIO()
        script_mapping = []
        metadata = []

        progress = st.progress(0)
        total_slots = len(chunks)

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, (slot_key, data) in enumerate(st.session_state.slot_results.items()):
                asset = data["asset"]
                slot_num = f"{idx+1:02d}"

                if asset:
                    try:
                        req = urllib.request.Request(asset["url"], headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=12) as resp:
                            file_name = f"{slot_num}{asset['ext']}"
                            zip_file.writestr(file_name, resp.read())

                            script_mapping.append(f"{file_name} | Slot {slot_num} | Sentence: '{data['script']}' | Keyword: '{data['query']}' | Source: {asset['source']}")
                            metadata.append({
                                "file": file_name,
                                "slot": idx + 1,
                                "sentence": data['script'],
                                "query": data['query'],
                                "source": asset['source'],
                                "score": asset['score'],
                                "reason": asset['reason']
                            })
                    except Exception:
                        pass

                progress.progress((idx + 1) / total_slots)

            # Package mapping and metadata files
            zip_file.writestr("Script_Mapping.txt", "\n".join(script_mapping))
            zip_file.writestr("Metadata.json", json.dumps(metadata, indent=2))

        zip_buffer.seek(0)
        st.success("🎉 Your B-Roll ZIP pack is ready!")
        st.download_button(
            label="⬇️ Download B-Roll's Collector Pack (.ZIP)",
            data=zip_buffer,
            file_name="broll_collector_pack.zip",
            mime="application/zip",
            use_container_width=True
        )
