import streamlit as st
import os
import json
import time
import copy
import PyPDF2
import numpy as np
from datetime import datetime
from google import genai
from fpdf import FPDF

# --- 1. INITIALIZATION & PRICING LEDGER ---
st.set_page_config(page_title="Department of Truth", layout="wide")
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CSS_FILE = os.path.join(BASE_DIR, "style.css")
QUOTA_FILE = os.path.join(LOG_DIR, "quota_tracker.json")
CUSTOM_PERSONAS_FILE = os.path.join(BASE_DIR, "custom_personas.json")
GLOBAL_TRUTHS_FILE = os.path.join(BASE_DIR, "global_truths.json")
RULES_FILE = os.path.join(BASE_DIR, "strict_rules.txt")
INTERCEPTOR_FILE = os.path.join(BASE_DIR, "interceptor_rules.txt")

for d in [SESSIONS_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css(CSS_FILE)

MODEL_PRICING = {
    "gemini-3-pro": {"input": 1.25, "output": 5.00}, 
    "gemini-3-flash": {"input": 0.075, "output": 0.30},
    "default": {"input": 1.00, "output": 4.00}
}

# --- 2. THE PERMANENT RULES & AUDIT LOGIC ---
def load_strict_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else "WARNING: strict_rules.txt is empty."
        except Exception:
            return "WARNING: Failed to read strict_rules.txt."
    return "WARNING: strict_rules.txt is missing. Engine operating without constraints."

STRICT_RULES = load_strict_rules()

def verify_pivot_rules(text):
    forbidden = []
    for line in STRICT_RULES.split('\n'):
        if "FORBIDDEN WORDS:" in line.upper():
            words_raw = line.split(":", 1)[1]
            forbidden = [w.strip(" .").lower() for w in words_raw.split(",")]
            break
    
    if not forbidden:
        forbidden = ["delve", "tapestry", "holistic", "costume", "calm"]

    text_lower = text.lower()
    for word in forbidden:
        if word and word in text_lower:
            return False, word
    return True, None

def verify_hype_meter(text):
    words = len(text.split())
    if words > 400:
        data_points = text.count('-') + text.count('*') + text.count(':')
        ratio = words / max(1, data_points)
        if ratio > 80: 
            return False, "Data density too low. Word-to-insight ratio exceeded."
    return True, ""

def load_interceptor_rules():
    if os.path.exists(INTERCEPTOR_FILE):
        try:
            with open(INTERCEPTOR_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else "WARNING: interceptor_rules.txt is empty."
        except Exception:
            return "WARNING: Failed to read interceptor_rules.txt."
    return "WARNING: interceptor_rules.txt is missing."

INTERCEPTOR_RULES = load_interceptor_rules()
    
def run_bias_interceptor(user_input, client):
    try:
        res = client.models.generate_content(
            model=get_background_model(), 
            contents=[{"role": "user", "parts": [{"text": INTERCEPTOR_RULES + "\n\nINPUT:\n" + user_input}]}],
            config={'temperature': 0.0} 
        )
        return res.text.strip()
    except Exception:
        return "PASS"

# --- 3. CONTEXT UTILITIES ---

def compact_context(messages, client):
    if len(messages) < 9:
        return messages
    
    head = messages[0]
    tail = messages[-6:]
    
    middle = [m for m in messages[1:-6] if m.get("persona_name") != "Context Manager"]

    try:
        res = client.models.generate_content(
            model=get_background_model(),
            contents="Extract a bulleted ledger of hard facts, technical constraints, numerical budgets, and finalized strategic decisions from this log. Drop all conversational filler and unverified ideas. Format as a strict data list: " + str(middle)
        )
        summary = {"role": "assistant", "content": f"[SYSTEM DATA LEDGER]:\n{res.text}", "persona_name": "Context Manager"}
        return [head, summary] + tail
    except Exception:
        return messages

# --- 4. CORE UTILITIES & RAG ENGINE ---
def get_stored_key():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            return ""
    return ""

def get_background_model():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("background_model", "gemini-3-flash")
        except Exception:
            return "gemini-3-flash"
    return "gemini-3-flash"

def load_quotas():
    today = datetime.now().strftime('%Y-%m-%d')
    default_q = {
        "date": today, 
        "daily_count": 0, "total_count": 0, "daily_limit": 50, "total_limit": 15000,
        "daily_tokens": 0, "total_tokens": 0, "daily_token_limit": 100000, "total_token_limit": 5000000,
        "daily_cost_usd": 0.0, "total_cost_usd": 0.0
    }
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") != today:
                    data["date"] = today
                    data["daily_count"] = 0
                    data["daily_tokens"] = 0
                    data["daily_cost_usd"] = 0.0
                for k in default_q:
                    if k not in data: 
                        data[k] = default_q[k]
                return data
        except Exception:
            return default_q
    return default_q

def save_quotas(data):
    with open(QUOTA_FILE, "w") as f:
        json.dump(data, f)

def calculate_cost(model_name, input_tokens, output_tokens):
    rates = MODEL_PRICING.get("default")
    for key in MODEL_PRICING:
        if key in model_name.lower():
            rates = MODEL_PRICING[key]
            break
            
    input_cost = (input_tokens / 1000000) * rates["input"]
    output_cost = (output_tokens / 1000000) * rates["output"]
    return input_cost + output_cost

def increment_quota(in_tokens, out_tokens, cost_usd):
    q = load_quotas()
    total_tokens = in_tokens + out_tokens
    q["daily_count"] += 1
    q["total_count"] += 1
    q["daily_tokens"] += total_tokens
    q["total_tokens"] += total_tokens
    q["daily_cost_usd"] += cost_usd
    q["total_cost_usd"] += cost_usd
    save_quotas(q)

def log_diagnostic(model, latency, tokens):
    log_path = os.path.join(LOG_DIR, "diagnostic_log.json")
    entry = {"timestamp": datetime.now().isoformat(), "model": model, "latency": f"{latency:.2f}s", "tokens": tokens}
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

def save_session():
    data = {
        "messages": st.session_state.messages,
        "id": st.session_state.session_id,
        "pinned": st.session_state.get("pinned_insights", []),
        "assumptions": st.session_state.get("pinned_assumptions", []),
        "path": st.session_state.get("breadcrumb_path", []),
        "market": st.session_state.get("market"),
        "style": st.session_state.get("answer_style")
    }
    with open(os.path.join(SESSIONS_DIR, f"{st.session_state.session_id}.json"), "w") as f:
        json.dump(data, f)

def load_global_truths():
    if os.path.exists(GLOBAL_TRUTHS_FILE):
        try:
            with open(GLOBAL_TRUTHS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_global_truths(data):
    with open(GLOBAL_TRUTHS_FILE, "w") as f:
        json.dump(data, f)

def get_dynamic_embed_model(client):
    if "active_embed_model" not in st.session_state:
        try:
            valid_models = [m.name for m in client.models.list() if "embedContent" in m.supported_actions]
            if valid_models:
                st.session_state.active_embed_model = valid_models[0]
            else:
                st.session_state.active_embed_model = "text-embedding-004"
        except Exception:
            st.session_state.active_embed_model = "text-embedding-004"
    return st.session_state.active_embed_model

def chunk_text(text, size=1000, overlap=200):
    chunks = []
    for i in range(0, len(text), size - overlap):
        chunks.append(text[i:i + size])
    return chunks

def get_embeddings(texts, client):
    embeddings = []
    embed_model = get_dynamic_embed_model(client)
    for text in texts:
        res = client.models.embed_content(
            model=embed_model,
            contents=text
        )
        embeddings.append(res.embeddings[0].values)
    return embeddings

def read_file_context(file, client):
    text = ""
    if file.type == "application/pdf":
        reader = PyPDF2.PdfReader(file)
        text = " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    elif file.type == "text/plain" or file.name.endswith(".csv"):
        try:
            text = file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            text = file.getvalue().decode("latin-1", errors="replace")
    
    if not text.strip():
        return None

    chunks = chunk_text(text)
    with st.spinner(f"Indexing {len(chunks)} document nodes..."):
        embeddings = get_embeddings(chunks, client)
    
    return {"chunks": chunks, "embeddings": embeddings}

def retrieve_relevant_context(query, file_data, client, top_k=3):
    if not file_data or not isinstance(file_data, dict) or "embeddings" not in file_data:
        return ""
    
    embed_model = get_dynamic_embed_model(client)
    query_res = client.models.embed_content(
        model=embed_model,
        contents=query
    )
    query_emb = query_res.embeddings[0].values
    
    doc_embs = np.array(file_data["embeddings"])
    
    query_norm = np.linalg.norm(query_emb)
    doc_norms = np.linalg.norm(doc_embs, axis=1)
    
    denominator = query_norm * doc_norms
    denominator[denominator == 0] = 1e-9 
    
    scores = np.dot(doc_embs, query_emb) / denominator
    
    valid_indices = np.where(scores > 0.65)[0]
    
    if len(valid_indices) == 0:
        return "NO RELEVANT DATA FOUND IN DOCUMENT."
        
    sorted_valid = valid_indices[np.argsort(scores[valid_indices])[-top_k:][::-1]]
    relevant_chunks = [file_data["chunks"][i] for i in sorted_valid]
    
    return "\n---\n".join(relevant_chunks)

def load_custom_personas():
    if os.path.exists(CUSTOM_PERSONAS_FILE):
        try:
            with open(CUSTOM_PERSONAS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_custom_personas(data):
    with open(CUSTOM_PERSONAS_FILE, "w") as f:
        json.dump(data, f)

def safe_encode(text):
    """
    Cleans the 'Hot Mess' of Unicode characters that crash FPDF Helvetica.
    Swaps smart quotes, emojis, and long dashes for PDF-safe equivalents.
    """
    if not text:
        return ""
    
    replacements = {
        '\u2019': "'",  
        '\u2018': "'",  
        '\u201c': '"',  
        '\u201d': '"',  
        '\u2013': "-",  
        '\u2014': "-",  
        '\u2026': "...", 
    }
    
    for unicode_char, safe_char in replacements.items():
        text = text.replace(unicode_char, safe_char)
    
    return text.encode('latin-1', 'replace').decode('latin-1')

def export_to_pdf(messages, session_id):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, safe_encode(f"FLUFFLESS STRATEGY: {session_id}"), ln=True)
    for msg in messages:
        pdf.set_font("Helvetica", "B", 10)
        role = msg.get('persona_name', msg['role']).upper()
        pdf.cell(0, 8, safe_encode(f"[{role}]:"), ln=True)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, safe_encode(msg["content"]))
        pdf.ln(4)
    path = os.path.join(LOG_DIR, f"EXPORT_{session_id}.pdf")
    pdf.output(path)
    return path

def execute_strategic_merge(file_a, file_b, client, model_id):
    try:
        clean_file_a = file_a.split(" (")[0]
        clean_file_b = file_b.split(" (")[0]

        with open(os.path.join(SESSIONS_DIR, clean_file_a), "r") as f:
            data_a = json.load(f)
        with open(os.path.join(SESSIONS_DIR, clean_file_b), "r") as f:
            data_b = json.load(f)
        
        pins_a = data_a.get("pinned", [])
        pins_b = data_b.get("pinned", [])
        assump_a = data_a.get("assumptions", [])
        assump_b = data_b.get("assumptions", [])
        
        merge_prompt = f"{STRICT_RULES}\nTASK: STRATEGIC MERGE ARBITRATOR.\nBRANCH A TRUTHS: {pins_a}\nBRANCH B TRUTHS: {pins_b}\nBRANCH A ASSUMPTIONS: {assump_a}\nBRANCH B ASSUMPTIONS: {assump_b}\nReconcile conflicts into a unified Master Strategy. Maintain and aggressively highlight unverified assumptions."
        api_payload = [{"role": "user", "parts": [{"text": merge_prompt}]}]
        
        with st.spinner("Executing Strategic Merge..."):
            res = client.models.generate_content(
                model=st.session_state.active_model_id, 
                contents=api_payload,
                config={'temperature': 0.3}
            )
            st.session_state.session_id = f"MERGE_{datetime.now().strftime('%H%M')}"
            st.session_state.messages = [{"role": "assistant", "content": res.text, "persona_name": "Master Arbitrator"}]
            st.session_state.pinned_insights = pins_a + pins_b
            st.session_state.pinned_assumptions = assump_a + assump_b
            
            in_tokens = getattr(res.usage_metadata, 'prompt_token_count', 0)
            out_tokens = getattr(res.usage_metadata, 'candidates_token_count', 0)
            usd_cost = calculate_cost(st.session_state.active_model_id, in_tokens, out_tokens)
            
            increment_quota(in_tokens, out_tokens, usd_cost)
            save_session()
    except Exception as e:
        st.error(f"Merge Failed: {e}")

# --- 5. PERSONA SUITE (FLATTENED) ---
BASE_PERSONAS = {
    "The Signal Extractor": {"desc": "Translates raw ramblings into business kernels.", "role": "Distill noise into signal.", "temp": 0.3},
    "User Advocate": {"desc": "Maps emotional needs and hidden friction.", "role": "Identify user pain points.", "temp": 0.5},
    "User Experience Architect": {"desc": "IA/IxD, and cognitive load.", "role": "Architect high-fidelity experiences.", "temp": 0.4},
    "Product Manager": {"desc": "MVP and JTBD prioritization.", "role": "Prioritize value and feasibility.", "temp": 0.3},
    "Technical Lead": {"desc": "Feasibility and scaling.", "role": "Ensure technical viability.", "temp": 0.1},
    "The Devil’s Advocate": {"desc": "Stress-tests assumptions and identifies friction.", "role": "Find operational and market risks without assuming inevitable failure.", "temp": 0.3},
    "The Solutions Architect": {"desc": "Rebuilds broken ideas into viable frameworks.", "role": "Propose structural improvements and alternative execution paths for every identified flaw.", "temp": 0.4},
    "Business Strategist": {"desc": "ROI and competitive moats.", "role": "Analyze market positioning.", "temp": 0.3},
    "Growth Marketer": {"desc": "Distribution and Acquisition logic.", "role": "Scale acquisition.", "temp": 0.5}
}

custom_p = load_custom_personas()
PERSONAS = {**BASE_PERSONAS, **custom_p}

# --- 6. STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "breadcrumb_path" not in st.session_state:
    st.session_state.breadcrumb_path = []
if "pinned_insights" not in st.session_state:
    st.session_state.pinned_insights = []
if "pinned_assumptions" not in st.session_state:
    st.session_state.pinned_assumptions = []
if "global_truths" not in st.session_state:
    st.session_state.global_truths = load_global_truths()
if "file_context" not in st.session_state:
    st.session_state.file_context = None
if "indexed_file" not in st.session_state:
    st.session_state.indexed_file = None
if "session_id" not in st.session_state:
    st.session_state.session_id = datetime.now().strftime('%Y-%m-%d_%H-%M')
if "processing" not in st.session_state:
    st.session_state.processing = False
if "market" not in st.session_state:
    st.session_state.market = "Worldwide"
if "answer_style" not in st.session_state:
    st.session_state.answer_style = "Balanced"
if "artifact_locked" not in st.session_state:
    st.session_state.artifact_locked = False

# --- 7. LOADING GATEKEEPER (TOP LEVEL) ---
if "do_load" in st.session_state and st.session_state.do_load:
    load_file = st.session_state.get("file_to_load")
    if load_file and load_file != "--":
        clean_file = load_file.split(" (")[0]
        try:
            with open(os.path.join(SESSIONS_DIR, clean_file), "r") as f:
                d = json.load(f)
                st.session_state.messages = d.get("messages", [])
                st.session_state.breadcrumb_path = d.get("path", [])
                st.session_state.pinned_insights = d.get("pinned", [])
                st.session_state.pinned_assumptions = d.get("assumptions", [])
                st.session_state.session_id = d.get("id", clean_file.replace(".json", ""))
                st.session_state.market = d.get("market", "Worldwide")
                st.session_state.answer_style = d.get("style", "Balanced")
                st.session_state.file_context = None
                st.session_state.indexed_file = None
                st.session_state.artifact_locked = False
            st.session_state.do_load = False
        except Exception as e:
            st.error(f"Load Failed: {e}", icon=":material/error:")

stored_key = get_stored_key()
if stored_key:
    client = genai.Client(api_key=stored_key)
else:
    st.sidebar.caption("**PUBLIC SERVER WARNING:** Your session logs are visible to anyone using this site. Do not input sensitive data. Export your work to PDF before leaving. Clone the repository for private local execution.")
    user_api_key = st.sidebar.text_input("Enter your Gemini API Key", type="password")
    if not user_api_key:
        st.warning("You must enter a Gemini API Key to proceed.")
        st.stop()
    client = genai.Client(api_key=user_api_key)

# --- 8. SIDEBAR (LEFT) ---
with st.sidebar:
    st.title("Department of Truth")
    
    st.text_input("Target Market", key="market")
    st.selectbox("Output Resolution", ["Balanced", "Bullet Points Only", "Big Picture / Executive"], key="answer_style")

    st.divider()

    with st.expander(":material/smart_toy: Custom Lens"):
        c_name = st.text_input("Name")
        c_role = st.text_area("Role Instruction")
        c_temp = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7)
        if st.button(":material/person_add: Lock Custom Lens"):
            new_key = f"CUSTOM: {c_name}"
            custom_p[new_key] = {"desc": "User Defined", "role": c_role, "temp": c_temp}
            save_custom_personas(custom_p)
            st.success(f"{c_name} saved persistently.", icon=":material/check_circle:")
            st.rerun()

    with st.expander(":material/upload_file: Knowledge Base & History"):
        up_file = st.file_uploader("Reference Document (Max 10MB)", type=["pdf", "txt", "csv"])
        
        if up_file:
            MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
            if up_file.size > MAX_FILE_SIZE:
                st.error(f"File too large ({up_file.size / 1024 / 1024:.1f}MB). The limit is 10MB to protect your quota.", icon=":material/error:")
            else:
                if st.session_state.indexed_file != up_file.name:
                    st.session_state.file_context = read_file_context(up_file, client)
                    st.session_state.indexed_file = up_file.name
                
                if st.session_state.file_context:
                    st.success(f"Semantic Index Ready ({len(st.session_state.file_context['chunks'])} chunks)", icon=":material/check_circle:")
        
        all_session_files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        
        saved_files_sorted = sorted(
            all_session_files, 
            key=lambda x: os.path.getmtime(os.path.join(SESSIONS_DIR, x)), 
            reverse=True
        )

        formatted_saved_options = []
        for f in saved_files_sorted:
            mtime = os.path.getmtime(os.path.join(SESSIONS_DIR, f))
            date_str = datetime.fromtimestamp(mtime).strftime('%b %d')
            formatted_saved_options.append(f"{f} ({date_str})")

        load_sid = st.selectbox("Load Session", ["--"] + formatted_saved_options, key="load_sid_select")
        
        if st.button(":material/restore: Load") and load_sid != "--":
            st.session_state.do_load = True
            st.session_state.file_to_load = load_sid
            st.rerun()

    with st.expander(":material/layers: Branch Synthesis"):
        f1 = st.selectbox("Branch A", ["--"] + formatted_saved_options)
        f2 = st.selectbox("Branch B", ["--"] + formatted_saved_options)
        if st.button(":material/call_merge: Execute Merge") and f1 != "--" and f2 != "--":
            _q = load_quotas()
            if _q["daily_count"] >= _q["daily_limit"] or _q["total_count"] >= _q["total_limit"] or _q["daily_tokens"] >= _q["daily_token_limit"]:
                st.error("Hard Limit Reached. Merge blocked to protect your budget.", icon=":material/error:")
            else:
                execute_strategic_merge(f1, f2, client, st.session_state.active_model_id)
                st.rerun()

    with st.expander(":material/public: Global Truths Ledger"):
        if not st.session_state.global_truths:
            st.caption("No permanent truths saved.")
        else:
            for idx, truth in enumerate(st.session_state.global_truths):
                col_text, col_del = st.columns([5, 2], vertical_alignment="center")
                
                with col_text:
                    with st.popover(f"{idx+1}. {truth[:30]}..."):
                        st.markdown(f"**Global Truth {idx+1}**")
                        st.markdown(truth.replace("$", "\\$"))
                        
                with col_del:
                    if st.button(":material/delete:", key=f"del_g_{idx}", help="Remove Global Truth"):
                        st.session_state.global_truths.pop(idx)
                        save_global_truths(st.session_state.global_truths)
                        st.rerun()

    st.divider()

    if st.button(":material/picture_as_pdf: Export PDF", use_container_width=True):
        if st.session_state.messages:
            p = export_to_pdf(st.session_state.messages, st.session_state.session_id)
            with open(p, "rb") as f:
                st.download_button(":material/download: Download report", f, file_name=os.path.basename(p))

    st.divider()

    if st.button(":material/add_comment: New Session", use_container_width=True):
        st.session_state.messages = []
        st.session_state.breadcrumb_path = []
        st.session_state.pinned_insights = []
        st.session_state.pinned_assumptions = []
        st.session_state.file_context = None
        st.session_state.indexed_file = None
        st.session_state.session_id = datetime.now().strftime('%Y-%m-%d_%H-%M')
        st.session_state.artifact_locked = False
        st.rerun()

    st.divider()

    with st.expander(":material/settings: Config & Quota Watchers", expanded=False):
        all_models = {
            f"{m.display_name}": m.name 
            for m in client.models.list() 
            if "generateContent" in m.supported_actions 
            and "gemini" in m.name.lower()
            and "deprecated" not in f"{m.name} {m.display_name}".lower()
            and "nano" not in f"{m.name} {m.display_name}".lower()
            and "banana" not in f"{m.name} {m.display_name}".lower()
        }
        
        default_target = None
        for name in all_models.keys():
            if "gemini 3" in name.lower() and "preview" in name.lower():
                default_target = name
                break
        if not default_target:
            default_target = list(all_models.keys())[0]

        if "selected_label" not in st.session_state:
            st.session_state.selected_label = default_target
        
        model_names = list(all_models.keys())
        safe_index = model_names.index(st.session_state.selected_label) if st.session_state.selected_label in model_names else 0
        
        sel_label = st.selectbox("Engine", model_names, index=safe_index)
        st.session_state.selected_label = sel_label
        st.session_state.active_model_id = all_models[sel_label]
        
        st.divider()
        current_q = load_quotas()
        
        current_q["daily_limit"] = st.number_input("Max Daily Reqs", min_value=1, value=current_q["daily_limit"])
        current_q["total_limit"] = st.number_input("Max Total Reqs", min_value=1, value=current_q["total_limit"])
        current_q["daily_token_limit"] = st.number_input("Max Daily Tokens", min_value=1, value=current_q["daily_token_limit"])
        save_quotas(current_q)
        
        d_ratio = min(current_q["daily_count"] / current_q["daily_limit"], 1.0)
        t_ratio = min(current_q["total_count"] / current_q["total_limit"], 1.0)
        dt_ratio = min(current_q["daily_tokens"] / current_q["daily_token_limit"], 1.0)
        
        st.progress(d_ratio, text=f"Daily Req: {current_q['daily_count']}/{current_q['daily_limit']}")
        st.progress(t_ratio, text=f"Total Req: {current_q['total_count']}/{current_q['total_limit']}")
        st.progress(dt_ratio, text=f"Daily Tokens: {current_q['daily_tokens']}/{current_q['daily_token_limit']}")
        
        st.divider()
        col_d_cost, col_t_cost = st.columns(2)
        with col_d_cost:
            st.metric("Daily Cost", f"${current_q['daily_cost_usd']:.4f}")
        with col_t_cost:
            st.metric("Total Cost", f"${current_q['total_cost_usd']:.4f}")
        
        quota_blocked = False
        if (current_q["daily_count"] >= current_q["daily_limit"] or 
            current_q["total_count"] >= current_q["total_limit"] or 
            current_q["daily_tokens"] >= current_q["daily_token_limit"]):
            st.error("Hard Limit Reached. API blocked to protect your budget.", icon=":material/error:")
            quota_blocked = True

# --- 9. MAIN INTERFACE ---

if st.session_state.session_id.startswith("FORK_"):
    st.info(f":material/call_split: **ACTIVE FORK:** {st.session_state.session_id}")
elif st.session_state.session_id.startswith("MERGE_"):
    st.success(f":material/call_merge: **MERGE SUCCESSFUL:** {st.session_state.session_id}")

if st.session_state.breadcrumb_path:
    st.caption(f":material/location_on: {' > '.join(st.session_state.breadcrumb_path)}")

default_persona_index = 0
persona_list = list(PERSONAS.keys())

if st.session_state.breadcrumb_path and st.session_state.breadcrumb_path[-1] in persona_list:
    default_persona_index = persona_list.index(st.session_state.breadcrumb_path[-1])

col_select, col_help = st.columns([10, 1], vertical_alignment="bottom")

with col_select:
    sel_p = st.selectbox(
        "Active Persona", 
        options=persona_list, 
        index=default_persona_index, 
        format_func=lambda x: f"{x}: {PERSONAS[x]['desc']}",
        label_visibility="collapsed"
    )

with col_help:
    with st.popover("Lens Guide"):
        guide_path = os.path.join(BASE_DIR, "lens_guide.txt")
        if os.path.exists(guide_path):
            with open(guide_path, "r", encoding="utf-8") as f:
                st.markdown(f.read())
        else:
            st.error("lens_guide.txt missing.", icon=":material/error:")

# --- EMPTY STATE ONBOARDING (OPTION 1) ---
if not st.session_state.messages:
    with st.chat_message("assistant", avatar=":material/psychology:"):
        st.markdown("### Let's map your product strategy.")
        st.markdown("To get actionable, grounded feedback, I need to know your actual constraints. **Copy the template below, fill it out, and paste it into the chat to begin:**")
        st.code("""
Target User: [Who exactly is this for?]
Core Problem: [What specific pain are you solving?]
Time & Budget: [e.g., 10 hours/week, $500 launch budget]
Technical Limits: [What can you build vs. what must you buy/outsource?]
Anti-Goals: [What will this product NEVER do?]
        """, language="markdown")
        st.markdown("*It is okay to leave blanks or write 'I don't know'. We will figure out the missing pieces together.*")

for i, msg in enumerate(st.session_state.messages):
    avatar_icon = ":material/person:" if msg["role"] == "user" else ":material/psychology:"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(f"**{msg.get('persona_name', msg['role']).upper()}**")
        
        is_pinned_truth = msg["content"] in st.session_state.pinned_insights
        is_pinned_assumption = msg["content"] in st.session_state.pinned_assumptions
        
        if is_pinned_truth:
            st.warning(msg['content'], icon=":material/push_pin:")
        elif is_pinned_assumption:
            st.error(msg['content'], icon=":material/warning:")
        else:
            # Escapes the dollar signs so they render as normal text
            safe_text = msg["content"].replace("$", "\\$")
            st.markdown(safe_text)
            
        if msg["role"] == "assistant":
            col_truth, col_assume, col_global, col_fork = st.columns(4)
            
            with col_truth:
                if is_pinned_truth:
                    if st.button(":material/keep_off: Unpin Truth", key=f"ut_{i}"):
                        st.session_state.pinned_insights.remove(msg["content"])
                        if msg["content"] in st.session_state.global_truths:
                            st.session_state.global_truths.remove(msg["content"])
                            save_global_truths(st.session_state.global_truths)
                        save_session()
                        st.rerun()
                elif not is_pinned_assumption:
                    if st.button(":material/push_pin: Pin Truth", key=f"pt_{i}"):
                        st.session_state.pinned_insights.append(msg["content"])
                        save_session()
                        st.rerun()
                        
            with col_assume:
                if is_pinned_assumption:
                    if st.button(":material/keep_off: Unpin Assump.", key=f"ua_{i}"):
                        st.session_state.pinned_assumptions.remove(msg["content"])
                        save_session()
                        st.rerun()
                elif not is_pinned_truth:
                    if st.button(":material/warning: Pin Assump.", key=f"pa_{i}"):
                        st.session_state.pinned_assumptions.append(msg["content"])
                        save_session()
                        st.rerun()
                        
            with col_global:
                if is_pinned_truth:
                    is_global = msg["content"] in st.session_state.global_truths
                    if is_global:
                        if st.button(":material/public_off: Unlink Global", key=f"g_{i}"):
                            st.session_state.global_truths.remove(msg["content"])
                            save_global_truths(st.session_state.global_truths)
                            st.rerun()
                    else:
                        if st.button(":material/public: Make Permanent", key=f"g_{i}"):
                            st.session_state.global_truths.append(msg["content"])
                            save_global_truths(st.session_state.global_truths)
                            st.rerun()
                            
            with col_fork:
                if st.button(":material/call_split: Fork", key=f"f_{i}"):
                    st.session_state.messages = st.session_state.messages[:i+1]
                    st.session_state.session_id = f"FORK_{datetime.now().strftime('%H%M')}"
                    st.session_state.artifact_locked = False
                    save_session()
                    st.rerun()
            
            with st.expander("Raw Markdown (Click to Copy)"):
                st.code(msg["content"], language="markdown")

# --- 10. SYNCHRONOUS INPUT & PROCESSING WITH 3-ATTEMPT RETRY ---
if prompt := st.chat_input("Input idea...", disabled=(st.session_state.processing or quota_blocked)):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_session()
    
    word_count = len(prompt.split())
    intercept_result = "PASS"
    relevant_text = ""
    
    if word_count > 5:
        with st.spinner("Scanning input for cognitive bias and retrieving context..."):
            intercept_result = run_bias_interceptor(prompt, client)
            relevant_text = retrieve_relevant_context(prompt, st.session_state.file_context, client) if st.session_state.file_context else ""
        
    if intercept_result.startswith("BLOCK:"):
        reason = intercept_result.replace("BLOCK:", "").strip()
        st.error(f"**BIAS DETECTED. PROMPT REJECTED.**\n\n{reason}\n\n*Rewrite your input with factual grounding.*", icon=":material/block:")
        st.session_state.messages.pop()
        save_session()
    else:
        st.session_state.messages = compact_context(st.session_state.messages, client)
        
        hidden_state = ""
        if len(st.session_state.messages) > 1 and st.session_state.breadcrumb_path:
            prev_p = st.session_state.breadcrumb_path[-1]
            if prev_p != sel_p:
                hidden_state = f"\n[HIDDEN STATE: You are taking over from {prev_p}. Synthesize their core logic and apply your specific lens to advance the strategy without repeating their points.]"

        if sel_p not in st.session_state.breadcrumb_path:
            st.session_state.breadcrumb_path.append(sel_p)
        
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(prompt.replace("$", "\\$"))
        
        start_t = time.time()
        
        rag_block = f"\nRELEVANT FILE CONTEXT: {relevant_text}" if relevant_text else ""
        interlock = f"\nGLOBAL TRUTHS: {st.session_state.global_truths}\nSESSION TRUTHS: {st.session_state.pinned_insights}\nUNVERIFIED ASSUMPTIONS: {st.session_state.pinned_assumptions}\nIf 'UNVERIFIED ASSUMPTIONS' exist, challenge them constructively. MANDATORY RULE: You are a strategic partner and an IDEA FLESHER. BENEFIT OF THE DOUBT: Assume baseline competence. ZERO-INFERENCE: Do not invent backstory. If data is missing, clearly state what data you need. TONE MANDATE: Use ZERO buzzwords. Be blunt, direct, and conversational. Speak in plain English.{rag_block}\nMARKET: {st.session_state.market}\nSTYLE: {st.session_state.answer_style}"
        full_instr = f"{STRICT_RULES}\nROLE: {PERSONAS[sel_p]['role']}{interlock}{hidden_state}"
        
        sys_instruct = {"role": "system", "parts": [{"text": full_instr}]}
        
        api_payload = []
        recent_messages = st.session_state.messages[-6:]
        for m in recent_messages:
            api_role = "model" if m["role"] == "assistant" else "user"
            if api_payload and api_payload[-1]["role"] == api_role:
                api_payload[-1]["parts"][0]["text"] += "\n\n" + m["content"]
            else:
                api_payload.append({"role": api_role, "parts": [{"text": m["content"]}]})
        
        with st.chat_message("assistant", avatar=":material/psychology:"):
            with st.spinner(f"{sel_p} is processing..."):
                success = False
                final_error = ""
                
                for attempt in range(3):
                    try:
                        # --- STAGE 1: FACT EXTRACTION ---
                        p1_prompt = f"TASK: Extract every hard claim, metric, and assumption. STRICT RULES: Remove marketing fluff. PINNED TRUTH: {st.session_state.pinned_insights}\nINPUT: {prompt}"
                        p1_payload = [{"role": "user", "parts": [{"text": p1_prompt}]}]
                            
                        res1 = client.models.generate_content(
                            model=st.session_state.active_model_id, 
                            contents=p1_payload,
                            config={'temperature': 0.0}
                        )
                        extracted_data = res1.text
                        
                        # --- STAGE 2: OBJECTIVE AUDIT ---
                        p2_prompt = f"TASK: Perform an Objective Strategy Audit.\nPERSONA: {sel_p}\nEXTRACTED DATA: {extracted_data}\nIdentify true operational friction. BENEFIT OF THE DOUBT: If a step is missing from the user's prompt, assume they executed it competently, but note that verifying it is required. STRICT RULE: Do not hallucinate worst-case scenarios to create fake friction. Be constructive and grounded."
                        p2_payload = [{"role": "user", "parts": [{"text": p2_prompt}]}]

                        res2 = client.models.generate_content(
                            model=st.session_state.active_model_id, 
                            contents=p2_payload,
                            config={'temperature': 0.0, 'system_instruction': sys_instruct}
                        )
                        audit_data = res2.text
                        
                        # --- STAGE 3: STRATEGIC SYNTHESIS ---
                        p3_payload = copy.deepcopy(api_payload)
                        p3_prompt = f"TASK: Build the resolution report.\nAUDIT DATA: {audit_data}\n\nMANDATORY CONSTRAINTS:\n1. Be Constructive & Direct: Output only what is necessary using plain English. Use ZERO buzzwords. Use short paragraphs, bulleted lists, and aggressive bolding for key concepts to ensure the text is highly scannable.\n2. The Triple-Helix Structure: You MUST format your response using these three specific headers:\n   - THE BIG IDEA: Validate the user's instinct. Explain why this has potential.\n   - THE PROBLEMS: Point out objective risks based ONLY on stated facts. If data is missing, ask for it neutrally (e.g., 'Assuming you handled X, we still need to verify Y').\n   - WHAT TO DO NEXT: Propose 2 concrete, highly specific next steps to build this into a reality.\n3. Conclude with a Strategic Recap table."
                        if p3_payload and p3_payload[-1]["role"] == "user":
                            p3_payload[-1]["parts"] = [{"text": p3_prompt}]
                        else:
                            p3_payload.append({"role": "user", "parts": [{"text": p3_prompt}]})

                        res3 = client.models.generate_content(
                            model=st.session_state.active_model_id, 
                            contents=p3_payload,
                            config={'temperature': PERSONAS[sel_p]['temp'], 'system_instruction': sys_instruct}
                        )
                        
                        is_valid, bad_word = verify_pivot_rules(res3.text)
                        if not is_valid:
                            final_error = f"Audit Flag: Internal system used forbidden word '{bad_word}'."
                            continue
                            
                        is_hype_valid, hype_msg = verify_hype_meter(res3.text)
                        if not is_hype_valid:
                            final_error = f"Hype Flag: {hype_msg}"
                            continue
                        
                        st.markdown(res3.text.replace("$", "\\$"))
                        st.session_state.messages.append({"role": "assistant", "content": res3.text, "persona_name": sel_p})
                        
                        # Safe Token Counting using getattr to prevent crashes if metadata is missing
                        in_tokens = (getattr(res1.usage_metadata, 'prompt_token_count', 0) + 
                                     getattr(res2.usage_metadata, 'prompt_token_count', 0) + 
                                     getattr(res3.usage_metadata, 'prompt_token_count', 0))
                        out_tokens = (getattr(res1.usage_metadata, 'candidates_token_count', 0) + 
                                      getattr(res2.usage_metadata, 'candidates_token_count', 0) + 
                                      getattr(res3.usage_metadata, 'candidates_token_count', 0))

                        usd_cost = calculate_cost(st.session_state.active_model_id, in_tokens, out_tokens)
                        
                        log_diagnostic(st.session_state.active_model_id, time.time() - start_t, in_tokens + out_tokens)
                        increment_quota(in_tokens, out_tokens, usd_cost)
                        save_session()
                        success = True
                        break
                        
                    except Exception as e:
                        if "429" in str(e):
                            st.warning(f"Rate limit hit. Retrying in {5 * (attempt + 1)}s...")
                            time.sleep(5 * (attempt + 1))
                            continue
                        else:
                            final_error = f"API Error: {str(e)}"
                            break
                
                if not success:
                    st.error(f"Generation failed after 3 attempts. Last reason: {final_error}", icon=":material/error:")
                    st.session_state.messages.pop()
                    save_session()
                    
        if success:
            st.rerun()

# --- 11. STRATEGIC ACTIONS BLOCK ---
if st.session_state.messages and not st.session_state.processing and not quota_blocked:
    
    if st.session_state.messages[-1].get("persona_name") != "Artifact Generator":
        st.session_state.artifact_locked = False
        
    is_locked = st.session_state.get("artifact_locked", False)

    st.divider()
    col_rt, col_ideas, col_art_sel, col_art_btn = st.columns([1.5, 1.5, 1.5, 1], vertical_alignment="bottom")
    
    with col_rt:
        if st.button(":material/rocket_launch: Roundtable Audit", use_container_width=True, disabled=is_locked):
            st.session_state.processing = True
            round_instr = f"{STRICT_RULES}\nACT AS A ROUNDTABLE TRIAD: 1. STRATEGIST, 2. USER ADVOCATE, 3. UX ARCHITECT."
            
            trigger_prompt = f"{round_instr}\n\nReview the above context and provide your triad audit."
            st.session_state.messages.append({"role": "user", "content": "Triggered Surgical Roundtable."})
            save_session()
            
            api_payload = []
            for m in st.session_state.messages[:-1]:
                api_role = "model" if m["role"] == "assistant" else "user"
                if api_payload and api_payload[-1]["role"] == api_role:
                    api_payload[-1]["parts"][0]["text"] += "\n\n" + m["content"]
                else:
                    api_payload.append({"role": api_role, "parts": [{"text": m["content"]}]})
            
            if api_payload and api_payload[-1]["role"] == "user":
                api_payload[-1]["parts"][0]["text"] += "\n\n" + trigger_prompt
            else:
                api_payload.append({"role": "user", "parts": [{"text": trigger_prompt}]})
                
            with st.chat_message("assistant", avatar=":material/groups:"):
                with st.spinner("Surgical Roundtable actively auditing..."):
                    success = False
                    final_error = ""
                    for attempt in range(3):
                        try:
                            start_t = time.time()
                            res = client.models.generate_content(
                                model=st.session_state.active_model_id, 
                                contents=api_payload,
                                config={'temperature': 0.3}
                            )
                            st.session_state.messages.append({"role": "assistant", "content": res.text, "persona_name": "Surgical Roundtable"})
                            
                            in_tokens = getattr(res.usage_metadata, 'prompt_token_count', 0)
                            out_tokens = getattr(res.usage_metadata, 'candidates_token_count', 0)
                            usd_cost = calculate_cost(st.session_state.active_model_id, in_tokens, out_tokens)
                            
                            increment_quota(in_tokens, out_tokens, usd_cost)
                            save_session()
                            success = True
                            break
                        except Exception as e:
                            if "429" in str(e):
                                st.warning(f"Rate limit hit. Retrying in {5 * (attempt + 1)}s...")
                                time.sleep(5 * (attempt + 1))
                                continue
                            else:
                                final_error = str(e)
                                break
                    if not success:
                        st.error(f"API Error: {final_error}", icon=":material/error:")
                        st.session_state.messages.pop()
                        save_session()
            
            st.session_state.processing = False
            if success:
                st.rerun()

    with col_ideas:
        if st.button(":material/explore: Extract New Ideas", use_container_width=True, disabled=is_locked):
            st.session_state.processing = True
            
            pivot_instr = f"{STRICT_RULES}\nACT AS A LATERAL GROWTH STRATEGIST. Review the preceding conversation. Your goal is to find hidden value. Identify 3 highly viable, distinct product applications or business models we are currently ignoring. \n\nCONSTRAINTS:\n1. Base these ideas ONLY on the technical capabilities, resources, and UX workflows already discussed.\n2. Do not hallucinate new capital, imaginary partnerships, or unverified technologies.\n3. Focus on immediate feasibility, clear ROI, and untapped user segments.\n4. Frame these as actionable opportunities. If the current conversation lacks enough substance, do not reject the premise; instead, suggest 2 specific areas we should brainstorm next to unlock new adjacencies."
            
            st.session_state.messages.append({"role": "user", "content": "Triggered Lateral Pivot Analysis."})
            save_session()
            
            api_payload = []
            for m in st.session_state.messages[:-1]:
                api_role = "model" if m["role"] == "assistant" else "user"
                if api_payload and api_payload[-1]["role"] == api_role:
                    api_payload[-1]["parts"][0]["text"] += "\n\n" + m["content"]
                else:
                    api_payload.append({"role": api_role, "parts": [{"text": m["content"]}]})
            
            if api_payload and api_payload[-1]["role"] == "user":
                api_payload[-1]["parts"][0]["text"] += "\n\n" + pivot_instr
            else:
                api_payload.append({"role": "user", "parts": [{"text": pivot_instr}]})
                
            with st.chat_message("assistant", avatar=":material/explore:"):
                with st.spinner("Mining session for unexplored adjacencies..."):
                    success = False
                    final_error = ""
                    for attempt in range(3):
                        try:
                            start_t = time.time()
                            res = client.models.generate_content(
                                model=st.session_state.active_model_id, 
                                contents=api_payload,
                                config={'temperature': 0.6} 
                            )
                            st.session_state.messages.append({"role": "assistant", "content": res.text, "persona_name": "Lateral Forecaster"})
                            
                            in_tokens = getattr(res.usage_metadata, 'prompt_token_count', 0)
                            out_tokens = getattr(res.usage_metadata, 'candidates_token_count', 0)
                            usd_cost = calculate_cost(st.session_state.active_model_id, in_tokens, out_tokens)
                            
                            increment_quota(in_tokens, out_tokens, usd_cost)
                            save_session()
                            success = True
                            break
                        except Exception as e:
                            if "429" in str(e):
                                st.warning(f"Rate limit hit. Retrying in {5 * (attempt + 1)}s...")
                                time.sleep(5 * (attempt + 1))
                                continue
                            else:
                                final_error = str(e)
                                break
                    if not success:
                        st.error(f"API Error: {final_error}", icon=":material/error:")
                        st.session_state.messages.pop()
                        save_session()
            
            st.session_state.processing = False
            if success:
                st.rerun()

    with col_art_sel:
        art_type = st.selectbox("Artifact Format", ["Product Requirements Document (PRD)", "Go-to-Market Strategy (GTM)", "Business Blueprint", "Executive Summary"], disabled=is_locked, key="artifact_format_selector")
        
    with col_art_btn:
        if is_locked:
            st.download_button(
                label=":material/markdown: Download .md",
                data=st.session_state.messages[-1]["content"],
                file_name=f"Artifact_{st.session_state.session_id}.md",
                mime="text/markdown",
                use_container_width=True
            )
        else:
            if st.button(":material/article: Compile Artifact", use_container_width=True):
                st.session_state.processing = True
                
                # Base instruction ensuring no fluff and forcing COST-AWARE tool recommendations
                art_instr = f"{STRICT_RULES}\nACT AS A LEAD PRODUCT MANAGER. Synthesize the entire preceding strategic session into a comprehensive, granular, and highly actionable {art_type}. Output strictly in Markdown. Do not include conversational filler. When recommending software, infrastructure, or marketing stacks, ALWAYS define the 'Required Capability' first, then provide a 'Bootstrapped/Free' option and a 'Premium/Scalable' option. Be highly mindful of startup costs."
                
                if art_type == "Business Blueprint":
                    art_instr += """

INSTRUCTION: Output using strictly the following Markdown structure. Expand the Execution Milestones into highly detailed, granular micro-steps. For tech stack needs, provide cost-tiered options.

# BUSINESS BLUEPRINT: [Project Name]

> **STATUS:** Audited
> **PRIMARY CONSTRAINT:** [Insert the biggest limiting factor]

---

## 1. THE CORE MECHANISM
*(A single, zero-fluff sentence defining exactly what this business does and who pays for it.)*
* **The Mechanism:** [Insert sentence]
* **The Value Exchange:** [Who gives you money] in exchange for [What exact utility].

## 2. HARD CONSTRAINTS
* **Budget Limit:** [Hard number]
* **Time to MVP:** [Hard timeline]
* **Technical Limit:** [Specific bottleneck or required tech]

## 3. STRUCTURAL VULNERABILITIES
* **Risk 1:** [Description of logic failure]
* **Risk 2:** [Description of logic failure]

## 4. ENGINEERED FIXES
* **Fix for Risk 1:** [Actionable solution]
* **Fix for Risk 2:** [Actionable solution]

## 5. EXECUTION MILESTONES (The Step-by-Step Roadmap)
*(Chronological, highly detailed steps. Include Tech Stack options where applicable.)*

### Phase 1: Validation & Prototyping (Days 1-14)
* **Objective:** [What needs to be proven true before writing code?]
* **Step-by-Step Execution:**
  1. [Micro-step 1: Exact action]
  2. [Micro-step 2: Exact action]
* **Tech Stack for Phase 1:** [Capability -> Bootstrapped Tool vs. Premium Tool]
* **Success Metric:** [Hard number, e.g., 10 paying beta users]

### Phase 2: The Build (Days 15-30)
* **Objective:** [Constructing the minimum viable core]
* **Step-by-Step Execution:**
  1. [Micro-step 1: Integration/Workflow step]
  2. [Micro-step 2: Quality assurance step]
* **Tech Stack for Phase 2:** [Capability -> Bootstrapped Tool vs. Premium Tool]
* **Success Metric:** [Hard operational number]

### Phase 3: Go-To-Market (Days 31-60)
* **Step-by-Step Execution:**
  1. [Micro-step 1: Exact marketing channel and hook]
  2. [Micro-step 2: Sales script / Ad copy concept]
* **Conversion Metric:** [What hard number indicates the GTM is working]
"""
                elif art_type == "Product Requirements Document (PRD)":
                    art_instr += """

INSTRUCTION: Use the following structure. Expand features into specific UI/UX flows. For the Technical Architecture, you MUST provide a Bootstrapped (Free/Cheap) option and a Premium (Scalable) option for each capability.

# PRD: [Project Name]

## 1. PRODUCT VISION
* **The Problem:** [Clear, single sentence]
* **The Solution:** [How the product mechanically solves it]

## 2. USER WORKFLOW (Step-by-Step)
*(Trace the exact click-by-click path the user takes.)*
1. **Entry:** [How they land on the product]
2. **Interaction:** [Exact steps of the core loop]
3. **Resolution/Conversion:** [The end state or payment trigger]

## 3. TECHNICAL ARCHITECTURE & COST TIERS
* **[Capability 1, e.g., Frontend/Form]:**
  * *Bootstrapped:* [Free/Low-cost tool]
  * *Premium:* [Paid/Scalable tool]
* **[Capability 2, e.g., Backend/Automation]:**
  * *Bootstrapped:* [Free/Low-cost tool]
  * *Premium:* [Paid/Scalable tool]
* **[Capability 3, e.g., AI/API]:**
  * *Bootstrapped:* [Free/Low-cost tool]
  * *Premium:* [Paid/Scalable tool]

## 4. FEATURE PRIORITIZATION
### P0 (Must-Have for MVP):
* [Feature 1]: [Granular description of how it works technically]
* [Feature 2]: [Granular description]

### P1 (Fast Follows):
* [Feature 3]: [Granular description]

## 5. EDGE CASES & FAIL STATES
* **Risk 1:** [What happens if a user inputs bad data?] -> **Fallback:** [System response]
* **Risk 2:** [Tech/API limit] -> **Fallback:** [System response]
"""
                elif art_type == "Go-to-Market Strategy (GTM)":
                    art_instr += """

INSTRUCTION: Use the following structure. Detail exact marketing channels, estimated budgets, and step-by-step conversion funnels. Include Bootstrapped vs. Premium tool options for marketing infrastructure.

# GTM STRATEGY: [Project Name]

## 1. POSITIONING & PRICING
* **The Hook:** [One-sentence marketing pitch]
* **Pricing Model:** [Exact dollar amount and structure]
* **Target Audience:** [Hyper-specific demographic]

## 2. ACQUISITION CHANNELS (The Attack Vector)
### Primary Channel: [e.g., Meta Ads, B2B Cold Email, SEO]
1. **Targeting:** [Specific parameters/lists]
2. **The Creative/Script:** [Exact angle or draft of the copy]
3. **The Call-to-Action:** [Where exactly do they click]

### Secondary Channel:
1. **Execution Step 1:** [Actionable micro-step]
2. **Execution Step 2:** [Actionable micro-step]

## 3. THE CONVERSION FUNNEL & MARKETING STACK
*(Step-by-step breakdown of how a click becomes revenue)*
1. **Landing Page:** [What is the primary H1 and lead magnet?]
2. **The Trigger:** [The exact moment the user is asked to pay/book]
3. **Friction Reduction:** [How you build trust, e.g., guarantees, portfolio]
* **Funnel Tech Stack:** [Capability -> Bootstrapped Tool vs. Premium Tool]

## 4. LAUNCH TIMELINE (Days 1-30)
* **Week 1:** [Specific granular tasks to prepare launch]
* **Week 2:** [Specific granular tasks for initial push]
* **Week 3-4:** [Specific granular tasks for optimization]

## 5. SUCCESS METRICS (KPIs)
* **CAC Target:** [$X]
* **Conversion Rate Target:** [X%]
"""
                elif art_type == "Executive Summary":
                    art_instr += """

INSTRUCTION: Use the following structure. Keep it high-level but grounded in hard numbers, identified risks, and immediate next steps.

# EXECUTIVE SUMMARY: [Project Name]

## 1. THE THESIS
* [1-2 sentences clearly explaining the business, the market gap, and the proposed solution.]

## 2. UNIT ECONOMICS & PROFITABILITY
* **Revenue Stream:** [How it makes money, specific price points]
* **Cost Structure:** [Main expenses, specific tools/labor]
* **Margin/Viability:** [Why this makes financial sense]

## 3. IDENTIFIED RISKS & MITIGATION
* **Operational Risk:** [Specific friction point] -> **Mitigation:** [Specific fix]
* **Market Risk:** [Specific friction point] -> **Mitigation:** [Specific fix]

## 4. IMMEDIATE NEXT STEPS (Next 48 Hours)
1. [Highly specific, granular action item]
2. [Highly specific, granular action item]
3. [Highly specific, granular action item]
"""
                
                trigger_prompt = f"{art_instr}\n\nReview the above context and generate the requested artifact."
                st.session_state.messages.append({"role": "user", "content": f"Triggered Artifact Compilation: {art_type}"})
                save_session()
                
                api_payload = []
                for m in st.session_state.messages[:-1]:
                    api_role = "model" if m["role"] == "assistant" else "user"
                    if api_payload and api_payload[-1]["role"] == api_role:
                        api_payload[-1]["parts"][0]["text"] += "\n\n" + m["content"]
                    else:
                        api_payload.append({"role": api_role, "parts": [{"text": m["content"]}]})
                
                if api_payload and api_payload[-1]["role"] == "user":
                    api_payload[-1]["parts"][0]["text"] += "\n\n" + trigger_prompt
                else:
                    api_payload.append({"role": "user", "parts": [{"text": trigger_prompt}]})
                    
                with st.chat_message("assistant", avatar=":material/psychology:"):
                    with st.spinner(f"Compiling {art_type}..."):
                        success = False
                        final_error = ""
                        for attempt in range(3):
                            try:
                                start_t = time.time()
                                res = client.models.generate_content(
                                    model=st.session_state.active_model_id, 
                                    contents=api_payload,
                                    config={'temperature': 0.2}
                                )
                                st.session_state.messages.append({"role": "assistant", "content": res.text, "persona_name": "Artifact Generator"})
                                
                                st.session_state.artifact_locked = True
                                
                                in_tokens = getattr(res.usage_metadata, 'prompt_token_count', 0)
                                out_tokens = getattr(res.usage_metadata, 'candidates_token_count', 0)
                                usd_cost = calculate_cost(st.session_state.active_model_id, in_tokens, out_tokens)
                                
                                increment_quota(in_tokens, out_tokens, usd_cost)
                                save_session()
                                success = True
                                break
                            except Exception as e:
                                if "429" in str(e):
                                    st.warning(f"Rate limit hit. Retrying in {5 * (attempt + 1)}s...")
                                    time.sleep(5 * (attempt + 1))
                                    continue
                                else:
                                    final_error = str(e)
                                    break
                        if not success:
                            st.error(f"API Error: {final_error}", icon=":material/error:")
                            st.session_state.messages.pop()
                            save_session()
                
                st.session_state.processing = False
                if success:
                    st.rerun()