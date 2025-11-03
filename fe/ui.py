import os, io, requests
import streamlit as st

st.set_page_config(page_title="Invoice Pipeline – Upload & Convert", layout="wide")
st.title("🧾 Invoice Pipeline – Upload & Convert")

# ---- URL backend (có thể dán) ----
default_url = st.session_state.get("backend_url", os.getenv("BACKEND_URL",""))
with st.expander("Kết nối Backend", expanded=True):
    backend_url = st.text_input(
        "Backend URL",
        value=default_url,
        placeholder="https://invoice-pipeline-xxxxxx.asia-southeast1.run.app",
        help="Dán URL Cloud Run của backend vào đây"
    )
    col1, col2 = st.columns([1,3])
    with col1:
        if st.button("Lưu URL"):
            st.session_state["backend_url"] = backend_url.strip()
            st.success("Đã lưu URL backend.")
    with col2:
        if st.button("Kiểm tra /health"):
            url = (backend_url or "").strip()
            if not url:
                st.error("Chưa có URL backend.")
            else:
                try:
                    r = requests.get(url.rstrip("/") + "/health", timeout=10)
                    st.write("Response status:", r.status_code)
                    st.code(r.text)
                    if r.ok:
                        st.success("Kết nối OK.")
                    else:
                        st.error("Backend trả về lỗi.")
                except Exception as e:
                    st.error(f"Không kết nối được: {e}")

# ---- Upload & Convert ----
st.markdown("---")
st.subheader("Chọn nhiều XML (d1...d5,...)")
uploaded = st.file_uploader(
    "Drag & drop hoặc Browse XML",
    type=["xml"],
    accept_multiple_files=True
)
merge_one = st.checkbox("Gộp nhiều file thành 1 Excel", value=True)

if st.button("🚀 Convert", type="primary", disabled=not uploaded):
    url = st.session_state.get("backend_url", "").strip()
    if not url:
        st.error("Chưa có URL backend. Hãy dán và Lưu URL trước.")
        st.stop()

    files = []
    for f in uploaded:
        files.append(("xml_files", (f.name, f.read(), "application/xml")))

    endpoint = "/pipeline/xml-to-xlsx" if merge_one else "/pipeline/xml-to-xlsx-multi"
    try:
        r = requests.post(url.rstrip("/") + endpoint, files=files, timeout=60)
        if r.ok and r.headers.get("content-type","").startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            st.success("Convert OK, tải file bên dưới:")
            st.download_button(
                "⬇️ Tải Excel",
                data=r.content,
                file_name="Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error(f"Lỗi convert (status={r.status_code}).")
            st.code(r.text)
    except Exception as e:
        st.error(f"Gọi API lỗi: {e}")
