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
st.set_page_config(page_title="MEP AI: Transparent Mode", layout="wide", page_icon="🏗️")

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

# --- 2. HELPER: REAL-TIME LOGGER ---
def log_stream(placeholder, message, level="INFO"):
    timestamp = time.strftime("%H:%M:%S")
    icon = "🟢" if level == "INFO" else "🟠" if level == "WARN" else "🔴"
    placeholder.markdown(f"`{timestamp}` {icon} **{message}**")
    time.sleep(0.5)

# --- 3. KNOWLEDGE ACCESS ---
def get_kb_content(filename):
    path = os.path.join("Manuals", filename)
    if not os.path.exists(path): return f"ไม่พบไฟล์ {filename}"
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

# --- 4. THE TEAM AGENT WORKFLOW ---

def run_team_a(image, round_num, feedback, log_ph):
    """ทีมสถาปนิก 6 คน"""
    log_stream(log_ph, f"ทีม A: เริ่มสแกนแบบ (รอบที่ {round_num})...")
    
    legend_ref = """
    [Reference Symbols]
    - Lighting: Circle+X (Downlight), Rect (Fluorescent)
    - Power: Circle+2lines (Duplex), +WP (Waterproof)
    - Switch: S, S2, S3
    """
    
    prompt = f"""
    คุณคือ "Team A" (สถาปนิกถอดแบบ 6 คน)
    บริบท: รอบที่ {round_num}
    คำสั่งแก้จากวิศวกร (Feedback): {feedback if feedback else "-"}
    
    หน้าที่: ระบุรายการอุปกรณ์ในภาพให้ละเอียดที่สุด (ห้ามส่งกระดาษเปล่า!)
    
    สมาชิกทีม:
    A1 (Grid): สแกนทุกตารางนิ้ว
    A2 (Symbol): เทียบรูปกับ Legend: {legend_ref}
    A3 (Text): อ่าน Label
    A4 (Context): ดูบริบทห้อง (เช่น ห้องน้ำ, ครัว)
    A5 (Tracer): ไล่สายไฟ
    A6 (Lead): สรุปผล
    
    Output Format: JSON List
    [ {{"id": 1, "room": "...", "item": "...", "spec": "...", "qty": 0, "note": "Found by A2"}} ]
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=[prompt, image])
        text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        log_stream(log_ph, f"ทีม A: สรุปได้ {len(data)} รายการ ส่งต่อให้ทีม B")
        return data
    except Exception as e:
        log_stream(log_ph, f"Error Team A: {e}", "ERR")
        return []

def run_team_b(data_from_a, round_num, log_ph):
    """ทีมวิศวกร 6 คน"""
    log_stream(log_ph, "ทีม B: ได้รับรายการแล้ว กำลังเปิดคู่มือตรวจ...")
    manual = get_kb_content("Engineering_Drawings_EE.pdf")
    
    prompt = f"""
    คุณคือ "Team B" (วิศวกรตรวจสอบ 6 คน)
    
    ข้อมูลจาก A: {json.dumps(data_from_a, ensure_ascii=False)}
    
    กฎเหล็กจากคู่มือ (Manual):
    {manual[:5000]}...
    
    หน้าที่: ตรวจสอบทีละรายการ (Item by Item)
    1. ความปลอดภัย (Safety) - ห้องน้ำใช้กันน้ำไหม?
    2. มาตรฐาน (Standard) - สเปคถูกต้องไหม?
    
    เงื่อนไข:
    - ถ้าผิดแม้แต่จุดเดียว: สั่ง "REJECTED" และระบุ ID รายการที่ผิด + วิธีแก้
    - ถ้าถูกหมด: สั่ง "APPROVED"
    
    Output Format:
    - REJECTED: [ระบุรายการที่ผิด และเหตุผลอย่างละเอียด]
    - APPROVED: [JSON List ที่ผ่านการรับรองแล้ว]
    """
    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
    return response.text

def run_team_c_d(final_data, log_ph):
    """ทีม C & D"""
    price_list = get_kb_content("Price_List.csv")
    
    log_stream(log_ph, "D (โฟร์แมน): กำลังวางแผนงานติดตั้ง...")
    prompt_d = f"เขียน Method Statement ภาษาไทย สำหรับ: {final_data}"
    method_d = client.models.generate_content(model=MODEL_ID, contents=prompt_d).text
    
    log_stream(log_ph, "C (QS): กำลังคำนวณราคาจาก CSV...")
    prompt_c = f"""
    คุณคือ C (QS) ทำ BOQ 4 ตาราง
    ราคาอ้างอิง: {price_list}
    ข้อมูล: {final_data}
    วิธีทำ: {method_d}
    
    Output JSON: {{ "table_1_total": [...], "table_2_mat": [...], "table_3_lab": [...], "table_4_po": [...] }}
    """
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt_c)
        return method_d, json.loads(res.text.replace("```json", "").replace("```", "").strip())
    except:
        return method_d, {"error": "JSON Error"}

# --- 5. MAIN UI ---
def main():
    st.title(f"🏗️ MEP AI: Transparent System ({MODEL_ID})")
    
    # Check Files
    c1, c2 = st.columns(2)
    with c1:
        if "Error" in get_kb_content("Price_List.csv"): st.error("❌ Missing Price_List.csv")
        else: st.success("✅ Price DB Ready")
    with c2:
        if "Error" in get_kb_content("Engineering_Drawings_EE.pdf"): st.warning("⚠️ Missing Manual PDF")
        else: st.success("✅ Engineer DB Ready")

    uploaded_file = st.file_uploader("📂 อัปโหลดแบบแปลน", type=['png', 'jpg'])
    
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Blueprint", width=400)
        
        if st.button("🚀 เริ่มทำงาน (Start Process)"):
            log_container = st.container()
            log_ph = log_container.empty()
            
            # --- ROUND 1 ---
            log_stream(log_ph, "--- เริ่มต้นรอบที่ 1 ---")
            data_r1 = run_team_a(image, 1, "", log_ph)
            
            if data_r1:
                # 🔥 แสดงรายการที่ A ส่งไปให้ B ดูชัดๆ
                st.subheader("📄 รายการที่ Team A ส่งให้ตรวจสอบ (Draft 1)")
                st.dataframe(pd.DataFrame(data_r1), use_container_width=True)
                
                res_b1 = run_team_b(data_r1, 1, log_ph)
                
                final_verdict = None
                if "REJECTED" in res_b1:
                    log_stream(log_ph, "❌ Team B ตีกลับงาน!", "WARN")
                    
                    # 🔥 แสดงคำสั่งแก้ของ B ให้เห็นชัดๆ
                    st.error(f"📝 **คำสั่งแก้ไขจากวิศวกร (Correction Order):**\n{res_b1.replace('REJECTED:', '').strip()}")
                    
                    # --- ROUND 2 ---
                    log_stream(log_ph, "--- เริ่มต้นรอบที่ 2 (แก้ไขงาน) ---")
                    data_r2 = run_team_a(image, 2, res_b1, log_ph)
                    
                    st.subheader("📄 รายการที่แก้ไขแล้ว (Draft 2)")
                    st.dataframe(pd.DataFrame(data_r2), use_container_width=True)
                    
                    res_b2 = run_team_b(data_r2, 2, log_ph)
                    
                    try:
                        json_str = res_b2.split("APPROVED:")[1].strip() if "APPROVED:" in res_b2 else res_b2
                        final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                        log_stream(log_ph, "✅ Team B อนุมัติแล้ว (Approved)")
                        st.success("🏆 **อนุมัติแบบก่อสร้าง (Final Approved):**")
                        st.dataframe(pd.DataFrame(final_verdict), use_container_width=True)
                    except:
                        log_stream(log_ph, "Error Parsing Final", "ERR")
                else:
                    log_stream(log_ph, "✅ Team B อนุมัติทันที")
                    try:
                        json_str = res_b1.split("APPROVED:")[1].strip() if "APPROVED:" in res_b1 else res_b1
                        final_verdict = json.loads(json_str.replace("```json", "").replace("```", "").strip())
                        st.success("🏆 **อนุมัติแบบก่อสร้าง (Final Approved):**")
                        st.dataframe(pd.DataFrame(final_verdict), use_container_width=True)
                    except:
                        final_verdict = data_r1

                # --- PHASE 3 ---
                if final_verdict:
                    st.markdown("---")
                    st.header("🚀 Execution Phase")
                    method_d, boq_data = run_team_c_d(final_verdict, log_ph)
                    
                    st.info(f"👷 **D (Method Statement):**\n{method_d}")
                    
                    if "error" not in boq_data:
                        log_stream(log_ph, "✅ ภารกิจเสร็จสิ้น!")
                        t1, t2, t3, t4 = st.tabs(["1. รวม", "2. ค่าของ", "3. ค่าแรง", "4. PO"])
                        def show_tab(key):
                            if key in boq_data:
                                df = pd.DataFrame(boq_data[key])
                                st.dataframe(df, use_container_width=True)
                                cols = df.columns
                                num_cols = df.select_dtypes(include=['number']).columns
                                if len(num_cols) > 0:
                                    target = next((x for x in cols if "รวม" in x or "Total" in x), num_cols[-1])
                                    try: st.metric("Grand Total", f"{df[target].sum():,.2f} THB")
                                    except: pass

                        with t1: show_tab("table_1_total")
                        with t2: show_tab("table_2_mat")
                        with t3: show_tab("table_3_lab")
                        with t4: show_tab("table_4_po")

if __name__ == "__main__":
    main()
