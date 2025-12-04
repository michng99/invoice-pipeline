import io
import os
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
import xlsxwriter
import xmltodict  # QUAY LẠI DÙNG THƯ VIỆN NÀY ĐỂ TỐI ƯU TỐC ĐỘ

# ==============================================================================
# 1. CẤU HÌNH & CSS
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

st.markdown("""
    <style>
        /* Ẩn UI rác */
        a[href*="streamlit.io/cloud"], div[class*="viewerBadge"], 
        #MainMenu, footer, header, [data-testid="stHeader"], .stDeployButton 
        { display: none !important; }
        
        .block-container { padding-top: 1rem !important; padding-bottom: 150px !important; }
        .custom-footer {
            width: 100%; text-align: center; color: #888;
            padding-top: 20px; margin-bottom: 20px; border-top: 1px solid #333;
            font-size: 12px; font-family: sans-serif;
        }
        button { min-height: 48px !important; }
        input { color: inherit !important; }
    </style>
""", unsafe_allow_html=True)

if "theme" not in st.session_state: st.session_state["theme"] = "light"
if st.session_state["theme"] == "dark":
    st.markdown("""<style>.stApp {background-color: #0E1117; color: #FAFAFA;} input {color: white !important;}</style>""", unsafe_allow_html=True)

# ==============================================================================
# 2. CORE LOGIC (XMLTODICT - SIÊU NHANH)
# ==============================================================================

COLUMN_ORDER = [
    "Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn",
    "ST người bán", "Tên người bán", "ĐC người bán", "C người bán",
    "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá",
    "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền",
    "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)",
]
MAX_FILES_ALLOWED = 50          
MAX_FILE_SIZE_MB = 10           

def _num(v):
    if not v: return 0.0
    try: return float(str(v).replace(",", "").strip())
    except: return 0.0

def _get_val_flexible(item: dict, keys: List[str]) -> str:
    """Tìm giá trị trong dict với nhiều key khác nhau"""
    for k in keys:
        if k in item and item[k]:
            return str(item[k])
    return ""

def _parse_invoice_fast(xml_bytes: bytes, filename: str) -> dict:
    try:
        # xmltodict parse cực nhanh và tự xử lý namespace
        doc = xmltodict.parse(xml_bytes, process_namespaces=True, namespaces=None)
        
        # Tìm root (thường là HDon)
        # Lấy value đầu tiên của dict vì root name có thể thay đổi
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # Chuẩn hóa truy cập (Dùng get để tránh lỗi nếu thiếu tag)
        dlhdon = hdon.get("DLHDon", {})
        ttchung = dlhdon.get("TTChung", {})
        ndhdon = dlhdon.get("NDHDon", {})
        
        # Header
        invoice = {
            "KHMSHDon": ttchung.get("KHMSHDon"),
            "KHHDon": ttchung.get("KHHDon"),
            "SHDon": ttchung.get("SHDon"),
            "NLap": ttchung.get("NLap"),
            "DVTTe": ttchung.get("DVTTe", "VND"),
            "TGia": ttchung.get("TGia", "1"),
        }
        
        # Người bán
        nban = ndhdon.get("NBan", {})
        invoice["NBan"] = {
            "Ten": nban.get("Ten"),
            "MST": nban.get("MST"),
            "DChi": nban.get("DChi"),
        }
        
        # Hàng hóa
        items = []
        dshhdv = ndhdon.get("DSHHDVu", {})
        if dshhdv:
            # xmltodict: Nếu có 1 item -> trả về dict. Nếu nhiều -> trả về list.
            # Cần chuẩn hóa thành list hết.
            raw_items = dshhdv.get("HHDVu")
            if isinstance(raw_items, dict): raw_items = [raw_items]
            if raw_items: items = raw_items
            
        invoice["Items"] = items
        return invoice
    except Exception as e:
        print(f"Lỗi đọc file {filename}: {e}")
        return {}

def _rows_from_invoice(inv: dict) -> list[dict]:
    if not inv: return []
    try:
        ms = inv.get("KHMSHDon") or ""
        kh = inv.get("KHHDon") or ""
        so = inv.get("SHDon") or ""
        ngay = inv.get("NLap") or ""
        cur = inv.get("DVTTe") or "VND"
        rate = _num(inv.get("TGia")) or 1
        seller = inv.get("NBan") or {}
        s_mst = seller.get("MST") or ""
        s_name = seller.get("Ten") or ""
        s_addr = seller.get("DChi") or ""
        ghichu = "Hoá đơn mới"

        items = inv.get("Items") or []
        rows = []

        for it in items:
            # Lấy dữ liệu cơ bản
            sl = _num(it.get("SLuong"))
            dg = _num(it.get("DGia"))
            tht = _num(it.get("ThTien"))
            
            # --- 1. SĂN LÙNG THUẾ SUẤT (TỪ ĐIỂN FULL) ---
            # Tìm trong item chính
            ts_raw = _get_val_flexible(it, ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "TaxRate", "LTSuat", "LTS"])
            
            # Nếu chưa có, tìm trong TTKhac (Thông tin khác)
            ttkhac = it.get("TTKhac") or it.get("ThongTinKhac") or {}
            if not ts_raw and isinstance(ttkhac, dict):
                ts_raw = _get_val_flexible(ttkhac, ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "TaxRate"])

            # --- 2. SĂN LÙNG TIỀN THUẾ & TỔNG ---
            vat = _num(_get_val_flexible(it, ["VATAmount", "TienThue", "TienThueGTGT"]))
            if vat == 0 and isinstance(ttkhac, dict): # Tìm trong con
                vat = _num(_get_val_flexible(ttkhac, ["VATAmount", "TienThue", "TienThueGTGT"]))
                
            total = _num(_get_val_flexible(it, ["Amount", "TongTien", "ThanhTien"]))
            if total == 0 and isinstance(ttkhac, dict):
                total = _num(_get_val_flexible(ttkhac, ["Amount", "TongTien"]))

            # --- 3. LOGIC TÍNH TOÁN & SUY LUẬN ---
            
            # Parse % thuế ra số (0.08, 0.1...)
            ts_val = 0.0
            if ts_raw:
                clean_ts = str(ts_raw).replace("%","").replace(",",".")
                try:
                    # Nếu là số (8, 10, 5)
                    if clean_ts[0].isdigit():
                        val = float(clean_ts)
                        ts_val = val / 100 if val > 1 else val
                except: pass

            # A. Tự tính VAT nếu thiếu (nhưng biết thuế suất)
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if str(cur).upper() == "VND": vat = round(vat)
            
            # B. SUY LUẬN NGƯỢC % NẾU THIẾU (nhưng biết tiền thuế) -> QUAN TRỌNG
            final_ts_display = ts_raw
            if not final_ts_display and vat > 0 and tht > 0:
                try:
                    calc = (vat / tht) * 100
                    # Làm tròn vào các mức thuế phổ biến VN (0, 5, 8, 10)
                    if abs(calc - 5) < 0.5: final_ts_display = "5%"
                    elif abs(calc - 8) < 0.5: final_ts_display = "8%"
                    elif abs(calc - 10) < 0.5: final_ts_display = "10%"
                    elif abs(calc - 0) < 0.1: final_ts_display = "0%"
                    else: final_ts_display = f"{round(calc, 2)}%" # Số lẻ
                except: pass

            # C. Tự tính Tổng
            if total == 0: total = tht + vat

            # Build row
            r = {k: "" for k in COLUMN_ORDER}
            r.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": rate,
                "Mã hàng": it.get("MHHDVu") or "",
                "Tên hàng": it.get("THHDVu") or "",
                "Đơn vị tính": it.get("DVTinh") or "",
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": tht,
                "Thuế suất": final_ts_display, # Kết quả cuối
                "Tiền thuế": vat, "Cộng tiền": total,
                "Cờ (Tchat)": it.get("TChat") or ""
            })
            rows.append(r)
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: list[dict]) -> io.BytesIO:
    df = pd.DataFrame(rows)
    df = df.reindex(columns=COLUMN_ORDER)
    for c in ["Số lượng","Đơn giá","Tiền hàng","Thuế suất","Tiền thuế","Cộng tiền","Tỷ giá"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
    buf.seek(0)
    return buf

# ==============================================================================
# 3. FRONTEND (TỐI ƯU UPLOAD)
# ==============================================================================

if "uploads" not in st.session_state: st.session_state.update({"uploads":{}, "busy":False, "lang_code":"vi", "theme":"light"})

def _add_uploads(files, T):
    store = st.session_state["uploads"]
    if len(store) + len(files) > MAX_FILES_ALLOWED:
        st.error(T["error_too_many"].format(max=MAX_FILES_ALLOWED)); return
    
    for f in files:
        try:
            name = f.name
            data = f.read() # Đọc 1 lần vào RAM
            if len(data) > MAX_FILE_SIZE_MB*1024*1024: 
                st.toast(f"File {name} quá lớn", icon="⚠️"); continue
            store[name] = {"data": data, "size": len(data), "uploaded_at": time.time()}
        except: continue

# --- UI LANGUAGE ---
LANG = {
    "vi": {
        "page_title": "Xử lý Hóa đơn", "settings": "Cài đặt", "theme_label": "Giao diện",
        "mode_info": "Chế độ: **All-in-One** (Bảo mật & Riêng tư)", "check_sys": "Kiểm tra hệ thống", "sys_ok": "✅ Ổn định",
        "upload_label": "Thả file XML vào đây", "added": "Đã thêm", "clear_all": "Xoá tất cả",
        "col_name": "Tên file", "col_size": "Kích thước", "merge_label": "Gộp 1 file", "convert_btn": "🚀 Chuyển đổi",
        "success_msg": "✅ Xong!", "error_msg": "Lỗi xử lý.", "download_btn": "⬇️ Tải về",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved", "error_too_many": "Quá tải.", "empty_list": "Chưa có file."
    },
    "en": {
        "page_title": "Invoice Pipeline", "settings": "Settings", "theme_label": "Theme",
        "mode_info": "Mode: **All-in-One** (Secure & Private)", "check_sys": "Check System", "sys_ok": "✅ Stable",
        "upload_label": "Drop XML files", "added": "Added", "clear_all": "Clear All",
        "col_name": "Filename", "col_size": "Size", "merge_label": "Merge to one", "convert_btn": "🚀 Convert",
        "success_msg": "✅ Done!", "error_msg": "Error.", "download_btn": "⬇️ Download",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved", "error_too_many": "Too many files.", "empty_list": "No files."
    }
}

T = LANG[st.session_state["lang_code"]]
col_head, col_set = st.columns([6, 1], gap="small")
with col_head: st.title(f"{T['page_title']}")
with col_set:
    with st.popover(f"⚙️ {T['settings']}", use_container_width=True):
        is_vn = st.session_state["lang_code"] == "vi"
        if st.toggle("Tiếng Việt / English", value=is_vn): st.session_state["lang_code"] = "vi"
        else: st.session_state["lang_code"] = "en"
        theme = st.radio("Theme", ["Light", "Dark"], index=0 if st.session_state["theme"]=="light" else 1, horizontal=True)
        st.session_state["theme"] = theme.lower()
        if st.button("Apply"): st.rerun()

with st.container(border=True):
    c1, c2 = st.columns([3,1])
    c1.info(T["mode_info"])
    if c2.button(f"🔗 {T['check_sys']}", use_container_width=True): c2.success(T["sys_ok"])

st.divider()
uploaded_files = st.file_uploader(T['upload_label'], type=["xml"], accept_multiple_files=True)
if uploaded_files: 
    _add_uploads(uploaded_files, T)
    st.rerun()

if st.session_state["uploads"]:
    c1, c2 = st.columns([3,1])
    rows = [{T['col_name']:k, T['col_size']:v["size"]} for k,v in st.session_state["uploads"].items()]
    c1.dataframe(rows, use_container_width=True, hide_index=True)
    if c2.button(f"🧽 {T['clear_all']}", use_container_width=True): 
        st.session_state["uploads"].clear(); st.session_state.pop("result_bytes", None); st.rerun()
else: st.caption(f"_{T['empty_list']}_")

merge = st.checkbox(T['merge_label'], value=True)
if st.button(T['convert_btn'], type="primary", disabled=not st.session_state["uploads"]):
    try:
        files_map = {k: v["data"] for k,v in st.session_state["uploads"].items()}
        per_file = []
        for name, data in files_map.items():
            # Dùng hàm parse mới (xmltodict)
            inv = _parse_invoice_fast(data, name) 
            rows = _rows_from_invoice(inv)
            if rows: per_file.append(rows)
        
        if per_file:
            all_rows = [r for sub in per_file for r in sub]
            xlsx = _df_to_xlsx_stream(all_rows)
            st.session_state["result_bytes"] = xlsx.getvalue()
            st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            st.success(T['success_msg'])
        else: st.warning("Không tìm thấy dữ liệu hợp lệ.")
    except Exception as e: 
        print(f"Error: {e}")
        st.error(T['error_msg'])

if st.session_state.get("result_bytes"):
    st.download_button(T['download_btn'], st.session_state["result_bytes"], "Data.xlsx", st.session_state["result_mime"], type="primary")

st.markdown(f'<div class="custom-footer">{T["copyright"]}</div>', unsafe_allow_html=True)
