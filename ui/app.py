"""
Agente Legal MVP — Interfaz Streamlit
3 secciones: Dashboard | Chat Legal | Cargar Contratos
"""

import streamlit as st
import requests
import os
import pandas as pd
import extra_streamlit_components as stx

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Agente Legal MVP",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sesión y autenticación ─────────────────────────────────────────────────

#@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

def api(method: str, path: str, **kwargs):
    headers = {}
    if "token" in st.session_state:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        r = getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)
        return r
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None


def login_screen():
    st.title("⚖️ Agente Legal MVP")
    st.subheader("Iniciar sesión")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Entrar")
    if submit:
        r = requests.post(
            f"{API_URL}/auth/login",
            data={"username": email, "password": password}
        )
        if r.status_code == 200:
            token = r.json()["access_token"]
            st.session_state.token = token
            st.session_state.email = email
            # Persistir en cookie (expira en 8 horas)
            cookie_manager.set("auth_token", token, max_age=28800)
            cookie_manager.set("auth_email", email, max_age=28800)
            st.rerun()
        else:
            st.error("Credenciales incorrectas")


# Restaurar sesión desde cookie si no está en session_state
if "token" not in st.session_state:
    cookie_token = cookie_manager.get("auth_token")
    cookie_email = cookie_manager.get("auth_email")
    if cookie_token:
        st.session_state.token = cookie_token
        st.session_state.email = cookie_email or ""

if "token" not in st.session_state:
    login_screen()
    st.stop()

# ─── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚖️ Legal MVP")
    st.caption(f"👤 {st.session_state.get('email', '')}")
    page = st.radio("Navegación", [
        "📊 Dashboard",
        "💬 Chat Legal",
        "📁 Cargar Contratos",
        "🔔 Alertas",
    ])
    if st.button("Cerrar sesión"):
        cookie_manager.delete("auth_token")
        cookie_manager.delete("auth_email")
        del st.session_state["token"]
        st.session_state.pop("email", None)
        st.rerun()

# ─── Dashboard ──────────────────────────────────────────────────────────────

if page == "📊 Dashboard":
    st.title("📊 Panel de Contratos")

    r = api("get", "/reports/summary")
    if r and r.status_code == 200:
        data = r.json()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total contratos", data["total"])
        col2.metric("Activos", data["active"])
        col3.metric("Vencen en 30d", data["expiring_30_days"], delta_color="inverse")
        col4.metric("Alto riesgo", data["high_risk"], delta_color="inverse")

        col5, col6 = st.columns(2)
        with col5:
            st.metric("Vencen en 90d", data["expiring_90_days"])
            st.metric("Sin fecha vencimiento", data["no_expiration_date"])
            st.metric("Expirados", data["expired"])

        with col6:
            if data["by_type"]:
                import plotly.express as px
                df = pd.DataFrame(
                    list(data["by_type"].items()),
                    columns=["Tipo", "Cantidad"]
                )
                fig = px.pie(df, names="Tipo", values="Cantidad", title="Por tipo de contrato")
                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Top contrapartes")
        if data["by_counterparty"]:
            df_cp = pd.DataFrame(
                list(data["by_counterparty"].items()),
                columns=["Contraparte", "Contratos"]
            )
            st.dataframe(df_cp, use_container_width=True)

        # Lista de contratos
        st.subheader("Contratos")
        r2 = api("get", "/ingest/list")
        if r2 and r2.status_code == 200:
            contracts = r2.json()
            if contracts:
                df_c = pd.DataFrame(contracts)
                cols = ["id", "filename", "contract_type", "counterparty",
                        "expiration_date", "risk_level", "status"]
                cols_exist = [c for c in cols if c in df_c.columns]
                st.dataframe(df_c[cols_exist], use_container_width=True)

        # Exportar Excel
        if st.button("📥 Exportar Excel"):
            r3 = api("get", "/reports/excel")
            if r3:
                st.download_button(
                    "Descargar .xlsx",
                    r3.content,
                    file_name="contratos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# ─── Chat Legal ─────────────────────────────────────────────────────────────

elif page == "💬 Chat Legal":
    st.title("💬 Consulta Legal")
    st.caption("Haz preguntas sobre tus contratos. El sistema busca en los documentos reales.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    with st.expander("🔍 Filtros (opcional)"):
        col1, col2 = st.columns(2)
        filter_type = col1.text_input("Tipo de contrato")
        filter_counterparty = col2.text_input("Contraparte")

    question = st.chat_input("¿Qué quieres saber sobre tus contratos?")

    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Analizando contratos..."):
                payload = {
                    "question": question,
                    "contract_type": filter_type or None,
                    "counterparty": filter_counterparty or None,
                }
                r = api("post", "/query/ask", json=payload)
                if r and r.status_code == 200:
                    data = r.json()
                    answer = data["answer"]
                    sources = data.get("sources", [])
                    if sources:
                        answer += f"\n\n---\n📄 *Documentos consultados: IDs {sources}*"
                else:
                    answer = "Error al consultar. Verifica que el sistema esté activo."

            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

# ─── Cargar Contratos ────────────────────────────────────────────────────────

elif page == "📁 Cargar Contratos":
    st.title("📁 Cargar Contratos")
    st.caption("Sube PDF o DOCX. El sistema extrae texto, metadatos y analiza cláusulas automáticamente.")

    uploaded_files = st.file_uploader(
        "Selecciona contratos",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files and st.button("⚡ Procesar contratos"):
        for uploaded_file in uploaded_files:
            with st.status(f"Procesando {uploaded_file.name}...") as status:
                r = api(
                    "post", "/ingest/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                )
                if r and r.status_code == 200:
                    data = r.json()
                    status.update(label=f"✅ {uploaded_file.name}", state="complete")
                    st.json({
                        "Contrato ID": data["contract_id"],
                        "status": data["status"],
                        "filename": data["filename"],
                        "message": data["message"],
                    })
                else:
                    status.update(label=f"❌ Error en {uploaded_file.name}", state="error")
                    if r:
                        st.error(r.json().get("detail", "Error desconocido"))

# ─── Alertas ─────────────────────────────────────────────────────────────────

elif page == "🔔 Alertas":
    st.title("🔔 Alertas de Vencimiento y Riesgo")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Revisar ahora"):
            r = api("post", "/alerts/run")
            if r and r.status_code == 200:
                data = r.json()
                st.success(f"{data['alerts_generated']} alertas generadas")

    r = api("get", "/alerts/")
    if r and r.status_code == 200:
        alerts = r.json()
        if alerts:
            for alert in alerts:
                icon = "🔴" if "30" in alert["alert_type"] else "🟡" if "60" in alert["alert_type"] else "🔵"
                st.info(f"{icon} {alert['message']}")
        else:
            st.success("✅ Sin alertas pendientes")
