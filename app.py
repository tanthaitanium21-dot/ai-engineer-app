import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import time
import os
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURATION & ROBUST SETUP ---
st.set_page_config(page_title="AI Engineer: Universal Mode", layout="wide", page_icon="🛡️")

# 🔑 API KEY (ใส่ Key ของคุณ)
API_KEY = "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI"

# ฟังก์ชันเลือกโมเดลอัตโนมัติ (กันตาย)
def get_working_model(api_key):
    genai.configure(api_key=api_key)
    
    # รายชื่อโมเดลที่จะไล่เช็ค (จากใหม่ไปเก่า)
    candidate_models = [
        'gemini-1.5-flash', 
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro',
        'gemini-1.5-pro-latest',
        'gemini-pro',       # รุ่นมาตรฐาน (เสถียรสุด)
        'gemini-1.0-pro'
    ]
    
    status_text = []
    active_model = None
    
    # วนลูปหาตัวที่ใช้ได้
    for model_name in candidate_models:
        try:
            # ลอง Test ยิงคำถามง่ายๆ
            test_model = genai.GenerativeModel(model_name)
            response = test_model.generate_content("Hi")
            if response:
                active_model = test_model
                status_text.append(f"✅ {model_name}: ใช้งานได้!")
                break # เจอแล้วหยุดหา
        except Exception as e:
            status_text.append(f"❌ {model_name}: ใช้ไม่ได้ ({str(e)[:50]}...)")
            
    return active_model, status_text

# เริ่มต้นระบบเลือกโมเดล
with st.spinner("🤖 กำลังค้นหาโมเดล AI ที่ดีที่สุดสำหรับ Server นี้..."):
    model, model_logs = get_working_model(API_KEY)

# --- 2. KNOWLEDGE BASE FUNCTIONS ---

def get_manual_content():
    """อ่านคู่มือ PDF จาก GitHub"""
    manual_path = "Manuals"
    text = ""
    if os.path.exists(manual_path):
        for f in os.listdir(manual_path):
            if f.endswith(".pdf"):
                try:
                    reader = PdfReader(os.path.join(manual_path, f))
                    # อ่านแค่ 20 หน้าแรกเพื่อความรวดเร็ว
                    for i, page in enumerate(reader.pages[:20]): 
                        text += page.extract_text() + "\n"
                except: pass
    return text if text else "ไม่พบคู่มือ PDF (ใช้กฎพื้นฐาน)"

def get_price_list_content():
    """อ่านบัญชีราคา CSV จาก GitHub"""
    manual_path = "Manuals"
    csv_file = os.path.join(manual_path, "Price_List.csv")
    
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            return df.to_markdown(index=False)
        except Exception as e:
            return f"Error reading CSV: {e}"
    return "ไม่พบไฟล์ Price_List.csv"

# --- 3. AGENT PROMPTS (THE 6x6 SYSTEM) ---

def run_agent_a_group(image):
    """ทีม A: สถาปนิก 6 คน"""
    if not model: return {"Error": "AI Model not found"}
    
    legend = "Legend: Circle+X=Downlight, Rect=Fluorescent, Circle+Lines=Outlet"
    prompts = {
        "A1 (Grid Scanner)": f"แบ่งภาพเป็นส่วนๆ ค้นหาอุปกรณ์ไฟฟ้าละเอียด อ้างอิง: {legend}",
        "A2 (Symbol Matcher)": f"ค้นหาเฉพาะสัญลักษณ์ที่ตรงกับ Legend: {legend}",
        "A3 (Text Reader)": "อ่าน Text Label ที่กำกับอุปกรณ์ (เช่น 'WP', 'TV')",
        "A4 (Context Analyzer)": "วิเคราะห์ตามบริบทห้อง (เช่น ห้องน้ำ, ครัว)",
        "A5 (Line Tracer)": "ไล่เส้นสายไฟหาปลายทาง",
        "A6 (Consolidator)": "รวมข้อมูลจาก A1-A5 ตัดตัวซ้ำ สรุปยอดเป็น JSON"
    }
    
    results = {}
    progress = st.progress(0)
    idx = 0
    
    for name, p in prompts.items():
        try:
            response = model.generate_content([p, image])
            results[name] = response.text
        except Exception as e:
            results[name] = f"Error: {e}"
        idx += 1
        progress.progress(idx / 6)
        time.sleep(1)
        
    return results

def run_agent_b_group(a_results):
    """ทีม B: วิศวกร 6 คน"""
    if not model: return {"Error": "AI Model not found"}
    
    consolidated_data = a_results.get("A6 (Consolidator)", str(a_results))
    real_manual = get_manual_content()
    
    prompts = {
        "B1 (Safety)": "ตรวจความปลอดภัย (กันน้ำ, สายดิน, เบรกเกอร์)",
        "B2 (Standard)": "ตรวจมาตรฐานติดตั้ง (ความสูง, ระยะห่าง)",
        "B3 (Design)": "ตรวจความสมเหตุสมผลการใช้งาน",
        "B4 (Spec Check)": "ตรวจสเปควัสดุเทียบตลาด",
        "B5 (Load Calc)": "คำนวณโหลดไฟฟ้าคร่าวๆ",
        "B6 (Chief Engineer)": "สรุป Final Draft เพื่อส่งต่อ QS"
    }
    
    results = {}
    progress = st.progress(0)
    idx = 0
    
    for name, p in prompts.items():
        full_prompt = f"""
        บทบาท: {name}
        Manual Ref: {real_manual[:10000]}...
        Data: {consolidated_data}
        คำสั่ง: ตรวจสอบและให้ความเห็น (Approved/Rejected)
        """
        try:
            response = model.generate_content(full_prompt)
            results[name] = response.text
        except Exception as e:
            results[name] = f"Error: {e}"
        idx += 1
        progress.progress(idx / 6)
        
    return results

def run_agent_c_d(final_draft):
    """ทีม C & D: คิดเงินและสั่งงาน"""
    if not model: return "Error", "Error"
    
    real_price_list = get_price_list_content()
    
    # D ทำงาน
    prompt_d = f"เขียน 'วิธีทำ (Method Statement)' สำหรับช่าง จากข้อมูล: {final_draft}"
    try:
        method_d = model.generate_content(prompt_d).text
    except: method_d = "Error generating Manual"

    # C ทำงาน
    prompt_c = f"""
    คุณคือ C (QS). ทำ BOQ 4 ตาราง โดยใช้ราคาจาก CSV เท่านั้น.
    Price List: {real_price_list}
    Data: {final_draft}
    Method: {method_d}
    Output Format: JSON with keys [Table_Total, Table_Material, Table_Labor, Table_PO]
    """
    try:
        response_c = model.generate_content(prompt_c)
        boq_data = json.loads(response_c.text.replace("```json", "").replace("```", "").strip())
    except:
        boq_data = {"error": "JSON Error"}
        
    return method_d, boq_data

# --- 4. MAIN APP UI ---
def main():
    st.title("🛡️ AI Engineer: Universal Version")
    
    # Debugging Section (ซ่อนได้)
    with st.expander("🛠️ System Status & Debugging Logs"):
        st.write(f"**Python Library Version:** `google-generativeai {genai.__version__}`")
        st.write("**Model Connection Check:**")
        for log in model_logs:
            if "✅" in log: st.success(log)
            else: st.error(log)
            
    if not model:
        st.error("🚨 Critical Error: ไม่สามารถเชื่อมต่อ Google AI ได้เลยทุกโมเดล กรุณาเช็ค API Key")
        st.stop()
    else:
        st.info("🟢 System Online: พร้อมทำงานด้วยโมเดลที่เสถียรที่สุด")

    # File Checks
    c1, c2 = st.columns(2)
    with c1:
        if "Price_List.csv" in get_price_list_content(): st.error("⚠️ Missing Price_List.csv")
        else: st.success("✅ Price DB Connected")
    with c2:
        if "ไม่พบ" in get_manual_content(): st.warning("⚠️ Missing PDF Manual")
        else: st.success("✅ Engineering DB Connected")

    # Upload
    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])

    if uploaded_file and st.button("🚀 รันระบบ 6x6 Agents"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        # Phase 1: A
        st.header("1. ทีมสถาปนิก 6 คน (A1-A6)")
        a_results = run_agent_a_group(image)
        for k,v in a_results.items(): st.write(f"**{k}:** {v[:100]}...")
            
        # Phase 2: B
        st.header("2. ทีมวิศวกร 6 คน (B1-B6)")
        b_results = run_agent_b_group(a_results)
        final_verdict = b_results.get("B6 (Chief Engineer)", "")
        st.success(f"🏆 Final Verdict:\n{final_verdict}")

        # Phase 3: C & D
        st.header("3. สรุปราคาและสั่งงาน")
        with st.spinner("กำลังคำนวณราคาและเขียนคู่มือ..."):
            method_d, boq_data = run_agent_c_d(final_verdict)
            
            st.info(f"👷 **Method Statement:**\n{method_d[:300]}...")
            
            if "error" not in boq_data:
                tab1, tab2, tab3, tab4 = st.tabs(["Total", "Material", "Labor", "PO"])
                def show_df(key):
                    if key in boq_data:
                        df = pd.DataFrame(boq_data[key])
                        st.dataframe(df, use_container_width=True)
                        if 'Total' in df.columns: st.metric("รวม", f"{df['Total'].sum():,.2f}")
                
                with tab1: show_df("Table_Total")
                with tab2: show_df("Table_Material")
                with tab3: show_df("Table_Labor")
                with tab4: show_df("Table_PO")

if __name__ == "__main__":
    main()
