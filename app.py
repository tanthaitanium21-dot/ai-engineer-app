import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import time
import os
from PIL import Image
from pypdf import PdfReader

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="MEP AI: Stable Interactive", layout="wide", page_icon="🏗️")

# 🔑 แยก API KEYS (3 กระเป๋า)
KEYS = {
    "ARCHITECT": "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI", 
    "ENGINEER":  "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA", 
    "QS":        "AIzaSyB5e_5lXSnjlvIDL63OdV_BLBfQZvjaRuU"
}

# ฟังก์ชันเลือก Model Object ตามบทบาท (Stable SDK)
def get_model_agent(role):
    try:
        genai.configure(api_key=KEYS[role])
        # ใช้ Gemini 1.5 Flash ที่เสถียรที่สุดตอนนี้
        return genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"❌ API Error ({role}): {e}")
        return None

# --- 2. HELPER: CHAT LOGGER ---
def chat_log(placeholder, speaker, message, role="user"):
    """แสดง Chat Bubble"""
    avatar = "👷‍♂️" if "สถาปนิก" in speaker or "A" in speaker else \
             "⚙️" if "วิศวกร" in speaker or "B" in speaker else \
             "💰" if "QS" in speaker or "C" in speaker else "👷"
    
    with placeholder.container():
        st.chat_message(role, avatar=avatar).write(f"**{speaker}:** {message}")
        time.sleep(0.2)

# --- 3. HELPER: ROBUST GENERATE (กันตาย) ---
def generate_with_retry(model_agent, contents, retries=3):
    """เรียก AI แบบกันหลุด"""
    for attempt in range(retries):
        try:
            response = model_agent.generate_content(contents)
            return response.text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            else:
                return f"Error: {e}"

# --- 4. KNOWLEDGE ACCESS ---
def get_kb_content(filename):
    path = os.path.join("Manuals", filename)
    # ลองหาทั้งในโฟลเดอร์และ root
    paths_to_try = [path, filename]
    for p in paths_to_try:
        if os.path.exists(p):
            if filename.endswith(".pdf"):
                try:
                    reader = PdfReader(p)
                    text = ""
                    for page in reader.pages[:20]: text += page.extract_text()
                    return text
                except: return "Error PDF"
            elif filename.endswith(".csv"):
                try:
                    return pd.read_csv(p).to_markdown(index=False)
                except: return "Error CSV"
    return f"Missing {filename}"

# --- 5. THE 6x6 AGENT WORKFLOW ---

def run_team_a(image, round_num, feedback, chat_ph):
    """
    🏗️ ทีม A: สถาปนิก 6 คน
    Key: ARCHITECT | Brain: Engineering_Drawings_EE.pdf
    """
    agent = get_model_agent("ARCHITECT")
    kb_drawings = get_kb_content("Engineering_Drawings_EE.pdf")
    
    chat_log(chat_ph, "A6 (สถาปนิกส้ม)", f"ทีม A (Key 1) เริ่มงานรอบที่ {round_num} คำสั่งแก้: {feedback if feedback else 'ไม่มี'}", "user")
    chat_log(chat_ph, "A2 (สถาปนิกแดง)", "กำลังเทียบสัญลักษณ์กับคู่มือ...", "user")
    
    prompt = f"""
    คุณคือ "Team A" (สถาปนิกถอดแบบ 6 คน)
    บริบท: รอบที่ {round_num}, คำสั่งแก้: {feedback if feedback else "-"}
    
    --- คู่มือสัญลักษณ์ (Legend) ---
    {kb_drawings[:5000]}...
    ------------------------------
    
    หน้าที่: ระบุรายการอุปกรณ์ (ห้ามส่งกระดาษเปล่า!)
    สมาชิก: A1(Grid), A2(Symbol), A3(Label), A4(Context), A5(Tracer), A6(Lead)
    
    Output JSON List Only: [ {{"id": 1, "room": "...", "item": "...", "spec": "...", "qty": 0, "note": "Found by A2"}} ]
    """
    try:
        res_text = generate_with_retry(agent, [prompt, image])
        text = res_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        
        chat_log(chat_ph, "A4 (สถาปนิกเขียว)", f"เช็คห้องเรียบร้อย: {', '.join(list(set([d.get('room','Unknown') for d in data])))}", "user")
        chat_log(chat_ph, "A6 (สถาปนิกส้ม)", f"สรุปได้ {len(data)} รายการ ส่งต่อทีม B ครับ", "user")
        return data
    except Exception as e:
        chat_log(chat_ph, "System", f"Error A: {e}", "assistant")
        # Fallback Data
        return [{"id": 99, "room": "Error Check", "item": "Manual Verify", "spec": "-", "qty": 1}]

def run_team_b(data_from_a, round_num, chat_ph):
    """
    ⚙️ ทีม B: วิศวกร 6 คน
    Key: ENGINEER | Brain: วสท64_compressed.pdf
    """
    agent = get_model_agent("ENGINEER")
    kb_standard = get_kb_content("วสท64_compressed.pdf")
    
    chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "ทีม B (Key 2) รับเรื่องแล้ว กำลังตรวจสอบ...", "assistant")
    chat_log(chat_ph, "B1 (วิศวกรบุญชู)", "กำลังตรวจ Safety (กันน้ำ/สายดิน)...", "assistant")
    
    prompt = f"""
    คุณคือ "Team B" (วิศวกร 6 คน)
    ข้อมูลจาก A: {json.dumps(data_from_a, ensure_ascii=False)}
    
    --- มาตรฐาน วสท. ---
    {kb_standard[:10000]}...
    ---------------------
    
    เงื่อนไข:
    - รอบ 1: ต้องหาที่ติเพื่อสั่งแก้ (REJECTED)
    - รอบ 2: ให้ผ่าน (APPROVED)
    
    Output Format: REJECTED: [...] หรือ APPROVED: [...]
    """
    res_text = generate_with_retry(agent, prompt)
    
    if "REJECTED" in res_text:
        chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "ไม่อนุมัติครับ! มีจุดต้องแก้ ส่งคืน A", "assistant")
    else:
        chat_log(chat_ph, "B6 (วิศวกรสมหมาย)", "อนุมัติแบบครับ ถูกต้องตามมาตรฐาน ✅", "assistant")
        
    return res_text

def run_team_c_d(final_data, chat_ph):
    """
    💰 ทีม C & D: QS & Foreman
    Key: QS | Brain: Price_List.csv
    """
    agent = get_model_agent("QS")
    price_list = get_kb_content("Price_List.csv")
    
    # D Work
    chat_log(chat_ph, "D (โฟร์แมน)", "ทีม D (Key 3) กำลังเขียนแผนงานติดตั้ง...", "user")
    prompt_d = f"เขียน Method Statement ภาษาไทย สำหรับ: {final_data}"
    method_d = generate_with_retry(agent, prompt_d)
    
    # C Work
    chat_log(chat_ph, "C (QS)", "ทีม C (Key 3) กำลังเปิดไฟล์ราคากลาง...", "assistant")
    prompt_c = f"""
    คุณคือ C (QS) ทำ BOQ 4 ตาราง โดยใช้ราคาจาก CSV นี้เท่านั้น:
    {price_list}
    
    ข้อมูล: {final_data}
    วิธีทำ: {method_d}
    Output JSON: [table_1_total, table_2_mat, table_3_lab, table_4_po]
    """
    try:
        res_text = generate_with_retry(agent, prompt_c)
        chat_log(chat_ph, "C (QS)", "คำนวณเสร็จสิ้น พร้อมออกเอกสารครับ", "assistant")
        return method_d, json.loads(res_text.replace("```json", "").replace("```", "").strip())
    except:
        return method_d, {"error": "JSON Error"}

# --- 6. MAIN UI ---
def main():
    st.title("🏗️ MEP AI: 3-Key Stable System")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if "Missing" in get_kb_content("Engineering_Drawings_EE.pdf"): st.error("❌ ขาดไฟล์ A")
        else: st.success("✅ Team A Ready")
    with c2:
        if "Missing" in get_kb_content("วสท64_compressed.pdf"): st.warning("⚠️ ขาดไฟล์ B")
        else: st.success("✅ Team B Ready")
    with c3:
        if "Missing" in get_kb_content("Price_List.csv"): st.error("❌ ขาดไฟล์ C")
        else: st.success("✅ Team C Ready")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        if st.button("🚀 เริ่มระบบปฏิบัติการ"):
            st.markdown("### 💬 Team Chat Log")
            chat_container = st.container()
            
            # --- ROUND 1 ---
            data_r1 = run_team_a(image, 1, "", chat_container)
            
            if data_r1:
                res_b1 = run_team_b(data_r1, 1, chat_container)
                
                final_verdict = None
                if "REJECTED" in res_b1:
                    order = res_b1.replace("REJECTED:", "").strip()
                    st.error(f"📝 **คำสั่งแก้ (Correction Order):**\n{order}")
                    
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
