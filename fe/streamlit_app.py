import io
import os
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Tuple, Dict, Any

import streamlit as st
import pandas as pd
import xlsxwriter
import xmltodict  # <--- QUAY LẠI DÙNG THƯ VIỆN NÀY (NHƯ BẢN GCP)

# ==============================================================================
# 1. CẤU HÌNH TRANG & CSS (GIỮ NGUYÊN GIAO DIỆN ĐÃ CHỐT)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

st.markdown("""
    <style>
        /* Ẩn rác UI */
        a[href*="streamlit.io/cloud"], div[class*="viewerBadge"], 
        #MainMenu, footer, header, [data-testid="stHeader"], .stDeployButton 
        { display: none !important; }
        
        /* Layout */
        .block-container { padding-top: 1rem !important; padding-bottom: 150px !important; }
        
        /* Footer */
        .custom-footer {
            width: 100%; text-align: center; color: #888;
            padding-top: 20px; margin-bottom: 20px; border-top: 1px solid #333;
            font-size: 12px; font-family: sans-serif;
        }
        
        /* Mobile buttons */
        button { min-height: 48px !important; }
        input { color: inherit !important; }
    </style>
""", unsafe_allow_html=True)

if "theme" not in st.session_state: st.session_state["theme"] = "light"
if st.session_state["theme"] == "dark":
    st.markdown("""<style>.stApp {background-color: #0E1117; color: #FAFAFA;} input {color: white !important;}</style>""", unsafe_allow_html=True)

# ==============================================================================
# 2. CORE LOGIC (SỬ DỤNG XMLTODICT - GIỐNG HỆT GCP)
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

def _get_val(obj, keys, default=""):
    """Hàm helper để lấy giá trị từ dict an toàn (tránh lỗi KeyError)"""
    if not obj: return default
    for k in keys:
        if k in obj and obj[k]:
            return obj[k]
    return default

def _parse_invoice_xmltodict(xml_bytes: bytes) -> dict:
    """
    Dùng xmltodict parse thẳng ra Dict. 
    Tự động xử lý Namespace, không cần regex tẩy rửa.
    """
    try:
        # process_namespaces=True nhưng namespaces=None để nó bỏ qua prefix (vd inv:Invoice -> Invoice)
        # Tuy nhiên xmltodict mặc định xử lý khá tốt.
        doc = xmltodict.parse(xml_bytes)
        
        # Tìm gốc HDon (Vì có thể root là HDon hoặc Invoice...)
        # Ta lấy values() đầu tiên của dict root
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # Chuẩn hóa về 1 format chung
        dlhdon = hdon.get("DLHDon", {})
        ttchung = dlhdon.get("TTChung", {})
        ndhdon = dlhdon.get("NDHDon", {})
        
        # Lấy thông tin chung
        res = {
            "KHMSHDon": ttchung.get("KHMSHDon"),
            "KHHDon": ttchung.get("KHHDon"),
            "SHDon": ttchung.get("SHDon"),
            "NLap": ttchung.get("NLap"),
            "DVTTe": ttchung.get("DVTTe", "VND"),
            "TGia": ttchung.get("TGia", "1"),
        }
        
        # Lấy người bán (NBan)
        nban = ndhdon.get("NBan", {})
        res["NBan"] = {
            "Ten": nban.get("Ten"),
            "MST": nban.get("MST"),
            "DChi": nban.get("DChi"),
        }
        
        # Lấy hàng hóa (Xử lý list hoặc dict đơn)
        items = []
        dshhdv = ndhdon.get("DSHHDVu", {})
        if dshhdv:
            raw_items = dshhdv.get("HHDVu")
            if isinstance(raw_items, dict): raw_items = [raw_items] # Nếu chỉ có 1 dòng
            if raw_items: items = raw_items
            
        res["Items"] = items
        return res
    except Exception:
        return {}

def _rows_from_invoice(inv: dict) -> list[dict]:
    if not inv: return []
    try:
        # Header info
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
            # Lấy dữ liệu thô từ Dict (An toàn hơn ElementTree nhiều)
            # Dùng _get_val để tìm nhiều key biến thể (TSuat, ThueSuat...)
            
            # 1. Thuế suất
            ts_raw = _get_val(it, ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "TaxRate", "LTSuat", "LTS"])
            if isinstance(ts_raw, dict): ts_raw = "" # Phòng trường hợp nó là dict rỗng
            
            # 2. Tiền
            sl = _num(it.get("SLuong"))
            dg = _num(it.get("DGia"))
            tht = _num(it.get("ThTien"))
            
            # 3. VAT & Tổng (Tìm cả trong TTKhac nếu có)
            ttkhac = it.get("TTKhac", {}) or {}
            # Tìm VAT
            vat_val = it.get("VATAmount") or it.get("TienThue") or ttkhac.get("VATAmount")
            vat = _num(vat_val)
            
            # Tìm Tổng
            amt_val = it.get("Amount") or it.get("TongTien") or ttkhac.get("Amount")
            total = _num(amt_val)

            # 4. LOGIC TÍNH TOÁN (Giữ nguyên logic thông minh)
            # Parse % thuế
            ts_val = 0.0
            ts_str = str(ts_raw).replace("%","").replace(",",".") if ts_raw else ""
            if ts_str and ts_str[0].isdigit():
                try:
                    val = float(ts_str)
                    ts_val = val / 100 if val > 1 else val
                except: pass

            # Tự tính VAT nếu thiếu
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if str(cur).upper() == "VND": vat = round(vat)
            
            # Tự điền ngược % thuế nếu thiếu (nhưng có tiền thuế)
            final_ts = ts_raw
            if not final_ts and vat > 0 and tht > 0:
                try:
                    r = (vat/tht)*100
                    if abs(r-8)<0.5: final_ts="8%"
                    elif abs(r-10)<0.5: final_ts="10%"
                    elif abs(r-5)<0.5: final_ts="5%"
                    else: final_ts=f"{round(r)}%"
                except: pass

            # Tự tính Tổng
            if total == 0: total = tht + vat

            # 5. Build row
            r = {k: "" for k in COLUMN_ORDER}
            r.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": rate,
                "Mã hàng": it.get("MHHDVu") or "",
                "Tên hàng": it.get("THHDVu") or "",
                "Đơn vị tính": it.get("DVTinh") or "",
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": tht,
                "Thuế suất": final_ts, "Tiền thuế": vat, "Cộng tiền": total,
                "Cờ (Tchat)": it.get("TChat") or ""
            })
            rows.append(r)
            
        return rows
    except Exception:
        return []

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
# 3. FRONTEND & HANDLER
# ==============================================================================

if "uploads" not in st.session_state: st.session_state.update({"uploads":{}, "sha_index":{}, "last_activity":time.time(), "busy":False, "do_convert":False, "result_bytes":None, "lang_code":"vi", "theme":"light"})

def _add_uploads(files, T):
    store = st.session_state["uploads"]
    if len(store) + len(files) > MAX_FILES_ALLOWED:
        st.error(T["error_too_many"].format(max=MAX_FILES_ALLOWED)); return
    
    for f in files:
        try:
            name = f.name
            data = f.read()
            # Basic validation
            if len(data) > MAX_FILE_SIZE_MB*1024*1024: 
                st.toast(f"File {name} quá lớn", icon="⚠️"); continue
            
            store[name] = {"data": data, "size": len(data), "uploaded_at": time.time()}
        except: continue
    st.session_state["last_activity"] = time.time()

# --- UI LANGUAGE ---
LANG = {
    "vi": {
        "page_title": "Xử lý Hóa đơn", "settings": "Cài đặt", "theme_label": "Giao diện",
        "mode_info": "Chế độ: **All-in-One** (Bảo mật & Riêng tư)",
        "check_sys": "Kiểm tra hệ thống", "sys_ok": "✅ Hệ thống hoạt động tốt",
        "upload_label": "Thả file XML vào đây", "added": "Đã thêm", "clear_all": "Xoá tất cả",
        "col_name": "Tên file", "col_size": "Kích thước", "col_ttl": "Còn lại",
        "merge_label": "Gộp thành 1 file Excel duy nhất", "convert_btn": "🚀 Chuyển đổi Ngay",
        "success_msg": "✅ Xử lý thành công!", "error_msg": "Lỗi xử lý.",
        "download_btn": "⬇️ Tải về kết quả", "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "error_too_many": "Quá tải số lượng file.", "empty_list": "Chưa có file nào."
    },
    "en": {
        "page_title": "Invoice Pipeline", "settings": "Settings", "theme_label": "Theme",
        "mode_info": "Mode: **All-in-One** (Secure & Private)",
        "check_sys": "System Check", "sys_ok": "✅ System Operational",
        "upload_label": "Drop XML files here", "added": "Added", "clear_all": "Clear All",
        "col_name": "File Name", "col_size": "Size", "col_ttl": "Time Left",
        "merge_label": "Merge into single Excel file", "convert_btn": "🚀 Convert Now",
        "success_msg": "✅ Processing Complete!", "error_msg": "Processing Error.",
        "download_btn": "⬇️ Download Result", "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "error_too_many": "Too many files.", "empty_list": "No files uploaded yet."
    }
}

# --- RENDER ---
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
if uploaded_files: _add_uploads(uploaded_files, T); st.rerun()

if st.session_state["uploads"]:
    c1, c2 = st.columns([3,1])
    rows = [{T['col_name']:k, T['col_size']:v["size"]} for k,v in st.session_state["uploads"].items()]
    c1.dataframe(rows, use_container_width=True, hide_index=True)
    if c2.button(f"🧽 {T['clear_all']}", use_container_width=True): 
        st.session_state["uploads"].clear(); st.session_state["result_bytes"] = None; st.rerun()
else: st.caption(f"_{T['empty_list']}_")

merge = st.checkbox(T['merge_label'], value=True)
if st.button(T['convert_btn'], type="primary", disabled=not st.session_state["uploads"]):
    try:
        files_map = {k: v["data"] for k,v in st.session_state["uploads"].items()}
        per_file = []
        for name, data in files_map.items():
            inv = _parse_invoice_xmltodict(data)
            rows = _rows_from_invoice(inv)
            if rows: per_file.append(rows)
        
        if per_file:
            all_rows = [r for sub in per_file for r in sub]
            xlsx = _df_to_xlsx_stream(all_rows)
            st.session_state["result_bytes"] = xlsx.getvalue()
            st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            st.success(T['success_msg'])
        else: st.warning("No valid data.")
    except Exception: st.error(T['error_msg'])

if st.session_state["result_bytes"]:
    st.download_button(T['download_btn'], st.session_state["result_bytes"], "Data.xlsx", st.session_state["result_mime"], type="primary")

st.markdown(f'<div class="custom-footer">{T["copyright"]}</div>', unsafe_allow_html=True)
