import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import time
import os
from PIL import Image

# --- CONFIG ---
st.set_page_config(page_title="Ultimate 6x6 MEP System", layout="wide", page_icon="🏢")
# 🔑 ใส่ API KEY ของคุณ
API_KEY = "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI"
genai.configure(api_key=API_KEY)

# 🔥 จุดที่แก้: ลองใช้ชื่อรุ่นเต็ม หรือถ้าไม่ได้ให้ใช้ 'gemini-pro'
try:
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
except:
    # ถ้าหา Flash ไม่เจอ ให้ถอยมาใช้รุ่นมาตรฐาน
    model = genai.GenerativeModel('gemini-pro')

# --- DATA MOCKUP (เพื่อความรวดเร็วในการสาธิต แต่โค้ดรองรับการอ่านจริง) ---
# ในการใช้งานจริง ฟังก์ชันเหล่านี้จะอ่าน PDF/CSV จาก GitHub
def get_knowledge(role):
    if "A" in role: return "คู่มือสัญลักษณ์ไฟฟ้า (Legend)"
    if "B" in role: return "มาตรฐาน วสท. และกฎความปลอดภัย"
    if "C" in role: return "Price_List.csv (ราคากลาง + ค่าแรง)"
    return ""

# --- AGENT LOGIC (THE 6x6 MATRIX) ---

def run_agent_a_group(image):
    """รัน A 6 ตัวพร้อมกัน (จำลอง)"""
    # A1-A6 มี Prompt ต่างกัน
    prompts = {
        "A1 (Grid)": "แบ่งภาพเป็นตาราง ค้นหาอุปกรณ์ไฟฟ้าทุกชิ้นอย่างละเอียด",
        "A2 (Symbol)": "ค้นหาเฉพาะสัญลักษณ์ที่ตรงกับ Legend เท่านั้น",
        "A3 (Text)": "อ่านตัวหนังสือ (Label) ที่กำกับอุปกรณ์ เช่น 'TV', 'WP'",
        "A4 (Context)": "วิเคราะห์ตามบริบทห้อง (เช่น ห้องน้ำต้องมีพัดลมดูดอากาศ)",
        "A5 (Tracer)": "ไล่เส้นสายไฟเพื่อหาตำแหน่งอุปกรณ์ปลายทาง",
        "A6 (Consolidator)": "รวมผลลัพธ์จาก A1-A5 ตัดตัวซ้ำ และสรุปยอดดิบ"
    }
    
    results = {}
    progress = st.progress(0)
    idx = 0
    
    for name, p in prompts.items():
        # จำลองการส่ง Prompt (ของจริงคือส่ง API request)
        full_prompt = f"คุณคือ {name}. หน้าที่: {p}. ให้ Output เป็น JSON รายการอุปกรณ์"
        try:
            # ใช้ API จริง
            response = model.generate_content([full_prompt, image])
            results[name] = response.text
        except:
            results[name] = "Error connecting"
        
        idx += 1
        progress.progress(idx / 6)
        time.sleep(1) # พักไม่ให้ Rate Limit เต็ม
        
    return results

def run_agent_b_group(a_results):
    """รัน B 6 ตัวเพื่อตรวจสอบ A"""
    # B จะได้รับข้อมูลรวมจาก A (สมมติว่า A6 สรุปมาให้แล้ว)
    consolidated_data = a_results.get("A6 (Consolidator)", "")
    
    prompts = {
        "B1 (Safety)": "ตรวจเรื่องความปลอดภัย (กันน้ำ, สายดิน) อย่างเดียว",
        "B2 (Standard)": "ตรวจมาตรฐานการติดตั้ง (ความสูง, ระยะห่าง)",
        "B3 (Design)": "ตรวจ Logic การใช้งาน (เช่น สวิตช์ถูกฝั่งไหม)",
        "B4 (Spec)": "ตรวจสเปควัสดุเทียบราคากลาง",
        "B5 (Load)": "คำนวณโหลดไฟฟ้าคร่าวๆ",
        "B6 (Chief)": "อ่านความเห็น B1-B5 แล้วสรุป Final Draft เพื่อส่ง C"
    }
    
    results = {}
    progress = st.progress(0)
    idx = 0
    
    for name, p in prompts.items():
        full_prompt = f"""
        คุณคือ {name}. หน้าที่: {p}. 
        ข้อมูลจาก A: {consolidated_data}
        กฎ: ถ้าเจอผิด ให้แจ้ง REJECT. ถ้าถูก ให้แจ้ง APPROVED.
        """
        response = model.generate_content(full_prompt)
        results[name] = response.text
        
        idx += 1
        progress.progress(idx / 6)
        
    return results

def run_agent_d(final_draft):
    """D เขียนวิธีทำ ส่งให้ C"""
    prompt = f"เขียน 'วิธีทำและระดับความยาก' ของงานนี้เพื่อส่งให้ฝ่ายประเมินค่าแรง: {final_draft}"
    return model.generate_content(prompt).text

def run_agent_c(final_draft, method_d):
    """C ทำ 4 ตาราง"""
    # จำลองการดึงราคาจาก CSV (Price_List.csv)
    # ในโค้ดจริงจะใช้ pandas read_csv
    
    prompt = f"""
    คุณคือ C (QS). ข้อมูลงาน: {final_draft}. วิธีทำจาก D: {method_d}.
    
    คำสั่ง: สร้างข้อมูลสำหรับ 4 ตาราง ดังนี้ (Output เป็น JSON):
    1. Table_Total: ค่าของ + ค่าแรง
    2. Table_Material: ค่าของอย่างเดียว
    3. Table_Labor: ค่าแรงอย่างเดียว
    4. Table_PO: ใบสั่งซื้อ (Purchase Order)
    
    สมมติราคา:
    - Switch: ของ 85, แรง 40
    - Socket: ของ 140, แรง 60
    - Downlight: ของ 250, แรง 80
    """
    response = model.generate_content(prompt)
    try:
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except:
        return {"error": "Failed to generate JSON"}

# --- MAIN APP ---
def main():
    st.title("🏗️ 6x6 Multi-Agent Analysis System")
    st.markdown("ระบบตรวจสอบความแม่นยำสูงสุด: **6 Architects (A) -> 6 Engineers (B) -> QS (C) & Foreman (D)**")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])

    if uploaded_file and st.button("🚀 รันระบบตรวจสอบเต็มรูปแบบ"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        # --- PHASE 1: A-Team (Mining) ---
        st.header("1. ทีมสถาปนิก 6 คน (A1-A6) กำลังทำงาน...")
        a_results = run_agent_a_group(image)
        
        with st.expander("ดูผลลัพธ์ของ A ทั้ง 6 คน"):
            for k, v in a_results.items():
                st.markdown(f"**{k}:** {v[:200]}...") # โชว์ย่อๆ
        
        # --- PHASE 2: B-Team (Auditing) ---
        st.header("2. ทีมวิศวกร 6 คน (B1-B6) กำลังตรวจสอบ...")
        b_results = run_agent_b_group(a_results)
        
        final_verdict = b_results.get("B6 (Chief)", "")
        st.success(f"🏆 **สรุปแบบที่ผ่านการอนุมัติ (By B6):** \n{final_verdict}")
        
        with st.expander("ดูความเห็นแย้งของ B แต่ละคน"):
            for k, v in b_results.items():
                st.warning(f"**{k}:** {v}")

        # --- PHASE 3: Execution (C & D) ---
        st.markdown("---")
        st.header("3. สรุปราคาและสั่งงาน (C & D)")
        
        # D ทำงาน
        with st.spinner("D กำลังประเมินหน้างาน..."):
            method_d = run_agent_d(final_verdict)
            st.info(f"👷 **D (Foreman):** {method_d[:300]}...")
            
        # C ทำงาน (4 ตาราง)
        with st.spinner("C กำลังทำ BOQ 4 ตาราง..."):
            boq_data = run_agent_c(final_verdict, method_d)
            
            if "error" not in boq_data:
                tab1, tab2, tab3, tab4 = st.tabs(["1. ค่าของ+ค่าแรง", "2. ค่าของ", "3. ค่าแรง", "4. ใบสั่งซื้อ (PO)"])
                
                # ฟังก์ชันแปลง JSON เป็น DataFrame
                def show_table(key):
                    if key in boq_data:
                        df = pd.DataFrame(boq_data[key])
                        st.dataframe(df, use_container_width=True)
                        st.metric("รวมเป็นเงิน", f"{df['Total'].sum() if 'Total' in df.columns else 0:,.2f} THB")
                
                with tab1: show_table("Table_Total")
                with tab2: show_table("Table_Material")
                with tab3: show_table("Table_Labor")
                with tab4: show_table("Table_PO")
            else:
                st.error("เกิดข้อผิดพลาดในการสร้างตารางราคา")

if __name__ == "__main__":
    main()

