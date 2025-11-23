# app.py
# 3-Agent Loop (A-B-A-B-C) Streamlit app
# - Supports PDF and image (.png, .jpg, .jpeg, .pnp.png)
# - Uses pdfplumber and pytesseract if available
# - Uses st.secrets or environment variables for API keys/endpoints
# - If APIs not configured, runs a simulated agent loop for testing
# - Produces BOQ with 4 sheets: ของ+ค่าแรง, ของ, ค่าแรง, PO

import os
import io
import uuid
import sqlite3
import datetime
import time
import json
import base64
import re
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st
import requests

# Optional libs
try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

# -----------------------
# Config & secrets
# -----------------------
DB_PATH = os.getenv("BOQ_APP_DB", "boq_app.db")
PRICE_CSV_CACHE = "price_list_cache.csv"

def secret_get(key: str):
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key)

ARCH_API_KEY = secret_get("ARCH_API_KEY")
ARCH_ENDPOINT = secret_get("ARCH_ENDPOINT")  # optional
ENG_API_KEY = secret_get("ENG_API_KEY")
ENG_ENDPOINT = secret_get("ENG_ENDPOINT")    # optional
PRICE_API_KEY = secret_get("PRICE_API_KEY")
PRICE_ENDPOINT = secret_get("PRICE_ENDPOINT")# optional

# sample/test PDF (local) - file path used earlier in session
TEST_PDF_PATH = "/mnt/data/7dfdf93c-beb9-4abf-a1eb-7668cd324077.pdf"

# -----------------------
# DB init
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            role TEXT,
            filename TEXT,
            metadata TEXT,
            version INTEGER,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS boqs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            submission_id TEXT,
            data_blob BLOB,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# -----------------------
# Utilities
# -----------------------
def now_iso():
    return datetime.datetime.utcnow().isoformat()

def read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def save_submission(project_id: str, role: str, filename: str, metadata: str) -> str:
    sid = str(uuid.uuid4())
    version = get_latest_version(project_id) + 1
    now = now_iso()
    c = conn.cursor()
    c.execute("INSERT INTO submissions (id, project_id, role, filename, metadata, version, created_at) VALUES (?,?,?,?,?,?,?)",
              (sid, project_id, role, filename, metadata, version, now))
    conn.commit()
    return sid

def get_latest_version(project_id: str) -> int:
    c = conn.cursor()
    c.execute("SELECT MAX(version) FROM submissions WHERE project_id = ?", (project_id,))
    r = c.fetchone()
    return int(r[0]) if r and r[0] is not None else 0

def save_boq_blob(project_id: str, submission_id: str, excel_bytes: bytes) -> str:
    bid = str(uuid.uuid4())
    now = now_iso()
    c = conn.cursor()
    c.execute("INSERT INTO boqs (id, project_id, submission_id, data_blob, created_at) VALUES (?,?,?,?,?)",
              (bid, project_id, submission_id, sqlite3.Binary(excel_bytes), now))
    conn.commit()
    return bid

# -----------------------
# Parsing (PDF and images)
# -----------------------
def extract_text_from_pdf_bytes(b: bytes) -> str:
    if pdfplumber:
        try:
            text = ""
            with pdfplumber.open(io.BytesIO(b)) as pdf:
                for p in pdf.pages:
                    pt = p.extract_text()
                    if pt:
                        text += pt + "\n"
            return text
        except Exception:
            return ""
    else:
        # fallback: try pypdf (if installed) or return empty
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(b))
            txt = ""
            for p in reader.pages:
                t = p.extract_text()
                if t:
                    txt += t + "\n"
            return txt
        except Exception:
            return ""

def extract_text_from_image_bytes(b: bytes) -> str:
    if Image is None:
        return ""
    try:
        img = Image.open(io.BytesIO(b))
    except Exception:
        return ""
    if pytesseract:
        try:
            text = pytesseract.image_to_string(img, lang='eng+tha')
            return text
        except Exception:
            return ""
    else:
        return ""

def parse_document_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Try to extract item rows from document bytes.
    If cannot reliably parse to rows, returns DataFrame with single column raw_text for manual check.
    """
    lower = filename.lower()
    text = ""
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf_bytes(file_bytes)
    elif lower.endswith((".png",".jpg",".jpeg",".pnp.png",".pnp",".pnp.png")):
        text = extract_text_from_image_bytes(file_bytes)
    else:
        # attempt pdf first
        text = extract_text_from_pdf_bytes(file_bytes)

    if not text:
        return pd.DataFrame({"raw_text":[f"(no extracted text) from {filename}"]})

    # Normalize lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Heuristic: extract lines that end with qty + unit or contain numeric qty
    rows = []
    # pattern: optional code, description, qty, unit
    pattern = re.compile(r"^(?:(?P<code>[A-Za-z0-9\-\._/]+)\s+)?(?P<desc>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<unit>[A-Za-zก-๙/%\"\.]+)$")
    for ln in lines:
        m = pattern.match(ln)
        if m:
            code = m.group("code") or ""
            desc = m.group("desc").strip()
            qty = float(m.group("qty").replace(",","."))
            unit = m.group("unit")
            rows.append({"item_code": code, "description": desc, "qty": qty, "unit": unit})
        else:
            # fallback: if line contains a number at end (qty unit)
            m2 = re.search(r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+([A-Za-zก-๙/%\"\.]+)$", ln)
            if m2:
                desc = m2.group(1).strip()
                qty = float(m2.group(2).replace(",","."))
                unit = m2.group(3)
                rows.append({"item_code":"", "description": desc, "qty": qty, "unit": unit})

    if rows:
        return pd.DataFrame(rows)
    # otherwise return raw text for manual inspection
    return pd.DataFrame({"raw_text": ["\n".join(lines[:200])]})

# -----------------------
# Price list helpers
# -----------------------
def load_price_list_from_buffer(buf) -> pd.DataFrame:
    try:
        df = pd.read_csv(buf, encoding='utf-8')
    except Exception:
        try:
            df = pd.read_csv(buf, encoding='latin1')
        except Exception:
            df = pd.DataFrame()
    return df

def load_price_list_from_github(raw_url: str) -> pd.DataFrame:
    try:
        r = requests.get(raw_url, timeout=20)
        r.raise_for_status()
        return load_price_list_from_buffer(io.StringIO(r.text))
    except Exception:
        return pd.DataFrame()

def match_price_local(items_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    out = items_df.copy()
    out["matched_code"] = ""
    out["matched_unit_price"] = 0.0
    out["match_confidence"] = 0.0
    if price_df is None or price_df.empty:
        return out
    for idx, row in out.iterrows():
        desc = str(row.get("description","")).lower()
        # try first token substring match
        token = desc.split()[0] if desc.split() else desc
        try:
            candidates = price_df[price_df["description"].str.lower().str.contains(token, na=False)]
        except Exception:
            candidates = price_df[price_df["description"].str.lower().str.contains(desc, na=False)]
        if not candidates.empty:
            chosen = candidates.iloc[0]
            out.at[idx,"matched_code"] = chosen.get("code","")
            try:
                out.at[idx,"matched_unit_price"] = float(chosen.get("unit_price",0))
            except Exception:
                out.at[idx,"matched_unit_price"] = 0.0
            out.at[idx,"match_confidence"] = 0.75
        else:
            out.at[idx,"match_confidence"] = 0.0
    return out

# -----------------------
# Agent API calls (wrapper)
# -----------------------
def call_api_json(endpoint: str, api_key: str, payload: dict, timeout=120) -> dict:
    """
    Generic POST JSON call. Expects endpoint and api_key to be provided.
    If not provided, raises.
    """
    if not endpoint or not api_key:
        raise ValueError("Missing endpoint or api_key for API call")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

# -----------------------
# Agent implementations (can run in sim mode if no endpoints)
# -----------------------
def run_A_agents_sim(file_bytes: bytes, n=6) -> List[dict]:
    # simple heuristic: each A returns parsed items with slight variation
    base = parse_document_bytes(file_bytes, "uploaded")
    variants = []
    for i in range(n):
        v = base.copy()
        # simulate variation by slightly changing qty for some rows
        if not v.empty and "qty" in v.columns:
            v2 = v.copy()
            v2["qty"] = v2["qty"].apply(lambda q: max(1, q * (1 + (i - n/2) * 0.02)))
            variants.append({"variant_id": i, "items": v2.to_dict(orient="records"), "notes": f"Variant {i}"})
        else:
            variants.append({"variant_id": i, "items": [], "notes": f"Variant {i}"})
    return variants

def run_A_agents_api(file_bytes: bytes, n=6):
    # send file bytes (base64) to ARCH_ENDPOINT for each agent
    if not ARCH_ENDPOINT or not ARCH_API_KEY:
        raise ValueError("ARCH endpoint/key not configured")
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    variants = []
    for i in range(n):
        payload = {"file_b64": b64, "variant_index": i}
        res = call_api_json(ARCH_ENDPOINT, ARCH_API_KEY, payload)
        variants.append(res)
        time.sleep(0.3)
    return variants

def run_B_agents_sim(variants: List[dict], n=6) -> dict:
    # each B reviews a different variant and returns a score + suggested edits
    reviews = []
    for i in range(min(n, len(variants))):
        v = variants[i]
        score = 0.8  # simulated
        reviews.append({"reviewer": i, "variant_id": v.get("variant_id", i), "score": score, "notes": f"OK {i}", "plan": v.get("items")})
    # pick best by score and aggregate notes
    best = max(reviews, key=lambda x: x["score"])
    merged = {"merged_plan": best["plan"], "feedback": [r["notes"] for r in reviews], "confidence": best["score"]}
    return merged

def run_B_agents_api(variants: List[dict], n=6):
    if not ENG_ENDPOINT or not ENG_API_KEY:
        raise ValueError("ENG endpoint/key not configured")
    reviews = []
    for i in range(min(n, len(variants))):
        payload = {"variant": variants[i]}
        res = call_api_json(ENG_ENDPOINT, ENG_API_KEY, payload)
        reviews.append(res)
    # merging logic depends on API; assume API returns {"score", "plan", "notes"}
    best = max(reviews, key=lambda r: r.get("score", 0))
    merged = {"merged_plan": best.get("plan"), "feedback": [r.get("notes") for r in reviews], "confidence": best.get("score", 0)}
    return merged

def run_C_agent_sim(final_plan: dict, price_df: pd.DataFrame) -> Dict[str, Any]:
    # final_plan can be list of items
    items = pd.DataFrame(final_plan) if isinstance(final_plan, list) else pd.DataFrame(final_plan.get("items", []))
    if items.empty:
        return {"boq_tables": {}, "summary": "No items"}
    matched = match_price_local(items, price_df)
    boq = calculate_boq_tables(matched)
    return {"boq_tables": boq, "matched": matched.to_dict(orient="records")}

def run_C_agent_api(final_plan: dict):
    if not PRICE_ENDPOINT or not PRICE_API_KEY:
        raise ValueError("PRICE endpoint/key not configured")
    payload = {"plan": final_plan}
    return call_api_json(PRICE_ENDPOINT, PRICE_API_KEY, payload)

# -----------------------
# BOQ helpers
# -----------------------
def calculate_boq_tables(matched_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    df = matched_df.copy()
    # ensure numeric
    for col in ["qty","matched_unit_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["material_cost"] = df.apply(lambda r: (r.get("matched_unit_price") or 0) * r.get("qty",0), axis=1)
    df["labor_cost"] = df["material_cost"] * 0.10
    df["total_cost"] = df["material_cost"] + df["labor_cost"]
    table1 = df.copy()  # ของ + ค่าแรง
    table2 = df[["item_code","description","qty","unit","matched_unit_price","material_cost"]] if not df.empty else df
    table3 = df[["item_code","description","qty","unit","labor_cost"]] if not df.empty else df
    table4 = pd.DataFrame([{"supplier":"TBD","amount": table1["total_cost"].sum() if not table1.empty else 0}])
    return {"table1": table1, "table2": table2, "table3": table3, "table4": table4}

# -----------------------
# Streamlit UI & Orchestration
# -----------------------
st.set_page_config(page_title="BOQ 3-Agent Loop", layout="wide")
st.title("BOQ — 3-Agent Loop (A6 / B6 / C)")

# Sidebar config
with st.sidebar:
    st.header("Config")
    role = st.selectbox("ฉันทําหน้าที่เป็น", ["Operator", "A (Architect)", "B (Engineer)", "C (Cost)"])
    project_name = st.text_input("Project name", value="Demo Project")
    project_desc = st.text_area("Project description", value="BOQ generation via 3-agent loop")
    st.markdown("---")
    st.subheader("API & Mode")
    use_apis = st.checkbox("เชื่อมต่อกับ APIs จริง (ต้องตั้งค่า st.secrets/env)", value=False)
    st.write("ARCH endpoint/key present:", bool(ARCH_ENDPOINT and ARCH_API_KEY))
    st.write("ENG endpoint/key present:", bool(ENG_ENDPOINT and ENG_API_KEY))
    st.write("PRICE endpoint/key present:", bool(PRICE_ENDPOINT and PRICE_API_KEY))
    st.markdown("---")
    st.subheader("Files")
    use_github = st.checkbox("Load Price_List from GitHub raw (if not uploaded)", value=True)
    st.write("Local test PDF path:", TEST_PDF_PATH)

# Price list area
st.subheader("Price list")
col1, col2 = st.columns([3,1])
with col1:
    uploaded_price = st.file_uploader("อัปโหลด Price_List.csv (optional)", type=["csv"], key="price_csv")
    price_df = pd.DataFrame()
    if uploaded_price is not None:
        price_df = load_price_list_from_buffer(uploaded_price)
        if not price_df.empty:
            price_df.to_csv(PRICE_CSV_CACHE, index=False)
            st.success("เก็บ Price_List ชั่วคราวแล้ว")
    else:
        # try cache
        try:
            price_df = pd.read_csv(PRICE_CSV_CACHE)
        except Exception:
            price_df = pd.DataFrame()
        if price_df.empty and use_github:
            git_raw = "https://raw.githubusercontent.com/tanthaitanium21-dot/ai-engineer-app/main/Manuals/Price_List.csv"
            price_df = load_price_list_from_github(git_raw)
            if not price_df.empty:
                price_df.to_csv(PRICE_CSV_CACHE, index=False)
                st.success("โหลด Price_List.csv จาก GitHub สำเร็จ")
            else:
                st.info("ไม่พบ Price_List.csv ใน GitHub หรือโหลดล้มเหลว")
with col2:
    if st.button("ดู price sample"):
        st.write(price_df.head(10) if not price_df.empty else "ไม่มี price list")

st.markdown("---")

# Upload document (pdf/image) to start
st.subheader("Upload document (PDF / Image)")
uploaded_doc = st.file_uploader("อัปโหลด PDF หรือ รูปภาพ (.pdf/.png/.jpg/.jpeg/.pnp.png)", type=["pdf","png","jpg","jpeg","pnp","pnp.png"])

# Quick test file button
if st.button("ใช้ไฟล์ทดสอบ local (ถ้ามี)"):
    if os.path.exists(TEST_PDF_PATH):
        with open(TEST_PDF_PATH,"rb") as f:
            uploaded_doc_bytes = f.read()
        uploaded_doc = io.BytesIO(uploaded_doc_bytes)
        uploaded_doc.name = os.path.basename(TEST_PDF_PATH)
        st.success("โหลดไฟล์ทดสอบสำเร็จ")
    else:
        st.error("ไฟล์ทดสอบไม่พบที่ path")

# Operator controls: run automated loop
st.markdown("### Operator / Run Loop")
if st.button("Run automatic 3-Agent loop"):
    st.info("เริ่มรัน 3-agent loop...")
    # Load document bytes
    if uploaded_doc is None:
        st.error("กรุณาอัปโหลดไฟล์หรือเลือกไฟล์ทดสอบก่อน")
    else:
        # get bytes & filename
        try:
            # uploaded_doc may be file-like or BytesIO or UploadedFile
            if hasattr(uploaded_doc, "read"):
                file_bytes = uploaded_doc.read()
                fname = getattr(uploaded_doc, "name", "uploaded")
            else:
                # it's BytesIO
                file_bytes = uploaded_doc.getvalue()
                fname = getattr(uploaded_doc, "name", "uploaded")
        except Exception:
            st.error("อ่านไฟล์ไม่สำเร็จ")
            file_bytes = None
            fname = "uploaded"
        if file_bytes:
            project_id = str(uuid.uuid4())
            # Step A: run A agents (6 variants)
            try:
                if use_apis and ARCH_ENDPOINT and ARCH_API_KEY:
                    variants = run_A_agents_api(file_bytes, n=6)
                else:
                    variants = run_A_agents_sim(file_bytes, n=6)
            except Exception as e:
                st.error(f"A agents failed: {e}")
                variants = run_A_agents_sim(file_bytes, n=6)

            st.write(f"สร้าง variants: {len(variants)}")
            # Step B: run B agents to review & merge
            try:
                if use_apis and ENG_ENDPOINT and ENG_API_KEY:
                    b_result = run_B_agents_api(variants, n=6)
                else:
                    b_result = run_B_agents_sim(variants, n=6)
            except Exception as e:
                st.error(f"B agents failed: {e}")
                b_result = run_B_agents_sim(variants, n=6)

            st.write("B result confidence:", b_result.get("confidence"))
            # send merged plan back to A for revision (simulate)
            try:
                if use_apis and ARCH_ENDPOINT and ARCH_API_KEY:
                    revised = call_api_json(ARCH_ENDPOINT, ARCH_API_KEY, {"action":"revise","merged": b_result.get("merged_plan"), "feedback": b_result.get("feedback")})
                else:
                    # simulate revise: slightly normalize quantities
                    merged_items = b_result.get("merged_plan", [])
                    if isinstance(merged_items, list):
                        revised = {"items": merged_items}
                    else:
                        revised = {"items": merged_items}
            except Exception as e:
                st.warning(f"A revision failed (simulating): {e}")
                revised = {"items": b_result.get("merged_plan", [])}

            # final B review
            try:
                if use_apis and ENG_ENDPOINT and ENG_API_KEY:
                    final = call_api_json(ENG_ENDPOINT, ENG_API_KEY, {"action":"finalize","plan": revised})
                else:
                    final = {"final_plan": revised.get("items", revised)}
            except Exception as e:
                st.warning(f"Final B review failed (simulating): {e}")
                final = {"final_plan": revised.get("items", revised)}

            # D: generate scope (simple)
            scope = {"scope_notes": "Auto-generated scope from B", "project": project_name}

            # C: price matching and BOQ generation
            try:
                if use_apis and PRICE_ENDPOINT and PRICE_API_KEY:
                    # call external price agent (expect it to return structured prices)
                    price_res = call_api_json(PRICE_ENDPOINT, PRICE_API_KEY, {"plan": final.get("final_plan")})
                    # if API returns structured tables, convert to DataFrames
                    matched_df = pd.DataFrame(price_res.get("matched_items", []))
                else:
                    # local matching
                    final_items = final.get("final_plan")
                    if isinstance(final_items, dict) and "items" in final_items:
                        final_items = final_items["items"]
                    matched_df = pd.DataFrame(final_items if final_items else [])
                    if not matched_df.empty:
                        matched_df = match_price_local(matched_df, price_df)
            except Exception as e:
                st.error(f"C agent failed: {e}")
                matched_df = pd.DataFrame()

            if matched_df.empty:
                st.warning("ไม่มีรายการที่สามารถคำนวณราคาได้ — แสดงผลต้นฉบับเพื่อเช็ค")
                st.write(final.get("final_plan"))
            else:
                st.success("สร้าง BOQ สำเร็จ (preview)")
                st.dataframe(matched_df.head(50))

                # Prepare BOQ tables
                boq_tables = calculate_boq_tables(matched_df)
                # Save to Excel in-memory
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as writer:
                    boq_tables["table1"].to_excel(writer, sheet_name="ของ_ค่าของ+ค่าแรง", index=False)
                    boq_tables["table2"].to_excel(writer, sheet_name="ค่าของ", index=False)
                    boq_tables["table3"].to_excel(writer, sheet_name="ค่าแรง", index=False)
                    boq_tables["table4"].to_excel(writer, sheet_name="PO", index=False)
                out.seek(0)
                # save BOQ blob
                submission_id = save_submission(project_id, "C", fname, json.dumps({"source":"agent_loop"}))
                bid = save_boq_blob(project_id, submission_id, out.getvalue())
                st.success(f"บันทึก BOQ ใน DB (id: {bid})")
                st.download_button("ดาวน์โหลด BOQ (.xlsx)", data=out.getvalue(), file_name=f"BOQ_{project_name}.xlsx")

# Admin / debug
st.markdown("---")
with st.expander("Admin / Debug"):
    st.write("DB path:", DB_PATH)
    if st.button("ล้าง DB (demo)"):
        c = conn.cursor()
        c.execute("DELETE FROM submissions")
        c.execute("DELETE FROM projects")
        c.execute("DELETE FROM boqs")
        conn.commit()
        st.warning("ลบข้อมูลทั้งหมดแล้ว")
    c = conn.cursor()
    c.execute("SELECT id, project_id, submission_id, created_at FROM boqs ORDER BY created_at DESC LIMIT 10")
    rows = c.fetchall()
    st.write("Recent BOQ records:")
    st.dataframe(rows)

# End of file
