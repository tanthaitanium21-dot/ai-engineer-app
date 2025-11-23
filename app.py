import streamlit as st
import pandas as pd
import time
import os

st.set_page_config(page_title="AI Engineer (GitHub Version)", layout="wide", page_icon="🏗️")

# --- 1. KNOWLEDGE BASE (อ่านจากโฟลเดอร์ใน GitHub) ---
# สร้างโฟลเดอร์ Manuals รอไว้ (ถ้าไม่มี)
if not os.path.exists('Manuals'):
    os.makedirs('Manuals')

def get_manuals():
    # อ่านไฟล์ PDF ที่คุณอัปโหลดขึ้น GitHub ในโฟลเดอร์ Manuals
    files = [f for f in os.listdir('Manuals') if f.endswith('.pdf')]
    return files

def search_manual(query, room_type):
    # Logic จำลองการค้นหา
    return [f"📖 อ้างอิงมาตรฐาน (จากไฟล์ใน GitHub): กฎของ {room_type} ระบุว่าต้องปลอดภัย"]

# --- 2. AGENT A & B (Logic เดิม) ---
def agent_process(image, manuals):
    time.sleep(1) # Simulate processing
    return pd.DataFrame([
        {"ID": "A1", "Item": "Switch", "Room": "Living Room", "Status": "✅ OK"},
        {"ID": "A2", "Item": "Socket", "Room": "Bathroom", "Status": "❌ Error (Need IP44)"}
    ])

# --- 3. MAIN APP ---
st.title("🏗️ AI Engineer System (Host on GitHub)")

# ส่วนแสดงคู่มือ
st.sidebar.header("📚 คู่มือในระบบ")
manuals = get_manuals()
if manuals:
    st.sidebar.success(f"พบคู่มือ {len(manuals)} เล่ม")
    for m in manuals:
        st.sidebar.write(f"- {m}")
else:
    st.sidebar.warning("ไม่พบคู่มือ (กรุณา Upload ใส่โฟลเดอร์ Manuals ใน GitHub)")

# ส่วนอัปโหลดแบบ
uploaded_file = st.file_uploader("📂 อัปโหลดแบบก่อสร้าง", type=['png', 'jpg'])

if uploaded_file:
    st.image(uploaded_file, caption="แบบก่อสร้าง", use_column_width=True)
    if st.button("🚀 เริ่มตรวจสอบ"):
        with st.spinner("AI กำลังทำงานบน Server..."):
            result_df = agent_process(uploaded_file, manuals)
            st.dataframe(result_df, use_container_width=True)
            if not result_df[result_df['Status'].str.contains("Error")].empty:
                st.error("พบข้อผิดพลาดในแบบ!")
            else:
                st.success("แบบถูกต้องสมบูรณ์")