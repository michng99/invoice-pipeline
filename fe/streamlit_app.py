from __future__ import annotations

import io
import os
import time
import hashlib
from pathlib import Path
from typing import Dict, Tuple, List

import requests
import streamlit as st

# ========= Cấu hình =========
TTL_SECONDS = 5 * 60  # TTL 5 phút
SECRETS_FILE = Path("fe/.streamlit/secrets.toml")  # lưu local trong image/volume

st.set_page_config(page_title="Invoice Pipeline – Upload & Convert", layout="wide")


# ========= Secrets & Backend URL =========
def _read_backend_from_secrets() -> str:
    try:
        try:
            import tomllib  # py>=3.11
        except Exception:  # pragma: no cover
            import tomli as tomllib  # type: ignore
        if SECRETS_FILE.exists():
            data = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            return (data.get("backend_url") or "").strip()
    except Exception:
        pass
    return ""


def _write_backend_to_secrets(url: str) -> None:
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(f'backend_url = "{url.strip()}"\n', encoding="utf-8")


def _get_backend_url() -> str:
    sec = st.session_state.get("backend_url", "")
    if not sec:
        sec = _read_backend_from_secrets()
        st.session_state["backend_url"] = sec
    return sec


def _set_backend_url(url: str) -> None:
    url = (url or "").strip()
    st.session_state["backend_url"] = url
    if url:
        _write_backend_to_secrets(url)


def _health(url: str) -> Tuple[int | None, str]:
    try:
        r = requests.get(url.rstrip("/") + "/health", timeout=6)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)


# ========= State & TTL =========
def _init_state() -> None:
    # Kho dữ liệu upload: name -> {data, size, uploaded_at, sha}
    if "uploads" not in st.session_state or not isinstance(st.session_state["uploads"], dict):
        st.session_state["uploads"] = {}

    # Chỉ mục nội dung: sha256 -> latest name (để detect nội dung trùng)
    if "sha_index" not in st.session_state or not isinstance(st.session_state["sha_index"], dict):
        st.session_state["sha_index"] = {}

    if "last_activity" not in st.session_state:
        st.session_state["last_activity"] = time.time()

    if "busy" not in st.session_state:
        st.session_state["busy"] = False

    if "do_convert" not in st.session_state:
        st.session_state["do_convert"] = False

    if "result_bytes" not in st.session_state:
        st.session_state["result_bytes"] = None

    if "just_converted" not in st.session_state:
        st.session_state["just_converted"] = False

    if "backend_url" not in st.session_state:
        st.session_state["backend_url"] = _read_backend_from_secrets()


# KHỐI MỚI ĐÃ SỬA LỖI
def _touch() -> None:
    st.session_state["last_activity"] = time.time()


def _fmt_left(uploaded_at: float) -> str:
    # 3 dòng này đã được thụt vào đúng
    left = max(0, (uploaded_at + TTL_SECONDS) - time.time())
    m, s = int(left // 60), int(left % 60)
    return f"{m:02d}:{s:02d}"


def _clear_all() -> None:
    st.session_state["uploads"].clear()
    st.session_state["sha_index"].clear()
    st.session_state["result_bytes"] = None
    st.session_state["do_convert"] = False
    st.session_state["just_converted"] = False
    _touch()


def _cleanup_ttl() -> None:
    # hết TTL -> reset phiên
    last = st.session_state.get("last_activity") or time.time()
    if time.time() - last > TTL_SECONDS:
        _clear_all()
        st.info("Phiên đã hết hạn 5 phút không tương tác. Đã xoá tất cả file.", icon="🧹")


# ========= Upload & chống trùng =========
def _sha256(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _add_uploads(files) -> Tuple[List[str], List[str], List[str]]:
    """
    Trả: (added_names, replaced_by_name, replaced_by_content)
    - replaced_by_name: ghi đè do tên trùng
    - replaced_by_content: ghi đè do nội dung trùng SHA (khác tên)
    """
    added: List[str] = []
    rep_name: List[str] = []
    rep_content: List[str] = []

    store: Dict[str, dict] = st.session_state["uploads"]
    sha_idx: Dict[str, str] = st.session_state["sha_index"]

    for f in files or []:
        name = (f.name or "unknown.xml").strip()
        data = f.read()
        size = len(data)
        sha = _sha256(data)

        # Nếu trùng nội dung (SHA) đã tồn tại -> ghi đè bản cũ bằng tên mới (giữ 1 bản cuối)
        if sha in sha_idx and sha_idx[sha] in store:
            old_name = sha_idx[sha]
            store[old_name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            if old_name != name:
                # đổi key về tên mới (ghi đè tên)
                store[name] = store.pop(old_name)
                sha_idx[sha] = name
            rep_content.append(name)
            continue

        # Nếu trùng tên -> ghi đè
        if name in store:
            rep_name.append(name)
            store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            sha_idx[sha] = name
            continue

        # File mới
        store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
        sha_idx[sha] = name
        added.append(name)

    _touch()
    return added, rep_name, rep_content


# ========= Call backend =========
def _post_convert(url: str, merge_to_one: bool):
+    files = []
+    for name, meta in st.session_state["uploads"].items():
+        # ĐỔI TÊN FIELD thành 'xml_files' để khớp FastAPI
+        files.append(("xml_files", (name, io.BytesIO(meta["data"]), "application/xml")))
     data = {"merge_to_one": str(merge_to_one).lower()}
     r = requests.post(url.rstrip("/") + "/pipeline/xml-to-xlsx", files=files, data=data, timeout=120)
     return r



# ========= UI =========
_init_state()
_cleanup_ttl()
st.title("📄 Invoice Pipeline | Upload & Convert")

# ---- Backend URL ----
with st.container(border=True):
    st.subheader("Kết nối Backend")
    url_input = st.text_input("Backend URL", value=_get_backend_url(), placeholder="https://<service>-<hash>-<region>.a.run.app")
    col1, col2 = st.columns([1,1], gap="small")
    with col1:
        if st.button("💾 Lưu URL", use_container_width=True):
            if url_input and url_input.startswith("http"):
                _set_backend_url(url_input)
                st.success("Đã lưu URL backend.")
            else:
                st.error("URL không hợp lệ.")
    with col2:
        if st.button("🔗 Kiểm tra /health", use_container_width=True):
            url = _get_backend_url()
            if not url:
                st.warning("Chưa cấu hình Backend URL.")
            else:
                code, text = _health(url)
                st.write(f"Response: {code} — {text[:500]}")

    using = _get_backend_url()
    if using:
        st.info(f"Đang dùng: {using}")

st.divider()

# ---- Upload zone ----
st.subheader("Chọn nhiều XML (d1…d5, …)")
uploaded_files = st.file_uploader(
    "Drag and drop files here",
    type=["xml"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    added, rep_n, rep_c = _add_uploads(uploaded_files)
    msg = []
    if added:
        msg.append("✅ Thêm: " + ", ".join(added))
    if rep_n:
        msg.append("♻️ Ghi đè (trùng tên): " + ", ".join(rep_n))
    if rep_c:
        msg.append("♻️ Ghi đè (trùng nội dung): " + ", ".join(rep_c))
    if msg:
        st.success(" | ".join(msg))

# ---- Bảng file & TTL ----
if st.session_state["uploads"]:
    colA, colB = st.columns([3,1])
    with colA:
        st.caption("Các file đang giữ tạm (tự xoá sau 5 phút không tương tác):")
        rows = []
        for name, meta in st.session_state["uploads"].items():
            rows.append({
                "Tên file": name,
                "Kích thước": meta["size"],
                "Còn lại (TTL)": _fmt_left(meta["uploaded_at"]),
            })
        st.dataframe(rows, hide_index=True, use_container_width=True)
    with colB:
        if st.button("🧽 Xoá tất cả file (ngay)", type="secondary", use_container_width=True):
            _clear_all()
            st.success("Đã xoá tất cả.")
else:
    st.info("Chưa có file nào.")

st.divider()

# ---- Convert form ----
merge_to_one = st.checkbox("Gộp nhiều file thành 1 Excel", value=True)
convert_btn = st.button("🚀 Convert", type="primary", disabled=not st.session_state["uploads"] or st.session_state["busy"])

# chống double-click: đặt cờ rồi rerun ở đầu chu trình render
if convert_btn and not st.session_state["busy"]:
    if not _get_backend_url():
        st.warning("Chưa cấu hình Backend URL.")
    else:
        st.session_state["do_convert"] = True
        st.session_state["busy"] = True
        st.rerun()

# thực thi convert 1 lần khi cờ bật
if st.session_state["do_convert"] and st.session_state["busy"]:
    try:
        r = _post_convert(_get_backend_url(), merge_to_one)
        if r.status_code == 200:
            st.session_state["result_bytes"] = r.content
            st.session_state["just_converted"] = True
            # xoá kho file ngay sau khi convert xong
            st.session_state["uploads"].clear()
            st.session_state["sha_index"].clear()
            st.success("✅ Convert thành công. Đã xoá file trên hệ thống.")
        else:
            st.error(f"Lỗi từ backend ({r.status_code}): {r.text[:500]}")
    except Exception as e:
        st.error(f"Không gọi được backend: {e}")
    finally:
        st.session_state["do_convert"] = False
        st.session_state["busy"] = False
        _touch()

# hiển thị download nếu có kết quả
if st.session_state["result_bytes"]:
    st.download_button(
        "⬇️ Download",
        data=st.session_state["result_bytes"],
        file_name="Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ---- Footer ----
st.markdown(
    """
    <div style="text-align:center;color:#888;margin-top:32px;">
      © 2025 Chuong Minh. All rights reserved. ·
      <a href="https://m.me/michng99" target="_blank">Messenger</a>
    </div>
    """,
    unsafe_allow_html=True,
)
