import streamlit as st
import requests
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta
import plotly.graph_objects as go

load_dotenv()

st.set_page_config(
    page_title="Pulso Económico Perú",
    page_icon="🇵🇪",
    layout="wide"
)

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; }
    </style>
""", unsafe_allow_html=True)

BCRP_BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"

MESES_ES = {
    "Ene": "Jan", "Feb": "Feb", "Mar": "Mar", "Abr": "Apr",
    "May": "May", "Jun": "Jun", "Jul": "Jul", "Ago": "Aug",
    "Sep": "Sep", "Oct": "Oct", "Nov": "Nov", "Dic": "Dec"
}

def convertir_fecha_bcrp(fecha_str):
    try:
        partes = fecha_str.split(".")
        if len(partes) == 3:
            dia = partes[0]
            mes = MESES_ES.get(partes[1], partes[1])
            anio = "20" + partes[2]
            return pd.to_datetime(f"{dia} {mes} {anio}", format="%d %b %Y")
        elif len(partes) == 2:
            mes = MESES_ES.get(partes[0], partes[0])
            anio = partes[1]
            return pd.to_datetime(f"01 {mes} {anio}", format="%d %b %Y")
    except Exception:
        return None

def fetch_serie(codigo, fecha_inicio, fecha_fin):
    url = f"{BCRP_BASE}/{codigo}/json/{fecha_inicio}/{fecha_fin}/esp"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        periodos = data.get("periods", [])
        registros = []
        for p in periodos:
            fecha_raw = p.get("name")
            valor = p.get("values", [None])[0]
            if valor is not None:
                try:
                    fecha = convertir_fecha_bcrp(fecha_raw)
                    if fecha is not None:
                        registros.append({
                            "fecha": fecha,
                            "valor": float(valor)
                        })
                except (ValueError, TypeError):
                    pass
        df = pd.DataFrame(registros)
        if not df.empty:
            df = df.sort_values("fecha").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()

def get_valor_hace_n_dias(df, n_dias):
    fecha_hoy = df.iloc[-1]["fecha"]
    fecha_objetivo = fecha_hoy - timedelta(days=n_dias)
    registros_anteriores = df[df["fecha"] <= fecha_objetivo]
    if not registros_anteriores.empty:
        return registros_anteriores.iloc[-1]
    return None

@st.cache_data(ttl=3600)
def cargar_datos():
    hoy = datetime.today()
    fecha_fin = hoy.strftime("%Y-%m-%d")
    fecha_inicio_45 = (hoy - timedelta(days=45)).strftime("%Y-%m-%d")

    datos_diarios = {}
    for nombre, codigo in {
        "tipo_cambio_venta":  "PD04638PD",
        "tipo_cambio_compra": "PD04637PD",
    }.items():
        datos_diarios[nombre] = fetch_serie(codigo, fecha_inicio_45, fecha_fin)

    datos_mensuales = {}
    for nombre, codigo in {
        "inflacion_12meses":  "PN01273PM",
        "tasa_interbancaria": "PN07819NM",
    }.items():
        datos_mensuales[nombre] = fetch_serie(codigo, "2025-01-01", fecha_fin)

    return datos_diarios, datos_mensuales

def construir_resumen(datos_diarios, datos_mensuales):
    resumen = []

    df_venta  = datos_diarios["tipo_cambio_venta"]
    ultimo    = df_venta.iloc[-1]
    penultimo = df_venta.iloc[-2]
    hace7     = get_valor_hace_n_dias(df_venta, 7)
    hace30    = get_valor_hace_n_dias(df_venta, 30)

    resumen.append({
        "indicador":    "Tipo de cambio venta",
        "valor_actual": round(ultimo["valor"], 4),
        "fecha":        ultimo["fecha"].strftime("%d/%m/%Y"),
        "var_1d":       round(ultimo["valor"] - penultimo["valor"], 4),
        "var_7d":       round(ultimo["valor"] - hace7["valor"], 4) if hace7 is not None else None,
        "var_30d":      round(ultimo["valor"] - hace30["valor"], 4) if hace30 is not None else None,
    })

    ultimo_inf   = datos_mensuales["inflacion_12meses"].iloc[-1]
    anterior_inf = datos_mensuales["inflacion_12meses"].iloc[-2]

    resumen.append({
        "indicador":    "Inflacion 12 meses",
        "valor_actual": round(ultimo_inf["valor"], 2),
        "fecha":        ultimo_inf["fecha"].strftime("%d/%m/%Y"),
        "var_1d":       None,
        "var_7d":       None,
        "var_30d":      round(ultimo_inf["valor"] - anterior_inf["valor"], 2),
    })

    ultimo_tasa   = datos_mensuales["tasa_interbancaria"].iloc[-1]
    anterior_tasa = datos_mensuales["tasa_interbancaria"].iloc[-2]

    resumen.append({
        "indicador":    "Tasa interbancaria",
        "valor_actual": round(ultimo_tasa["valor"], 2),
        "fecha":        ultimo_tasa["fecha"].strftime("%d/%m/%Y"),
        "var_1d":       None,
        "var_7d":       None,
        "var_30d":      round(ultimo_tasa["valor"] - anterior_tasa["valor"], 2),
    })

    return pd.DataFrame(resumen)

# ── Header ──
st.title("🇵🇪 Pulso Económico Perú")
st.caption(f"Datos del BCRP · Última actualización: {datetime.today().strftime('%d/%m/%Y %H:%M')}")
st.info("Los datos provienen del BCRP. Este análisis es informativo y no constituye asesoría financiera certificada.")

# ── Carga de datos ──
with st.spinner("Cargando datos del BCRP..."):
    datos_diarios, datos_mensuales = cargar_datos()
    df_resumen = construir_resumen(datos_diarios, datos_mensuales)

tc   = df_resumen[df_resumen["indicador"] == "Tipo de cambio venta"].iloc[0]
inf  = df_resumen[df_resumen["indicador"] == "Inflacion 12 meses"].iloc[0]
tasa = df_resumen[df_resumen["indicador"] == "Tasa interbancaria"].iloc[0]

# ── Layout 2 columnas ──
col_izq, col_der = st.columns([1, 1.4])

# ── Columna izquierda: métricas + gráfica ──
with col_izq:
    st.subheader("Indicadores del día")

    m1, m2, m3 = st.columns(3)
    m1.metric(
        label="Tipo de cambio venta",
        value=f"S/ {tc['valor_actual']}",
        delta=f"{tc['var_1d']:+.4f} vs ayer"
    )
    m2.metric(
        label="Inflación 12 meses",
        value=f"{inf['valor_actual']}%",
        delta=f"{inf['var_30d']:+.2f} vs mes anterior"
    )
    m3.metric(
        label="Tasa interbancaria",
        value=f"{tasa['valor_actual']}%",
        delta=f"{tasa['var_30d']:+.2f} vs mes anterior"
    )

    st.subheader("Tendencia del tipo de cambio")
    df_tc = datos_diarios["tipo_cambio_venta"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_tc["fecha"],
        y=df_tc["valor"],
        mode="lines+markers",
        name="Tipo de cambio venta",
        line=dict(color="#E63946", width=2),
        marker=dict(size=4)
    ))
    fig.update_layout(
        xaxis_title="Fecha",
        yaxis_title="S/ por USD",
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=220,
        yaxis=dict(tickformat=".4f")
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Columna derecha: perfil + briefing ──
with col_der:
    st.subheader("¿Cómo te afecta a ti?")
    st.write("Responde 3 preguntas para recibir un análisis personalizado.")

    q1, q2, q3 = st.columns(3)
    ahorros = q1.radio("¿Tus ahorros están en?", ["Soles", "Dólares", "Ambos"])
    credito = q2.radio("¿Tienes crédito activo?", ["Sí", "No"])
    negocio = q3.radio("¿Tienes negocio propio?", ["Sí", "No"])

    if st.button("Generar mi briefing personalizado", type="primary"):
        perfil = {
            "ahorros": ahorros.lower(),
            "credito": credito.lower(),
            "negocio": negocio.lower()
        }

        contexto = f"""
DATOS ECONÓMICOS DEL BCRP HOY:
- Tipo de cambio venta: S/ {tc['valor_actual']}
- Variación vs ayer: {tc['var_1d']:+.4f}
- Variación vs semana pasada: {tc['var_7d']:+.4f}
- Inflación 12 meses: {inf['valor_actual']}%
- Tasa interbancaria: {tasa['valor_actual']}%

PERFIL DEL USUARIO:
- Ahorros en: {perfil['ahorros']}
- Tiene crédito activo: {perfil['credito']}
- Tiene negocio propio: {perfil['negocio']}
"""

        system_prompt = """
Eres un asesor económico personal para ciudadanos peruanos.
Responde ÚNICAMENTE con una tabla markdown con exactamente estas columnas:
| Indicador | Situación | Impacto para ti | Acción recomendada |

Reglas de la tabla:
- Fila 1: Tipo de cambio
- Fila 2: Inflación
- Fila 3: Tasa de interés
- En "Situación" usa: 🟢 Favorable / 🟡 Neutral / 🔴 Desfavorable según el perfil del usuario
- En "Impacto para ti" sé específico según el perfil — menciona si tiene ahorros, crédito o negocio
- En "Acción recomendada" da una acción concreta y simple
- Después de la tabla agrega UNA sola línea de conclusión en lenguaje coloquial
- Termina con: "⚠️ Este análisis es informativo y no constituye asesoría financiera certificada."
"""

        client = OpenAI()

        with st.spinner("Generando tu briefing..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": contexto}
                ]
            )

        briefing = response.choices[0].message.content
        st.divider()
        st.subheader("Tu briefing de hoy")
        st.caption(f"Generado el {datetime.today().strftime('%d/%m/%Y %H:%M')}")
        st.markdown(briefing)
        st.caption("Fuente: Banco Central de Reserva del Perú (BCRP) · estadisticas.bcrp.gob.pe")