import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import time
import os
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURATION & MULTI-KEY SETUP ---
st.set_page_config(page_title="MEP AI: 3-Key System", layout="wide", page_icon="🏗️")

# Define Keys for each Role
KEYS = {
    "Architect": "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI",
    "Engineer": "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA",
    "QS": "AIzaSyB5e_5lXSnjlvIDL63OdV_BLBfQZvjaRuU"
}

# Function to switch brains (Clients)
def get_client(role):
    try:
        return genai.Client(api_key=KEYS[role])
    except: return None

# --- 2. KNOWLEDGE ACCESS (Specific Files) ---
def get_file_content(filename, folder="Manuals"):
    path = os.path.join(folder, filename)
    if not os.path.exists(path): return f"⚠️ Missing File: {filename}"
    
    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(path)
            text = ""
            # อ่าน 30 หน้าแรก (ปรับได้)
            for p in reader.pages[:30]: text += p.extract_text()
            return text
        except: return "Error reading PDF"
    elif filename.endswith(".csv"):
        try:
            return pd.read_csv(path).to_markdown(index=False)
        except: return "Error reading CSV"
    return ""

# --- 3. AGENT WORKFLOW (6x6 Logic) ---

def run_team_a(image, round_num, feedback=""):
    """
    🏢 Team A: สถาปนิก 6 คน (ใช้ Key: Architect)
    Brain: Engineering_Drawings_EE.pdf
    """
    client = get_client("Architect")
    kb_drawings = get_file_content("Engineering_Drawings_EE.pdf")
    
    prompt = f"""
    คุณคือ "Team A" (สถาปนิกถอดแบบ 6 คน) ทำงานรอบที่ {round_num}
    คำสั่งแก้ไขจากวิศวกร: {feedback if feedback else "-"}
    
    --- อ้างอิงสัญลักษณ์ (Symbol Reference) ---
    {kb_drawings[:5000]}...
    ----------------------------------------
    
    ให้สถาปนิกทั้ง 6 คนระดมสมอง (Grid, Symbol, Text, Context, Line, Counter):
    1. ค้นหาอุปกรณ์ไฟฟ้าในภาพให้ครบถ้วนที่สุด
    2. ระบุชนิด (Item), ห้อง (Room), สเปค (Spec)
    3. ห้ามส่งกระดาษเปล่า! ถ้ามองไม่ชัดให้ระบุว่า Unclear
    
    Output: JSON List เท่านั้น
    [ {{"room": "...", "item": "...", "spec": "...", "qty": 0}} ]
    """
    try:
        # ใช้ Gemini 2.5 Flash หรือ 1.5 Flash
        res = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt, image])
        return json.loads(res.text.replace("```json","").replace("```","").strip())
    except:
        # Fallback model
        try:
            res = client.models.generate_content(model="gemini-1.5-flash", contents=[prompt, image])
            return json.loads(res.text.replace("```json","").replace("```","").strip())
        except: return []

def run_team_b(data_from_a, round_num):
    """
    ⚙️ Team B: วิศวกร 6 คน (ใช้ Key: Engineer)
    Brain: วสท64_compressed.pdf
    """
    client = get_client("Engineer")
    kb_standard = get_file_content("วสท64_compressed.pdf")
    
    prompt = f"""
    คุณคือ "Team B" (วิศวกร 6 คน) ตรวจสอบงานรอบที่ {round_num}
    
    --- มาตรฐาน วสท. (Reference) ---
    {kb_standard[:10000]}...
    -------------------------------
    
    ข้อมูลจาก A: {json.dumps(data_from_a, ensure_ascii=False)}
    
    คำสั่ง:
    1. ตรวจสอบความปลอดภัยและมาตรฐาน (Safety, Standard, Design, Spec, Load)
    
    เงื่อนไขการตัดสินใจ:
    - หากเป็นรอบที่ 1: "บังคับ" ให้หาจุดบกพร่องและสั่งแก้ไข (REJECTED) เพื่อความรัดกุม
    - หากเป็นรอบที่ 2: ถ้าแก้ไขแล้วให้ (APPROVED)
    
    Output Format (เลือก 1 อย่าง):
    - REJECTED: [รายการสั่งแก้ 1, รายการสั่งแก้ 2...]
    - APPROVED: [JSON Final List ที่สมบูรณ์ที่สุด]
    """
    res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    return res.text

def run_team_c_d(final_data):
    """
    💰 Team C & D: QS & Foreman (ใช้ Key: QS)
    Brain: Price_List.csv
    """
    client = get_client("QS")
    kb_price = get_file_content("Price_List.csv")
    
    # 1. D ส่งรายละเอียดงาน (Method)
    prompt_d = f"""
    คุณคือ D (Foreman)
    ข้อมูลงาน: {final_data}
    หน้าที่: เขียน "Method Statement" ส่งให้ C คิดค่าแรง
    ระบุความยากง่ายและขั้นตอนการติดตั้งอย่างละเอียด
    """
    method_d = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_d).text
    
    # 2. C สรุปราคา 4 ตาราง
    prompt_c = f"""
    คุณคือ C (QS)
    หน้าที่: ทำ BOQ 4 ตาราง โดยใช้ราคาจาก CSV เท่านั้น
    
    --- Price List (CSV) ---
    {kb_price}
    ------------------------
    
    ข้อมูลงาน: {final_data}
    วิธีทำ (เพื่อประเมินค่าแรง): {method_d}
    
    คำสั่ง: สร้าง JSON Output สำหรับ 4 ตาราง:
    keys: [table_1_total, table_2_mat, table_3_lab, table_4_po]
    
    รายละเอียด:
    1. ค่าของ+ค่าแรง (Total)
    2. ค่าของ (Material Only)
    3. ค่าแรง (Labor Only - อิงจาก CSV หรือประเมินจากความยาก)
    4. PO (รายการสั่งซื้อ)
    """
    res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_c)
    try:
        return method_d, json.loads(res.text.replace("```json","").replace("```","").strip())
    except: return method_d, {"error": "JSON Error"}

# --- 4. MAIN UI ---
def main():
    st.title("🏗️ 6x6 Consensus System (3-Key Edition)")
    st.caption("Architecture: Double-Loop Verification | Multi-Brain RAG")
    
    # Check Files
    c1, c2, c3 = st.columns(3)
    with c1: 
        if "Missing" in get_file_content("Engineering_Drawings_EE.pdf"): st.error("❌ ขาดไฟล์ Engineering_Drawings_EE.pdf")
        else: st.success("✅ Architect Brain Ready")
    with c2:
        if "Missing" in get_file_content("วสท64_compressed.pdf"): st.warning("⚠️ ขาดไฟล์ วสท64 (จะใช้กฎทั่วไปแทน)")
        else: st.success("✅ Engineer Brain Ready")
    with c3:
        if "Missing" in get_file_content("Price_List.csv"): st.error("❌ ขาดไฟล์ Price_List.csv")
        else: st.success("✅ QS Brain Ready")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file and st.button("🚀 START OPERATION"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        # --- ROUND 1 ---
        st.info("🔄 Round 1: Initial Drafting & Audit")
        
        with st.spinner("Team A (Architects) is scanning..."):
            data_r1 = run_team_a(image, 1)
            if not data_r1: st.error("Team A failed to see objects."); st.stop()
            st.expander("Draft 1 Output").json(data_r1)
            
        with st.spinner("Team B (Engineers) is auditing..."):
            res_b1 = run_team_b(data_r1, 1)
            
        # บังคับเข้า Loop แก้ไขเสมอในรอบแรก (ตาม Logic ความรัดกุม)
        feedback = res_b1.replace("REJECTED:", "").strip()
        if "APPROVED" in res_b1: 
            feedback = "ตรวจสอบซ้ำอีกครั้งให้ละเอียดที่สุดเพื่อความแน่ใจ" # Force feedback even if approved
            
        st.warning(f"📝 **คำสั่งแก้ไขจาก Team B:**\n{feedback}")
        
        # --- ROUND 2 ---
        st.info("🔄 Round 2: Refinement & Finalization")
        
        with st.spinner("Team A is fixing defects..."):
            data_r2 = run_team_a(image, 2, feedback)
            
        with st.spinner("Team B is finalizing..."):
            res_b2 = run_team_b(data_r2, 2)
            
        # Extract Final Data
        try:
            json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
            final_verdict = json.loads(json_str.replace("```json","").replace("```","").strip())
            st.success("🏆 **Final Approved Draft:**")
            st.json(final_verdict)
        except:
            st.error("Error parsing final verdict")
            final_verdict = data_r2 # Fallback

        # --- EXECUTION ---
        st.markdown("---")
        st.header("🚀 Execution Phase (C & D)")
        
        with st.spinner("Processing Costs & Method Statement..."):
            method_d, boq_data = run_team_c_d(final_verdict)
            
            st.info(f"👷 **D (Foreman):**\n{method_d[:500]}...")
            
            if "error" not in boq_data:
                t1, t2, t3, t4 = st.tabs(["1. รวม (Total)", "2. ค่าของ (Mat)", "3. ค่าแรง (Lab)", "4. ใบสั่งซื้อ (PO)"])
                
                def show_tab(key):
                    if key in boq_data:
                        df = pd.DataFrame(boq_data[key])
                        st.dataframe(df, use_container_width=True)
                        # Calculate Total
                        cols = df.columns
                        if len(cols) > 0:
                            numeric_cols = df.select_dtypes(include=['number']).columns
                            target = next((x for x in cols if "รวม" in x or "Total" in x or "Amount" in x), numeric_cols[-1] if len(numeric_cols)>0 else None)
                            if target:
                                try: st.metric("Grand Total", f"{df[target].sum():,.2f} THB")
                                except: pass

                with t1: show_tab("table_1_total")
                with t2: show_tab("table_2_mat")
                with t3: show_tab("table_3_lab")
                with t4: show_tab("table_4_po")
            else:
                st.error("Agent C Calculation Error")

if __name__ == "__main__":
    main()
