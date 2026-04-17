import requests
import pandas as pd
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

load_dotenv()

BCRP_BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"

SERIES = {
    "tipo_cambio_venta": "PD04638PD",
    "tipo_cambio_compra": "PD04637PD",
    "tasa_interbancaria": "PD04649PD",
}

def get_fecha_rango(dias=30):
    hoy = datetime.today()
    inicio = hoy - timedelta(days=dias)
    return inicio.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d")

def fetch_serie(codigo, fecha_inicio, fecha_fin):
    url = f"{BCRP_BASE}/{codigo}/json/{fecha_inicio}/{fecha_fin}/esp"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        periodos = data.get("periods", [])
        registros = []
        for p in periodos:
            fecha = p.get("name")
            valor = p.get("values", [None])[0]
            if valor is not None:
                try:
                    registros.append({
                        "fecha": fecha,
                        "valor": float(valor)
                    })
                except (ValueError, TypeError):
                    pass
        df = pd.DataFrame(registros)
        if not df.empty:
            df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True)
            df = df.sort_values("fecha").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error al obtener serie {codigo}: {e}")
        return pd.DataFrame()

def fetch_todas_las_series():
    fecha_inicio, fecha_fin = get_fecha_rango(dias=30)
    print(f"Descargando datos del {fecha_inicio} al {fecha_fin}...\n")
    resultados = {}
    for nombre, codigo in SERIES.items():
        df = fetch_serie(codigo, fecha_inicio, fecha_fin)
        resultados[nombre] = df
        if not df.empty:
            ultimo = df.iloc[-1]
            anterior = df.iloc[-2] if len(df) > 1 else None
            variacion = ""
            if anterior is not None:
                diff = ultimo["valor"] - anterior["valor"]
                pct = (diff / anterior["valor"]) * 100
                signo = "+" if diff >= 0 else ""
                variacion = f"  |  variación: {signo}{diff:.4f} ({signo}{pct:.2f}%)"
            print(f"{nombre}: S/ {ultimo['valor']:.4f} "
                  f"al {ultimo['fecha'].strftime('%d/%m/%Y')}{variacion}")
        else:
            print(f"{nombre}: sin datos disponibles")
    return resultados

def calcular_variaciones(df):
    if df.empty or len(df) < 2:
        return {}
    ultimo = df.iloc[-1]["valor"]
    hace_1d = df.iloc[-2]["valor"] if len(df) >= 2 else None
    hace_7d = df.iloc[-7]["valor"] if len(df) >= 7 else None
    hace_30d = df.iloc[0]["valor"]
    def var(anterior):
        if anterior is None:
            return None
        diff = ultimo - anterior
        pct = (diff / anterior) * 100
        return {"diff": round(diff, 4), "pct": round(pct, 2)}
    return {
        "valor_actual": round(ultimo, 4),
        "var_1d": var(hace_1d),
        "var_7d": var(hace_7d),
        "var_30d": var(hace_30d),
        "fecha": df.iloc[-1]["fecha"].strftime("%d/%m/%Y")
    }

if __name__ == "__main__":
    datos = fetch_todas_las_series()
    print("\n--- Variaciones calculadas ---\n")
    for nombre, df in datos.items():
        variaciones = calcular_variaciones(df)
        if variaciones:
            print(f"\n{nombre.upper()}")
            print(f"  Valor actual ({variaciones['fecha']}): "
                  f"{variaciones['valor_actual']}")
            if variaciones["var_1d"]:
                s = "+" if variaciones["var_1d"]["diff"] >= 0 else ""
                print(f"  vs ayer:      {s}{variaciones['var_1d']['diff']} "
                      f"({s}{variaciones['var_1d']['pct']}%)")
            if variaciones["var_7d"]:
                s = "+" if variaciones["var_7d"]["diff"] >= 0 else ""
                print(f"  vs 7 días:    {s}{variaciones['var_7d']['diff']} "
                      f"({s}{variaciones['var_7d']['pct']}%)")
            if variaciones["var_30d"]:
                s = "+" if variaciones["var_30d"]["diff"] >= 0 else ""
                print(f"  vs 30 días:   {s}{variaciones['var_30d']['diff']} "
                      f"({s}{variaciones['var_30d']['pct']}%)")