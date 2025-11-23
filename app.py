# app.py
# Full 3-Agent Loop (A6 → B6 → A revise → B finalize → C)
# Supports PDF & image inputs (.pdf, .png, .jpg, .jpeg, .pnp.png)
# Simulation mode if no external APIs configured. Use st.secrets for real APIs.

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

# Optional libs for better parsing/OCR
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
# Configuration / Paths
# -----------------------
DB_PATH = os.getenv("BOQ_APP_DB", "boq_app.db")
PRICE_CSV_CACHE = "price_list_cache.csv"

# IMPORTANT: default test PDF path from current session history — used as "file URL" test input
TEST_PDF_PATH = "/mnt/data/7dfdf93c-beb9-4abf-a1eb-7668cd324077.pdf"

# Helper to read secrets (do not hardcode keys)
def secret_get(key: str):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)

# API keys & endpoints (optional — set in st.secrets or env)
ARCH_API_KEY = secret_get("ARCH_API_KEY")
ARCH_ENDPOINT = secret_get("ARCH_ENDPOINT")
ENG_API_KEY = secret_get("ENG_API_KEY")
ENG_ENDPOINT = secret_get("ENG_ENDPOINT")
PRICE_API_KEY = secret_get("PRICE_API_KEY")
PRICE_ENDPOINT = secret_get("PRICE_ENDPOINT")

# GitHub raw price list (adjust if your repo path differs)
GITHUB_PRICE_RAW = "https://raw.githubusercontent.com/tanthaitanium21-dot/ai-engineer-app/main/Manuals/Price_List.csv"

# -----------------------
# Database (SQLite)
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
# Document parsing helpers
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
            pass
    # Fallback to pypdf if installed
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
        img = Image.open(io.BytesIO(b)).convert("RGB")
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
    """Extract rows (item_code, description, qty, unit) from bytes.
       If parsing fails, return DataFrame with raw_text for manual inspection."""
    lower = filename.lower()
    text = ""
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf_bytes(file_bytes)
    elif lower.endswith((".png", ".jpg", ".jpeg", ".pnp", ".pnp.png")):
        text = extract_text_from_image_bytes(file_bytes)
    else:
        # try pdf first
        text = extract_text_from_pdf_bytes(file_bytes)

    if not text:
        return pd.DataFrame({"raw_text":[f"(no extracted text) {filename}"]})

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows = []
    # pattern: optional code, description, qty, unit (Thai or Eng units)
    pattern = re.compile(r"^(?:(?P<code>[A-Za-z0-9\-\._/]+)\s+)?(?P<desc>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<unit>[A-Za-zก-๙/%\"\.]+)$")
    for ln in lines:
        m = pattern.match(ln)
        if m:
            code = m.group("code") or ""
            desc = m.group("desc").strip()
            qty = float(m.group("qty").replace(",", "."))
            unit = m.group("unit")
            rows.append({"item_code": code, "description": desc, "qty": qty, "unit": unit})
        else:
            # fallback: lines that end with qty unit
            m2 = re.search(r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+([A-Za-zก-๙/%\"\.]+)$", ln)
            if m2:
                desc = m2.group(1).strip()
                qty = float(m2.group(2).replace(",", "."))
                unit = m2.group(3)
                rows.append({"item_code": "", "description": desc, "qty": qty, "unit": unit})

    if rows:
        return pd.DataFrame(rows)
    # no structured rows found -> return first chunk of raw text for manual inspection
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
        r = requests.get(raw_url, timeout=15)
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
        token = desc.split()[0] if desc.split() else desc
        try:
            candidates = price_df[price_df["description"].str.lower().str.contains(re.escape(token), na=False)]
        except Exception:
            try:
                candidates = price_df[price_df["description"].str.lower().str.contains(re.escape(desc), na=False)]
            except Exception:
                candidates = pd.DataFrame()
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
# Simple BOQ calculations
# -----------------------
def calculate_boq_tables(matched_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    df = matched_df.copy()
    # Ensure numeric
    for col in ["qty","matched_unit_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df["material_cost"] = df.apply(lambda r: (r.get("matched_unit_price") or 0) * r.get("qty",0), axis=1)
    df["labor_cost"] = df["material_cost"] * 0.10
    df["total_cost"] = df["material_cost"] + df["labor_cost"]
    table1 = df.copy()  # ของ + ค่าแรง
    table2 = df[["item_code","description","qty","unit","matched_unit_price","material_cost"]] if not df.empty else df
    table3 = df[["item_code","description","qty","unit","labor_cost"]] if not df.empty else df
    table4 = pd.DataFrame([{"supplier":"TBD","amount": table1["total_cost"].sum() if not table1.empty else 0}])
    return {"table1": table1, "table2": table2, "table3": table3, "table4": table4}

# -----------------------
# API wrapper for JSON calls
# -----------------------
def call_api_json(endpoint: str, api_key: str, payload: dict, timeout=120) -> dict:
    if not endpoint or not api_key:
        raise ValueError("Missing endpoint or api_key for API call")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

# -----------------------
# Agent implementations (simulation and API modes)
# -----------------------
def run_A_agents_sim(file_bytes: bytes, n=6) -> List[dict]:
    base = parse_document_bytes(file_bytes, "uploaded")
    variants = []
    for i in range(n):
        if not base.empty and "qty" in base.columns:
            v = base.copy()
            # create small variation in qty to simulate different interpretations
            v["qty"] = v["qty"].apply(lambda q: max(1, q * (1.0 + (i-(n/2))/50.0)))
            variants.append({"variant_id": i, "items": v.to_dict(orient="records"), "notes": f"Sim variant {i}"})
        else:
            variants.append({"variant_id": i, "items": [], "notes": f"Sim variant {i}"})
    return variants

def run_A_agents_api(file_bytes: bytes, n=6) -> List[dict]:
    if not ARCH_ENDPOINT or not ARCH_API_KEY:
        raise ValueError("ARCH endpoint/key not configured")
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    variants = []
    for i in range(n):
        payload = {"file_b64": b64, "variant_index": i}
        res = call_api_json(ARCH_ENDPOINT, ARCH_API_KEY, payload)
        variants.append(res)
        time.sleep(0.2)
    return variants

def run_B_agents_sim(variants: List[dict], n=6) -> dict:
    reviews = []
    for i in range(min(n, len(variants))):
        v = variants[i]
        # naive scoring: more items => slightly higher score
        score = 0.6 + min(0.4, 0.01 * (len(v.get("items", []))))
        reviews.append({"reviewer": i, "variant_id": v.get("variant_id", i), "score": round(score, 2), "notes": f"Checked by B{i}", "plan": v.get("items")})
    best = max(reviews, key=lambda x: x["score"])
    merged = {"merged_plan": best["plan"], "feedback": [r["notes"] for r in reviews], "confidence": best["score"]}
    return merged

def run_B_agents_api(variants: List[dict], n=6) -> dict:
    if not ENG_ENDPOINT or not ENG_API_KEY:
        raise ValueError("ENG endpoint/key not configured")
    reviews = []
    for i in range(min(n, len(variants))):
        payload = {"variant": variants[i]}
        res = call_api_json(ENG_ENDPOINT, ENG_API_KEY, payload)
        reviews.append(res)
    # assume API returns score, plan, notes
    best = max(reviews, key=lambda r: r.get("score", 0))
    merged = {"merged_plan": best.get("plan"), "feedback": [r.get("notes") for r in reviews], "confidence": best.get("score", 0)}
    return merged

def run_C_agent_sim(final_plan: dict, price_df: pd.DataFrame) -> Dict[str, Any]:
    # final_plan can be list of item dicts or dict with "items"
    items = []
    if isinstance(final_plan, list):
        items = final_plan
    elif isinstance(final_plan, dict) and "items" in final_plan:
        items = final_plan["items"]
    elif isinstance(final_plan, dict) and "final_plan" in final_plan:
        fp = final_plan["final_plan"]
        items = fp if isinstance(fp, list) else fp.get("items", [])
    matched_df = pd.DataFrame(items if items else [])
    if not matched_df.empty:
        matched_df = match_price_local(matched_df, price_df)
    boq_tables = calculate_boq_tables(matched_df) if not matched_df.empty else {"table1": pd.DataFrame(), "table2": pd.DataFrame(), "table3": pd.DataFrame(), "table4": pd.DataFrame()}
    return {"boq_tables": boq_tables, "matched": matched_df}

def run_C_agent_api(final_plan: dict) -> Dict[str, Any]:
    if not PRICE_ENDPOINT or not PRICE_API_KEY:
        raise ValueError("PRICE endpoint/key not configured")
    payload = {"plan": final_plan}
    res = call_api_json(PRICE_ENDPOINT, PRICE_API_KEY, payload)
    # Expect API to return matched items or BOQ tables
    return res

# -----------------------
# Streamlit UI & orchestration
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
    st.subheader("API Mode")
    use_apis = st.checkbox("ใช้ API จริง (ต้องตั้งค่า st.secrets/env)", value=False)
    st.write("ARCH endpoint/key present:", bool(ARCH_ENDPOINT and ARCH_API_KEY))
    st.write("ENG endpoint/key present:", bool(ENG_ENDPOINT and ENG_API_KEY))
    st.write("PRICE endpoint/key present:", bool(PRICE_ENDPOINT and PRICE_API_KEY))
    st.markdown("---")
    st.subheader("Files")
    use_github_price = st.checkbox("Load Price_List.csv from GitHub raw if not uploaded", value=True)
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
        try:
            price_df = pd.read_csv(PRICE_CSV_CACHE)
        except Exception:
            price_df = pd.DataFrame()
        if price_df.empty and use_github_price:
            price_df = load_price_list_from_github(GITHUB_PRICE_RAW)
            if not price_df.empty:
                price_df.to_csv(PRICE_CSV_CACHE, index=False)
                st.success("โหลด Price_List.csv จาก GitHub สำเร็จ")
            else:
                st.info("ไม่พบ Price_List.csv ใน GitHub หรือโหลดล้มเหลว")
with col2:
    if st.button("ดู price sample"):
        st.write(price_df.head(10) if not price_df.empty else "ไม่มี price list")

st.markdown("---")

# Document upload
st.subheader("Upload document (PDF / Image)")
uploaded_doc = st.file_uploader("อัปโหลด PDF หรือ รูปภาพ (.pdf/.png/.jpg/.jpeg/.pnp.png)", type=["pdf","png","jpg","jpeg","pnp","pnp.png"])

# Quick test: load local test PDF (from session history path)
if st.button("ใช้ไฟล์ทดสอบ local (ถ้ามี)"):
    if os.path.exists(TEST_PDF_PATH):
        with open(TEST_PDF_PATH, "rb") as f:
            data = f.read()
        uploaded_doc = io.BytesIO(data)
        uploaded_doc.name = os.path.basename(TEST_PDF_PATH)
        st.success("โหลดไฟล์ทดสอบสำเร็จ")
    else:
        st.error("ไฟล์ทดสอบไม่พบที่ path")

# Operator run loop
st.markdown("### Operator: Run full automated loop")
if st.button("Run automatic 3-Agent loop"):
    st.info("เริ่มรัน 3-agent loop ...")
    # Check uploaded doc
    if uploaded_doc is None:
        st.error("กรุณาอัปโหลดไฟล์หรือเลือกไฟล์ทดสอบก่อน")
    else:
        # Read bytes and filename robustly
        try:
            if hasattr(uploaded_doc, "read"):
                file_bytes = uploaded_doc.read()
                fname = getattr(uploaded_doc, "name", "uploaded")
            elif isinstance(uploaded_doc, bytes):
                file_bytes = uploaded_doc
                fname = "uploaded"
            else:
                # BytesIO-like
                file_bytes = uploaded_doc.getvalue()
                fname = getattr(uploaded_doc, "name", "uploaded")
        except Exception as e:
            st.error(f"อ่านไฟล์ไม่สำเร็จ: {e}")
            file_bytes = None
            fname = "uploaded"
        if not file_bytes:
            st.error("ไม่มีข้อมูลไฟล์ให้อ่าน")
        else:
            project_id = str(uuid.uuid4())
            # Step A: run A agents (6 variants)
            try:
                if use_apis and ARCH_ENDPOINT and ARCH_API_KEY:
                    variants = run_A_agents_api(file_bytes, n=6)
                else:
                    variants = run_A_agents_sim(file_bytes, n=6)
            except Exception as e:
                st.warning(f"A agents error, switching to simulation: {e}")
                variants = run_A_agents_sim(file_bytes, n=6)
            st.write(f"A variants created: {len(variants)}")

            # Show preview of one variant
            if variants and isinstance(variants, list):
                st.subheader("ตัวอย่าง Variant จาก A (variant 0)")
                st.write(variants[0])

            # Step B: review & merge
            try:
                if use_apis and ENG_ENDPOINT and ENG_API_KEY:
                    b_result = run_B_agents_api(variants, n=6)
                else:
                    b_result = run_B_agents_sim(variants, n=6)
            except Exception as e:
                st.warning(f"B agents error, sim fallback: {e}")
                b_result = run_B_agents_sim(variants, n=6)

            st.write("B result:", {"confidence": b_result.get("confidence"), "feedback_sample": b_result.get("feedback")[:3]})
            # send merged plan back to A for revision (simulate or API)
            try:
                if use_apis and ARCH_ENDPOINT and ARCH_API_KEY:
                    revised = call_api_json(ARCH_ENDPOINT, ARCH_API_KEY, {"action": "revise", "merged": b_result.get("merged_plan"), "feedback": b_result.get("feedback")})
                else:
                    # simulate revise: round quantities and normalize
                    merged_items = b_result.get("merged_plan", [])
                    if isinstance(merged_items, list):
                        for it in merged_items:
                            if "qty" in it:
                                it["qty"] = round(float(it["qty"]), 2)
                    revised = {"items": merged_items}
            except Exception as e:
                st.warning(f"A revision failed (simulate): {e}")
                revised = {"items": b_result.get("merged_plan", [])}

            # final B validation
            try:
                if use_apis and ENG_ENDPOINT and ENG_API_KEY:
                    final = call_api_json(ENG_ENDPOINT, ENG_API_KEY, {"action": "finalize", "plan": revised})
                else:
                    final = {"final_plan": revised.get("items", revised)}
            except Exception as e:
                st.warning(f"Final B validation failed (simulate): {e}")
                final = {"final_plan": revised.get("items", revised)}

            st.write("Final plan preview (sample):", final.get("final_plan")[:5] if isinstance(final.get("final_plan"), list) else final.get("final_plan"))

            # D: simple scope generation
            scope = {"scope_notes": "Auto-generated scope from B", "project": project_name}

            # Step C: price matching & BOQ generation
            try:
                if use_apis and PRICE_ENDPOINT and PRICE_API_KEY:
                    price_res = run_C_agent_api(final)
                    # expected price_res contains structured matched items or tables
                    matched_df = pd.DataFrame(price_res.get("matched_items", []))
                    boq_tables = price_res.get("boq_tables", {})
                else:
                    # local match using price_df loaded earlier
                    final_items = final.get("final_plan")
                    if isinstance(final_items, dict) and "items" in final_items:
                        final_items = final_items["items"]
                    matched_df = pd.DataFrame(final_items if final_items else [])
                    if not matched_df.empty:
                        matched_df = match_price_local(matched_df, price_df)
                    boq_tables = calculate_boq_tables(matched_df) if not matched_df.empty else {"table1": pd.DataFrame(), "table2": pd.DataFrame(), "table3": pd.DataFrame(), "table4": pd.DataFrame()}
            except Exception as e:
                st.error(f"C agent failed: {e}")
                matched_df = pd.DataFrame()
                boq_tables = {"table1": pd.DataFrame(), "table2": pd.DataFrame(), "table3": pd.DataFrame(), "table4": pd.DataFrame()}

            if matched_df.empty:
                st.warning("ไม่มีรายการที่สามารถคำนวณราคาได้ — กรุณาตรวจสอบผลลัพธ์จาก Agent A/B")
                # show raw final plan for manual inspection
                st.write("Final plan (raw):", final.get("final_plan"))
            else:
                st.success("สร้าง BOQ สำเร็จ (preview)")
                st.dataframe(matched_df.head(50))

                # Prepare Excel to download
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as writer:
                    boq_tables["table1"].to_excel(writer, sheet_name="ของ_ค่าของ+ค่าแรง", index=False)
                    boq_tables["table2"].to_excel(writer, sheet_name="ค่าของ", index=False)
                    boq_tables["table3"].to_excel(writer, sheet_name="ค่าแรง", index=False)
                    boq_tables["table4"].to_excel(writer, sheet_name="PO", index=False)
                out.seek(0)

                # Save to DB
                submission_id = save_submission(project_id, "C", getattr(uploaded_doc, "name", "uploaded"), json.dumps({"source": "agent_loop"}))
                bid = save_boq_blob(project_id, submission_id, out.getvalue())
                st.success(f"บันทึก BOQ ในฐานข้อมูล (id: {bid})")
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
