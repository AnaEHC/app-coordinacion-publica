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

st.set_page_config(page_title="Semáforo Coordinación", layout="wide")

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

st.title("🚦 Semáforo de Clientes (Coordinación)")

# Configuración global
hoy = datetime.now().date()
festivos = {datetime(2025, 5, 17).date(), datetime(2025, 5, 19).date()}
productos = ["F2025", "F2026", "HL", "VIGILANCIA", "IMPLANT", "DENUNCIAS"]
archivo_guardado = "semaforo_guardado.xlsx"
colores_semaforo = {
    "AZUL - FINALIZADO": ("#0070C0", "#ffffff"),
    "VERDE": ("#00FF00", "#000000"),
    "AMARILLO": ("#FFFF00", "#000000"),
    "ROJO": ("#FF0000", "#ffffff")
}

# Funciones auxiliares
def calcular_dia_habil(fecha, festivos):
    while fecha.weekday() >= 5 or fecha in festivos:
        fecha += timedelta(days=1)
    return fecha

def insertar_cliente(call, comercial, cliente):
    fecha = calcular_dia_habil(hoy, festivos)
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
    for cliente in df["CLIENTE"].unique():
        bloque = df[df["CLIENTE"] == cliente]
        checks = bloque[productos].applymap(lambda x: x == "✔").sum(axis=1)
        cruces = bloque[productos].applymap(lambda x: x == "❌").sum(axis=1)
        if any(checks == 6):
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

def toggle(valor):
    return "✔" if valor == "❌" else "❌"

def exportar_pdf(df, ruta_pdf, filtro_call="", filtro_comercial=""):
    c = canvas.Canvas(ruta_pdf, pagesize=A4)
    width, height = A4
    x_offset = 1.5 * cm
    y_offset = height - 2 * cm
    row_height = 0.8 * cm
    fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
    titulo = "Informe de Clientes - Semáforo"
    if filtro_call:
        titulo += f" | CALL: {filtro_call}"
    if filtro_comercial:
        titulo += f" | COMERCIAL: {filtro_comercial}"
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_offset, y_offset, titulo)
    c.setFont("Helvetica", 10)
    c.drawString(x_offset, y_offset - 0.7 * cm, f"Generado el {fecha_actual}")
    y_offset -= 2 * cm

    colores_orden = ["AZUL - FINALIZADO", "VERDE", "AMARILLO", "ROJO"]

    columnas = ["CALL", "COMERCIAL", "CLIENTE", "DIA"]
    ancho_col = 4.5 * cm

    for color in colores_orden:
        grupo = df[df['SEMAFORO'] == color]
        if not grupo.empty:
            if y_offset < 3 * cm:
                c.showPage()
                y_offset = height - 2 * cm

            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.HexColor(colores_semaforo[color][0]))
            c.drawString(x_offset, y_offset, color)
            y_offset -= row_height

            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(colors.black)
            for i, col in enumerate(columnas):
                c.drawString(x_offset + i * ancho_col, y_offset, col)

            y_offset -= row_height
            c.setFont("Helvetica", 9)

            for _, row in grupo.iterrows():
                if y_offset < 2 * cm:
                    c.showPage()
                    y_offset = height - 2 * cm

                for i, col in enumerate(columnas):
                    texto = str(row[col]) if col != "DIA" else row[col].strftime("%d/%m/%Y")
                    c.drawString(x_offset + i * ancho_col, y_offset, texto)
                y_offset -= row_height

            y_offset -= 0.5 * cm

    resumen = df["SEMAFORO"].value_counts()
    y_offset -= cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_offset, y_offset, "Resumen de clientes por estado:")
    y_offset -= row_height
    c.setFont("Helvetica", 9)

    for estado in colores_orden:
        cantidad = resumen.get(estado, 0)
        if cantidad:
            c.drawString(x_offset, y_offset, f"{estado}: {cantidad} clientes")
            y_offset -= row_height

    c.save()

def subir_a_drive(nombre_archivo_local, nombre_final_en_drive, folder_id):
    try:
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': nombre_final_en_drive,
            'parents': [folder_id]
        }
        media = MediaFileUpload(
            nombre_archivo_local,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        archivo = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        st.success(f"✅ Archivo subido a Drive: {nombre_final_en_drive}")
        return archivo.get('id')

    except Exception as e:
        st.error(f"❌ Error al subir a Drive: {e}")

def limpiar_clientes_expirados(df, festivos):
    hoy = datetime.now().date()
    df_filtrado = df.copy()
    clientes_eliminar = []
    filas_exportar_closers = []
    filas_exportar_finalizadas = []

    for cliente in df_filtrado["CLIENTE"].unique():
        bloque = df_filtrado[df_filtrado["CLIENTE"] == cliente].sort_values("DIA")
        if len(bloque) < 3:
            continue

        primer_dia = bloque.iloc[0]["DIA"]
        fecha_limite = primer_dia
        for _ in range(3):
            fecha_limite = calcular_dia_habil(fecha_limite + timedelta(days=1), festivos)

        if hoy >= fecha_limite:
            ultima_fila = bloque.iloc[2]
            estado = ultima_fila["SEMAFORO"]
            if estado == "ROJO":
                filas_exportar_closers.append(ultima_fila)
                clientes_eliminar.append(cliente)
            elif estado == "AZUL - FINALIZADO":
                filas_exportar_finalizadas.append(ultima_fila)
                clientes_eliminar.append(cliente)

    # Exportar archivos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if filas_exportar_closers:
        df_closers = pd.DataFrame(filas_exportar_closers)
        archivo_local = "temp_rojo.xlsx"
        df_closers.to_excel(archivo_local, index=False)
        subir_a_drive(archivo_local, f"CLIENTES_ROJOS_{timestamp}.xlsx", "1MMvklfuHM1uWXn2aQslstCpT-W1fHc3L")

    if filas_exportar_finalizadas:
        df_finalizados = pd.DataFrame(filas_exportar_finalizadas)
        archivo_local = "temp_azul.xlsx"
        df_finalizados.to_excel(archivo_local, index=False)
        subir_a_drive(archivo_local, f"VENTAS_FINALIZADAS_{timestamp}.xlsx", "1O2IFO5NeOcCxnvFSJ6GBh1QwijPOkmHE")






    # Eliminar clientes del DataFrame original
    df = df[~df["CLIENTE"].isin(clientes_eliminar)].copy()
    return df



# Cargar archivo si existe
df_cargado = pd.read_excel(archivo_guardado) if os.path.exists(archivo_guardado) else pd.DataFrame(columns=["CALL", "COMERCIAL", "CLIENTE", "DIA"] + productos + ["SEMAFORO"])
df_cargado["DIA"] = pd.to_datetime(df_cargado["DIA"]).dt.date

# Actualizar colores
df_cargado = actualizar_semaforo(df_cargado)
df_cargado = limpiar_clientes_expirados(df_cargado, festivos)


# Filtros
if "filtros" not in st.session_state:
    st.session_state.filtros = {"CALL": "", "COMERCIAL": "", "CLIENTE": "", "SEMAFORO": ""}

with st.expander("🔍 Filtros de búsqueda", expanded=False):
    with st.form("form_filtros"):
        c1, c2, c3, c4 = st.columns(4)
        call = c1.text_input("CALL", value=st.session_state.filtros["CALL"], key="f1")
        comercial = c2.text_input("COMERCIAL", value=st.session_state.filtros["COMERCIAL"], key="f2")
        cliente = c3.text_input("CLIENTE", value=st.session_state.filtros["CLIENTE"], key="f3")
        semaforo = c4.selectbox("SEMAFORO", options=[""] + list(colores_semaforo.keys()), index=0, key="f4")
        aplicar, borrar = st.columns([5, 1])
        if aplicar.form_submit_button("Aplicar filtros"):
            st.session_state.filtros = {"CALL": call, "COMERCIAL": comercial, "CLIENTE": cliente, "SEMAFORO": semaforo}
            st.rerun()
        if borrar.form_submit_button("🧹 Mostrar todos"):
            st.session_state.filtros = {"CALL": "", "COMERCIAL": "", "CLIENTE": "", "SEMAFORO": ""}
            st.rerun()

# Aplicar filtros
df_filtrado = df_cargado.copy()
f = st.session_state.filtros
if f["CALL"]:
    df_filtrado = df_filtrado[df_filtrado["CALL"].str.contains(f["CALL"], case=False, na=False)]
if f["COMERCIAL"]:
    df_filtrado = df_filtrado[df_filtrado["COMERCIAL"].str.contains(f["COMERCIAL"], case=False, na=False)]
if f["CLIENTE"]:
    df_filtrado = df_filtrado[df_filtrado["CLIENTE"].str.contains(f["CLIENTE"], case=False, na=False)]
if f["SEMAFORO"]:
    df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == f["SEMAFORO"]]

# Mostrar número de clientes
st.markdown(f"**👥 Clientes mostrados:** {df_filtrado['CLIENTE'].nunique()} / {df_cargado['CLIENTE'].nunique()}")

# Formulario insertar
with st.form("formulario_cliente", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    call = c1.text_input("CALL")
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
clientes_advertidos = set()
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
