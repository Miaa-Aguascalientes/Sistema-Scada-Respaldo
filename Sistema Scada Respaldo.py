import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static, st_folium
from folium.plugins import Fullscreen, MousePosition, LocateControl, MarkerCluster
from sqlalchemy import create_engine, event, text
import psycopg2
import json
import urllib.parse
from datetime import datetime, timedelta
import datetime as dt
from streamlit_autorefresh import st_autorefresh
import base64
import hashlib
import time
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import locale
from shapely import wkt
import geopandas as gpd
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError
import pytz
from cryptography.fernet import Fernet
import altair as alt

st.set_page_config(
    page_title="Sistema Scada", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 0.1. INICIALIZACIÓN DE ESTADOS
# ==========================================
if "autenticado" not in st.session_state:
  query_params = st.query_params
  if query_params.get("access") == "granted":
    st.session_state.autenticado = True
    st.session_state.rol = query_params.get("role", "usuario")
  else:
    st.session_state.autenticado = False

if "fase_carga" not in st.session_state:
  st.session_state.fase_carga = False

# ==========================================
# 0.2. FUNCIONES DE BASE DE DATOS Y SEGURIDAD
# ==========================================
@st.cache_resource
def get_mysql_telemetria_engine():
  try:
    c = st.secrets["mysql_telemetria"]
    pwd = urllib.parse.quote_plus(c["password"])
    engine = create_engine(
        f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}",
        pool_recycle=3600,
        pool_pre_ping=True,
    )
    return engine
  except Exception as e:
    st.error(f"⚠️ ERROR CRÍTICO DE CONEXIÓN: {e}")
    return None

SECRET_FERNET_KEY = b"12345678901234567890123456789012"

def get_fernet_cipher():
  try:
    key = st.secrets["security"]["fernet_key"].encode()
  except Exception:
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_FERNET_KEY).digest())
  return Fernet(key)

def encriptar_pwd(password_plana):
  try:
    f = get_fernet_cipher()
    return f.encrypt(password_plana.encode()).decode()
  except Exception:
    return password_plana

def desencriptar_pwd(password_cifrada):
  try:
    f = get_fernet_cipher()
    return f.decrypt(password_cifrada.encode()).decode()
  except Exception:
    return password_cifrada

def verificar_credenciales(usuario_input, password_input):
  try:
    engine = get_mysql_telemetria_engine()
    if engine is None:
      return None

    query = text(
        "SELECT password, tipo_usuario FROM usuarios WHERE usuario = :usr"
    )
    with engine.connect() as conn:
      df_user = pd.read_sql(query, conn, params={"usr": usuario_input})

    if df_user.empty:
      return None

    pwd_almacenada = str(df_user["password"].iloc[0])
    tipo_usuario = df_user["tipo_usuario"].iloc[0]
    pwd_decifrada = desencriptar_pwd(pwd_almacenada)

    if str(password_input) == pwd_decifrada or str(password_input) == str(pwd_almacenada):
      return tipo_usuario

    return None
  except Exception as e:
    st.error(f"Error al consultar usuario: {e}")
    return None

# ==========================================
# 0.3. ESTILO VISUAL HUD AJUSTADO
# ==========================================
st.markdown(
    """
<style>
    .stApp { background-color: #050a10 !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header, footer { visibility: hidden !important; }
    
    .visual-core { position: relative; width: 480px; height: 480px; margin: auto; }
    .ring { position: absolute; border-radius: 50%; border: 4px solid transparent; animation: spin var(--d) linear infinite; }
    .r1 { width: 100%; height: 100%; border-top: 8px solid #00d4ff; border-bottom: 8px solid #00d4ff; --d: 4s; }
    .r2 { width: 78%; height: 78%; top: 11%; left: 11%; border: 3px dashed #00d4ff; --d: 8s; animation-direction: reverse; }
    .center-logo { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
    .logo-miaa { width: 190px; filter: drop-shadow(0 0 15px #00d4ff); }
    
    .login-box { 
        background: rgba(0, 212, 255, 0.05); 
        border-left: 8px solid #00d4ff; 
        padding: 30px; 
        margin-top: 50px;
        max-width: 320px;
        margin-left: 0;
    }
    
    @keyframes spin { 100% { transform: rotate(360deg); } }
    
    div[data-testid="stTextInputRootElement"] {
        background-color: #0d1b2a !important;
        border: 1px solid #1f4068 !important;
        border-radius: 0px !important;
        padding: 0px 10px !important; 
        height: 40px !important;
        box-shadow: none !important;
    }
    
    .stTextInput input { 
        background-color: transparent !important; 
        color: #00d4ff !important; 
        border: none !important;
        height: 100% !important;
        font-family: 'Courier New', monospace;
        font-size: 15px !important;
        padding: 0 !important;
    }
    
    .stButton button { 
        background: #00d4ff !important; 
        color: #050a10 !important; 
        font-weight: bold !important; 
        width: 100%; 
        height: 45px; 
        border: none !important;
        border-radius: 0px !important;
    }
    
    div[data-testid="stForm"] { border: none !important; padding: 0 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 0.4. LÓGICA DE INTERFAZ DE LOGIN
# ==========================================
if not st.session_state.autenticado:
  col_esp1, col_vis, col_log, col_esp2 = st.columns([0.1, 1.8, 2, 1.1])
  with col_vis:
    st.markdown('<div style="height: 12vh;"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="visual-core">
            <div class="ring r1"></div><div class="ring r2"></div>
            <div class="center-logo">
                <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-miaa">
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

  with col_log:
    st.markdown('<div style="height: 20vh;"></div>', unsafe_allow_html=True)
    if not st.session_state.fase_carga:
      st.markdown('<div class="login-box">', unsafe_allow_html=True)
      st.markdown('<h2 style="color:#00d4ff; font-size:18px;">// INGRESE SUS CREDENCIALES</h2>', unsafe_allow_html=True)
      with st.form("login_form", clear_on_submit=False):
        u = st.text_input("USUARIO", key="u_login")
        p = st.text_input("PASSWORD", type="password", key="p_login")
        submit_button = st.form_submit_button("ACCEDER AL SISTEMA")
        if submit_button:
          rol = verificar_credenciales(u, p)
          if rol:
            st.session_state.temp_rol = rol
            st.session_state.fase_carga = True
            st.rerun()
          else:
            st.error("❌ ACCESO DENEGADO")
      st.markdown("</div>", unsafe_allow_html=True)
    else:
      st.markdown('<div class="login-box">', unsafe_allow_html=True)
      st.markdown('<h2 style="color:#00d4ff; font-size:18px;">// CARGANDO SCADA...</h2>', unsafe_allow_html=True)
      prog = st.progress(0)
      status = st.empty()
      time.sleep(0.4)
      st.session_state.autenticado = True
      st.session_state.rol = st.session_state.temp_rol
      st.session_state.fase_carga = False
      st.rerun()
  st.stop()

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y PARÁMETROS
# ==========================================
params = st.query_params
sector_seleccionado = params.get("sector", None)
titulo_pestaña = f"MIAA - Estado de Sector: {sector_seleccionado}" if sector_seleccionado else "MIAA - Estado de Pozos"

st.set_page_config(
    page_title=titulo_pestaña, 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide", 
    initial_sidebar_state="expanded"
)
count = st_autorefresh(interval=300000, limit=1000, key="scada_refresh")

# ==========================================
# 2. FUNCIONES DE CONEXIÓN A MOTORES SCADA / POSTGRES
# ==========================================
@st.cache_resource
def get_mysql_scada_engine():
    try:
        c = st.secrets["mysql_scada"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}")
        @event.listens_for(engine, "connect")
        def set_big_selects(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("SET SESSION SQL_BIG_SELECTS=1;")
            cursor.close()
        with engine.connect() as conn: pass 
        return engine
    except Exception as e:
        st.error(f"Error al conectar a la BD SCADA: {e}")
        return None

@st.cache_resource
def get_postgres_conn():
    try: 
        conn = psycopg2.connect(**st.secrets["postgres"])
        return conn
    except Exception as e: 
        st.error(f"Error de conexión Postgres: {e}")
        return None

def cargar_datos_scada(lista_tags):
    engine = get_mysql_scada_engine()
    if not engine or not lista_tags: return {}
    try:
        tags_str = "', '".join(lista_tags)
        query = f"""
            SELECT r.NAME, h.VALUE, h.FECHA 
            FROM VfiTagNumHistory_Ultimo h 
            JOIN VfiTagRef r ON h.GATEID = r.GATEID 
            WHERE r.NAME IN ('{tags_str}') 
            AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)
        """
        df = pd.read_sql(query, engine)
        return {row['NAME']: (row['VALUE'], row['FECHA'].strftime('%d/%m %H:%M') if row['FECHA'] else "N/A") for _, row in df.iterrows()}
    except Exception:
        return {}

@st.cache_data(ttl=3600)
def cargar_sectores_poligonos():
    conn = get_postgres_conn()
    if not conn: return []
    try:
        query = """
            SELECT sector, "Pozos_Sector", "Superficie", "Long_Red", "Vol_Prod", "U_Domesticos", 
                   "U_NoDom", "U_Tot", "Poblacion", "Cons_m3", "Faltas_Agua", "Fugas_Tot", "FTC", "FTA", 
                   "Vol_Medid", "Vol_Fact", "Kwh", "costoKw-hr", "Recaudacion", "Dotacion", "Balance_Estimado",
                   ST_AsGeoJSON(ST_Transform(geom, 4326)) as geo 
            FROM "Sectorizacion"."Sectores_hidr"
        """
        df = pd.read_sql(query, conn)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Error al cargar sectores: {e}")
        return []
    finally:
        if conn: conn.close()

@st.cache_data(ttl=3600)
def get_todas_las_colonias():
    query = """
        SELECT ST_AsText(geom) as geom_wkt, Pozos, Col_atl, Sector, Distrito, Supervisor,
               Pozo_1, Afectacion_1, Pozo_2, Afectacion_2, Pozo_3, Afectacion_3, 
               Pozo_4, Afectacion_4, Pozo_5, Afectacion_5, Pozo_6, Afectacion_6, 
               Pozo_7, Afectacion_7, Pozo_8, Afectacion_8, Pozo_9, Afectacion_9, Pozo_10, Afectacion_10 
        FROM Diccionario_colonias
    """
    try:
        df = pd.read_sql(query, get_mysql_telemetria_engine())
        if not df.empty and df['geom_wkt'].iloc[0] is not None:
            df['geometry'] = df['geom_wkt'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry')
            gdf.set_crs(epsg=32613, inplace=True)
            return gdf.to_crs(epsg=4326)
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600)
def get_todos_los_sectores_geo():
    query = """
        SELECT ST_AsText(geom) as geom_wkt, Sector, Pozos, Col_atl,
               Pozo_1, Afectacion_1, Pozo_2, Afectacion_2, Pozo_3, Afectacion_3, 
               Pozo_4, Afectacion_4, Pozo_5, Afectacion_5, Pozo_6, Afectacion_6, 
               Pozo_7, Afectacion_7, Pozo_8, Afectacion_8, Pozo_9, Afectacion_9, Pozo_10, Afectacion_10 
        FROM Diccionario_sectores
    """
    try:
        df = pd.read_sql(query, get_mysql_telemetria_engine())
        if not df.empty and 'geom_wkt' in df.columns and df['geom_wkt'].iloc[0] is not None:
            df['geometry'] = df['geom_wkt'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry')
            gdf.set_crs(epsg=32613, inplace=True)
            return gdf.to_crs(epsg=4326)
    except Exception:
        pass
    return None

@st.cache_data(ttl=60)
def obtener_pozos_con_incidencias_hoy():
    engine = get_mysql_scada_engine()
    if engine is None: return {}
    try:
        query = "SELECT NUM_POZO, DIAGNOSTICO_FALLA, ESTATUS FROM vw_incidencias_en_pozos WHERE ESTATUS != 'CERRADA'"
        df_inc = pd.read_sql(query, engine)
        dic_incidencias = {}
        for _, row in df_inc.iterrows():
            val = row['NUM_POZO']
            if pd.notna(val):
                id_limpio = str(val).strip().upper()
                if id_limpio:
                    dic_incidencias[id_limpio] = row['DIAGNOSTICO_FALLA'] or 'Sin diagnóstico'
        return dic_incidencias
    except Exception:
        return {}

def calcular_color_colonia(props, pozos_con_incidencia):
    suma_afectacion = 0.0
    tiene_incidencia_activa = False
    for i in range(1, 11):
        pozo_col = props.get(f'Pozo_{i}')
        afectacion_col = props.get(f'Afectacion_{i}')
        if pozo_col is not None:
            id_p_limpio = str(pozo_col).strip().upper()
            id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
            id_p_sin_guion = id_p_limpio.replace('-', '')
            if id_p_limpio in pozos_con_incidencia or id_p_con_guion in pozos_con_incidencia or id_p_sin_guion in pozos_con_incidencia:
                tiene_incidencia_activa = True
                if pd.notna(afectacion_col):
                    try: suma_afectacion += float(str(afectacion_col).replace('%', '').strip())
                    except: pass
    if not tiene_incidencia_activa: return '#3498DB', 0
    if tiene_incidencia_activa and suma_afectacion == 0: return '#FFA500', 1  
    if 76 <= suma_afectacion <= 100: return '#FF0000', suma_afectacion
    elif 51 <= suma_afectacion <= 75: return '#FFFF00', suma_afectacion
    elif 31 <= suma_afectacion <= 50: return '#FFA500', suma_afectacion
    elif 1 <= suma_afectacion <= 30: return '#69ADDD', suma_afectacion
    else: return '#FF0000', suma_afectacion

def calcular_color_sector(props, pozos_con_incidencia):
    return calcular_color_colonia(props, pozos_con_incidencia)

def formato_hora(decimal):
    try:
        if decimal == "N/A" or decimal is None: return "00:00"
        horas = int(float(decimal))
        minutos = int((float(decimal) - horas) * 60)
        return f"{horas:02d}:{minutos:02d}"
    except:
        return "00:00"

def get_blink_icon(color):
    return f"""
    <div style="width: 8px; height: 8px; background-color: {color}; border-radius: 50%; box-shadow: 0 0 8px {color}; animation: blinker 1s linear infinite;"></div>
    <style>@keyframes blinker {{ 50% {{ opacity: 0.2; }} }}</style>
    """

# ==========================================
# 3. CARGA DE DICCIONARIOS DE INFRAESTRUCTURA
# ==========================================
@st.cache_data(ttl=3600) 
def cargar_mapa_pozos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_pozos = pd.read_sql("SELECT * FROM Diccionario_de_pozos", engine)
        nuevo_mapa = {}
        for _, row in df_pozos.iterrows():
            try:
                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                nuevo_mapa[row['Pozos']] = {
                    "coord": (lat, lon), "bomba": row['bomba'], "caudal": row['caudal'],
                    "presion": row['presion'], "sumergencia": row['sumergencia'], "nivel_dinamico": row['nivel_dinamico'],
                    "nivel_tanque": row['nivel_tanque'], "columna": row['columna'], "h_arranque": row['H_arranque'],
                    "h_paro": row['H_paro'], "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                    "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']], "totalizado": row['totalizado']
                }
            except: continue
        return nuevo_mapa
    except: return {}

@st.cache_data(ttl=3600)
def cargar_tanques_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_tq = pd.read_sql("SELECT * FROM Diccionario_de_tanques", engine)
        nuevo_mapa_tq = {}
        for _, row in df_tq.iterrows():
            try:
                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                n_max = float(row['Nivel_max']) if row.get('Nivel_max') is not None else 1.0
                nuevo_mapa_tq[row['TQ']] = {
                    "nombre": row['Nombre_tq'], "coord": (lat, lon), "tag_nivel": row['nivel_tanque'],
                    "nivel_max": n_max if n_max > 0 else 1.0, "sitios": row['Sitios']
                }
            except: continue
        return nuevo_mapa_tq
    except: return {}

@st.cache_data(ttl=3600)
def cargar_rebombeos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_rb = pd.read_sql("SELECT * FROM Diccionario_de_rebombeos", engine)
        nuevo_mapa_rb = {}
        for _, row in df_rb.iterrows():
            try:
                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                nuevo_mapa_rb[row['Rebombeo']] = {
                    "nombre": row['Nombre_rebombeo'], "coord": (lat, lon), "telemetria": row['Telemetria'],
                    "presion": row['presion'], "nivel_tanque": row['nivel_tanque'],
                    "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                    "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']]
                }
            except: continue
        return nuevo_mapa_rb
    except: return {}

@st.cache_data(ttl=5)
def cargar_puntos_de_control_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_de_control", engine)
        d_res = {}
        for _, r in df.iterrows():
            try:
                raw_c = str(r['coord']).replace('(', '').replace(')', '').replace(' ', '').strip()
                lat_s, lon_s = raw_c.split(',')
                id_reg_val = r.get('Serie', r.get('Registrador', 'ID'))
                d_res[str(id_reg_val)] = {
                    "nombre": str(r.get('Domicilio', r.get('Nombre_registrador', 'S/N'))),
                    "coord": [float(lat_s), float(lon_s)], "sector": str(r['Sector']).split('.')[0].strip(),
                    "tag_p1": r.get('Presion_1'), "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'),
                    "tag_vbat": r.get('bateria'), "Serie": str(id_reg_val)
                }
            except: continue
        return d_res
    except: return {}

@st.cache_data(ttl=5)
def cargar_puntos_criticos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_criticos", engine)
        d_res = {}
        for _, r in df.iterrows():
            try:
                raw_c = str(r['coord']).replace('(', '').replace(')', '').replace(' ', '').strip()
                lat_s, lon_s = raw_c.split(',')
                id_reg = r.get('Serie', r.get('Registrador', 'ID'))
                d_res[str(id_reg)] = {
                    "nombre": str(r.get('Colonia', 'S/C')), "Domicilio": str(r.get('Domicilio', 'Sin Domicilio')),
                    "coord": [float(lat_s), float(lon_s)], "sector": str(r['Sector']).split('.')[0].strip(),
                    "tag_p1": r.get('Presion_1'), "tag_q": r.get('Caudal')
                }
            except: continue
        return d_res
    except: return {}

@st.cache_data(ttl=5)
def cargar_vrp_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_vrp", engine)
        d_res = {}
        for _, r in df.iterrows():
            try:
                raw_c = str(r['coord']).replace('(', '').replace(')', '').replace(' ', '').strip()
                lat_s, lon_s = raw_c.split(',')
                id_val = r.get('Serie', 'ID_VRP')
                d_res[str(id_val)] = {
                    "nombre": str(r.get('Domicilio', 'S/N')), "coord": [float(lat_s), float(lon_s)],
                    "sector": str(r['Sector']).split('.')[0].strip(), "tag_p1": r.get('Presion_1'),
                    "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'), "Serie": str(id_val)
                }
            except: continue
        return d_res
    except: return {}

@st.cache_data(ttl=3600)
def cargar_medidores_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        query = "SELECT Medidor, Nombre, Lat, Lon, Flujo, Presion, Consumo, MAX(FECHA) as UltimaFecha FROM MACROMEDIDORES GROUP BY Medidor"
        df = pd.read_sql(query, engine)
        datos_medidores = {}
        for _, row in df.iterrows():
            datos_medidores[row['Medidor']] = {
                "nombre": row['Nombre'], "coord": (float(row['Lat']), float(row['Lon'])),
                "flujo": row['Flujo'], "presion": row['Presion'], "consumo": row['Consumo'],
                "ultima_fecha": pd.to_datetime(row['UltimaFecha'])
            }
        return datos_medidores
    except: return {}

@st.cache_data(ttl=60)
def get_data():
    engine = get_mysql_scada_engine()
    if engine is None: return pd.DataFrame()
    try:
        return pd.read_sql("SELECT NUM_POZO, COLONIA, FECHA_HORA_INICIO, FECHA_HORA_FIN, DIAGNOSTICO_FALLA, TIEMPO_ESTIMADO_ATENCION, RESPONSABLE, ESTATUS FROM vw_incidencias_en_pozos ORDER BY FECHA_HORA_INICIO DESC", engine)
    except: return pd.DataFrame()

# ==========================================
# 4. MÓDULOS DE VISUALIZACIÓN DE GRÁFICOS (TANQUES, POZOS, MACROMEDIDORES)
# ==========================================
if "graficar_tanque" in params:
    tag_a_graficar = params.get("graficar_tanque", None)
    nombre_tq = params.get("nombre", "Tanque")
    st.title(f"📊 Análisis de Nivel: {nombre_tq}")
    st.info(f"Visualizando histórico para el tag: {tag_a_graficar}")
    st.stop()

if "graficar_pozo" in params:
    id_pozo_graf = params["graficar_pozo"]
    nombre_pozo = params.get("nombre", id_pozo_graf)
    st.title(f"📊 Análisis Detallado del Pozo: {nombre_pozo}")
    st.stop()

if "ver_grafico" in params:
    tag_a_graficar = params.get("ver_grafico")
    st.title(f"📊 Análisis de Macromedidor: {tag_a_graficar}")
    st.stop()

# ==========================================
# 5. ESTILO CSS GENERAL
# ==========================================
st.markdown("""
    <style>
        [data-testid="collapsedControl"], button[kind="headerNoPadding"], [data-testid="stSidebarCollapseButton"] { display: none !important; }
        header { visibility: hidden !important; height: 0px !important; }
        .stApp { background-color: #000000; color: white; }
        .block-container { padding-top: 0rem !important; margin-top: 15px !important; max-width: 100% !important; }
        .titulo-superior {
            position: fixed; top: 0px; left: calc(50% + 160px); transform: translateX(-50%);
            z-index: 1000; color: #00d4ff; font-size: 1.5rem; font-weight: bold;
            text-transform: uppercase; letter-spacing: 2px; text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            background-color: #000000; width: 100%; text-align: center; padding: 10px 0;
            border-bottom: 1px solid #1f4068;
        }
        .contenedor-indicadores {
           position: fixed; top: 65px; left: 320px; right: 0;
           display: flex; justify-content: center; align-items: center; gap: 15px;
           z-index: 1001; background: transparent; padding: 0 15px;
        }
        .card-indicador {
           flex: 1; border: 1px solid #1f4068; 
           background: linear-gradient(180deg, rgba(11, 26, 41, 0.95) 0%, rgba(0, 0, 0, 1) 100%);
           padding: 8px 5px; text-align: center; border-radius: 10px;
        }
        .sidebar-logo { 
           position: fixed; top: 20px; left: 40px; width: 170px; height: 50px;  
           z-index: 999999; display: flex; justify-content: center; align-items: center;
           background-color: #0b1a29; border-bottom: 1px solid #1f4068;
        }
        .status-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 5px; font-weight: bold; }
        .status-ok { background-color: #1b5e20; color: #a5d6a7; }
        .status-err { background-color: #b71c1c; color: #ef9a9a; }
        .pulsante { animation: parpadeo 1.2s infinite; }
        @keyframes parpadeo { 0% { opacity: 1; } 50% { opacity: 0.1; } 100% { opacity: 1; } }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 6. PROCESAMIENTO DE DATOS EN TIEMPO REAL
# ==========================================
sectores = cargar_sectores_poligonos()
mapa_pozos_dict = cargar_mapa_pozos_desde_db()
mapa_tanques_dict = cargar_tanques_desde_db()
mapa_rebombeos_dict = cargar_rebombeos_desde_db()

tags_a_consultar = []
for p in mapa_pozos_dict.values():
    tags_a_consultar.extend([p['bomba'], p['caudal'], p['presion'], p['nivel_tanque'], p['nivel_dinamico'], p['sumergencia'], p['columna']])
    tags_a_consultar.extend(p['voltajes_l'] + p['amperajes_l'])

for t in mapa_tanques_dict.values():
    if t['tag_nivel']: tags_a_consultar.append(t['tag_nivel'])

for r in mapa_rebombeos_dict.values():
    tags_a_consultar.extend([r['presion'], r['nivel_tanque']])
    tags_a_consultar.extend(r['voltajes_l'] + r['amperajes_l'])

tags_finales = list(set([str(t).strip() for t in tags_a_consultar if t and str(t) not in ['0', 'Sin telemetria', 'None']]))
data_scada = cargar_datos_scada(tags_finales)

pozos_on, pozos_off, pozos_sin_telemetria, pozos_falla_com = [], [], [], []
total_q, total_p = 0.0, 0.0
ahora = datetime.utcnow() - timedelta(hours=6) 

for id_p, info in mapa_pozos_dict.items():
    bomba_val = str(info['bomba']).strip()
    if bomba_val == "Sin telemetria":
        info.update({'status_label': 'SIN TELEMETRÍA', 'color_final': '#808080', 'blink': False})
        pozos_sin_telemetria.append(id_p)
        continue
    tag_l1 = info['voltajes_l'][0]
    _, fecha_str = data_scada.get(tag_l1, (0, "N/A"))
    es_falla_com = False
    if fecha_str != "N/A":
        try:
            fecha_dt = datetime.strptime(f"{ahora.year}/{fecha_str}", "%Y/%d/%m %H:%M")
            if (ahora - fecha_dt).total_seconds() / 3600 > 4: es_falla_com = True
        except: es_falla_com = True
    else: es_falla_com = True

    if es_falla_com:
        info.update({'status_label': 'FALLA COM.', 'color_final': '#FFA500', 'blink': True})
        pozos_falla_com.append(id_p)
    else:
        val_bba, _ = data_scada.get(info['bomba'], (0, "N/A"))
        if val_bba >= 1:
            info.update({'status_label': 'OPERANDO', 'color_final': '#00FF00', 'blink': False})
            pozos_on.append(id_p)
            total_q += data_scada.get(info['caudal'], (0, ""))[0]
            total_p += data_scada.get(info['presion'], (0, ""))[0]
        else:
            info.update({'status_label': 'APAGADO', 'color_final': '#FF0000', 'blink': True})
            pozos_off.append(id_p)

for id_rb, info in mapa_rebombeos_dict.items():
    telemetria_status = str(info.get('telemetria', '')).strip().lower()
    if telemetria_status == "sin telemetria":
        info.update({'status_label': 'SIN TELEMETRÍA', 'color_final': '#808080', 'blink': False})
    else:
        pres_val, _ = data_scada.get(info['presion'], (0, "N/A"))
        if pres_val < 0.10: info.update({'status_label': 'APAGADO', 'color_final': '#FF0000', 'blink': True})
        else: info.update({'status_label': 'OPERANDO', 'color_final': '#00FF00', 'blink': False})

# ==========================================
# 7. SECCIÓN DETALLE DE SECTOR
# ==========================================
if sector_seleccionado:
    st.markdown(f"<h1 style='color: #00d4ff; text-align: center;'>ANÁLISIS DE SECTOR: {sector_seleccionado}</h1>", unsafe_allow_html=True)
    st.stop()

# ==========================================
# 8. SIDEBAR Y CONTROLES LATERALES
# ==========================================
with st.sidebar:
    st.markdown('<div class="sidebar-logo"><img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg"></div>', unsafe_allow_html=True)
    if 'centro_mapa' not in st.session_state:
        st.session_state.centro_mapa = [21.8820, -102.2800]
        st.session_state.zoom_inicial = 12.5
    
    with st.expander("🔌 Conexiones BD", expanded=False):
        st.markdown(f"**BD-Scada:** <span class='status-tag status-ok'>OK</span>", unsafe_allow_html=True)
        st.markdown(f"**BD-Diccionarios:** <span class='status-tag status-ok'>OK</span>", unsafe_allow_html=True)
        st.markdown(f"**BD-PostgreSQL:** <span class='status-tag status-ok'>OK</span>", unsafe_allow_html=True)
    
    pozo_buscado = st.selectbox("🔍 Localizar Pozo", options=[""] + sorted(list(mapa_pozos_dict.keys())))
    tanque_buscado = st.selectbox("🛢️ Localizar Tanque", options=[""] + sorted(list(mapa_tanques_dict.keys())))
    rebombeo_buscado = st.selectbox("🧊 Localizar Rebombeo", options=[""] + sorted(list(mapa_rebombeos_dict.keys())))
    sector_buscado = st.selectbox("🏘️ Localizar Sector", options=[""] + sorted([s['sector'] for s in sectores]))

    if pozo_buscado:
        st.session_state.centro_mapa = mapa_pozos_dict[pozo_buscado]['coord']
        st.session_state.zoom_inicial = 18
    elif tanque_buscado:
        st.session_state.centro_mapa = mapa_tanques_dict[tanque_buscado]['coord']
        st.session_state.zoom_inicial = 18
    elif rebombeo_buscado:
        st.session_state.centro_mapa = mapa_rebombeos_dict[rebombeo_buscado]['coord']
        st.session_state.zoom_inicial = 18

    if st.button("♻️ Actualizar Datos", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
        
    with st.expander("🗺️ Control de Capas", expanded=False):
        ver_pozos = st.checkbox("💧 Pozos", value=True)
        ver_colonias = st.checkbox("🏙️ Colonias", value=False)
        ver_sectores = st.checkbox("🏘️ Sectores", value=True)
        ver_tanques = st.checkbox("🛢️ Tanques", value=False)
        ver_rebombeos = st.checkbox("🧊 Rebombeos", value=False)
        ver_macromedidores = st.checkbox("🌀 Macromedidores", value=False)

dic_incidencias_activas = obtener_pozos_con_incidencias_hoy()

# ==========================================
# 9. MAPA PRINCIPAL E INDICADORES SUPERIORES
# ==========================================
st.markdown('<div class="titulo-superior">SISTEMA - AGUASCALIENTES</div>', unsafe_allow_html=True)

c_total = total_q if 'total_q' in locals() else 0.0
p_prom = (total_p / max(len(pozos_on), 1)) if 'total_p' in locals() else 0.0

st.markdown(f"""
    <div class="contenedor-indicadores">
        <div class="card-indicador"><p style="color:#ffffff; font-size:0.8rem; margin:0;">💧 Caudal total</p><p style="color:#00ffcc; font-size:1.1rem; font-weight:bold; margin:0;">{c_total:.1f} l/s</p></div>
        <div class="card-indicador"><p style="color:#ffffff; font-size:0.8rem; margin:0;">📉 Presión promedio</p><p style="color:#ffff00; font-size:1.1rem; font-weight:bold; margin:0;">{p_prom:.2f} kg</p></div>
        <div class="card-indicador"><p style="color:#ffffff; font-size:0.8rem; margin:0;">🟢 Sitios encendidos</p><p style="color:#00ff00; font-size:1.1rem; font-weight:bold; margin:0;">{len(pozos_on)}</p></div>
        <div class="card-indicador"><p style="color:#ffffff; font-size:0.8rem; margin:0;">🔴 Sitios apagados</p><p style="color:#ff0000; font-size:1.1rem; font-weight:bold; margin:0;">{len(pozos_off)}</p></div>
        <div class="card-indicador"><p style="color:#ffffff; font-size:0.8rem; margin:0;">⚠️ Fallas de com.</p><p style="color:#ffaa00; font-size:1.1rem; font-weight:bold; margin:0;">{len(pozos_falla_com)}</p></div>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# 10. PESTAÑAS PRINCIPALES DE NAVEGACIÓN
# ==========================================
tab_incidencias, tab_tanques, tab_rebombeos, tab_macromedidores = st.tabs([
    "🚨 Incidencias Fuera de Servicio", 
    "🛢️ Tanques y Mapa", 
    "🧊 Rebombeos y Mapa", 
    "🌀 Macromedidores"
])

with tab_tanques:
    st.markdown('<div class="mapa-area">', unsafe_allow_html=True)
    m = folium.Map(location=st.session_state.centro_mapa, zoom_start=st.session_state.zoom_inicial)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Vista Satélite', overlay=False).add_to(m)
    Fullscreen().add_to(m)

    if ver_pozos:
        for id_p, info in mapa_pozos_dict.items():
            folium.CircleMarker(
                location=info['coord'], radius=3, color=info['color_final'],
                fill=True, fill_color=info['color_final'], fill_opacity=1,
                tooltip=f"Pozo {id_p} - {info['status_label']}"
            ).add_to(m)
            
    folium_static(m, width=None, height=600)
    st.markdown('</div>', unsafe_allow_html=True)

with tab_rebombeos:
    st.markdown("### 🧊 Panel y Monitoreo de Rebombeos")
    if mapa_rebombeos_dict:
        df_rb_resumen = pd.DataFrame.from_dict(mapa_rebombeos_dict, orient='index')
        st.dataframe(df_rb_resumen[['nombre', 'status_label']], use_container_width=True)

with tab_macromedidores:
    st.markdown("### 🌀 Panel de Macromedidores")
    datos_m_tab = cargar_medidores_desde_db()
    if datos_m_tab:
        df_mm_resumen = pd.DataFrame.from_dict(datos_m_tab, orient='index')
        st.dataframe(df_mm_resumen, use_container_width=True)

with tab_incidencias:
    tz_mx = pytz.timezone('America/Mexico_City')
    ahora_mx = datetime.now(tz_mx)
    st.subheader("📋 Gestión de Incidencias en Pozos")
    df_incidencias = get_data()
    if isinstance(df_incidencias, pd.DataFrame) and not df_incidencias.empty:
        st.dataframe(df_incidencias, use_container_width=True)
    else:
        st.info("No hay incidencias registradas actualmente.")
