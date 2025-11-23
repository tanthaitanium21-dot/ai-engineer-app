import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import time
import os
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="MEP AI: Ultimate 6x6 System", layout="wide", page_icon="🏗️")

# 🔑 API KEY
API_KEY = "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA"

# 🔥 AUTO-DETECT MODEL
def get_client_and_model():
    try:
        client = genai.Client(api_key=API_KEY)
        candidate_models = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.0-pro']
        for m in candidate_models:
            try:
                client.models.generate_content(model=m, contents="Hi")
                return client, m
            except: continue
        return None, None
    except Exception as e: return None, None

# Init AI
with st.spinner("🤖 System Initializing..."):
    client, MODEL_ID = get_client_and_model()

if not client:
    st.error("🚨 Connection Failed: Check API Key")
    st.stop()

# --- 2. HELPER FUNCTIONS ---
def generate(prompt, image=None):
    try:
        if image: response = client.models.generate_content(model=MODEL_ID, contents=[prompt, image])
        else: response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        return response.text
    except: return "Error"

def get_kb_text(filename):
    path = os.path.join("Manuals", filename)
    if not os.path.exists(path): return "File not found"
    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(path)
            text = ""
            for p in reader.pages[:20]: text += p.extract_text() + "\n"
            return text
        except: return "Error reading PDF"
    elif filename.endswith(".csv"):
        try:
            return pd.read_csv(path).to_markdown(index=False)
        except: return "Error reading CSV"
    return ""

# --- 3. THE 6x6 AGENT CLUSTER ---

def run_team_a_6_perspectives(image, round_num, feedback=""):
    """A 6 คน: หาข้อมูลคนละวิธี"""
    instruction = f"รอบที่ {round_num}"
    if feedback: instruction += f" (แก้ไขตามคำสั่ง: {feedback})"
    
    # นิยามความเชี่ยวชาญ 6 ด้าน
    perspectives = {
        "A1 (Grid)": "แบ่งภาพเป็นตาราง 9 ช่อง สแกนทีละช่องอย่างละเอียด",
        "A2 (Symbol)": "โฟกัสแค่รูปร่างสัญลักษณ์ เทียบกับ Legend มาตรฐาน",
        "A3 (Text)": "อ่านตัวหนังสือ Label (เช่น WP, TV, S2) เพื่อยืนยันชนิด",
        "A4 (Context)": "ดูบริบทห้อง (เช่น ถ้าเป็นห้องน้ำ ต้องหาเครื่องทำน้ำอุ่น)",
        "A5 (Lines)": "ไล่เส้นสายไฟ (Circuit Line) เพื่อดูการเชื่อมต่อ",
        "A6 (Counter)": "นับจำนวนและจัดหมวดหมู่ ตัดตัวซ้ำออก"
    }
    
    results = {}
    
    # ในทางปฏิบัติ เพื่อความเร็ว เราจะส่ง Prompt รวมให้ AI สวมบทบาท 6 คนพร้อมกัน
    # (แต่ถ้าจะแยก Call จริงๆ ก็ทำได้ แต่จะช้ามาก)
    full_prompt = f"""
    คุณคือทีมสถาปนิก 6 คน ({instruction}) ช่วยกันถอดแบบจากภาพนี้
    
    ให้แต่ละคนทำงานตามความถนัด:
    {json.dumps(perspectives, indent=2, ensure_ascii=False)}
    
    สรุปผลงานของทั้ง 6 คนออกมาเป็น JSON List เดียวที่แม่นยำที่สุด:
    [
      {{"room": "...", "item": "...", "spec": "...", "qty": 0, "found_by": "A1,A3"}}
    ]
    """
    try:
        res = generate(full_prompt, image)
        return json.loads(res.replace("```json", "").replace("```", "").strip())
    except: return []

def run_team_b_6_auditors(data_from_a, round_num):
    """B 6 คน: ตรวจสอบและสรุป"""
    manual = get_kb_text("Engineering_Drawings_EE.pdf")
    
    prompt = f"""
    คุณคือทีมวิศวกร 6 คน (Safety, Standard, Design, Spec, Load, Chief)
    กำลังตรวจสอบงานรอบที่ {round_num} จากทีม A
    
    --- กฎหมายและมาตรฐาน (Reference) ---
    {manual[:5000]}...
    ------------------------------------
    
    ข้อมูลจาก A: {json.dumps(data_from_a, ensure_ascii=False)}
    
    หน้าที่:
    1. B1-B5 รุมตรวจสอบหาจุดผิด (Error Detection)
    2. B6 (Chief) สรุปผล
    
    ถ้าเป็นรอบที่ 1: ให้เน้นหาจุดผิดแล้วสั่ง A แก้ไข (Output: FEEDBACK_ORDER)
    ถ้าเป็นรอบที่ 2 (Final): ให้สรุปแบบเพื่อสร้าง (Output: FINAL_APPROVED)
    
    รูปแบบคำตอบ (เลือก 1 อย่าง):
    - FEEDBACK: [รายการแก้ไขที่ 1, รายการแก้ไขที่ 2, ...]
    - APPROVED: [ข้อมูล JSON ที่ถูกต้องที่สุดเพื่อส่งต่อ C]
    """
    return generate(prompt)

def run_execution_c_d(final_data):
    """D เขียนวิธี -> C คิดเงิน"""
    price_list = get_kb_text("Price_List.csv")
    
    # 1. D (Foreman) ส่งรายละเอียดงานให้ C
    prompt_d = f"เขียน 'รายละเอียดขั้นตอนการทำงาน (Method Statement)' อย่างละเอียดสำหรับข้อมูลนี้ เพื่อให้ฝ่ายบัญชีประเมินค่าแรงได้ถูก: {final_data}"
    method_d = generate(prompt_d)
    
    # 2. C (QS) สรุปราคา 4 ตาราง
    prompt_c = f"""
    คุณคือ C (QS) รับข้อมูลจาก B และ D
    
    --- ราคากลาง (CSV) ---
    {price_list}
    ---------------------
    
    ข้อมูลของ: {final_data}
    ข้อมูลค่าแรง/วิธีทำจาก D: {method_d}
    
    คำสั่ง: ทำ BOQ 4 ตาราง (JSON Keys: table_1_total, table_2_mat, table_3_lab, table_4_po)
    1. table_1_total: รายการ, จำนวน, ค่าวัสดุ, ค่าแรง, รวม
    2. table_2_mat: รายการ, จำนวน, ค่าวัสดุ/หน่วย, รวมวัสดุ
    3. table_3_lab: รายการ, จำนวน, ค่าแรง/หน่วย (อิงจากความยากง่ายของ D), รวมค่าแรง
    4. table_4_po: รายการวัสดุที่จะสั่งซื้อ (Purchase Order)
    
    Output: JSON Only
    """
    try:
        res_c = generate(prompt_c)
        boq_data = json.loads(res_c.replace("```json", "").replace("```", "").strip())
    except: boq_data = {"error": "JSON Error"}
    
    return method_d, boq_data

# --- 4. MAIN APP UI ---
def main():
    st.title("🏗️ Ultimate 6x6 MEP System")
    st.caption(f"Engine: {MODEL_ID} | Status: Ready")
    
    # File Check
    c1, c2 = st.columns(2)
    with c1:
        if "not found" in get_kb_text("Price_List.csv"): st.error("❌ Missing Price_List.csv")
        else: st.success("✅ Price DB (C) Ready")
    with c2:
        if "not found" in get_kb_text("Engineering_Drawings_EE.pdf"): st.warning("⚠️ Missing Manual PDF")
        else: st.success("✅ Engineer DB (B) Ready")

    uploaded_file = st.file_uploader("📂 Upload Blueprint", type=['png', 'jpg'])
    
    if uploaded_file and st.button("🚀 START 6x6 PROCESS"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Source Blueprint", width=400)
        
        # --- ROUND 1: DRAFT ---
        st.info("🔄 Round 1: Initial Drafting...")
        
        with st.spinner("Team A (6 Experts) is mining data..."):
            data_r1 = run_team_a_6_perspectives(image, 1)
            # st.json(data_r1) # Debug
            
        with st.spinner("Team B (6 Engineers) is auditing Round 1..."):
            res_b1 = run_team_b_6_auditors(data_r1, 1)
        
        # Check if B approved or ordered feedback
        feedback_order = ""
        if "FEEDBACK:" in res_b1:
            feedback_order = res_b1.split("FEEDBACK:")[1].strip()
            st.warning(f"📝 **B สั่งแก้ไขงาน (Correction Order):**\n{feedback_order}")
        else:
            st.success("✅ B อนุมัติทันทีในรอบแรก (Perfect Design)")
            
        # --- ROUND 2: REFINEMENT (ถ้ามีแก้) ---
        final_verdict = data_r1 # Default
        
        if feedback_order:
            st.info("🔄 Round 2: Refinement & Finalization...")
            with st.spinner("Team A is fixing defects..."):
                data_r2 = run_team_a_6_perspectives(image, 2, feedback_order)
                
            with st.spinner("Team B is Finalizing..."):
                res_b2 = run_team_b_6_auditors(data_r2, 2)
                
            # Extract JSON from B's final approval
            try:
                json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
                # Clean up markdown if present
                json_str = json_str.replace("```json", "").replace("```", "").strip()
                final_verdict = json.loads(json_str)
                st.success("🏆 **Final Approved Draft (By Team B):**")
                st.json(final_verdict)
            except:
                st.error("Error parsing final verdict from B")
                st.write(res_b2)

        # --- PHASE 3: C & D EXECUTION ---
        st.markdown("---")
        st.header("🚀 Execution Phase (C & D)")
        
        with st.spinner("D กำลังเขียน Method Statement & C กำลังทำ BOQ..."):
            if isinstance(final_verdict, list) or isinstance(final_verdict, dict):
                method_d, boq_data = run_execution_c_d(final_verdict)
                
                # Show D's Work
                st.subheader("👷 D: รายละเอียดงาน (Method Statement)")
                st.info(method_d)
                
                # Show C's Work (4 Tables)
                if "error" not in boq_data:
                    st.subheader("💰 C: สรุป BOQ 4 ตาราง")
                    t1, t2, t3, t4 = st.tabs(["1. ค่าของ+ค่าแรง", "2. ค่าของ", "3. ค่าแรง", "4. ใบสั่งซื้อ (PO)"])
                    
                    def display_tab(key):
                        if key in boq_data:
                            df = pd.DataFrame(boq_data[key])
                            st.dataframe(df, use_container_width=True)
                            if "รวม" in str(df.columns) or "Total" in str(df.columns):
                                # Try to sum numeric columns
                                numeric_cols = df.select_dtypes(include=['number']).columns
                                if len(numeric_cols) > 0:
                                    st.metric("Grand Total", f"{df[numeric_cols[-1]].sum():,.2f} THB")
                    
                    with t1: display_tab("table_1_total")
                    with t2: display_tab("table_2_mat")
                    with t3: display_tab("table_3_lab")
                    with t4: display_tab("table_4_po")
                else:
                    st.error("เกิดข้อผิดพลาดในการสร้างตารางราคา")
            else:
                st.error("ข้อมูลไม่ถูกต้อง ไม่สามารถไปต่อที่ C/D ได้")

if __name__ == "__main__":
    main()
