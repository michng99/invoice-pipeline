import io
import os
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from xml.etree import ElementTree as ET

import streamlit as st
import pandas as pd
import xlsxwriter

# ==============================================================================
# 1. CẤU HÌNH & CSS (TỐI ƯU GIAO DIỆN)
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
# 2. CORE LOGIC (ELEMENT TREE NGUYÊN BẢN - KHÔNG REGEX)
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

def _txt(x): return (x or "").strip()

# --- HÀM TÌM KIẾM THÔNG MINH (BỎ QUA NAMESPACE) ---
def _get_tag_val(node: ET.Element, tag_names: List[str]) -> str:
    """
    Tìm giá trị của thẻ con dựa trên list tên (bỏ qua namespace).
    Ví dụ: tag_names=['TSuat'] sẽ tìm thấy cả <ns:TSuat> và <TSuat>.
    Chỉ tìm ở level con trực tiếp (Nhanh).
    """
    if node is None: return ""
    
    # Duyệt qua các thẻ con thực sự
    for child in node:
        # Lấy tên thẻ thuần (bỏ {http...})
        raw_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if raw_tag in tag_names:
            return _txt(child.text)
    return ""

def _parse_invoice_fast(xml_bytes: bytes, filename: str) -> dict:
    try:
        # Parse trực tiếp từ bytes (Siêu nhanh)
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        print(f"Lỗi đọc XML {filename}: {e}")
        return {}

    # Helper đệ quy tìm thẻ bất chấp độ sâu (Dùng cho Header)
    def find_anywhere(names):
        for elem in root.iter():
            raw = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if raw in names:
                return _txt(elem.text)
        return ""

    try:
        # Lấy thông tin chung (Header)
        invoice = {
            "KHMSHDon": find_anywhere(["KHMSHDon", "MauSo"]), 
            "KHHDon":   find_anywhere(["KHHDon", "KyHieu"]),
            "SHDon":    find_anywhere(["SHDon", "SoHoaDon"]),
            "NLap":     find_anywhere(["NLap", "NgayLap"]),
            "DVTTe":    find_anywhere(["DVTTe"]) or "VND",
            "TGia":     find_anywhere(["TGia"]) or "1",
        }
        
        # Người bán
        invoice["NBan"] = {
            "Ten":  find_anywhere(["Ten", "Name"]), # Cẩn thận trùng tên hàng
            "MST":  find_anywhere(["MST", "MaSoThue"]),
            "DChi": find_anywhere(["DChi", "DiaChi"]),
        }
        # Fix lại tên người bán nếu lỡ lấy nhầm (thường header nằm trên nên iter sẽ thấy trước)
        # Để chắc ăn, ta tìm node NBan cụ thể
        for elem in root.iter():
            raw = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if raw == "NBan":
                invoice["NBan"]["Ten"] = _get_tag_val(elem, ["Ten"])
                invoice["NBan"]["MST"] = _get_tag_val(elem, ["MST"])
                invoice["NBan"]["DChi"] = _get_tag_val(elem, ["DChi"])
                break

        # Lấy hàng hóa
        items = []
        # Tìm tất cả thẻ HHDVu
        for elem in root.iter():
            raw = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if raw == "HHDVu":
                # Lấy các trường cơ bản
                it = {
                    "TChat":   _get_tag_val(elem, ["TChat"]),
                    "MHHDVu":  _get_tag_val(elem, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_tag_val(elem, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_tag_val(elem, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_tag_val(elem, ["SLuong", "SoLuong"]),
                    "DGia":    _get_tag_val(elem, ["DGia", "DonGia"]),
                    "ThTien":  _get_tag_val(elem, ["ThTien", "ThanhTien"]),
                    "TSuat":   _get_tag_val(elem, ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "LTSuat", "LTS"]),
                    "VATAmount": "",
                    "Amount": ""
                }
                
                # Tìm VAT & Amount (Thường nằm trong TTKhac con của HHDVu)
                # Hoặc nằm ngay trong HHDVu
                vat_direct = _get_tag_val(elem, ["VATAmount", "TienThue"])
                amt_direct = _get_tag_val(elem, ["Amount", "TongTien"])
                
                if vat_direct: it["VATAmount"] = vat_direct
                if amt_direct: it["Amount"] = amt_direct
                
                # Nếu chưa thấy, tìm trong con (TTKhac)
                for child in elem:
                    raw_child = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if raw_child in ["TTKhac", "ThongTinKhac"]:
                        if not it["VATAmount"]: it["VATAmount"] = _get_tag_val(child, ["VATAmount", "TienThue"])
                        if not it["Amount"]: it["Amount"] = _get_tag_val(child, ["Amount", "TongTien"])

                items.append(it)
                
        invoice["Items"] = items
        return invoice
    except Exception as e:
        print(f"Logic error {filename}: {e}")
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
            sl = _num(it.get("SLuong"))
            dg = _num(it.get("DGia"))
            tht = _num(it.get("ThTien"))
            vat = _num(it.get("VATAmount"))
            total = _num(it.get("Amount"))
            
            # Xử lý thuế suất
            ts_raw = it.get("TSuat")
            ts_val = 0.0
            if ts_raw:
                try:
                    clean = ts_raw.replace("%","").replace(",",".")
                    if clean[0].isdigit():
                        val = float(clean)
                        ts_val = val / 100 if val > 1 else val
                except: pass

            # --- TÍNH TOÁN & SUY LUẬN ---
            
            # 1. Tự tính VAT nếu thiếu (nhưng có thuế suất)
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if str(cur).upper() == "VND": vat = round(vat)
            
            # 2. Suy luận ngược % nếu thiếu (nhưng có tiền thuế)
            final_ts = ts_raw
            if not final_ts and vat > 0 and tht > 0:
                try:
                    r = (vat/tht)*100
                    if abs(r-5)<0.5: final_ts="5%"
                    elif abs(r-8)<0.5: final_ts="8%"
                    elif abs(r-10)<0.5: final_ts="10%"
                    else: final_ts=f"{round(r)}%"
                except: pass

            if total == 0: total = tht + vat

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
            # Đọc file một lần duy nhất
            data = f.read() 
            store[name] = {"data": data, "size": len(data), "uploaded_at": time.time()}
        except: continue

# --- UI ---
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
# Logic upload nhanh gọn, không seek tới lui
if uploaded_files: 
    _add_uploads(uploaded_files, T)
    st.rerun() # Refresh ngay để enable nút convert

if st.session_state["uploads"]:
    c1, c2 = st.columns([3,1])
    rows = [{T['col_name']:k, T['col_size']:v["size"]} for k,v in st.session_state["uploads"].items()]
    c1.dataframe(rows, use_container_width=True, hide_index=True)
    if c2.button(f"🧽 {T['clear_all']}", use_container_width=True): 
        st.session_state["uploads"].clear(); st.session_state.pop("result_bytes", None); st.rerun()
else: st.caption(f"_{T['empty_list']}_")

merge = st.checkbox(T['merge_label'], value=True)
# Nút convert chỉ hiện khi có file
if st.button(T['convert_btn'], type="primary", disabled=not st.session_state["uploads"]):
    try:
        files_map = {k: v["data"] for k,v in st.session_state["uploads"].items()}
        per_file = []
        for name, data in files_map.items():
            inv = _parse_invoice_fast(data, name) # Dùng hàm parse mới siêu nhanh
            rows = _rows_from_invoice(inv)
            if rows: per_file.append(rows)
        
        if per_file:
            all_rows = [r for sub in per_file for r in sub]
            xlsx = _df_to_xlsx_stream(all_rows)
            st.session_state["result_bytes"] = xlsx.getvalue()
            st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            st.success(T['success_msg'])
        else: st.warning("Không tìm thấy dữ liệu hợp lệ trong file XML.")
    except Exception as e: 
        print(f"Error: {e}")
        st.error(T['error_msg'])

if st.session_state.get("result_bytes"):
    st.download_button(T['download_btn'], st.session_state["result_bytes"], "Data.xlsx", st.session_state["result_mime"], type="primary")

st.markdown(f'<div class="custom-footer">{T["copyright"]}</div>', unsafe_allow_html=True)
