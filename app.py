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
st.set_page_config(page_title="MEP AI: Interactive Team", layout="wide", page_icon="🏗️")

# 🔑 API KEY
API_KEY = "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA"

try:
    client = genai.Client(api_key=API_KEY)
    MODEL_ID = "gemini-2.5-flash"
    client.models.generate_content(model=MODEL_ID, contents="Ping")
except:
    MODEL_ID = "gemini-1.5-flash"
    client = genai.Client(api_key=API_KEY)

# --- 2. HELPER: CHAT LOGGER ---
def chat_log(placeholder, speaker, message, role="user"):
    """แสดงข้อความแบบ Chat Bubble"""
    avatar = "👷‍♂️" if "A" in speaker else "⚙️" if "B" in speaker else "💰" if "C" in speaker else "👷"
    
    with placeholder.container():
        st.chat_message(role, avatar=avatar).write(f"**{speaker}:** {message}")
        time.sleep(0.3) # หน่วงเวลาให้อ่านทัน

# --- 3. KNOWLEDGE ACCESS ---
def get_kb_content(filename):
    path = os.path.join("Manuals", filename)
    # Fallback checks... (เหมือนเดิม)
    paths_to_try = [path, filename]
    for p in paths_to_try:
        if os.path.exists(p):
            if filename.endswith(".pdf"):
                try:
                    reader = PdfReader(p)
                    text = ""
                    for p in reader.pages[:20]: text += p.extract_text()
                    return text
                except: return "Error PDF"
            elif filename.endswith(".csv"):
                try:
                    return pd.read_csv(p).to_markdown(index=False)
                except: return "Error CSV"
    return f"Missing {filename}"

# --- 4. AGENT WORKFLOW WITH Q&A ---

def run_team_a(image, round_num, feedback, chat_ph):
    """Team A: Mining"""
    legend_ref = """[Ref: Circle+X=Downlight, Rect=Fluorescent, Circle+2lines=Duplex, +WP=Waterproof, S=Switch]"""
    
    # Simulate Team Discussion
    chat_log(chat_ph, "A6 (สถาปนิกส้ม)", f"ทุกคนครับ! เริ่มงานรอบที่ {round_num} ครับ คำสั่งแก้: {feedback if feedback else 'ไม่มี'}", "user")
    chat_log(chat_ph, "A1 (สถาปนิกดำ)", "รับทราบครับ ผมกำลังแบ่ง Grid สแกนพื้นที่...", "user")
    chat_log(chat_ph, "A2 (สถาปนิกแดง)", f"ผมเตรียมโพยแล้วครับ: {legend_ref}", "user")
    
    prompt = f"""
    คุณคือ "Team A" (สถาปนิก 6 คน)
    บริบท: รอบที่ {round_num}, คำสั่งแก้: {feedback if feedback else "-"}
    
    หน้าที่: ระบุรายการอุปกรณ์ (ห้ามส่งกระดาษเปล่า!)
    สมาชิก: A1(Grid), A2(Symbol), A3(Label), A4(Context), A5(Tracer), A6(Lead)
    
    Output JSON: [ {{"id": 1, "room": "...", "item": "...", "spec": "...", "qty": 0, "note": "Found by A2"}} ]
    """
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=[prompt, image])
        text = res.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        
        chat_log(chat_ph, "A4 (สถาปนิกเขียว)", f"ผมเช็คห้องแล้วครับ เจอบริบทห้อง: {', '.join(list(set([d['room'] for d in data])))}", "user")
        chat_log(chat_ph, "A6 (สถาปนิกส้ม)", f"สรุปยอดรวมได้ {len(data)} รายการครับ ส่งให้ทีมวิศวกรเลยนะครับ", "user")
        
        return data
    except Exception as e:
        chat_log(chat_ph, "System", f"Error A: {e}", "assistant")
        return [{"id": 99, "room": "Error", "item": "Manual Check", "spec": "-", "qty": 1}]

def run_team_b(data_from_a, round_num, chat_ph):
    """Team B: Auditing"""
    manual = get_kb_content("Engineering_Drawings_EE.pdf")
    
    chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "ได้รับข้อมูลแล้วครับ ทีม B ประจำสถานี!", "assistant")
    chat_log(chat_ph, "B1 (วิศวกรบุญชู)", "กำลังตรวจความปลอดภัย... ห้องน้ำต้องกันน้ำเท่านั้นนะ", "assistant")
    chat_log(chat_ph, "B2 (วิศวกรสมชาย)", "กำลังเปิดคู่มือมาตรฐานเทียบครับ...", "assistant")
    
    prompt = f"""
    คุณคือ "Team B" (วิศวกร 6 คน)
    ข้อมูลจาก A: {json.dumps(data_from_a, ensure_ascii=False)}
    คู่มือ: {manual[:5000]}...
    
    เงื่อนไข:
    - รอบ 1: ต้องหาที่ติเพื่อสั่งแก้ (REJECTED)
    - รอบ 2: ให้ผ่าน (APPROVED)
    
    Output Format: REJECTED: [...] หรือ APPROVED: [...]
    """
    res = client.models.generate_content(model=MODEL_ID, contents=prompt)
    
    if "REJECTED" in res.text:
        chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "มีจุดต้องแก้ครับ! ส่งคืนทีม A เดี๋ยวนี้", "assistant")
    else:
        chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "ตรวจสอบแล้วถูกต้องครับ อนุมัติแบบได้ ✅", "assistant")
        
    return res.text

def run_team_c_d(final_data, chat_ph):
    """Team C & D"""
    price_list = get_kb_content("Price_List.csv")
    
    # D Work
    chat_log(chat_ph, "D (โฟร์แมน)", "รับทราบครับ ผมกำลังเขียนแผนงานติดตั้งให้...", "user")
    prompt_d = f"เขียน Method Statement ภาษาไทย สำหรับ: {final_data}"
    method_d = client.models.generate_content(model=MODEL_ID, contents=prompt_d).text
    chat_log(chat_ph, "D (โฟร์แมน)", "แผนงานเสร็จแล้วครับ ส่งต่อให้ฝ่ายบัญชี", "user")
    
    # C Work
    chat_log(chat_ph, "C (QS)", "กำลังดึงราคาจาก CSV... (คิดค่าของ+ค่าแรง)", "assistant")
    prompt_c = f"""
    คุณคือ C (QS) ทำ BOQ 4 ตาราง
    ราคา: {price_list}
    ข้อมูล: {final_data}
    วิธีทำ: {method_d}
    Output JSON: [table_1_total, table_2_mat, table_3_lab, table_4_po]
    """
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt_c)
        chat_log(chat_ph, "C (QS)", "คำนวณเสร็จสิ้นครับ ออกใบ BOQ ได้เลย", "assistant")
        return method_d, json.loads(res.text.replace("```json", "").replace("```", "").strip())
    except:
        return method_d, {"error": "JSON Error"}

# --- 5. MAIN UI ---
def main():
    st.title(f"🏗️ MEP AI: Interactive Operation")
    
    # Files
    c1, c2 = st.columns(2)
    with c1: 
        if "Missing" in get_kb_content("Price_List.csv"): st.error("Price List Not Found")
        else: st.success("Price DB: OK")
    with c2:
        if "Missing" in get_kb_content("Engineering_Drawings_EE.pdf"): st.warning("Manual Not Found")
        else: st.success("Manual DB: OK")

    uploaded_file = st.file_uploader("📂 Upload Blueprint", type=['png', 'jpg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        if st.button("🚀 Start Interactive Mission"):
            # Chat Container
            st.markdown("### 💬 Team Chat Room")
            chat_container = st.container()
            
            # --- ROUND 1 ---
            data_r1 = run_team_a(image, 1, "", chat_container)
            
            if data_r1:
                res_b1 = run_team_b(data_r1, 1, chat_container)
                
                final_verdict = None
                if "REJECTED" in res_b1:
                    order = res_b1.replace("REJECTED:", "").strip()
                    st.error(f"📝 **Correction Order:**\n{order}")
                    
                    # --- ROUND 2 ---
                    data_r2 = run_team_a(image, 2, res_b1, chat_container)
                    res_b2 = run_team_b(data_r2, 2, chat_container)
                    
                    try:
                        json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
                        final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                    except:
                        st.error("Error Parsing Final")
                else:
                    try:
                        json_str = res_b1.split("APPROVED:")[1].strip() if "APPROVED:" in res_b1 else res_b1
                        final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                    except:
                        final_verdict = data_r1

                # --- EXECUTION ---
                if final_verdict:
                    st.success("🏆 **Final Approved!**")
                    st.markdown("---")
                    
                    method_d, boq_data = run_team_c_d(final_verdict, chat_container)
                    
                    st.info(f"👷 **Method Statement:**\n{method_d[:500]}...")
                    
                    if "error" not in boq_data:
                        t1, t2, t3, t4 = st.tabs(["Total", "Material", "Labor", "PO"])
                        def show(key):
                            if key in boq_data:
                                df = pd.DataFrame(boq_data[key])
                                st.dataframe(df, use_container_width=True)
                                if 'รวมเป็นเงิน' in df.columns: 
                                    total = df['รวมเป็นเงิน'].astype(str).str.replace(',','').astype(float).sum()
                                    st.metric("Total", f"{total:,.2f}")

                        with t1: show("table_1_total")
                        with t2: show("table_2_mat")
                        with t3: show("table_3_lab")
                        with t4: show("table_4_po")

if __name__ == "__main__":
    main()
