import io
import time
from typing import List, Any, Dict, Optional
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH & BẢO MẬT (CONFIGURATION & SECURITY)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

# Giới hạn cứng để chống DDoS và tràn RAM
MAX_FILES_ALLOWED = 50       
MAX_FILE_SIZE_MB = 10        
ALLOWED_EXTENSIONS = ["xml"]

# CSS Tối ưu giao diện (Clean UI)
st.markdown("""
    <style>
        /* Ẩn các thành phần mặc định của Streamlit */
        .stDeployButton, footer, header, [data-testid="stHeader"] { display: none !important; }
        .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
        
        /* Custom Footer */
        .custom-footer {
            width: 100%; text-align: center; color: #888;
            padding-top: 20px; border-top: 1px solid #eee;
            font-size: 12px; margin-top: 40px; font-family: sans-serif;
        }
        
        /* Nút bấm to rõ */
        button[kind="primary"] { 
            min-height: 50px !important; 
            font-weight: 600 !important;
            font-size: 16px !important;
        }
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Session State
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None

# ==============================================================================
# 2. LOGIC LÕI (CORE BUSINESS LOGIC)
# ==============================================================================

def _num(v: Any) -> float:
    """Chuyển đổi an toàn sang số thực. Xử lý tốt cả dấu chấm và phẩy."""
    if not v: return 0.0
    try:
        s = str(v).strip()
        # Case: 1.000,00 (VN) -> bỏ chấm, thay phẩy bằng chấm
        if "," in s and "." in s: 
            if s.find(".") < s.find(","): # Dạng 1.000,00
                s = s.replace(".", "").replace(",", ".")
            else: # Dạng 1,000.00 (US)
                s = s.replace(",", "")
        elif "," in s: 
            s = s.replace(",", ".") # Case: 10,5 -> 10.5
        return float(s)
    except: return 0.0

def _find_key_recursive(obj: Any, targets: List[str]) -> Any:
    """Tìm giá trị (Value) của key trong XML bất chấp độ sâu."""
    if isinstance(obj, dict):
        # Tìm ở level hiện tại
        for k, v in obj.items():
            clean_k = k.split(":")[-1] # Xử lý namespace vd: inv:InvoiceData
            if clean_k in targets and v is not None:
                return v
        # Đào sâu xuống con
        for v in obj.values():
            found = _find_key_recursive(v, targets)
            if found is not None: return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, targets)
            if found is not None: return found
    return None

def _check_tag_exists_recursive(obj: Any, targets: List[str]) -> bool:
    """Kiểm tra sự TỒN TẠI của thẻ (dùng bắt lỗi HĐ Điều chỉnh/Thay thế)."""
    if isinstance(obj, dict):
        for k in obj.keys():
            clean_k = k.split(":")[-1]
            if clean_k in targets: return True
        for v in obj.values():
            if _check_tag_exists_recursive(v, targets): return True
    elif isinstance(obj, list):
        for item in obj:
            if _check_tag_exists_recursive(item, targets): return True
    return False

def _get_value(obj: dict, targets: List[str]) -> str:
    """Wrapper an toàn, trả về chuỗi rỗng nếu không tìm thấy."""
    val = _find_key_recursive(obj, targets)
    if val:
        if isinstance(val, (dict, list)): return "" 
        return str(val)
    return ""

def _parse_invoice_data(xml_bytes: bytes, filename: str) -> dict:
    """Phân tích XML thành Dict, trích xuất thông tin quan trọng."""
    try:
        # Parse XML (đã bỏ disable_entities để tương thích tốt hơn với xmltodict chuẩn)
        doc = xmltodict.parse(xml_bytes)
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # 1. Logic phân loại hóa đơn
        is_dieuchinh = _check_tag_exists_recursive(hdon, ["TDieuChinh", "DieuChinh"])
        is_thaythe = _check_tag_exists_recursive(hdon, ["ThayThe"])
        
        note_str = "Hóa đơn mới"
        if is_dieuchinh: note_str = "Hóa đơn điều chỉnh"
        elif is_thaythe: note_str = "Hóa đơn thay thế"
        
        # 2. Header Info
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
            "GhiChu":   note_str 
        }
        
        # 3. Seller Info
        nban_data = _find_key_recursive(hdon, ["NBan", "Seller", "NguoiBan"]) or hdon
        invoice["NBan"] = {
            "Ten":  _get_value(nban_data, ["Ten", "Name", "TNNBan"]),
            "MST":  _get_value(nban_data, ["MST", "MaSoThue", "MSTNban"]),
            "DChi": _get_value(nban_data, ["DChi", "DiaChi", "DCNBan"]),
        }
        
        # 4. Items Info
        items = []
        # Tìm container chứa danh sách hàng hóa
        list_container = _find_key_recursive(hdon, ["DSHHDVu", "ListItems"]) or hdon
        # Tìm danh sách hàng hóa cụ thể
        raw_items = _find_key_recursive(list_container, ["HHDVu", "Item", "HangHoa"])
        
        if raw_items:
            if isinstance(raw_items, dict): raw_items = [raw_items] # Chuẩn hóa thành list
            
            for it in raw_items:
                items.append({
                    "MHHDVu":  _get_value(it, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_value(it, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_value(it, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_value(it, ["SLuong", "SoLuong"]),
                    "DGia":    _get_value(it, ["DGia", "DonGia"]),
                    "ThTien":  _get_value(it, ["ThTien", "ThanhTien", "ThanhTienTruocThue"]),
                    "TSuat":   _get_value(it, ["TSuat", "ThueSuat", "TSuatGTGT", "TaxRate"]),
                    "TChat":   _get_value(it, ["TChat", "TinhChat"]) 
                })
        
        invoice["Items"] = items
        del doc 
        return invoice

    except Exception as e:
        return {}

def _rows_from_invoice(inv: dict) -> List[dict]:
    """Chuyển Dict Invoice -> List Rows (Tính toán lại thuế chuẩn xác)."""
    if not inv: return []
    try:
        # Thông tin chung cho mọi dòng của hóa đơn này
        header_info = {
            "Mẫu số": inv.get("KHMSHDon", ""),
            "KH hóa đơn": inv.get("KHHDon", ""),
            "Số hóa đơn": inv.get("SHDon", ""),
            "Ngày hóa đơn": inv.get("NLap", ""),
            "MST người bán": inv["NBan"].get("MST", ""),
            "Tên người bán": inv["NBan"].get("Ten", ""),
            "ĐC người bán": inv["NBan"].get("DChi", ""),
            "Đơn vị tiền": inv.get("DVTTe", "VND"),
            "Tỷ giá": _num(inv.get("TGia")),
            "Ghi chú": inv.get("GhiChu", "")
        }

        items = inv.get("Items", [])
        rows = []
        
        for it in items:
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            
            # Ưu tiên lấy Thành tiền gốc từ XML, nếu không có mới tự nhân
            tht_raw = it["ThTien"]
            tht = _num(tht_raw) if tht_raw else (sl * dg)

            # --- LOGIC TÍNH THUẾ CHUẨN ---
            ts_raw = str(it["TSuat"]).strip().upper()
            rate_val = 0.0
            ts_display = ts_raw
            
            # Xử lý các case thuế suất quái dị
            if any(x in ts_raw for x in ["KCT", "KKKNT", "KHONG"]):
                rate_val = 0.0
            elif '%' in ts_raw:
                try:
                    clean_num = ts_raw.replace('%', '').replace(',', '.')
                    rate_val = float(clean_num) / 100
                except: rate_val = 0.0
            elif ts_raw.replace('.', '').isdigit() and ts_raw != "": 
                try:
                    val_check = float(ts_raw)
                    # Quy ước: Nếu < 1 (0.08) là tỷ lệ, nếu > 1 (8) là số phần trăm
                    if val_check < 1: 
                        rate_val = val_check
                        ts_display = f"{int(val_check*100)}%"
                    else: 
                        rate_val = val_check / 100
                        ts_display = f"{ts_raw}%"
                except: rate_val = 0.0
            
            # Tính Tiền Thuế = Round(Thành tiền * Thuế suất)
            vat = round(tht * rate_val, 0)
            
            # Cộng tiền = Thành tiền + Tiền thuế
            total = tht + vat
            
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"],
                "Tên hàng": it["THHDVu"],
                "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl,
                "Đơn giá": dg,
                "Tiền hàng": int(tht),     # Ép kiểu int cho gọn số tiền VND
                "Thuế suất": ts_display,
                "Tiền thuế": int(vat),
                "Cộng tiền": int(total),
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
            
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: List[dict]) -> io.BytesIO:
    """Xuất Excel đẹp sử dụng XlsxWriter."""
    if not rows: return None
    
    # Thứ tự cột mong muốn
    COLUMN_ORDER = [
        "Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn",
        "MST người bán", "Tên người bán", "ĐC người bán",
        "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá",
        "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền",
        "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)",
    ]
    
    df = pd.DataFrame(rows)
    # Reorder columns nếu tồn tại
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[existing_cols]
    
    # Clean data lần cuối
    cols_to_num = ["Số lượng","Đơn giá","Tiền hàng","Tiền thuế","Cộng tiền","Tỷ giá"]
    for c in cols_to_num:
        if c in df.columns: 
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
        
        workbook = wr.book
        worksheet = wr.sheets['Data']
        
        # Format Header: Xanh nhạt, Bold, Border
        header_fmt = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'vcenter', 
            'fg_color': '#D7E4BC', 'border': 1, 'font_size': 10
        })
        
        # Format Số: Có dấu phân cách hàng nghìn
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1})
        text_fmt = workbook.add_format({'border': 1, 'text_wrap': False})
        
        # Apply Format cho từng cột
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            
            # Set width
            width = 15
            if "Tên" in value or "ĐC" in value: width = 35
            elif "Ghi chú" in value: width = 20
            elif "Số lượng" in value or "ĐVT" in value: width = 10
            worksheet.set_column(col_num, col_num, width)
        
    buf.seek(0)
    return buf

# ==============================================================================
# 3. GIAO DIỆN NGƯỜI DÙNG (FRONTEND UI)
# ==============================================================================

LANG = {
    "vi": {
        "title": "Hệ thống Xử lý Hóa đơn XML", 
        "settings": "Cài đặt",
        "desc": "Chế độ: **Tự động toàn diện** (Tính lại thuế & Phân loại hóa đơn)",
        "upload_lbl": "Thả file XML vào đây để xử lý", 
        "upload_hlp": f"Tối đa {MAX_FILES_ALLOWED} file/lần",
        "col_file": "Tên file", "col_size": "Size", 
        "btn_convert": "🚀 Bắt đầu Xử lý & Xuất Excel",
        "success": "✅ Đã xử lý xong!", "error": "Có lỗi xảy ra.",
        "btn_dl": "⬇️ Tải file Excel kết quả",
        "clear": "Xóa danh sách", "empty": "Chưa có file nào"
    },
    "en": {
        "title": "XML Invoice Processor", "settings": "Settings",
        "desc": "Mode: **Full Auto** (Re-calc Tax & Classify)",
        "upload_lbl": "Drop XML files here", 
        "upload_hlp": f"Max {MAX_FILES_ALLOWED} files",
        "col_file": "Filename", "col_size": "Size", 
        "btn_convert": "🚀 Process to Excel",
        "success": "✅ Done!", "error": "Error.",
        "btn_dl": "⬇️ Download Excel",
        "clear": "Clear", "empty": "Empty list"
    }
}
T = LANG[st.session_state["lang_code"]]

# --- UI Header ---
c1, c2 = st.columns([8, 1])
with c1: st.title(T["title"])
with c2:
    with st.popover(f"⚙️ {T['settings']}"):
        is_vn = st.session_state["lang_code"] == "vi"
        if st.toggle("Tiếng Việt / English", value=is_vn):
            st.session_state["lang_code"] = "vi"
        else:
            st.session_state["lang_code"] = "en"
        if st.button("Reload UI", use_container_width=True):
            st.rerun()

st.info(T["desc"])

# --- Upload Area ---
uploaded_files = st.file_uploader(
    label=T["upload_lbl"], type=ALLOWED_EXTENSIONS, 
    accept_multiple_files=True, help=T["upload_hlp"], key="uploader"
)

# Logic Accumulate (Cộng dồn file upload)
if uploaded_files:
    store = st.session_state["uploads"]
    count_new = 0
    for f in uploaded_files:
        if len(store) >= MAX_FILES_ALLOWED: break
        if f.name not in store:
            if f.size <= MAX_FILE_SIZE_MB * 1024 * 1024:
                store[f.name] = {"data": f.read(), "size": f.size}
                count_new += 1
    
    if count_new > 0:
        st.toast(f"Đã thêm {count_new} file mới!", icon="📥")
        time.sleep(0.5)
        st.rerun()

# --- Main View ---
if st.session_state["uploads"]:
    c_list, c_act = st.columns([3, 1])
    
    # Hiển thị list file
    data_view = [{"STT": i+1, T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                 for i, (k,v) in enumerate(st.session_state["uploads"].items())]
    
    with c_list:
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=250)
    
    with c_act:
        st.write("### Tác vụ")
        if st.button(f"🗑️ {T['clear']}", use_container_width=True):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()

        st.write("") # Spacer
        if st.button(T["btn_convert"], type="primary", use_container_width=True):
            with st.status("Đang xử lý dữ liệu...", expanded=True) as status:
                try:
                    all_rows = []
                    files = st.session_state["uploads"]
                    total = len(files)
                    bar = st.progress(0)
                    
                    for idx, (fname, fcontent) in enumerate(files.items()):
                        # 1. Parse XML
                        inv_data = _parse_invoice_data(fcontent["data"], fname)
                        # 2. Extract Rows & Calc Tax
                        rows = _rows_from_invoice(inv_data)
                        if rows: all_rows.extend(rows)
                        
                        # Update progress
                        bar.progress((idx + 1) / total)
                        
                        # Free memory ngay lập tức
                        del inv_data, rows
                    
                    # 3. Export Excel
                    if all_rows:
                        excel_data = _df_to_xlsx_stream(all_rows)
                        st.session_state["result_bytes"] = excel_data.getvalue()
                        st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        
                        status.update(label=T["success"], state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="Không tìm thấy dữ liệu hợp lệ!", state="error")
                        
                except Exception as e:
                    st.error(f"{T['error']}: {str(e)}")
                    status.update(label="Thất bại", state="error")

# --- Download Section ---
if st.session_state.get("result_bytes"):
    st.divider()
    c_dl1, c_dl2, c_dl3 = st.columns([1, 2, 1])
    with c_dl2:
        st.download_button(
            label=f"👉 {T['btn_dl']} 👈",
            data=st.session_state["result_bytes"],
            file_name=f"KetQua_HoaDon_{int(time.time())}.xlsx",
            mime=st.session_state["result_mime"],
            type="primary",
            use_container_width=True
        )

# Footer
st.markdown('<div class="custom-footer">© 2025 Invoice Processor Tool | Optimized for Performance</div>', unsafe_allow_html=True)
