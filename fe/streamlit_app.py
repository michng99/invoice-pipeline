import io
import time
import re
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
import xlsxwriter
import xmltodict

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
        /* Ẩn UI mặc định rác của Streamlit */
        a[href*="streamlit.io/cloud"], div[class*="viewerBadge"], 
        #MainMenu, footer, header, [data-testid="stHeader"], .stDeployButton 
        { display: none !important; }
        
        .block-container { padding-top: 1rem !important; padding-bottom: 100px !important; }
        
        /* Footer custom */
        .custom-footer {
            width: 100%; text-align: center; color: #888;
            padding-top: 20px; margin-bottom: 20px; border-top: 1px solid #333;
            font-size: 12px; font-family: sans-serif;
        }
        
        /* Button to hơn cho dễ bấm */
        button { min-height: 48px !important; }
        
        /* Fix màu input cho dark/light mode */
        input { color: inherit !important; }
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Session State chuẩn chỉ
def init_session_state():
    defaults = {
        "uploads": {},       # Chứa file raw bytes
        "busy": False,       # Trạng thái xử lý
        "lang_code": "vi",   # Mặc định Tiếng Việt
        "theme": "light",    # Mặc định sáng
        "result_bytes": None,# Kết quả excel
        "result_mime": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# Apply Theme thủ công (nếu cần xử lý sâu hơn CSS)
if st.session_state["theme"] == "dark":
    st.markdown("""<style>.stApp {background-color: #0E1117; color: #FAFAFA;}</style>""", unsafe_allow_html=True)

# ==============================================================================
# 2. CORE LOGIC (DEEP SEARCH & PARSING)
# ==============================================================================

COLUMN_ORDER = [
    "Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn",
    "ST người bán", "Tên người bán", "ĐC người bán",
    "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá",
    "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền",
    "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)",
]
MAX_FILES_ALLOWED = 50          
MAX_FILE_SIZE_MB = 10            

def _num(v):
    """Chuyển đổi an toàn sang float"""
    if not v: return 0.0
    try:
        # Xử lý các trường hợp chuỗi số kiểu "1,000.00" hoặc "1.000,00"
        s = str(v).strip()
        if "," in s and "." in s: s = s.replace(",", "") # Ưu tiên format chuẩn
        else: s = s.replace(",", "")
        return float(s)
    except: return 0.0

def _find_key_recursive(obj: Any, targets: List[str]) -> Any:
    """
    Deep Search: Tìm key trong dict bất chấp độ sâu (Recursive).
    Dùng để đào 'TSuat' hoặc 'ThueSuat' nếu nó bị giấu sâu.
    """
    if isinstance(obj, dict):
        # 1. Tìm ở level hiện tại (Fuzzy - bỏ namespace)
        for k, v in obj.items():
            clean_k = k.split(":")[-1] if ":" in k else k
            if clean_k in targets and v is not None:
                return v
        
        # 2. Nếu không thấy, đào sâu xuống con
        for v in obj.values():
            found = _find_key_recursive(v, targets)
            if found: return found
            
    elif isinstance(obj, list):
        # Nếu là list, duyệt từng phần tử
        for item in obj:
            found = _find_key_recursive(item, targets)
            if found: return found
            
    return None

def _get_value(obj: dict, targets: List[str]) -> str:
    """Wrapper cho hàm tìm kiếm, trả về string an toàn"""
    val = _find_key_recursive(obj, targets)
    if val:
        if isinstance(val, (dict, list)): return "" # Không lấy nếu nó là object phức tạp
        return str(val)
    return ""

def _parse_invoice_smart(xml_bytes: bytes, filename: str) -> dict:
    try:
        # Parse XML -> Dict
        doc = xmltodict.parse(xml_bytes, disable_entities=True) # Bảo mật XXE
        
        # Lấy root node
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # --- HEADER INFO ---
        # Tìm các trường thông tin chung bằng Deep Search luôn cho chắc
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
        }
        
        # --- SELLER INFO ---
        # Tìm node người bán trước để khoanh vùng tìm kiếm cho chính xác
        # Tránh nhầm với người mua
        nban_data = _find_key_recursive(hdon, ["NBan", "Seller", "NguoiBan"]) or hdon
        invoice["NBan"] = {
            "Ten":  _get_value(nban_data, ["Ten", "Name", "TNNBan"]),
            "MST":  _get_value(nban_data, ["MST", "MaSoThue", "MSTNban"]),
            "DChi": _get_value(nban_data, ["DChi", "DiaChi", "DCNBan"]),
        }
        
        # --- ITEMS (HÀNG HÓA) ---
        items = []
        # Tìm list hàng hóa. Cố gắng tìm node cha trước: DSHHDVu
        list_container = _find_key_recursive(hdon, ["DSHHDVu", "ListItems"]) or hdon
        
        # Tìm mảng item bên trong
        raw_items = _find_key_recursive(list_container, ["HHDVu", "Item", "HangHoa"])
        
        if raw_items:
            if isinstance(raw_items, dict): raw_items = [raw_items] # Chuẩn hóa list
            
            for it in raw_items:
                # Tìm thuế suất (Deep search trong scope của item này)
                ts_keys = ["TSuat", "ThueSuat", "TSuatGTGT", "TaxRate", "LTSuat"]
                ts_val = _get_value(it, ts_keys)
                
                # Tìm tiền thuế & thành tiền
                vat = _get_value(it, ["VATAmount", "TienThue", "TienThueGTGT"])
                amt = _get_value(it, ["Amount", "TongTien", "ThanhTienSauThue"])
                tht = _get_value(it, ["ThTien", "ThanhTien", "ThanhTienTruocThue"])

                items.append({
                    "MHHDVu":  _get_value(it, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_value(it, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_value(it, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_value(it, ["SLuong", "SoLuong"]),
                    "DGia":    _get_value(it, ["DGia", "DonGia"]),
                    "ThTien":  tht,
                    "TSuat":   ts_val,
                    "VATAmount": vat,
                    "Amount":  amt,
                    "TChat":   _get_value(it, ["TChat", "TinhChat"])
                })
        
        invoice["Items"] = items
        return invoice

    except Exception as e:
        # print(f"Lỗi parse {filename}: {e}") # Debug only
        return {}

def _rows_from_invoice(inv: dict) -> list[dict]:
    if not inv: return []
    try:
        # Lấy thông tin chung
        header_info = {
            "Mẫu số": inv.get("KHMSHDon", ""),
            "KH hóa đơn": inv.get("KHHDon", ""),
            "Số hóa đơn": inv.get("SHDon", ""),
            "Ngày hóa đơn": inv.get("NLap", ""),
            "ST người bán": inv["NBan"].get("MST", ""),
            "Tên người bán": inv["NBan"].get("Ten", ""),
            "ĐC người bán": inv["NBan"].get("DChi", ""),
            "Đơn vị tiền": inv.get("DVTTe", "VND"),
            "Tỷ giá": _num(inv.get("TGia")),
            "Ghi chú": "Hoá đơn điện tử"
        }

        items = inv.get("Items", [])
        rows = []
        
        for it in items:
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            tht = _num(it["ThTien"])
            vat = _num(it["VATAmount"])
            total = _num(it["Amount"])
            
            # --- XỬ LÝ LOGIC THUẾ SUẤT THÔNG MINH ---
            ts_raw = it["TSuat"]
            ts_display = ts_raw # Giá trị hiển thị cuối cùng
            
            # Logic: Nếu có text thuế suất, hiển thị text đó.
            # Nếu text rỗng hoặc "0", mà có tiền thuế -> Tính ngược lại để hiển thị
            is_vat_valid = vat > 0 and tht > 0
            
            # Clean text thuế suất (ví dụ: "8%" -> 8, "0.08" -> 8)
            clean_ts = str(ts_raw).replace("%","").replace(",",".").strip()
            
            # Case 1: Nếu data gốc không có thuế suất hoặc = 0, nhưng có tiền thuế -> Tính ngược
            if (not ts_raw or clean_ts == "0") and is_vat_valid:
                 calc = (vat / tht) * 100
                 # Snap vào các mốc phổ biến
                 if abs(calc - 5) < 0.5: ts_display = "5%"
                 elif abs(calc - 8) < 0.5: ts_display = "8%"
                 elif abs(calc - 10) < 0.5: ts_display = "10%"
                 else: ts_display = f"{round(calc, 2)}%"
            
            # Tính lại tổng nếu thiếu
            if total == 0: total = tht + vat
            
            # Tạo dòng
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"],
                "Tên hàng": it["THHDVu"],
                "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl,
                "Đơn giá": dg,
                "Tiền hàng": tht,
                "Thuế suất": ts_display,
                "Tiền thuế": vat,
                "Cộng tiền": total,
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
            
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: list[dict]) -> io.BytesIO:
    if not rows: return None
    df = pd.DataFrame(rows)
    # Đảm bảo đúng thứ tự cột
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[existing_cols]
    
    # Convert số học
    cols_to_num = ["Số lượng","Đơn giá","Tiền hàng","Tiền thuế","Cộng tiền","Tỷ giá"]
    for c in cols_to_num:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
        
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
        # Format cột rộng ra chút cho đẹp
        worksheet = wr.sheets['Data']
        worksheet.set_column('A:T', 15) 
    buf.seek(0)
    return buf

# ==============================================================================
# 3. FRONTEND (GIAO DIỆN & TƯƠNG TÁC)
# ==============================================================================

# --- UI LANGUAGE DICTIONARY ---
LANG = {
    "vi": {
        "page_title": "Xử lý Hóa đơn", "settings": "Cài đặt",
        "mode_info": "Chế độ: **All-in-One** (Bảo mật & Riêng tư)",
        "upload_label": "Thả file XML vào đây (Hỗ trợ kéo thả nhiều file)", 
        "upload_help": "Giới hạn 50 file, tối đa 10MB/file",
        "col_name": "Tên file", "col_size": "Kích thước", 
        "convert_btn": "🚀 Chuyển đổi sang Excel",
        "success_msg": "✅ Xử lý thành công!", "error_msg": "Có lỗi xảy ra trong quá trình xử lý.",
        "download_btn": "⬇️ Tải file Excel",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "clear_all": "Xoá danh sách", "empty_list": "Chưa có file nào được chọn."
    },
    "en": {
        "page_title": "Invoice Pipeline", "settings": "Settings",
        "mode_info": "Mode: **All-in-One** (Secure & Private)",
        "upload_label": "Drop XML files here", 
        "upload_help": "Limit 50 files, max 10MB/file",
        "col_name": "Filename", "col_size": "Size", 
        "convert_btn": "🚀 Convert to Excel",
        "success_msg": "✅ Done!", "error_msg": "Processing error.",
        "download_btn": "⬇️ Download Excel",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "clear_all": "Clear List", "empty_list": "No files selected."
    }
}

T = LANG[st.session_state["lang_code"]]

# Header & Settings
col_head, col_set = st.columns([6, 1], gap="small")
with col_head: st.title(f"{T['page_title']}")
with col_set:
    # Fix warning use_container_width
    with st.popover(f"⚙️ {T['settings']}"):
        # Language Switcher
        is_vn = st.session_state["lang_code"] == "vi"
        new_lang_val = st.toggle("Tiếng Việt / English", value=is_vn)
        new_lang_code = "vi" if new_lang_val else "en"
        
        # Chỉ rerun nếu có thay đổi thực sự
        if new_lang_code != st.session_state["lang_code"]:
            st.session_state["lang_code"] = new_lang_code
            st.rerun()

        # Theme Switcher
        theme = st.radio("Theme", ["Light", "Dark"], index=0 if st.session_state["theme"]=="light" else 1, horizontal=True)
        if theme.lower() != st.session_state["theme"]:
            st.session_state["theme"] = theme.lower()
            st.rerun()

with st.container(border=True):
    st.info(T["mode_info"])

st.divider()

# --- UPLOAD SECTION (FIXED KEY) ---
# Quan trọng: key="main_uploader" giúp giữ trạng thái file khi đổi ngôn ngữ
uploaded_files = st.file_uploader(
    label=T['upload_label'],
    type=["xml"],
    accept_multiple_files=True,
    help=T['upload_help'],
    key="main_uploader" 
)

# Logic thêm file vào Session State (Accumulator Pattern)
if uploaded_files:
    store = st.session_state["uploads"]
    new_files_count = 0
    for f in uploaded_files:
        if len(store) >= MAX_FILES_ALLOWED: break
        if f.name not in store: # Tránh trùng lặp
            try:
                data = f.read()
                if len(data) <= MAX_FILE_SIZE_MB * 1024 * 1024:
                    store[f.name] = {"data": data, "size": len(data)}
                    new_files_count += 1
            except Exception: pass
    
    # Nếu có file mới, rerun nhẹ để cập nhật danh sách hiển thị bên dưới
    if new_files_count > 0:
        # ĐÃ SỬA LỖI Ở DÒNG DƯỚI NÀY (icon="📥")
        st.toast(f"Đã thêm {new_files_count} file mới!", icon="📥")

# --- FILE LIST VIEW ---
if st.session_state["uploads"]:
    c1, c2 = st.columns([3, 1])
    
    # Hiển thị list file dạng bảng nhỏ gọn
    file_list = [{"STT": i+1, T['col_name']: k, T['col_size']: f"{v['size']/1024:.1f} KB"} 
                 for i, (k, v) in enumerate(st.session_state["uploads"].items())]
    
    with c1:
        st.dataframe(file_list, use_container_width=True, hide_index=True, height=min(300, 100 + len(file_list)*35))
    
    with c2:
        if st.button(f"🗑️ {T['clear_all']}", use_container_width=True):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()
else:
    st.caption(f"_{T['empty_list']}_")

# --- CONVERT ACTION ---
if st.button(T['convert_btn'], type="primary", disabled=not st.session_state["uploads"]):
    with st.status("Đang xử lý dữ liệu...", expanded=True) as status:
        try:
            st.write("Reading XML...")
            files_map = st.session_state["uploads"]
            all_rows = []
            
            progress_bar = st.progress(0)
            total_files = len(files_map)
            
            for idx, (name, info) in enumerate(files_map.items()):
                # Parse
                inv = _parse_invoice_smart(info["data"], name)
                # Extract Rows
                rows = _rows_from_invoice(inv)
                if rows: all_rows.extend(rows)
                
                # Update progress
                progress_bar.progress((idx + 1) / total_files)
            
            st.write("Exporting Excel...")
            xlsx_buffer = _df_to_xlsx_stream(all_rows)
            
            if xlsx_buffer:
                st.session_state["result_bytes"] = xlsx_buffer.getvalue()
                st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                status.update(label=T['success_msg'], state="complete", expanded=False)
                st.balloons()
            else:
                status.update(label="Không tìm thấy dữ liệu hóa đơn hợp lệ!", state="error")
                
        except Exception as e:
            st.error(f"{T['error_msg']} {str(e)}")
            status.update(label="Failed", state="error")

# --- DOWNLOAD AREA ---
if st.session_state.get("result_bytes"):
    st.divider()
    col_dl_1, col_dl_2 = st.columns([1, 2])
    with col_dl_1:
        st.download_button(
            label=T['download_btn'],
            data=st.session_state["result_bytes"],
            file_name=f"Invoice_Export_{int(time.time())}.xlsx",
            mime=st.session_state["result_mime"],
            type="primary",
            use_container_width=True
        )

st.markdown(f'<div class="custom-footer">{T["copyright"]}</div>', unsafe_allow_html=True)
