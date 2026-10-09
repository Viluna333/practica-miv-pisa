"""
PRÁCTICA 1 — Desmuntant la mentida visual
Rediseño interactivo del informe PISA (España vs OCDE)

Mapa del código respecto al enunciado
-------------------------------------
Fase 2 · Preprocesamiento  -> función `cargar_y_preprocesar` (4 operaciones justificadas)
Fase 3 · Redisseny gráfico -> `fig_evolucion` y `fig_brecha`
Fase 3 · Interactividad    -> controles de la cabecera (5 tipologías del curso):
    - Filtrar              : selector de asignatura
    - Seleccionar          : edición PISA a destacar
    - Connectar            : la edición elegida se resalta a la vez en las dos figuras
    - Abstraer / Elaborar  : tooltips al pasar el ratón + tabla de datos bajo demanda
    - Reconfigurar         : escala del eje Y (ajustada / desde 0)

Ejecutar:  streamlit run app.py   (con pisa_esp_ocde.csv en la misma carpeta)
"""
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="PISA: España vs OCDE", layout="wide")  # debe ser la 1ª llamada a st

CSV_PATH = Path(__file__).parent / "pisa_esp_ocde.csv"

# Paleta pensada para que el protagonista (España) destaque y la referencia (OCDE)
# quede en segundo plano: principio de similitud/figura-fondo de la Gestalt.
COLOR_ESP = "#0072B2"   # azul saturado (apto para daltonismo)
COLOR_OCDE = "#8C8C8C"  # gris neutro
COLOR_EJE = "#444444"

ETIQ_ASIGNATURA = {"Matematicas": "Matemáticas", "Lectura": "Lectura", "Ciencia": "Ciencias"}


def fmt(n):
    """Entero con signo explícito y signo menos tipográfico (0 sin signo)."""
    n = int(n)
    return "0" if n == 0 else f"{n:+d}".replace("-", "−")


def a_ancho_completo(funcion, *args, **kwargs):
    """Compatibilidad entre versiones: Streamlit reciente usa width="stretch" y
    `use_container_width` está obsoleto; las versiones antiguas solo conocen este último."""
    try:
        return funcion(*args, width="stretch", **kwargs)
    except TypeError:
        return funcion(*args, use_container_width=True, **kwargs)


# ==========================================
# FASE 2: CARGA Y PREPROCESAMIENTO
# ==========================================
@st.cache_data
def cargar_y_preprocesar(path):
    df = pd.read_csv(path)

    # --- PREPROCESAMIENTO 1: limpieza e integridad -----------------------------
    # El CSV transcrito a mano trae tabuladores sobrantes en la cabecera
    # ("Puntuacion\t\t") y finales de línea CRLF. Se limpian los textos, se fuerzan
    # tipos numéricos (si no, el eje X sería categórico y el Y podría ser texto) y
    # se verifica que no haya nulos ni duplicados antes de calcular nada.
    df.columns = df.columns.str.strip()
    for col in ["Asignatura", "Region"]:
        df[col] = df[col].astype(str).str.strip()
    df["Ano"] = pd.to_numeric(df["Ano"])
    df["Puntuacion"] = pd.to_numeric(df["Puntuacion"])
    if df.isna().any().any():
        raise ValueError("El CSV contiene valores nulos o no numéricos.")
    if df.duplicated(["Ano", "Asignatura", "Region"]).any():
        raise ValueError("El CSV contiene filas duplicadas (año, asignatura, región).")

    # --- PREPROCESAMIENTO 2: normalización a magnitudes comparables ------------
    # La puntuación absoluta de cada región esconde lo importante: la DIFERENCIA.
    # Se pivota (una fila por asignatura y año) y se calculan:
    #   - Brecha = España − OCDE (puntos): comparación directa en cada edición.
    #   - Cambio acumulado respecto a la primera edición (puntos): permite comparar
    #     trayectorias aunque España y la OCDE partan de niveles distintos.
    ancho = (
        df.pivot(index=["Asignatura", "Ano"], columns="Region", values="Puntuacion")
        .reset_index()
        .sort_values(["Asignatura", "Ano"])
    )
    if ancho[["Espana", "OCDE"]].isna().any().any():
        raise ValueError("Falta algún dato de España u OCDE en alguna edición.")
    ancho["Brecha"] = ancho["Espana"] - ancho["OCDE"]
    for reg in ["Espana", "OCDE"]:
        ancho[f"{reg}_cambio"] = ancho[reg] - ancho.groupby("Asignatura")[reg].transform("first")

    # --- PREPROCESAMIENTO 3: reordenación lógica --------------------------------
    # Orden alfabético por defecto = Ciencias, Lectura, Matemáticas (sin significado).
    # Se ordenan las asignaturas por la brecha de la última edición, de la peor a la
    # mejor, y se usa ese orden en el selector. Además se recodifican las etiquetas
    # (tildes, "Ciencia" -> "Ciencias") para que el texto mostrado sea correcto.
    ancho["Asignatura"] = ancho["Asignatura"].map(ETIQ_ASIGNATURA).fillna(ancho["Asignatura"])
    ultima = ancho[ancho["Ano"] == ancho["Ano"].max()].set_index("Asignatura")["Brecha"]
    orden = ultima.sort_values().index.tolist()
    ancho["Asignatura"] = pd.Categorical(ancho["Asignatura"], categories=orden, ordered=True)
    ancho = ancho.sort_values(["Asignatura", "Ano"]).reset_index(drop=True)

    # --- PREPROCESAMIENTO 4: agrupamiento lógico de la brecha -------------------
    # La brecha es continua; se agrupa en tres categorías legibles que alimentan los
    # tooltips y la tabla (evita que el lector tenga que interpretar signos).
    def situacion(b):
        if b > 0:
            return "Por encima de la OCDE"
        if b < 0:
            return "Por debajo de la OCDE"
        return "Igual a la OCDE"

    ancho["Situacion"] = ancho["Brecha"].map(situacion)
    return ancho, orden


try:
    datos, ASIGNATURAS = cargar_y_preprocesar(CSV_PATH)
except (FileNotFoundError, ValueError) as e:
    st.error(f"No se pudieron cargar los datos: {e}")
    st.stop()

ANOS = sorted(datos["Ano"].unique().tolist())

# Rangos COMUNES a todas las asignaturas: al cambiar de filtro, una misma distancia
# visual significa siempre los mismos puntos (si no, el filtro "miente" al reescalar).
Y_MIN = math.floor((datos[["Espana", "OCDE"]].min().min() - 5) / 10) * 10
Y_MAX = math.ceil((datos[["Espana", "OCDE"]].max().max() + 5) / 10) * 10
LIM_BRECHA = math.ceil(datos["Brecha"].abs().max()) + 3


# ==========================================
# FASE 3: REDISEÑO GRÁFICO (TUFTE)
# ==========================================
def base_layout(fig, titulo, titulo_x, titulo_y, rango_y):
    """Estilo común: fondo blanco, sin cajas, rejilla mínima (alto ratio datos-tinta)."""
    fig.update_layout(
        template="plotly_white",
        height=430,
        margin=dict(l=10, r=10, t=60, b=10),
        title=dict(text=titulo, x=0, xanchor="left", font=dict(size=16, color=COLOR_EJE)),
        xaxis=dict(
            title=titulo_x,
            tickmode="array",
            tickvals=ANOS,                    # solo las ediciones reales del informe
            range=[min(ANOS) - 1, max(ANOS) + 1],
            showgrid=False,
        ),
        yaxis=dict(title=titulo_y, range=rango_y, gridcolor="#EEEEEE", zeroline=False),
        font=dict(color=COLOR_EJE),
    )
    return fig


def fig_evolucion(d, ano_sel, desde_cero):
    """Líneas: lo correcto para una magnitud que evoluciona en el tiempo.
    El eje X es numérico, por lo que el espaciado refleja los años reales
    (2015-2018-2022-2025 no son equidistantes)."""
    fig = go.Figure()
    destacado = (d["Ano"] == ano_sel).tolist()
    series = [  # OCDE primero para que España se dibuje encima
        ("OCDE", "OCDE", COLOR_OCDE, "dash", 2.5, 2),
        ("España", "Espana", COLOR_ESP, "solid", 4, 1),
    ]
    for nombre, col, color, dash, ancho, rank in series:
        fig.add_trace(
            go.Scatter(
                x=d["Ano"], y=d[col], name=nombre, legendrank=rank,
                mode="lines+markers",
                line=dict(color=color, width=ancho, dash=dash),  # dash: distinguible también en B/N
                marker=dict(color=color, size=[14 if s else 7 for s in destacado]),
                customdata=d["Brecha"],
                hovertemplate=(
                    nombre + ": <b>%{y} pts</b>"
                    + (" (%{customdata:+d} vs OCDE)" if col == "Espana" else "")
                    + "<extra></extra>"
                ),
            )
        )
    fig.add_vline(x=ano_sel, line=dict(color="#BBBBBB", width=1, dash="dot"))  # [Seleccionar]

    titulo_y = "Puntuación media (puntos PISA)"
    if not desde_cero:
        titulo_y += " · el eje no empieza en 0"
    rango = [0, 600] if desde_cero else [Y_MIN, Y_MAX]
    base_layout(fig, "Evolución de la puntuación", "Edición del informe PISA (año)", titulo_y, rango)
    fig.update_layout(
        hovermode="x unified",  # [Abstraer/Elaborar] detalle bajo demanda
        legend=dict(orientation="h", x=1, xanchor="right", y=1.04, yanchor="bottom", title_text=""),
    )
    return fig


def fig_brecha(d, ano_sel):
    """Barras sobre una línea base en 0: aquí el cero SÍ es significativo (empate con
    la OCDE) y la longitud de la barra es proporcional a la diferencia."""
    opacidad = [1.0 if a == ano_sel else 0.35 for a in d["Ano"]]  # [Connectar] mismo estado
    fig = go.Figure(
        go.Bar(
            x=d["Ano"], y=d["Brecha"], width=1.4,
            marker=dict(color=COLOR_ESP, opacity=opacidad),
            text=[fmt(b) for b in d["Brecha"]], textposition="outside",
            customdata=d["Situacion"],
            hovertemplate="%{customdata}: <b>%{y:+d} pts</b><extra></extra>",
        )
    )
    base_layout(
        fig, "Brecha España − OCDE", "Edición del informe PISA (año)",
        "Diferencia (puntos PISA)", [-LIM_BRECHA, LIM_BRECHA],
    )
    fig.update_layout(
        showlegend=False,
        yaxis=dict(range=[-LIM_BRECHA, LIM_BRECHA], gridcolor="#EEEEEE",
                   zeroline=True, zerolinecolor=COLOR_EJE, zerolinewidth=1.5,
                   title="Diferencia (puntos PISA)"),
    )
    for texto, y, anclaje in [("▲ España por encima de la OCDE", LIM_BRECHA - 0.5, "top"),
                              ("▼ España por debajo de la OCDE", -LIM_BRECHA + 0.5, "bottom")]:
        fig.add_annotation(x=0, xref="paper", y=y, yref="y", text=texto, showarrow=False,
                           xanchor="left", yanchor=anclaje, font=dict(size=11, color="#666666"))
    return fig


# ==========================================
# INTERFAZ E INTERACTIVIDAD
# ==========================================
st.title(f"PISA {min(ANOS)}–{max(ANOS)}: ¿cuánto se aleja España de la OCDE?")
st.caption("Rediseño del informe PISA: puntuaciones absolutas, brecha respecto a la OCDE y "
           "una escala del eje honesta y explícita.")

c1, c2, c3 = st.columns(3)
with c1:
    # [Filtrar] un único subgrupo cada vez: menos carga cognitiva que 6 líneas a la vez
    asignatura = st.radio("Asignatura", ASIGNATURAS, horizontal=True,
                          help="Ordenadas de mayor a menor brecha negativa en la última edición.")
with c2:
    # [Seleccionar] resalta una edición clave en ambas figuras y en las tarjetas
    ano_sel = st.select_slider("Edición a destacar", options=ANOS, value=ANOS[-1])
with c3:
    # [Reconfigurar] el usuario puede comprobar cómo cambia la percepción con otra escala
    escala = st.radio("Escala del eje Y (puntuación)", ["Ajustada a los datos", "Desde 0"],
                      horizontal=True,
                      help="La escala PISA no tiene un cero natural (se definió con una media de "
                           "referencia de unos 500 puntos), así que no hace falta empezar en 0. "
                           "Con 'Desde 0' se ve cómo se aplanan las diferencias.")
desde_cero = escala == "Desde 0"

d = datos[datos["Asignatura"] == asignatura].reset_index(drop=True)
i = int(d.index[d["Ano"] == ano_sel][0])
fila = d.loc[i]
prev = d.loc[i - 1] if i > 0 else None
primera, ultima = d.iloc[0], d.iloc[-1]

# Mensaje principal, calculado a partir de los datos (no escrito a mano)
st.markdown(
    f"**{asignatura}.** Entre {int(primera['Ano'])} y {int(ultima['Ano'])}, España ha variado "
    f"**{fmt(ultima['Espana_cambio'])} puntos** y la OCDE **{fmt(ultima['OCDE_cambio'])}**; la brecha "
    f"pasa de **{fmt(primera['Brecha'])}** a **{fmt(ultima['Brecha'])}** puntos."
)

m1, m2, m3 = st.columns(3)
m1.metric(f"España · {ano_sel}", f"{int(fila['Espana'])} pts",
          delta=None if prev is None else f"{int(fila['Espana'] - prev['Espana']):+d} vs {int(prev['Ano'])}")
m2.metric(f"OCDE · {ano_sel}", f"{int(fila['OCDE'])} pts",
          delta=None if prev is None else f"{int(fila['OCDE'] - prev['OCDE']):+d} vs {int(prev['Ano'])}")
flecha = "up" if fila["Brecha"] > 0 else "down" if fila["Brecha"] < 0 else "off"
try:
    m3.metric("Brecha España − OCDE", f"{fmt(fila['Brecha'])} pts",
              delta=fila["Situacion"], delta_color="off", delta_arrow=flecha)
except TypeError:  # Streamlit antiguo sin delta_arrow
    m3.metric("Brecha España − OCDE", f"{fmt(fila['Brecha'])} pts")
    m3.caption(fila["Situacion"])

# [Connectar] las dos figuras comparten asignatura y edición destacada
g1, g2 = st.columns([3, 2])
with g1:
    a_ancho_completo(st.plotly_chart, fig_evolucion(d, ano_sel, desde_cero))
with g2:
    a_ancho_completo(st.plotly_chart, fig_brecha(d, ano_sel))

st.caption(
    "Datos transcritos de la tabla del gráfico de José Gefaell (@ChGefaell, X, 8/9/2026), que cita como "
    "fuente el informe PISA 2015–2025 de la OCDE (cifras de 2025 coincidentes con las publicadas en septiembre "
    "de 2026). El CSV no incluye errores estándar: según el Ministerio de Educación, en 2025 las tres brechas "
    "son significativas, pero en ediciones anteriores diferencias de pocos puntos podrían no serlo."
)

# [Abstraer/Elaborar] más detalle solo si el usuario lo pide
with st.expander("Ver tabla de datos procesados"):
    tabla = d[["Asignatura", "Ano", "Espana", "OCDE", "Brecha", "Situacion"]].rename(
        columns={"Ano": "Año", "Espana": "España", "Situacion": "Situación"}
    )
    a_ancho_completo(st.dataframe, tabla, hide_index=True)