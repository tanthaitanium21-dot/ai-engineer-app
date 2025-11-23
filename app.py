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
st.set_page_config(page_title="MEP AI: The Dream Team", layout="wide", page_icon="👷")

# 🔑 API KEY
API_KEY = "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA"

# Auto-Detect Model
try:
    client = genai.Client(api_key=API_KEY)
    MODEL_ID = "gemini-2.5-flash"
    client.models.generate_content(model=MODEL_ID, contents="Ping")
except:
    MODEL_ID = "gemini-1.5-flash"
    client = genai.Client(api_key=API_KEY)

# --- 2. KNOWLEDGE ACCESS ---
def get_kb_content(filename):
    path = os.path.join("Manuals", filename)
    if not os.path.exists(path): return f"Missing {filename}"
    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(path)
            text = ""
            for p in reader.pages[:20]: text += p.extract_text()
            return text
        except: return "Error PDF"
    elif filename.endswith(".csv"):
        try:
            return pd.read_csv(path).to_markdown(index=False)
        except: return "Error CSV"
    return ""

# --- 3. THE TEAM AGENT WORKFLOW ---

def run_team_a(image, round_num, feedback=""):
    """ทีมสถาปนิก 6 คน (A1-A6)"""
    
    legend_ref = """
    [Reference Symbols from PDF]
    - Lighting: Circle+X (Downlight), Rect (Fluorescent)
    - Power: Circle+2lines (Duplex), +WP (Waterproof)
    - Switch: S, S2, S3
    """
    
    prompt = f"""
    คุณคือ "Team A" ทีมสถาปนิกถอดแบบ 6 คน
    บริบท: ทำงานรอบที่ {round_num}
    Feedback จากวิศวกร: {feedback if feedback else "-"}
    
    ให้สมาชิกทุกคนทำงานตามบทบาทอย่างเคร่งครัด:
    
    1. **A1 สถาปนิก "ดำ" (Grid Scanner):**
       - หน้าที่: สแกนพื้นที่ทีละตารางนิ้ว เพื่อค้นหาอุปกรณ์ทุกชิ้นที่ซ่อนอยู่
    
    2. **A2 สถาปนิก "แดง" (Symbol Expert):**
       - หน้าที่: เทียบรูปร่างสัญลักษณ์กับ Legend: {legend_ref} อย่างแม่นยำ
    
    3. **A3 สถาปนิก "ขาว" (Label Reader):**
       - หน้าที่: อ่านตัวหนังสือ Label กำกับอุปกรณ์ (เช่น TV, TEL, WP, AC) เพื่อระบุชนิด
    
    4. **A4 สถาปนิก "เขียว" (Room Scope):**
       - หน้าที่: ระบุชื่อห้องและขอบเขตห้อง
       - **กฎเหล็ก:** "ตาเห็นสิ่งใด ให้บันทึกสิ่งนั้น" ห้ามเดาบริบท ห้ามคิดเองว่าห้องน้ำต้องมีพัดลมถ้าในแบบไม่ได้วาดไว้ ห้ามเพิ่มของเองเด็ดขาด
    
    5. **A5 สถาปนิก "ฟ้า" (Circuit Tracer):**
       - หน้าที่: ไล่เส้นประสายไฟเพื่อดูการจับคู่อุปกรณ์ (เช่น สวิตช์ตัวนี้คุมไฟดวงไหน)
    
    6. **A6 สถาปนิก "ส้ม" (Consolidator):**
       - หน้าที่: รวบรวมข้อมูลจาก A1-A5 ตัดรายการซ้ำซ้อน และจัดทำบัญชีรายการ
    
    Output: ขอ JSON List ของรายการอุปกรณ์ทั้งหมด (สรุปโดย A6):
    [
      {{"room": "...", "item": "...", "spec": "...", "qty": 0, "found_by": "A1,A2"}}
    ]
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=[prompt, image])
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return []

def run_team_b(data_from_a, round_num):
    """ทีมวิศวกร 6 คน (B1-B6)"""
    manual = get_kb_content("Engineering_Drawings_EE.pdf")
    
    prompt = f"""
    คุณคือ "Team B" ทีมวิศวกรตรวจสอบ 6 คน
    ข้อมูลจากทีม A: {json.dumps(data_from_a, ensure_ascii=False)}
    
    ให้สมาชิกทุกคนตรวจสอบตามบทบาท:
    
    1. **B1 วิศวกร "บุญชู" (Safety Lead):**
       - ตรวจความปลอดภัย (กันน้ำในโซนเปียก, สายดิน, เบรกเกอร์)
    
    2. **B2 วิศวกร "สมชาย" (Standard):**
       - ตรวจมาตรฐานการติดตั้งเทียบกับคู่มือ: {manual[:5000]}...
    
    3. **B3 วิศวกร "สมหญิง" (Design & UX):**
       - ตรวจตำแหน่งการใช้งาน (สวิตช์ถูกด้านประตู?, ปลั๊กหัวเตียงมีไหม?)
    
    4. **B4 วิศวกร "สมศักดิ์" (Spec & Cost):**
       - ตรวจสเปควัสดุว่าสมเหตุสมผลและมีขายจริงหรือไม่
    
    5. **B5 วิศวกร "สมปอง" (Load Calc):**
       - ประเมินโหลดไฟฟ้าคร่าวๆ ว่าเหมาะสมหรือไม่
    
    6. **B6 วิศวกร "สมหมาย" (Project Manager):**
       - รวบรวมความเห็นและตัดสินใจอนุมัติ
    
    เงื่อนไขการตัดสิน:
    - ถ้าพบจุดผิดพลาดร้ายแรง (Critical): สั่ง "REJECTED" พร้อมระบุสิ่งที่ A ต้องแก้
    - ถ้าถูกต้องครบถ้วน: สั่ง "APPROVED"
    
    Output Format:
    - REJECTED: [รายการสั่งแก้ 1, รายการสั่งแก้ 2...]
    - APPROVED: [JSON Final List]
    """
    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
    return response.text

def run_team_c_d(final_data):
    """ทีมประเมินและหน้างาน"""
    price_list = get_kb_content("Price_List.csv")
    
    # Step 1: D (Foreman) เขียนวิธีทำ
    prompt_d = f"""
    คุณคือ D (โฟร์แมน/หัวหน้าช่าง)
    ข้อมูลงาน: {final_data}
    หน้าที่: เขียน "Method Statement" (วิธีการทำงาน) อย่างละเอียด และประเมินความยากง่ายส่งให้ฝ่ายบัญชี
    """
    method_d = client.models.generate_content(model=MODEL_ID, contents=prompt_d).text
    
    # Step 2: C (QS) คิดเงิน
    prompt_c = f"""
    คุณคือ C (QS)
    หน้าที่: ทำ BOQ 4 ตาราง โดยอ้างอิงราคาจาก Price List นี้เท่านั้น:
    {price_list}
    
    ข้อมูลงาน: {final_data}
    วิธีทำจาก D: {method_d}
    
    คำสั่ง: สร้าง JSON Output 4 ตาราง:
    1. table_1_total (รวมค่าของ+แรง)
    2. table_2_mat (ค่าของ)
    3. table_3_lab (ค่าแรง)
    4. table_4_po (ใบสั่งซื้อ)
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt_c)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return method_d, json.loads(text)
    except:
        return method_d, {"error": "JSON Error"}

# --- 4. MAIN UI ---
def main():
    st.title(f"🏗️ MEP Dream Team ({MODEL_ID})")
    
    # File Check
    c1, c2 = st.columns(2)
    with c1:
        if "Error" in get_kb_content("Price_List.csv"): st.error("❌ ขาดไฟล์ Price_List.csv")
        else: st.success("✅ ฐานข้อมูลราคา (C) พร้อม")
    with c2:
        if "Error" in get_kb_content("Engineering_Drawings_EE.pdf"): st.warning("⚠️ ขาดไฟล์คู่มือ PDF")
        else: st.success("✅ ฐานข้อมูลวิศวกรรม (B) พร้อม")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file and st.button("🚀 เรียกทีมงาน A-B-C-D"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        # --- ROUND 1 ---
        st.markdown("### 🔄 Round 1: A สำรวจ & B ตรวจสอบ")
        with st.spinner("ทีม A (ดำ, แดง, ขาว, เขียว, ฟ้า, ส้ม) กำลังรุมถอดแบบ..."):
            data_r1 = run_team_a(image, 1)
            if not data_r1:
                st.error("ทีม A มองไม่เห็นข้อมูล (ลองภาพที่ชัดขึ้น)")
                st.stop()
            st.expander("Draft 1 (โดย สถาปนิกส้ม)").json(data_r1)
            
        with st.spinner("ทีม B (บุญชู, สมชาย, สมหญิง, สมศักดิ์, สมปอง, สมหมาย) กำลังรุมตรวจ..."):
            res_b1 = run_team_b(data_r1, 1)
        
        # Check Result
        final_verdict = None
        if "REJECTED" in res_b1:
            st.warning(f"📝 **ใบสั่งแก้จาก วิศวกรสมหมาย:**\n{res_b1}")
            
            # --- ROUND 2 ---
            st.markdown("### 🔄 Round 2: แก้ไข & อนุมัติ")
            with st.spinner("ทีม A กำลังแก้ไขตามคำสั่ง..."):
                data_r2 = run_team_a(image, 2, feedback=res_b1)
                
            with st.spinner("ทีม B ตรวจสอบครั้งสุดท้าย..."):
                res_b2 = run_team_b(data_r2, 2)
                
            try:
                json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
                final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                st.success("🏆 **แบบผ่านการอนุมัติ (Final Approved):**")
                st.json(final_verdict)
            except:
                st.error("Error Parsing Final Verdict")
        else:
            st.success("✅ แบบผ่านตั้งแต่รอบแรก (Perfect Design)")
            try:
                json_str = res_b1.split("APPROVED:")[1].strip() if "APPROVED:" in res_b1 else res_b1
                final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
            except:
                final_verdict = data_r1

        # --- PHASE 3 ---
        if final_verdict:
            st.markdown("---")
            st.header("🚀 Execution Phase")
            
            with st.spinner("D (Foreman) & C (QS) กำลังทำงาน..."):
                method_d, boq_data = run_team_c_d(final_verdict)
                
                st.info(f"👷 **D (วิธีทำ):**\n{method_d[:500]}...")
                
                if "error" not in boq_data:
                    t1, t2, t3, t4 = st.tabs(["1. รวม", "2. ค่าของ", "3. ค่าแรง", "4. PO"])
                    def show_tab(key):
                        if key in boq_data:
                            df = pd.DataFrame(boq_data[key])
                            st.dataframe(df, use_container_width=True)
                            # Sum logic
                            cols = df.columns
                            numeric_cols = df.select_dtypes(include=['number']).columns
                            if len(numeric_cols) > 0:
                                col_to_sum = next((x for x in cols if "รวม" in x or "Total" in x), numeric_cols[-1])
                                try: st.metric("Grand Total", f"{df[col_to_sum].sum():,.2f} THB")
                                except: pass

                    with t1: show_tab("table_1_total")
                    with t2: show_tab("table_2_mat")
                    with t3: show_tab("table_3_lab")
                    with t4: show_tab("table_4_po")
                else:
                    st.error("C (QS) คำนวณตัวเลขผิดพลาด")

if __name__ == "__main__":
    main()
