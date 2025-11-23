import os
import io
import uuid
import sqlite3
import datetime
import pandas as pd
import streamlit as st

from pypdf import PdfReader

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
DB_PATH = "boq_app.db"

ARCH_API_KEY = os.getenv("ARCH_API_KEY")
ENG_API_KEY = os.getenv("ENG_API_KEY")
PRICE_API_KEY = os.getenv("PRICE_API_KEY")

# ---------------------------------------------------------------------
# DATABASE INIT
# ---------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            role TEXT,
            filename TEXT,
            notes TEXT,
            version INTEGER,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS boq (
            id TEXT PRIMARY KEY,
            submission_id TEXT,
            excel BLOB,
            created_at TEXT
        )
    """)

    conn.commit()
    return conn

conn = init_db()

# ---------------------------------------------------------------------
# PDF PARSER — REAL
# ---------------------------------------------------------------------
def parse_pdf(file_bytes: bytes) -> pd.DataFrame:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))

        text_join = ""
        for page in reader.pages:
            text_join += page.extract_text() + "\n"

        rows = []
        for line in text_join.split("\n"):
            if any(x in line for x in ["สาย", "ท่อ", "LED", "ปลั๊ก", "ไฟ", "เบรกเกอร์"]):
                rows.append({
                    "description": line.strip(),
                    "qty": 1,
                    "unit": "ea"
                })

        if len(rows) == 0:
            rows.append({"description": "ไม่พบข้อมูลใน PDF", "qty": 0, "unit": ""})

        return pd.DataFrame(rows)

    except Exception:
        return pd.DataFrame([{"description": "PDF อ่านไม่ได้", "qty": 0, "unit": ""}])

# ---------------------------------------------------------------------
# PRICE LIST LOAD
# ---------------------------------------------------------------------
def load_price_list(uploaded):
    if uploaded is None:
        return pd.DataFrame(columns=["description", "unit", "unit_price"])
    try:
        return pd.read_csv(uploaded)
    except:
        return pd.DataFrame(columns=["description", "unit", "unit_price"])

# ---------------------------------------------------------------------
# MATCH PRICES
# ---------------------------------------------------------------------
def match_prices(items: pd.DataFrame, price_df: pd.DataFrame):
    result = items.copy()
    result["unit_price"] = 0

    for i, row in result.iterrows():
        desc = str(row["description"])
        match = price_df[
            price_df["description"].str.contains(desc.split()[0], case=False, na=False)
        ]

        if len(match) > 0:
            result.at[i, "unit_price"] = float(match.iloc[0]["unit_price"])

    result["material_cost"] = result["unit_price"] * result["qty"]
    result["labor_cost"] = result["material_cost"] * 0.10
    result["total_cost"] = result["material_cost"] + result["labor_cost"]

    return result

# ---------------------------------------------------------------------
# SAVE BOQ
# ---------------------------------------------------------------------
def save_boq(submission_id: str, excel_bytes: bytes):
    bid = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    c = conn.cursor()
    c.execute(
        "INSERT INTO boq (id, submission_id, excel, created_at) VALUES (?,?,?,?)",
        (bid, submission_id, sqlite3.Binary(excel_bytes), now)
    )
    conn.commit()
    return bid

# ---------------------------------------------------------------------
# UI START
# ---------------------------------------------------------------------
st.title("BOQ – 3 Agent Loop (A / B / C)")

role = st.selectbox("Role", ["A - Architect", "B - Engineer", "C - Cost Engineer"])

# ---------------------------------------------------------------------
# A — Upload
# ---------------------------------------------------------------------
if role.startswith("A"):
    st.header("A – Upload แบบ")

    file = st.file_uploader("อัปโหลดแบบ (PDF)", type=["pdf"])
    notes = st.text_area("ข้อความถึง B")

    if st.button("ส่งแบบให้ B"):
        if file is None:
            st.error("ต้องอัปโหลด PDF ก่อน")
        else:
            raw = file.read()

            sid = str(uuid.uuid4())
            now = datetime.datetime.utcnow().isoformat()
            c = conn.cursor()
            c.execute(
                "INSERT INTO submissions (id, role, filename, notes, version, created_at) VALUES (?,?,?,?,1,?)",
                (sid, "A", file.name, notes, now)
            )
            conn.commit()

            parsed = parse_pdf(raw)
            st.success(f"ส่งแล้ว Submission ID: {sid}")
            st.write("ผลการอ่าน PDF:")
            st.dataframe(parsed)

# ---------------------------------------------------------------------
# B — Review
# ---------------------------------------------------------------------
elif role.startswith("B"):
    st.header("B – ตรวจแบบจาก A")

    c = conn.cursor()
    subs = c.execute("SELECT * FROM submissions WHERE role='A' ORDER BY created_at DESC").fetchall()
    df = pd.DataFrame(subs, columns=["id","role","filename","notes","version","created_at"])
    st.dataframe(df)

    sid = st.text_input("Submission ID ที่ต้องการโหลด")

    if st.button("โหลดเพื่อตรวจ"):
        row = df[df["id"] == sid]
        if row.empty:
            st.error("ไม่พบ Submission")
        else:
            st.success("โหลดสำเร็จ (DEMO ไม่มีไฟล์จริง)")
            st.write("หมายเหตุจาก A:", row.iloc[0]["notes"])

# ---------------------------------------------------------------------
# C — BOQ
# ---------------------------------------------------------------------
elif role.startswith("C"):
    st.header("C – สรุปราคา สร้าง BOQ")

    pdf = st.file_uploader("อัปโหลด PDF", type=["pdf"])
    price_csv = st.file_uploader("อัปโหลด Price_List.csv (ไม่ต้องมี errors=)", type=["csv"])

    if pdf and price_csv:
        pdf_bytes = pdf.read()
        items = parse_pdf(pdf_bytes)
        price_df = load_price_list(price_csv)

        matched = match_prices(items, price_df)

        st.write("รายการ + ราคา:")
        st.dataframe(matched)

        excel = io.BytesIO()
        with pd.ExcelWriter(excel, engine="openpyxl") as w:
            matched.to_excel(w, index=False, sheet_name="BOQ")

        excel.seek(0)

        st.download_button(
            "ดาวน์โหลด BOQ.xlsx",
            data=excel,
            file_name="BOQ.xlsx"
        )

