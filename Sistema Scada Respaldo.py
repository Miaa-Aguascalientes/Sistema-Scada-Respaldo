import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from folium.plugins import Fullscreen
from sqlalchemy import create_engine
import psycopg2
import json
import urllib.parse
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import base64
import hashlib
import bcrypt
import time
import urllib.parse
from datetime import datetime, timedelta
import plotly.graph_objects as go
from folium.plugins import MousePosition, LocateControl
from streamlit_folium import st_folium
import locale
from shapely import wkt
import geopandas as gpd
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError
import pytz
from datetime import datetime
from sqlalchemy import create_engine, text
from cryptography.fernet import Fernet
import altair as alt


st.set_page_config(
    page_title="Sistema Scada", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="expanded"
)



# 0.1. INICIALIZACIÓN DE ESTADOS
if "autenticado" not in st.session_state:
  query_params = st.query_params
  if query_params.get("access") == "granted":
    st.session_state.autenticado = True
    st.session_state.rol = query_params.get("role", "usuario")
  else:
    st.session_state.autenticado = False

if "fase_carga" not in st.session_state:
  st.session_state.fase_carga = False

# 0.2. FUNCIONES DE BASE DE DATOS (REFORZADAS)


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


# --- LLAVE DE CIFRADO FIJA Y SEGURA ---
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

    if str(password_input) == pwd_decifrada or str(
        password_input
    ) == str(pwd_almacenada):
      return tipo_usuario

    return None
  except Exception as e:
    st.error(f"Error al consultar usuario: {e}")
    return None


# 0.3. ESTILO VISUAL HUD AJUSTADO
st.markdown(
    """
<style>
    /* Configuración base */
    .stApp { background-color: #050a10 !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header, footer { visibility: hidden !important; }
    
    /* HUD Visual Elements */
    .visual-core { position: relative; width: 480px; height: 480px; margin: auto; }
    .ring { position: absolute; border-radius: 50%; border: 4px solid transparent; animation: spin var(--d) linear infinite; }
    .r1 { width: 100%; height: 100%; border-top: 8px solid #00d4ff; border-bottom: 8px solid #00d4ff; --d: 4s; }
    .r2 { width: 78%; height: 78%; top: 11%; left: 11%; border: 3px dashed #00d4ff; --d: 8s; animation-direction: reverse; }
    .center-logo { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
    .logo-miaa { width: 190px; filter: drop-shadow(0 0 15px #00d4ff); }
    
    /* Login Box */
    .login-box { 
        background: rgba(0, 212, 255, 0.05); 
        border-left: 8px solid #00d4ff; 
        padding: 30px; 
        margin-top: 50px;
        max-width: 320px;
        margin-left: 0;
    }
    
    @keyframes spin { 100% { transform: rotate(360deg); } }
    
    /* --- ESTILO INTEGRADO PARA INPUTS --- */
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
    
    div[data-testid="stTextInputRootElement"]:focus-within {
        border: 1px solid #00d4ff !important;
        box-shadow: none !important;
    }
    
    /* Botones */
    .stButton button { 
        background: #00d4ff !important; 
        color: #050a10 !important; 
        font-weight: bold !important; 
        width: 100%; 
        height: 45px; 
        border: none !important;
        border-radius: 0px !important;
    }
    
    div[data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# 0.4. LÓGICA DE INTERFAZ
if not st.session_state.autenticado:
  col_esp1, col_vis, col_log, col_esp2 = st.columns([0.1, 1.8, 2, 1.1])

  with col_vis:
    st.markdown(
        '<div style="height: 12vh;"></div>', unsafe_allow_html=True
    )
    st.markdown(
        f"""
        <div class="visual-core">
            <div class="ring r1"></div><div class="ring r2"></div>
            <div class="center-logo">
                <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-miaa">
                <h2 style="color:#00d4ff; font-family:Orbitron; font-size:-400px; letter-spacing:5px; margin-top:-35px;"></h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

  with col_log:
    st.markdown(
        '<div style="height: 20vh;"></div>', unsafe_allow_html=True
    )

    if not st.session_state.fase_carga:
      st.markdown('<div class="login-box">', unsafe_allow_html=True)
      st.markdown(
          '<h2 style="color:#00d4ff; font-size:18px;">// INGRESE SUS'
          " CREDENCIALES</h2>",
          unsafe_allow_html=True,
      )

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
      st.markdown(
          '<h2 style="color:#00d4ff; font-size:18px;">// CARGANDO SCADA...</h2>',
          unsafe_allow_html=True,
      )
      prog = st.progress(0)
      status = st.empty()

      tareas = [
          ("Conectando DB", "get_mysql_telemetria_engine"),
          ("Sectores", "cargar_sectores_poligonos"),
          ("Pozos", "cargar_mapa_pozos_desde_db"),
          ("Tanques", "cargar_tanques_desde_db"),
          ("Rebombeos", "cargar_rebombeos_desde_db"),
      ]

      for i, (nombre, func) in enumerate(tareas):
        status.write(f"Cargando {nombre}...")
        if func in globals():
          try:
            globals()[func]()
          except Exception as e:
            st.warning(f"Error en {nombre}: {e}")
        prog.progress((i + 1) / len(tareas))
        time.sleep(0.4)

      st.cache_data.clear()
      st.cache_resource.clear()
      st.session_state.autenticado = True
      st.session_state.rol = st.session_state.temp_rol
      st.session_state.fase_carga = False
      st.rerun()
      st.markdown("</div>", unsafe_allow_html=True)

  st.stop()

# 1.  SECCION---------------------------------------------------------------------------1. CONFIGURACIÓN DE PÁGINA ----------------------------------------------------------------------------------------------------------
params = st.query_params
sector_seleccionado = params.get("sector", None)

if sector_seleccionado:
    titulo_pestaña = f"MIAA - Estado de Sector: {sector_seleccionado}"
else:
    titulo_pestaña = "MIAA - Estado de Pozos"

st.set_page_config(
    page_title=titulo_pestaña, 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide", 
    initial_sidebar_state="expanded"
)
count = st_autorefresh(interval=300000, limit=1000, key="scada_refresh")

# 2.  SECCION------------------------------------------------------------------------------2. FUNCIONES DE CONEXIÓN ------------------------------------------------------------------------------------------------------

from sqlalchemy import create_engine, event # Asegúrate de importar 'event' aquí

# 2.1. Secretos de la base de datos de SCADA
@st.cache_resource
def get_mysql_scada_engine():
    try:
        c = st.secrets["mysql_scada"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}")
        
        # --- AÑADIR ESTE BLOQUE AQUÍ ---
        @event.listens_for(engine, "connect")
        def set_big_selects(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("SET SESSION SQL_BIG_SELECTS=1;")
            cursor.close()
        # -------------------------------
        
        with engine.connect() as conn: pass 
        return engine
    except Exception as e:
        st.error(f"Error al conectar a la BD: {e}")
        return None

# 2.2. Secretos de la base de datos de Telemetria 2
@st.cache_resource
def get_mysql_telemetria_engine():
    try:
        c = st.secrets["mysql_telemetria"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}")
        with engine.connect() as conn: pass 
        return engine
    except: return None

# 2.3. Secretos de la base de datos de POSTGRES
@st.cache_resource
def get_postgres_conn():
    try: 
        # Simplemente crea y retorna el objeto de conexión
        conn = psycopg2.connect(**st.secrets["postgres"])
        return conn
    except Exception as e: 
        st.error(f"Error de conexión Postgres: {e}")
        return None
        
 # 2.4. Funcion para cargar el ultimo dato de SCADA
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
    except Exception as e:
        return {}

# 2.5. Funcion para optener los ultimos 7 dias de valores de SCADA
def obtener_historia_7_dias(tag_name):
    engine = get_mysql_scada_engine()
    if not engine or not tag_name: return pd.DataFrame()
    try:
        query = f"""
            SELECT h.FECHA, h.VALUE 
            FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME = '{tag_name}'
            AND h.FECHA >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            ORDER BY h.FECHA ASC
        """
        df = pd.read_sql(query, engine)
        df['FECHA'] = pd.to_datetime(df['FECHA']) 
        return df
    except:
        return pd.DataFrame()
        
# 2.6. Funcion para optener los poligonos de los sectores y sus demas campos
@st.cache_data(ttl=3600)
def cargar_sectores_poligonos():
    # Obtenemos una conexión fresca
    conn = psycopg2.connect(**st.secrets["postgres"])
    if not conn:
        return []
    try:
        query = """
            SELECT fid,
                   sector,
                   "Pozos_Sector",
                   "Cantidad_Pozos",
                   "AREA",
                   "USUARIOS",
                   "USU_DOM",
                   "POB_2025",
                   "Q_PROD",
                   "VOL_PROD-MES",
                   "LONG_RED",
                   "CONS_PROM",
                   "VOL_FACT",
                   "DOM_A",
                   "DOM_B",
                   "DOM_C",
                   "COMERCIAL",
                   "FALTAS_AGUA",
                   "FUGAS",
                   "DOTACION",
                   "BAL_VOL",
                   "EF",
                   "ANF",
                   "IMP-FACT_US",
                   "PERD_US_MES",
                   "PERD_HAB_DIA",
                   "NIV_MOROSIDAD",
                   "FA_USUARIO",
                   "FUGAS_KM",
                   ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geo
            FROM "Sectorizacion"."sectores_hidr"
        """
        # Leemos los datos
        df = pd.read_sql(query, conn)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Error al cargar sectores: {e}")
        return []
    finally:
        conn.close()

# Función corregida para leer el campo 'geom' directamente
@st.cache_data(ttl=3600)
def get_todas_las_colonias():
    query = """
        SELECT ST_AsText(geom) as geom_wkt, Pozos, Col_atl, Sector, Distrito, Supervisor,
               Pozo_1, Afectacion_1, Pozo_2, Afectacion_2, 
               Pozo_3, Afectacion_3, Pozo_4, Afectacion_4, 
               Pozo_5, Afectacion_5, Pozo_6, Afectacion_6, 
               Pozo_7, Afectacion_7, Pozo_8, Afectacion_8, 
               Pozo_9, Afectacion_9, Pozo_10, Afectacion_10 
        FROM Diccionario_colonias
    """
    try:
        df = pd.read_sql(query, get_mysql_telemetria_engine())
        if not df.empty and df['geom_wkt'].iloc[0] is not None:
            df['geometry'] = df['geom_wkt'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry')
            gdf.set_crs(epsg=32613, inplace=True)
            return gdf.to_crs(epsg=4326)
    except Exception as e:
        st.error(f"Error cargando polígonos: {e}")
    return None

@st.cache_data(ttl=3600)
def get_todos_los_sectores_geo():
    query = """
        SELECT ST_AsText(geom) as geom_wkt, Sector, Pozos, Col_atl,
               Pozo_1, Afectacion_1, Pozo_2, Afectacion_2, 
               Pozo_3, Afectacion_3, Pozo_4, Afectacion_4, 
               Pozo_5, Afectacion_5, Pozo_6, Afectacion_6, 
               Pozo_7, Afectacion_7, Pozo_8, Afectacion_8, 
               Pozo_9, Afectacion_9, Pozo_10, Afectacion_10,
               Pozo_11, Afectacion_11, Pozo_12, Afectacion_12 
        FROM Diccionario_sectores
    """
    try:
        df = pd.read_sql(query, get_mysql_telemetria_engine())
        if not df.empty and 'geom_wkt' in df.columns and df['geom_wkt'].iloc[0] is not None:
            df['geometry'] = df['geom_wkt'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry')
            gdf.set_crs(epsg=32613, inplace=True)
            return gdf.to_crs(epsg=4326)
    except Exception as e:
        st.error(f"Error cargando polígonos de sectores: {e}")
    return None

def _variantes_id_sitio(id_sitio):
    limpio = re.sub(r'\s+', '', str(id_sitio or '').strip().upper())
    if not limpio:
        return []
    variantes = {limpio, limpio.replace('-', '')}
    con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', limpio.replace('-', ''))
    if con_guion:
        variantes.add(con_guion)
    return list(variantes)

def _buscar_incidencia_sitio(id_sitio, dic_incidencias):
    if not dic_incidencias or not id_sitio:
        return None
    for var in _variantes_id_sitio(id_sitio):
        if var in dic_incidencias:
            return dic_incidencias[var]
    return None

@st.cache_data(ttl=60)
def obtener_pozos_con_incidencias_hoy():
    engine = get_mysql_scada_engine()
    if engine is None:
        return {}
    try:
        query = """
            SELECT NUM_POZO, DIAGNOSTICO_FALLA, ESTATUS 
            FROM vw_incidencias_en_pozos 
            WHERE ESTATUS != 'CERRADA'
        """
        df_inc = pd.read_sql(query, engine)
        dic_incidencias = {}
        for _, row in df_inc.iterrows():
            val = row['NUM_POZO']
            if pd.notna(val):
                # Conservamos letras, números y guiones medios (ej. P-087A, R-087, REB01, REB-01)
                id_limpio = str(val).strip().upper()
                if id_limpio:
                    diagnostico = row['DIAGNOSTICO_FALLA'] or 'Sin diagnóstico'
                    for var in _variantes_id_sitio(id_limpio):
                        dic_incidencias.setdefault(var, diagnostico)
        return dic_incidencias
    except Exception as e:
        return {}

def calcular_color_colonia(props, pozos_con_incidencia):
    suma_afectacion = 0.0
    tiene_incidencia_activa = False
    
    for i in range(1, 11):
        pozo_col = props.get(f'Pozo_{i}')
        afectacion_col = props.get(f'Afectacion_{i}')
        
        if pozo_col is not None and str(pozo_col).strip():
            if _buscar_incidencia_sitio(pozo_col, pozos_con_incidencia) is not None:
                tiene_incidencia_activa = True
                if pd.notna(afectacion_col):
                    try:
                        val_str = str(afectacion_col).replace('%', '').strip()
                        val_afect = float(val_str)
                        suma_afectacion += val_afect
                    except:
                        pass

    if not tiene_incidencia_activa:
        return '#3498DB', 0  # Azul para colonias sin afectación activa

    if tiene_incidencia_activa and suma_afectacion == 0:
        return '#FFA500', 1  

    # Rangos de color según la afectación acumulada total
    if 76 <= suma_afectacion <= 100:
        return '#FF0000', suma_afectacion  # Rojo
    elif 51 <= suma_afectacion <= 75:
        return '#FFFF00', suma_afectacion  # Amarillo
    elif 31 <= suma_afectacion <= 50:
        return '#FFA500', suma_afectacion  # Naranja
    elif 1 <= suma_afectacion <= 30:
        return '#69ADDD', suma_afectacion  # Azul claro
    else:
        return '#FF0000', suma_afectacion  # Por si supera el 100%

def calcular_color_sector(props, pozos_con_incidencia):
    suma_afectacion = 0.0
    tiene_incidencia_activa = False
    
    for i in range(1, 13):
        pozo_col = props.get(f'Pozo_{i}')
        afectacion_col = props.get(f'Afectacion_{i}')
        
        if pozo_col is not None and str(pozo_col).strip():
            if _buscar_incidencia_sitio(pozo_col, pozos_con_incidencia) is not None:
                tiene_incidencia_activa = True
                if pd.notna(afectacion_col):
                    try:
                        val_str = str(afectacion_col).replace('%', '').strip()
                        val_afect = float(val_str)
                        suma_afectacion += val_afect
                    except:
                        pass

    # Colores exactamente iguales a los de las colonias:
    if not tiene_incidencia_activa:
        return '#3498DB', 0  # Azul estándar para sectores sin afectación

    if tiene_incidencia_activa and suma_afectacion == 0:
        return '#FFA500', 1  

    if 76 <= suma_afectacion <= 100:
        return '#FF0000', suma_afectacion  # Rojo
    elif 51 <= suma_afectacion <= 75:
        return '#FFFF00', suma_afectacion  # Amarillo
    elif 31 <= suma_afectacion <= 50:
        return '#FFA500', suma_afectacion  # Naranja
    elif 1 <= suma_afectacion <= 30:
        return '#69ADDD', suma_afectacion  # Azul Claro
    else:
        return '#FF0000', suma_afectacion

# 2.7. Funcion para cambiar el formato de horas
def formato_hora(decimal):
    try:
        if decimal == "N/A" or decimal is None: return "00:00"
        horas = int(float(decimal))
        minutos = int((float(decimal) - horas) * 60)
        return f"{horas:02d}:{minutos:02d}"
    except:
        return "00:00"

# 2.8. Funcion para el color de los sectores
def get_blink_icon(color):
    return f"""
    <div style="
        width: 8px; height: 8px; 
        background-color: {color}; 
        border-radius: 50%; 
        box-shadow: 0 0 8px {color};
        animation: blinker 1s linear infinite;">
    </div>
    <style>
    @keyframes blinker {{ 50% {{ opacity: 0.2; }} }}
    </style>
    """

# 3. SECCION -------------------------------------------------------------------------------- 3. CARGA DE DATOS DE DICCIONARIOS -------------------------------------------------------------------------------------------

# 3.1 Funcion para optener la base de datos Diccionario_de_pozos  
@st.cache_data(ttl=3600) 
def cargar_mapa_pozos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        query = "SELECT * FROM Diccionario_de_pozos"
        df_pozos = pd.read_sql(query, engine)
        
        nuevo_mapa = {}
        for _, row in df_pozos.iterrows():
            try:
                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                coords = (lat, lon)
            except: continue

            nuevo_mapa[row['Pozos']] = {
                "coord": coords,
                "bomba": row['bomba'],
                "caudal": row['caudal'],
                "presion": row['presion'],
                "sumergencia": row['sumergencia'],
                "nivel_dinamico": row['nivel_dinamico'],
                "nivel_tanque": row['nivel_tanque'],
                "columna": row['columna'],
                "h_arranque": row['H_arranque'],
                "h_paro": row['H_paro'],
                "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']],
                "totalizado": row['totalizado']
            }
        return nuevo_mapa
    except:
        return {}

# 3.2. Funcion para optener la base de datos Diccionario_de_tanques
@st.cache_data(ttl=3600)
def cargar_tanques_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        query = "SELECT * FROM Diccionario_de_tanques"
        df_tq = pd.read_sql(query, engine)
        
        nuevo_mapa_tq = {}
        for _, row in df_tq.iterrows():
            try:

                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                
                n_max = float(row['Nivel_max']) if row.get('Nivel_max') is not None else 1.0
                if n_max <= 0: n_max = 1.0

                nuevo_mapa_tq[row['TQ']] = {
                    "nombre": row['Nombre_tq'],
                    "coord": (lat, lon),
                    "tag_nivel": row['nivel_tanque'],
                    "nivel_max": n_max,
                    "sitios": row['Sitios']
                }
            except: continue
        return nuevo_mapa_tq
    except: return {}
        
# 3.3. Funcion para optener la base de datos Diccionario_de_rebombeos
@st.cache_data(ttl=3600)
def cargar_rebombeos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        query = "SELECT * FROM Diccionario_de_rebombeos"
        df_rb = pd.read_sql(query, engine)
        
        nuevo_mapa_rb = {}
        for _, row in df_rb.iterrows():
            try:
                coords_str = str(row['coord']).strip().replace('(', '').replace(')', '')
                lat, lon = map(float, coords_str.split(','))
                
                nuevo_mapa_rb[row['Rebombeo']] = {
                    "nombre": row['Nombre_rebombeo'],
                    "coord": (lat, lon),
                    "telemetria": row['Telemetria'],
                    "presion": row['presion'],
                    "nivel_tanque": row['nivel_tanque'],
                    "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                    "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']]
                }
            except: continue
        return nuevo_mapa_rb
    except: return {}

# 3.4. Funcion para optener los puntos de control de la base de datos Diccionario_puntos_de_control
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
                
                # Obtenemos la serie
                id_reg_val = r.get('Serie', r.get('Registrador', 'ID'))
                
                d_res[str(id_reg_val)] = {
                    "nombre": str(r.get('Domicilio', r.get('Nombre_registrador', 'S/N'))),
                    "coord": [float(lat_s), float(lon_s)],
                    "sector": str(r['Sector']).split('.')[0].strip(),
                    "tag_p1": r.get('Presion_1'), 
                    "tag_p2": r.get('Presion_2'), 
                    "tag_q": r.get('Caudal'),     
                    "tag_vbat": r.get('bateria'), 
                    "tag_idx": r.get('indice'),
                    # --- CRUCIAL: Agregamos la Serie aquí para que el marcador la vea ---
                    "Serie": str(id_reg_val) 
                }
            except Exception as e:
                continue
        return d_res
    except Exception as e:
        return {}

# 3.5. Funcion para optener los puntos de criticos de la base de datos Diccionario_puntos_criticos
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
                
                # CORRECCIÓN AQUÍ: Guardar explícitamente 'Domicilio'
                d_res[str(id_reg)] = {
                    "nombre": str(r.get('Colonia', 'S/C')), # Usamos Colonia para el nombre interno
                    "Domicilio": str(r.get('Domicilio', 'Sin Domicilio')), # <--- CLAVE NUEVA
                    "coord": [float(lat_s), float(lon_s)],
                    "sector": str(r['Sector']).split('.')[0].strip(),
                    "tag_p1": r.get('Presion_1'),
                    "tag_q": r.get('Caudal'),        
                }
            except Exception as e:
                continue
        return d_res
    except Exception as e:
        return {}
        
# 3.4. Funcion para optener las valvulas reductoras de presion de la base de datos Diccionario_vrp
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
                
                # Obtenemos el valor de la serie
                id_val = r.get('Serie', 'ID_VRP')
                
                d_res[str(id_val)] = {
                    "nombre": str(r.get('Domicilio', 'S/N')),
                    "coord": [float(lat_s), float(lon_s)],
                    "sector": str(r['Sector']).split('.')[0].strip(),
                    "tag_p1": r.get('Presion_1'),
                    "tag_p2": r.get('Presion_2'),
                    "tag_q": r.get('Caudal'),
                    # --- AGREGAMOS ESTA LÍNEA ---
                    "Serie": str(id_val)
                }
            except: continue
        return d_res
    except: return {}

# 3.5. Funcion para optener los macromedidores desde la base de datos

@st.cache_data(ttl=3600)
def cargar_medidores_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        # Consulta modificada para obtener la fecha más reciente por medidor
        # Agrupamos por Medidor para obtener el último registro de cada uno
        query = """
            SELECT Medidor, Nombre, Lat, Lon, Flujo, Presion, Consumo, MAX(FECHA) as UltimaFecha 
            FROM MACROMEDIDORES 
            GROUP BY Medidor
        """
        df = pd.read_sql(query, engine)
        
        datos_medidores = {}
        for _, row in df.iterrows():
            datos_medidores[row['Medidor']] = {
                "nombre": row['Nombre'],
                "coord": (float(row['Lat']), float(row['Lon'])),
                "flujo": row['Flujo'],
                "presion": row['Presion'],
                "consumo": row['Consumo'],
                "ultima_fecha": pd.to_datetime(row['UltimaFecha']) # Convertimos a formato fecha
            }
        return datos_medidores
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return {}
        
# 3.6. Funcion para optener las incidencias
@st.cache_data(ttl=60)
def get_data():
    engine = get_mysql_scada_engine()
    
    if engine is None:
        st.error("No se pudo establecer conexión.")
        return pd.DataFrame()
        
    try:
        # AQUÍ ES DONDE AGREGAS TODOS LOS CAMPOS QUE QUIERAS TRAER
        query = """
            SELECT NUM_POZO, COLONIA, FECHA_HORA_INICIO, FECHA_HORA_FIN, 
                   DIAGNOSTICO_FALLA, TIEMPO_ESTIMADO_ATENCION, RESPONSABLE, ESTATUS 
            FROM vw_incidencias_en_pozos 
            ORDER BY FECHA_HORA_INICIO DESC
        """
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()
        
# 3.7. Funcion para optener las colonias del diccionario de colonias        
@st.cache_data(ttl=60)
def get_diccionario_completo():
    try:
        # Asegúrate de que get_engine_telemetria() esté disponible en tu archivo
        query = "SELECT Pozos, Col_atl, Sector, Distrito, Supervisor, ST_AsText(geom) as geom_wkt FROM Diccionario_colonias"
        return pd.read_sql(query, get_mysql_telemetria_engine())
    except Exception as e:
        st.error(f"Error en get_diccionario_colonias: {e}")
        return pd.DataFrame()
        
# 3.8. Funcion para optener las colonias del diccionario de colonias
@st.cache_data(ttl=60)
def get_geometries(num_pozo):
    numero_limpio = re.sub(r'\D', '', str(num_pozo))
    busqueda = numero_limpio if numero_limpio else str(num_pozo)
    
    # La consulta ya trae los campos, vamos a asegurarnos de que no se pierdan
    query = f"""
    SELECT ST_AsText(geom) as geom_wkt, Col_atl, Sector, Distrito, Supervisor 
    FROM Diccionario_colonias 
    WHERE Pozos LIKE '%%{busqueda}%%'
    """
    
    try:
        df = pd.read_sql(query, get_mysql_telemetria_engine())
        if not df.empty and df['geom_wkt'].iloc[0] is not None:
            df['geometry'] = df['geom_wkt'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry')
            gdf.set_crs(epsg=32613, inplace=True)
            # Retornamos el gdf con las columnas intactas
            return gdf.to_crs(epsg=4326)
    except Exception as e:
        st.error(f"Error en BD: {e}")
    return None

# 4. SECCION -------------------------------------------------------------------------------- 4. GRAFICAR LOS TANQUES EN EL POPUP --------------------------------------------------------------------
params = st.query_params
tag_a_graficar = params.get("graficar_tanque", None)
nombre_tq = params.get("nombre", "Tanque")

if tag_a_graficar:
    import datetime
    import plotly.express as px
    import pandas as pd
    import plotly.graph_objects as go
    
    st.title(f"📊 Análisis de Nivel: {nombre_tq}")
    
    # 4.1. FILTROS DE FECHA ---
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        opcion_fecha = st.selectbox(
            "Selecciona un rango:",
            ["Hoy", "Esta Semana", "Últimos 14 días", "Este Mes", "Personalizado"],
            index=3, # <--- CAMBIO: Ahora selecciona 'Últimos 14 días' por defecto
            key="pop_selector_final_v8"
        )

    hoy = datetime.date.today()
    
    # 4.2. Lógica de selección de fechas
    if opcion_fecha == "Hoy":
        fecha_inicio = hoy
        fecha_fin = hoy
    elif opcion_fecha == "Esta Semana":
        fecha_inicio = hoy - datetime.timedelta(days=hoy.weekday())
        fecha_fin = hoy
    elif opcion_fecha == "Últimos 14 días":
        fecha_inicio = hoy - datetime.timedelta(days=14)
        fecha_fin = hoy
    elif opcion_fecha == "Este Mes":
        fecha_inicio = hoy.replace(day=1)
        fecha_fin = hoy
    else: 
        with col_f2:
            rango = st.date_input("Periodo:", value=(hoy - datetime.timedelta(days=7), hoy), max_value=hoy, key="pop_cal_v8")
            fecha_inicio, fecha_fin = rango if isinstance(rango, tuple) and len(rango)==2 else (hoy, hoy)

    # 4.3. CONSULTA A LA BASE DE DATOS
    try:
        engine = get_mysql_scada_engine()
        f_desde = f"{fecha_inicio} 00:00:00"
        f_hasta = f"{fecha_fin} 23:59:59"
        
        query = f"""
            SELECT h.FECHA, h.VALUE 
            FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME = '{tag_a_graficar}'
            AND h.FECHA BETWEEN '{f_desde}' AND '{f_hasta}'
            ORDER BY h.FECHA ASC
        """
        
        df_hist = pd.read_sql(query, engine)

        if not df_hist.empty:
            df_hist['FECHA'] = pd.to_datetime(df_hist['FECHA'])
            df_hist['VALUE'] = df_hist['VALUE'].round(2)
            
            # 4.4. CREACIÓN DEL GRÁFICO DE ÁREA DESVANECIDA
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=df_hist['FECHA'],
                y=df_hist['VALUE'],
                mode='lines+markers',
                line=dict(color='#00d4ff', width=2),
                marker=dict(size=4, color='#00d4ff'),
                fill='tozeroy',
                fillcolor='rgba(0, 212, 255, 0.2)', # Efecto desvanecido
                hovertemplate="<b>%{y:.2f} m</b><extra></extra>"
            ))

            # 1. Definimos las fechas de tus líneas y el diccionario de traducción
            dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
            meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 
                        7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
            fechas_lineas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')

            # 2. Lógica de filtrado dinámico para evitar amontonamiento
            # Si seleccionas muchos días, mostramos solo una etiqueta cada X días
            num_dias = len(fechas_lineas)
            if num_dias > 15:
                paso = 2 if num_dias <= 30 else 5  # Muestra cada 2 días o cada 5
            else:
                paso = 1
            
            # Aplicamos el filtro al rango
            ticks_filtrados = fechas_lineas[::paso]

            # 3. Construimos etiquetas solo para los ticks filtrados
            etiquetas_filtradas = [
                f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                for d in ticks_filtrados
            ]

            # 4. CONFIGURACIÓN DEL EJE X
            fig.update_xaxes(
                tickvals=ticks_filtrados,
                ticktext=etiquetas_filtradas,
                tickangle=0,
                automargin=True,
                showspikes=True,
                spikecolor="gray",
                spikethickness=1,
                spikemode="across",
                spikesnap="cursor",
                spikedash="dash",
                showgrid=True,
                gridcolor='#333'
            )

            fig.update_layout(
                template="plotly_dark",
                hovermode="x unified",
                xaxis_title="Fecha y Hora",
                yaxis_title="Nivel (m)",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=600,
                # --- CONFIGURACIÓN DEL EJE X CON RANGE SLIDER ---
                xaxis=dict(
                    rangeslider=dict(
                        visible=True,
                        thickness=0.08
                    ),
                    type="date",
                    showgrid=True,
                    gridcolor='#333'
                ),
                yaxis=dict(
                    tickformat=".2f",
                    showgrid=True,
                    gridcolor='#333'
                ),
                hoverlabel=dict(
                    bgcolor="#1f2c38",
                    font_size=12
                )
            )

            dias_intermedios = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
            
            for dia in dias_intermedios:
                es_lunes = dia.weekday() == 0
                
                # 1. El sombreado gris (la "sombra" detrás de la línea)
                # Usamos un ancho fijo (delta) para que sea una franja pequeña
                delta = pd.Timedelta(hours=1) # Ajusta este valor para hacer la sombra más ancha o angosta
                
                fig.add_vrect(
                    x0=dia - delta,
                    x1=dia + delta,
                    fillcolor="gray",
                    opacity=0.2, # Ajusta esta opacidad para que sea más clara o más oscura
                    layer="below",
                    line_width=0
                )
                
                # 2. La línea punteada encima
                fig.add_vline(
                    x=dia, 
                    line_width=1.5,
                    line_dash="dash",
                    line_color="yellow" if es_lunes else "white",
                    opacity=0.5,
                    layer="above"
                )
                
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("Ver tabla de datos detallada"):
                st.dataframe(
                    df_hist[['FECHA', 'VALUE']].sort_values(by='FECHA', ascending=False), 
                    use_container_width=True
                )
        else:
            st.warning(f"No hay datos registrados desde el {f_desde} hasta el {f_hasta}")
            
    except Exception as e:
        st.error(f"Error en la consulta: {e}")
    
    st.stop()

# 4.6. SECCION -------------------------------------------------------------------------------- 5. GRAFICAR LOS POZOS --------------------------------------------------------------------

from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

params = st.query_params

if "graficar_pozo" in params:
    id_pozo_graf = params["graficar_pozo"]
    nombre_pozo = params.get("nombre", id_pozo_graf)
    
    mapa_pozos_dict = cargar_mapa_pozos_desde_db()
    pozo_info = mapa_pozos_dict.get(id_pozo_graf)

    if not pozo_info:
        st.error(f"❌ No se encontró configuración para el pozo: {id_pozo_graf}")
        st.stop()

    cabecera_placeholder = st.empty()
    
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        opcion_fecha = st.selectbox(
            "Rango de tiempo:", 
            ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 3 meses", "Últimos 6 meses", "Personalizado"], 
            index=4, 
            key="fecha_pozo_v8"
        )

    hoy_dt = datetime.now()
# Definimos medianoche como base para todas las comparaciones
    medianoche = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    f_fin = hoy_dt # Por defecto hasta el momento actual

    if opcion_fecha == "Hoy":
        f_ini = medianoche
    elif opcion_fecha == "Ayer":
        f_ini = (medianoche - timedelta(days=1))
        f_fin = medianoche - timedelta(seconds=1)
    elif opcion_fecha == "Últimos 7 días":
        f_ini = (medianoche - timedelta(days=7))
    elif opcion_fecha == "Últimos 14 días":
        f_ini = (medianoche - timedelta(days=14))
    elif opcion_fecha == "Este Mes":
        f_ini = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Último Mes":
        f_ini = (hoy_dt.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        f_fin = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    elif opcion_fecha == "Últimos 3 meses":
        f_ini = (medianoche - timedelta(days=90))    
    elif opcion_fecha == "Últimos 6 meses":
        f_ini = (medianoche - timedelta(days=180))
    elif opcion_fecha == "Personalizado":
        with col_f2:
            rango = st.date_input("Selecciona el periodo:", value=(hoy_dt.date() - timedelta(days=7), hoy_dt.date()), max_value=hoy_dt.date())
        if isinstance(rango, (list, tuple)) and len(rango) == 2:
            f_ini = datetime.combine(rango[0], datetime.min.time())
            f_fin = datetime.combine(rango[1], datetime.max.time())
        else:
            st.info("Selecciona el rango.")
            st.stop()

    tag_totalizado = str(pozo_info.get('totalizado', '')).strip()
    tag_caudal_real = pozo_info.get('caudal', '')
    tag_nivel_tanque = pozo_info.get('nivel_tanque', '')
    tag_presion_real = pozo_info.get('presion', '')
    tag_nivel_dinamico = pozo_info.get('nivel_dinamico', '')
    tag_sumergencia = pozo_info.get('sumergencia', '')
    tags_voltaje = [t for t in pozo_info.get('voltajes_l', []) if t and t != 'N/A']
    tags_amperaje = [t for t in pozo_info.get('amperajes_l', []) if t and t != 'N/A']
    
    config_visual = [
        ('caudal', "Caudal (Lps)", 'y', '#00d4ff'), 
        ('nivel_tanque', "Nivel Tanque (m)", 'y5', '#00ffcc'),
        ('presion', "Presión (Kg/cm²)", 'y2', '#00ff00'),
        ('nivel_dinamico', "Nivel Dinámico (m)", 'y3', '#ff00b4'),
        ('sumergencia', "Sumergencia (m)", 'y3', '#a800ff')
    ]
    
    for i, t in enumerate(pozo_info.get('voltajes_l', [])):
        if t and t != 'N/A': config_visual.append((t, f"V L{i+1}", 'y4', '#fffb00'))
    for i, t in enumerate(pozo_info.get('amperajes_l', [])):
        if t and t != 'N/A': config_visual.append((t, f"Amp L{i+1}", 'y4', '#ff8000'))

    tags_grafico = []
    for item in config_visual:
        real_t = pozo_info.get(item[0], item[0])
        if real_t and real_t != 'N/A': tags_grafico.append({'tag': real_t, 'label': item[1], 'axis': item[2], 'color': item[3]})
    
    tags_query = [t['tag'] for t in tags_grafico]
    if tag_totalizado and tag_totalizado != 'N/A': tags_query.append(tag_totalizado)

    if tags_query:
        try:
            engine = get_mysql_scada_engine()
            lista_tags_str = f"','".join(list(set(tags_query)))
            
            q = f"""
                SELECT r.NAME as TagName, h.VALUE, h.FECHA 
                FROM vfitagnumhistory h 
                JOIN VfiTagRef r ON h.GATEID = r.GATEID 
                WHERE r.NAME IN ('{lista_tags_str}') 
                AND h.FECHA BETWEEN '{f_ini}' AND '{f_fin}'
            """
            df = pd.read_sql(q, engine)
            df['FECHA'] = pd.to_datetime(df['FECHA'])
            df = df.sort_values('FECHA', ascending=True)

            # --- CORRECCIÓN LÓGICA AQUÍ ---
            if df.empty:
                # Si está vacío, mostramos el aviso y salimos de esta parte
                st.warning(f"⚠️ No hay registros disponibles para el rango seleccionado.")
                
            else:
                # --- LÓGICA DE INDICADORES (Solo se ejecuta si hay datos) ---
                val_vol, val_cau_prom, val_pre_prom = "0.00", "0.00", "0.00"
                val_v_prom, val_a_prom = "0.00", "0.00"
                val_nd_prom, val_sum_prom, val_nt_prom = "0.00", "0.00", "0.00"
                val_nt_ultimo = "0.00"

                if tag_totalizado in df['TagName'].values:
                    df_tot = df[df['TagName'] == tag_totalizado].sort_values('FECHA')
                    if len(df_tot) >= 2:
                        consumo_neta = float(df_tot['VALUE'].iloc[-1]) - float(df_tot['VALUE'].iloc[0])
                        val_vol = f"{consumo_neta:,.2f}"
                    
                
                if tag_caudal_real in df['TagName'].values:
                    val_cau_prom = f"{df[df['TagName'] == tag_caudal_real]['VALUE'].mean():,.2f}"
                if tag_nivel_tanque in df['TagName'].values:
                    df_nt = df[df['TagName'] == tag_nivel_tanque].sort_values('FECHA')
                    val_nt_ultimo = f"{df_nt['VALUE'].iloc[-1]:,.2f}"
                if tag_presion_real in df['TagName'].values:
                    val_pre_prom = f"{df[df['TagName'] == tag_presion_real]['VALUE'].mean():,.2f}"
                if tag_nivel_dinamico in df['TagName'].values:
                    val_nd_prom = f"{df[df['TagName'] == tag_nivel_dinamico]['VALUE'].mean():,.2f}"
                if tag_sumergencia in df['TagName'].values:
                    val_sum_prom = f"{df[df['TagName'] == tag_sumergencia]['VALUE'].mean():,.2f}"
                if tags_voltaje:
                    val_v_prom = f"{df[df['TagName'].isin(tags_voltaje)]['VALUE'].mean():,.1f}"
                if tags_amperaje:
                    val_a_prom = f"{df[df['TagName'].isin(tags_amperaje)]['VALUE'].mean():,.1f}"

# ----------------------- RENDER CABECERA INDICADORES EN TARGETAS DEL POZO ---------------------------------------------------------------------------------------------
            cabecera_placeholder.markdown(f"""
<div style="display: flex; align-items: center; gap: 20px; margin-bottom: 25px; border-bottom: 1px solid #333; padding-bottom: 15px;">
    <h1 style="margin: 0; font-size: 32px; color: white; white-space: nowrap;">Sitio: <span style="color:#00d4ff;">{nombre_pozo}</span></h1>
    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <div style="padding: 12px 18px; background: rgba(0, 212, 255, 0.05); border: 2px solid #00d4ff; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Caudal Promedio</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_cau_prom} <small style="font-size: 12px; color: #00d4ff;">Lps</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(0, 212, 255, 0.05); border: 2px solid #00d4ff; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Volumen</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_vol} <small style="font-size: 12px; color: #00d4ff;">m³</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(0, 255, 0, 0.05); border: 2px solid #00ff00; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Presión Promedio</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_pre_prom} <small style="font-size: 12px; color: #00ff00;">Kg/cm²</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(0, 255, 204, 0.05); border: 2px solid #00ffcc; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Nivel Tanque</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_nt_ultimo} <small style="font-size: 12px; color: #00ffcc;">m</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(255, 0, 180, 0.05); border: 2px solid #ff00b4; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Nivel Dinámico</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_nd_prom} <small style="font-size: 12px; color: #ff00b4;">m</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(168, 0, 255, 0.05); border: 2px solid #a800ff; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Sumergencia</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_sum_prom} <small style="font-size: 12px; color: #a800ff;">m</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(255, 251, 0, 0.05); border: 2px solid #fffb00; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Voltaje Prom</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_v_prom} <small style="font-size: 12px; color: #fffb00;">Volt</small></span>
        </div>
        <div style="padding: 12px 18px; background: rgba(255, 128, 0, 0.05); border: 2px solid #ff8000; border-radius: 12px; min-width: 130px; text-align: center;">
            <span style="color: #888; font-size: 13px; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 6px;">Amperaje Prom</span>
            <span style="color: white; font-size: 24px; font-weight: bold;">{val_a_prom} <small style="font-size: 12px; color: #ff8000;">Amp</small></span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------- PESTAÑA DE VOLÚMENES Y GRAFICO DE BARRAS DE VOLUMEN TOTALIZADO ------------------------------------------------------------------------------
            with st.expander("📅 Análisis de volumen real", expanded=False):
                if tag_totalizado and tag_totalizado != 'N/A':
                    curr_year = datetime.now().year
                    q_hist = f"""
                        SELECT YEAR(h.FECHA) as anio, MONTH(h.FECHA) as mes, h.VALUE, h.FECHA 
                        FROM vfitagnumhistory h 
                        JOIN VfiTagRef r ON h.GATEID = r.GATEID 
                        WHERE r.NAME = '{tag_totalizado}' 
                        AND h.FECHA >= DATE_SUB(NOW(), INTERVAL 24 MONTH)
                        ORDER BY h.FECHA ASC
                    """
                    df_h = pd.read_sql(q_hist, engine)

                    if not df_h.empty:
                        res_meses = df_h.groupby(['anio', 'mes'])['VALUE'].first().reset_index()
                        res_meses = res_meses.sort_values(['anio', 'mes'])
                        
                        # Calculamos la diferencia entre el valor del mes actual y el mes siguiente
                        res_meses['produccion_neta'] = res_meses['VALUE'].shift(-1) - res_meses['VALUE']
                        
                        nombres_meses = {1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic'}
                        res_meses['Mes_Txt'] = res_meses['mes'].map(nombres_meses)

                        curr_year = datetime.now().year
                        res_meses = res_meses[res_meses['anio'].isin([curr_year, curr_year - 1])]
                        
                        # Eliminamos el último registro (el mes actual) que no tiene producción cerrada
                        res_meses = res_meses.dropna(subset=['produccion_neta'])

                        col_g, col_t = st.columns([2, 1])
                        with col_g:
                            fig_hist = go.Figure()
                            for an in sorted(res_meses['anio'].unique()):
                                df_a = res_meses[res_meses['anio'] == an].sort_values('mes')
                                fig_hist.add_trace(go.Bar(
                                    x=df_a['Mes_Txt'], 
                                    y=df_a['produccion_neta'], 
                                    name=f'Año {an}', 
                                    marker_color='#00d4ff' if an == curr_year else 'rgba(150,150,150,0.4)',
                                    hovertemplate='%{x}<br>Volumen: %{y:,.2f}<extra></extra>'
                                ))
                            fig_hist.update_layout(
                                template="plotly_dark",
                                barmode='group',
                                height=350,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                yaxis=dict(tickformat=',.0f')
                            )
                            st.plotly_chart(fig_hist, use_container_width=True)

                        with col_t:
                            pivot = res_meses.pivot(index='mes', columns='anio', values='produccion_neta').sort_index(ascending=True)
                            pivot.index = [nombres_meses[m] for m in pivot.index]
                            st.dataframe(pivot.style.format("{:,.0f}"), use_container_width=True)
                    else: st.info("Sin datos.")

            # ------------------------ PROCESAMIENTO GRAFICO DE VARIABLES DEL POZO -------------------------------------------------------------------------------------------------------------------
            if not df.empty:
                df['FECHA'] = pd.to_datetime(df['FECHA'])
                
                eje_tiempo_global = sorted(df['FECHA'].unique())
                df_interactivo = pd.DataFrame({'FECHA_INDEX': eje_tiempo_global})
                
                fig_line = go.Figure()
                
                for t in tags_grafico:
                    dft_l = df[df['TagName'] == t['tag']].sort_values('FECHA').copy()

                    if len(dft_l) <= 3:
                        continue
                    
                    if dft_l.empty:
                        fecha_limite = f_ini - timedelta(days=30)
                        q_ultimo = f"""
                            SELECT r.NAME as TagName, h.VALUE, h.FECHA 
                            FROM vfitagnumhistory h 
                            JOIN VfiTagRef r ON h.GATEID = r.GATEID 
                            WHERE r.NAME = '{t['tag']}' 
                            AND h.FECHA BETWEEN '{fecha_limite}' AND '{f_ini}'
                            ORDER BY h.FECHA DESC 
                            LIMIT 1
                        """
                        df_ultimo_reg = pd.read_sql(q_ultimo, engine)
                        
                        if not df_ultimo_reg.empty:
                            df_ultimo_reg['FECHA'] = pd.to_datetime(df_ultimo_reg['FECHA'])
                            dft_l = df_ultimo_reg
                        else:
                            dft_l = pd.DataFrame([{
                                'TagName': t['tag'],
                                'VALUE': 0.0,
                                'FECHA': pd.to_datetime(f_ini)
                            }])

                    # 1. GEOMETRÍA VISUAL REAL
                    fig_line.add_trace(
                        go.Scatter(
                            x=dft_l['FECHA'], 
                            y=dft_l['VALUE'], 
                            name=t['label'], 
                            mode='lines+markers',
                            line=dict(color=t['color'], width=2.2),
                            marker=dict(size=4, symbol='circle'),
                            yaxis=t['axis'],
                            showlegend=True,
                            hoverinfo="skip"
                        )
                    )
                    
                    dias_es = {'Mon': 'Lun', 'Tue': 'Mar', 'Wed': 'Mié', 'Thu': 'Jue', 'Fri': 'Vie', 'Sat': 'Sáb', 'Sun': 'Dom'}
                    meses_es = {'Jan': 'Ene', 'Feb': 'Feb', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'May', 'Jun': 'Jun', 
                                'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Sep', 'Oct': 'Oct', 'Nov': 'Nov', 'Dec': 'Dic'}

                    # 2. PROCESAMIENTO DE FECHA TRADUCIDA
                    # En lugar de solo strftime, transformamos el formato al vuelo
                    def traducir_fecha(d):
                        dia_nom = dias_es.get(d.strftime('%a'), d.strftime('%a'))
                        mes_nom = meses_es.get(d.strftime('%b'), d.strftime('%b'))
                        return f"{dia_nom} {d.day}-{mes_nom} {d.strftime('%H:%M:%S')}"

                    # Aplicamos la traducción a la columna antes del merge
                    dft_l['HORA_TRADUCIDA'] = dft_l['FECHA'].apply(traducir_fecha)
                    
                    df_tag_maestro = pd.merge_asof(
                        df_interactivo, 
                        dft_l, 
                        left_on='FECHA_INDEX', 
                        right_on='FECHA', 
                        direction='backward'
                    )
                    df_tag_maestro['VALUE'] = df_tag_maestro['VALUE'].bfill()
                    # Usamos la columna traducida
                    df_tag_maestro['HORA_TRADUCIDA'] = df_tag_maestro['HORA_TRADUCIDA'].bfill()
                    
                    # 3. TRAZA DE HOVER (Aquí no cambias nada más, el customdata ya lleva el texto en español)
                    fig_line.add_trace(
                        go.Scatter(
                            x=df_interactivo['FECHA_INDEX'],
                            y=df_tag_maestro['VALUE'],
                            name=t['label'],
                            mode='lines',
                            line=dict(color=t['color'], width=0.01), 
                            yaxis=t['axis'],
                            showlegend=False,
                            customdata=df_tag_maestro['HORA_TRADUCIDA'].tolist(), # <--- YA VA TRADUCIDO
                            hovertext=df_tag_maestro['VALUE'].tolist(),
                            hovertemplate=f"<span style='color:{t['color']};'>■</span> <b>{t['label']}</b>: %{{hovertext:,.2f}} <span style='color:#888; font-size:11px;'>(%{{customdata}})</span><extra></extra>",
                            hoverlabel=dict(
                                bordercolor=t['color']
                            )
                        )
                    )

                # 1. GENERACIÓN DE ETIQUETAS Y FECHAS (BLOQUE DE APOYO)
                dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 
                            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                fechas_lineas = pd.date_range(start=f_ini, end=f_fin, freq='D')
                num_dias = len(fechas_lineas)
                paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
                ticks_filtrados = fechas_lineas[::paso]

                etiquetas_filtradas = [
                    f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                    for d in ticks_filtrados
                ]

                # 2. DIBUJO DE LÍNEAS CON SOMBRA (VRECT + VLINE)
                delta = pd.Timedelta(hours=0.15) # Ancho del halo detrás de la línea
                for d in fechas_lineas:
                    es_lunes = (d.dayofweek == 0)
                    
                    # Sombra (vrect)
                    fig_line.add_vrect(
                        x0=d - delta,
                        x1=d + delta,
                        fillcolor="gray",
                        opacity=0.2,
                        layer="below",
                        line_width=0
                    )
                    
                    # Línea punteada principal (vline)
                    fig_line.add_vline(
                        x=d, 
                        line_width=1.5, 
                        line_dash="dash", 
                        line_color="#fffb00" if es_lunes else "white",
                        opacity=0.5,
                        layer="above"
                    )

                # 3. CONFIGURACIÓN DEL EJE X
                fig_line.update_layout(
                    template="plotly_dark", 
                    height=580, 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    plot_bgcolor='rgba(0,0,0,0)', 
                    
                    # Mantiene el estado del gráfico al interactuar
                    uirevision='constant', 
                    hovermode="x unified", 
                    legend=dict(orientation="h", y=1.08),
                    
                    xaxis=dict(
                    title=dict(text="<b>Tiempo</b>"),
                    domain=[0.07, 0.91],
                    tickangle=0,
                    showline=False,
                    autorange=True,
                    showspikes=True,
                    spikethickness=1,
                    spikedash="dash",
                    spikemode="across",
                    spikecolor="rgba(255, 255, 255, 0.6)",
                    # Configuración para mostrar día y hora automáticamente
                    tickformatstops=[
                    dict(dtickrange=[None, 86400000], value="%H:%M <br>%A %d-%b-%Y"),
                    dict(dtickrange=[86400000, 604800000], value="%H:%M <br>%A %d-%b-%Y"),
                    dict(dtickrange=[604800000, None], value="%H:%M <br>%d-%b-%Y")
                ]
                ),
                
                    
                    # --- CONFIGURACIÓN DE EJES Y (LÍNEAS DIVISORIAS INTERNAS COMPLETAS) ---
                    yaxis5=dict(
                        title=dict(text="<b>Nivel Tanque (m)</b>", font=dict(color="#00ffcc")), 
                        tickfont=dict(color="#00ffcc"), 
                        side="left",
                        overlaying="y",
                        anchor="free",
                        position=0.00,
                        showline=True,        # Línea activa: Divide Nivel Tanque de Caudal
                        linecolor='white',
                        linewidth=1.5
                    ),
                    yaxis=dict(
                        title=dict(text="<b>Caudal (Lps)</b>", font=dict(color="#00d4ff")), 
                        tickfont=dict(color="#00d4ff"),
                        side="left",
                        anchor="free",
                        position=0.07,
                        showline=True,        # Línea activa: Cierre del área de gráfica izquierda
                        linecolor='white',
                        linewidth=1.5
                    ),
                    yaxis2=dict(
                        title=dict(text="<b>Presión (Kg/cm²)</b>", font=dict(color="#00ff00")), 
                        tickfont=dict(color="#00ff00"), 
                        side="right",
                        overlaying="y",
                        anchor="free",
                        position=0.92,
                        showline=True,        # Línea activa: Cierre del área de gráfica derecha
                        linecolor='white',
                        linewidth=1.5
                    ),
                    yaxis3=dict(
                        title=dict(text="<b>Niveles Pozo (m)</b>", font=dict(color="#ff00b4")), 
                        tickfont=dict(color="#ff00b4"), 
                        side="right",
                        overlaying="y",
                        anchor="free",
                        position=0.955,
                        showline=True,        # Línea activa: Divide Presión de Niveles Pozo
                        linecolor='white',
                        linewidth=1.5
                    ),
                    yaxis4=dict(
                        title=dict(text="<b>Eléctricos (V / A)</b>", font=dict(color="#ff8000")), 
                        tickfont=dict(color="#ff8000"), 
                        side="right",
                        overlaying="y",
                        anchor="free",
                        position=1.00,
                        showline=True,        # Línea activa: Divide Niveles Pozo de Eléctricos
                        linecolor='white',
                        linewidth=1.5,
                        rangemode="tozero"
                    )
                )
                st.plotly_chart(fig_line, use_container_width=True)

                # --- NUEVA SECCIÓN: DESCARGA DE DATOS ---
                # Usamos el dataframe 'df' que ya contiene toda la información de los tags
                if not df.empty:
                    # 1. Identificamos las etiquetas que corresponden a caudal
                    # Buscamos todas las que contengan 'CAU_INS'
                    mask_caudal = df['TagName'].str.contains('CAU_INS', na=False)
                    
                    # 2. Aplicamos filtros SOLO a esas filas
                    # Ponemos en None los valores fuera de rango solo en las filas de caudal
                    df.loc[mask_caudal & (df['VALUE'] < 0), 'VALUE'] = None
                    df.loc[mask_caudal & (df['VALUE'] > 100), 'VALUE'] = None
                    
                    # 3. Pivotamos los datos
                    df_pivot = df.pivot(index='FECHA', columns='TagName', values='VALUE')
                    
                    # 4. Aplicamos el rellenado hacia adelante (ffill) a todo el dataframe
                    # Como ya limpiamos los valores inválidos de caudal, el ffill
                    # tomará el último valor válido para todas las variables.
                    df_pivot = df_pivot.ffill().reset_index()
                    
                    # 5. Convertimos a CSV
                    csv_data = df_pivot.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="📥 Descargar datos del grafico",
                        data=csv_data,
                        file_name=f"Datos_{nombre_pozo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        help="Descarga los datos: Caudales (0-100 Lps) y resto de variables sin filtrar"
                    )
                else:
                    st.warning("No hay datos disponibles para procesar.")

        except Exception as e: 
            st.error(f"Error: {e}")
            
    st.stop()


# 4.7. SECCION ---------------------------------------------------------------- 4.7. GRAFICAR LOS MACROMEDIDORES ------------------------------------------------------------------------------------
import streamlit as st
import pandas as pd
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# --- Configuración de página ---
if "ver_grafico" in st.query_params:
    st.set_page_config(layout="wide", page_title="Miaa - Macromedidores")
    
    if not st.session_state.get('autenticado'):
        if st.query_params.get("access") == "granted":
            st.session_state.autenticado = True
        else:
            st.stop()

    tag_a_graficar = st.query_params.get("ver_grafico")
    nombre_mm = st.query_params.get("nombre")

    engine = get_mysql_telemetria_engine()
    hoy_dt = dt.datetime.now()
    medianoche = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Consulta con JOIN para traer el Diámetro desde la otra tabla
    query = f"""
        SELECT 
            m.Nombre, 
            m.Domicilio, 
            m.Colonia, 
            b.Diametro 
        FROM MACROMEDIDORES m
        LEFT JOIN Base_macromedidores b ON m.Medidor = b.Medidor
        WHERE m.Medidor = '{tag_a_graficar}' 
        AND m.Medidor != '1000' 
        LIMIT 1
    """
    
    df_info = pd.read_sql(query, engine)
    
    # Asignación segura de variables
    info = df_info.iloc[0] if not df_info.empty else {"Nombre": "N/A", "Domicilio": "N/A", "Colonia": "N/A", "Diametro": "N/A"}

    # --- Cabecera y CSS ---
    st.markdown(f"""
        <style>
            @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
            .spin-icon {{ animation: spin 4s linear infinite; display: inline-block; vertical-align: middle; }}
            .logo-miaa {{ height: 35px; margin-right: 15px; vertical-align: middle; }}
            .cabecera-contenedor {{ display: flex; align-items: center; background-color: #0e1117; padding: 10px 20px; border-radius: 10px; border: 1px solid #30363d; margin-bottom: 10px; flex-wrap: nowrap; }}
            div[data-testid="column"] {{ padding-top: 0px !important; }}
            div[data-testid="stVerticalBlock"] {{ gap: 0px !important; }}
        </style>
        <div class="cabecera-contenedor">
            <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-miaa">
            <svg class="spin-icon" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#00FFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 15px;">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path>
            </svg>
            <h3 style="margin: 0; color: #ffffff; margin-right: 20px; font-size: 1.2rem; white-space: nowrap;"> Macro medidor</h3>
            <div style="display: flex; gap: 20px; font-size: 12px; color: #c9d1d9; border-left: 2px solid #00FFFF; padding-left: 15px; align-items: center; text-transform: none !important;">
                <div><b>ID:</b> <span style="color:#ffffff;">{tag_a_graficar}</span></div>
                <div><b>Nombre:</b> <span style="color:#ffffff;">{info['Nombre']}</span></div>
                <div><b>Domicilio:</b> {info['Domicilio']}</div>
                <div><b>Colonia:</b> {info['Colonia']}</div>
                <div style="display: flex; align-items: baseline; gap: 5px;">
                    <b style="color: #c9d1d9;">Diámetro:</b> 
                    <span style="color:#00FFFF; font-size: 16px; font-weight: bold;">{info['Diametro']} Ø</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- Selector de fechas ---
    col_sel, col_ind, col_btn = st.columns([2.0, 0.5, 6.0])

    with col_sel:
        st.markdown('<div style="margin-top: 26px;"></div>', unsafe_allow_html=True)
        opcion_fecha = st.selectbox("rango", 
            ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"],
            index=4, label_visibility="collapsed", key="selector_fechas_unico")

    # --- Lógica de fechas (DEBE IR ANTES DE LA CONSULTA SQL) ---
    f_fin = hoy_dt
    if opcion_fecha == "Hoy": f_ini = medianoche
    elif opcion_fecha == "Ayer": f_ini, f_fin = medianoche - dt.timedelta(days=1), medianoche - dt.timedelta(seconds=1)
    elif opcion_fecha == "Últimos 7 días": f_ini = medianoche - dt.timedelta(days=7)
    elif opcion_fecha == "Últimos 14 días": f_ini = medianoche - dt.timedelta(days=14)
    elif opcion_fecha == "Este Mes": f_ini = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Último Mes":
        primer_dia = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        f_fin = primer_dia - dt.timedelta(seconds=1)
        f_ini = (primer_dia.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    elif opcion_fecha == "Últimos 6 meses": f_ini = medianoche - dt.timedelta(days=180)
    else: 
        rango = st.date_input("Periodo:", value=(hoy_dt.date() - dt.timedelta(days=7), hoy_dt.date()))
        f_ini, f_fin = dt.datetime.combine(rango[0], dt.time.min), dt.datetime.combine(rango[1], dt.time.max)

    # --- Consulta de datos ---
    df = pd.read_sql(f"SELECT FECHA, Flujo, Presion, Consumo FROM MACROMEDIDORES WHERE Medidor = '{tag_a_graficar}' AND Medidor != '1000' AND FECHA BETWEEN '{f_ini}' AND '{f_fin}' ORDER BY FECHA ASC", engine)
    df = df.groupby('FECHA').agg({
        'Flujo': 'mean',
        'Presion': 'mean',
        'Consumo': 'sum'
    }).reset_index()
    
    df_diario_exp = pd.DataFrame()
    if not df.empty:
        df_diario_exp = df.copy()
        df_diario_exp['FECHA'] = pd.to_datetime(df_diario_exp['FECHA']).dt.date
        df_diario_exp = df_diario_exp.groupby('FECHA')['Consumo'].sum().reset_index()

    # --- Botones en col_btn ---
    with col_btn:
        st.markdown('<div style="margin-top: 26px;"></div>', unsafe_allow_html=True)
        c_b1, c_b2 = st.columns(2)
        if not df.empty:
            with c_b1:
                st.download_button("📥 Exportar datos de caudal (lps) y presión (kg7cm2)", df.to_csv(index=False).encode('utf-8'), "datos.csv", "text/csv", use_container_width=True)
            with c_b2:
                st.download_button("📊 Exportar datos de consumo (m3)", df_diario_exp.to_csv(index=False).encode('utf-8'), "consumo.csv", "text/csv", use_container_width=True)
        else:
            with c_b1: st.button("📥", disabled=True)
            with c_b2: st.button("📊", disabled=True)

   
    # Creamos el placeholder para indicadores
    placeholder_indicadores = st.empty()

    if not df.empty:
        # 1. Cálculos de indicadores
        avg_caudal = df['Flujo'].mean()
        avg_presion = df['Presion'].mean()
        
        # Cálculo de consumo total para el indicador
        df_diario_calc = df.copy()
        df_diario_calc['FECHA'] = pd.to_datetime(df_diario_calc['FECHA']).dt.date
        total_consumo = df_diario_calc.groupby('FECHA')['Consumo'].sum().sum()
        
        # Formato manual para asegurar punto decimal y coma de miles
        entera = int(total_consumo)
        decimal = int(round((total_consumo - entera) * 100))
        consumo_fmt = f"{entera:,d}.{decimal:02d}".replace(",", "X").replace(".", ",").replace("X", ".")

        # 2. Renderizado de los 3 indicadores JUNTOS
        with placeholder_indicadores.container():
            _, col_m1, col_m2, col_m3, _ = st.columns([1, 2, 2, 2, 1])
            estilo_div = "text-align: center; padding: 5px;"
            estilo_titulo = "font-size: 0.7rem; color: #ffffff; font-weight: bold; margin-bottom: 2px;"
            estilo_valor = "font-size: 1.2rem; font-weight: bold; color: #ffffff;"

            with col_m1:
                st.markdown(f'<div style="{estilo_div}"><div style="{estilo_titulo}">Caudal promedio</div><div style="{estilo_valor}">{avg_caudal:.2f} <span style="font-size: 0.8rem; color: #00FFFF;">Lps</span></div></div>', unsafe_allow_html=True)
            with col_m2:
                st.markdown(f'<div style="{estilo_div}"><div style="{estilo_titulo}">Presión promedio</div><div style="{estilo_valor}">{avg_presion:.2f} <span style="font-size: 0.8rem; color: #00FF00;">kg/cm²</span></div></div>', unsafe_allow_html=True)
            with col_m3:
                st.markdown(f'<div style="{estilo_div}"><div style="{estilo_titulo}">Consumo total</div><div style="{estilo_valor}">{consumo_fmt} <span style="font-size: 0.8rem; color: #00FFFF;">m³</span></div></div>', unsafe_allow_html=True)
                        
        # --- Gráfico de Flujo y Presión ---
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(go.Scatter(
            x=df['FECHA'], y=df['Flujo'],
            name="Caudal (Lps)",
            mode='lines+markers',                # <--- MODO LÍNEAS Y PUNTOS
            marker=dict(size=5),                 # Tamaño de los puntos
            line=dict(color='#00FFFF', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 255, 255, 0.2)',
            hovertemplate="%{y:.2f} Lps<extra></extra>"
        ), secondary_y=False)
        
        # Presión: líneas + puntos
        fig.add_trace(go.Scatter(
            x=df['FECHA'], y=df['Presion'],
            name="Presión (Kg/cm²)",
            mode='lines+markers',                # <--- MODO LÍNEAS Y PUNTOS
            marker=dict(size=5),                 # Tamaño de los puntos
            line=dict(color='#00FF00', width=2),
            hovertemplate="%{y:.2f} Kg/cm²<extra></extra>"
        ), secondary_y=True)

        # 1. GENERACIÓN DE ETIQUETAS Y FECHAS (ESTÁNDAR)
        dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
        meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 
                    7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

        fechas_lineas = pd.date_range(start=df['FECHA'].min().floor('D'), 
                                      end=df['FECHA'].max().ceil('D'), freq='D')
        
        ticks_filtrados = fechas_lineas
        etiquetas_filtradas = [
            f"00:00<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
            for d in ticks_filtrados
        ]

        # 2. DIBUJO DE LÍNEAS CON SOMBRA
        delta = pd.Timedelta(hours=1)
        for d in fechas_lineas:
            es_lunes = (d.dayofweek == 0)

            # Sombra gris detrás
            fig.add_vrect(
                x0=d - delta,
                x1=d + delta,
                fillcolor="gray",
                opacity=0.2,
                layer="below",
                line_width=0)

            # Línea punteada nítida
            fig.add_vline(
                x=d, line_width=1.5,
                line_dash="dash", 
                line_color="#fffb00" if es_lunes else "white", 
                opacity=0.5, 
                layer="above")

        # 3. CONFIGURACIÓN FINAL
        fig.update_layout(
            height=400, 
            template="plotly_dark",
            hovermode="x unified",
            xaxis=dict(
                rangeslider=dict(visible=True,
                thickness=0.10),
                tickvals=ticks_filtrados,
                ticktext=etiquetas_filtradas,
                tickangle=0, showline=False),
            
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            uirevision='constant'
        )
        
        fig.update_yaxes(title_text="Caudal (Lps)", secondary_y=False)
        fig.update_yaxes(title_text="Presión (Kg/cm²)", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)
        
        # 4. Gráfico de Barras (Consumo) --------------------------------------------------------------------------------------------------------------------
        df_diario = df.copy()
        df_diario['FECHA'] = pd.to_datetime(df_diario['FECHA']).dt.date
        df_diario = df_diario.groupby('FECHA')['Consumo'].sum().reset_index()
        rango_completo = pd.date_range(start=df_diario['FECHA'].min(), end=df_diario['FECHA'].max())
        df_diario = df_diario.set_index('FECHA').reindex(rango_completo, fill_value=0).reset_index()
        df_diario.columns = ['FECHA', 'Consumo']
        df_diario['FECHA'] = df_diario['FECHA'].dt.strftime('%d %b %Y')
        
        fig_bar = px.bar(df_diario, x='FECHA', y='Consumo', text='Consumo', color_discrete_sequence=['#00FFFF'])
        fig_bar.update_layout(
            height=300, template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(tickmode='linear', title=None), yaxis=dict(title="Consumo (m3)"),
            margin=dict(t=30, b=20, l=20, r=20), showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="right", x=1)
        )
        fig_bar.update_traces(
            texttemplate='%{text:.1f}',
            textposition='outside',
            name='Consumo (m³)',
            hovertemplate="<b>Día:</b> %{x}<br><b>Consumo:</b> %{y:.2f} m³<extra></extra>"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        placeholder_indicadores.empty() # Limpia si no hay datos
        st.warning("No hay datos registrados en este rango.")

        # --- Gráfico de Flujo y Presión ---
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df['FECHA'], y=df['Flujo'], name="Caudal (Lps)", line=dict(color='#00FFFF', width=2), fill='tozeroy', fillcolor='rgba(0, 255, 255, 0.2)'), secondary_y=False)
        fig.add_trace(go.Scatter(x=df['FECHA'], y=df['Presion'], name="Presión (Kg/cm²)", line=dict(color='#00FF00', width=2)), secondary_y=True)
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df['FECHA'], y=df['Flujo'], name="Caudal (Lps)", line=dict(color='#00FFFF', width=2), fill='tozeroy', fillcolor='rgba(0, 255, 255, 0.2)'), secondary_y=False)
        fig.add_trace(go.Scatter(x=df['FECHA'], y=df['Presion'], name="Presión (Kg/cm²)", line=dict(color='#00FF00', width=2)), secondary_y=True)
                
        fig.update_yaxes(title_text="Caudal (Lps)", secondary_y=False)
        fig.update_yaxes(title_text="Presión (Kg/cm²)", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

        df_diario = df.copy()
        df_diario['FECHA'] = pd.to_datetime(df_diario['FECHA']).dt.date
        df_diario = df_diario.groupby('FECHA')['Consumo'].sum().reset_index()
        
        rango_completo = pd.date_range(start=df_diario['FECHA'].min(), end=df_diario['FECHA'].max())
        df_diario = df_diario.set_index('FECHA').reindex(rango_completo, fill_value=0).reset_index()
        df_diario.columns = ['FECHA', 'Consumo']
        df_diario['FECHA'] = df_diario['FECHA'].dt.strftime('%b %d')

        fig_bar = px.bar(
            df_diario, 
            x='FECHA', 
            y='Consumo', 
            text='Consumo', 
            color_discrete_sequence=['#00FFFF'],
            
        )      
        fig_bar.update_traces(name="Consumo (m³)", showlegend=True)
        fig_bar.update_layout(
            height=300, 
            template="plotly_dark", 
            plot_bgcolor='rgba(0,0,0,0)', 
            paper_bgcolor='rgba(0,0,0,0)', 
            xaxis=dict(tickmode='linear', title=None), # Quitamos título eje X para ahorrar espacio  
            yaxis=dict(title="Consumo (m3)"),
            margin=dict(t=40, b=20, l=20, r=20),
            showlegend=True,                           # Esto activa la leyenda
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.1,                                 # Ajustado para que se vea bien
                xanchor="left",
                x=0
            )
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.stop()

# 5. ESTILO CSS GENERAL ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
st.markdown("""
    <style>
        [data-testid="collapsedControl"], button[kind="headerNoPadding"], [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }
        header { visibility: hidden !important; height: 0px !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        .stApp { background-color: #000000; color: white; }
        
        .block-container {
            padding-top: 5px !important; 
            padding-bottom: 0rem !important;
            margin-top: 0px !important;
            max-width: 100% !important;
        }

        div[data-testid="stHorizontalBlock"] {
            margin-top: 0px !important;
            padding-top: 0px !important;
        }

        .stMarkdown {
            margin-top: 0px !important;
            padding-top: 0px !important;
        }

        /* Barra de pestañas arriba */
        .miaa-skew-bar {
            display: flex;
            gap: 10px;
            width: 100%;
            margin-top: -12px !important; 
            margin-bottom: 8px !important;
            padding: 0 !important;
            position: relative;
            z-index: 999;
        }

        /* Mapa ajustado justo debajo de las pestañas */
        div.element-container:has(iframe) {
            margin-top: -25px !important;
            margin-bottom: 0px !important;
        }

        .mapa-area {
            margin-top: 0px !important;
        }

        .mapa-area iframe { 
            margin-top: 0px !important;
            border: 1px solid #1f4068 !important;
            height: 85vh !important;
        }

        .mapa-area [data-testid="column"] {
            flex: 1 1 0% !important;
            margin-top: 0px !important;
            padding-top: 0px !important;
        }

        .titulo-superior {
            position: fixed;
            top: 0px; 
            left: calc(50% + 160px); 
            transform: translateX(-50%);
            z-index: 1000;
            color: #00d4ff; 
            font-size: 1.5rem;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            background-color: #000000;
            width: 100%;
            text-align: center;
            padding: 4px 0;
            border-bottom: 1px solid #1f4068;
        }

        .contenedor-indicadores {
           position: fixed;
           top: 65px; 
           left: 320px;
           right: 0;
           display: flex;
           justify-content: center;
           align-items: center;
           gap: 15px;
           z-index: 1001;
           background: transparent;
           padding: 0 15px;
        }

        .card-indicador {
           flex: 1;
           border: 1px solid #1f4068; 
           background: linear-gradient(180deg, rgba(11, 26, 41, 0.95) 0%, rgba(0, 0, 0, 1) 100%);
           padding: 8px 5px;
           text-align: center;
           border-radius: 10px;
           box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.5);
        }
        .card-indicador:first-child { border-left: 1px solid #1f4068; }

        .card-label { color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; margin: 0; }
        .card-value { font-family: 'Courier New', monospace; font-size: 1.5rem; font-weight: bold; margin: 0; }
        
        .mapa-principal-ajuste {
            margin-top: -200px !important;
            z-index: 1;
        }
        .mapa-principal-ajuste iframe {
            border: 1px solid #1f4068 !important;
            border-top: none !important;
        }

        /* --- BARRA LATERAL SEPARADA DE LA DERECHA Y FORZADA VISIBLE --- */
        [data-testid="stSidebarContent"] {
            padding-top: 3px !important; 
            padding-right: 8px !important;
        }

        [data-testid="stSidebar"] { 
            background-color: #0b1a29 !important; 
            border-right: 2px solid #1f4068 !important; 
            margin-right: 10px !important;
            display: block !important;
            visibility: visible !important;
            transform: none !important;
            min-width: 280px !important;
        }

       .sidebar-logo { 
            position: fixed; 
            top: 20px; 
            left: 40px; 
            width: 170px;  
            height: 50px;  
            z-index: 999999; 
            display: flex; 
            justify-content: center; 
            align-items: center;
            background-color: #0b1a29; 
            border-bottom: 1px solid #1f4068;
        }
         
        .status-tag { 
            font-size: 10px; 
            padding: 2px 6px; 
            border-radius: 4px; 
            margin-left: 5px; 
            font-weight: bold; 
        }
        
        .status-ok { background-color: #1b5e20; color: #a5d6a7; }
        .status-err { background-color: #b71c1c; color: #ef9a9a; }
        
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
        .blink_me { animation: blink 1.2s infinite; }

        .pulsante {
            animation: parpadeo 1.2s infinite;
        }
        @keyframes parpadeo {
            0% { opacity: 1; }
            50% { opacity: 0.1; }
            100% { opacity: 1; }
        }
    </style>
""", unsafe_allow_html=True)

# 6. PROCESAMIENTO DE DATOS BASE -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

sectores = cargar_sectores_poligonos()
mapa_pozos_dict = cargar_mapa_pozos_desde_db()
mapa_tanques_dict = cargar_tanques_desde_db()
mapa_rebombeos_dict = cargar_rebombeos_desde_db()

tags_a_consultar = []
for p in mapa_pozos_dict.values():
    tags_a_consultar.extend([
        p['bomba'], p['caudal'], p['presion'], p['nivel_tanque'],
        p['nivel_dinamico'], p['sumergencia'], p['columna']
    ])
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

ahora = dt.datetime.utcnow() - dt.timedelta(hours=6) 

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
            fecha_dt = dt.datetime.strptime(f"{ahora.year}/{fecha_str}", "%Y/%d/%m %H:%M")
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
        if pres_val < 0.10:
            info.update({'status_label': 'APAGADO', 'color_final': '#FF0000', 'blink': True})
        else:
            info.update({'status_label': 'OPERANDO', 'color_final': '#00FF00', 'blink': False})

# 7. DETALLE DE SECTOR -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- 

if sector_seleccionado:
    st.markdown("""
        <style>
            :root { color-scheme: dark; }
            .stApp { background: #081421; color: #e4edf7; }
            header[data-testid="stHeader"] { background: #081421; display: none !important; }
            [data-testid="stSidebar"] { display: none !important; }
            .block-container { padding: 0rem 2rem 3.5rem !important; max-width: 1920px; margin-top: -25px !important; }
            h1 { font-size: 1.9rem !important; font-weight: 650 !important; letter-spacing: -0.045rem; padding-top: 0rem !important; margin-top: 0rem !important; }
            h3 { font-size: 1.03rem !important; font-weight: 600 !important; padding: .1rem 0 !important; }
            
            [data-testid="stVerticalBlockBorderWrapper"] > div { border-color: #22384d !important; border-radius: 12px !important; background: linear-gradient(135deg, #030d17 0%, #081c30 50%, #030d17 100%) !important; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5); }
            [data-testid="stCaptionContainer"] { color: #91a8bf; font-size: .78rem; }

            .dma-op-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0.52rem 0;
                border-bottom: 1px solid rgba(31, 64, 104, 0.4);
                font-size: 0.85rem;
            }
            .dma-op-row:last-child { border-bottom: none; }
            .dma-op-label { color: #9ab0c7; display: flex; align-items: center; gap: 8px; }
            .dma-op-value { color: #f0f7ff; font-weight: 600; font-variant-numeric: tabular-nums; }

            div[data-baseweb="select"], div[data-baseweb="select"] > div, div[data-baseweb="select"] div {
                background-color: #030d17 !important; background: #030d17 !important;
            }
            div[data-baseweb="select"] > div {
                border: 1px solid #1f4068 !important; border-radius: 8px !important; color: #e4edf7 !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
            }
            div[data-baseweb="select"] span { color: #e4edf7 !important; }
            div[data-baseweb="popover"] div { background-color: #0b1a29 !important; color: #e4edf7 !important; }

            @keyframes drop-pulse {
                0% { transform: scale(1); filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.6)); }
                50% { transform: scale(1.15); filter: drop-shadow(0 0 12px rgba(0, 212, 255, 1)); }
                100% { transform: scale(1); filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.6)); }
            }
            @keyframes line-glow {
                0% { opacity: 0.7; }
                50% { opacity: 1; filter: drop-shadow(0 0 8px rgba(0, 212, 255, 0.9)); }
                100% { opacity: 0.7; }
            }

            .miaa-logo-img { height: 42px; width: auto; max-width: 170px; object-fit: contain; filter: drop-shadow(0 0 6px rgba(0, 212, 255, 0.4)); margin-top: 6px; }
            .miaa-center-content { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; }
            .miaa-title-main { color: #ffffff; font-size: 1.55rem; font-weight: 700; margin: 0 0 6px 0; letter-spacing: -0.02rem; white-space: nowrap; text-align: center; line-height: 1.2; }
            .miaa-sector-highlight { color: #00d4ff; text-shadow: 0 0 10px rgba(0, 212, 255, 0.5); }
            .miaa-lines-row { display: flex; align-items: center; width: 100%; justify-content: center; gap: 14px; }
            .miaa-neon-bar { flex-grow: 1; height: 2px; background: linear-gradient(90deg, rgba(0,212,255,0) 0%, #00d4ff 100%); box-shadow: 0 0 8px #00d4ff; animation: line-glow 3s infinite ease-in-out; }
            .miaa-neon-bar.right-side { background: linear-gradient(90deg, #00d4ff 0%, rgba(0,212,255,0) 100%); }
            .miaa-animated-water-drop { width: 22px; height: 22px; animation: drop-pulse 2.5s infinite ease-in-out; flex-shrink: 0; }

            @keyframes pulse-glow {
                0% { transform: scale(1); filter: drop-shadow(0 0 2px rgba(71,175,208,0.4)); }
                50% { transform: scale(1.12); filter: drop-shadow(0 0 8px rgba(71,175,208,0.9)); }
                100% { transform: scale(1); filter: drop-shadow(0 0 2px rgba(71,175,208,0.4)); }
            }
            @keyframes radar-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
            @keyframes water-flow { 0% { stroke-dashoffset: 24; } 100% { stroke-dashoffset: 0; } }
            @keyframes float-up { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
            .anim-pulse { animation: pulse-glow 2.5s infinite ease-in-out; transform-origin: center; }
            .anim-spin { animation: radar-spin 8s infinite linear; transform-origin: center; }
            .anim-flow { stroke-dasharray: 6; animation: water-flow 1.5s infinite linear; }
            .anim-float { animation: float-up 3s infinite ease-in-out; }

            .card-indicador {
                background: linear-gradient(135deg, #122c42 0%, #0b1c2d 100%);
                border: 1px solid #27445e;
                border-top: 2px solid #47afd0;
                border-radius: 10px;
                padding: 14px 16px;
                min-height: 95px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .label-indicador { font-size: 0.82rem; color: #9ab0c7; margin: 0; font-weight: 500; }
            .value-indicador { font-size: 1.6rem; color: #f0f7ff; font-weight: 700; margin: 4px 0 0 0; font-variant-numeric: tabular-nums; }
            iframe { border-radius: 8px; }

            /* Ocultar barra de atribución de Leaflet */
            .leaflet-control-attribution {
                display: none !important;
            }
        </style>
    """, unsafe_allow_html=True)

    if 'sector_seleccionado' not in locals() and 'sector_seleccionado' in st.session_state:
        sector_seleccionado = st.session_state['sector_seleccionado']
    if 'sector_elegido' not in locals():
        sector_elegido = globals().get('sector_seleccionado', 'Sector Desconocido')

    sec_val_actual = sector_seleccionado if 'sector_seleccionado' in locals() and sector_seleccionado else sector_elegido
    sec_id = str(sec_val_actual).split('.')[0].strip()
    sec_id_clean = re.sub(r'^[^\d]*', '', sec_id)
    
    datos_s = next((s for s in sectores if str(s.get('sector', '')).strip() == sec_id), None)
    
    if datos_s is None:
        datos_s = {
            'sector': sec_val_actual,
            'Distrito': 'Oriente',
            'Poblacion': 0,
            'Superficie': 0.0,
            'Long_Red': 42.6,
            'Vol_Prod': 0,
            'U_Domesticos': 0,
            'U_NoDom': 0,
            'Cons_m3': 0.0,
            'Vol_Medid': 0.0,
            'Vol_Fact': 0,
            'Balance_Estimado': 0.0,
            'geo': None,
            'Pozos_Sector': ''
        }

    def _fmt_indicador_postgres(val, decimals=2, integer_only=False, is_pct=False):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "N/D"
        txt = str(val).strip()
        if not txt or txt.lower() in ("none", "nan", "nat", "n/d"):
            return "N/D"
        try:
            num = float(txt.replace("%", "").replace(",", "").strip())
            if pd.isna(num):
                return txt
            if integer_only:
                res = f"{num:,.0f}"
            else:
                res = f"{num:,.{decimals}f}"
            return f"{res}%" if is_pct else res
        except (ValueError, TypeError):
            return txt if (not is_pct or txt.endswith("%")) else f"{txt}%"

    # 1. EF -> Eficiencia Física (EF) en porcentaje
    val_ef = _fmt_indicador_postgres(datos_s.get("EF"), decimals=0, is_pct=True)

    # 2. ANF -> Agua No Facturada (ANF) exclusivamente de la columna ANF, en porcentaje
    val_anf = _fmt_indicador_postgres(datos_s.get("ANF"), decimals=0, is_pct=True)

    # 3. DOTACION -> Dotación
    val_dotacion = _fmt_indicador_postgres(datos_s.get("DOTACION"), integer_only=True)

    # 4. PERD_US_MES -> Pérd. Usuario-Mes
    val_perd_us_mes = _fmt_indicador_postgres(datos_s.get("PERD_US_MES"), decimals=2)

    # 5. FUGAS_KM -> Fugas por Km
    val_fugas_km = _fmt_indicador_postgres(datos_s.get("FUGAS_KM"), decimals=2)

    with st.container(border=True):
        head_col1, head_col2, head_col3 = st.columns([1.5, 5.5, 2.2], gap="medium")
        
        with head_col1:
            st.markdown(
                '<img class="miaa-logo-img" src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" alt="Logo MIAA">',
                unsafe_allow_html=True
            )

        with head_col2:
            st.markdown(f"""
                <div class="miaa-center-content">
                    <h1 class="miaa-title-main">Monitoreo de sector: <span class="miaa-sector-highlight">{sector_seleccionado}</span></h1>
                    <div class="miaa-lines-row">
                        <div class="miaa-neon-bar"></div>
                        <svg class="miaa-animated-water-drop" viewBox="0 0 24 24" fill="#00d4ff">
                            <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
                        </svg>
                        <div class="miaa-neon-bar right-side"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with head_col3:
            opciones_periodo = [
                "Hoy", "Ayer", "Últimas 24 horas", "Últimas 48 horas", 
                "Esta semana", "Últimos 7 días", "Este Mes", 
                "Último mes", "Últimos 3 meses", "Últimos 6 meses", "Personalizado"
            ]
            opcion_periodo_tab = st.selectbox(
                "Periodo:",
                opciones_periodo,
                index=4,
                key="f_sector_periodo_tab_detalle"
            )

    st.write("")

    hoy_dt = datetime.now()
    medianoche = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    f_fin_h = hoy_dt

    if opcion_periodo_tab == "Hoy":
        f_ini_h = medianoche
    elif opcion_periodo_tab == "Ayer":
        f_ini_h = medianoche - timedelta(days=1)
        f_fin_h = medianoche - timedelta(seconds=1)
    elif opcion_periodo_tab == "Últimas 24 horas":
        f_ini_h = hoy_dt - timedelta(hours=24)
    elif opcion_periodo_tab == "Últimas 48 horas":
        f_ini_h = hoy_dt - timedelta(hours=48)
    elif opcion_periodo_tab == "Esta semana":
        f_ini_h = medianoche - timedelta(days=medianoche.weekday())
    elif opcion_periodo_tab == "Últimos 7 días":
        f_ini_h = medianoche - timedelta(days=7)
    elif opcion_periodo_tab == "Este Mes":
        f_ini_h = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif opcion_periodo_tab == "Último mes":
        f_ini_h = medianoche - timedelta(days=30)
    elif opcion_periodo_tab == "Últimos 3 meses":
        f_ini_h = medianoche - timedelta(days=90)
    elif opcion_periodo_tab == "Últimos 6 meses":
        f_ini_h = medianoche - timedelta(days=180)
    else:
        f_ini_h = medianoche - timedelta(days=7)

    def coincide_sector(item_dict):
        val_sec = str(item_dict.get('Sector') or item_dict.get('sector') or '').strip()
        s_actual_limpio = ''.join(c for c in str(sec_val_actual).upper() if c.isalnum())
        s_item_limpio = ''.join(c for c in val_sec.upper() if c.isalnum())
        return s_item_limpio == s_actual_limpio or val_sec.upper() == str(sec_val_actual).upper()

    dict_reg_all = cargar_puntos_de_control_desde_db() 
    dict_reg = {k: v for k, v in dict_reg_all.items() if coincide_sector(v)}
    
    dict_vrp_all = cargar_vrp_desde_db()
    dict_vrp_sec = {k: v for k, v in dict_vrp_all.items() if coincide_sector(v)}

    mapa_pc_all = cargar_puntos_criticos_desde_db()
    dict_pc_sec = {k: v for k, v in mapa_pc_all.items() if coincide_sector(v)}

    ids_p = [str(p).strip() for p in datos_s.get('Pozos_Sector', '').split(',')] if datos_s.get('Pozos_Sector') else []

    mapa_series_nombres = {}
    series_caudal_sector = []

    for k, r in dict_reg.items():
        s_val = r.get('Serie') or r.get('dispositivo') or k
        if s_val and str(s_val).strip().lower() not in ['none', 'n/a', 'null', '0']:
            serie_str = str(s_val).strip()
            mapa_series_nombres[serie_str] = r.get('nombre', f"Punto Control ({serie_str})")
            if any('CAUDAL' in str(v).upper() for v in r.get('variables', [])) or 'CAUDAL' in str(k).upper():
                series_caudal_sector.append(serie_str)

    for k, v in dict_vrp_sec.items():
        s_val = v.get('Serie') or k
        if s_val and str(s_val).strip().lower() not in ['none', 'n/a', 'null', '0']:
            serie_str = str(s_val).strip()
            mapa_series_nombres[serie_str] = v.get('nombre', f"VRP ({serie_str})")
            series_caudal_sector.append(serie_str)

    for k, pc in dict_pc_sec.items():
        s_val = pc.get('Serie') or k
        if s_val and str(s_val).strip().lower() not in ['none', 'n/a', 'null', '0']:
            mapa_series_nombres[str(s_val).strip()] = pc.get('Domicilio', f"Punto Crítico ({s_val})")

    tags_para_scada = []
    tags_agregados_set = set()
    
    for id_p in ids_p:
        if id_p in mapa_pozos_dict:
            p_info = mapa_pozos_dict[id_p]
            for kt in ['caudal', 'presion', 'nivel_tanque']:
                t_val = p_info.get(kt)
                if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    if str(t_val) not in tags_agregados_set:
                        tags_para_scada.append(str(t_val))
                        tags_agregados_set.add(str(t_val))

    scada_res_reg = cargar_datos_scada([str(t) for t in set(tags_para_scada) if t])

    ultimos_valores_mapa = {}
    if mapa_series_nombres:
        try:
            engine_tel = get_mysql_telemetria_engine()
            series_in_sql = "', '".join(list(mapa_series_nombres.keys()))
            q_ultimos_directo = f"""
                SELECT DISPOSITIVO, VARIABLE, VALOR, FECHA_HORA_LOGGER 
                FROM BD_MADRE 
                WHERE (DISPOSITIVO, FECHA_HORA_LOGGER) IN (
                    SELECT DISPOSITIVO, MAX(FECHA_HORA_LOGGER) 
                    FROM BD_MADRE 
                    WHERE DISPOSITIVO IN ('{series_in_sql}') 
                    GROUP BY DISPOSITIVO, VARIABLE
                )
            """
            df_ultimos = pd.read_sql(q_ultimos_directo, engine_tel)
            if not df_ultimos.empty:
                caudales_detectados = df_ultimos[df_ultimos['VARIABLE'].str.upper().str.contains('CAUDAL', na=False)]['DISPOSITIVO'].astype(str).tolist()
                series_caudal_sector = list(set(series_caudal_sector + caudales_detectados))

                for _, row in df_ultimos.iterrows():
                    dev = str(row['DISPOSITIVO']).strip()
                    var = str(row['VARIABLE']).strip()
                    val_db = row['VALOR']
                    if 'PRESION' in var.upper() and val_db is not None:
                        try:
                            val_db = float(val_db) * 10.0
                        except (ValueError, TypeError):
                            pass
                    if dev not in ultimos_valores_mapa:
                        ultimos_valores_mapa[dev] = {}
                    ultimos_valores_mapa[dev][var] = {'valor': val_db, 'fecha': row['FECHA_HORA_LOGGER']}
        except Exception:
            pass

    min_nocturno_str = "-"

    if series_caudal_sector:
        try:
            series_q_in = "', '".join(series_caudal_sector)
            q_nocturno = f"""
                SELECT FECHA_HORA_LOGGER AS Fecha, VALOR 
                FROM BD_MADRE 
                WHERE DISPOSITIVO IN ('{series_q_in}')
                  AND VARIABLE LIKE '%CAUDAL%'
                  AND FECHA_HORA_LOGGER BETWEEN '{f_ini_h}' AND '{f_fin_h}'
                ORDER BY FECHA_HORA_LOGGER ASC
            """
            df_noc = pd.read_sql(q_nocturno, engine_tel)
            if not df_noc.empty:
                df_noc['FECHA'] = pd.to_datetime(df_noc['Fecha'], errors='coerce')
                df_noc['VALOR'] = pd.to_numeric(df_noc['VALOR'], errors='coerce')
                
                mask_nocturno = (df_noc['FECHA'].dt.hour >= 22) | (df_noc['FECHA'].dt.hour < 6)
                df_noc_filtered = df_noc[mask_nocturno].dropna(subset=['VALOR'])

                if not df_noc_filtered.empty:
                    if (df_noc_filtered['VALOR'] == 0).any():
                        min_nocturno_str = "-"
                    else:
                        val_min = df_noc_filtered['VALOR'].min()
                        min_nocturno_str = f"{val_min:,.1f} <span style='font-size:0.8rem; font-weight:normal;'>L/s</span>"
        except Exception:
            pass

    demanda_estimada_val = datos_s.get('Cons_m3', 0.0)

    texto_nivel_tq = "Sin registro de nivel TQ"
    fec_nivel_tq_str = "N/A"
    for id_p in ids_p:
        if id_p in mapa_pozos_dict:
            p_info = mapa_pozos_dict[id_p]
            t_niv = p_info.get('nivel_tanque')
            if t_niv and str(t_niv).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                val_niv, fec_niv = scada_res_reg.get(str(t_niv), (0.0, "N/A"))
                fec_str = fec_niv.strftime('%d/%m %H:%M') if hasattr(fec_niv, 'strftime') else str(fec_niv)
                texto_nivel_tq = f"{val_niv:,.2f} m"
                fec_nivel_tq_str = f"{fec_str} · En línea"
                break

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-flow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83"></path></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Eficiencia Física (EF)</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{val_ef}</p>
        </div>''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-float" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Agua No Facturada (ANF)</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{val_anf}</p>
        </div>''', unsafe_allow_html=True)
    with c3:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-pulse" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Dotación</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{val_dotacion} <span style="font-size:0.8rem; font-weight:normal;">L/hab/d</span></p>
        </div>''', unsafe_allow_html=True)
    with c4:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-float" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Pérd. Usuario-Mes</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{val_perd_us_mes} <span style="font-size:0.8rem; font-weight:normal;">m³</span></p>
        </div>''', unsafe_allow_html=True)
    with c5:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Fugas por Km</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{val_fugas_km} <span style="font-size:0.8rem; font-weight:normal;">fugas/km</span></p>
        </div>''', unsafe_allow_html=True)
    with c6:
        st.markdown(f'''<div class="card-indicador">
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                <svg class="anim-pulse" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#47afd0" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
                <p class="label-indicador" style="font-size: 13px; margin:0;">Mínimo nocturno</p>
            </div>
            <p class="value-indicador" style="font-size: 1.35rem; text-align: center;">{min_nocturno_str}</p>
        </div>''', unsafe_allow_html=True)
    st.write("")

    col_izq, col_der = st.columns([0.7, 1.3])

# =========================================================================== INICIO DE MAPA SECTORES ============================================================================================================
    
    with col_izq:
        st.markdown(f"""
            <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Sector y puntos de medición</p>
                <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">{sector_elegido} - Distrito {datos_s.get('Distrito', 'Oriente')}</p>
            </div>
        """, unsafe_allow_html=True)

        m_sec = folium.Map(location=[21.8820, -102.2800], zoom_start=12, tiles=None, height=360, attribution_control=False)
        
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
            attr='Google', 
            name='Vista Satélite', 
            overlay=False
        ).add_to(m_sec)
        
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satélite (Esri)',
            overlay=False,
            control=True
        ).add_to(m_sec)

        api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
        folium.TileLayer(
            tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
            name="Vista Nocturna",
            attr='&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains="abcd",
            max_zoom=20,
            overlay=False,
            control=True
        ).add_to(m_sec)

        capa_sector = folium.FeatureGroup(name="Límite del sector", overlay=True, control=True).add_to(m_sec)
        capa_control = folium.FeatureGroup(name="Puntos de control", overlay=True, control=True).add_to(m_sec)
        capa_criticos = folium.FeatureGroup(name="Puntos críticos", overlay=True, control=True).add_to(m_sec)
        capa_vrp = folium.FeatureGroup(name="VRP", overlay=True, control=True).add_to(m_sec)
        capa_pozos = folium.FeatureGroup(name="Pozos", overlay=True, control=True).add_to(m_sec)

        if datos_s and datos_s.get('geo'):
            try:
                geo_data = json.loads(datos_s['geo'])
                folium_geo = folium.GeoJson(
                    geo_data, 
                    style_function=lambda x: {'fillColor': '#00d4ff', 'color': '#ffffff', 'weight': 2, 'fillOpacity': 0.15},
                    name="Límite del sector"
                ).add_to(capa_sector)
                m_sec.fit_bounds(folium_geo.get_bounds(), padding=(30, 30), max_zoom=15)
            except: 
                pass

        for r_k, r in dict_reg.items():
            serie_reg = str(r.get('Serie', r_k)).strip()
            vals_dev = ultimos_valores_mapa.get(serie_reg, {})
            
            html_vars_detalle = ""
            for var_name, info_v in vals_dev.items():
                val_num = info_v.get('valor', 0.0)
                try:
                    val_num = float(val_num) if val_num is not None else 0.0
                except (ValueError, TypeError):
                    val_num = 0.0

                var_label_display = var_name
                if var_label_display in ["Presion1", "Presion2"]:
                    var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                elif var_label_display == "Caudal1":
                    var_label_display = "Q1"

                unidad_v = "L/s" if "CAUDAL" in var_name.upper() else ("mca" if "PRESION" in var_name.upper() else ("V" if "VOLT" in var_name.upper() else ""))
                html_vars_detalle += f"&bull; {var_label_display}: <b>{val_num:.2f} {unidad_v}</b><br>"
            
            if not html_vars_detalle:
                html_vars_detalle = "Sin registros recientes<br>"

            html_popup_reg = f"""
                <div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00FFFF; width:230px;">
                    <b style="color:#00FFFF;">{r.get('nombre', 'Punto de Control')}</b><br>
                    <small style="color:#aaa;">SN: {serie_reg}</small><hr style="border-color:#333; margin:6px 0;">
                    {html_vars_detalle}
                </div>
            """
            icon_html = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #66ccff, #007bff, #003366); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
            folium.Marker(location=r['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html), popup=folium.Popup(html_popup_reg, max_width=250)).add_to(capa_control)
            folium.Marker(location=r['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #00FFFF; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(0,255,255,0.4);">SN: {serie_reg} • Registrador</div>')).add_to(capa_control)

        for id_pc, pc in dict_pc_sec.items():
            domicilio_texto = pc.get('Domicilio', 'S/D')
            serie_pc = str(pc.get('Serie', id_pc)).strip()
            vals_pc = ultimos_valores_mapa.get(serie_pc, {})
            
            html_vars_pc = ""
            for var_name, info_v in vals_pc.items():
                val_num = info_v.get('valor', 0.0)
                try:
                    val_num = float(val_num) if val_num is not None else 0.0
                except (ValueError, TypeError):
                    val_num = 0.0

                var_label_display = var_name
                if var_label_display in ["Presion1", "Presion2"]:
                    var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                elif var_label_display == "Caudal1":
                    var_label_display = "Q1"

                unidad_v = "mca" if "PRESION" in var_name.upper() else ("V" if "VOLT" in var_name.upper() else "")
                html_vars_pc += f"&bull; {var_label_display}: <b>{val_num:.2f} {unidad_v}</b><br>"
            
            if not html_vars_pc:
                html_vars_pc = "Sin registros recientes<br>"

            html_pc = f"""
                <div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #FF00FF; width:200px;">
                    <b style="color:#FF00FF;">PUNTO CRÍTICO</b><br><small>{domicilio_texto}</small><hr style="border-color:#333; margin:6px 0;">
                    {html_vars_pc}
                </div>
            """
            icon_html_pc = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #ff4d4d, #ff0000, #800000); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
            folium.Marker(location=pc['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_pc), popup=folium.Popup(html_pc, max_width=250)).add_to(capa_criticos)
            folium.Marker(location=pc['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #FF00FF; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(255,0,255,0.4);">NS: {serie_pc} • Punto critico</div>')).add_to(capa_criticos)

        for id_vrp, vrp in dict_vrp_sec.items():
            serie_vrp = str(vrp.get('Serie', id_vrp)).strip()
            vals_vrp = ultimos_valores_mapa.get(serie_vrp, {})
            
            html_vars_vrp = ""
            for var_name, info_v in vals_vrp.items():
                val_num = info_v.get('valor', 0.0)
                try:
                    val_num = float(val_num) if val_num is not None else 0.0
                except (ValueError, TypeError):
                    val_num = 0.0

                var_label_display = var_name
                if var_label_display in ["Presion1", "Presion2"]:
                    var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                elif var_label_display == "Caudal1":
                    var_label_display = "Q1"

                unidad_v = "L/s" if "CAUDAL" in var_name.upper() else ("mca" if "PRESION" in var_name.upper() else ("V" if "VOLT" in var_name.upper() else ""))
                html_vars_vrp += f"&bull; {var_label_display}: <b>{val_num:.2f} {unidad_v}</b><br>"
            
            if not html_vars_vrp:
                html_vars_vrp = "Sin registros recientes<br>"

            html_vrp = f"""
                <div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00FFCC; width:220px;">
                    <b style="color:#00FFCC;">VÁLVULA VRP</b><br><small>{vrp.get('nombre', 'S/N')}</small><br><small style="color:#aaa;">SN: {serie_vrp}</small><hr style="border-color:#333; margin:6px 0;">
                    {html_vars_vrp}
                </div>
            """
            icon_html_vrp = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #a1ffce, #28a745, #004d1a); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
            folium.Marker(location=vrp['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_vrp), popup=folium.Popup(html_vrp, max_width=250)).add_to(capa_vrp)
            folium.Marker(location=vrp['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #00FFCC; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: rgba(0,255,204,0.4);">SN: {serie_vrp} • Vrp</div>')).add_to(capa_vrp)

        tags_bomba_mapa = []
        for id_p in ids_p:
            if id_p in mapa_pozos_dict:
                p_info = mapa_pozos_dict[id_p]
                t_bomba = p_info.get('bomba')
                if t_bomba and str(t_bomba).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    if str(t_bomba).strip().lower() != 'sin telemetria':
                        if str(t_bomba) not in tags_bomba_mapa:
                            tags_bomba_mapa.append(str(t_bomba))

        scada_res_bombas = cargar_datos_scada([str(t) for t in set(tags_bomba_mapa) if t]) if tags_bomba_mapa else {}

        for id_p in ids_p:
            if id_p in mapa_pozos_dict:
                p_info = mapa_pozos_dict[id_p]
                coord_pz = p_info.get('coord')
                if coord_pz:
                    val_bomba_str = str(p_info.get('bomba', '')).strip()
                    t_pz_q = p_info.get('caudal')
                    val_q_pz, _ = scada_res_reg.get(str(t_pz_q), (0.0, "N/A")) if t_pz_q else (0.0, "N/A")

                    if val_bomba_str.lower() == 'sin telemetria' or not val_bomba_str or val_bomba_str.lower() in ['none', 'n/a', 'null', '0']:
                        color_pz = "#808080"
                        estado_txt = "Sin Telemetría"
                    else:
                        val_bomba_scada, _ = scada_res_bombas.get(val_bomba_str, (0.0, "N/A"))
                        es_encendido = val_bomba_scada > 0.5
                        color_pz = "#00ff00" if es_encendido else "#ff4d4d"
                        estado_txt = 'Encendido' if es_encendido else 'Apagado'
                    
                    id_p_limpio = str(id_p).strip()
                    if id_p_limpio.upper().startswith('PR'):
                        id_p_limpio = 'R' + id_p_limpio[2:]
                    elif id_p_limpio.upper().startswith('PP'):
                        id_p_limpio = id_p_limpio[1:]
                    elif not id_p_limpio.upper().startswith('P') and not id_p_limpio.upper().startswith('R'):
                        id_p_limpio = 'P' + id_p_limpio

                    html_popup_pz = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid {color_pz}; width:200px;"><b style="color:{color_pz};">POZO {id_p_limpio}</b><br>Estado Bomba: {estado_txt}<br>Caudal: {val_q_pz:.2f} L/s</div>"""
                    icon_html_pz = f"""<div style="position: relative; width: 26px; height: 26px;"><div style="width: 16px; height: 16px; background: {color_pz}; border-radius: 50%; box-shadow: 0 0 8px {color_pz}; position: absolute; top: 5px; left: 5px; z-index: 2;"></div></div>"""
                    folium.Marker(location=coord_pz, icon=folium.DivIcon(icon_size=(26, 26), icon_anchor=(13, 13), html=icon_html_pz), popup=folium.Popup(html_popup_pz, max_width=250)).add_to(capa_pozos)
                    folium.Marker(location=coord_pz, icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-12, 15), html=f'<div style="font-size: 8.5pt; color: {color_pz}; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: {color_pz};">{id_p_limpio}</div>')).add_to(capa_pozos)

        folium.LayerControl(collapsed=True).add_to(m_sec)
        Fullscreen(position='topleft').add_to(m_sec)

        folium_static(m_sec, width=None, height=360)

        st.markdown("""
            <div style="
                position: relative;
                margin-top: -175px;
                margin-left: 12px;
                width: 190px;
                background: rgba(11, 26, 41, 0.95);
                backdrop-filter: blur(4px);
                border: 1px solid #1f4068;
                border-radius: 6px;
                padding: 6px 9px;
                font-family: sans-serif;
                font-size: 11px;
                color: #ffffff;
                box-shadow: 0 4px 12px rgba(0,0,0,0.8);
                z-index: 99;
                pointer-events: none;
            ">
                <div style="font-weight: bold; margin-bottom: 3px; color: #00d4ff; border-bottom: 1px solid #1f4068; padding-bottom: 2px;">Leyenda</div>
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
                    <span style="width: 10px; height: 10px; background-color: #ff4d4d; border-radius: 50%; display: inline-block;"></span>
                    <span>Punto crítico</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
                    <span style="width: 10px; height: 10px; background-color: #00ff00; border-radius: 50%; display: inline-block;"></span>
                    <span>Pozos</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
                    <span style="width: 10px; height: 10px; background-color: #007bff; border-radius: 50%; display: inline-block;"></span>
                    <span>Punto de control</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="width: 10px; height: 10px; background-color: #a1ffce; border-radius: 50%; display: inline-block;"></span>
                    <span>Vrp</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    
    with col_der:
        st.markdown(f"""
            <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Comportamiento hidráulico</p>
            </div>
        """, unsafe_allow_html=True)

        fig = go.Figure()

        dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
        meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

        f_ini_dia = f_ini_h.replace(hour=0, minute=0, second=0, microsecond=0)
        f_fin_dia = f_fin_h.replace(hour=23, minute=59, second=59, microsecond=0)
        fechas_lineas = pd.date_range(start=f_ini_dia, end=f_fin_dia, freq='D')
        num_dias = len(fechas_lineas)
        paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
        ticks_filtrados = fechas_lineas[::paso]

        etiquetas_filtradas = [
            f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
            for d in ticks_filtrados
        ]

        idx_q = 0
        idx_p = 0
        colores_azules_pc = ["#8acbf5", "#0088ff", "#3399ff", "#1a75ff"]
        colores_verdes_pc = ["#73e6b0", "#00ffaa", "#00cc66", "#33ff99"]

        # --- 1. GRAFICAR PUNTOS DE CONTROL (Caudal tipo área, Presión normal) ---
        series_puntos_control = [str(r.get('Serie', k)).strip() for k, r in dict_reg.items() if r.get('Serie') or k]
        if series_puntos_control:
            try:
                engine_tel = get_mysql_telemetria_engine()
                series_in_sql = "', '".join(series_puntos_control)
                q_madre_sector = f"""
                    SELECT FECHA_HORA_LOGGER AS Fecha, DISPOSITIVO AS Serie, VARIABLE, VALOR 
                    FROM BD_MADRE 
                    WHERE DISPOSITIVO IN ('{series_in_sql}')
                      AND VARIABLE != 'Volt_bateria'
                      AND FECHA_HORA_LOGGER BETWEEN '{f_ini_h}' AND '{f_fin_h}'
                    ORDER BY FECHA_HORA_LOGGER ASC
                """
                df_madre_sector = pd.read_sql(q_madre_sector, engine_tel)
                
                if not df_madre_sector.empty:
                    df_madre_sector['FECHA'] = pd.to_datetime(df_madre_sector['Fecha'], errors='coerce')
                    df_madre_sector['Serie_str'] = df_madre_sector['Serie'].astype(str).str.strip()
                    
                    is_not_caudal = ~df_madre_sector['VARIABLE'].str.upper().str.contains('CAUDAL', na=False)
                    df_madre_sector['VALOR'] = pd.to_numeric(df_madre_sector['VALOR'], errors='coerce')
                    df_madre_sector.loc[is_not_caudal, 'VALOR'] *= 10.0

                    for r_k, r_info in dict_reg.items():
                        serie_raw = str(r_info.get('Serie', r_k)).strip()
                        nombre_reg = r_info.get('nombre', f"SN:{serie_raw}")
                        df_temp_s = df_madre_sector[df_madre_sector['Serie_str'] == serie_raw]

                        if not df_temp_s.empty:
                            for var_name, df_v_group in df_temp_s.groupby('VARIABLE'):
                                df_v_group = df_v_group.sort_values('FECHA')
                                if df_v_group['VALOR'].notna().any():
                                    is_caudal = 'CAUDAL' in str(var_name).upper()
                                    
                                    var_label_display = str(var_name)
                                    if var_label_display in ["Presion1", "Presion2"]:
                                        var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                                    elif var_label_display == "Caudal1":
                                        var_label_display = "Q1"

                                    if is_caudal:
                                        color_q = colores_azules_pc[idx_q % len(colores_azules_pc)]
                                        idx_q += 1
                                        fig.add_trace(go.Scatter(
                                            x=df_v_group['FECHA'], y=df_v_group['VALOR'],
                                            name=f"{nombre_reg} - {var_label_display}",
                                            yaxis="y1", mode='lines+markers',
                                            line=dict(width=2, color=color_q),
                                            marker=dict(size=4, symbol='circle'),
                                            fill='tozeroy',  # Caudal / Q de tipo área
                                            fillcolor="rgba(138, 203, 245, 0.15)",
                                            hovertemplate=f'<b>{nombre_reg} - {var_label_display}</b>: %{{y:.2f}} L/s<extra></extra>'
                                        ))
                                    else:
                                        color_p = colores_verdes_pc[idx_p % len(colores_verdes_pc)]
                                        idx_p += 1
                                        fig.add_trace(go.Scatter(
                                            x=df_v_group['FECHA'], y=df_v_group['VALOR'],
                                            name=f"{nombre_reg} - {var_label_display}",
                                            yaxis="y2", mode='lines+markers',
                                            line=dict(width=2, color=color_p),
                                            marker=dict(size=4, symbol='circle'),
                                            fill=None,  # Presión normal sin área
                                            hovertemplate=f'<b>{nombre_reg} - {var_label_display}</b>: %{{y:.2f}} mca<extra></extra>'
                                        ))
            except Exception:
                pass

        # --- 2. GRAFICAR VRPs ---
        series_vrp_list = [str(v_info.get('Serie', v_key)) for v_key, v_info in dict_vrp_sec.items() if v_info.get('Serie') or v_key]
        if dict_vrp_sec and series_vrp_list:
            try:
                series_vrp_in = "', '".join(series_vrp_list)
                q_madre_vrp = f"""
                    SELECT FECHA_HORA_LOGGER AS Fecha, DISPOSITIVO AS Serie, VARIABLE, VALOR 
                    FROM BD_MADRE 
                    WHERE DISPOSITIVO IN ('{series_vrp_in}')
                      AND VARIABLE != 'Volt_bateria'
                      AND FECHA_HORA_LOGGER BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59'
                    ORDER BY FECHA_HORA_LOGGER ASC
                """
                df_madre_vrp = pd.read_sql(q_madre_vrp, engine_tel)
                if not df_madre_vrp.empty:
                    df_madre_vrp['FECHA'] = pd.to_datetime(df_madre_vrp['Fecha'], errors='coerce')
                    df_madre_vrp['Serie_str'] = df_madre_vrp['Serie'].astype(str).str.strip()
                    
                    is_not_caudal_vrp = ~df_madre_vrp['VARIABLE'].str.upper().str.contains('CAUDAL', na=False)
                    df_madre_vrp['VALOR'] = pd.to_numeric(df_madre_vrp['VALOR'], errors='coerce')
                    df_madre_vrp.loc[is_not_caudal_vrp, 'VALOR'] *= 10.0
                    
                    colores_vrp = ["#00ffcc", "#28a745", "#a1ffce", "#00cc66"]
                    idx_vrp_c = 0
                    for v_key, v_info in dict_vrp_sec.items():
                        serie_raw = str(v_info.get('Serie', v_key)).strip()
                        nombre_vrp = v_info.get('nombre', f'VRP {serie_raw}')
                        df_temp = df_madre_vrp[df_madre_vrp['Serie_str'] == serie_raw]
                        if not df_temp.empty:
                            for var_name, df_v_group in df_temp.groupby('VARIABLE'):
                                df_v_group = df_v_group.sort_values('FECHA').dropna(subset=['VALOR'])
                                if not df_v_group.empty:
                                    color_trace_vrp = colores_vrp[idx_vrp_c % len(colores_vrp)]
                                    idx_vrp_c += 1
                                    is_q_vrp = 'CAUDAL' in str(var_name).upper()

                                    var_label_display = str(var_name)
                                    if var_label_display in ["Presion1", "Presion2"]:
                                        var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                                    elif var_label_display == "Caudal1":
                                        var_label_display = "Q1"

                                    fig.add_trace(go.Scatter(
                                        x=df_v_group['FECHA'], y=df_v_group['VALOR'],
                                        name=f"{nombre_vrp} - {var_label_display}",
                                        yaxis="y1" if is_q_vrp else "y2", mode='lines+markers',
                                        marker=dict(size=4, symbol='circle'),
                                        line=dict(width=2, color=color_trace_vrp),
                                        fill='tozeroy' if is_q_vrp else None,  # Si es Q en VRP, tipo área
                                        fillcolor="rgba(0, 255, 204, 0.15)" if is_q_vrp else None,
                                        hovertemplate=f'<b>{nombre_vrp} - {var_label_display}</b><br>Valor: %{{y:.2f}}<extra></extra>'
                                    ))
            except Exception:
                pass

        # --- 3. GRAFICAR PUNTOS CRÍTICOS ---
        series_pc_list = [str(pc_info.get('Serie', pc_key)) for pc_key, pc_info in dict_pc_sec.items() if pc_info.get('Serie') or pc_key]
        if dict_pc_sec and series_pc_list:
            try:
                series_pc_in = "', '".join(series_pc_list)
                q_madre_pc_hc = f"""
                    SELECT FECHA_HORA_LOGGER AS Fecha, DISPOSITIVO AS Serie, VARIABLE, VALOR 
                    FROM BD_MADRE 
                    WHERE DISPOSITIVO IN ('{series_pc_in}')
                      AND VARIABLE != 'Volt_bateria'
                      AND VARIABLE NOT LIKE '%CAUDAL%'
                      AND FECHA_HORA_LOGGER BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59'
                    ORDER BY FECHA_HORA_LOGGER ASC
                """
                df_madre_pc_hc = pd.read_sql(q_madre_pc_hc, engine_tel)
                if not df_madre_pc_hc.empty:
                    df_madre_pc_hc['FECHA'] = pd.to_datetime(df_madre_pc_hc['Fecha'], errors='coerce')
                    df_madre_pc_hc['Serie_str'] = df_madre_pc_hc['Serie'].astype(str).str.strip()
                    df_madre_pc_hc['VALOR'] = pd.to_numeric(df_madre_pc_hc['VALOR'], errors='coerce') * 10.0
                    
                    colores_pc_hc = ["#ff4d4d", "#ff8080", "#ffb3b3", "#ff1a1a"]
                    idx_pc_hc = 0
                    for pc_key, pc_info in dict_pc_sec.items():
                        serie_raw = str(pc_info.get('Serie', pc_key)).strip()
                        domicilio_nombre = pc_info.get('Domicilio', pc_info.get('nombre', f'PC {serie_raw}'))
                        df_temp = df_madre_pc_hc[df_madre_pc_hc['Serie_str'] == serie_raw]
                        if not df_temp.empty:
                            for var_name, df_v_group in df_temp.groupby('VARIABLE'):
                                df_v_group = df_v_group.sort_values('FECHA').dropna(subset=['VALOR'])
                                if not df_v_group.empty:
                                    color_trace_pc_hc = colores_pc_hc[idx_pc_hc % len(colores_pc_hc)]
                                    idx_pc_hc += 1

                                    var_label_display = str(var_name)
                                    if var_label_display in ["Presion1", "Presion2"]:
                                        var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                                    elif var_label_display == "Caudal1":
                                        var_label_display = "Q1"

                                    fig.add_trace(go.Scatter(
                                        x=df_v_group['FECHA'], y=df_v_group['VALOR'],
                                        name=f"PC: {domicilio_nombre} - {var_label_display}",
                                        yaxis="y2", mode='lines+markers',
                                        marker=dict(size=4, symbol='circle'),
                                        line=dict(width=2, color=color_trace_pc_hc),
                                        fill=None,
                                        visible='legendonly',
                                        hovertemplate=f'<b>PC: {domicilio_nombre} - {var_label_display}</b><br>Valor: %{{y:.2f}} mca<extra></extra>'
                                    ))
            except Exception:
                pass

        # --- 4. GRAFICAR POZOS DEL SECTOR (Caudal tipo área, Nivel TQ normal sin área) ---
        tags_pozos_visualizar = []
        mapeo_pozos_config = {}
        for id_p in ids_p:
            if id_p in mapa_pozos_dict:
                p_info = mapa_pozos_dict[id_p]
                conf_pz = [
                    ('caudal', f"Pozo {id_p} - Q", "y1"),
                    ('presion', f"Pozo {id_p} - P", "y2"),
                    ('nivel_tanque', "Nivel TQ", "y3")
                ]
                for key_t, lb, axis_target in conf_pz:
                    tag_v = p_info.get(key_t)
                    if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        if str(tag_v) not in tags_pozos_visualizar:
                            tags_pozos_visualizar.append(str(tag_v))
                            mapeo_pozos_config[str(tag_v)] = {'label': lb, 'axis': axis_target}

        if tags_pozos_visualizar:
            try:
                engine_h = get_mysql_scada_engine()
                tags_unicos_query = "', '".join([str(t) for t in set(tags_pozos_visualizar) if t])
                if tags_unicos_query:
                    q_hist = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_unicos_query}') AND h.FECHA BETWEEN '{f_ini_h}' AND '{f_fin_h}' ORDER BY h.FECHA ASC"
                    df_h = pd.read_sql(q_hist, engine_h)

                    if not df_h.empty:
                        df_h['FECHA'] = pd.to_datetime(df_h['FECHA'])
                        for tag_name in tags_pozos_visualizar:
                            df_tag = df_h[df_h['TAG'] == tag_name].sort_values('FECHA')
                            if not df_tag.empty:
                                cfg = mapeo_pozos_config[tag_name]
                                target_axis = cfg['axis']

                                if target_axis == "y1": unidad_pc = "L/s"
                                elif target_axis == "y3": unidad_pc = "m"
                                else: unidad_pc = "mca"

                                val_y_series = pd.to_numeric(df_tag['VALUE'], errors='coerce')
                                if target_axis == "y2":
                                    val_y_series = val_y_series * 10.0

                                if target_axis == "y3":
                                    color_base = "#d400ff"
                                    vis_estado = True
                                    fill_mode = None  # El Nivel del Tanque (TQ) se muestra normal, sin área
                                elif target_axis == "y1":
                                    color_base = "#00d4ff"
                                    vis_estado = 'legendonly'
                                    fill_mode = 'tozeroy'  # Caudal / Q de tipo área
                                else:
                                    color_base = "#00ff00"
                                    vis_estado = 'legendonly'
                                    fill_mode = None

                                fig.add_trace(go.Scatter(
                                    x=df_tag['FECHA'], y=val_y_series, name=cfg['label'], 
                                    yaxis=target_axis, mode='lines+markers',
                                    line=dict(width=2, color=color_base),
                                    marker=dict(size=4, symbol='circle'),
                                    fill=fill_mode,
                                    fillcolor="rgba(0, 212, 255, 0.15)" if fill_mode else None,
                                    visible=vis_estado,
                                    hovertemplate='<b>%{fullData.name}</b>: %{y:.2f} ' + unidad_pc + '<extra></extra>'
                                ))
            except Exception:
                pass

        delta = pd.Timedelta(minutes=7.5)
        for d in fechas_lineas:
            es_lunes = (d.dayofweek == 0)
            fig.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
            fig.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")

        fig.update_layout(
            paper_bgcolor='rgba(11,26,41,1)', plot_bgcolor='rgba(11,26,41,1)', height=380, 
            margin=dict(l=40, r=20, t=25, b=10), hovermode="x unified", 
            legend=dict(
                orientation="h", 
                yanchor="bottom", 
                y=1.04, 
                x=0.5, 
                xanchor="center", 
                font=dict(color="white", size=11),
                itemwidth=30
            ),
            xaxis=dict(domain=[0, 0.90], range=[f_ini_h, f_fin_h], color="#888888", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0),
            
            yaxis=dict(
                title=dict(text="Caudal (L/s)", font=dict(color="#00d4ff")),
                tickfont=dict(color="#00d4ff"),
                color="#00d4ff",
                showgrid=True, 
                gridcolor="#16304a"
            ),
            
            yaxis2=dict(
                title=dict(text="Presión (mca)", font=dict(color="#00ff00"), standoff=15), 
                tickfont=dict(color="#00ff00"),
                side="right", 
                overlaying="y", 
                anchor="free", 
                position=0.94, 
                color="#00ff00", 
                showgrid=False,
                rangemode="tozero",
                tickformat="d",
                showline=True,
                linecolor="#22384d",
                linewidth=1,
                ticks="outside",
                ticklen=6,
                tickwidth=1
            ),
            
            yaxis3=dict(
                title=dict(text="Nivel Tq (mts)", font=dict(color="#d400ff"), standoff=15), 
                tickfont=dict(color="#d400ff"),
                side="right", 
                overlaying="y", 
                anchor="free", 
                position=1.0, 
                color="#d400ff", 
                showgrid=False,
                rangemode="tozero",
                tickformat="d",
                showline=True,
                linecolor="#22384d",
                linewidth=1,
                ticks="outside",
                ticklen=6,
                tickwidth=1
            )
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- FILA INFERIOR: PUNTOS CRÍTICOS (EN TONOS VERDES DIFERENTES) Y DATOS OPERATIVOS ---
    col_pc, col_op = st.columns([1.0, 1.0], gap="medium")

    with col_pc:
        st.markdown("""
            <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Puntos críticos</p>
                <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Presión real en los puntos críticos del sector (Diccionario_puntos_criticos)</p>
            </div>
        """, unsafe_allow_html=True)
        
        fig_pc = go.Figure()
        try:
            if dict_pc_sec and series_pc_list:
                engine_tel = get_mysql_telemetria_engine()
                series_pc_in = "', '".join(series_pc_list)
                q_madre_pc = f"""
                    SELECT FECHA_HORA_LOGGER AS Fecha, DISPOSITIVO AS Serie, VARIABLE, VALOR 
                    FROM BD_MADRE 
                    WHERE DISPOSITIVO IN ('{series_pc_in}')
                      AND VARIABLE != 'Volt_bateria'
                      AND VARIABLE NOT LIKE '%CAUDAL%'
                      AND FECHA_HORA_LOGGER BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59'
                    ORDER BY FECHA_HORA_LOGGER ASC
                """
                df_madre_pc = pd.read_sql(q_madre_pc, engine_tel)
                if not df_madre_pc.empty:
                    df_madre_pc['FECHA'] = pd.to_datetime(df_madre_pc['Fecha'], errors='coerce')
                    df_madre_pc['Serie_str'] = df_madre_pc['Serie'].astype(str).str.strip()
                    df_madre_pc['VALOR'] = pd.to_numeric(df_madre_pc['VALOR'], errors='coerce') * 10.0

                    dias_es_pc = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                    meses_es_pc = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                    f_ini_dia_pc = f_ini_h.replace(hour=0, minute=0, second=0, microsecond=0)
                    f_fin_dia_pc = f_fin_h.replace(hour=23, minute=59, second=59, microsecond=0)
                    fechas_lineas_pc = pd.date_range(start=f_ini_dia_pc, end=f_fin_dia_pc, freq='D')
                    
                    num_dias_pc = len(fechas_lineas_pc)
                    paso_pc = 1 if num_dias_pc <= 15 else (2 if num_dias_pc <= 30 else 5)
                    ticks_pc = fechas_lineas_pc[::paso_pc]
                    
                    etiquetas_pc = [
                        f"{d.strftime('%H:%M')}<br>{dias_es_pc[d.dayofweek]} {d.day}-{meses_es_pc[d.month]}-{d.year}"
                        for d in ticks_pc
                    ]

                    # Tonos verdes diferentes para los puntos críticos
                    colores_verdes_distintos = ["#2ecc71", "#1abc9c", "#27ae60", "#16a085", "#58d68d", "#48c9b0", "#52be80"]
                    idx_pc_c = 0

                    for pc_key, pc_info in dict_pc_sec.items():
                        serie_raw = str(pc_info.get('Serie', pc_key)).strip()
                        domicilio_nombre = pc_info.get('Domicilio', pc_info.get('nombre', f'Serie {serie_raw}'))

                        df_temp = df_madre_pc[df_madre_pc['Serie_str'] == serie_raw]
                        if not df_temp.empty:
                            for var_name, df_v_group in df_temp.groupby('VARIABLE'):
                                df_v_group = df_v_group.sort_values('FECHA').dropna(subset=['VALOR'])
                                if not df_v_group.empty:
                                    color_trace_pc = colores_verdes_distintos[idx_pc_c % len(colores_verdes_distintos)]
                                    idx_pc_c += 1

                                    var_label_display = str(var_name)
                                    if var_label_display in ["Presion1", "Presion2"]:
                                        var_label_display = "P1" if var_label_display == "Presion1" else "P2"
                                    elif var_label_display == "Caudal1":
                                        var_label_display = "Q1"

                                    fig_pc.add_trace(go.Scatter(
                                        x=df_v_group['FECHA'], 
                                        y=df_v_group['VALOR'], 
                                        name=f"{domicilio_nombre} - {var_label_display}", 
                                        mode='lines+markers',
                                        connectgaps=False,
                                        showlegend=True,
                                        marker=dict(size=4, symbol='circle'), 
                                        line=dict(width=2, color=color_trace_pc),
                                        hovertemplate=f'<b>{domicilio_nombre} - {var_label_display}</b><br>Valor: %{{y:.2f}} mca<extra></extra>'
                                    ))

                    delta_h = pd.Timedelta(minutes=7.5)
                    for d in fechas_lineas_pc:
                        es_lunes = (d.dayofweek == 0)
                        fig_pc.add_vrect(x0=d - delta_h, x1=d + delta_h, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                        fig_pc.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")
        except Exception:
            pass

        fig_pc.add_hline(
            y=30, line_dash="dot", line_color="#ffd700", line_width=1.5,
            annotation_text="Máx. 30 mca", annotation_position="top right",
            annotation_font=dict(color="#ffd700", size=11)
        )
        fig_pc.add_hline(
            y=5, line_dash="dot", line_color="#ffd700", line_width=1.5,
            annotation_text="Mín. 5 mca", annotation_position="bottom right",
            annotation_font=dict(color="#ffd700", size=11)
        )

        fig_pc.update_layout(
            paper_bgcolor='rgba(11,26,41,1)', plot_bgcolor='rgba(11,26,41,1)', height=360, 
            margin=dict(l=40, r=40, t=10, b=10), hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.5, xanchor="center", font=dict(color="white", size=12)),
            xaxis=dict(range=[f_ini_h, f_fin_h], color="#888888", showgrid=False, tickvals=ticks_pc if 'ticks_pc' in locals() else None, ticktext=etiquetas_pc if 'etiquetas_pc' in locals() else None, tickangle=0),
            yaxis=dict(tickformat=".2f", color="#2ecc71", showgrid=True, gridcolor="#16304a", title="Presión (mca)")
        )
        st.plotly_chart(fig_pc, use_container_width=True)

    with col_op:
        st.markdown("""
            <style>
                .dma-op-grid .dma-op-row {
                    padding: 0.34rem 0 !important;
                    font-size: 0.82rem !important;
                }
            </style>
            <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Datos operativos</p>
                <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Ficha del sector y últimas lecturas del periodo</p>
            </div>
        """, unsafe_allow_html=True)

        def _svg_op(kind):
            s = 'width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"'
            c_cyan = "#00d4ff"
            c_green = "#2ecc71"
            c_amber = "#ffb020"
            c_red = "#ff5c5c"
            c_purple = "#c77dff"

            icons = {
                "pin": f'<svg {s} stroke="{c_cyan}"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
                "users_group": f'<svg {s} stroke="{c_cyan}"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
                "user": f'<svg {s} stroke="{c_cyan}"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
                "home": f'<svg {s} stroke="{c_cyan}"><path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/></svg>',
                "building": f'<svg {s} stroke="{c_cyan}"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h2m2 0h2M9 11h2m2 0h2M9 15h2m2 0h2"/></svg>',
                "grid": f'<svg {s} stroke="{c_cyan}"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
                "area": f'<svg {s} stroke="{c_cyan}"><path d="M3 20L20 3v17H3z"/><path d="M7 20V11l9-9"/></svg>',
                "ruler": f'<svg {s} stroke="{c_cyan}"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/></svg>',
                "hash": f'<svg {s} stroke="{c_cyan}"><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>',
                "well": f'<svg {s} stroke="{c_cyan}"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2"/></svg>',
                "bolt": f'<svg {s} stroke="{c_cyan}"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
                "cylinder": f'<svg {s} stroke="{c_cyan}"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14a8 3 0 0 0 16 0V5"/></svg>',
                "chart": f'<svg {s} stroke="{c_cyan}"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
                "receipt": f'<svg {s} stroke="{c_cyan}"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1Z"/><line x1="8" y1="7" x2="16" y2="7"/><line x1="8" y1="11" x2="16" y2="11"/><line x1="8" y1="15" x2="13" y2="15"/></svg>',
                "scale": f'<svg {s} stroke="{c_cyan}"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>',
                "drop": f'<svg {s} stroke="{c_cyan}"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>',
                "alert_off": f'<svg {s} stroke="{c_red}"><circle cx="12" cy="12" r="9"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>',
                "wrench": f'<svg {s} stroke="{c_amber}"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
                "currency": f'<svg {s} stroke="{c_green}"><circle cx="12" cy="12" r="9"/><path d="M14.5 9a2.5 2.5 0 0 0-5 0c0 2.5 5 1.5 5 4a2.5 2.5 0 0 1-5 0"/><line x1="12" y1="5.5" x2="12" y2="18.5"/></svg>',
                "trend_down": f'<svg {s} stroke="{c_amber}"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/></svg>',
                "warning": f'<svg {s} stroke="{c_amber}"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
                "file_check": f'<svg {s} stroke="{c_cyan}"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><polyline points="9 15 11 17 15 13"/></svg>',
                "gauge": f'<svg {s} stroke="{c_cyan}"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>',
                "tank": f'<svg {s} stroke="{c_purple}"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M4 13h16"/><circle cx="12" cy="8.5" r="1"/></svg>',
            }
            return icons.get(kind, icons["drop"])

        def _get_val_op(d, *keys):
            if not isinstance(d, dict):
                return None
            norm_map = {}
            for k, v in d.items():
                nk = str(k).strip().lower().replace("-", "_").replace(" ", "_")
                norm_map[nk] = v
            for k in keys:
                nk = str(k).strip().lower().replace("-", "_").replace(" ", "_")
                if nk in norm_map:
                    val = norm_map[nk]
                    if val is not None and not (isinstance(val, float) and pd.isna(val)):
                        return val
            return None

        def _fmt_op(val, suffix="", decimals=2, integer_only=False):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return "N/D"
            txt = str(val).strip()
            if not txt or txt.lower() in ("none", "nan", "nat", "n/d"):
                return "N/D"
            try:
                num = float(txt.replace("%", "").replace(",", "").strip())
                if pd.isna(num):
                    return f"{txt}{suffix}"
                if integer_only:
                    num_str = f"{num:,.0f}"
                else:
                    num_str = f"{num:,.{decimals}f}"
                return f"{num_str}{suffix}"
            except (ValueError, TypeError):
                return f"{txt}{suffix}"

        distrito_val = _get_val_op(datos_s, "Distrito", "DISTRITO") or "Oriente"
        cant_pozos_val = _fmt_op(_get_val_op(datos_s, "Cantidad_Pozos", "CANTIDAD_POZOS"), integer_only=True)
        pozos_sec_raw = _get_val_op(datos_s, "Pozos_Sector", "POZOS_SECTOR")
        pozos_sec_val = str(pozos_sec_raw).strip() if pozos_sec_raw and str(pozos_sec_raw).strip().lower() not in ("none", "nan", "") else "N/D"
        area_val = _fmt_op(_get_val_op(datos_s, "AREA", "Superficie", "AREA_KM"), suffix=" km²", decimals=2)
        long_red_raw = _get_val_op(datos_s, "LONG_RED", "Long_Red")
        long_red_val = _fmt_op(long_red_raw if long_red_raw is not None else 42.6, suffix=" km", decimals=2)

        usuarios_val = _fmt_op(_get_val_op(datos_s, "USUARIOS", "Usuarios"), integer_only=True)
        usu_dom_raw = _get_val_op(datos_s, "USU_DOM", "U_Domesticos")
        usu_dom_val = _fmt_op(usu_dom_raw, integer_only=True)
        pob_2025_raw = _get_val_op(datos_s, "POB_2025", "Poblacion", "POB_TOT_23")
        pob_2025_val = _fmt_op(pob_2025_raw, integer_only=True)

        q_prod_val = _fmt_op(_get_val_op(datos_s, "Q_PROD"), suffix=" L/s", decimals=2)
        vol_prod_mes_val = _fmt_op(_get_val_op(datos_s, "VOL_PROD-MES", "VOL_PROD_MES", "Vol_Prod"), suffix=" m³", decimals=2)
        cons_prom_raw = _get_val_op(datos_s, "CONS_PROM", "Cons_m3", "Demanda")
        cons_prom_val = _fmt_op(cons_prom_raw if cons_prom_raw is not None else demanda_estimada_val, suffix=" m³", decimals=2)
        vol_fact_val = _fmt_op(_get_val_op(datos_s, "VOL_FACT", "Vol_Fact"), suffix=" m³", decimals=2)
        bal_vol_val = _fmt_op(_get_val_op(datos_s, "BAL_VOL", "Balance_Estimado"), suffix=" m³", decimals=2)

        dom_a_val = _fmt_op(_get_val_op(datos_s, "DOM_A"), integer_only=True)
        dom_b_val = _fmt_op(_get_val_op(datos_s, "DOM_B"), integer_only=True)
        dom_c_val = _fmt_op(_get_val_op(datos_s, "DOM_C"), integer_only=True)
        comercial_raw = _get_val_op(datos_s, "COMERCIAL", "U_NoDom")
        comercial_val = _fmt_op(comercial_raw, integer_only=True)

        faltas_agua_val = _fmt_op(_get_val_op(datos_s, "FALTAS_AGUA"), integer_only=True)
        fugas_val = _fmt_op(_get_val_op(datos_s, "FUGAS"), integer_only=True)
        imp_fact_us_val = _fmt_op(_get_val_op(datos_s, "IMP-FACT_US", "IMP_FACT_US"), decimals=2)
        perd_hab_dia_val = _fmt_op(_get_val_op(datos_s, "PERD_HAB_DIA"), suffix=" L/hab/d", decimals=2)
        niv_morosidad_val = _fmt_op(_get_val_op(datos_s, "NIV_MOROSIDAD"), suffix="%", decimals=2)
        fa_usuario_val = _fmt_op(_get_val_op(datos_s, "FA_USUARIO"), decimals=2)

        filas_col1 = [
            ("pin", "Distrito", f"Distrito {distrito_val}"),
            ("users_group", "Pob. 2025", pob_2025_val),
            ("user", "Usuarios", usuarios_val),
            ("home", "Usu. dom.", usu_dom_val),
            ("building", "Comercial", comercial_val),
            ("grid", "Dom. A / B / C", f"{dom_a_val}/{dom_b_val}/{dom_c_val}"),
            ("area", "Área", area_val),
            
        ]

        filas_col2 = [
            ("ruler", "Long. red", long_red_val),
            ("well", "Pozos sector", pozos_sec_val),
            ("bolt", "Q prod.", q_prod_val),
            ("cylinder", "Vol. prod. mes", vol_prod_mes_val),
            ("chart", "Cons. prom.", cons_prom_val),
            ("receipt", "Vol. fact.", vol_fact_val),
            ("scale", "Bal. vol.", bal_vol_val),
           
        ]

        filas_col3 = [
            ("alert_off", "Faltas agua", faltas_agua_val),
            ("wrench", "Fugas", fugas_val),
            ("currency", "Imp. fact./us.", imp_fact_us_val),
            ("trend_down", "Pérd. hab./día", perd_hab_dia_val),
            ("warning", "Morosidad", niv_morosidad_val),
            ("file_check", "FA usuario", fa_usuario_val),
            ("tank", "TQ-055", f"{texto_nivel_tq} · {fec_nivel_tq_str}"),
        ]

        html_col1 = "".join(
            f'<div class="dma-op-row"><span class="dma-op-label">{_svg_op(ico)}{lbl}</span><span class="dma-op-value">{val}</span></div>'
            for ico, lbl, val in filas_col1
        )
        html_col2 = "".join(
            f'<div class="dma-op-row"><span class="dma-op-label">{_svg_op(ico)}{lbl}</span><span class="dma-op-value">{val}</span></div>'
            for ico, lbl, val in filas_col2
        )
        html_col3 = "".join(
            f'<div class="dma-op-row"><span class="dma-op-label">{_svg_op(ico)}{lbl}</span><span class="dma-op-value">{val}</span></div>'
            for ico, lbl, val in filas_col3
        )

        st.markdown(f"""
            <div class="dma-op-grid" style="
                background: #0b1a29;
                border: 1px solid #1f4068;
                border-top: none;
                border-radius: 0 0 8px 8px;
                padding: 8px 16px;
                height: 360px;
                max-height: 360px;
                overflow-y: auto;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0 22px;
                align-content: space-between;
            ">
                <div>{html_col1}</div>
                <div>{html_col2}</div>
                <div>{html_col3}</div>
            </div>
        """, unsafe_allow_html=True)

    st.stop()
    
# 8. SIDEBAR -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-logo"><img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg"></div>', unsafe_allow_html=True)

    if 'centro_mapa' not in st.session_state:
        st.session_state.centro_mapa = [21.8820, -102.2800]
        st.session_state.zoom_inicial = 12.5
    
    with st.expander("🔌 Conexiones BD", expanded=False):
        status_mysql_scada = "OK" if get_mysql_scada_engine() else "ERROR"
        status_mysql_tele = "OK" if get_mysql_telemetria_engine() else "ERROR"
        status_postgres = "OK" if get_postgres_conn() else "ERROR"

        def render_status_line(label, status):
            cls = "status-ok" if status == "OK" else "status-err"
            html = f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <span style="font-weight: bold; font-size: 13px;">{label}</span>
                <span class="status-tag {cls}">{status}</span>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

        render_status_line("BD-Scada:", status_mysql_scada)
        render_status_line("BD-Diccionarios:", status_mysql_tele)
        render_status_line("BD-PostgreSQL:", status_postgres)
    
    lista_pozos_nombres = sorted(list(mapa_pozos_dict.keys()))
    pozo_buscado = st.selectbox(
        "🔍 Localizar Pozo",
        options=[""] + lista_pozos_nombres,
        format_func=lambda x: "Seleccionar" if x == "" else f"📍 {x}"
    )

    lista_tanques_nombres = sorted(list(mapa_tanques_dict.keys()))
    tanque_buscado = st.selectbox(
        "🛢️ Localizar Tanque",
        options=[""] + lista_tanques_nombres,
        format_func=lambda x: "Seleccionar" if x == "" else f"📦 {x} - {mapa_tanques_dict[x]['nombre']}"
    )

    lista_rebombeos_nombres = sorted(list(mapa_rebombeos_dict.keys()))
    rebombeo_buscado = st.selectbox(
        "🧊 Localizar Rebombeo",
        options=[""] + lista_rebombeos_nombres,
        format_func=lambda x: "Seleccionar" if x == "" else f"🔄 {x}"
    )

    lista_sectores = sorted([s['sector'] for s in sectores])
    sector_buscado = st.selectbox(
        "🏘️ Localizar Sector",
        options=[""] + lista_sectores,
        format_func=lambda x: "Seleccionar" if x == "" else f" {x}",
        key="busqueda_sectores"
    )

    if 'gdf_colonias_lista' not in st.session_state:
        st.session_state.gdf_colonias_lista = get_todas_las_colonias()
    
    df_col = st.session_state.gdf_colonias_lista
    if df_col is not None and not df_col.empty and 'Col_atl' in df_col.columns:
        lista_colonias = sorted(df_col['Col_atl'].unique().tolist())
    else:
        lista_colonias = []

    colonia_buscada = st.sidebar.selectbox(
        "🏙️ Localizar Colonia",
        options=[""] + lista_colonias,
        format_func=lambda x: "Seleccionar" if x == "" else f" {x}",
        key="busqueda_colonias"
    )

    datos_sector_resaltado = None
    if pozo_buscado:
        st.session_state.centro_mapa = mapa_pozos_dict[pozo_buscado]['coord']
        st.session_state.zoom_inicial = 18
    elif tanque_buscado:
        st.session_state.centro_mapa = mapa_tanques_dict[tanque_buscado]['coord']
        st.session_state.zoom_inicial = 18
    elif rebombeo_buscado:
        st.session_state.centro_mapa = mapa_rebombeos_dict[rebombeo_buscado]['coord']
        st.session_state.zoom_inicial = 18
    elif sector_buscado:
        datos_s = next((s for s in sectores if s['sector'] == sector_buscado), None)
        if datos_s:
            datos_sector_resaltado = datos_s
            try:
                geom = json.loads(datos_s['geo'])
                coords_raw = geom['coordinates'][0][0][0] if geom['type'] == 'MultiPolygon' else geom['coordinates'][0][0]
                st.session_state.centro_mapa = [coords_raw[1], coords_raw[0]]
                st.session_state.zoom_inicial = 14.5
            except: pass
    elif colonia_buscada and colonia_buscada != "":
        df = st.session_state.gdf_colonias_lista
        if df is not None:
            col_sel = df[df['Col_atl'] == colonia_buscada]
            if not col_sel.empty:
                st.session_state.colonia_resaltada = col_sel.iloc[0]
                centro = st.session_state.colonia_resaltada.geometry.centroid
                st.session_state.centro_mapa = [centro.y, centro.x]
                st.session_state.zoom_inicial = 15.5
    else:
        st.session_state.centro_mapa = [21.8820, -102.2800]
        st.session_state.zoom_inicial = 12.5
        
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
    
    with st.expander(f"🟢 Bombas ON ({len(pozos_on)})", expanded=False):
        for p in sorted(pozos_on): st.write(f"🟢 {p}")
    with st.expander(f"🔴 Bombas OFF ({len(pozos_off)})", expanded=False):
        for p in sorted(pozos_off): st.write(f"🔴 {p}")
    if pozos_falla_com:
        with st.expander(f"⚠️ Falla de Com. ({len(pozos_falla_com)})", expanded=False):
            for p in sorted(pozos_falla_com): st.write(f"🟠 {p}")
    if pozos_sin_telemetria:
        with st.expander(f"⚪ Sin Telemetría ({len(pozos_sin_telemetria)})", expanded=False):
            for p in sorted(pozos_sin_telemetria): st.write(f"⚪ {p}")

    datos_macros = cargar_medidores_desde_db()
    if datos_macros:
        lista_filtrada = []
        for id_medidor, info in datos_macros.items():
            id_str = str(id_medidor).strip()
            nombre = str(info.get('nombre', '')).strip()
            if id_str != '1000' and nombre != 'Sin instalar':
                lista_filtrada.append((id_str, nombre))
        lista_filtrada.sort()
        
        with st.expander(f"🟣 Macromedidores ({len(lista_filtrada)})", expanded=False):
            for id_medidor, nombre in lista_filtrada:
                st.write(f"🟣 {id_medidor}")
    else:
        st.warning("No hay macromedidores disponibles.")

dic_incidencias_activas = obtener_pozos_con_incidencias_hoy() if 'obtener_pozos_con_incidencias_hoy' in globals() else {}             



# ==============================================================================
# 9. ORGANIZACIÓN EN PESTAÑAS (MAPA PRINCIPAL VS INCIDENCIAS VS MIAA TANQUES)
# ==============================================================================

# 1. Obtenemos la pestaña activa de la URL (por defecto "mapa")
query_params = st.query_params
tab_activa = query_params.get("nav", "mapa")

# 2. Inyectamos los estilos CSS para las pestañas inclinadas con efectos de brillo
st.markdown("""
<style>
    .miaa-skew-bar {
        display: flex;
        gap: 10px;
        width: 100%;
        margin-bottom: 25px;
        padding: 5px 0;
    }

    .skew-tab {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        text-decoration: none !important;
        /* Inclinación tipo paralelogramo */
        transform: skewX(-14deg);
        background: linear-gradient(135deg, rgba(8, 25, 50, 0.85) 0%, rgba(4, 12, 25, 0.95) 100%);
        border: 1px solid rgba(0, 140, 255, 0.25);
        border-radius: 6px;
        padding: 12px 10px;
        box-shadow: inset 0 1px 4px rgba(255, 255, 255, 0.08), 0 4px 15px rgba(0, 0, 0, 0.5);
        transition: all 0.3s ease-in-out;
    }

    /* Enderezamos el contenido interno para que el texto y los iconos no salgan chuecos */
    .skew-content {
        transform: skewX(14deg);
        display: flex;
        align-items: center;
        gap: 10px;
        text-align: left;
    }

    .skew-tab span {
        color: #8da4c4;
        font-family: 'Segoe UI', Tahoma, sans-serif;
        font-size: 13px;
        font-weight: 600;
        line-height: 1.2;
        transition: color 0.3s ease;
    }

    .skew-tab img {
        width: 26px;
        height: 26px;
        object-fit: contain;
        filter: brightness(0.8);
        transition: filter 0.3s ease, transform 0.3s ease;
    }

    /* Efecto Hover con vida */
    .skew-tab:hover {
        border-color: rgba(0, 212, 255, 0.6);
        background: linear-gradient(135deg, rgba(12, 38, 75, 0.9) 0%, rgba(6, 20, 40, 0.95) 100%);
    }

    .skew-tab:hover span {
        color: #ffffff;
    }

    .skew-tab:hover img {
        filter: brightness(1.1);
        transform: scale(1.08);
    }

    /* ESTADO ACTIVO: Pestaña brillante con degradado cian intenso y resplandor (idéntico a la imagen) */
    .skew-tab.active {
        background: linear-gradient(135deg, #0055ff 0%, #00d4ff 100%) !important;
        border: 1px solid #00ffff !important;
        box-shadow: 0 0 22px rgba(0, 212, 255, 0.65), inset 0 1px 4px rgba(255, 255, 255, 0.5) !important;
        transform: skewX(-14deg) scale(1.02);
        z-index: 2;
    }

    .skew-tab.active span {
        color: #ffffff !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    }

    .skew-tab.active img {
        filter: brightness(1.2) drop-shadow(0 0 6px rgba(255, 255, 255, 0.8));
        transform: scale(1.1);
    }
</style>
""", unsafe_allow_html=True)

# URL base para conservar tus parámetros de sesión y roles
base_url = f"?access=granted&role={st.session_state.get('rol', 'usuario')}"

# 3. Renderizamos la barra interactiva con columnas de Streamlit
col_n1, col_n2, col_n3, col_n4 = st.columns(4)

with col_n1:
    cls = "active" if tab_activa == "mapa" else ""
    st.markdown(f"""
        <div class="miaa-skew-bar" style="margin:0;">
            <a href="{base_url}&nav=mapa" target="_self" class="skew-tab {cls}">
                <div class="skew-content">
                    <img src="https://cdn-icons-png.flaticon.com/512/854/854878.png">
                    <span>Mapa Principal</span>
                </div>
            </a>
        </div>
    """, unsafe_allow_html=True)

with col_n2:
    cls = "active" if tab_activa == "incidencias" else ""
    st.markdown(f"""
        <div class="miaa-skew-bar" style="margin:0;">
            <a href="{base_url}&nav=incidencias" target="_self" class="skew-tab {cls}">
                <div class="skew-content">
                    <img src="https://cdn-icons-png.flaticon.com/512/564/564619.png">
                    <span>Incidencias Activas<br>y del día</span>
                </div>
            </a>
        </div>
    """, unsafe_allow_html=True)

with col_n3:
    cls = "active" if tab_activa == "tanques" else ""
    st.markdown(f"""
        <div class="miaa-skew-bar" style="margin:0;">
            <a href="{base_url}&nav=tanques" target="_self" class="skew-tab {cls}">
                <div class="skew-content">
                    <img src="https://cdn-icons-png.flaticon.com/512/3105/3105807.png">
                    <span>Miaa Tanques</span>
                </div>
            </a>
        </div>
    """, unsafe_allow_html=True)

with col_n4:
    cls = "active" if tab_activa == "sectores" else ""
    st.markdown(f"""
        <div class="miaa-skew-bar" style="margin:0;">
            <a href="{base_url}&nav=sectores" target="_self" class="skew-tab {cls}">
                <div class="skew-content">
                    <img src="https://cdn-icons-png.flaticon.com/512/3105/3105785.png">
                    <span>Sectores Hidráulicos</span>
                </div>
            </a>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

# =====================================================================================================================================================================================================================================
# PESTAÑA 1 MAPA DE POZOS, TANQUES Y REBOMBEOS
# =====================================================================================================================================================================================================================================
if tab_activa == "mapa":
    st.markdown('<div class="titulo-superior">SISTEMA - AGUASCALIENTES</div>', unsafe_allow_html=True)

    c_total = total_q if 'total_q' in locals() else 0.0
    p_prom = (total_p / max(len(pozos_on), 1)) if 'total_p' in locals() else 0.0

    # 3 Columnas: Mapa más ancho (0.80), separador pequeño (0.02) y panel lateral estrecho (0.18)
    col_mapa, col_capas, col_panel_derecho = st.columns([0.85, 0.01, 0.10])

    with col_panel_derecho:
        st.markdown('<div style="margin-top: 0px;"></div>', unsafe_allow_html=True)
        st.markdown('<h4 style="color: #00d4ff; font-size: 11px; text-align: center; margin-bottom: 16px; letter-spacing: 1px;">// ESTADO GENERAL</h4>', unsafe_allow_html=True)
        
        # Estilos de animación incorporados para que el sistema se vea "vivo"
        st.markdown('''
            <style>
                @keyframes pulse-glow {
                    0% { transform: scale(1); filter: drop-shadow(0 0 2px rgba(46,204,113,0.4)); }
                    50% { transform: scale(1.12); filter: drop-shadow(0 0 8px rgba(46,204,113,0.9)); }
                    100% { transform: scale(1); filter: drop-shadow(0 0 2px rgba(46,204,113,0.4)); }
                }
                @keyframes radar-spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
                @keyframes warning-blink {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.3; }
                }
                @keyframes water-flow {
                    0% { stroke-dashoffset: 24; }
                    100% { stroke-dashoffset: 0; }
                }
                .icon-encendido { animation: pulse-glow 2s infinite ease-in-out; transform-origin: center; }
                .icon-presion { animation: radar-spin 8s infinite linear; transform-origin: center; }
                .icon-alerta { animation: warning-blink 1.2s infinite ease-in-out; }
                .icon-flujo { stroke-dasharray: 6; animation: water-flow 1.5s infinite linear; }
            </style>
        ''', unsafe_allow_html=True)

        # Margen inferior de 40px exactos entre cada indicador
        estilo_tarjeta = "background: linear-gradient(180deg, rgba(11, 26, 41, 0.95) 0%, rgba(0, 0, 0, 1) 100%); border: 1px solid #1f4068; border-radius: 6px; display: flex; align-items: center; margin-bottom: 40px; padding: 6px 8px; box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.5);"

        st.markdown(f'''
            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #52a3f5;">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path class="icon-flujo" d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4m-17.07 7.07l2.83-2.83m8.48-8.48l2.83-2.83"></path><circle cx="12" cy="12" r="3" fill="currentColor"></circle></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">CAUDAL TOTAL</p>
                    <p style="color:#00ffcc; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{c_total:.1f} L/s</p>
                </div>
            </div>

            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #52a3f5;">
                    <svg class="icon-presion" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">PRESIÓN PROMEDIO</p>
                    <p style="color:#ffff00; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{p_prom:.2f} kg</p>
                </div>
            </div>

            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #2ecc71;">
                    <svg class="icon-encendido" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4" fill="currentColor"></circle><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2m-15.07 7.07l1.41-1.41m11.32-11.32l1.41-1.41"></path></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">SITIOS ENCENDIDOS</p>
                    <p style="color:#00ff00; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{len(pozos_on)}</p>
                </div>
            </div>

            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #e74c3c;">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><text x="12" y="16" font-size="11" text-anchor="middle" fill="currentColor" stroke="none" font-weight="bold">A</text></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">SITIOS APAGADOS</p>
                    <p style="color:#ff4d4d; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{len(pozos_off)}</p>
                </div>
            </div>

            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #f39c12;">
                    <svg class="icon-alerta" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">FALLAS COMUNICACIÓN</p>
                    <p style="color:#ffaa00; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{len(pozos_falla_com)}</p>
                </div>
            </div>

            <div style="{estilo_tarjeta}">
                <div style="flex: 0 0 32px; display: flex; justify-content: center; align-items: center; border-right: 1px solid rgba(255,255,255,0.15); padding-right: 6px; margin-right: 6px; color: #95a5a6;">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line><line x1="2" y1="2" x2="22" y2="22"></line></svg>
                </div>
                <div style="flex-grow: 1; text-align: center;">
                    <p style="color:#a0aec0; font-size:0.55rem; font-weight:bold; margin:0 0 2px 0; text-transform:uppercase;">SIN TELEMETRÍA</p>
                    <p style="color:#ffffff; font-size:1.0rem; font-weight:bold; margin:0; font-family:'Courier New', monospace;">{len(pozos_sin_telemetria)}</p>
                </div>
            </div>
        ''', unsafe_allow_html=True)

    with col_mapa:
        st.markdown('<div class="mapa-area">', unsafe_allow_html=True)
        
        m = folium.Map(
            location=st.session_state.centro_mapa, 
            zoom_start=st.session_state.zoom_inicial,
            attribution_control=False,
        )

        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
            attr='Google',
            name='Vista Satélite',
            overlay=False,
            control=True
        ).add_to(m)

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satélite (Esri)',
            overlay=False,
            control=True
        ).add_to(m)

        api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
        folium.TileLayer(
            tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
            name="Vista Nocturna",
            attr='&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains="abcd",
            max_zoom=20,
            overlay=False,
            control=True
        ).add_to(m)

        Fullscreen().add_to(m)

# 9.2. Añadir el resaltado del sector si existe
        if datos_sector_resaltado:
            folium.GeoJson(
                json.loads(datos_sector_resaltado['geo']),
                style_function=lambda x: {'fillColor': '#00d4ff', 'color': '#ffffff', 'weight': 3, 'fillOpacity': 0.4}
            ).add_to(m)

         
# 9.5. RENDERIZADO DE POLÍGONOS DE SECTORES (Diccionario_sectores) ----------------------------------------------------------------------------------------------------------------------------------------------
        if ver_sectores:
            gdf_sectores = get_todos_los_sectores_geo()
            if gdf_sectores is not None and not gdf_sectores.empty:
                lista_incidencias_sec_tooltip = []
                lista_afectacion_sec_tooltip = []
                lista_colonias_sec_tooltip = []
                
                for idx, row in gdf_sectores.iterrows():
                    suma_afec_sec = 0.0
                    descripciones_fallas_sec = []
                    col_atl_raw = str(row.get('Col_atl', ''))
                    if pd.isna(row.get('Col_atl')) or not col_atl_raw.strip():
                        colonias_html = "Sin colonias registradas"
                    else:
                        lista_c = [c.strip() for c in col_atl_raw.split(',') if c.strip()]
                        colonias_html = "<br>".join([f"• {c}" for c in lista_c])
                    lista_colonias_sec_tooltip.append(colonias_html)
                    
                    for i in range(1, 13):
                        pozo_sec = row.get(f'Pozo_{i}')
                        afectacion_sec = row.get(f'Afectacion_{i}')
                        if pd.notna(pozo_sec) and str(pozo_sec).strip():
                            falla = _buscar_incidencia_sitio(pozo_sec, dic_incidencias_activas)
                            if falla is not None:
                                falla_txt = falla.get('diagnostico', falla.get('motivo', 'Activa')) if isinstance(falla, dict) else str(falla)
                                descripciones_fallas_sec.append(f"{pozo_sec}: {falla_txt}")
                                
                                if pd.notna(afectacion_sec):
                                    try:
                                        val_str = str(afectacion_sec).replace('%', '').strip()
                                        suma_afec_sec += float(val_str)
                                    except: pass
                    
                    if descripciones_fallas_sec:
                        lista_incidencias_sec_tooltip.append(" | ".join(descripciones_fallas_sec))
                        lista_afectacion_sec_tooltip.append(f"{int(suma_afec_sec)}%" if suma_afec_sec > 0 else "N/D")
                    else:
                        lista_incidencias_sec_tooltip.append("Ninguna")
                        lista_afectacion_sec_tooltip.append("0%")

                gdf_sectores['Info_Incidencia'] = lista_incidencias_sec_tooltip
                gdf_sectores['Info_Porcentaje'] = lista_afectacion_sec_tooltip
                gdf_sectores['Info_Colonias'] = lista_colonias_sec_tooltip

                fg_sectores = folium.FeatureGroup(name="Sectores Hidráulicos")
                def estilo_final_sector(feature):
                    props = feature.get('properties', {})
                    color_dinamico, afectacion_val = calcular_color_sector(props, dic_incidencias_activas)
                    if afectacion_val > 0:
                        border_color_final = color_dinamico
                        weight_final = 2.5
                        opacity_final = 0.25
                    else:
                        border_color_final = '#2980B9'
                        weight_final = 1
                        opacity_final = 0.08
                    return {'fillColor': color_dinamico, 'color': border_color_final, 'weight': weight_final, 'fillOpacity': opacity_final}

                def estilo_hover_sector(feature):
                    return {'fillOpacity': 0.8, 'weight': 3, 'color': '#FFFFFF'}

                for _, row in gdf_sectores.iterrows():
                    feature_dict = {
                        'type': 'Feature',
                        'geometry': row['geometry'].__geo_interface__,
                        'properties': row.drop('geometry').to_dict()
                    }
                    props = feature_dict['properties']
                    color_dinamico, _ = calcular_color_sector(props, dic_incidencias_activas)
                    nombre_sec = str(props.get('Sector', 'N/A'))
                    sector_encoded = urllib.parse.quote(nombre_sec)
                    url_acceso = f"/?sector={sector_encoded}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                    
                    html_popup_sector = f"""
                    <div style="background: #050505; color: white; padding: 12px; border-radius: 10px; width: 320px; max-height: 300px; overflow-y: auto; border: 2px solid {color_dinamico}; font-family: sans-serif;">
                        <b style="color: #00d4ff; font-size: 15px;">SECTOR: {nombre_sec}</b>
                        <hr style="border: 0.5px solid #333; margin: 6px 0;">
                        <div style="font-size: 11px; line-height: 1.4; margin-bottom: 10px;">
                            <b>Pozos:</b> {props.get('Pozos', 'N/A')}<br>
                            <b>Incidencia:</b> <span style="color: #ff4d4d;">{props.get('Info_Incidencia', 'Ninguna')}</span><br>
                            <b>Afectación:</b> <span style="color: #ffff00;">{props.get('Info_Porcentaje', '0%')}</span><br>
                            <b style="display: block; margin-top: 6px; color: #00ffcc;">Colonias afectadas:</b>
                            <div style="margin-top: 3px; padding-left: 5px; color: #d1d5db; font-size: 10px; max-height: 100px; overflow-y: auto;">
                                {props.get('Info_Colonias', 'Sin registro')}
                            </div>
                        </div>
                        <a href="{url_acceso}" target="_blank" style="display: block; text-align: center; background-color: #00d4ff; color: #0b1a29; text-decoration: none; font-weight: bold; font-size: 12px; padding: 8px; border-radius: 5px; transition: 0.3s;">🚀 ABRIR SECTOR</a>
                    </div>
                    """
                    folium.GeoJson(
                        feature_dict,
                        style_function=estilo_final_sector,
                        highlight_function=estilo_hover_sector,
                        popup=folium.Popup(html_popup_sector, max_width=350),
                        tooltip=f"Sector: {nombre_sec} (Clic para ver detalle)"
                    ).add_to(fg_sectores)
                fg_sectores.add_to(m)

# 9.6. RENDERIZADO DE POLÍGONOS DE COLONIAS --------------------------------------------------------------------------------------------------------------------------------------------------------------------------

        if ver_colonias:
            gdf_colonias = get_todas_las_colonias()
            if gdf_colonias is not None and not gdf_colonias.empty:
                lista_incidencias_tooltip = []
                lista_afectacion_tooltip = []
                
                for idx, row in gdf_colonias.iterrows():
                    suma_afec = 0.0
                    descripciones_fallas = []
                    for i in range(1, 11):
                        pozo_col = row.get(f'Pozo_{i}')
                        afectacion_col = row.get(f'Afectacion_{i}')
                        if pd.notna(pozo_col) and str(pozo_col).strip():
                            falla = _buscar_incidencia_sitio(pozo_col, dic_incidencias_activas)
                            if falla is not None:
                                falla_txt = falla.get('diagnostico', falla.get('motivo', 'Activa')) if isinstance(falla, dict) else str(falla)
                                descripciones_fallas.append(f"{pozo_col}: {falla_txt}")
                                
                                if pd.notna(afectacion_col):
                                    try:
                                        val_str = str(afectacion_col).replace('%', '').strip()
                                        suma_afec += float(val_str)
                                    except: pass
                    
                    if descripciones_fallas:
                        lista_incidencias_tooltip.append(" | ".join(descripciones_fallas))
                        lista_afectacion_tooltip.append(f"{int(suma_afec)}%" if suma_afec > 0 else "N/D")
                    else:
                        lista_incidencias_tooltip.append("Ninguna")
                        lista_afectacion_tooltip.append("0%")

                gdf_colonias['Info_Incidencia'] = lista_incidencias_tooltip
                gdf_colonias['Info_Porcentaje'] = lista_afectacion_tooltip

                fg_colonias = folium.FeatureGroup(name="Colonias")
                def estilo_final(feature):
                    props = feature.get('properties', {})
                    nombre_actual = props.get('Col_atl')
                    col_sel = st.session_state.get('colonia_resaltada')
                    es_match = (col_sel is not None and nombre_actual == col_sel.get('Col_atl'))
                    color_dinamico, afectacion_val = calcular_color_colonia(props, dic_incidencias_activas)
                    fill_color_final = '#F1C40F' if es_match else color_dinamico
                    
                    if es_match:
                        border_color_final, weight_final, opacity_final = '#F39C12', 3, 0.5
                    elif afectacion_val > 0:
                        border_color_final, weight_final, opacity_final = color_dinamico, 2.5, 0.25
                    else:
                        border_color_final, weight_final, opacity_final = '#2980B9', 1, 0.08
                    
                    return {'fillColor': fill_color_final, 'color': border_color_final, 'weight': weight_final, 'fillOpacity': opacity_final}

                def estilo_hover(feature):
                    return {'fillOpacity': 0.8, 'weight': 4, 'color': '#FFFFFF'}

                folium.GeoJson(
                    gdf_colonias,
                    name="Colonias",
                    style_function=estilo_final,
                    highlight_function=estilo_hover,
                    tooltip=folium.GeoJsonTooltip(
                        fields=['Col_atl', 'Pozos', 'Sector', 'Distrito', 'Info_Incidencia', 'Info_Porcentaje'],
                        aliases=['Colonia:', 'Pozos:', 'Sector:', 'Distrito:', 'Incidencia:', 'Afectación:'],
                        localize=True, sticky=True
                    )
                ).add_to(fg_colonias)
                fg_colonias.add_to(m)

# 9.7. RENDERIZADO DE POZOS EN EL MAPA PRINCIPAL  -----------------------------------------------------------------------------------------------------------------------------------------------------------------

        if ver_pozos:  
            fg_pozos = folium.FeatureGroup(name="Pozos", overlay=True, control=True)
            for id_p, info in mapa_pozos_dict.items():
                d = lambda tag: data_scada.get(str(tag).strip(), (0, "N/A"))[0]
                v_q, v_p, v_nt, v_nd, v_sum, v_col = d(info['caudal']), d(info['presion']), d(info['nivel_tanque']), d(info['nivel_dinamico']), d(info['sumergencia']), d(info['columna'])
                vs = [d(v) for v in info['voltajes_l']]
                amps = [d(a) for a in info['amperajes_l']]
                _, f_dt = data_scada.get(info['voltajes_l'][0], (0, "N/A"))
                
                color_final = info.get('color_final', '#00FF00')
                status_label = info.get('status_label', 'OPERANDO')
                blink = info.get('blink', False)

                # --- VALIDACIÓN DE INCIDENCIA ACTIVA ---
                tiene_incidencia = False
                diagnostico_falla = ""
                if 'dic_incidencias_activas' in globals():
                    diagnostico_falla = _buscar_incidencia_sitio(id_p, dic_incidencias_activas)
                    if diagnostico_falla is not None:
                        tiene_incidencia = True
                # -------------------------------------

                id_p_limpio = str(id_p).strip()
                if id_p_limpio.upper().startswith('PR'):
                    id_p_limpio = 'R' + id_p_limpio[2:]
                elif id_p_limpio.upper().startswith('PP'):
                    id_p_limpio = id_p_limpio[1:]
                elif not id_p_limpio.upper().startswith('P') and not id_p_limpio.upper().startswith('R'):
                    id_p_limpio = 'P' + id_p_limpio

                url_grafica = f"?graficar_pozo={urllib.parse.quote(str(id_p))}&nombre={urllib.parse.quote(str(id_p_limpio))}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                
                html_popup = f"""
                <div style="background: #000000; color: white; padding: 12px; border-radius: 10px; width: 320px; border: 2px solid {color_final}; font-family: sans-serif;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <b style="color: #00d4ff; font-size: 16px;">POZO {id_p_limpio}</b>
                        <span style="background-color: {color_final}; color: black; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 10px;">{status_label}</span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
                        <span>Caudal: <b>{v_q:.2f} L/s</b></span> <span>Presión: <b>{v_p:.2f} kg</b></span>
                        <span>N. Tanque: <b>{v_nt:.2f} m</b></span> <span>N. Dinámico: <b>{v_nd:.2f} m</b></span>
                        <span>Sumergencia: <b>{v_sum:.2f} m</b></span> <span>Columna: <b>{v_col:.2f} m</b></span>
                        <span>H. Arranque: <b>{formato_hora(info['h_arranque'])}</b></span> <span>H. Paro: <b>{formato_hora(info['h_paro'])}</b></span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="font-size: 11px; margin-bottom: 4px;">
                        <span>Voltaje: <b>{vs[0]:.1f}V</b> | <b>{vs[1]:.1f}V</b> | <b>{vs[2]:.1f}V</b></span><br>
                        <span>Amperaje: <b>{amps[0]:.1f}A</b> | <b>{amps[1]:.1f}A</b> | <b>{amps[2]:.1f}A</b></span>
                    </div>
                    <div style="font-size: 10px; color: #aaa;">Última lectura: {f_dt}</div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <a href="{url_grafica}" target="_blank" style="display: block; text-align: center; background-color: #00d4ff; color: #0b1a29; text-decoration: none; font-weight: bold; font-size: 12px; padding: 8px; border-radius: 5px; transition: 0.3s;">📈 VER GRÁFICA</a>
                </div>
                """
                
                # --- CONSTRUCCIÓN DEL GLOBO DE INCIDENCIA SI APLICA ---
                html_globo_incidencia = ""
                if tiene_incidencia:
                    html_globo_incidencia = f"""
                    <div style="position: absolute; bottom: 26px; left: 50%; transform: translateX(-50%); z-index: 10; display: flex; flex-direction: column; align-items: center; pointer-events: none;">
                        <div style="background: #b71c1c; color: #ffffff; border: 1.5px solid #ff5252; border-radius: 6px; padding: 2px 7px; font-size: 9px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,0.9); text-transform: uppercase; letter-spacing: 0.5px;">
                            ⚠️ {diagnostico_falla}
                        </div>
                        <div style="width: 2px; height: 10px; background: #ff5252;"></div>
                        <div style="width: 6px; height: 6px; border-radius: 50%; background: #ff5252; margin-top: -2px;"></div>
                    </div>
                    """
                # ------------------------------------------------------

                icon_html = f"""
                <div style="position: relative; width: 26px; height: 26px;">
                    {html_globo_incidencia}
                    <div class="{'blink_me' if blink else ''}" style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, {color_final}aa, {color_final}, #000000); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div>
                    <div style="width: 10px; height: 4px; background: rgba(0,0,0,0.3); border-radius: 50%; position: absolute; bottom: 2px; left: 8px; filter: blur(1px);"></div>
                </div>
                """

                folium.Marker(
                    location=info['coord'],
                    icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html),
                    popup=folium.Popup(html_popup, max_width=350),
                    tooltip=f"Pozo {id_p_limpio} ({status_label})" + (f" [INCIDENCIA: {diagnostico_falla}]" if tiene_incidencia else "")
                ).add_to(fg_pozos)

                html_etiqueta = f"""
                <div style="font-size: 8.5pt; color: {color_final}; font-weight: bold; text-shadow: 1px 1px 3px #000, -1px -1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid {color_final}44; display: inline-block; white-space: nowrap;">
                    {id_p_limpio}
                </div>
                """
                
                folium.Marker(
                    location=info['coord'],
                    icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-12, 15), html=html_etiqueta),
                    tooltip=f"Pozo {id_p_limpio}"
                ).add_to(fg_pozos)
                
            fg_pozos.add_to(m)

# 9.8. RENDERIZADO DE TANQUES EN EL MAPA PRINCIPAL ----------------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_tanques:
            fg_tanques = folium.FeatureGroup(name="Tanques", overlay=True, control=True)
            for id_t, info in mapa_tanques_dict.items():
                val_niv, fecha_niv = data_scada.get(info['tag_nivel'], (0.0, "N/A"))
                porcentaje = min(max((val_niv / info['nivel_max']) * 100, 0), 100)
                
                if porcentaje < 25: color_fill = "#ff4d4d"
                elif porcentaje < 50: color_fill = "#ffff00"
                else: color_fill = "#00ff00"

                url_grafica_tq = f"?graficar_tanque={urllib.parse.quote(str(info['tag_nivel']))}&nombre={urllib.parse.quote(str(info['nombre']))}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                
                html_popup_tq = f"""
                <div style="background: #000000; color: white; padding: 12px; border-radius: 10px; width: 280px; border: 2px solid #00d4ff; font-family: sans-serif;">
                    <b style="color: #00d4ff; font-size: 16px;">{info['nombre']}</b><br>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="font-size: 12px; line-height: 1.5;">
                        <span>Nivel actual: <b>{val_niv:.2f} m</b> ({porcentaje:.1f}%)</span><br>
                        <span>Nivel máximo: <b>{info['nivel_max']:.2f} m</b></span><br>
                        <span>Sitios de extracción: <b>{info['sitios']}</b></span><br>
                        <span>Última lectura: <small style="color: #aaa;">{fecha_niv}</small></span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <a href="{url_grafica_tq}" target="_blank" style="display: block; text-align: center; background-color: #00d4ff; color: #0b1a29; text-decoration: none; font-weight: bold; font-size: 12px; padding: 8px; border-radius: 5px; transition: 0.3s;">📈 VER GRÁFICA</a>
                </div>
                """

                icon_html_tq = f"""
                <div style="position: relative; width: 32px; height: 22px; background: #1a2639; border: 1.5px solid #00d4ff; border-radius: 4px; overflow: hidden; box-shadow: 2px 3px 5px rgba(0,0,0,0.6);">
                    <div style="position: absolute; bottom: 0; left: 0; width: 100%; height: {porcentaje}%; background: {color_fill}; transition: height 0.5s ease;"></div>
                    <div style="position: relative; z-index: 2; font-size: 8px; font-weight: bold; color: white; text-align: center; line-height: 22px; text-shadow: 1px 1px 1px #000;">{porcentaje:.0f}%</div>
                </div>
                """

                folium.Marker(
                    location=info['coord'],
                    icon=folium.DivIcon(icon_size=(32, 22), icon_anchor=(16, 11), html=icon_html_tq),
                    popup=folium.Popup(html_popup_tq, max_width=310),
                    tooltip=f"Tanque {info['nombre']} ({porcentaje:.1f}%)"
                ).add_to(fg_tanques)

                html_etiqueta_tq = f"""
                <div style="font-size: 8.5pt; color: #00d4ff; font-weight: bold; text-shadow: 1px 1px 3px #000, -1px -1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(0,212,255,0.4); display: inline-block; white-space: nowrap;">
                    {info['nombre']}
                </div>
                """
                
                folium.Marker(
                    location=info['coord'],
                    icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-18, 11), html=html_etiqueta_tq),
                    tooltip=f"Tanque {info['nombre']}"
                ).add_to(fg_tanques)

            fg_tanques.add_to(m)

# 9.9. RENDERIZADO DE REBOMBEOS EN EL MAPA PRINCIPAL ---------------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_rebombeos or any(
            _buscar_incidencia_sitio(id_rb, dic_incidencias_activas) is not None
            for id_rb in mapa_rebombeos_dict.keys()
        ):
            fg_rebombeos = folium.FeatureGroup(name="Rebombeos", overlay=True, control=True)
            for id_rb, info in mapa_rebombeos_dict.items():
                d = lambda tag: data_scada.get(str(tag).strip(), (0, "N/A"))[0]
                v_p, v_nt = d(info['presion']), d(info['nivel_tanque'])
                vs = [d(v) for v in info['voltajes_l']]
                amps = [d(a) for a in info['amperajes_l']]
                _, f_dt = data_scada.get(info['presion'], (0, "N/A"))
                
                color_final = info.get('color_final', '#00FF00')
                status_label = info.get('status_label', 'OPERANDO')
                blink = info.get('blink', False)

                # --- VALIDACIÓN DE INCIDENCIA ACTIVA EN REBOMBEOS (REB...) ---
                tiene_incidencia_rb = False
                diagnostico_falla_rb = ""
                if 'dic_incidencias_activas' in globals():
                    diagnostico_falla_rb = _buscar_incidencia_sitio(id_rb, dic_incidencias_activas)
                    if diagnostico_falla_rb is not None:
                        tiene_incidencia_rb = True
                # --------------------------------------------------------------

                html_popup_rb = f"""
                <div style="background: #000000; color: white; padding: 12px; border-radius: 10px; width: 320px; border: 2px solid {color_final}; font-family: sans-serif;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <b style="color: #00d4ff; font-size: 16px;">{info['nombre']}</b>
                        <span style="background-color: {color_final}; color: black; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 10px;">{status_label}</span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
                        <span>Presión: <b>{v_p:.2f} kg</b></span> <span>N. Tanque: <b>{v_nt:.2f} m</b></span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="font-size: 11px; margin-bottom: 4px;">
                        <span>Voltaje: <b>{vs[0]:.1f}V</b> | <b>{vs[1]:.1f}V</b> | <b>{vs[2]:.1f}V</b></span><br>
                        <span>Amperaje: <b>{amps[0]:.1f}A</b> | <b>{amps[1]:.1f}A</b> | <b>{amps[2]:.1f}A</b></span>
                    </div>
                    <div style="font-size: 10px; color: #aaa;">Última lectura: {f_dt}</div>
                </div>
                """

                # --- CONSTRUCCIÓN DEL GLOBO DE INCIDENCIA PARA REBOMBEOS ---
                html_globo_incidencia_rb = ""
                if tiene_incidencia_rb:
                    html_globo_incidencia_rb = f"""
                    <div style="position: absolute; bottom: 26px; left: 50%; transform: translateX(-50%); z-index: 10; display: flex; flex-direction: column; align-items: center; pointer-events: none;">
                        <div style="background: #b71c1c; color: #ffffff; border: 1.5px solid #ff5252; border-radius: 6px; padding: 2px 7px; font-size: 9px; font-weight: bold; white-space: nowrap; box-shadow: 0 2px 6px rgba(0,0,0,0.9); text-transform: uppercase; letter-spacing: 0.5px;">
                            ⚠️ {diagnostico_falla_rb}
                        </div>
                        <div style="width: 2px; height: 10px; background: #ff5252;"></div>
                        <div style="width: 6px; height: 6px; border-radius: 50%; background: #ff5252; margin-top: -2px;"></div>
                    </div>
                    """
                # -----------------------------------------------------------

                icon_html_rb = f"""
                <div style="position: relative; width: 26px; height: 26px;">
                    {html_globo_incidencia_rb}
                    <div class="{'blink_me' if blink else ''}" style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, {color_final}aa, {color_final}, #000000); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div>
                    <div style="width: 10px; height: 4px; background: rgba(0,0,0,0.3); border-radius: 50%; position: absolute; bottom: 2px; left: 8px; filter: blur(1px);"></div>
                </div>
                """

                folium.Marker(
                    location=info['coord'],
                    icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_rb),
                    popup=folium.Popup(html_popup_rb, max_width=350),
                    tooltip=f"Rebombeo {info['nombre']} ({status_label})" + (f" [INCIDENCIA: {diagnostico_falla_rb}]" if tiene_incidencia_rb else "")
                ).add_to(fg_rebombeos)

                html_etiqueta_rb = f"""
                <div style="font-size: 8.5pt; color: {color_final}; font-weight: bold; text-shadow: 1px 1px 3px #000, -1px -1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid {color_final}44; display: inline-block; white-space: nowrap;">
                    {info['nombre']}
                </div>
                """
                
                folium.Marker(
                    location=info['coord'],
                    icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-12, 15), html=html_etiqueta_rb),
                    tooltip=f"Rebombeo {info['nombre']}"
                ).add_to(fg_rebombeos)

            fg_rebombeos.add_to(m)

# 9.10. RENDERIZADO DE MACROMEDIDORES EN EL MAPA PRINCIPAL ---------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_macromedidores:
            datos_macros = cargar_medidores_desde_db()
            if datos_macros:
                fg_macromedidores = folium.FeatureGroup(name="Macromedidores", overlay=True, control=True)
                
                ahora_mac = dt.datetime.now()
                limite_24h = ahora_mac - dt.timedelta(hours=24)

                for id_medidor, info in datos_macros.items():
                    id_str = str(id_medidor).strip()
                    nombre = str(info.get('nombre', '')).strip()
                    
                    if id_str == '1000' or nombre == 'Sin instalar':
                        continue
                        
                    coord = info.get('coord')
                    flujo = info.get('flujo', 0.0)
                    presion = info.get('presion', 0.0)
                    consumo = info.get('consumo', 0.0)
                    ultima_fecha = info.get('ultima_fecha')
                    
                    # --- VERIFICACIÓN DE ÚLTIMAS 24 HORAS ---
                    es_reciente = False
                    fecha_str = "N/A"
                    if ultima_fecha is not None and not pd.isna(ultima_fecha):
                        fecha_str = ultima_fecha.strftime("%d/%m/%Y %H:%M")
                        if ultima_fecha >= limite_24h:
                            es_reciente = True
                            
                    color_m = "#ff00ff" if es_reciente else "#808080"
                    estado_txt_m = "EN LÍNEA" if es_reciente else "SIN COMUNICACIÓN (>24h)"
                    
                    url_grafica_mm = f"?ver_grafico={urllib.parse.quote(id_str)}&nombre={urllib.parse.quote(nombre)}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                    
                    html_popup_mm = f"""
                    <div style="background: #000000; color: white; padding: 12px; border-radius: 10px; width: 320px; border: 2px solid {color_m}; font-family: sans-serif;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <b style="color: #00d4ff; font-size: 16px;">{nombre}</b>
                            <span style="background-color: {color_m}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 10px;">{estado_txt_m}</span>
                        </div>
                        <small style="color: #aaa;">ID: {id_str}</small>
                        <hr style="border: 0.5px solid #333; margin: 8px 0;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 12px;">
                            <span>Flujo: <b>{flujo:.2f} L/s</b></span> <span>Presión: <b>{presion:.2f} kg/cm²</b></span>
                            <span>Consumo: <b>{consumo:.2f} m³</b></span> <span>Última lectura: <b><small>{fecha_str}</small></b></span>
                        </div>
                        <hr style="border: 0.5px solid #333; margin: 8px 0;">
                        <a href="{url_grafica_mm}" target="_blank" style="display: block; text-align: center; background-color: #00d4ff; color: #0b1a29; text-decoration: none; font-weight: bold; font-size: 12px; padding: 8px; border-radius: 5px; transition: 0.3s;">📈 VER GRÁFICA</a>
                    </div>
                    """
                    
                    icon_html_mm = f"""
                    <div style="position: relative; width: 26px; height: 26px;">
                        <div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, {color_m}aa, {color_m}, #000000); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div>
                        <div style="width: 10px; height: 4px; background: rgba(0,0,0,0.3); border-radius: 50%; position: absolute; bottom: 2px; left: 8px; filter: blur(1px);"></div>
                    </div>
                    """

                    folium.Marker(
                        location=coord,
                        icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_mm),
                        popup=folium.Popup(html_popup_mm, max_width=350),
                        tooltip=f"{nombre} ({id_str}) - {estado_txt_m}"
                    ).add_to(fg_macromedidores)
                    
                    html_etiqueta_mm = f"""
                    <div style="font-size: 8.5pt; color: {color_m}; font-weight: bold; text-shadow: 1px 1px 3px #000, -1px -1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid {color_m}44; display: inline-block; white-space: nowrap;">
                        {id_str}
                    </div>
                    """
                    
                    folium.Marker(
                        location=coord,
                        icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-12, 15), html=html_etiqueta_mm),
                        tooltip=f"{nombre} ({id_str})"
                    ).add_to(fg_macromedidores)
                    
                fg_macromedidores.add_to(m)

        folium.LayerControl(collapsed=True).add_to(m)
        
        st_data = st_folium(m, width="100%", height=680, returned_objects=[])
        st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================================================================================================================================================================================
# PESTAÑA 2: INCIDENCIAS ACTIVAS Y DEL DÍA
# =====================================================================================================================================================================================================================================

elif tab_activa == "incidencias":
    st.markdown("""
        <style>
            .card-incidencia-activa { background: linear-gradient(145deg, rgba(16, 36, 62, 0.9), rgba(8, 20, 38, 0.95)); border: 1px solid rgba(255, 77, 77, 0.4); border-left: 5px solid #ff4d4d; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4); }
            .card-incidencia-cerrada { background: linear-gradient(145deg, rgba(16, 36, 62, 0.8), rgba(8, 20, 38, 0.9)); border: 1px solid rgba(46, 204, 113, 0.35); border-left: 5px solid #2ecc71; border-radius: 10px; padding: 12px 15px; margin-bottom: 10px; }
            .badge-estado { padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; display: inline-block; }
            .badge-activa { background-color: rgba(255, 77, 77, 0.2); color: #ff6b6b; border: 1px solid #ff4d4d; }
            .badge-cerrada { background-color: rgba(46, 204, 113, 0.2); color: #2ecc71; border: 1px solid #2ecc71; }
            .badge-retraso { background-color: rgba(255, 193, 7, 0.2); color: #ffc107; border: 1px solid #ffc107; }
            .duracion-box { background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(0, 212, 255, 0.25); border-radius: 8px; padding: 6px 10px; text-align: center; font-family: 'Courier New', monospace; }
            .metric-card-inc { background: rgba(11, 26, 41, 0.85); border: 1px solid #1f4068; border-radius: 10px; padding: 12px; text-align: center; }
        </style>
    """, unsafe_allow_html=True)

    df_inc = get_data()

    if df_inc is not None and not df_inc.empty:
        df_inc['ESTATUS_NORM'] = df_inc['ESTATUS'].astype(str).str.strip().str.upper()
        df_inc['INICIO_DT'] = pd.to_datetime(df_inc['FECHA_HORA_INICIO'], errors='coerce')
        df_inc['FIN_DT'] = pd.to_datetime(df_inc['FECHA_HORA_FIN'], errors='coerce')

        ahora_inc = dt.datetime.now()
        hoy_date = ahora_inc.date()

        df_activas = df_inc[df_inc['ESTATUS_NORM'] != 'CERRADA'].copy()
        df_cerradas_hoy = df_inc[
            (df_inc['ESTATUS_NORM'] == 'CERRADA') & 
            (df_inc['FIN_DT'].dt.date == hoy_date)
        ].copy()

        total_activas = len(df_activas)
        total_cerradas_hoy = len(df_cerradas_hoy)

        def calcular_duracion(inicio, fin=None):
            if pd.isna(inicio):
                return "N/D", False
            referencia = fin if (fin is not None and not pd.isna(fin)) else ahora_inc
            diff = referencia - inicio
            if diff.total_seconds() < 0:
                diff = dt.timedelta(seconds=0)
            dias = diff.days
            horas, rem = divmod(diff.seconds, 3600)
            minutos, _ = divmod(rem, 60)
            if dias > 0:
                txt = f"{dias}d {horas:02d}h {minutos:02d}m"
            else:
                txt = f"{horas:02d}h {minutos:02d}m"
            excede_24h = (fin is None) and (diff.total_seconds() >= 86400)
            return txt, excede_24h

        retrasos_24h = 0
        for _, r_a in df_activas.iterrows():
            _, exc = calcular_duracion(r_a['INICIO_DT'], None)
            if exc:
                retrasos_24h += 1

        c_m1, c_m2, c_m3 = st.columns(3)
        with c_m1:
            st.markdown(f"""
                <div class="metric-card-inc">
                    <div style="color: #8da4c4; font-size: 12px; font-weight: bold;">INCIDENCIAS ACTIVAS</div>
                    <div style="color: #ff6b6b; font-size: 28px; font-weight: bold; font-family: 'Courier New', monospace;">{total_activas}</div>
                </div>
            """, unsafe_allow_html=True)
        with c_m2:
            st.markdown(f"""
                <div class="metric-card-inc">
                    <div style="color: #8da4c4; font-size: 12px; font-weight: bold;">CERRADAS HOY</div>
                    <div style="color: #2ecc71; font-size: 28px; font-weight: bold; font-family: 'Courier New', monospace;">{total_cerradas_hoy}</div>
                </div>
            """, unsafe_allow_html=True)
        with c_m3:
            st.markdown(f"""
                <div class="metric-card-inc">
                    <div style="color: #8da4c4; font-size: 12px; font-weight: bold;">ACTIVAS +24 HORAS</div>
                    <div style="color: #ffc107; font-size: 28px; font-weight: bold; font-family: 'Courier New', monospace;">{retrasos_24h}</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)

        f_col1, f_col2 = st.columns([2, 1])
        with f_col1:
            filtro_busqueda = st.text_input("🔎 Buscar por pozo / rebombeo, colonia, diagnóstico o responsable:", placeholder="Ej. P-045, REB-01, Morelos, Bomba...")
        with f_col2:
            solo_mas_24h = st.checkbox("⏱️ Solo activas > 24h", value=False)

        if filtro_busqueda and filtro_busqueda.strip():
            termino = filtro_busqueda.strip().lower()
            mask_act = df_activas.apply(lambda row: termino in str(row.values).lower(), axis=1)
            df_activas = df_activas[mask_act]
            mask_cer = df_cerradas_hoy.apply(lambda row: termino in str(row.values).lower(), axis=1)
            df_cerradas_hoy = df_cerradas_hoy[mask_cer]

        if solo_mas_24h:
            indices_24h = []
            for idx_row, r_a in df_activas.iterrows():
                _, exc = calcular_duracion(r_a['INICIO_DT'], None)
                if exc:
                    indices_24h.append(idx_row)
            df_activas = df_activas.loc[indices_24h]

        col_activas, col_cerradas = st.columns([1.25, 1], gap="large")

        with col_activas:
            st.markdown(f"### 🚨 Incidencias Activas ({len(df_activas)})")
            if df_activas.empty:
                st.info("No hay incidencias activas que coincidan con el filtro.")
            else:
                for _, row in df_activas.iterrows():
                    num_pozo = str(row.get('NUM_POZO', 'N/D')).strip()
                    colonia = str(row.get('COLONIA', 'N/D')).strip()
                    diagnostico = str(row.get('DIAGNOSTICO_FALLA', 'Sin diagnóstico')).strip()
                    responsable = str(row.get('RESPONSABLE', 'No asignado')).strip()
                    tiempo_est = str(row.get('TIEMPO_ESTIMADO_ATENCION', 'No especificado')).strip()
                    estatus_txt = str(row.get('ESTATUS', 'ACTIVA')).strip()
                    inicio_dt = row.get('INICIO_DT')
                    inicio_str = inicio_dt.strftime("%d/%m/%Y %H:%M") if pd.notna(inicio_dt) else "N/D"

                    dur_str, exc_24 = calcular_duracion(inicio_dt, None)
                    badge_24_html = '<span class="badge-estado badge-retraso" style="margin-left:6px;">+24H</span>' if exc_24 else ''

                    st.markdown(f"""
                        <div class="card-incidencia-activa">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
                                <div>
                                    <span style="color: #00d4ff; font-size: 17px; font-weight: bold;">📍 {num_pozo}</span>
                                    <span class="badge-estado badge-activa" style="margin-left: 8px;">{estatus_txt}</span>
                                    {badge_24_html}
                                    <div style="color: #dce7f7; font-size: 13px; margin-top: 4px;"><b>Colonia:</b> {colonia}</div>
                                </div>
                                <div class="duracion-box">
                                    <div style="color: #8da4c4; font-size: 10px;">TIEMPO ACTIVA</div>
                                    <div style="color: {'#ffc107' if exc_24 else '#00d4ff'}; font-size: 13px; font-weight: bold;">{dur_str}</div>
                                </div>
                            </div>
                            <hr style="border: 0.5px solid rgba(255,255,255,0.1); margin: 8px 0;">
                            <div style="font-size: 12px; color: #c9d8eb; line-height: 1.5;">
                                <div><b>🔧 Diagnóstico:</b> {diagnostico}</div>
                                <div><b>👷 Responsable:</b> {responsable}</div>
                                <div><b>⏳ Tiempo estimado:</b> {tiempo_est}</div>
                                <div><b>🕒 Inicio:</b> {inicio_str}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

        with col_cerradas:
            st.markdown(f"### ✅ Cerradas Hoy ({len(df_cerradas_hoy)})")
            if df_cerradas_hoy.empty:
                st.info("Aún no se registran incidencias cerradas el día de hoy.")
            else:
                for _, row in df_cerradas_hoy.iterrows():
                    num_pozo = str(row.get('NUM_POZO', 'N/D')).strip()
                    colonia = str(row.get('COLONIA', 'N/D')).strip()
                    diagnostico = str(row.get('DIAGNOSTICO_FALLA', 'Sin diagnóstico')).strip()
                    responsable = str(row.get('RESPONSABLE', 'No asignado')).strip()
                    inicio_dt = row.get('INICIO_DT')
                    fin_dt = row.get('FIN_DT')
                    inicio_str = inicio_dt.strftime("%d/%m %H:%M") if pd.notna(inicio_dt) else "N/D"
                    fin_str = fin_dt.strftime("%d/%m %H:%M") if pd.notna(fin_dt) else "N/D"

                    dur_cierre_str, _ = calcular_duracion(inicio_dt, fin_dt)

                    st.markdown(f"""
                        <div class="card-incidencia-cerrada">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <span style="color: #2ecc71; font-size: 15px; font-weight: bold;">✔️ {num_pozo}</span>
                                    <span class="badge-estado badge-cerrada" style="margin-left: 6px;">CERRADA</span>
                                </div>
                                <span style="color: #8da4c4; font-size: 11px; font-family: 'Courier New', monospace;">Duración: <b>{dur_cierre_str}</b></span>
                            </div>
                            <div style="font-size: 12px; color: #c9d8eb; margin-top: 6px; line-height: 1.45;">
                                <div><b>Colonia:</b> {colonia}</div>
                                <div><b>Diagnóstico:</b> {diagnostico}</div>
                                <div><b>Responsable:</b> {responsable}</div>
                                <div style="color: #9ab0c7; font-size: 11px; margin-top: 3px;">Inicio: {inicio_str} &nbsp;|&nbsp; Fin: {fin_str}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
    else:
        st.warning("No se encontraron registros de incidencias en la base de datos.")

# =====================================================================================================================================================================================================================================
# PESTAÑA 3: MIAA TANQUES
# =====================================================================================================================================================================================================================================

elif tab_activa == "tanques":
    st.markdown("""
        <style>
            .tq-card {
                background: linear-gradient(145deg, rgba(14, 32, 56, 0.95), rgba(6, 15, 28, 0.98));
                border: 1px solid rgba(0, 212, 255, 0.35);
                border-radius: 12px;
                padding: 14px;
                margin-bottom: 14px;
                box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
                transition: transform 0.2s ease, border-color 0.2s ease;
            }
            .tq-card:hover {
                transform: translateY(-2px);
                border-color: #00d4ff;
            }
            .tq-visual-wrap {
                position: relative;
                width: 64px;
                height: 82px;
                background: rgba(5, 14, 26, 0.9);
                border: 2px solid #00d4ff;
                border-radius: 8px;
                overflow: hidden;
                flex-shrink: 0;
                box-shadow: inset 0 0 10px rgba(0, 212, 255, 0.25);
            }
            .tq-liquid {
                position: absolute;
                bottom: 0;
                left: 0;
                width: 100%;
                transition: height 0.5s ease;
                opacity: 0.88;
            }
            .tq-pct-overlay {
                position: relative;
                z-index: 2;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: 'Courier New', monospace;
                font-weight: bold;
                font-size: 14px;
                color: #ffffff;
                text-shadow: 0 0 5px #000000, 1px 1px 2px #000000;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("### 🛢️ Monitoreo de Tanques")

    if not mapa_tanques_dict:
        st.warning("No hay tanques configurados en `Diccionario_de_tanques`.")
    else:
        resumen_tq = []
        for id_t, info in mapa_tanques_dict.items():
            val_niv, fecha_niv = data_scada.get(info['tag_nivel'], (0.0, "N/A"))
            try:
                val_niv_num = float(val_niv) if val_niv is not None else 0.0
            except (ValueError, TypeError):
                val_niv_num = 0.0

            n_max = float(info.get('nivel_max', 1.0) or 1.0)
            if n_max <= 0:
                n_max = 1.0

            pct = max(0.0, min((val_niv_num / n_max) * 100.0, 100.0))

            if pct < 25:
                estado_tq = "CRÍTICO"
                color_tq = "#ff4d4d"
            elif pct < 50:
                estado_tq = "PRECAUCIÓN"
                color_tq = "#ffc107"
            else:
                estado_tq = "NORMAL"
                color_tq = "#2ecc71"

            resumen_tq.append({
                "id": id_t,
                "nombre": info.get("nombre", id_t),
                "nivel": val_niv_num,
                "nivel_max": n_max,
                "pct": pct,
                "sitios": info.get("sitios", "N/D"),
                "fecha": fecha_niv,
                "tag_nivel": info.get("tag_nivel", ""),
                "estado": estado_tq,
                "color": color_tq
            })

        total_tq = len(resumen_tq)
        tq_criticos = sum(1 for x in resumen_tq if x["estado"] == "CRÍTICO")
        tq_precaucion = sum(1 for x in resumen_tq if x["estado"] == "PRECAUCIÓN")
        tq_normales = sum(1 for x in resumen_tq if x["estado"] == "NORMAL")
        prom_pct_tq = sum(x["pct"] for x in resumen_tq) / max(total_tq, 1)

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">TANQUES MONITOREADOS</p>
                    <p class="card-value" style="color: #00d4ff;">{total_tq}</p>
                </div>
            """, unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">NIVEL PROMEDIO</p>
                    <p class="card-value" style="color: #00ffcc;">{prom_pct_tq:.1f}%</p>
                </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">NIVEL CRÍTICO (&lt;25%)</p>
                    <p class="card-value" style="color: #ff4d4d;">{tq_criticos}</p>
                </div>
            """, unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">NORMAL / PRECAUCIÓN</p>
                    <p class="card-value" style="color: #2ecc71;">{tq_normales} <span style="font-size: 1rem; color: #ffc107;">/ {tq_precaucion}</span></p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

        c_fil1, c_fil2 = st.columns([2, 1])
        with c_fil1:
            buscar_tq = st.text_input("🔎 Buscar tanque por nombre, clave o sitio:", placeholder="Ej. TQ-055, Oriente, Pozo...")
        with c_fil2:
            filtro_estado_tq = st.selectbox("Filtrar por nivel:", ["Todos", "CRÍTICO (<25%)", "PRECAUCIÓN (25%-50%)", "NORMAL (>50%)"])

        filtrados_tq = []
        for item in resumen_tq:
            if buscar_tq and buscar_tq.strip():
                b_low = buscar_tq.strip().lower()
                texto_busqueda = f"{item['id']} {item['nombre']} {item['sitios']}".lower()
                if b_low not in texto_busqueda:
                    continue

            if filtro_estado_tq == "CRÍTICO (<25%)" and item["estado"] != "CRÍTICO":
                continue
            elif filtro_estado_tq == "PRECAUCIÓN (25%-50%)" and item["estado"] != "PRECAUCIÓN":
                continue
            elif filtro_estado_tq == "NORMAL (>50%)" and item["estado"] != "NORMAL":
                continue

            filtrados_tq.append(item)

        if not filtrados_tq:
            st.info("No hay tanques que coincidan con el filtro seleccionado.")
        else:
            cols_por_fila = 3
            for i in range(0, len(filtrados_tq), cols_por_fila):
                fila_items = filtrados_tq[i:i + cols_por_fila]
                grid_cols = st.columns(cols_por_fila, gap="medium")
                for idx_c, tq in enumerate(fila_items):
                    with grid_cols[idx_c]:
                        url_graf_tq = f"?graficar_tanque={urllib.parse.quote(str(tq['tag_nivel']))}&nombre={urllib.parse.quote(str(tq['nombre']))}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                        st.markdown(f"""
                            <div class="tq-card">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                    <div>
                                        <div style="color: #00d4ff; font-weight: bold; font-size: 15px;">{tq['nombre']}</div>
                                        <div style="color: #8da4c4; font-size: 11px;">ID: {tq['id']}</div>
                                    </div>
                                    <span style="background: {tq['color']}22; color: {tq['color']}; border: 1px solid {tq['color']}; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: bold;">
                                        {tq['estado']}
                                    </span>
                                </div>
                                <div style="display: flex; gap: 14px; align-items: center;">
                                    <div class="tq-visual-wrap">
                                        <div class="tq-liquid" style="height: {tq['pct']:.1f}%; background: {tq['color']};"></div>
                                        <div class="tq-pct-overlay">{tq['pct']:.0f}%</div>
                                    </div>
                                    <div style="font-size: 12px; color: #d8e6f8; line-height: 1.55; flex-grow: 1;">
                                        <div><b>Nivel actual:</b> <span style="color: {tq['color']}; font-weight: bold;">{tq['nivel']:.2f} m</span></div>
                                        <div><b>Nivel máx.:</b> {tq['nivel_max']:.2f} m</div>
                                        <div><b>Sitios:</b> {tq['sitios']}</div>
                                        <div style="color: #8da4c4; font-size: 11px;"><b>Lectura:</b> {tq['fecha']}</div>
                                    </div>
                                </div>
                                <div style="margin-top: 12px;">
                                    <a href="{url_graf_tq}" target="_blank" style="display: block; text-align: center; background-color: #00d4ff; color: #050a10; text-decoration: none; font-weight: bold; font-size: 12px; padding: 7px; border-radius: 6px;">
                                        📈 VER HISTÓRICO DE NIVEL
                                    </a>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

# =====================================================================================================================================================================================================================================
# PESTAÑA 4: SECTORES HIDRÁULICOS
# =====================================================================================================================================================================================================================================

elif tab_activa == "sectores":
    st.markdown("""
        <style>
            .sec-card {
                background: linear-gradient(145deg, rgba(12, 30, 52, 0.95), rgba(5, 14, 26, 0.98));
                border: 1px solid rgba(0, 212, 255, 0.3);
                border-left: 4px solid #00d4ff;
                border-radius: 10px;
                padding: 14px 16px;
                margin-bottom: 12px;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4);
            }
            .sec-card-afectado {
                border-left: 4px solid #ff4d4d;
                border-color: rgba(255, 77, 77, 0.45);
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("### 🏘️ Sectores Hidráulicos")

    if not sectores:
        st.warning("No se pudieron cargar los sectores hidráulicos desde PostgreSQL.")
    else:
        gdf_sec_info = get_todos_los_sectores_geo()
        mapa_sec_incidencias = {}

        if gdf_sec_info is not None and not gdf_sec_info.empty:
            for _, r_geo in gdf_sec_info.iterrows():
                nom_s = str(r_geo.get('Sector', '')).strip()
                fallas_s = []
                afec_s = 0.0
                for idx_p in range(1, 13):
                    pz_col = r_geo.get(f'Pozo_{idx_p}')
                    af_col = r_geo.get(f'Afectacion_{idx_p}')
                    if pd.notna(pz_col) and str(pz_col).strip():
                        diag_p = _buscar_incidencia_sitio(pz_col, dic_incidencias_activas)
                        if diag_p is not None:
                            fallas_s.append(f"{pz_col} ({diag_p})")
                            if pd.notna(af_col):
                                try:
                                    afec_s += float(str(af_col).replace('%', '').strip())
                                except:
                                    pass
                mapa_sec_incidencias[nom_s] = {
                    "tiene_falla": len(fallas_s) > 0,
                    "detalle": ", ".join(fallas_s) if fallas_s else "Sin incidencia",
                    "afectacion": afec_s
                }

        total_sectores = len(sectores)
        sectores_con_falla = sum(
            1 for s in sectores
            if mapa_sec_incidencias.get(str(s.get('sector', '')).strip(), {}).get("tiene_falla", False)
        )
        total_usuarios_sec = 0
        for s in sectores:
            try:
                u_val = s.get('USUARIOS')
                if u_val is not None and not pd.isna(u_val):
                    total_usuarios_sec += float(str(u_val).replace(',', '').strip())
            except:
                pass

        s_k1, s_k2, s_k3 = st.columns(3)
        with s_k1:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">TOTAL DE SECTORES</p>
                    <p class="card-value" style="color: #00d4ff;">{total_sectores}</p>
                </div>
            """, unsafe_allow_html=True)
        with s_k2:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">SECTORES CON INCIDENCIA</p>
                    <p class="card-value" style="color: {'#ff4d4d' if sectores_con_falla > 0 else '#2ecc71'};">{sectores_con_falla}</p>
                </div>
            """, unsafe_allow_html=True)
        with s_k3:
            st.markdown(f"""
                <div class="card-indicador">
                    <p class="card-label">USUARIOS REGISTRADOS</p>
                    <p class="card-value" style="color: #00ffcc;">{total_usuarios_sec:,.0f}</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

        sf1, sf2 = st.columns([2, 1])
        with sf1:
            buscar_sec = st.text_input("🔎 Buscar sector o sitio asociado:", placeholder="Ej. Oriente, P-012, REB-01...")
        with sf2:
            solo_falla_sec = st.checkbox("⚠️ Solo sectores con incidencia activa", value=False)

        sectores_filtrados = []
        for s in sectores:
            nom_sec = str(s.get('sector', 'N/D')).strip()
            pozos_sec_txt = str(s.get('Pozos_Sector', 'N/D')).strip()
            info_inc_s = mapa_sec_incidencias.get(nom_sec, {"tiene_falla": False, "detalle": "Sin incidencia", "afectacion": 0.0})

            if solo_falla_sec and not info_inc_s["tiene_falla"]:
                continue

            if buscar_sec and buscar_sec.strip():
                b_txt = buscar_sec.strip().lower()
                if b_txt not in f"{nom_sec} {pozos_sec_txt} {info_inc_s['detalle']}".lower():
                    continue

            sectores_filtrados.append((s, info_inc_s))

        if not sectores_filtrados:
            st.info("No se encontraron sectores con los filtros aplicados.")
        else:
            for s_item, inc_info in sectores_filtrados:
                nom_sec = str(s_item.get('sector', 'N/D')).strip()
                sec_enc = urllib.parse.quote(nom_sec)
                url_det_sec = f"/?sector={sec_enc}&access=granted&role={st.session_state.get('rol', 'usuario')}"

                def _dato_limpio(clave, sufijo="", dec=2, entero=False):
                    v = s_item.get(clave)
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return "N/D"
                    try:
                        num = float(str(v).replace('%', '').replace(',', '').strip())
                        if entero:
                            return f"{num:,.0f}{sufijo}"
                        return f"{num:,.{dec}f}{sufijo}"
                    except:
                        return f"{v}{sufijo}"

                ef_txt = _dato_limpio("EF", "%", 0)
                anf_txt = _dato_limpio("ANF", "%", 0)
                dot_txt = _dato_limpio("DOTACION", " L/hab/d", 0, entero=True)
                usu_txt = _dato_limpio("USUARIOS", "", 0, entero=True)
                pozos_txt = str(s_item.get('Pozos_Sector') or 'N/D')

                clase_extra = "sec-card-afectado" if inc_info["tiene_falla"] else ""
                estado_badge = (
                    f'<span style="background: rgba(255,77,77,0.2); color: #ff6b6b; border: 1px solid #ff4d4d; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: bold;">⚠️ {inc_info["detalle"]}</span>'
                    if inc_info["tiene_falla"]
                    else '<span style="background: rgba(46,204,113,0.18); color: #2ecc71; border: 1px solid #2ecc71; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: bold;">✔️ SIN INCIDENCIA</span>'
                )

                st.markdown(f"""
                    <div class="sec-card {clase_extra}">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                            <div>
                                <span style="color: #00d4ff; font-size: 17px; font-weight: bold;">Sector: {nom_sec}</span>
                                <span style="margin-left: 10px;">{estado_badge}</span>
                            </div>
                            <a href="{url_det_sec}" target="_blank" style="background-color: #00d4ff; color: #050a10; text-decoration: none; font-weight: bold; font-size: 12px; padding: 6px 14px; border-radius: 6px;">
                                🚀 ABRIR MONITOREO
                            </a>
                        </div>
                        <hr style="border: 0.5px solid rgba(255,255,255,0.1); margin: 8px 0;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; font-size: 12px; color: #d6e4f5;">
                            <div><b>Usuarios:</b> {usu_txt}</div>
                            <div><b>Eficiencia Física:</b> {ef_txt}</div>
                            <div><b>ANF:</b> {anf_txt}</div>
                            <div><b>Dotación:</b> {dot_txt}</div>
                            <div style="grid-column: span 2;"><b>Sitios / Pozos:</b> {pozos_txt}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
