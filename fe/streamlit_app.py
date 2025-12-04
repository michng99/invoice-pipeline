import io
import time
import hashlib
import zipfile
import traceback
from decimal import Decimal
from typing import List, Tuple, Dict, Any
from xml.etree import ElementTree as ET

import streamlit as st
import pandas as pd
import xlsxwriter
import xmltodict # Yêu cầu đã cài trong requirements.txt

# ==============================================================================
# PHẦN 1: LOGIC CONVERTER (PORT TỪ app/converters/xml_to_xlsx.py)
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
    try:
        return float(Decimal(str(v)))
    except Exception:
        return None

def _txt(x):
    return (x or "").strip()

def _find_text(node: ET.Element, path: str):
    if node is None: return ""
    n = node.find(path)
    return _txt(n.text) if n is not None and n.text is not None else ""

def _parse_invoice(xml_bytes: bytes) -> dict:
    # Dùng ElementTree như code gốc
    root = ET.fromstring(xml_bytes)

    def f(p): 
        n = root.find(p)
        return _txt(n.text) if n is not None and n.text is not None else ""

    # Thông tin chung
    invoice = {
        "KHMSHDon": f("./DLHDon/TTChung/KHMSHDon"),
        "KHHDon":   f("./DLHDon/TTChung/KHHDon"),
        "SHDon":    f("./DLHDon/TTChung/SHDon"),
        "NLap":     f("./DLHDon/TTChung/NLap"),
        "DVTTe":    f("./DLHDon/TTChung/DVTTe") or "VND",
        "TGia":     f("./DLHDon/TTChung/TGia") or "1",
    }

    # Người bán
    nban = root.find("./DLHDon/NDHDon/NBan")
    invoice["NBan"] = {
        "Ten":  _find_text(nban, "Ten") if nban is not None else "",
        "MST":  _find_text(nban, "MST") if nban is not None else "",
        "DChi": _find_text(nban, "DChi") if nban is not None else "",
    }

    # Hàng hoá
    items_parent = root.find("./DLHDon/NDHDon/DSHHDVu")
    items = []
    if items_parent is not None:
        for it in items_parent.findall("./HHDVu"):
            items.append({
                "TChat":   _find_text(it, "TChat"),
                "MHHDVu":  _find_text(it, "MHHDVu"),
                "THHDVu":  _find_text(it, "THHDVu"),
                "DVTinh":  _find_text(it, "DVTinh"),
                "SLuong":  _find_text(it, "SLuong") or "0",
                "DGia":    _find_text(it, "DGia") or "0",
                "ThTien":  _find_text(it, "ThTien") or "0",
                "TSuat":   _find_text(it, "TSuat"),
                "VATAmount": _find_text(it, "./TTKhac/VATAmount") or "0",
                "Amount":    _find_text(it, "./TTKhac/Amount") or "0",
            })
    invoice["Items"] = items
    return invoice

def _rows_from_invoice(inv: dict) -> list[dict]:
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
    ghichu = "Hoá đơn mới"

    items = inv.get("Items") or []
    rows = []

    # a) Các dòng mô tả TChat=4
    for it in items:
        if (it.get("TChat") or "").strip() == "4":
            row = {k: "" for k in COLUMN_ORDER}
            row.update({
                "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
                "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
                "C người bán": "",
                "Mã hàng": "", "Tên hàng": it.get("THHDVu") or "", "Đơn vị tính": "",
                "Số lượng": _num(it.get("SLuong") or 0) or 0,
                "Đơn giá":  _num(it.get("DGia") or 0) or 0,
                "Tiền hàng": _num(it.get("ThTien") or 0) or 0,
                "Thuế suất": (it.get("TSuat") or "").replace("%","").replace(",",".") if it.get("TSuat") else "",
                "Tiền thuế": _num(it.get("VATAmount") or 0) or 0,
                "Cộng tiền": _num(it.get("Amount") or 0) or 0,
                "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": _num(rate) or 1,
                "Cờ (Tchat)": 4,
            })
            rows.append(row)

    # b) Hàng hóa còn lại
    for it in items:
        if (it.get("TChat") or "").strip() == "4":
            continue
        row = {k: "" for k in COLUMN_ORDER}
        row.update({
            "Mẫu số": ms, "KH hóa đơn": kh, "Số hóa đơn": so, "Ngày hóa đơn": ngay,
            "ST người bán": s_mst, "Tên người bán": s_name, "ĐC người bán": s_addr,
            "C người bán": "",
            "Mã hàng": it.get("MHHDVu") or "",
            "Tên hàng": it.get("THHDVu") or "",
            "Đơn vị tính": it.get("DVTinh") or "",
            "Số lượng": _num(it.get("SLuong") or 0) or 0,
            "Đơn giá":  _num(it.get("DGia") or 0) or 0,
            "Tiền hàng": _num(it.get("ThTien") or 0) or 0,
            "Thuế suất": (it.get("TSuat") or "").replace("%","").replace(",",".") if it.get("TSuat") else "",
            "Tiền thuế": _num(it.get("VATAmount") or 0) or 0,
            "Cộng tiền": _num(it.get("Amount") or 0) or 0,
            "Ghi chú": ghichu, "Đơn vị tiền": cur, "Tỷ giá": _num(rate) or 1,
            "Cờ (Tchat)": _num(it.get("TChat")) if (it.get("TChat") or "").isdigit() else "",
        })
        rows.append(row)

    return rows

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
# PHẦN 2: FRONTEND STREAMLIT (ĐÃ SỬA LỖI MẤT NÚT DOWNLOAD)
# ==============================================================================

if "uploads" not in st.session_state: st.session_state.update({"uploads":{}, "busy":False, "lang_code":"vi", "theme":"light"})

def _add_uploads(files, T):
    store = st.session_state["uploads"]
    sha_idx = st.session_state["sha_index"]

    for f in files or []:
        name = (f.name or "unknown.xml").strip()
        data = f.read()
        size = len(data)
        sha = _sha256(data)

        if sha in sha_idx and sha_idx[sha] in store:
            old_name = sha_idx[sha]
            store[old_name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            if old_name != name:
                store[name] = store.pop(old_name)
                sha_idx[sha] = name
            rep_c.append(name)
            continue

        if name in store:
            rep_n.append(name)
            store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            sha_idx[sha] = name
            continue

        store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
        sha_idx[sha] = name
        added.append(name)

    _touch()
    return added, rep_n, rep_c

# ========= UI =========
_init_state()
_cleanup_ttl()

st.title("📄 Invoice Pipeline | All-in-One")

with st.container(border=True):
    c1, c2 = st.columns([3,1])
    c1.info(T["mode_info"])
    if c2.button(f"🔗 {T['check_sys']}", use_container_width=True): c2.success(T["sys_ok"])

st.divider()

# --- Upload Zone ---
uploaded_files = st.file_uploader("Thả file XML vào đây", type=["xml"], accept_multiple_files=True)
if uploaded_files:
    added, rep_n, rep_c = _add_uploads(uploaded_files)
    msg = []
    if added: msg.append(f"✅ Thêm {len(added)}")
    if rep_n: msg.append(f"♻️ Ghi đè tên {len(rep_n)}")
    if rep_c: msg.append(f"♻️ Ghi đè nội dung {len(rep_c)}")
    if msg: st.toast(" | ".join(msg))

# --- File Table ---
if st.session_state["uploads"]:
    colA, colB = st.columns([3,1])
    with colA:
        rows = [{"Tên file": k, "Size": v["size"], "TTL": _fmt_left(v["uploaded_at"])} 
                for k, v in st.session_state["uploads"].items()]
        st.dataframe(rows, hide_index=True, use_container_width=True)
    with colB:
        if st.button("🧽 Xoá hết", use_container_width=True):
            _clear_all()
            st.rerun()

# --- Convert Action ---
num_files = len(st.session_state["uploads"])
merge_to_one = st.checkbox("Gộp thành 1 file Excel", value=True, disabled=num_files <= 1)
convert_btn = st.button("🚀 Convert Ngay", type="primary", disabled=num_files == 0 or st.session_state["busy"])

if convert_btn and not st.session_state["busy"]:
    st.session_state["do_convert"] = True
    st.session_state["busy"] = True
    st.rerun()

if st.session_state["do_convert"] and st.session_state["busy"]:
    try:
        # Lấy dữ liệu từ session state
        files_map = {k: v["data"] for k, v in st.session_state["uploads"].items()}
        
        # Gọi hàm xử lý nội bộ (logic mới)
        res_bytes, res_mime = process_conversion_internal(files_map, merge_to_one)
        
        st.session_state["result_bytes"] = res_bytes
        st.session_state["result_mime"] = res_mime
        
        # Dọn dẹp
        st.session_state["uploads"].clear()
        st.session_state["sha_index"].clear()
        st.success("✅ Xử lý thành công!")
    except Exception as e:
        st.error(f"Lỗi xử lý: {e}")
    finally:
        st.session_state["do_convert"] = False
        st.session_state["busy"] = False
        _touch()
        st.rerun()

# --- Download ---
if st.session_state["result_bytes"]:
    ext = "xlsx" if "spreadsheet" in str(st.session_state["result_mime"]) else "zip"
    fname = "Data.xlsx" if ext == "xlsx" else "excels.zip"
    
    st.download_button(
        f"⬇️ Tải về kết quả ({ext.upper()})",
        data=st.session_state["result_bytes"],
        file_name=fname,
        mime=st.session_state["result_mime"],
        use_container_width=True,
        type="primary"
    )

st.markdown('<div style="text-align:center;color:#888;margin-top:50px;">© 2025 Michng99 | All-in-One Version</div>', unsafe_allow_html=True)
