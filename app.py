"""
app.py
Streamlit skeleton app for the A-B-C-D BOQ workflow described.
- This is a working starter app (skeleton) that demonstrates uploads, simple parsing stub,
  price matching stub, BOQ generation, versioned submissions (SQLite) and Excel export.

How to run:
1. Create virtualenv and `pip install -r requirements.txt` (requirements suggested below)
2. Set environment variables for sensitive keys (if any). Do NOT hardcode API keys here.
3. `streamlit run app.py`

Suggested requirements (not included here):
streamlit, pandas, sqlalchemy, pdfplumber, openpyxl, rapidfuzz

"""

import os
import io
import uuid
import sqlite3
import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st

# -----------------------
# Config & Helpers
# -----------------------

DB_PATH = os.getenv("BOQ_APP_DB", "boq_app.db")
PRICE_CSV_CACHE = "price_list_cache.csv"

# API keys -- pulled from env vars (do NOT commit keys)
ARCH_API_KEY = os.getenv("ARCH_API_KEY")
ENG_API_KEY = os.getenv("ENG_API_KEY")
PRICE_API_KEY = os.getenv("PRICE_API_KEY")

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
# Parsing / Matching stubs
# -----------------------

def parse_pdf_stub(file_bytes: bytes) -> pd.DataFrame:
    """Placeholder parser: in real system use pdfplumber / camelot / OCR fallback.
    Returns a dataframe with columns: item_code, description, qty, unit
    """
    # For demo, return an example table
    data = [
        {"item_code": "EL-001", "description": "สายไฟ THW 2.5 mm2", "qty": 100, "unit": "m"},
        {"item_code": "EL-002", "description": "ท่อ EMT 1/2\"", "qty": 20, "unit": "m"},
        {"item_code": "EL-003", "description": "โคมไฟ LED 18W", "qty": 10, "unit": "ea"},
    ]
    return pd.DataFrame(data)


def load_price_list_from_csv(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception:
        # create empty
        df = pd.DataFrame(columns=["code", "description", "unit", "unit_price", "source"])
    return df


def match_price_stub(items_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """Very simple exact-match/mapping. Replace with fuzzy matching (rapidfuzz) in production."""
    out = items_df.copy()
    out["matched_code"] = None
    out["matched_unit_price"] = None
    out["match_confidence"] = 0.0

    for idx, row in out.iterrows():
        desc = str(row["description"]).lower()
        # Try exact substring match in price list descriptions
        matched = price_df[price_df["description"].str.lower().str.contains(desc.split()[0])]
        if not matched.empty:
            # pick the first
            out.at[idx, "matched_code"] = matched.iloc[0]["code"]
            out.at[idx, "matched_unit_price"] = float(matched.iloc[0]["unit_price"]) if pd.notna(matched.iloc[0]["unit_price"]) else None
            out.at[idx, "match_confidence"] = 0.75
        else:
            out.at[idx, "match_confidence"] = 0.0
    return out


def calculate_boq(items_df: pd.DataFrame) -> pd.DataFrame:
    df = items_df.copy()
    df["material_cost"] = df.apply(lambda r: (r.get("matched_unit_price") or 0) * r["qty"], axis=1)
    # Simple labor cost assumption (e.g., 10% of material cost per item) -- replace with real model
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
st.title("BOQ — A/B/C/D Workflow (Skeleton)")

# Sidebar: Project and role
with st.sidebar:
    st.header("Config")
    role = st.selectbox("ฉันทําหน้าที่เป็น", ["A (Architect)", "B (Engineer)", "C (Cost)", "D (Scope)"])
    project_name = st.text_input("Project name", value="ตัวอย่างโปรเจกต์")
    project_desc = st.text_area("Project description", value="คำอธิบายสั้น ๆ ของโปรเจกต์")
    if st.button("สร้าง/บันทึก project"):
        pid = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        c = conn.cursor()
        c.execute("INSERT INTO projects (id, name, description, created_at) VALUES (?,?,?,?)", (pid, project_name, project_desc, now))
        conn.commit()
        st.success("สร้าง project แล้ว (ID: %s)" % pid)

# Load price list from uploaded CSV or cache
st.subheader("Price list (for matching)")
col1, col2 = st.columns([3,1])
with col1:
    uploaded_price = st.file_uploader("อัปโหลด Price_List.csv (optional)", type=["csv"] , key='price_csv')
    if uploaded_price is not None:
        price_df = pd.read_csv(uploaded_price)
        price_df.to_csv(PRICE_CSV_CACHE, index=False)
        st.success("อัปโหลดและเก็บ price list ชั่วคราวเรียบร้อย")
    else:
        price_df = load_price_list_from_csv(PRICE_CSV_CACHE)
        if price_df.empty:
            st.info("ไม่มี price list cache — อัปโหลดไฟล์หรือวางไฟล์ไว้ที่ {PRICE_CSV_CACHE}" )
with col2:
    if st.button("ดู price sample"):
        st.write(price_df.head(10))

st.markdown("---")

# Main area per role
if role.startswith("A"):
    st.header("หน้า A — สถาปนิก: ส่งแบบ (Upload)")
    file = st.file_uploader("อัปโหลดไฟล์แบบ (PDF/ZIP)", type=["pdf","zip","dwg"], key='a_upload')
    notes = st.text_area("หมายเหตุถึงทีม B")
    if st.button("ส่งแบบให้ B") and file is not None:
        # parse (stub) and save submission
        raw = file.read()
        # save file in uploads/ with safe name
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        fname = f"{uuid.uuid4()}_{file.name}"
        path = os.path.join(uploads_dir, fname)
        with open(path, "wb") as f:
            f.write(raw)
        pid = "demo-project"  # in prod map to real project id
        sid = save_submission(pid, "A", fname, notes)
        st.success(f"ส่งแบบเรียบร้อย (submission id: {sid})")
        st.info("ระบบจะรัน parser แบบตัวอย่างและสร้างตารางตัวอย่างให้ B ตรวจ")
        parsed = parse_pdf_stub(raw)
        st.dataframe(parsed)

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
            # load file
            row = df_subs[df_subs["id"]==chosen]
            if row.empty:
                st.error("ไม่พบ submission id")
            else:
                fname = row.iloc[0]["filename"]
                path = os.path.join("uploads", fname)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        raw = f.read()
                    parsed = parse_pdf_stub(raw)
                    st.subheader("ผลการ parse (ตัวอย่าง)")
                    st.dataframe(parsed)
                    if st.button("สรุปแบบและส่งกลับให้ A (request changes)"):
                        st.success("ส่งคำขอกลับให้ A เรียบร้อย — (demo)")

elif role.startswith("D"):
    st.header("หน้า D — ส่งรายละเอียดงานให้ C")
    st.write("ป้อนรายละเอียดงาน (scope) ที่ C จะใช้คำนวณ")
    scope_text = st.text_area("รายละเอียดงาน (Scope)")
    if st.button("ส่งให้ C") and scope_text:
        # in prod would create a submission
        sid = save_submission("demo-project", "D", "scope_text.txt", scope_text)
        st.success(f"ส่ง scope ให้ C แล้ว (submission id: {sid})")

elif role.startswith("C"):
    st.header("หน้า C — สรุปราคา & สร้าง BOQ")
    st.info("โหลดแบบสุดท้ายจาก B, ตรวจแม็ปรายการกับ price list แล้วสร้าง BOQ 4 ตาราง")
    uploaded = st.file_uploader("(ทางเลือก) อัปโหลด PDF แบบถ้าต้องการทดสอบ parser", type=["pdf"], key='c_upload')
    if uploaded is not None:
        raw = uploaded.read()
        items = parse_pdf_stub(raw)
        st.subheader("รายการที่ดึงได้ (parsed)")
        st.dataframe(items)
        matched = match_price_stub(items, price_df)
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
