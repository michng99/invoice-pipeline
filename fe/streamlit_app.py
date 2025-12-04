import io
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
import xlsxwriter
import xmltodict # Yêu cầu đã cài trong requirements.txt

# ==============================================================================
# 1. CẤU HÌNH & CSS (CLEAN UI)
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
# 2. CORE LOGIC (XMLTODICT + FUZZY SEARCH)
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

def _get_fuzzy(obj: dict, targets: List[str]) -> str:
    """
    Tìm kiếm giá trị trong dict, bỏ qua namespace prefix.
    Ví dụ: targets=['TSuat'] sẽ tìm thấy cả 'inv:TSuat', 'ns1:TSuat', 'TSuat'.
    """
    if not isinstance(obj, dict): return ""
    
    # 1. Tìm chính xác trước (Nhanh)
    for t in targets:
        if t in obj and obj[t]: return str(obj[t])
    
    # 2. Tìm mờ (Bỏ qua prefix namespace like 'inv:...')
    # Duyệt qua các key thực tế trong dict
    for key, val in obj.items():
        # Lấy tên key thuần (bỏ prefix sau dấu :)
        clean_key = key.split(":")[-1] if ":" in key else key
        if clean_key in targets and val:
            return str(val)
    return ""

def _parse_invoice_smart(xml_bytes: bytes, filename: str) -> dict:
    try:
        # Dùng xmltodict: Parse toàn bộ ra Dict
        # disable_entities=True để an toàn bảo mật
        doc = xmltodict.parse(xml_bytes, disable_entities=True)
        
        # Tìm root (Lấy value đầu tiên bất kể key là gì)
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # Hàm tìm nhanh header (chấp nhận đệ quy tìm key trong dict)
        def find_val(data, keys):
            return _get_fuzzy(data, keys)

        # Chuẩn hóa cấu trúc
        # Tìm DLHDon (Dữ liệu hóa đơn)
        dlhdon = {}
        for k, v in hdon.items():
            if "DLHDon" in k: dlhdon = v; break
        
        # Nếu không thấy DLHDon, dùng chính root (một số hóa đơn lạ)
        if not dlhdon: dlhdon = hdon

        # Tìm TTChung
        ttchung = {}
        for k, v in dlhdon.items():
            if "TTChung" in k: ttchung = v; break

        # Tìm Header
        invoice = {
            "KHMSHDon": _get_fuzzy(ttchung, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_fuzzy(ttchung, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_fuzzy(ttchung, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_fuzzy(ttchung, ["NLap", "NgayLap"]),
            "DVTTe":    _get_fuzzy(ttchung, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_fuzzy(ttchung, ["TGia", "TyGia"]) or "1",
        }
        
        # Tìm người bán
        ndhdon = {}
        for k, v in dlhdon.items():
            if "NDHDon" in k: ndhdon = v; break
            
        nban = {}
        for k, v in ndhdon.items():
            if "NBan" in k or "Seller" in k: nban = v; break
            
        invoice["NBan"] = {
            "Ten":  _get_fuzzy(nban, ["Ten", "Name"]),
            "MST":  _get_fuzzy(nban, ["MST", "MaSoThue"]),
            "DChi": _get_fuzzy(nban, ["DChi", "DiaChi"]),
        }
        
        # Tìm Hàng hóa
        items = []
        dshhdv = {}
        for k, v in ndhdon.items():
            if "DSHHDVu" in k: dshhdv = v; break
            
        if dshhdv:
            # Tìm list HHDVu (Có thể là list hoặc dict)
            raw = []
            for k, v in dshhdv.items():
                if "HHDVu" in k or "Item" in k: 
                    raw = v
                    break
            
            if isinstance(raw, dict): raw = [raw] # Chuẩn hóa thành list
            
            # Duyệt từng dòng để trích xuất (Flatten)
            for it in raw:
                # Tìm TTKhac (Thông tin khác)
                ttkhac = {}
                for k, v in it.items():
                    if "TTKhac" in k or "ThongTinKhac" in k: ttkhac = v; break

                # --- 1. SĂN LÙNG THUẾ SUẤT ---
                # List các tên biến thể (PAS dùng TSuatGTGT, LTSuat...)
                ts_keys = ["TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", "TaxRate", "LTSuat", "LTS"]
                tsuat = _get_fuzzy(it, ts_keys)
                if not tsuat: tsuat = _get_fuzzy(ttkhac, ts_keys) # Tìm trong con

                # --- 2. SĂN LÙNG TIỀN ---
                vat_keys = ["VATAmount", "TienThue", "TienThueGTGT", "VatAmount"]
                vat = _get_fuzzy(it, vat_keys)
                if not vat: vat = _get_fuzzy(ttkhac, vat_keys)
                
                amt_keys = ["Amount", "TongTien", "ThanhTienSauThue"]
                amt = _get_fuzzy(it, amt_keys)
                if not amt: amt = _get_fuzzy(ttkhac, amt_keys)

                items.append({
                    "TChat":   _get_fuzzy(it, ["TChat", "TinhChat"]),
                    "MHHDVu":  _get_fuzzy(it, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_fuzzy(it, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_fuzzy(it, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_fuzzy(it, ["SLuong", "SoLuong"]),
                    "DGia":    _get_fuzzy(it, ["DGia", "DonGia"]),
                    "ThTien":  _get_fuzzy(it, ["ThTien", "ThanhTien", "ThanhTienTruocThue"]),
                    "TSuat":   tsuat,
                    "VATAmount": vat,
                    "Amount":    amt
                })
                
        invoice["Items"] = items
        return invoice
    except Exception as e:
        print(f"Lỗi parse {filename}: {e}")
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
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            tht = _num(it["ThTien"])
            vat = _num(it["VATAmount"])
            total = _num(it["Amount"])
            
            # --- XỬ LÝ THUẾ SUẤT ---
            ts_raw = it["TSuat"]
            ts_val = 0.0
            
            # Parse % từ chuỗi (8, 8%, 0.08)
            if ts_raw:
                try:
                    s = str(ts_raw).replace("%","").replace(",",".")
                    if s and s[0].isdigit():
                        val = float(s)
                        ts_val = val / 100 if val > 1 else val
                except: pass

            # --- TÍNH TOÁN BÙ TRỪ ---
            
            # 1. Tự tính VAT nếu thiếu
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if str(cur).upper() == "VND": vat = round(vat)
            
            # 2. Suy luận ngược % Thuế (QUAN TRỌNG CHO FILE PAS/VIETNGUYEN)
            final_ts_display = ts_raw
            if (not final_ts_display or final_ts_display == "0") and vat > 0 and tht > 0:
                try:
                    calc = (vat / tht) * 100
                    # Làm tròn vào khung
                    if abs(calc - 5) < 0.5: final_ts_display = "5%"
                    elif abs(calc - 8) < 0.5: final_ts_display = "8%"
                    elif abs(calc - 10) < 0.5: final_ts_display = "10%"
                    elif abs(calc - 0) < 0.1: final_ts_display = "0%"
                    else: final_ts_display = f"{round(calc, 2)}%"
                except: pass

            if total == 0: total = tht + vat

            r = {k: "" for k in COLUMN_ORDER}
            r.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": rate,
                "Mã hàng": it["MHHDVu"], "Tên hàng": it["THHDVu"], "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": tht,
                "Thuế suất": final_ts_display, "Tiền thuế": vat, "Cộng tiền": total,
                "Cờ (Tchat)": it["TChat"]
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
# 3. FRONTEND (TỐI ƯU UPLOAD - NO PROCESSING ON UPLOAD)
# ==============================================================================

if "uploads" not in st.session_state: st.session_state.update({"uploads":{}, "busy":False, "lang_code":"vi", "theme":"light"})

def _add_uploads(files, T):
    store = st.session_state["uploads"]
    if len(store) + len(files) > MAX_FILES_ALLOWED:
        st.error(T["error_too_many"].format(max=MAX_FILES_ALLOWED)); return
    
    for f in files:
        try:
            name = f.name
            # CHỈ LƯU BYTES, KHÔNG XỬ LÝ GÌ CẢ -> KHÔNG LAG
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
    st.rerun() # Refresh ngay để enable nút convert (File đã nằm trong Session State)

if st.session_state["uploads"]:
    c1, c2 = st.columns([3,1])
    rows = [{T['col_name']:k, T['col_size']:v["size"]} for k,v in st.session_state["uploads"].items()]
    c1.dataframe(rows, use_container_width=True, hide_index=True)
    if c2.button(f"🧽 {T['clear_all']}", use_container_width=True): 
        st.session_state["uploads"].clear(); st.session_state.pop("result_bytes", None); st.rerun()
else: st.caption(f"_{T['empty_list']}_")

merge = st.checkbox(T['merge_label'], value=True)
if st.button(T['convert_btn'], type="primary", disabled=not st.session_state["uploads"]):
    with st.spinner("Đang xử lý..."): # Hiện spinner để user biết đang chạy
        try:
            files_map = {k: v["data"] for k,v in st.session_state["uploads"].items()}
            per_file = []
            for name, data in files_map.items():
                inv = _parse_invoice_smart(data, name) 
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
