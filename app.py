import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import time
import os
import io
from PIL import Image
from pypdf import PdfReader
import fitz  # PyMuPDF (For Visual PDF Reading)

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="MEP AI: The Final Execution", layout="wide", page_icon="🏗️")

# 🔑 API KEYS (ฝังตามคำสั่ง)
KEYS = {
    "ARCHITECT": "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI", 
    "ENGINEER":  "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA", 
    "QS":        "AIzaSyB5e_5lXSnjlvIDL63OdV_BLBfQZvjaRuU"
}

def get_model(role):
    try:
        genai.configure(api_key=KEYS[role])
        # พยายามใช้โมเดลใหม่ล่าสุด ถ้าไม่ได้ให้ถอยกลับมาตัวเสถียร
        return genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"❌ API Error ({role}): {e}")
        return None

# --- 2. HELPER: CHAT LOG ---
def chat_log(placeholder, speaker, message, role="user"):
    avatar = "👷‍♂️" if "สถาปนิก" in speaker else "⚙️" if "วิศวกร" in speaker else "💰" if "QS" in speaker else "👷"
    with placeholder.container():
        st.chat_message(role, avatar=avatar).write(f"**{speaker}:** {message}")
        time.sleep(0.1)

# --- 3. INTELLIGENT KNOWLEDGE ACCESS ---
def get_pdf_images(filename, limit=5):
    """แปลง PDF เป็นรูปภาพ เพื่อให้ A มองเห็นสัญลักษณ์"""
    path = os.path.join("Manuals", filename)
    images = []
    if os.path.exists(path):
        try:
            doc = fitz.open(path)
            for i in range(min(len(doc), limit)): # อ่าน 5 หน้าแรกที่เป็น Legend
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                images.append(Image.open(io.BytesIO(img_data)))
        except: pass
    return images

def get_text_content(filename):
    """อ่าน Text จาก PDF/CSV"""
    path = os.path.join("Manuals", filename)
    if os.path.exists(path):
        if filename.endswith(".pdf"):
            try:
                reader = PdfReader(path)
                text = ""
                for p in reader.pages[:30]: text += p.extract_text()
                return text
            except: return "Error Reading PDF"
        elif filename.endswith(".csv"):
            try: return pd.read_csv(path).to_markdown(index=False)
            except: return "Error Reading CSV"
    return f"Missing {filename}"

# --- 4. AGENT WORKFLOW ---

def run_team_a(image, round_num, feedback, chat_ph):
    """Team A: สถาปนิก (Visual Mode)"""
    model = get_model("ARCHITECT")
    
    # โหลดคู่มือแบบรูปภาพ
    legend_imgs = get_pdf_images("Engineering_Drawings_EE.pdf")
    
    chat_log(chat_ph, "A6 สถาปนิกส้ม", f"เริ่มงานรอบที่ {round_num} ครับ (โหลดคู่มือรูปภาพ {len(legend_imgs)} หน้า)...", "user")
    
    prompt = f"""
    คุณคือ "Team A" ทีมสถาปนิกถอดแบบ 6 คน
    บริบท: รอบที่ {round_num}, คำสั่งแก้: {feedback if feedback else "-"}
    
    **คำสั่งพิเศษ:** ฉันแนบ "รูปภาพคู่มือสัญลักษณ์" ไปให้ด้วย 
    ให้คุณเทียบรูปร่างอุปกรณ์ในแบบแปลน กับรูปในคู่มือให้แม่นยำที่สุด
    
    สมาชิกทีม:
    1. **A1 สถาปนิกดำ (Grid):** สแกนละเอียด
    2. **A2 สถาปนิกแดง (Visual Matcher):** ดูรูปคู่มือแล้วเทียบสัญลักษณ์
    3. **A3 สถาปนิกขาว (Text):** อ่าน Label
    4. **A4 สถาปนิกเขียว (Context):** "ตาเห็นอะไรบันทึกอันนั้น" ห้ามเดา
    5. **A5 สถาปนิกฟ้า (Trace):** ไล่สาย
    6. **A6 สถาปนิกส้ม (Lead):** สรุปผล
    
    **MANDATORY:** ห้ามส่งกระดาษเปล่า!
    
    Output JSON: [ {{"room": "...", "item": "...", "spec": "...", "qty": 0}} ]
    """
    try:
        # ส่ง Prompt + แบบแปลน + รูปคู่มือ
        contents = [prompt, image] + legend_imgs
        response = model.generate_content(contents)
        data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        chat_log(chat_ph, "A6 สถาปนิกส้ม", f"สรุปยอดได้ {len(data)} รายการ ส่งต่อทีมวิศวกรครับ", "user")
        return data
    except Exception as e:
        chat_log(chat_ph, "System", f"Error A: {e}", "assistant")
        return [{"room": "Check", "item": "Manual", "spec": "-", "qty": 1}]

def run_team_b(data, round_num, chat_ph):
    """Team B: วิศวกร (Text Rules)"""
    model = get_model("ENGINEER")
    manual_text = get_text_content("วสท64_compressed.pdf")
    
    chat_log(chat_ph, "B6 วิศวกรสมหมาย", "ทีม B รับเรื่องแล้วครับ กำลังตรวจสอบ...", "assistant")
    
    prompt = f"""
    คุณคือ "Team B" วิศวกรตรวจสอบ 6 คน นำโดย วิศวกรบุญชู
    ข้อมูล: {json.dumps(data, ensure_ascii=False)}
    
    --- มาตรฐาน วสท. ---
    {manual_text[:10000]}...
    ---------------------
    
    เงื่อนไข:
    - รอบ 1: บังคับหาที่ผิดและสั่งแก้ (REJECTED)
    - รอบ 2: อนุมัติ (APPROVED)
    
    Output: REJECTED: [...] หรือ APPROVED: [...]
    """
    response = model.generate_content(prompt)
    text = response.text
    
    if "REJECTED" in text:
        chat_log(chat_ph, "B1 วิศวกรบุญชู", "มีจุดต้องแก้ครับ! เรื่องความปลอดภัยสำคัญมาก", "assistant")
    else:
        chat_log(chat_ph, "B6 วิศวกรสมหมาย", "แบบสมบูรณ์แล้วครับ อนุมัติให้สร้างได้ ✅", "assistant")
        
    return text

def run_team_c_d(data, chat_ph):
    """Team C & D: Execution"""
    model = get_model("QS")
    price_list = get_text_content("Price_List.csv")
    
    # D: Method
    chat_log(chat_ph, "D โฟร์แมน", "กำลังเขียนคู่มือติดตั้ง...", "user")
    prompt_d = f"เขียน Method Statement ภาษาไทย สำหรับ: {data}"
    method_d = model.generate_content(prompt_d).text
    
    # C: BOQ
    chat_log(chat_ph, "C QS", "กำลังคำนวณราคาจาก CSV...", "assistant")
    prompt_c = f"""
    คุณคือ C (QS) ทำ BOQ 4 ตาราง จาก Price List นี้เท่านั้น:
    {price_list}
    
    ข้อมูล: {data}
    วิธีทำ: {method_d}
    
    Output JSON Keys: [table_1_total, table_2_mat, table_3_lab, table_4_po]
    """
    try:
        res = model.generate_content(prompt_c)
        boq = json.loads(res.text.replace("```json", "").replace("```", "").strip())
        chat_log(chat_ph, "C QS", "คำนวณเสร็จสิ้นครับ", "assistant")
        return method_d, boq
    except:
        return method_d, {"error": "JSON Error"}

# --- 5. MAIN UI ---
def main():
    st.title("🏗️ MEP AI: Final Execution")
    
    # Check Files
    c1, c2, c3 = st.columns(3)
    with c1: 
        if os.path.exists("Manuals/Engineering_Drawings_EE.pdf"): st.success("✅ A: Visual Legend OK")
        else: st.error("❌ ขาดไฟล์ Engineering_Drawings_EE.pdf")
    with c2:
        if os.path.exists("Manuals/วสท64_compressed.pdf"): st.success("✅ B: Standard OK")
        else: st.warning("⚠️ ขาดไฟล์ วสท. (ใช้กฎทั่วไป)")
    with c3:
        if os.path.exists("Manuals/Price_List.csv"): st.success("✅ C: Price DB OK")
        else: st.error("❌ ขาดไฟล์ Price_List.csv")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        if st.button("🚀 START SYSTEM"):
            st.markdown("### 💬 Live Operation Log")
            chat_container = st.container()
            chat_ph = chat_container.empty()
            
            # Round 1
            data_r1 = run_team_a(image, 1, "", chat_ph)
            if data_r1:
                res_b1 = run_team_b(data_r1, 1, chat_ph)
                
                final_data = None
                if "REJECTED" in res_b1:
                    feedback = res_b1.replace("REJECTED:", "").strip()
                    st.warning(f"📝 **สั่งแก้ไข (Round 1):** {feedback}")
                    
                    # Round 2
                    data_r2 = run_team_a(image, 2, feedback, chat_ph)
                    res_b2 = run_team_b(data_r2, 2, chat_ph)
                    
                    try:
                        json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
                        final_data = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                        st.success("🏆 **Final Approved Draft**")
                        st.json(final_data)
                    except: st.error("Error Parsing Final")
                else:
                    st.success("Approved in Round 1")
                    
                # Execution
                if final_data:
                    st.markdown("---")
                    method_d, boq = run_team_c_d(final_data, chat_ph)
                    
                    st.info(f"👷 **Method Statement:**\n{method_d[:500]}...")
                    
                    if "error" not in boq:
                        t1, t2, t3, t4 = st.tabs(["รวม", "ค่าของ", "ค่าแรง", "PO"])
                        def show(k):
                            if k in boq:
                                df = pd.DataFrame(boq[k])
                                st.dataframe(df, use_container_width=True)
                                if 'รวมเป็นเงิน' in df.columns:
                                    total = df['รวมเป็นเงิน'].astype(str).str.replace(',','').astype(float).sum()
                                    st.metric("Total", f"{total:,.2f} THB")
                        with t1: show("table_1_total")
                        with t2: show("table_2_mat")
                        with t3: show("table_3_lab")
                        with t4: show("table_4_po")

if __name__ == "__main__":
    main()
