# app_coordinacion.py
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import os
import time
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import json

st.set_page_config(page_title="Semáforo Coordinación", layout="wide")

# ===== LOGIN DE COORDINADORES Y DIRECCIÓN =====
credenciales = {
    "ELCHE 2.0": "elche2025",
    "ELCHE 3.0": "elche3025",
    "ELCHE 4.0": "elche4025",
    "VIGO 1.0": "vigo1025",
    "VIGO 2.0": "vigo2025",
    "VIGO 3.0": "vigo3025",
    "LEON 1.0": "leon1025",
    "DIRECCION": "direccion2025"
}

if "usuario" not in st.session_state:
    st.session_state.usuario = ""

if not st.session_state.usuario:
    st.subheader("🔐 Iniciar sesión")
    user = st.text_input("Usuario (nombre del call o DIRECCION)")
    pwd = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if user in credenciales and credenciales[user] == pwd:
            st.session_state.usuario = user
            st.rerun()
        else:
            st.error("❌ Usuario o contraseña incorrectos")
    st.stop()

# Guardar nombre de call activo
usuario_actual = st.session_state.usuario
solo_direccion = usuario_actual == "DIRECCION"

colores_semaforo = {
    "AZUL - FINALIZADO": ("#0070C0", "#ffffff"),
    "VERDE": ("#00FF00", "#000000"),
    "AMARILLO": ("#FFFF00", "#000000"),
    "ROJO": ("#FF0000", "#ffffff")
}

# Estilos visuales
st.markdown("""
<style>
    .tabla-container {
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 10px;
        background-color: #f9f9f9;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .bloque-cliente-wrap {
        margin-bottom: 12px;
    }
    .bloque-cliente-inner {
        border: 1px solid rgba(0, 0, 0, 0.125);
        border-radius: 8px;
        padding: 10px;
        background-color: rgba(249, 249, 249, 1);
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    div[data-testid="column"] {
        margin-bottom: 2px !important;
    }
</style>
""", unsafe_allow_html=True)

st.title(f"🚦 Semáforo de Clientes — {usuario_actual}")
if st.button("🔄 Cambiar de usuario / call"):
    st.session_state.usuario = ""
    st.session_state.filtros = {}  # opcional, por si estaba definido
    st.rerun()
	

# Filtros (visibles para todos, pero sin permitir cambiar el CALL en coordinadores)
if "filtros" not in st.session_state:
    st.session_state.filtros = {"CALL": usuario_actual, "COMERCIAL": "", "CLIENTE": "", "SEMAFORO": ""}

# BLOQUE DE FILTROS
with st.expander("🔍 Filtros de búsqueda", expanded=False):

    # FORM 1: aplicar filtros
    with st.form("form_filtros_aplicar"):
        c1, c2, c3, c4 = st.columns(4)
        call = c1.text_input("CALL", value=st.session_state.filtros.get("CALL", usuario_actual))
        comercial = c2.text_input("COMERCIAL", value=st.session_state.filtros.get("COMERCIAL", ""))
        cliente = c3.text_input("CLIENTE", value=st.session_state.filtros.get("CLIENTE", ""))
        semaforo = c4.selectbox("SEMAFORO", options=[""] + list(colores_semaforo.keys()), index=0)
        aplicar_filtros = st.form_submit_button("✅ Aplicar filtros")
        if aplicar_filtros:
            st.session_state.filtros = {
                "CALL": call,
                "COMERCIAL": comercial,
                "CLIENTE": cliente,
                "SEMAFORO": semaforo
            }
            st.rerun()

    # FORM 2: borrar filtros
    with st.form("form_filtros_borrar"):
        mostrar_todos = st.form_submit_button("🧹 Mostrar todos")
        if mostrar_todos:
            st.session_state.filtros.clear()
            st.rerun()

# Aplicar filtros
f = st.session_state.filtros
productos = ["F2025", "F2026", "HL", "VIGILANCIA", "IMPLANT", "DENUNCIAS"]
festivos = {datetime(2025, 5, 17).date(), datetime(2025, 5, 19).date()}
colores_semaforo = {
    "AZUL - FINALIZADO": ("#0070C0", "#ffffff"),
    "VERDE": ("#00FF00", "#000000"),
    "AMARILLO": ("#FFFF00", "#000000"),
    "ROJO": ("#FF0000", "#ffffff")
}
# Cargar archivo si existe
archivo_guardado = "semaforo_guardado.xlsx"
df_cargado = pd.read_excel(archivo_guardado) if os.path.exists(archivo_guardado) else pd.DataFrame(columns=["CALL", "COMERCIAL", "CLIENTE", "DIA"] + productos + ["SEMAFORO"])
df_cargado["DIA"] = pd.to_datetime(df_cargado["DIA"]).dt.date

df_filtrado = df_cargado.copy()
if f.get("CALL", ""):
    df_filtrado = df_filtrado[df_filtrado["CALL"].str.contains(f["CALL"], case=False, na=False)]
if f.get("COMERCIAL", ""):
    df_filtrado = df_filtrado[df_filtrado["COMERCIAL"].str.contains(f["COMERCIAL"], case=False, na=False)]
if f.get("CLIENTE", ""):
    df_filtrado = df_filtrado[df_filtrado["CLIENTE"].str.contains(f["CLIENTE"], case=False, na=False)]
if f.get("SEMAFORO", ""):
    df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == f["SEMAFORO"]]


def calcular_dia_habil(fecha, festivos):
    while fecha.weekday() >= 5 or fecha in festivos:
        fecha += timedelta(days=1)
    return fecha

def insertar_cliente(call, comercial, cliente):
    fecha = calcular_dia_habil(datetime.now().date(), festivos)
    filas = []
    for _ in range(3):
        filas.append({
            "CALL": call,
            "COMERCIAL": comercial,
            "CLIENTE": cliente,
            "DIA": fecha,
            **{p: "❌" for p in productos},
            "SEMAFORO": ""
        })
        fecha = calcular_dia_habil(fecha + timedelta(days=1), festivos)
    return pd.DataFrame(filas)

def actualizar_semaforo(df):
    df = df.copy()
    hoy = datetime.now().date()
    for cliente in df["CLIENTE"].unique():
        bloque = df[df["CLIENTE"] == cliente]
        checks = bloque[productos].applymap(lambda x: x == "✔").sum(axis=1)
        cruces = bloque[productos].applymap(lambda x: x == "❌").sum(axis=1)
        if any(checks == len(productos)):
            for idx in bloque.index:
                if df.at[idx, "DIA"] <= hoy:
                    df.at[idx, "SEMAFORO"] = "AZUL - FINALIZADO"
                else:
                    df.at[idx, "SEMAFORO"] = ""
        else:
            idx = bloque.index.tolist()
            if df.at[idx[0], "DIA"] <= hoy and checks.iloc[0] >= 1:
                df.at[idx[0], "SEMAFORO"] = "VERDE"
            if df.at[idx[1], "DIA"] <= hoy and cruces.iloc[1] >= 1:
                df.at[idx[1], "SEMAFORO"] = "AMARILLO"
            if df.at[idx[2], "DIA"] <= hoy and cruces.iloc[2] >= 1:
                df.at[idx[2], "SEMAFORO"] = "ROJO"
    df["SEMAFORO"] = df["SEMAFORO"].fillna("")
    return df

def limpiar_clientes_expirados(df, festivos):
    hoy = datetime.now().date()
    df_filtrado = df.copy()
    clientes_eliminar = []

    for cliente in df_filtrado["CLIENTE"].unique():
        bloque = df_filtrado[df_filtrado["CLIENTE"] == cliente].sort_values("DIA")
        if len(bloque) < 3:
            continue

        primer_dia = bloque.iloc[0]["DIA"]
        fecha_limite = primer_dia
        for _ in range(3):
            fecha_limite = calcular_dia_habil(fecha_limite + timedelta(days=1), festivos)

        if hoy >= fecha_limite:
            clientes_eliminar.append(cliente)

    df = df[~df["CLIENTE"].isin(clientes_eliminar)].copy()
    return df



# Cargar archivo si existe
archivo_guardado = "semaforo_guardado.xlsx"
df_cargado = pd.read_excel(archivo_guardado) if os.path.exists(archivo_guardado) else pd.DataFrame(columns=["CALL", "COMERCIAL", "CLIENTE", "DIA"] + productos + ["SEMAFORO"])
df_cargado["DIA"] = pd.to_datetime(df_cargado["DIA"]).dt.date

df_cargado = actualizar_semaforo(df_cargado)
df_cargado = limpiar_clientes_expirados(df_cargado, festivos)

df_filtrado = df_cargado.copy()
if f.get("CALL", ""):
    df_filtrado = df_filtrado[df_filtrado["CALL"].str.contains(f["CALL"], case=False, na=False)]
if f.get("COMERCIAL", ""):
    df_filtrado = df_filtrado[df_filtrado["COMERCIAL"].str.contains(f["COMERCIAL"], case=False, na=False)]
if f.get("CLIENTE", ""):
    df_filtrado = df_filtrado[df_filtrado["CLIENTE"].str.contains(f["CLIENTE"], case=False, na=False)]
if f.get("SEMAFORO", ""):
    df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == f["SEMAFORO"]]

# Mostrar número de clientes
st.markdown(f"**👥 Clientes mostrados:** {df_filtrado['CLIENTE'].nunique()} / {df_cargado['CLIENTE'].nunique()}")

# Formulario insertar nuevo cliente
with st.form("formulario_cliente", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)

    if solo_direccion:
        call = c1.text_input("CALL")
    else:
        c1.markdown(f"**CALL:** {usuario_actual}")
        call = usuario_actual

    comercial = c2.text_input("COMERCIAL")
    cliente = c3.text_input("CLIENTE")

    insertar = st.form_submit_button("➕ Insertar Cliente")
    if insertar and call and comercial and cliente:
        df_nuevo = insertar_cliente(call, comercial, cliente)
        df_cargado = pd.concat([df_cargado, df_nuevo], ignore_index=True)
        df_cargado.to_excel(archivo_guardado, index=False)
        st.success(f"✅ Cliente **{cliente}** insertado correctamente. 🎉")
        time.sleep(3)
        st.rerun()

# Mostrar tabla
df_filtrado = actualizar_semaforo(df_filtrado)
hoy = datetime.now().date()

clientes_advertidos = set()
def toggle(valor):
    return "✔" if valor == "❌" else "❌"

for cliente in df_filtrado["CLIENTE"].unique():
    bloque = df_filtrado[df_filtrado["CLIENTE"] == cliente]
    st.markdown("<div class='bloque-cliente-wrap'><div class='bloque-cliente-inner'>", unsafe_allow_html=True)
    advertir = False
    for i, fila in bloque.iterrows():
        cols = st.columns([1.2, 1.2, 1.5, 1.1] + [0.7]*len(productos) + [1.5])
        cols[0].markdown(fila["CALL"])
        cols[1].markdown(fila["COMERCIAL"])
        cols[2].markdown(fila["CLIENTE"])
        cols[3].markdown(fila["DIA"].strftime("%d/%m"))
        for j, p in enumerate(productos):
            if fila["DIA"] == hoy:
                if cols[4+j].button(fila[p], key=f"{i}_{p}"):
                    df_cargado.at[i, p] = toggle(fila[p])
                    df_cargado = actualizar_semaforo(df_cargado)
                    df_cargado.to_excel(archivo_guardado, index=False)
                    st.rerun()
            else:
                if cols[4+j].button(fila[p], key=f"{i}_{p}"):
                    advertir = True
        semaforo_val = fila["SEMAFORO"]
        if semaforo_val in colores_semaforo:
            bg, fg = colores_semaforo[semaforo_val]
            cols[-1].markdown(f"<div style='background-color:{bg}; color:{fg}; padding:5px; text-align:center; border-radius:4px;'><b>{semaforo_val}</b></div>", unsafe_allow_html=True)
    if advertir and cliente not in clientes_advertidos:
        st.warning(f"⚠️ Solo puedes editar los datos del día actual para **{cliente}**.")
        clientes_advertidos.add(cliente)
    st.markdown("</div></div>", unsafe_allow_html=True)

# Exportar PDF
if st.button("📄 Exportar clientes a PDF"):
    carpeta_pdf = os.path.join(os.getcwd(), "INFORMES PDF")
    os.makedirs(carpeta_pdf, exist_ok=True)
    nombre_archivo = f"informe_clientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta_completa = os.path.join(carpeta_pdf, nombre_archivo)
    exportar_pdf(df_filtrado, ruta_completa, st.session_state.filtros.get("CALL"), st.session_state.filtros.get("COMERCIAL"))
    st.success(f"✅ PDF generado en 'INFORMES PDF' como {nombre_archivo}")
    with open(ruta_completa, "rb") as pdf:
        st.download_button("⬇️ Descargar PDF generado", pdf, file_name=nombre_archivo, mime="application/pdf")
