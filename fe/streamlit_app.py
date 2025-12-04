import io
import os
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Dict, Any
from xml.etree import ElementTree as ET

import streamlit as st
import pandas as pd
import xlsxwriter

# ==============================================================================
# 1. CẤU HÌNH & CSS (GIỮ NGUYÊN UI)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

st.markdown("""
    <style>
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
# 2. CORE LOGIC (THUẬT TOÁN QUÉT 1 LẦN - SIÊU NHANH)
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

# Hàm cắt bỏ namespace {http://...}Tag -> Tag (Xử lý chuỗi đơn giản, cực nhanh)
def _local_tag(tag):
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag

def _parse_invoice_super_fast(xml_bytes: bytes, filename: str) -> dict:
    try:
        # Parse cây XML
        tree = ET.fromstring(xml_bytes)
    except Exception as e:
        print(f"Lỗi XML {filename}: {e}")
        return {}

    # Khởi tạo data
    inv = {
        "NBan": {"Ten": "", "MST": "", "DChi": ""},
        "Items": []
    }
    
    # 1. Quét toàn bộ cây XML 1 lần để tìm Header & Người bán
    # (Dùng iter() là cách nhanh nhất của ElementTree để duyệt phẳng)
    for elem in tree.iter():
        tag = _local_tag(elem.tag)
        text = _txt(elem.text)
        if not text: continue # Bỏ qua thẻ rỗng

        # Header Map
        if tag in ["KHMSHDon", "MauSo"]: inv["KHMSHDon"] = text
        elif tag in ["KHHDon", "KyHieu"]: inv["KHHDon"] = text
        elif tag in ["SHDon", "SoHoaDon"]: inv["SHDon"] = text
        elif tag in ["NLap", "NgayLap"]: inv["NLap"] = text
        elif tag in ["DVTTe", "DonViTienTe"]: inv["DVTTe"] = text
        elif tag in ["TGia", "TyGia"]: inv["TGia"] = text
        
        # Người bán Map (Chấp nhận lấy giá trị đầu tiên tìm thấy)
        # Lưu ý: Cẩn thận trùng với người mua hoặc tên hàng
        # Logic này đơn giản hóa để chạy nhanh. 
        # Nếu muốn chính xác tuyệt đối phải duyệt theo path, nhưng path thay đổi liên tục.
        # Ở đây ta ưu tiên tìm các thẻ đặc thù của người bán nếu có prefix
        
    # 2. Tìm chính xác Người bán (Duyệt lại node NBan nếu có để ghi đè cho chính xác)
    # Tìm node NBan bất kể namespace
    nban_node = None
    for elem in tree.iter():
        if _local_tag(elem.tag) in ["NBan", "Seller", "NguoiBan"]:
            nban_node = elem
            break
            
    if nban_node:
        # Chỉ quét trong node NBan
        for child in nban_node.iter():
            tag = _local_tag(child.tag)
            text = _txt(child.text)
            if not text: continue
            if tag in ["Ten", "Name", "TenNguoiBan"]: inv["NBan"]["Ten"] = text
            elif tag in ["MST", "MaSoThue", "TaxCode"]: inv["NBan"]["MST"] = text
            elif tag in ["DChi", "DiaChi", "Address"]: inv["NBan"]["DChi"] = text

    # 3. Quét Hàng hóa (HHDVu)
    # Tìm tất cả node HHDVu trước
    item_nodes = []
    for elem in tree.iter():
        if _local_tag(elem.tag) in ["HHDVu", "Item", "HangHoa"]:
            item_nodes.append(elem)
            
    for node in item_nodes:
        it = {
            "TChat": "", "MHHDVu": "", "THHDVu": "", "DVTinh": "",
            "SLuong": "", "DGia": "", "ThTien": "", 
            "TSuat": "", "VATAmount": "", "Amount": ""
        }
        
        # Duyệt cây con của Item này (Bất chấp độ sâu - TTKhac hay gì cũng thấy)
        for child in node.iter():
            tag = _local_tag(child.tag)
            text = _txt(child.text)
            if not text: continue
            
            # Map dữ liệu hàng hóa
            if tag in ["TChat", "TinhChat"]: it["TChat"] = text
            elif tag in ["MHHDVu", "MaHang"]: it["MHHDVu"] = text
            elif tag in ["THHDVu", "TenHang", "TenHangHoa"]: it["THHDVu"] = text
            elif tag in ["DVTinh", "DonViTinh"]: it["DVTinh"] = text
            elif tag in ["SLuong", "SoLuong"]: it["SLuong"] = text
            elif tag in ["DGia", "DonGia"]: it["DGia"] = text
            elif tag in ["ThTien", "ThanhTien", "ThanhTienTruocThue"]: it["ThTien"] = text
            
            # Map Thuế & Tiền (Full Dictionary)
            elif tag in ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "TaxRate", "LTSuat", "LTS"]: 
                it["TSuat"] = text
            elif tag in ["VATAmount", "TienThue", "TienThueGTGT", "VatAmount"]: 
                it["VATAmount"] = text
            elif tag in ["Amount", "TongTien", "ThanhTienSauThue"]: 
                it["Amount"] = text
                
        inv["Items"].append(it)

    return inv

def _rows_from_invoice(inv: dict) -> list[dict]:
    if not inv: return []
    try:
        # Safe Get
        h = inv
        items = inv.get("Items", [])
        
        ms = h.get("KHMSHDon") or ""
        kh = h.get("KHHDon") or ""
        so = h.get("SHDon") or ""
        ngay = h.get("NLap") or ""
        cur = h.get("DVTTe") or "VND"
        rate = _num(h.get("TGia") or 1)
        
        nb = h.get("NBan", {})
        s_ten = nb.get("Ten", "")
        s_mst = nb.get("MST", "")
        s_dchi = nb.get("DChi", "")
        ghichu = "Hoá đơn mới"

        rows = []
        for it in items:
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            tht = _num(it["ThTien"])
            vat = _num(it["VATAmount"])
            total = _num(it["Amount"])
            
            # --- XỬ LÝ THUẾ SUẤT ---
            ts_raw = it["TSuat"]
            ts_val = 0.0
            
            # Parse %
            if ts_raw:
                s = ts_raw.replace("%","").replace(",",".")
                if s and s[0].isdigit():
                    try:
                        v = float(s)
                        ts_val = v / 100 if v > 1 else v
                    except: pass
            
            # 1. Tự tính Tiền Thuế (Nếu thiếu)
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if str(cur).upper() == "VND": vat = round(vat)
            
            # 2. Suy luận ngược % Thuế (Nếu thiếu % nhưng có tiền)
            final_ts = ts_raw
            # Logic: Thuế rỗng hoặc bằng 0, nhưng có tiền thuế > 0
            if (not final_ts or final_ts == "0") and vat > 0 and tht > 0:
                try:
                    r = (vat / tht) * 100
                    # Gán nhãn đẹp
                    if abs(r - 5) < 0.5: final_ts = "5%"
                    elif abs(r - 8) < 0.5: final_ts = "8%"
                    elif abs(r - 10) < 0.5: final_ts = "10%"
                    elif abs(r - 0) < 0.1: final_ts = "0%" # Trường hợp KCT
                    else: final_ts = f"{round(r, 2)}%"
                except: pass
            
            # 3. Tự tính Tổng
            if total == 0: total = tht + vat

            row = {
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_ten, "ĐC người bán": s_dchi,
                "C người bán": "",
                "Mã hàng": it["MHHDVu"], "Tên hàng": it["THHDVu"], "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": tht,
                "Thuế suất": final_ts, "Tiền thuế": vat, "Cộng tiền": total,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": rate, "Cờ (Tchat)": it["TChat"]
            }
            rows.append(row)
        return rows
    except Exception as e:
        print(f"Build row error: {e}")
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
# 3. FRONTEND (TỐI ƯU STATE)
# ==============================================================================

if "uploads" not in st.session_state: st.session_state.update({"uploads":{}, "busy":False, "lang_code":"vi", "theme":"light"})

def _add_uploads(files, T):
    store = st.session_state["uploads"]
    if len(store) + len(files) > MAX_FILES_ALLOWED:
        st.error(T["error_too_many"].format(max=MAX_FILES_ALLOWED)); return
    for f in files:
        try:
            name = f.name
            data = f.read()
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
            inv = _parse_invoice_super_fast(data, name)
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
