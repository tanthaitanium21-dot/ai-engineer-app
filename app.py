import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import time
import os
import io
from PIL import Image
from pypdf import PdfReader
import fitz  # PyMuPDF

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="MEP AI: Gemini 2.5 System", layout="wide", page_icon="🏗️")

# 🔑 API KEYS
KEYS = {
    "ARCHITECT": "AIzaSyCWlcMMJddJ5xJQGKeEU8Cn2fcCIx3upXI", 
    "ENGINEER":  "AIzaSyBk9zUBY6TuYO13QxPw6ZVziENedIx0yJA", 
    "QS":        "AIzaSyB5e_5lXSnjlvIDL63OdV_BLBfQZvjaRuU"
}

# โมเดลเป้าหมาย
TARGET_MODEL = "gemini-2.5-flash"

def get_client(role):
    try:
        # ใช้ SDK ใหม่ google-genai
        client = genai.Client(api_key=KEYS[role])
        return client
    except Exception as e:
        st.error(f"❌ Client Error ({role}): {e}")
        return None

# --- 2. HELPER: CHAT LOG ---
def chat_log(placeholder, speaker, message, role="user"):
    avatar = "👷‍♂️" if "สถาปนิก" in speaker else "⚙️" if "วิศวกร" in speaker else "💰" if "QS" in speaker else "👷"
    with placeholder.container():
        st.chat_message(role, avatar=avatar).write(f"**{speaker}:** {message}")
        time.sleep(0.1)

# --- 3. KNOWLEDGE ACCESS ---
def get_pdf_images(filename, limit=5):
    path = os.path.join("Manuals", filename)
    images = []
    # Fallback paths
    if not os.path.exists(path):
        if os.path.exists(filename): path = filename
        else: return []

    if os.path.exists(path):
        try:
            doc = fitz.open(path)
            for i in range(min(len(doc), limit)):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                # แปลงเป็น PIL Image
                images.append(Image.open(io.BytesIO(img_data)))
        except: pass
    return images

def get_text_content(filename):
    path = os.path.join("Manuals", filename)
    # Fallback paths
    if not os.path.exists(path):
        if os.path.exists(filename): path = filename
        else: return f"Missing {filename}"

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

# --- 4. AGENT WORKFLOW (NEW SDK) ---

def run_team_a(image, round_num, feedback, chat_ph):
    client = get_client("ARCHITECT")
    legend_imgs = get_pdf_images("Engineering_Drawings_EE.pdf")
    
    chat_log(chat_ph, "A6 สถาปนิกส้ม", f"เริ่มงานรอบที่ {round_num} (Model: {TARGET_MODEL})...", "user")
    
    prompt = f"""
    คุณคือ "Team A" ทีมสถาปนิก 6 คน
    บริบท: รอบที่ {round_num}, คำสั่งแก้: {feedback if feedback else "-"}
    
    คำสั่งพิเศษ: เทียบรูปร่างอุปกรณ์ในแบบแปลน กับรูปภาพคู่มือสัญลักษณ์ที่แนบไปให้
    
    หน้าที่:
    1. A1 (Grid): สแกนละเอียด
    2. A2 (Visual): ดูรูปคู่มือแล้วเทียบสัญลักษณ์
    3. A3 (Text): อ่าน Label
    4. A4 (Context): ห้ามเดาบริบท
    5. A5 (Trace): ไล่สาย
    6. A6 (Lead): สรุปผล JSON
    
    Output JSON: [ {{"room": "...", "item": "...", "spec": "...", "qty": 0}} ]
    """
    
    try:
        # SDK ใหม่: ส่ง contents เป็น list ได้เลย (Text + Images)
        contents = [prompt, image] + legend_imgs
        
        # เรียก API แบบใหม่
        response = client.models.generate_content(
            model=TARGET_MODEL,
            contents=contents
        )
        
        data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        chat_log(chat_ph, "A6 สถาปนิกส้ม", f"เจอ {len(data)} รายการครับ", "user")
        return data
    except Exception as e:
        chat_log(chat_ph, "System", f"Error A: {e}", "assistant")
        # Fallback ถ้า 2.5 ยังใช้ไม่ได้ ให้ลอง 1.5
        if "404" in str(e) or "not found" in str(e).lower():
             chat_log(chat_ph, "System", "Gemini 2.5 not found, falling back to 1.5...", "assistant")
             try:
                 response = client.models.generate_content(model="gemini-1.5-flash", contents=contents)
                 data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
                 return data
             except: pass
        return [{"room": "Error", "item": "Check Manual", "spec": "-", "qty": 1}]

def run_team_b(data, round_num, chat_ph):
    client = get_client("ENGINEER")
    manual_text = get_text_content("วสท64_compressed.pdf")
    
    chat_log(chat_ph, "B6 วิศวกรสมหมาย", "ทีม B กำลังตรวจสอบ...", "assistant")
    
    prompt = f"""
    คุณคือ "Team B" วิศวกร 6 คน
    ข้อมูล: {json.dumps(data, ensure_ascii=False)}
    มาตรฐาน: {manual_text[:10000]}...
    
    เงื่อนไข:
    - รอบ 1: บังคับ REJECTED เพื่อแก้
    - รอบ 2: APPROVED
    
    Output: REJECTED: [...] หรือ APPROVED: [...]
    """
    
    try:
        response = client.models.generate_content(
            model=TARGET_MODEL,
            contents=prompt
        )
        return response.text
    except Exception as e:
        # Fallback
        try:
            response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
            return response.text
        except: return "Error B"

def run_team_c_d(data, chat_ph):
    client = get_client("QS")
    price_list = get_text_content("Price_List.csv")
    
    # D
    chat_log(chat_ph, "D โฟร์แมน", "เขียนวิธีทำ...", "user")
    prompt_d = f"เขียน Method Statement ภาษาไทย: {data}"
    try:
        method_d = client.models.generate_content(model=TARGET_MODEL, contents=prompt_d).text
    except:
        method_d = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_d).text
    
    # C
    chat_log(chat_ph, "C QS", "คำนวณราคา...", "assistant")
    prompt_c = f"""
    คุณคือ C (QS) ทำ BOQ 4 ตาราง จาก Price List นี้:
    {price_list}
    
    ข้อมูล: {data}
    วิธีทำ: {method_d}
    Output JSON Keys: [table_1_total, table_2_mat, table_3_lab, table_4_po]
    """
    try:
        res = client.models.generate_content(model=TARGET_MODEL, contents=prompt_c)
        boq = json.loads(res.text.replace("```json", "").replace("```", "").strip())
        return method_d, boq
    except:
        # Fallback
        try:
            res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_c)
            boq = json.loads(res.text.replace("```json", "").replace("```", "").strip())
            return method_d, boq
        except: return method_d, {"error": "JSON Error"}

# --- 5. MAIN UI ---
def main():
    st.title(f"🏗️ MEP AI: GenAI SDK ({TARGET_MODEL})")
    
    # Check Files
    c1, c2, c3 = st.columns(3)
    with c1: 
        if os.path.exists("Manuals/Engineering_Drawings_EE.pdf"): st.success("✅ A: Visual Legend OK")
        else: st.error("❌ ขาดไฟล์ A")
    with c2:
        if os.path.exists("Manuals/วสท64_compressed.pdf"): st.success("✅ B: Standard OK")
        else: st.warning("⚠️ ขาดไฟล์ B")
    with c3:
        if os.path.exists("Manuals/Price_List.csv"): st.success("✅ C: Price DB OK")
        else: st.error("❌ ขาดไฟล์ C")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        if st.button("🚀 START SYSTEM"):
            chat_container = st.container()
            chat_ph = chat_container.empty()
            
            # Round 1
            data_r1 = run_team_a(image, 1, "", chat_ph)
            if data_r1:
                res_b1 = run_team_b(data_r1, 1, chat_ph)
                
                final_data = None
                if "REJECTED" in res_b1:
                    feedback = res_b1.replace("REJECTED:", "").strip()
                    st.warning(f"📝 **สั่งแก้:** {feedback}")
                    
                    # Round 2
                    data_r2 = run_team_a(image, 2, feedback, chat_ph)
                    res_b2 = run_team_b(data_r2, 2, chat_ph)
                    
                    try:
                        if "APPROVED" in res_b2:
                            json_str = res_b2.split("APPROVED:")[1].strip()
                            final_data = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                            st.success("🏆 **Final Approved**")
                            st.json(final_data)
                        else:
                            st.error("Still Rejected")
                    except: st.error("Error Parsing Final")
                else:
                    st.success("Approved in Round 1")
                    try:
                        # Try parse if B approved immediately
                        json_str = res_b1.split("APPROVED:")[1].strip()
                        final_data = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                    except: final_data = data_r1 # fallback

                # Execution
                if final_data:
                    st.markdown("---")
                    method, boq = run_team_c_d(final_data, chat_ph)
                    st.info(f"👷 **Method:**\n{method[:300]}...")
                    
                    if "error" not in boq:
                        t1,t2,t3,t4 = st.tabs(["Total","Mat","Lab","PO"])
                        
                        def show(k):
                            if k in boq:
                                df = pd.DataFrame(boq[k])
                                st.dataframe(df, use_container_width=True)
                                if 'รวมเป็นเงิน' in df.columns:
                                    try:
                                        tot = df['รวมเป็นเงิน'].astype(str).str.replace(',','').astype(float).sum()
                                        st.metric("Total", f"{tot:,.2f}")
                                    except: pass
                        
                        with t1: show("table_1_total")
                        with t2: show("table_2_mat")
                        with t3: show("table_3_lab")
                        with t4: show("table_4_po")

if __name__ == "__main__":
    main()
