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
st.set_page_config(page_title="MEP AI: Advanced System", layout="wide", page_icon="🏗️")

# 🔑 API KEY (ใส่ Key ของคุณ)
API_KEY = "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA"

# 🔥 AUTO-DETECT MODEL (ระบบเลือกโมเดลอัจฉริยะ)
def get_client_and_model():
    try:
        client = genai.Client(api_key=API_KEY)
        
        # รายชื่อโมเดลที่จะลอง (เรียงจากใหม่ไปเก่า)
        candidate_models = [
            'gemini-2.5-flash',      # ตัวใหม่ล่าสุดที่คุณต้องการ
            'gemini-1.5-flash',      # ตัวรองที่เร็ว
            'gemini-1.5-pro',        # ตัวฉลาด
            'gemini-1.0-pro'         # ตัวกันตาย
        ]
        
        for model_name in candidate_models:
            try:
                # ลองยิง Test เบาๆ
                client.models.generate_content(model=model_name, contents="Hi")
                return client, model_name # เจอตัวที่ใช้ได้ ส่งกลับเลย
            except:
                continue # ถ้าพัง ให้ลองตัวถัดไป
                
        return None, None
    except Exception as e:
        st.error(f"Client Init Error: {e}")
        return None, None

# เริ่มต้นระบบเชื่อมต่อ AI
with st.spinner("🤖 กำลังจูนเครื่องยนต์ AI (ค้นหาโมเดลที่ดีที่สุด)..."):
    client, MODEL_ID = get_client_and_model()

if not client:
    st.error("🚨 Critical Error: ไม่สามารถเชื่อมต่อกับ Google AI ได้เลยทุกโมเดล (เช็ค API Key หรือโควต้า)")
    st.stop()
else:
    st.success(f"✅ เชื่อมต่อสำเร็จ! ระบบเลือกใช้งานโมเดล: **{MODEL_ID}**")

# --- 2. HELPER FUNCTIONS (ฟังก์ชันกลาง) ---
def generate_content(prompt_text, image=None):
    """เรียก AI ด้วยโมเดลที่เลือกมาแล้ว"""
    try:
        if image:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=[prompt_text, image]
            )
        else:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt_text
            )
        return response.text
    except Exception as e:
        return f"Error generation: {e}"

# --- 3. KNOWLEDGE BASE FUNCTIONS ---
def get_manual_content():
    """อ่านคู่มือ PDF"""
    manual_path = "Manuals"
    text = ""
    if os.path.exists(manual_path):
        for f in os.listdir(manual_path):
            if f.endswith(".pdf"):
                try:
                    reader = PdfReader(os.path.join(manual_path, f))
                    # อ่าน 20 หน้าแรก
                    for i, page in enumerate(reader.pages[:20]): 
                        text += page.extract_text() + "\n"
                except: pass
    return text if text else "ไม่พบคู่มือ PDF (ใช้กฎพื้นฐาน)"

def get_price_list_content():
    """อ่านบัญชีราคา CSV"""
    manual_path = "Manuals"
    csv_file = os.path.join(manual_path, "Price_List.csv")
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            return df.to_markdown(index=False)
        except: return "Error reading CSV"
    return "ไม่พบไฟล์ Price_List.csv"

# --- 4. AGENT PROMPTS (6x6 Logic) ---

def run_agent_a_group(image):
    """ทีม A: สถาปนิก 6 คน (จำลองด้วย AI ตัวเดียวเพื่อความเร็ว)"""
    legend = "Legend: Circle+X=Downlight, Rect=Fluorescent, Circle+Lines=Outlet, S=Switch"
    
    prompt = f"""
    คุณคือทีมสถาปนิก 6 คน ช่วยกันถอดแบบไฟฟ้าจากภาพนี้
    อ้างอิงสัญลักษณ์: {legend}
    
    คำสั่ง:
    1. กวาดสายตาทั่วแบบ (Grid Scan)
    2. อ่าน Text ที่กำกับอุปกรณ์ (Text Reader)
    3. วิเคราะห์ตามบริบทห้อง (Context)
    
    สรุปรายการอุปกรณ์ทั้งหมดออกมาเป็น JSON List:
    [
      {{"room": "Living Room", "item": "Downlight", "spec": "9W LED", "qty": 4}},
      {{"room": "Bathroom", "item": "Waterproof Outlet", "spec": "IP44", "qty": 1}}
    ]
    """
    try:
        text_resp = generate_content(prompt, image)
        clean_json = text_resp.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except: return []

def run_agent_b_group(data):
    """ทีม B: วิศวกรตรวจสอบ"""
    manual = get_manual_content()
    prompt = f"""
    คุณคือทีมวิศวกรตรวจสอบ 6 คน (Safety, Standard, Design, Spec, Load, Chief)
    
    --- กฎหมายและมาตรฐาน (PDF) ---
    {manual[:10000]}...
    -----------------------------
    
    ข้อมูลหน้างาน: {json.dumps(data, ensure_ascii=False)}
    
    คำสั่ง: 
    ตรวจสอบรายการทั้งหมดว่า "ผ่าน" หรือ "ไม่ผ่าน" ตามคู่มือ
    ถ้าผ่าน ตอบ "APPROVED"
    ถ้าไม่ผ่าน ตอบ "REJECTED: [ระบุสาเหตุและวิธีแก้]"
    """
    return generate_content(prompt)

def run_agent_c_d(data):
    """ทีม C & D: คิดเงินและสั่งงาน"""
    price_list = get_price_list_content()
    
    # D: เขียนวิธีทำ
    prompt_d = f"เขียน 'วิธีทำ (Method Statement)' สำหรับช่าง จากข้อมูล: {json.dumps(data, ensure_ascii=False)}"
    method = generate_content(prompt_d)
    
    # C: คิดเงิน
    prompt_c = f"""
    คุณคือ C (QS). ทำ BOQ 4 ตาราง โดยใช้ราคาจาก CSV เท่านั้น.
    
    --- บัญชีราคากลาง (CSV) ---
    {price_list}
    ---------------------------
    
    ข้อมูล: {json.dumps(data, ensure_ascii=False)}
    วิธีทำ: {method}
    
    คำสั่ง: สร้าง JSON Data สำหรับ 4 ตาราง:
    Output JSON Keys: [Table_Total, Table_Material, Table_Labor, Table_PO]
    """
    try:
        text_resp = generate_content(prompt_c)
        boq = json.loads(text_resp.replace("```json", "").replace("```", "").strip())
    except: boq = {"error": "JSON Error"}
    
    return method, boq

# --- 5. MAIN UI ---
def main():
    st.title(f"🚀 MEP AI System (Engine: {MODEL_ID})")
    
    # Check Files Status
    c1, c2 = st.columns(2)
    with c1:
        if "Price_List.csv" in get_price_list_content(): st.error("⚠️ Missing Price_List.csv")
        else: st.success("✅ Price DB Connected")
    with c2:
        if "ไม่พบ" in get_manual_content(): st.warning("⚠️ Missing PDF Manual")
        else: st.success("✅ Engineering DB Connected")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file and st.button("🚀 รันระบบเต็มรูปแบบ"):
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        # Phase 1: A
        st.header("1. ทีมสถาปนิก (A) ถอดแบบ")
        with st.spinner("กำลังสแกนแบบ..."):
            data = run_agent_a_group(image)
            st.json(data)
            
        # Phase 2: B
        st.header("2. ทีมวิศวกร (B) ตรวจสอบ")
        with st.spinner("กำลังตรวจมาตรฐาน..."):
            res_b = run_agent_b_group(data)
            if "APPROVED" in res_b:
                st.success(f"🏆 ผลตรวจ: {res_b}")
                
                # Phase 3: C & D
                st.markdown("---")
                st.header("3. สรุปราคาและสั่งงาน")
                with st.spinner("กำลังคำนวณราคา..."):
                    method, boq = run_agent_c_d(data)
                    
                    st.info(f"👷 **คู่มือช่าง:**\n{method[:300]}...")
                    
                    if "error" not in boq:
                        tab1, tab2, tab3, tab4 = st.tabs(["รวม", "ค่าของ", "ค่าแรง", "PO"])
                        def show_df(key):
                            if key in boq:
                                df = pd.DataFrame(boq[key])
                                st.dataframe(df, use_container_width=True)
                                if 'Total' in df.columns: st.metric("รวม", f"{df['Total'].sum():,.2f}")
                        
                        with tab1: show_df("Table_Total")
                        with tab2: show_df("Table_Material")
                        with tab3: show_df("Table_Labor")
                        with tab4: show_df("Table_PO")
            else:
                st.error(f"❌ แบบไม่ผ่าน: {res_b}")

if __name__ == "__main__":
    main()
