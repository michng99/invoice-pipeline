import io
import os
import time
import hashlib
import zipfile
import traceback
import re
from decimal import Decimal
from typing import List, Tuple, Dict, Any
from xml.etree import ElementTree as ET

import streamlit as st
import pandas as pd
import xlsxwriter

# ==============================================================================
# 1. CẤU HÌNH TRANG & CSS
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

# CSS Tối ưu giao diện & Ẩn các thành phần thừa
st.markdown("""
    <style>
        /* Ẩn Decoration của Streamlit Cloud */
        a[href*="streamlit.io/cloud"] { display: none !important; }
        div[class*="viewerBadge"] { display: none !important; }
        
        /* Ẩn Header/Footer mặc định */
        #MainMenu {visibility: hidden !important;}
        footer {visibility: hidden !important;}
        header {visibility: hidden !important;}
        [data-testid="stHeader"] {display: none !important;}
        [data-testid="stToolbar"] {display: none !important;}
        .stDeployButton {display: none !important;}
        
        /* Tối ưu khoảng cách cho Mobile & Tránh Footer đè nút */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 150px !important;
        }

        /* Footer tự chế */
        .custom-footer {
            width: 100%;
            text-align: center;
            color: #888;
            padding-top: 20px;
            margin-bottom: 20px;
            border-top: 1px solid #333;
            font-size: 12px;
            font-family: sans-serif;
        }

        /* Fix màu Input trong Dark Mode */
        input { color: inherit !important; }
        button { min-height: 48px !important; }
    </style>
""", unsafe_allow_html=True)

if "theme" not in st.session_state: st.session_state["theme"] = "light"
if st.session_state["theme"] == "dark":
    st.markdown("""
        <style>
        .stApp {background-color: #0E1117; color: #FAFAFA;}
        div[data-baseweb="select"] > div, div[data-baseweb="input"] {
            background-color: #262730 !important; color: white !important;
        }
        input {color: white !important;}
        </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. CORE LOGIC (NAMESPACE CLEANING & TAG HUNTING)
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
MAX_TOTAL_SIZE_MB = 50          

def _num(v):
    if not v: return 0.0
    s = str(v).replace(",", "").strip()
    try:
        return float(Decimal(s))
    except Exception:
        return 0.0

def _txt(x): return (x or "").strip()

def _find_text(node: ET.Element, path: str):
    if node is None: return ""
    n = node.find(path)
    return _txt(n.text) if n is not None and n.text is not None else ""

# Helper tìm tag linh hoạt (thử nhiều đường dẫn)
def _find_flexible(node: ET.Element, paths: List[str]) -> str:
    if node is None: return ""
    for p in paths:
        found = _find_text(node, p)
        if found: return found
    return ""

def _parse_invoice(xml_bytes: bytes, filename: str = "unknown") -> dict:
    try:
        # --- BƯỚC QUAN TRỌNG: TẨY RỬA NAMESPACE ---
        # Chuyển bytes sang string
        xml_str = xml_bytes.decode("utf-8", errors="ignore")
        
        # Xóa các khai báo xmlns="..." để tránh lỗi tìm tag
        # Regex này tìm xmlns="..." và thay bằng rỗng
        xml_str = re.sub(r' xmlns="[^"]+"', '', xml_str, count=1)
        xml_str = re.sub(r' xmlns:xsi="[^"]+"', '', xml_str, count=1)
        xml_str = re.sub(r' xsi:schemaLocation="[^"]+"', '', xml_str, count=1)

        root = ET.fromstring(xml_str)
    except Exception:
        # Nếu lỗi decode hoặc parse, trả về dict rỗng
        return {}

    def f(p): 
        n = root.find(p)
        return _txt(n.text) if n is not None and n.text is not None else ""

    try:
        # Cấu trúc chuẩn hóa đơn thuế (Circular 78)
        invoice = {
            "KHMSHDon": f(".//TTChung/KHMSHDon"), # Dùng .// để tìm sâu bất chấp level
            "KHHDon":   f(".//TTChung/KHHDon"),
            "SHDon":    f(".//TTChung/SHDon"),
            "NLap":     f(".//TTChung/NLap"),
            "DVTTe":    f(".//TTChung/DVTTe") or "VND",
            "TGia":     f(".//TTChung/TGia") or "1",
        }
        
        # Tìm thông tin người bán (Có thể nằm ở NDHDon/NBan hoặc trực tiếp)
        nban = root.find(".//NBan")
        invoice["NBan"] = {
            "Ten":  _find_text(nban, "Ten") if nban is not None else "",
            "MST":  _find_text(nban, "MST") if nban is not None else "",
            "DChi": _find_text(nban, "DChi") if nban is not None else "",
        }
        
        items = []
        # Tìm danh sách hàng hóa (DSHHDVu/HHDVu)
        # Dùng findall với .// để tìm HHDVu ở bất kỳ độ sâu nào
        all_items = root.findall(".//HHDVu")
        
        for it in all_items:
            # --- LIST TAG THUẾ SUẤT ĐẦY ĐỦ NHẤT ---
            tsuat = _find_flexible(it, [
                "TSuat", "ThueSuat", "TSuatGTGT", "ThueSuatGTGT", 
                "TaxRate", "TS"
            ])
            
            # Tìm VAT & Amount (Ưu tiên tìm trong TTKhac trước, rồi tìm ở ngoài)
            vat_amt = _find_flexible(it, ["./TTKhac/VATAmount", "VATAmount", "TienThue", "TienThueGTGT"])
            amt     = _find_flexible(it, ["./TTKhac/Amount", "Amount", "TongTien", "ThanhTien"])
            
            # Nếu tìm Amount thất bại, thử lấy ThTien + VAT
            if not amt:
                tht_val = _num(_find_text(it, "ThTien"))
                vat_val = _num(vat_amt)
                if tht_val > 0:
                    amt = str(tht_val + vat_val)

            items.append({
                "TChat":   _find_text(it, "TChat"),
                "MHHDVu":  _find_text(it, "MHHDVu"),
                "THHDVu":  _find_text(it, "THHDVu"),
                "DVTinh":  _find_text(it, "DVTinh"),
                "SLuong":  _find_text(it, "SLuong") or "0",
                "DGia":    _find_text(it, "DGia") or "0",
                "ThTien":  _find_text(it, "ThTien") or "0",
                "TSuat":   tsuat,
                "VATAmount": vat_amt or "0",
                "Amount":    amt or "0",
            })
            
        invoice["Items"] = items
        return invoice
    except Exception:
        return {}

def _rows_from_invoice(inv: dict) -> list[dict]:
    if not inv: return []
    try:
        ms  = inv.get("KHMSHDon") or ""
        kh  = inv.get("KHHDon") or ""
        so  = inv.get("SHDon") or ""
        ngay = inv.get("NLap") or ""
        cur = inv.get("DVTTe") or "VND"
        rate = inv.get("TGia") or 1
        seller = inv.get("NBan") or {}
        s_mst  = seller.get("MST") or ""
        s_name = seller.get("Ten") or ""
        s_addr = seller.get("DChi") or ""
        ghichu_base = "Hoá đơn mới"
        items = inv.get("Items") or []
        rows = []

        def create_row(it, override_vals=None):
            sl = _num(it.get("SLuong"))
            dg = _num(it.get("DGia"))
            tht = _num(it.get("ThTien"))
            vat = _num(it.get("VATAmount"))
            total = _num(it.get("Amount"))
            
            # Xử lý thuế suất text
            ts_raw = _txt(it.get("TSuat"))
            # Chuẩn hóa chuỗi thuế suất (bỏ %, đổi phẩy thành chấm)
            ts_str = ts_raw.replace("%","").replace(",",".")
            ts_val = 0.0 

            # Cố gắng parse số %
            if ts_str:
                try:
                    # Xử lý trường hợp "KCT", "KKKNT" -> 0
                    if not ts_str[0].isdigit():
                        ts_val = 0.0
                    else:
                        val = float(ts_str)
                        # Nếu ghi 8 -> 0.08, nếu ghi 0.08 -> 0.08
                        if val > 1: val = val / 100 
                        ts_val = val
                except:
                    ts_val = 0.0
            
            # LOGIC: Tự tính tiền thuế nếu thiếu (Chỉ khi có thuế suất > 0)
            if vat == 0 and tht != 0 and ts_val > 0:
                vat = tht * ts_val
                if cur.upper() == "VND": vat = round(vat)
            
            # LOGIC: Suy luận ngược % (Nếu thiếu % nhưng có tiền thuế)
            # Điều kiện: Thuế suất gốc rỗng VÀ có tiền > 0
            final_ts_display = ts_raw
            if not final_ts_display and vat > 0 and tht > 0:
                try:
                    calc_rate = (vat / tht) * 100
                    # Làm tròn vào các mức phổ biến
                    if abs(calc_rate - 8) < 0.5: final_ts_display = "8%"
                    elif abs(calc_rate - 10) < 0.5: final_ts_display = "10%"
                    elif abs(calc_rate - 5) < 0.5: final_ts_display = "5%"
                    else: final_ts_display = f"{round(calc_rate)}%"
                except:
                    pass 

            # Tính tổng cuối cùng
            if total == 0:
                total = tht + vat

            r = {k: "" for k in COLUMN_ORDER}
            r.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "Ghi chú": ghichu_base, "Đơn vị tiền": cur, "Tỷ giá": _num(rate) or 1,
                "Mã hàng": it.get("MHHDVu") or "",
                "Tên hàng": it.get("THHDVu") or "",
                "Đơn vị tính": it.get("DVTinh") or "",
                "Số lượng": sl,
                "Đơn giá":  dg,
                "Tiền hàng": tht,
                "Thuế suất": final_ts_display,
                "Tiền thuế": vat,
                "Cộng tiền": total,
                "Cờ (Tchat)": _num(it.get("TChat")) if (it.get("TChat") or "").isdigit() else "",
            })
            if override_vals: r.update(override_vals)
            return r

        for it in items:
            if (it.get("TChat") or "").strip() == "4":
                rows.append(create_row(it, {"Cờ (Tchat)": 4, "Mã hàng": "", "Đơn vị tính": ""}))
        for it in items:
            if (it.get("TChat") or "").strip() == "4": continue
            rows.append(create_row(it))
        return rows
    except Exception:
        return []

def _df_to_xlsx_stream(rows: list[dict], sheet_name="Data") -> io.BytesIO:
    df = pd.DataFrame(rows)
    df = df.reindex(columns=COLUMN_ORDER)
    for c in ["Số lượng","Đơn giá","Tiền hàng","Thuế suất","Tiền thuế","Cộng tiền","Tỷ giá","Cờ (Tchat)"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf

def process_conversion_internal(files_data: Dict[str, bytes], merge: bool) -> Tuple[bytes, str]:
    per_file_rows = []
    named_streams = []
    
    for name, data in files_data.items():
        try:
            inv = _parse_invoice(data, filename=name)
            rows = _rows_from_invoice(inv)
            if not rows: continue
            per_file_rows.append(rows)
            
            if not merge:
                xlsx = _df_to_xlsx_stream(rows)
                named_streams.append((f"{name.rsplit('.',1)[0]}.xlsx", xlsx.getvalue()))
        except Exception: continue 

    if not per_file_rows: return None, None

    try:
        if merge or len(named_streams) == 1:
            all_rows = []
            for r in per_file_rows: all_rows.extend(r)
            final_xlsx = _df_to_xlsx_stream(all_rows, sheet_name="Data")
            return final_xlsx.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
                for name, payload in named_streams: z.writestr(name, payload)
            zbuf.seek(0)
            return zbuf.getvalue(), "application/zip"
    except Exception: return None, None

# ==============================================================================
# 3. FRONTEND
# ==============================================================================

if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "sha_index" not in st.session_state: st.session_state["sha_index"] = {}
if "last_activity" not in st.session_state: st.session_state["last_activity"] = time.time()
if "busy" not in st.session_state: st.session_state["busy"] = False
if "do_convert" not in st.session_state: st.session_state["do_convert"] = False
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "theme" not in st.session_state: st.session_state["theme"] = "light"

TTL_SECONDS = 3 * 60 

def _touch(): st.session_state["last_activity"] = time.time()
def _fmt_left(uploaded_at: float) -> str:
    left = max(0, (uploaded_at + TTL_SECONDS) - time.time())
    m, s = int(left // 60), int(left % 60)
    return f"{m:02d}:{s:02d}"
def _clear_all():
    st.session_state["uploads"].clear()
    st.session_state["sha_index"].clear()
    st.session_state["result_bytes"] = None
    st.session_state["do_convert"] = False
    _touch()
def _cleanup_ttl():
    last = st.session_state.get("last_activity") or time.time()
    if time.time() - last > TTL_SECONDS: _clear_all()
def _sha256(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()
def _add_uploads(files, text_dict):
    added, rep_n, rep_c = [], [], []
    store = st.session_state["uploads"]
    sha_idx = st.session_state["sha_index"]
    current_count = len(store)
    new_count = len(files) if files else 0
    if current_count + new_count > MAX_FILES_ALLOWED:
        st.error(text_dict["error_too_many"].format(max=MAX_FILES_ALLOWED))
        return [], [], []
    current_total_size = sum(item["size"] for item in store.values())
    for f in files or []:
        try:
            f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
            name = (f.name or "unknown.xml").strip()
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                st.toast(text_dict["error_file_big"].format(name=name, size=MAX_FILE_SIZE_MB), icon="⚠️"); continue
            if current_total_size + size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
                st.toast(text_dict["error_total_big"].format(name=name, size=MAX_TOTAL_SIZE_MB), icon="🛑"); break 
            data = f.read(); sha = _sha256(data)
            if sha in sha_idx and sha_idx[sha] in store:
                old_name = sha_idx[sha]
                store[old_name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
                if old_name != name: store[name] = store.pop(old_name); sha_idx[sha] = name
                rep_c.append(name); current_total_size += size; continue
            if name in store:
                old_size = store[name]["size"]; current_total_size = current_total_size - old_size + size
                rep_n.append(name); store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
                sha_idx[sha] = name; continue
            store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            sha_idx[sha] = name; added.append(name); current_total_size += size
        except Exception: continue
    _touch(); return added, rep_n, rep_c

LANG = {
    "en": {
        "page_title": "Invoice Pipeline",
        "settings": "Settings",
        "theme_label": "Theme",
        "dark": "Dark", "light": "Light",
        "lang_label": "Language",
        "mode_info": "Mode: **All-in-One** (Secure & Private)",
        "check_sys": "System Check",
        "sys_ok": "✅ System Operational",
        "upload_label": "Drop XML files here",
        "added": "Added",
        "replaced_name": "Replaced (Name)",
        "replaced_content": "Replaced (Content)",
        "clear_all": "Clear All",
        "col_name": "File Name",
        "col_size": "Size",
        "col_ttl": "Time Left",
        "merge_label": "Merge into single Excel file",
        "convert_btn": "🚀 Convert Now",
        "success_msg": "✅ Processing Complete!",
        "error_msg": "Processing Error: ",
        "download_btn": "⬇️ Download Result",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "error_too_many": "⚠️ Overload: Max {max} files allowed.",
        "error_file_big": "❌ Skipped '{name}': Too large (> {size}MB)",
        "error_total_big": "❌ Stop '{name}': Total size exceeds {size}MB",
        "empty_list": "No files uploaded yet."
    },
    "vi": {
        "page_title": "Xử lý Hóa đơn",
        "settings": "Cài đặt",
        "theme_label": "Giao diện",
        "dark": "Tối", "light": "Sáng",
        "lang_label": "Ngôn ngữ",
        "mode_info": "Chế độ: **All-in-One** (Bảo mật & Riêng tư)",
        "check_sys": "Kiểm tra hệ thống",
        "sys_ok": "✅ Hệ thống hoạt động tốt",
        "upload_label": "Thả file XML vào đây",
        "added": "Đã thêm",
        "replaced_name": "Ghi đè (Trùng tên)",
        "replaced_content": "Ghi đè (Trùng nội dung)",
        "clear_all": "Xoá tất cả",
        "col_name": "Tên file",
        "col_size": "Kích thước",
        "col_ttl": "Còn lại",
        "merge_label": "Gộp thành 1 file Excel duy nhất",
        "convert_btn": "🚀 Chuyển đổi Ngay",
        "success_msg": "✅ Xử lý thành công!",
        "error_msg": "Lỗi xử lý. Vui lòng thử lại hoặc liên hệ admin.",
        "download_btn": "⬇️ Tải về kết quả",
        "copyright": "© 2025 Chuong Minh | All Rights Reserved",
        "error_too_many": "⚠️ Quá tải: Chỉ chấp nhận tối đa {max} file.",
        "error_file_big": "❌ Bỏ qua '{name}': Quá lớn (> {size}MB)",
        "error_total_big": "❌ Dừng thêm '{name}': Tổng dung lượng vượt quá {size}MB",
        "empty_list": "Chưa có file nào."
    }
}

_cleanup_ttl()
T = LANG[st.session_state["lang_code"]]

col_head, col_set = st.columns([6, 1], gap="small")
with col_head: st.title(f"{T['page_title']}")
with col_set:
    with st.popover(f"⚙️ {T['settings']}", use_container_width=True):
        is_vn = st.session_state["lang_code"] == "vi"
        toggle_lang = st.toggle("Tiếng Việt / English", value=is_vn)
        new_lang = "vi" if toggle_lang else "en"
        st.write(f"**{T['theme_label']}**")
        theme_opt = st.radio("Theme", [T["light"], T["dark"]], index=0 if st.session_state["theme"]=="light" else 1, label_visibility="collapsed", horizontal=True)
        new_theme = "light" if theme_opt == T["light"] else "dark"
        if new_lang != st.session_state["lang_code"] or new_theme != st.session_state["theme"]:
            st.session_state["lang_code"] = new_lang; st.session_state["theme"] = new_theme; st.rerun()

with st.container(border=True):
    col1, col2 = st.columns([3, 1])
    with col1: st.info(f"ℹ️ {T['mode_info']}")
    with col2:
        if st.button(f"🔗 {T['check_sys']}", use_container_width=True): st.success(T['sys_ok'])

st.divider()
uploaded_files = st.file_uploader(T['upload_label'], type=["xml"], accept_multiple_files=True)
if uploaded_files:
    added, rep_n, rep_c = _add_uploads(uploaded_files, T); msg = []
    if added: msg.append(f"✅ {T['added']} {len(added)}")
    if rep_n: msg.append(f"♻️ {T['replaced_name']} {len(rep_n)}")
    if rep_c: msg.append(f"♻️ {T['replaced_content']} {len(rep_c)}")
    if msg: st.toast(" | ".join(msg))

if st.session_state["uploads"]:
    colA, colB = st.columns([3,1])
    with colA:
        rows = [{T['col_name']: k, T['col_size']: v["size"], T['col_ttl']: _fmt_left(v["uploaded_at"])} for k, v in st.session_state["uploads"].items()]
        st.dataframe(rows, hide_index=True, use_container_width=True)
    with colB:
        if st.button(f"🧽 {T['clear_all']}", type="secondary", use_container_width=True): _clear_all(); st.rerun()
else: st.caption(f"_{T['empty_list']}_")

num_files = len(st.session_state["uploads"])
merge_to_one = st.checkbox(T['merge_label'], value=True, disabled=num_files <= 1)
convert_btn = st.button(T['convert_btn'], type="primary", disabled=num_files == 0 or st.session_state["busy"])

if convert_btn and not st.session_state["busy"]:
    st.session_state["do_convert"] = True; st.session_state["busy"] = True; st.rerun()

if st.session_state["do_convert"] and st.session_state["busy"]:
    try:
        files_map = {k: v["data"] for k, v in st.session_state["uploads"].items()}
        res_bytes, res_mime = process_conversion_internal(files_map, merge_to_one)
        if res_bytes:
            st.session_state["result_bytes"] = res_bytes
            st.session_state["result_mime"] = res_mime
            st.session_state["uploads"].clear()
            st.session_state["sha_index"].clear()
            st.success(T['success_msg'])
        else: st.warning("Không có dữ liệu hợp lệ.")
    except Exception as e:
        print("❌ [CRITICAL SYSTEM ERROR]:"); print(traceback.format_exc()); st.error(f"{T['error_msg']}") 
    finally:
        st.session_state["do_convert"] = False; st.session_state["busy"] = False; _touch(); st.rerun()

if st.session_state["result_bytes"]:
    ext = "xlsx" if "spreadsheet" in str(st.session_state["result_mime"]) else "zip"
    fname = "Data.xlsx" if ext == "xlsx" else "excels.zip"
    st.download_button(f"{T['download_btn']} ({ext.upper()})", data=st.session_state["result_bytes"], file_name=fname, mime=st.session_state["result_mime"], use_container_width=True, type="primary")

st.markdown(f'<div class="custom-footer">{T["copyright"]}</div>', unsafe_allow_html=True)
