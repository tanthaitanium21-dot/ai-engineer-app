"""
app.py
Streamlit BOQ App (merged) — includes real PDF parsing (pdfplumber) and GitHub-loading option.
"""

import os
import io
import uuid
import sqlite3
import datetime
import re
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st

# Optional libs: pdfplumber for text extraction, pytesseract for OCR fallback (if installed)
try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from PIL import Image
    import pytesseract
except Exception:
    pytesseract = None

# -----------------------
# Config & Helpers
# -----------------------

DB_PATH = os.getenv("BOQ_APP_DB", "boq_app.db")
PRICE_CSV_CACHE = "price_list_cache.csv"

# API keys -- use streamlit secrets or environment variables (DO NOT hardcode)
# Example access: st.secrets["ARCH_API"] or os.getenv("ARCH_API_KEY")
def get_secret(key: str):
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key)

ARCH_API_KEY = get_secret("ARCHITECT_API")
ENG_API_KEY = get_secret("ENGINEER_API")
PRICE_API_KEY = get_secret("PRICE_API")

# Test PDF path (the file you uploaded; you said it's not A/B/C)
TEST_PDF_PATH = "/mnt/data/7dfdf93c-beb9-4abf-a1eb-7668cd324077.pdf"

# Simple DB initialization
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            created_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            role TEXT,
            filename TEXT,
            metadata TEXT,
            version INTEGER,
            created_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS boqs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            submission_id TEXT,
            data_blob BLOB,
            created_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS price_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            description TEXT,
            unit TEXT,
            unit_price REAL,
            source TEXT
        )
        """
    )
    conn.commit()
    return conn

conn = init_db()

# -----------------------
# PDF parsing (real)
# -----------------------

def extract_text_with_pdfplumber_bytes(file_bytes: bytes) -> str:
    if pdfplumber is None:
        return ""
    text_all = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_all += page_text + "\n"
    except Exception:
        return ""
    return text_all

def extract_text_with_ocr_bytes(file_bytes: bytes) -> str:
    # OCR fallback: convert pages to images and run pytesseract (requires poppler & pillow & pytesseract)
    if pytesseract is None:
        return ""
    try:
        from pdf2image import convert_from_bytes
    except Exception:
        return ""
    text_all = ""
    try:
        pages = convert_from_bytes(file_bytes)
        for img in pages:
            text_all += pytesseract.image_to_string(img, lang='eng+tha') + "\n"
    except Exception:
        return ""
    return text_all

def parse_pdf_real(file_bytes: bytes) -> pd.DataFrame:
    """
    Read PDF bytes and attempt to extract tabular item lines into a DataFrame.
    Strategy:
      1) Try pdfplumber text extraction
      2) If no text, try OCR (if available)
      3) Parse lines with regex to find rows like: code description qty unit
    Returns DataFrame with columns: item_code, description, qty, unit
    """
    text_all = extract_text_with_pdfplumber_bytes(file_bytes)
    if not text_all:
        text_all = extract_text_with_ocr_bytes(file_bytes)

    if not text_all:
        # nothing extracted
        st.warning("ไม่สามารถสกัดข้อความจาก PDF ได้ (ลองใช้ไฟล์อื่นหรือติดตั้ง OCR)")
        return pd.DataFrame(columns=["item_code","description","qty","unit"])

    # normalize whitespace
    lines = [ln.strip() for ln in text_all.splitlines() if ln.strip()]

    # Heuristic regex patterns (may need tuning per document style)
    patterns = [
        # e.g. EL-001  สายไฟ THW 2.5 mm2  100  m
        r"^([A-Za-z0-9\-\._/]+)\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+([A-Za-zก-๙/%\"\.]+)$",
        # e.g. 1. สายไฟ THW 2.5 mm2 100 m
        r"^\d+\.\s*(.+?)\s+(\d+(?:[.,]\d+)?)\s+([A-Za-zก-๙/%\"\.]+)$"
    ]

    rows = []
    for line in lines:
        matched = False
        for pat in patterns:
            m = re.match(pat, line)
            if m:
                if len(m.groups()) == 4:
                    code = m.group(1)
                    desc = m.group(2)
                    qty = float(str(m.group(3)).replace(",", "."))
                    unit = m.group(4)
                else:
                    # fallback grouping
                    code = ""
                    desc = m.group(1)
                    qty = float(str(m.group(2)).replace(",", "."))
                    unit = m.group(3)
                rows.append({
                    "item_code": code,
                    "description": desc,
                    "qty": qty,
                    "unit": unit
                })
                matched = True
                break
        # if not matched, try to find lines containing a qty and unit at end
        if not matched:
            m2 = re.search(r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+([A-Za-zก-๙/%\"\.]+)$", line)
            if m2:
                desc = m2.group(1)
                qty = float(str(m2.group(2)).replace(",", "."))
                unit = m2.group(3)
                rows.append({
                    "item_code": "",
                    "description": desc,
                    "qty": qty,
                    "unit": unit
                })

    if not rows:
        st.info("ไม่พบแถวที่ตรงกับรูปแบบอัตโนมัติ — ระบบจะแสดงข้อความเต็มของ PDF เพื่อให้ตรวจด้วยมือ")
        return pd.DataFrame({"raw_text":[text_all]})

    return pd.DataFrame(rows)

# -----------------------
# Parsing / Matching stubs (kept for UI)
# -----------------------

def parse_pdf_stub(file_bytes: bytes) -> pd.DataFrame:
    """Legacy stub kept for fallback/demo"""
    data = [
        {"item_code": "EL-001", "description": "สายไฟ THW 2.5 mm2", "qty": 100, "unit": "m"},
        {"item_code": "EL-002", "description": "ท่อ EMT 1/2\"", "qty": 20, "unit": "m"},
        {"item_code": "EL-003", "description": "โคมไฟ LED 18W", "qty": 10, "unit": "ea"},
    ]
    return pd.DataFrame(data)

def load_price_list_from_csv(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, encoding='utf-8', errors='ignore')
    except Exception:
        df = pd.DataFrame(columns=["code", "description", "unit", "unit_price", "source"])
    return df

def match_price_stub(items_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    out = items_df.copy()
    out["matched_code"] = None
    out["matched_unit_price"] = None
    out["match_confidence"] = 0.0

    if price_df is None or price_df.empty:
        out["match_confidence"] = 0.0
        return out

    for idx, row in out.iterrows():
        desc = str(row.get("description","")).lower()
        # Try approximate substring match
        try:
            matched = price_df[price_df["description"].str.lower().str.contains(desc.split()[0])]
        except Exception:
            matched = price_df[price_df["description"].str.lower().str.contains(desc)] if not price_df.empty else pd.DataFrame()
        if not matched.empty:
            out.at[idx, "matched_code"] = matched.iloc[0]["code"]
            out.at[idx, "matched_unit_price"] = float(matched.iloc[0]["unit_price"]) if pd.notna(matched.iloc[0]["unit_price"]) else None
            out.at[idx, "match_confidence"] = 0.75
        else:
            out.at[idx, "match_confidence"] = 0.0
    return out

def calculate_boq(items_df: pd.DataFrame) -> pd.DataFrame:
    df = items_df.copy()
    df["material_cost"] = df.apply(lambda r: (r.get("matched_unit_price") or 0) * r["qty"], axis=1)
    df["labor_cost"] = df["material_cost"] * 0.10
    df["total_cost"] = df["material_cost"] + df["labor_cost"]
    return df

# -----------------------
# Persistence helpers
# -----------------------

def save_submission(project_id: str, role: str, filename: str, metadata: str) -> str:
    sid = str(uuid.uuid4())
    version = get_latest_version(project_id) + 1
    now = datetime.datetime.utcnow().isoformat()
    c = conn.cursor()
    c.execute(
        "INSERT INTO submissions (id, project_id, role, filename, metadata, version, created_at) VALUES (?,?,?,?,?,?,?)",
        (sid, project_id, role, filename, metadata, version, now),
    )
    conn.commit()
    return sid

def get_latest_version(project_id: str) -> int:
    c = conn.cursor()
    c.execute("SELECT MAX(version) FROM submissions WHERE project_id = ?", (project_id,))
    r = c.fetchone()
    return int(r[0]) if r and r[0] is not None else 0

def save_boq_blob(project_id: str, submission_id: str, excel_bytes: bytes) -> str:
    bid = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    c = conn.cursor()
    c.execute(
        "INSERT INTO boqs (id, project_id, submission_id, data_blob, created_at) VALUES (?,?,?,?,?)",
        (bid, project_id, submission_id, sqlite3.Binary(excel_bytes), now),
    )
    conn.commit()
    return bid

# -----------------------
# Streamlit UI
# -----------------------

st.set_page_config(page_title="BOQ A-B-C-D Workflow", layout="wide")
st.title("BOQ — A/B/C/D Workflow (Merged)")

# Sidebar: Project and role
with st.sidebar:
    st.header("Config")
    role = st.selectbox("ฉันทําหน้าที่เป็น", ["A (Architect)", "B (Engineer)", "C (Cost)", "D (Scope)"])
    project_name = st.text_input("Project name", value="ตัวอย่างโปรเจกต์")
    project_desc = st.text_area("Project description", value="คำอธิบายสั้น ๆ ของโปรเจกต์")

    st.markdown("---")
    st.subheader("ไฟล์สมอง / Price list")
    use_github_files = st.checkbox("ใช้ไฟล์จาก GitHub (A/B/C) ถ้ามี", value=True)
    st.write("Test PDF (local):", TEST_PDF_PATH)
    if st.button("สร้าง/บันทึก project"):
        pid = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        c = conn.cursor()
        c.execute("INSERT INTO projects (id, name, description, created_at) VALUES (?,?,?,?)", (pid, project_name, project_desc, now))
        conn.commit()
        st.success("สร้าง project แล้ว (ID: %s)" % pid)

# Load price list from uploaded CSV or cache or GitHub raw
st.subheader("Price list (for matching)")
col1, col2 = st.columns([3,1])
with col1:
    uploaded_price = st.file_uploader("อัปโหลด Price_List.csv (optional)", type=["csv"] , key='price_csv')
    if uploaded_price is not None:
        price_df = pd.read_csv(uploaded_price, encoding='utf-8', errors='ignore')
        price_df.to_csv(PRICE_CSV_CACHE, index=False)
        st.success("อัปโหลดและเก็บ price list ชั่วคราวเรียบร้อย")
    else:
        # try cache
        price_df = load_price_list_from_csv(PRICE_CSV_CACHE)
        if price_df.empty and use_github_files:
            # try to load from GitHub (raw)
            GITHUB_BASE = "https://raw.githubusercontent.com/tanthaitanium21-dot/ai-engineer-app/main/Manuals/"
            PRICE_LIST_URL = GITHUB_BASE + "Price_List.csv"
            try:
                price_df = pd.read_csv(PRICE_LIST_URL, encoding='utf-8', errors='ignore')
                st.success("โหลด Price_List.csv จาก GitHub สำเร็จ")
                price_df.to_csv(PRICE_CSV_CACHE, index=False)
            except Exception as e:
                st.warning(f"โหลด Price_List.csv จาก GitHub ไม่สำเร็จ: {e}")
        if price_df.empty:
            st.info(f"ไม่มี price list cache — อัปโหลดไฟล์หรือวางไฟล์ไว้ที่ {PRICE_CSV_CACHE}" )
with col2:
    if st.button("ดู price sample"):
        st.write(price_df.head(10) if price_df is not None else "ไม่มี price list")

st.markdown("---")

# Main area per role
if role.startswith("A"):
    st.header("หน้า A — สถาปนิก: ส่งแบบ (Upload)")
    file = st.file_uploader("อัปโหลดไฟล์แบบ (PDF/ZIP)", type=["pdf","zip","dwg"], key='a_upload')
    notes = st.text_area("หมายเหตุถึงทีม B")
    if st.button("ส่งแบบให้ B") and file is not None:
        raw = file.read()
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        fname = f"{uuid.uuid4()}_{file.name}"
        path = os.path.join(uploads_dir, fname)
        with open(path, "wb") as f:
            f.write(raw)
        pid = "demo-project"
        sid = save_submission(pid, "A", fname, notes)
        st.success(f"ส่งแบบเรียบร้อย (submission id: {sid})")
        st.info("ระบบจะรัน parser จริงและสร้างตารางตัวอย่างให้ B ตรวจ")
        parsed = parse_pdf_real(raw)
        st.dataframe(parsed)

    # Quick test load from local TEST_PDF_PATH
    st.markdown("### ทดสอบ: โหลด PDF ตัวอย่างจากระบบ (local)")
    if st.button("โหลด PDF ตัวอย่าง (local)"):
        if os.path.exists(TEST_PDF_PATH):
            with open(TEST_PDF_PATH, "rb") as f:
                raw = f.read()
            parsed = parse_pdf_real(raw)
            st.subheader("ผลการ parse จากไฟล์ทดสอบ")
            st.dataframe(parsed)
        else:
            st.error("ไม่พบไฟล์ทดสอบที่ path นั้น")

elif role.startswith("B"):
    st.header("หน้า B — วิศวกร: ตรวจแบบ & สรุป")
    st.info("สำหรับเดโม: โหลด submissions ล่าสุดจาก DB และเลือกเพื่อตรวจ")
    c = conn.cursor()
    c.execute("SELECT id, project_id, role, filename, metadata, version, created_at FROM submissions ORDER BY created_at DESC LIMIT 20")
    subs = c.fetchall()
    if not subs:
        st.write("ยังไม่มี submission — ขอให้ A ส่งแบบก่อน")
    else:
        df_subs = pd.DataFrame(subs, columns=["id","project_id","role","filename","metadata","version","created_at"])
        st.dataframe(df_subs)
        chosen = st.text_input("เลือก submission id ที่จะตรวจ")
        if st.button("โหลด submission") and chosen:
            row = df_subs[df_subs["id"]==chosen]
            if row.empty:
                st.error("ไม่พบ submission id")
            else:
                fname = row.iloc[0]["filename"]
                path = os.path.join("uploads", fname)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        raw = f.read()
                    parsed = parse_pdf_real(raw)
                    st.subheader("ผลการ parse (จริง)")
                    st.dataframe(parsed)
                    if st.button("สรุปแบบและส่งกลับให้ A (request changes)"):
                        st.success("ส่งคำขอกลับให้ A เรียบร้อย — (demo)")

elif role.startswith("D"):
    st.header("หน้า D — ส่งรายละเอียดงานให้ C")
    st.write("ป้อนรายละเอียดงาน (scope) ที่ C จะใช้คำนวณ")
    scope_text = st.text_area("รายละเอียดงาน (Scope)")
    if st.button("ส่งให้ C") and scope_text:
        sid = save_submission("demo-project", "D", "scope_text.txt", scope_text)
        st.success(f"ส่ง scope ให้ C แล้ว (submission id: {sid})")

elif role.startswith("C"):
    st.header("หน้า C — สรุปราคา & สร้าง BOQ")
    st.info("โหลดแบบสุดท้ายจาก B, ตรวจแม็ปรายการกับ price list แล้วสร้าง BOQ 4 ตาราง")
    uploaded = st.file_uploader("(ทางเลือก) อัปโหลด PDF แบบถ้าต้องการทดสอบ parser", type=["pdf"], key='c_upload')
    if uploaded is not None:
        raw = uploaded.read()
        items = parse_pdf_real(raw)
        st.subheader("รายการที่ดึงได้ (parsed)")
        st.dataframe(items)
        matched = match_price_stub(items, price_df if 'price_df' in locals() else pd.DataFrame())
        st.subheader("หลังแม็ปราคา (candidate)")
        st.dataframe(matched)

        # Allow manual adjustments
        st.markdown("**ปรับราคา / เลือกรายการที่แม็ป**")
        editable = matched.copy()
        for i in editable.index:
            col1, col2 = st.columns([2,1])
            with col1:
                editable.at[i, "matched_unit_price"] = st.number_input(f"ราคา: {editable.at[i,'description']}", value=float(editable.at[i,'matched_unit_price'] or 0.0), key=f"price_{i}")
            with col2:
                editable.at[i, "qty"] = st.number_input(f"ปริมาณ: {editable.at[i,'description']}", value=float(editable.at[i,'qty']), key=f"qty_{i}")

        boq_df = calculate_boq(editable)
        st.subheader("BOQ preview — ตาราง 1: ของ+ค่าแรง")
        st.dataframe(boq_df)

        # Create separate tables
        table_material_plus_labor = boq_df.copy()
        table_material = boq_df[["item_code","description","qty","unit","matched_unit_price","material_cost"]]
        table_labor = boq_df[["item_code","description","qty","unit","labor_cost"]]
        table_po = pd.DataFrame([{"supplier":"TBD","amount": table_material_plus_labor["total_cost"].sum()}])

        # Export to Excel in-memory
        to_download = io.BytesIO()
        with pd.ExcelWriter(to_download, engine="openpyxl") as writer:
            table_material_plus_labor.to_excel(writer, sheet_name="ของ_ค่าของ+ค่าแรง", index=False)
            table_material.to_excel(writer, sheet_name="ค่าของ", index=False)
            table_labor.to_excel(writer, sheet_name="ค่าแรง", index=False)
            table_po.to_excel(writer, sheet_name="PO", index=False)
        to_download.seek(0)

        if st.button("บันทึก BOQ และสรุปเป็นไฟล์ Excel"):
            sid = save_submission("demo-project", "C", uploaded.name if uploaded else "generated", "BOQ generated by C")
            bid = save_boq_blob("demo-project", sid, to_download.getvalue())
            st.success(f"บันทึก BOQ เรียบร้อย (boq id: {bid})")
            st.download_button("ดาวน์โหลดไฟล์ BOQ (.xlsx)", data=to_download.getvalue(), file_name=f"BOQ_{project_name}.xlsx")

# -----------------------
# Admin / Debug area
# -----------------------

st.markdown("---")
with st.expander("Admin / Debug"):
    st.write("DB path: ", DB_PATH)
    if st.button("ล้าง DB ตัวอย่าง (danger)"):
        c = conn.cursor()
        c.execute("DELETE FROM submissions")
        c.execute("DELETE FROM projects")
        c.execute("DELETE FROM boqs")
        conn.commit()
        st.warning("ลบข้อมูลทั้งหมดแล้ว — ใช้ใน demo เท่านั้น")
    st.write("Recent BOQ records:")
    c = conn.cursor()
    c.execute("SELECT id, project_id, submission_id, created_at FROM boqs ORDER BY created_at DESC LIMIT 10")
    rows = c.fetchall()
    st.dataframe(rows)

# End of app
