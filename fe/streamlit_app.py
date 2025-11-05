from __future__ import annotations
import os, re, typing as t
from pathlib import Path
import requests
import streamlit as st

try:
    import tomllib  # py3.11+
except Exception:
    tomllib = None

APP_DIR = Path(__file__).resolve().parent
SECRETS_DIR = APP_DIR / ".streamlit"
SECRETS_FILE = SECRETS_DIR / "secrets.toml"
BACKEND_ENV = os.getenv("BACKEND_URL", "").strip()

def _read_secrets_file() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    if tomllib is None:
        txt = SECRETS_FILE.read_text(encoding="utf-8")
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith("backend_url"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return {"backend_url": val}
        return {}
    with open(SECRETS_FILE, "rb") as f:
        return tomllib.load(f)

def load_backend_url() -> str:
    # Thứ tự ưu tiên: session -> st.secrets -> file -> env
    if "backend_url" in st.session_state and st.session_state["backend_url"]:
        return st.session_state["backend_url"]
    url = st.secrets.get("backend_url", "")
    if url:
        st.session_state["backend_url"] = url
        return url
    data = _read_secrets_file()
    url = data.get("backend_url", "")
    if url:
        st.session_state["backend_url"] = url
        return url
    if BACKEND_ENV:
        st.session_state["backend_url"] = BACKEND_ENV
        return BACKEND_ENV
    return ""

def save_backend_url(url: str):
    url = (url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        st.error("Vui lòng nhập URL hợp lệ.")
        return

    # Tạo thư mục và lưu lại vào secrets.toml để nhớ giữa các lần mở app
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(f'backend_url = "{url}"\n', encoding="utf-8")

    # Cập nhật session_state để dùng ngay trong lần render hiện tại
    st.session_state["backend_url"] = url

    # Thông báo xong là thôi, KHÔNG rerun để tránh vòng lặp
    st.success("Đã lưu URL backend. (Không cần tải lại trang)")
    st.info("Nếu giao diện chưa phản ánh URL mới, bấm **Kiểm tra /health** hoặc Refresh trình duyệt là được.")

def check_health(base_url: str) -> tuple[int | None, str]:
    if not base_url:
        return None, "Chưa có Backend URL."
    url = base_url.rstrip("/") + "/health"
    try:
        r = requests.get(url, timeout=15)
        return r.status_code, r.text
    except Exception as e:
        return None, f"ERROR: {e}"

def call_convert(base_url: str, files: list[st.runtime.uploaded_file_manager.UploadedFile], merge_to_one: bool) -> requests.Response:
    if not base_url:
        raise RuntimeError("Chưa cấu hình Backend URL.")
    endpoint = base_url.rstrip("/") + "/pipeline/xml-to-xlsx"
    form_files: list[tuple[str, tuple[str, bytes, str]]] = []
    for f in files:
        content = f.getvalue()
        form_files.append(("xml_files", (f.name, content, "application/xml")))
    data = {"merge_to_one": "true" if merge_to_one else "false"}
    return requests.post(endpoint, files=form_files, data=data, timeout=300)

def parse_filename_from_headers(resp: requests.Response, fallback: str) -> str:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename="([^"]+)"', cd)
    return m.group(1) if m else fallback

# ---------------------- UI ----------------------
st.set_page_config(page_title="Invoice Pipeline", layout="wide")
st.title("🧾 Invoice Pipeline – Upload & Convert")

with st.expander("🔌 Kết nối Backend", expanded=True):
    current_url = load_backend_url()
    url_input = st.text_input("Backend URL", value=current_url, placeholder="https://<service>-<hash>-<region>.a.run.app")
    colA, colB, colC = st.columns([1, 1, 4], gap="small")
    if colA.button("💾 Lưu URL", use_container_width=True):
        if not url_input.strip():
            st.error("Vui lòng nhập URL hợp lệ.")
        else:
            save_backend_url(url_input)
    if colB.button("🩺 Kiểm tra /health", use_container_width=True):
        backend_url_to_check = load_backend_url()
        status, text = check_health(backend_url_to_check)
        if status is None:
            st.error(text)
        elif status == 200:
            st.success(f"200 OK — {text}")
        else:
            st.warning(f"{status} — {text}")
    if current_url:
        colC.info(f"Đang dùng: **{current_url}**")
    else:
        colC.warning("Chưa có Backend URL. Hãy nhập và bấm **Lưu URL**.")

st.divider()
st.subheader("Chọn nhiều XML (d1…d5, …)")
uploaded = st.file_uploader("Drag & drop hoặc Browse XML", type=["xml"], accept_multiple_files=True, label_visibility="collapsed")
merge_one = st.checkbox("Gộp nhiều file thành 1 Excel", value=True)

col1, _ = st.columns([1, 5])
if col1.button("🚀 Convert", type="primary"):
    if not uploaded:
        st.error("Vui lòng chọn ít nhất 1 tệp XML.")
        st.stop()
    backend_url = load_backend_url().strip()
    if not backend_url:
        st.error("Chưa cấu hình Backend URL.")
        st.stop()
    with st.spinner("Đang xử lý…"):
        try:
            resp = call_convert(backend_url, uploaded, merge_one)
        except Exception as e:
            st.error(f"Không gọi được backend: {e}")
            st.stop()
    if resp.status_code != 200:
        try:
            msg = resp.json()
        except Exception:
            msg = resp.text
        st.error(f"Lỗi từ backend ({resp.status_code}): {msg}")
        st.stop()
    default_name = "Data.xlsx" if (merge_one or len(uploaded) == 1) else "excels.zip"
    filename = parse_filename_from_headers(resp, fallback=default_name)
    mime = resp.headers.get("content-type", "application/octet-stream")
    st.success("Hoàn tất. Bấm nút để tải xuống.")
    st.download_button("⬇️ Download", data=resp.content, file_name=filename, mime=mime, use_container_width=True)

st.caption("Tip: URL backend được lưu ở `fe/.streamlit/secrets.toml`. Có thể set nhanh bằng `BACKEND_URL`.")

# === FOOTER_2025_COPYRIGHT ===
def _render_footer():
    import streamlit as st
    FOOTER_HTML = """
    <div style="margin-top:48px; padding-top:8px; text-align:center; font-size:13px; opacity:0.75">
        &copy; 2025 <strong>Chuong Minh. All rights reserved.</strong> &middot;
        <a href="https://m.me/michng99" target="_blank" rel="noopener noreferrer">
            Messenger
        </a>
    </div>
    """
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)

# Tự động vẽ footer ở cuối trang dù app có return sớm
try:
    _render_footer()
except Exception:
    pass
