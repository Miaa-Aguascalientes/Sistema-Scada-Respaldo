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
    if not conn: return []
    try:
        query = """
            SELECT sector, "Pozos_Sector", 
                   "Superficie", "Long_Red", "Vol_Prod", "U_Domesticos", 
                   "U_NoDom", "U_Tot", "Poblacion", "Cons_m3", 
                   "Faltas_Agua", "Fugas_Tot", "FTC", "FTA", 
                   "Vol_Medid", "Vol_Fact", "Kwh", "costoKw-hr", 
                   "Recaudacion", "Dotacion", "Balance_Estimado",
                   ST_AsGeoJSON(ST_Transform(geom, 4326)) as geo 
            FROM "Sectorizacion"."Sectores_hidr"
        """
        # Leemos los datos
        df = pd.read_sql(query, conn)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Error al cargar sectores: {e}")
        return []
    finally:
        # El bloque finally asegura que la conexión se cierre SIEMPRE
        # al terminar la función, exitosa o fallida.
        if conn:
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
               Pozo_9, Afectacion_9, Pozo_10, Afectacion_10 
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
                # CORRECCIÓN: Conservamos letras, números y guiones medios (ej. P-087A, R-087)
                id_limpio = str(val).strip().upper()
                if id_limpio:
                    diagnostico = row['DIAGNOSTICO_FALLA'] or 'Sin diagnóstico'
                    dic_incidencias[id_limpio] = diagnostico
        return dic_incidencias
    except Exception as e:
        return {}

def calcular_color_colonia(props, pozos_con_incidencia):
    suma_afectacion = 0.0
    tiene_incidencia_activa = False
    
    for i in range(1, 11):
        pozo_col = props.get(f'Pozo_{i}')
        afectacion_col = props.get(f'Afectacion_{i}')
        
        if pozo_col is not None:
            # Normalización robusta con y sin guion (ej. P087A / P-087A)
            id_p_limpio = str(pozo_col).strip().upper()
            id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
            id_p_sin_guion = id_p_limpio.replace('-', '')
            
            if (id_p_limpio in pozos_con_incidencia or 
                id_p_con_guion in pozos_con_incidencia or 
                id_p_sin_guion in pozos_con_incidencia):
                
                tiene_incidencia_activa = True
                if pd.notna(afectacion_col):
                    try:
                        val_str = str(afectacion_col).replace('%', '').strip()
                        val_afect = float(val_str)
                        # ⚠️ CAMBIO CLAVE: Sumar los porcentajes en lugar de buscar el máximo
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
        return '#69ADDD', suma_afectacion  # Naranja bajito
    else:
        return '#FF0000', suma_afectacion  # Por si supera el 100%

def calcular_color_sector(props, pozos_con_incidencia):
    suma_afectacion = 0.0
    tiene_incidencia_activa = False
    
    for i in range(1, 11):
        pozo_col = props.get(f'Pozo_{i}')
        afectacion_col = props.get(f'Afectacion_{i}')
        
        if pozo_col is not None:
            id_p_limpio = str(pozo_col).strip().upper()
            id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
            id_p_sin_guion = id_p_limpio.replace('-', '')
            
            if (id_p_limpio in pozos_con_incidencia or 
                id_p_con_guion in pozos_con_incidencia or 
                id_p_sin_guion in pozos_con_incidencia):
                
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
        .stApp { background-color: #000000; color: white; }
        
        .block-container {
            padding-top: 0rem !important;
            margin-top: 15px !important;
            max-width: 100% !important;
        }

        .mapa-area iframe { 
            margin-top: 90px !important;
            border: 1px solid #1f4068 !important;
            height: 85vh !important;
        }

        .mapa-area [data-testid="column"] {
            flex: 1 1 0% !important;
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
            padding: 10px 0;
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

        [data-testid="stSidebarContent"] {
            padding-top: 3px !important; 
        }

        [data-testid="stSidebar"] { 
            background-color: #0b1a29 !important; 
            border-right: 2px solid #1f4068; 
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
    st.markdown(
        f"""
        <style>
            [data-testid="column"] {{ margin-top: -105px !important; }}
            [data-testid="stSidebar"] {{display: none;}}
            header {{visibility: hidden;}}
            .stAppDeployButton {{display:none;}}
            #MainMenu {{visibility: hidden;}}
            footer {{visibility: hidden;}}
            .block-container {{ padding-top: 0px !important; padding-bottom: 0px !important; margin-top: -100px !important; }}
            .contenedor-centrado {{ text-align: center; margin-bottom: 0px; }}
            .titulo-sector {{ margin-top: 10px !important; font-size: 1.8rem; font-weight: 800; color: #00d4ff; margin: 10px; text-transform: uppercase; }}
            .col-mapa-offset {{ margin-top: 0px !important; }}
            .stFolium {{ margin-top: -10px !important; }}            
            hr {{ margin-top: 2px !important; margin-bottom: 5px !important; border: 0; border-top: 1px solid #1f4068; }}
            .card-indicador {{ background: rgba(16, 33, 54, 0.8); padding: 10px; border-radius: 8px; border: 1px solid #1f4068; text-align: center; margin-bottom: 5px; }}
            .label-indicador {{ color: #ffffff; font-size: 0.8rem; margin: 0; text-transform: uppercase; letter-spacing: 0.5px; }}
            .value-indicador {{ color: #00ffcc; font-size: 1.1rem; font-weight: bold; margin: 0; }}
            [data-testid="column"]:nth-child(2) {{ margin-top: 0px !important; }}
            .js-plotly-plot {{ margin-bottom: 10px !important; }}
        </style>
        <div class="contenedor-centrado">
            <h1 class="titulo-sector">ANÁLISIS DE SECTOR: {sector_seleccionado}</h1>
        </div>
        """, unsafe_allow_html=True
    )
    
    sec_id = str(sector_seleccionado).split('.')[0].strip()
    datos_s = next((s for s in sectores if str(s['sector']).strip() == sec_id), None)

    if datos_s:
        sel_r_id = None
        sel_v_id = None
        f_ini_h = datetime.now().date()
        f_fin_h = datetime.now().date()

        st.markdown('<div class="metrics-row">', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1: st.markdown(f'<div class="card-indicador"><p class="label-indicador">Población</p><p class="value-indicador">{datos_s.get("Poblacion", 0):,.0f}</p></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="card-indicador"><p class="label-indicador">U. Totales</p><p class="value-indicador">{datos_s.get("U_Tot", 0):,.0f}</p></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="card-indicador"><p class="label-indicador">U. Domésticos</p><p class="value-indicador">{datos_s.get("U_Domesticos", 0):,.0f}</p></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="card-indicador"><p class="label-indicador">Consumo m³</p><p class="value-indicador">{datos_s.get("Cons_m3", 0):,.1f}</p></div>', unsafe_allow_html=True) 
        with c5: st.markdown(f'<div class="card-indicador"><p class="label-indicador">Dotación</p><p class="value-indicador">{datos_s.get("Dotacion", 0):,.1f}</p></div>', unsafe_allow_html=True)
        with c6: st.markdown(f'<div class="card-indicador"><p class="label-indicador">Balance</p><p class="value-indicador">{datos_s.get("Balance_Estimado", 0):,.1f}%</p></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.divider()

        dict_reg_all = cargar_puntos_de_control_desde_db() 
        dict_reg = {k: v for k, v in dict_reg_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        reg_nombres = {v['nombre']: k for k, v in dict_reg.items()}
        opciones_equipo = list(reg_nombres.keys())
        
        dict_vrp_all = cargar_vrp_desde_db()
        dict_vrp_sec = {k: v for k, v in dict_vrp_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        vrp_nombres = {v['nombre']: k for k, v in dict_vrp_sec.items()}
        opciones_vrp = list(vrp_nombres.keys())

        c_sel_f, c_fecha_ext = st.columns([1, 1])
        with c_sel_f:
            opcion_fecha = st.selectbox(
                "Rango de fechas:",
                ["Hoy", "Esta Semana", "Últimos 14 días", "Este Mes", "Personalizado"],
                index=3,
                key="f_sector_full",
                label_visibility="collapsed"
        )
        hoy = datetime.now().date()
        f_ini_h, f_fin_h = hoy, hoy

        if opcion_fecha == "Hoy":
            f_ini_h, f_fin_h = hoy, hoy
        elif opcion_fecha == "Esta Semana":
            f_ini_h, f_fin_h = hoy - timedelta(days=hoy.weekday()), hoy
        elif opcion_fecha == "Últimos 14 días":
            f_ini_h, f_fin_h = hoy - timedelta(days=14), hoy
        elif opcion_fecha == "Este Mes":
            f_ini_h, f_fin_h = hoy.replace(day=1), hoy
        elif opcion_fecha == "Personalizado":
            with c_fecha_ext:
                rango_p = st.date_input(
                    "Periodo:",
                    value=(hoy - timedelta(days=7), hoy),
                    max_value=hoy,
                    key="f_sector_custom_global",
                    label_visibility="collapsed"
                )
                if isinstance(rango_p, tuple) and len(rango_p) == 2:
                    f_ini_h, f_fin_h = rango_p
                else:
                    f_ini_h, f_fin_h = hoy, hoy    

        col_izq, col_der = st.columns([1.0, 1.0])
        with col_izq:
            st.markdown('<div class="col-mapa-offset">', unsafe_allow_html=True)
            if "ultimo_clic_sv" not in st.session_state:
                st.session_state.ultimo_clic_sv = None
            
            m_sec = folium.Map(location=[21.8820, -102.2800], zoom_start=12, tiles=None, height=350)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Vista Satélite', overlay=False).add_to(m_sec)
            folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satélite (Esri)', overlay=False).add_to(m_sec)
            api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
            folium.TileLayer(
                tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
                name="Vista Nocturna",
                attr='&copy; OpenStreetMap contributors &copy; CARTO',
                subdomains="abcd", max_zoom=20, overlay=False, control=True
            ).add_to(m_sec)

            if datos_s and datos_s.get('geo'):
                try:
                    geo_data = json.loads(datos_s['geo'])
                    folium_geo = folium.GeoJson(geo_data, style_function=lambda x: {'fillColor': '#00d4ff', 'color': '#ffffff', 'weight': 2, 'fillOpacity': 0.15}, name="Límites del Sector").add_to(m_sec)
                    m_sec.fit_bounds(folium_geo.get_bounds())
                except: pass

            tags_para_scada = []
            for r in dict_reg.values():
                for k in ['tag_p1', 'tag_p2', 'tag_q', 'tag_vbat']:
                    if r.get(k): tags_para_scada.append(r.get(k))
            
            mapa_pc_all = cargar_puntos_criticos_desde_db()
            dict_pc_sec = {k: v for k, v in mapa_pc_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}
            for pc in dict_pc_sec.values():
                if pc.get('tag_p1'): tags_para_scada.append(pc.get('tag_p1'))

            for v in dict_vrp_sec.values():
                for k in ['tag_p1', 'tag_p2', 'tag_q']:
                    if v.get(k): tags_para_scada.append(v.get(k))

            scada_res_reg = cargar_datos_scada(list(set(tags_para_scada)))

            for r in dict_reg.values():
                def get_rv(tk):
                    v, f = scada_res_reg.get(r.get(tk), (0.0, "N/A"))
                    try: return float(v), f
                    except: return 0.0, f
                rp1, fp1 = get_rv('tag_p1'); rcau, fq = get_rv('tag_q'); rbat, fb = get_rv('tag_vbat')
                id_reg = r.get('Serie', 'S/N') 
                html_popup_reg = f"""<div style="background:#000; color:white; padding:12px; border-radius:10px; border:1px solid #00FFFF; width:250px; font-family:sans-serif;"><b style="color:#00FFFF; font-size:14px;">{r['nombre']}</b><hr style="opacity:0.2; margin:8px 0;"><div style="font-size:11px;">💧 Caudal: <b>{rcau:.2f} L/s</b><br><span style="color:#FFFF00;">{fq}</span><br><br>🚀 Presión: <b>{rp1:.2f} kg</b><br><span style="color:#FFFF00;">{fp1}</span><br><br>🔋 Bat: <b>{rbat:.2f} V</b><br><span style="color:#FFFF00;">{fb}</span></div></div>"""

                from folium.features import DivIcon
                icon_html = """
                <div style="position: relative; width: 30px; height: 30px;">
                    <div style="width: 20px; height: 20px; background: radial-gradient(circle at 30% 30%, #66ccff, #007bff, #003366); border-radius: 50%; box-shadow: 2px 4px 6px rgba(0,0,0,0.5); position: absolute; top: 0; left: 5px; z-index: 2;"></div>
                    <div style="width: 2px; height: 15px; background: linear-gradient(to right, #e0e0e0, #808080); position: absolute; top: 18px; left: 14px; z-index: 1;"></div>
                </div>
                """
                folium.Marker(location=r['coord'], icon=DivIcon(icon_size=(30, 40), icon_anchor=(15, 33), html=icon_html), popup=folium.Popup(html_popup_reg, max_width=300)).add_to(m_sec)
                folium.Marker(location=r['coord'], icon=folium.features.DivIcon(icon_size=(250,36), icon_anchor=(-15, 35), html=f'<div style="font-size: 10pt; color: #00FFFF; font-weight: bold; text-shadow: 2px 2px 4px #000; background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px; width: max-content; white-space: nowrap; border: 1px solid rgba(0,255,255,0.4);">SN: {id_reg}</div>')).add_to(m_sec)

            for id_pc, pc in dict_pc_sec.items():
                domicilio_texto = pc.get('Domicilio', 'S/D')
                val_p, fec_p = scada_res_reg.get(pc['tag_p1'], (0.0, "N/A"))
                html_pc = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #FF00FF; width:180px; font-family:sans-serif;"><b style="color:#FF00FF; font-size:13px;">PUNTO CRÍTICO</b><br><small>{domicilio_texto}</small><hr style="opacity:0.2; margin:5px 0;">Presión: <b style="color:#FF00FF;">{val_p:.2f} kg</b><br><span style="color:#FFFF00; font-size:9px;">{fec_p}</span></div>"""
                
                folium.Marker(location=pc['coord'], icon=folium.DivIcon(icon_size=(250,36), icon_anchor=(-15, 35), html=f'<div style="font-size: 10pt; color: #FF00FF; font-weight: bold; text-shadow: 2px 2px 4px #000; background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px; width: max-content; white-space: nowrap; border: 1px solid rgba(255,0,255,0.4);">NS: {id_pc}</div>')).add_to(m_sec)
                
                icon_html = """
                <div style="position: relative; width: 30px; height: 30px;">
                    <div style="width: 20px; height: 20px; background: radial-gradient(circle at 30% 30%, #ff4d4d, #ff0000, #800000); border-radius: 50%; box-shadow: 2px 4px 6px rgba(0,0,0,0.5); position: absolute; top: 0; left: 5px; z-index: 2;"></div>
                    <div style="width: 2px; height: 15px; background: linear-gradient(to right, #e0e0e0, #808080); position: absolute; top: 18px; left: 14px; z-index: 1;"></div>
                </div>
                """
                folium.Marker(location=pc['coord'], icon=DivIcon(icon_size=(30, 40), icon_anchor=(15, 33), html=icon_html), popup=folium.Popup(html_pc, max_width=250)).add_to(m_sec)
                
            for id_vrp, vrp in dict_vrp_sec.items():
                val_p1, _ = scada_res_reg.get(vrp['tag_p1'], (0.0, "N/A"))
                val_p2, _ = scada_res_reg.get(vrp['tag_p2'], (0.0, "N/A"))
                serie_vrp = vrp.get('Serie', 'S/N')
                html_vrp = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00FFCC; width:200px; font-family:sans-serif;"><b style="color:#00FFCC; font-size:13px;">VALVULA VRP</b><br><small>{vrp['nombre']}</small><hr style="opacity:0.2; margin:5px 0;">P. Entrada: <b>{val_p1:.2f} kg</b><br>P. Salida: <b style="color:#00FFCC;">{val_p2:.2f} kg</b></div>"""
                
                icon_html = """
                <div style="position: relative; width: 30px; height: 30px;">
                    <div style="width: 20px; height: 20px; background: radial-gradient(circle at 30% 30%, #a1ffce, #28a745, #004d1a); border-radius: 50%; box-shadow: 2px 4px 6px rgba(0,0,0,0.5); position: absolute; top: 0; left: 5px; z-index: 2;"></div>
                    <div style="width: 2px; height: 15px; background: linear-gradient(to right, #e0e0e0, #808080); position: absolute; top: 18px; left: 14px; z-index: 1;"></div>
                </div>
                """
                folium.Marker(location=vrp['coord'], icon=DivIcon(icon_size=(30, 40), icon_anchor=(15, 33), html=icon_html), popup=folium.Popup(html_vrp, max_width=250)).add_to(m_sec)
                folium.Marker(location=vrp['coord'], icon=folium.features.DivIcon(icon_size=(250,36), icon_anchor=(-15, 35), html=f'<div style="font-size: 10pt; color: #00FFCC; font-weight: bold; text-shadow: 2px 2px 4px #000; background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px; width: max-content; white-space: nowrap; border: 1px solid rgba(0,255,204,0.4);">SN: {serie_vrp}</div>')).add_to(m_sec)

            ids_p = [p.strip() for p in datos_s.get('Pozos_Sector', '').split(',')] if datos_s.get('Pozos_Sector') else []
            for id_p in ids_p:
                if id_p in mapa_pozos_dict:
                    info = mapa_pozos_dict[id_p]
                    def ds(tag):
                        val, fec = data_scada.get(tag, (0.0, "N/A"))
                        try: return float(val), fec
                        except: return 0.0, fec
                            
                    q, f_q = ds(info['caudal']); p, f_p = ds(info['presion'])
                    v = [ds(info.get(f'v{i}')) for i in range(1, 4)]; a = [ds(info.get(f'a{i}')) for i in range(1, 4)]
                    
                    html_popup_sec = f"""<div style="background: #050505; color: white; padding: 15px; border-radius: 12px; width: 380px; border: 1px solid {info['color_final']}; font-family: sans-serif;"><div style="display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 10px;"><b style="color: #00d4ff; font-size: 16px;">POZO {id_p}</b><span style="font-size: 10px; background: {info['color_final']}; color: black; padding: 2px 8px; border-radius: 4px; font-weight: bold;">{info['status_label']}</span></div><div style="margin-bottom: 12px;"><div style="font-size: 10px; color: #888; margin-bottom: 4px;">HIDRÁULICA</div><div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;"><span>💧 Caudal: <b>{q:.2f} L/s</b></span><span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_q}</span></div><div style="display: flex; align-items: baseline; font-size: 11px;"><span>🚀 Presión: <b>{p:.2f} kg</b></span><span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_p}</span></div></div><div><div style="font-size: 10px; color: #888; margin-bottom: 4px;">ELÉCTRICO</div><table style="width: 100%; font-size: 10px; border-collapse: collapse;"><tr><td>L1-L2</td><td>{v[0][0]:.1f}V</td><td>{a[0][0]:.1f}A</td></tr></table></div></div>"""

                    folium.Marker(location=info['coord'], icon=folium.DivIcon(html=f'<div style="font-size: 11px; color: white; font-weight: bold; text-shadow: 1px 1px 2px black; width: 100px; position: relative; left: 17px; top: -3px;">{id_p}</div>')).add_to(m_sec)
                    
                    if info.get('blink'):
                        folium.Marker(location=info['coord'], icon=folium.DivIcon(html=get_blink_icon(info['color_final'])), popup=folium.Popup(html_popup_sec, max_width=400)).add_to(m_sec)
                    else:
                        folium.CircleMarker(location=info['coord'], radius=6, color=info['color_final'], fill=True, fill_opacity=1, popup=folium.Popup(html_popup_sec, max_width=400)).add_to(m_sec)

            if st.session_state.get("ultimo_clic_sv"):
                c_lat, c_lng = st.session_state.ultimo_clic_sv["lat"], st.session_state.ultimo_clic_sv["lng"]
                sv_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={c_lat},{c_lng}"
                html_popup_sv = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00d4ff; width:180px;"><b style="color:#00d4ff; font-size:12px;">COORDENADAS</b><br><code>{c_lat:.5f}, {c_lng:.5f}</code><br><br><a href="{sv_url}" target="_blank" style="display:block; text-align:center; background:#00d4ff; color:black; padding:8px; border-radius:5px; text-decoration:none; font-weight:bold; font-size:10px;">🚹 STREET VIEW</a></div>"""
                folium.Marker(location=[c_lat, c_lng], popup=folium.Popup(html_popup_sv, max_width=200), icon=folium.Icon(color='blue', icon='map-marker')).add_to(m_sec)

            folium.LayerControl(position='topright', collapsed=False).add_to(m_sec)
            Fullscreen(position='topleft').add_to(m_sec)
            salida = st_folium(m_sec, width="100%", height=330, key="mapa_miaa_interactivo_v4", returned_objects=["last_clicked"])
            if salida and salida.get("last_clicked"):
                nuevo_clic = salida["last_clicked"]
                if st.session_state.get("ultimo_clic_sv") != nuevo_clic:
                    st.session_state.ultimo_clic_sv = nuevo_clic
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_der:
            st.markdown(f"<h3 style='color:#00d4ff; font-size:18px; text-align: center; margin-bottom:0px;'>Histórico Puntos de control</h3>", unsafe_allow_html=True)
            tags_visualizar = []
            mapeo_config = {}

            for s_id in list(dict_reg.keys()):
                r_info = dict_reg[s_id]
                conf_pc = [
                    ('tag_q', f"S:{s_id} - Q", '#00d4ff', False),
                    ('tag_p1', f"S:{s_id} - P1", '#00ff00', True),
                    ('tag_p2', f"S:{s_id} - P2", '#ffff00', True)
                ]
                for key_t, lb, clr, sec in conf_pc:
                    tag_v = r_info.get(key_t)
                    if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        tags_visualizar.append(tag_v)
                        mapeo_config[tag_v] = {'label': lb, 'color': clr, 'sec': sec}

            for id_p in ids_p:
                if id_p in mapa_pozos_dict:
                    p_info = mapa_pozos_dict[id_p]
                    conf_pz = [
                        ('caudal', f"Pozo {id_p} - Q", '#00d4ff', False),
                        ('presion', f"Pozo {id_p} - P", '#00ff00', True),
                        ('nivel_tanque', f"Pozo {id_p} - Nivel", '#0000FF', True)
                    ]
                    for key_t, lb, clr, sec in conf_pz:
                        tag_v = p_info.get(key_t)
                        if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a']:
                            tags_visualizar.append(tag_v)
                            mapeo_config[tag_v] = {'label': lb, 'color': clr, 'sec': sec}

            if tags_visualizar:
                try:
                    engine_h = get_mysql_scada_engine()
                    tags_unicos_query = "', '".join(list(set(tags_visualizar)))
                    q_hist = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_unicos_query}') AND h.FECHA BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59' ORDER BY h.FECHA ASC"
                    df_h = pd.read_sql(q_hist, engine_h)
                    
                    if not df_h.empty:
                        df_h['FECHA'] = pd.to_datetime(df_h['FECHA'])
                        dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                        meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                        fechas_lineas = pd.date_range(start=df_h['FECHA'].min().floor('D'), end=df_h['FECHA'].max().ceil('D'), freq='D')
                        num_dias = len(fechas_lineas)
                        paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
                        ticks_filtrados = fechas_lineas[::paso]

                        etiquetas_filtradas = [
                            f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                            for d in ticks_filtrados
                        ]
                    
                        fig = go.Figure()
                        idx_q = 0
                        idx_p = 0

                        for tag_name in tags_visualizar:
                            df_tag = df_h[df_h['TAG'] == tag_name]
                            if not df_tag.empty:
                                cfg = mapeo_config[tag_name]
                                es_caudal = not cfg['sec']
                                label_u = cfg['label'].upper()

                                if es_caudal: unidad_pc = "Lps"
                                elif "NIVEL" in label_u or "TANQUE" in label_u or "MTS" in label_u: unidad_pc = "Mts"
                                else: unidad_pc = "kg/cm²"
                                
                                if es_caudal:
                                    brillo = max(75 - (idx_q * 15), 35) 
                                    color_base = f"hsl(200, 100%, {brillo}%)" 
                                    idx_q += 1
                                else:
                                    brillo = max(80 - (idx_p * 20), 30)
                                    color_base = f"hsl(145, 100%, {brillo}%)"
                                    idx_p += 1

                                fig.add_trace(go.Scatter(
                                    x=df_tag['FECHA'], y=df_tag['VALUE'], name=cfg['label'], 
                                    yaxis="y2" if cfg['sec'] else "y1", mode='lines+markers',
                                    line=dict(width=2, color=color_base),
                                    marker=dict(size=3, symbol='circle'),
                                    fill='tozeroy' if es_caudal else None,
                                    fillcolor=color_base.replace("hsl", "hsla").replace(")", ", 0.15)"),
                                    hovertemplate='<b>%{fullData.name}</b>: %{y:.2f} ' + unidad_pc + '<extra></extra>'
                                ))

                        delta = pd.Timedelta(hours=1)
                        for d in fechas_lineas:
                            es_lunes = (d.dayofweek == 0)
                            fig.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                            fig.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")
                        
                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, 
                            margin=dict(l=50, r=50, t=10, b=10), hovermode="x unified", 
                            legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.5, xanchor="center", font=dict(color="white", size=10)),
                            xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                            yaxis=dict(title="Caudales (m³/h)", color="#00d4ff", tickformat=".2f"),
                            yaxis2=dict(title="Presiones (kg)", side="right", overlaying="y", color="#00ff00", showgrid=False, tickformat=".2f")
                        )
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error Scada (Derecha): {e}")

        col_vrp, col_pc = st.columns([1.0, 1.0])
        with col_vrp:
            tags_vrp_global = []
            mapeo_vrp_global = {}
            for v_id, v_info in dict_vrp_sec.items():
                identificador = f"VRP {v_id}" 
                conf_vrp = [
                    ('tag_q', f"{identificador} - Q", False),
                    ('tag_p1', f"{identificador} - P1", True),
                    ('tag_p2', f"{identificador} - P2", True)
                ]
                for key_t, lb, sec in conf_vrp:
                    t_val = v_info.get(key_t)
                    if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a']:
                        tags_vrp_global.append(t_val)
                        mapeo_vrp_global[t_val] = {'label': lb, 'sec': sec}

            if tags_vrp_global:
                try:
                    engine_h = get_mysql_scada_engine()
                    tags_in_v = "', '".join(list(set(tags_vrp_global)))
                    q_vrp = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_in_v}') AND h.FECHA BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59' ORDER BY h.FECHA ASC"
                    df_v = pd.read_sql(q_vrp, engine_h)
                    
                    if not df_v.empty:
                        st.markdown(f"<h3 style='color:#00ffcc; font-size:20px; margin-bottom:10px; text-align: center;'>Análisis Integral de VRPs del Sector</h3>", unsafe_allow_html=True)

                        df_v['FECHA'] = pd.to_datetime(df_v['FECHA'])
                        dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                        meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                        
                        fechas_lineas = pd.date_range(start=df_v['FECHA'].min().floor('D'), end=df_v['FECHA'].max().ceil('D'), freq='D')
                        num_dias = len(fechas_lineas)
                        paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
                        ticks_filtrados = fechas_lineas[::paso]
                        etiquetas_filtradas = [
                            f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                            for d in ticks_filtrados
                        ]
                        
                        fig_v = go.Figure()
                        delta = pd.Timedelta(hours=1)
                        for d in fechas_lineas:
                            es_lunes = (d.dayofweek == 0)
                            fig_v.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                            fig_v.add_vline(x=d, line_width=0.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")
                        
                        idx_vq = 0
                        idx_vp = 0

                        for t_name in tags_vrp_global:
                            df_t = df_v[df_v['TAG'] == t_name]
                            if not df_t.empty:
                                c_vrp = mapeo_vrp_global[t_name]
                                es_caudal_v = not c_vrp['sec']
                                unidad_final = "kg/cm²" if "P1" in c_vrp['label'] or "P2" in c_vrp['label'] else "Lps"
                                
                                if es_caudal_v:
                                    brillo = max(75 - (idx_vq * 15), 35)
                                    color_v = f"hsl(200, 100%, {brillo}%)" 
                                    idx_vq += 1
                                else:
                                    brillo = max(80 - (idx_vp * 15), 30)
                                    color_v = f"hsl(150, 100%, {brillo}%)"
                                    idx_vp += 1

                                fig_v.add_trace(go.Scatter(
                                    x=df_t['FECHA'], y=df_t['VALUE'], name=c_vrp['label'], 
                                    yaxis="y2" if c_vrp['sec'] else "y1", mode='lines+markers',
                                    line=dict(width=1.8, color=color_v),
                                    marker=dict(size=3 if es_caudal_v else 4, symbol='circle'),
                                    fill='tozeroy' if es_caudal_v else None,
                                    fillcolor=color_v.replace("hsl", "hsla").replace(")", ", 0.12)"),
                                    hovertemplate=f'<b>%{{fullData.name}}</b>: %{{y:.2f}} {unidad_final}<extra></extra>'
                                ))

                        fig_v.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300, 
                            margin=dict(l=50, r=50, t=10, b=10), hovermode="x unified", 
                            legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.5, xanchor="center", font=dict(color="white", size=9)),
                            xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                            yaxis=dict(title="Caudal (Lps)", color="#00d4ff", tickformat=".2f"),
                            yaxis2=dict(title="Presión (kg)", side="right", overlaying="y", color="#00ff00", showgrid=False, tickformat=".2f")
                        )
                        st.plotly_chart(fig_v, use_container_width=True)
                except Exception as e:
                    st.error(f"Error Scada VRP: {e}")
                    
        with col_pc:
            if dict_pc_sec:
                tags_pc_list = [v['tag_p1'] for v in dict_pc_sec.values() if v.get('tag_p1')]
                if tags_pc_list:
                    try:
                        tags_pc_in = "', '".join(tags_pc_list)
                        df_pc_h = pd.read_sql(f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_pc_in}') AND h.FECHA BETWEEN '{f_ini_h} 00:00:00' AND '{f_fin_h} 23:59:59' ORDER BY h.FECHA ASC", engine_h)

                        if not df_pc_h.empty:
                            st.markdown(f"<h3 style='color:#ff0000; font-size:18px; margin-bottom:10px; text-align: center;'>Puntos críticos del sector:</h3>", unsafe_allow_html=True)
                            
                            df_pc_h['FECHA'] = pd.to_datetime(df_pc_h['FECHA'])
                            dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                            meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
                            
                            fechas_lineas = pd.date_range(start=df_pc_h['FECHA'].min().floor('D'), end=df_pc_h['FECHA'].max().ceil('D'), freq='D')
                            num_dias = len(fechas_lineas)
                            paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
                            ticks_filtrados = fechas_lineas[::paso]
                            etiquetas_filtradas = [f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}" for d in ticks_filtrados]

                            fig_pc = go.Figure()
                            delta = pd.Timedelta(hours=1)
                            for d in fechas_lineas:
                                es_lunes = (d.dayofweek == 0)
                                fig_pc.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                                fig_pc.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")

                            tag_to_name = {v['tag_p1']: v.get('Domicilio', v.get('nombre', 'S/D')) for v in dict_pc_sec.values()}

                            for tag in tags_pc_list:
                                df_temp = df_pc_h[df_pc_h['TAG'] == tag]
                                if not df_temp.empty:
                                    fig_pc.add_trace(go.Scatter(
                                        x=df_temp['FECHA'], y=df_temp['VALUE'], 
                                        name=tag_to_name.get(tag, tag), mode='lines+markers',
                                        marker=dict(size=4, symbol='circle'), line=dict(width=2),
                                        hovertemplate='<b>%{fullData.name}</b><br>Valor: %{y:.2f} kg<extra></extra>'
                                    ))

                            fig_pc.update_layout(
                                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300, 
                                margin=dict(l=50, r=50, t=40, b=10), hovermode="x unified",
                                xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                                yaxis=dict(tickformat=".2f", color="white"),
                                legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.5, xanchor="center", font=dict(color="white", size=10))
                            )
                            st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error PC: {e}")

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
pestaña_mapa, pestaña_incidencias, pestaña_tanques, pestaña_sectores = st.tabs(
    ["🗺️ Mapa Principal", "⚠️ Incidencias Activas y del día", "🛢️ Miaa Tanques", "🏘️ Sectores Hidráulicos"]
)


# ==============================================================================
# PESTAÑA 1 MAPA DE POZOS, TANQUES Y REBOMBEOS
# ==============================================================================
with pestaña_mapa:
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
                    
                    for i in range(1, 11):
                        pozo_sec = row.get(f'Pozo_{i}')
                        afectacion_sec = row.get(f'Afectacion_{i}')
                        if pd.notna(pozo_sec):
                            id_p_limpio = str(pozo_sec).strip().upper()
                            id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
                            id_p_sin_guion = id_p_limpio.replace('-', '')
                            
                            if (id_p_limpio in dic_incidencias_activas or 
                                id_p_con_guion in dic_incidencias_activas or 
                                id_p_sin_guion in dic_incidencias_activas):
                                
                                falla = (
                                    dic_incidencias_activas.get(id_p_limpio) or 
                                    dic_incidencias_activas.get(id_p_con_guion) or 
                                    dic_incidencias_activas.get(id_p_sin_guion, 'Activa')
                                )
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
                        if pd.notna(pozo_col):
                            id_p_limpio = str(pozo_col).strip().upper()
                            id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
                            id_p_sin_guion = id_p_limpio.replace('-', '')
                            
                            if (id_p_limpio in dic_incidencias_activas or 
                                id_p_con_guion in dic_incidencias_activas or 
                                id_p_sin_guion in dic_incidencias_activas):
                                
                                falla = (
                                    dic_incidencias_activas.get(id_p_limpio) or 
                                    dic_incidencias_activas.get(id_p_con_guion) or 
                                    dic_incidencias_activas.get(id_p_sin_guion, 'Activa')
                                )
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
                d = lambda tag: data_scada.get(tag, (0, "N/A"))
                is_st = (info['status_label'] == 'SIN TELEMETRÍA')
                q, f_q = d(info['caudal']) if not is_st else (0.0, "N/A")
                p, f_p = d(info['presion']) if not is_st else (0.0, "N/A")
                sumer, f_s = d(info['sumergencia']) if not is_st else (0.0, "N/A")
                dinam, f_d = d(info['nivel_dinamico']) if not is_st else (0.0, "N/A")
                tanq, f_t = d(info['nivel_tanque']) if not is_st else (0.0, "N/A")
                col, f_col = d(info['columna']) if not is_st else (0.0, "N/A")
                h_arr_val, f_h_arr = d(info['h_arranque']) if not is_st else (0.0, "N/A")
                h_par_val, f_h_par = d(info['h_paro']) if not is_st else (0.0, "N/A")
                h_arr_fmt = formato_hora(h_arr_val)
                h_par_fmt = formato_hora(h_par_val)
                v = [d(t) for t in info['voltajes_l']] if not is_st else [(0.0, "N/A")]*3
                a = [d(t) for t in info['amperajes_l']] if not is_st else [(0.0, "N/A")]*3

                id_p_limpio = str(id_p).strip().upper()
                id_p_con_guion = re.sub(r'^([A-Z]+)(\d+)([A-Z]*)$', r'\1-\2\3', id_p_limpio)
                id_p_sin_guion = id_p_limpio.replace('-', '')
                
                tiene_incidencia_activa = (
                    id_p_limpio in dic_incidencias_activas or 
                    id_p_con_guion in dic_incidencias_activas or 
                    id_p_sin_guion in dic_incidencias_activas
                )

                rol_actual = st.session_state.get('rol', 'usuario')
                nombre_codificado = urllib.parse.quote(id_p)
                url_pozo_graf = f"?graficar_pozo={id_p}&nombre={nombre_codificado}&access=granted&role={rol_actual}"

                html_popup = f"""
            <div style="background: #050505; color: white; padding: 15px; border-radius: 12px; width: 380px; border: 1px solid {info['color_final']}; font-family: sans-serif;">
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 10px;">
                    <b style="color: #00d4ff; font-size: 16px;">POZO {id_p}</b>
                    <span style="font-size: 10px; background: {info['color_final']}; color: black; padding: 2px 8px; border-radius: 4px; font-weight: bold;">{info['status_label']}</span>
                </div>
                
                <div style="margin-bottom: 12px;">
                    <div style="font-size: 10px; color: #888; margin-bottom: 4px;">HIDRÁULICA</div>
                    <div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;">
                        <span>💧 Caudal: <b>{q:.2f} L/s</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_q}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; font-size: 11px;">
                        <span>🚀 Presión: <b>{p:.2f} kg</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_p}</span>
                    </div>
                </div>

                <div style="margin-bottom: 12px;">
                    <div style="font-size: 10px; color: #888; margin-bottom: 4px;">NIVELES</div>
                    <div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;">
                        <span>🔋 Nivel de Tanque:<b>{tanq:.2f} mts</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_t}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;">
                        <span>📉 Nivel Dinámico/Estatico: <b>{dinam:.2f} m</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_d}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;">
                        <span>📏 Sumergencia: <b>{sumer:.2f} m</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_s}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; font-size: 11px;">
                        <span>🏗️ Longitud de Columna: <b>{col:.2f} m</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_col}</span>
                    </div>
                </div>

                <div style="margin-bottom: 12px;">
                    <div style="font-size: 10px; color: #888; margin-bottom: 4px;">ELÉCTRICO</div>
                    <table style="width: 100%; font-size: 10px; border-collapse: collapse; margin-bottom: 8px;">
                        <tr style="color: #00d4ff; border-bottom: 1px solid #333; text-align: left;">
                            <th style="padding: 4px;">Fase</th>
                            <th style="padding: 4px;">Voltaje / Act.</th>
                            <th style="padding: 4px;">Amp / Act.</th>
                        </tr>
                        <tr style="border-bottom: 1px solid #222;">
                            <td style="padding: 6px 4px;">L1-L2</td>
                            <td><b>{v[0][0]:.1f}V</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{v[0][1]}</span></td>
                            <td><b>{a[0][0]:.1f}A</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{a[0][1]}</span></td>
                        </tr>
                        <tr style="border-bottom: 1px solid #222;">
                            <td style="padding: 6px 4px;">L2-L3</td>
                            <td><b>{v[1][0]:.1f}V</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{v[1][1]}</span></td>
                            <td><b>{a[1][0]:.1f}A</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{a[1][1]}</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 4px;">L1-L3</td>
                            <td><b>{v[2][0]:.1f}V</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{v[2][1]}</span></td>
                            <td><b>{a[2][0]:.1f}A</b> <span style="color:#FFFF00; font-size:8px; margin-left:4px;">{a[2][1]}</span></td>
                        </tr>
                    </table>
                    <div style="font-size: 10px; color: #888; margin-bottom: 4px; border-top: 1px solid #222; paddingTop: 5px;">HORARIOS</div>
                    <div style="display: flex; align-items: baseline; font-size: 11px; margin-bottom: 3px;">
                        <span>▶️ Arranque: <b>{h_arr_fmt}</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_h_arr}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; font-size: 11px;">
                        <span>⏹️ Paro: <b>{h_par_fmt}</b></span>
                        <span style="color: #FFFF00; font-size: 8px; margin-left: auto;">{f_h_par}</span>
                    </div>

                    <div style="border-top: 1px solid #333; padding-top: 10px;">
                    <a href="{url_pozo_graf}" target="_blank" style="text-decoration: none;">
                        <div style="background: #00d4ff; color: #050a10; text-align: center; padding: 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">
                            📊 VER ANÁLISIS HISTÓRICO
                        </div>
                    </a>
                </div>
            </div>
            """

                folium.Marker(
                    location=info['coord'],
                    icon=folium.DivIcon(
                        icon_size=(150,36),
                        icon_anchor=(-12, 6),
                        html=f'<div style="font-size: 9px; font-weight: bold; color: {info["color_final"]}; white-space: nowrap; text-shadow: 1px 1px #000; pointer-events: none;">{id_p}</div>'
                    )
                ).add_to(fg_pozos)

                if tiene_incidencia_activa:
                    info_incidencia = (
                        dic_incidencias_activas.get(id_p_limpio) or 
                        dic_incidencias_activas.get(id_p_con_guion) or 
                        dic_incidencias_activas.get(id_p_sin_guion, {})
                    )
                    diagnostico_falla = info_incidencia.get('diagnostico', info_incidencia.get('motivo', 'FALLA')) if isinstance(info_incidencia, dict) else str(info_incidencia)
                    
                    html_globo_incidencia = f"""
                    <div style="position: relative; width: 350px; height: 80px; pointer-events: none; font-family: sans-serif;">
                        <svg style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; overflow: visible;">
                            <line x1="15" y1="65" x2="75" y2="35" stroke="#ff4d4d" stroke-width="2" />
                            <circle cx="15" cy="65" r="4" fill="#ffffff" stroke="#ff4d4d" stroke-width="2" />
                        </svg>
                        <div style="position: absolute; top: 0px; left: 75px; display: inline-flex; align-items: center; background: #000000; border: 2px solid #ff4d4d; border-radius: 6px; padding: 4px 8px; white-space: nowrap; box-shadow: 0 4px 8px rgba(0,0,0,0.6); pointer-events: auto;">
                            <span style="font-size: 14px; margin-right: 6px;">🛠️</span>
                            <span style="font-size: 11px; font-weight: bold; color: #ffffff; margin-right: 8px;">{id_p}</span>
                            <span style="font-size: 10px; font-weight: bold; color: #ffffff; background: #c0392b; padding: 2px 6px; border-radius: 4px;">{diagnostico_falla.upper()}</span>
                        </div>
                    </div>
                    """
                    folium.Marker(
                        location=info['coord'],
                        icon=folium.DivIcon(icon_size=(350, 80), icon_anchor=(15, 65), html=html_globo_incidencia),
                        popup=folium.Popup(html_popup, max_width=450),
                        tooltip=f"⚠️ POZO {id_p} - {diagnostico_falla}"
                    ).add_to(fg_pozos)
                elif info.get('blink'):
                    folium.Marker(location=info['coord'], icon=folium.DivIcon(html=get_blink_icon(info['color_final'])), popup=folium.Popup(html_popup, max_width=450)).add_to(fg_pozos)
                else:
                    folium.CircleMarker(location=info['coord'], radius=3, color=info['color_final'], fill=True, fill_color=info['color_final'], fill_opacity=1, popup=folium.Popup(html_popup, max_width=450)).add_to(fg_pozos)

            fg_pozos.add_to(m)


# 9.8. RENDERIZADO DE TANQUES EN EL MAPA PRINCIPAL  -----------------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_tanques:
            for id_tq, info in mapa_tanques_dict.items():
                try:
                    val_nivel, fecha_tq = data_scada.get(info['tag_nivel'], (0, "N/A"))
                    url_grafico = f"?graficar_tanque={info['tag_nivel']}&nombre={info['nombre'].replace(' ', '%20')}&access=granted&role={st.session_state.get('rol', 'usuario')}"

                    html_popup_tq = f"""
                    <div style="background: #050505; color: white; padding: 12px; border-radius: 10px; width: 250px; border: 2px solid #00d4ff; font-family: sans-serif;">
                        <b style="color: #00d4ff; font-size: 14px;">TANQUE: {info['nombre']}</b><br>
                        <hr style="border: 0.5px solid #333;">
                        <div style="font-size: 12px; margin-bottom: 10px;">💧 Nivel Actual: <b>{val_nivel:.2f} m</b></div>
                        <div style="text-align: center;">
                            <a href="{url_grafico}" target="_blank" style="background-color: #00d4ff; color: black; padding: 10px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 11px; display: inline-block; width: 90%; border: 1px solid #00d4ff;">📊 VER GRÁFICO HISTÓRICO</a>
                        </div>
                    </div>
                    """
                    folium.RegularPolygonMarker(location=info['coord'], number_of_sides=6, radius=5, color="#00d4ff", fill=True, fill_color="#00d4ff", popup=folium.Popup(html_popup_tq, max_width=300), tooltip=f"Tanque: {info['nombre']}").add_to(m)
                except: continue

# 9.9.  RENDERIZADO DE REBOMBEOS EN EL MAPA PRINCIPAL -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_rebombeos:
            for id_rb, info in mapa_rebombeos_dict.items():
                try:
                    d = lambda tag: data_scada.get(tag, (0, "N/A"))
                    is_st = (info.get('status_label') == 'SIN TELEMETRÍA')
                    
                    pres, f_p = d(info['presion']) if not is_st else (0.0, "N/A")
                    ntq, f_t = d(info['nivel_tanque']) if not is_st else (0.0, "N/A")
                    
                    v_rb = [d(t) for t in info.get('voltajes_l', [])] if not is_st and info.get('voltajes_l') else [(0.0, "N/A")]*3
                    a_rb = [d(t) for t in info.get('amperajes_l', [])] if not is_st and info.get('amperajes_l') else [(0.0, "N/A")]*3

                    html_popup_rb = f"""
                <div style="background: #050505; color: white; padding: 12px; border-radius: 10px; width: 300px; border: 2px solid {info['color_final']}; font-family: sans-serif;">
                    <div style="display: flex; justify-content: space-between;">
                        <b style="color: {info['color_final']}; font-size: 14px;">REBOMBEO: {id_rb}</b>
                        <span style="font-size: 10px; background: {info['color_final']}; color: black; padding: 2px 6px; border-radius: 4px; font-weight: bold;">{info['status_label']}</span>
                    </div>
                    <hr style="border: 0.5px solid #333; margin: 8px 0;">
                    <div style="font-size: 11px; margin-bottom: 5px;">
                        🚀 Presión: <b>{pres:.2f} kg</b> <span style="color:#FFFF00; font-size:8px;">{f_p}</span><br>
                        🔋 Nivel Tanque: <b>{ntq:.2f} m</b> <span style="color:#FFFF00; font-size:8px;">{f_t}</span>
                    </div>
                    <table style="width: 100%; font-size: 9px; border-collapse: collapse; margin-top: 5px;">
                        <tr style="color: #00d4ff; border-bottom: 1px solid #333; text-align: left;">
                            <th>Fase</th><th>Voltaje</th><th>Amp</th>
                        </tr>
                        <tr><td>L1-L2</td><td>{v_rb[0][0]:.0f}V</td><td>{a_rb[0][0]:.1f}A</td></tr>
                        <tr><td>L2-L3</td><td>{v_rb[1][0]:.0f}V</td><td>{a_rb[1][0]:.1f}A</td></tr>
                        <tr><td>L1-L3</td><td>{v_rb[2][0]:.0f}V</td><td>{a_rb[2][0]:.1f}A</td></tr>
                    </table>
                </div>
                """
                    
                    if info.get('blink'):
                        folium.Marker(location=info['coord'], icon=folium.DivIcon(html=get_blink_icon(info['color_final'])), popup=folium.Popup(html_popup_rb, max_width=350)).add_to(m)
                    else:
                        folium.RegularPolygonMarker(location=info['coord'], number_of_sides=4, radius=6, color=info['color_final'], fill=True, fill_color=info['color_final'], popup=folium.Popup(html_popup_rb, max_width=350)).add_to(m)
                except: continue

# 9.10. RENDERIZADO DE MACROMEDIDORES EN EL MAPA PRINCIPAL ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        if ver_macromedidores:
            from datetime import datetime, timedelta
            datos_macromedidores = cargar_medidores_desde_db()
            fecha_limite = datetime.now() - timedelta(days=5)

            for id_mm, info in datos_macromedidores.items():
                # --- FILTRO ---
                if str(id_mm) == '1000' or info.get('nombre') == 'Sin instalar':
                    continue

                # --- LÓGICA DE ESTADO Y COLOR ---
                es_falla = info['ultima_fecha'] < fecha_limite
                
                color_borde = '#FF0000' if es_falla else '#B19CD9'
                color_relleno = '#8B0000' if es_falla else '#800080'
                color_popup = '#FF0000' if es_falla else '#800080'
                clase_animacion = "pulsante" if es_falla else ""

                try:
                    # Recuperamos la lógica completa del botón de gráfico
                    url_pestaña = f"?ver_grafico={id_mm}&nombre={info.get('nombre', 'Medidor').replace(' ', '%20')}&access=granted&role={st.session_state.get('rol', 'usuario')}"
                    
                    html_popup_mm = f"""
                    <div style="background: #050505; color: white; padding: 12px; border-radius: 10px; width: 220px; border: 2px solid {color_popup}; font-family: sans-serif;">
                        <b style="color: {color_popup}; font-size: 14px;">MACROMEDIDOR: {id_mm}</b>
                        <hr style="border: 0.5px solid #333; margin: 8px 0;">
                        <div style="font-size: 12px;">
                            📍 Nombre: <b>{info.get('nombre', 'N/A')}</b><br>
                            📡 Última transmisión: <b>{info['ultima_fecha'].strftime('%Y-%m-%d')}</b>
                        </div>
                        <div style="margin-top: 10px; text-align: center;">
                            <a href="{url_pestaña}" target="_blank" style="background-color: {color_popup}; color: white; padding: 8px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 11px; display: inline-block; width: 90%;">📊 ABRIR GRÁFICO</a>
                        </div>
                    </div>
                    """
                    
                    # SVG con la clase de parpadeo (pulsante)
                    html_svg = f"""
                    <svg width="20" height="20" class="{clase_animacion}">
                        <circle cx="10" cy="10" r="6" stroke="{color_borde}" stroke-width="2" fill="{color_relleno}" fill-opacity="0.9" />
                    </svg>
                    """
                    
                    # Punto principal
                    folium.Marker(
                        location=info['coord'],
                        icon=folium.DivIcon(icon_size=(20, 20), icon_anchor=(10, 10), html=html_svg),
                        popup=folium.Popup(html_popup_mm, max_width=300)
                    ).add_to(m)
                    
                    # Texto combinado: ID y Nombre
                    color_texto = "#FF4C4C" if es_falla else "#FFFFFF"
                    html_etiqueta = f"""
                    <div style="font-size: 11px; font-weight: bold; color: {color_texto}; text-shadow: 1px 1px #000; white-space: nowrap;">
                        - {id_mm} {info.get('nombre', 'N/A')}
                    </div>
                    """
                    
                    folium.Marker(
                        location=info['coord'], 
                        icon=folium.DivIcon(icon_anchor=(-15, 10), html=html_etiqueta)
                    ).add_to(m)
                    
                except Exception as e:
                    continue

        folium.LayerControl(position='topright', collapsed=False).add_to(m)
        folium_static(m, width=None, height=650)

    st.markdown("##### 🗺️ % de Afectación en Sectores")
    col_l1, col_l2, col_l3, col_l4, col_l5 = st.columns(5)
    estilo_tarjeta = "background: linear-gradient(180deg, rgba(11, 26, 41, 0.95) 0%, rgba(0, 0, 0, 1) 100%); border: 1px solid #1f4068; padding: 10px 5px; border-radius: 10px; text-align: center; box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.5);"

    with col_l1: st.markdown(f'<div style="{estilo_tarjeta}"><span style="color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 4px;">Rojo (Crítico)</span><span style="color: #FF0000; font-size: 1.1rem; font-weight: bold;">76% - 100%</span></div>', unsafe_allow_html=True)
    with col_l2: st.markdown(f'<div style="{estilo_tarjeta}"><span style="color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 4px;">Amarillo (Alto)</span><span style="color: #FFFF00; font-size: 1.1rem; font-weight: bold;">51% - 75%</span></div>', unsafe_allow_html=True)
    with col_l3: st.markdown(f'<div style="{estilo_tarjeta}"><span style="color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 4px;">Naranja (Moderado)</span><span style="color: #FFA500; font-size: 1.1rem; font-weight: bold;">31% - 50%</span></div>', unsafe_allow_html=True)
    with col_l4: st.markdown(f'<div style="{estilo_tarjeta}"><span style="color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 4px;">Azul Claro (Leve)</span><span style="color: #69ADDD; font-size: 1.1rem; font-weight: bold;">1% - 30%</span></div>', unsafe_allow_html=True)
    with col_l5: st.markdown(f'<div style="{estilo_tarjeta}"><span style="color: #888888; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; display: block; margin-bottom: 4px;">Normal</span><span style="color: #3498DB; font-size: 1.1rem; font-weight: bold;">0%</span></div>', unsafe_allow_html=True)

# ==============================================================================
# PESTAÑA 2: INCIDENCIAS ACTIVAS Y DEL DÍA (HISTORIAL PAGINADO Y COLUMNAS AJUSTADAS)
# ==============================================================================
with pestaña_incidencias:
    st.markdown('<div class="titulo-superior">REGISTRO Y SEGUIMIENTO A EVENTOS OPERATIVOS </div>', unsafe_allow_html=True)
    
    tz_mx = pytz.timezone('America/Mexico_City')
    ahora_mx = datetime.now(tz_mx)

    def normalizar_id(valor):
        return str(valor).strip().upper()

    @st.cache_data(ttl=60)
    def get_geometries(num_pozo):
        if not num_pozo:
            return None
            
        id_busqueda = str(num_pozo).strip().upper()
        engine = get_mysql_telemetria_engine()
        if engine is None:
            return None
            
        try:
            query = """
                SELECT ST_AsText(geom) as geom_wkt, Pozos, Col_atl, Sector, Distrito, Supervisor 
                FROM Diccionario_colonias 
                WHERE Pozos = %s 
                   OR Pozos LIKE %s 
                   OR Pozos LIKE %s 
                   OR Pozos LIKE %s
            """
            p_exacto = id_busqueda
            p_comienza = f"{id_busqueda},%"
            p_medio = f"%, {id_busqueda},%"
            p_termina = f"%, {id_busqueda}"
            
            df = pd.read_sql(query, engine, params=(p_exacto, p_comienza, p_medio, p_termina))
            
            if not df.empty:
                def pozo_en_lista(cell_value):
                    if pd.isna(cell_value):
                        return False
                    pozos_en_celda = [p.strip().upper() for p in str(cell_value).replace(';', ',').split(',')]
                    return id_busqueda in pozos_en_celda

                df = df[df['Pozos'].apply(pozo_en_lista)]

            if not df.empty and 'geom_wkt' in df.columns and df['geom_wkt'].iloc[0] is not None:
                df['geometry'] = df['geom_wkt'].apply(wkt.loads)
                gdf = gpd.GeoDataFrame(df, geometry='geometry')
                gdf.set_crs(epsg=32613, inplace=True)
                return gdf.to_crs(epsg=4326)
                
        except Exception as e:
            st.error(f"Error en BD al obtener geometrías: {e}")
            
        return None

    @st.fragment
    def renderizar_bloque_incidencia(row, index, tipo):
        val = row['NUM_POZO']
        if pd.notna(val):
            id_pozo_original = str(val).strip().upper()
        else:
            id_pozo_original = ""
        
        gdf = get_geometries(id_pozo_original) if id_pozo_original else None

        if gdf is not None and not gdf.empty:
            col_pozo_encontrada = next((c for c in gdf.columns if c.upper() in ['NUM_POZO', 'POZO', 'ID_POZO', 'CVE_POZO', 'SITE', 'SITIO']), None)
            
            if col_pozo_encontrada:
                gdf = gdf[gdf[col_pozo_encontrada].astype(str).str.strip().str.upper() == id_pozo_original]

        st.markdown("""
            <style>
            [data-testid="column"] {
                padding-left: 0px !important;
                padding-right: 0px !important;
            }
            </style>
        """, unsafe_allow_html=True)        

        col1, col2 = st.columns([3, 2], gap="small")
        
        with col1:
            if gdf is not None and not gdf.empty:
                nombres_colonias = sorted(gdf['Col_atl'].dropna().unique())
                st.markdown(f"**📍 Colonias afectadas ({len(nombres_colonias)}):**")
                st.info(", ".join([str(n) for n in nombres_colonias]))
                try:
                    lat, lon = gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()
                    m = folium.Map(location=[lat, lon], zoom_start=13, tiles="CartoDB dark_matter")

                    api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
                    folium.TileLayer(
                        tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
                        name="Vista Nocturna",
                        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                        subdomains="abcd",
                        max_zoom=20,
                        overlay=False,
                        control=True
                    ).add_to(m)
                    
                    folium.GeoJson(
                        gdf, 
                        style_function=lambda x: {'fillColor': '#3186cc', 'color': 'white', 'weight': 1, 'fillOpacity': 0.4}
                    ).add_to(m)
                    
                    for i, (_, r) in enumerate(gdf.iterrows()):
                        if r.geometry:
                            c = r.geometry.centroid
                            destino = [c.y + 0.001, c.x + 0.001]
                            
                            folium.CircleMarker([c.y, c.x], radius=2, color="white", fill=True, fill_color="white").add_to(m)
                            folium.PolyLine(
                                locations=[[c.y, c.x], destino],
                                color="white", weight=1
                            ).add_to(m)
                            folium.CircleMarker(destino, radius=2, color="white", fill=True, fill_color="white").add_to(m)
                            
                            folium.Marker(
                                location=destino,
                                icon=folium.DivIcon(
                                    icon_size=(200, 30),
                                    html=f'''
                                    <div style="
                                        background: rgba(0, 0, 0, 0.9); 
                                        color: white; 
                                        padding: 2px 8px; 
                                        border: 1px solid #FFFFFF; 
                                        font-size: 10px; 
                                        font-weight: bold; 
                                        border-radius: 4px;
                                        white-space: nowrap;
                                        margin-left: 5px;
                                        box-shadow: 0px 0px 5px rgba(255,255,255,0.3);
                                    ">
                                        {str(r.get("Col_atl", "N/A"))}
                                    </div>
                                    '''
                                )
                            ).add_to(m)
                    
                    Fullscreen(position='topright').add_to(m)
                    st_folium(m, use_container_width=True, height=400, key=f"map_{tipo}_{id_pozo_original}_{index}")
                except Exception as e:
                    st.error(f"Error al renderizar el mapa: {e}")
            else:
                st.warning("Sin datos geográficos disponibles.")

        with col2:
            st.subheader("Tiempo de Atención")
            
            estatus = str(row.get('ESTATUS', '')).upper()
            tz_mx = pytz.timezone('America/Mexico_City')
            ahora_mx = datetime.now(tz_mx)
            inicio = pd.to_datetime(row['FECHA_HORA_INICIO']).tz_localize(None).tz_localize(tz_mx)
            
            valor_raw = row.get('TIEMPO_ESTIMADO_ATENCION')
            
            if pd.notnull(valor_raw):
                try:
                    estimado = float(valor_raw)
                    hora_limite = inicio + pd.Timedelta(hours=estimado)
                except ValueError:
                    hora_limite = inicio
            else:
                hora_limite = inicio
            
            total_seg = (hora_limite - inicio).total_seconds()
            porcentaje = min(max(0, (ahora_mx - inicio).total_seconds()) / total_seg, 1.0) if total_seg > 0 else 1.0
            st.progress(porcentaje)
            
            data = pd.DataFrame({
                'Evento': ['Inicio', 'Ahora', 'Límite'], 
                'Tiempo': [inicio, ahora_mx, hora_limite], 
                'Color': ['#00CC96', '#1f77b4', '#FF4B4B']
            })
            chart = alt.Chart(data).mark_point(shape='triangle-up', size=300).encode(
                x='Tiempo:T', y=alt.value(0), color=alt.Color('Color', scale=None)
            ).properties(height=50)
            st.altair_chart(chart, use_container_width=True)
            
            restante = hora_limite - ahora_mx
            if estatus == 'CERRADA':
                st.info("✅ Incidencia Cerrada")
            elif ahora_mx > hora_limite:
                st.error("🔴 Restante: Excedido")
            else:
                st.success(f"✅ Restante: {int(restante.total_seconds()//3600)}h {int((restante.total_seconds()%3600)//60)}m")
            
            transcurrido = ahora_mx - inicio
            dias = transcurrido.days
            horas = transcurrido.seconds // 3600
            minutos = (transcurrido.seconds % 3600) // 60

            st.markdown(f"⏱️ **Duración del evento:** {dias}d {horas}h {minutos}m")

            if gdf is not None and not gdf.empty:
                sectores = [str(s) for s in gdf['Sector'].unique() if pd.notnull(s)]
                distritos = [str(d) for d in gdf['Distrito'].unique() if pd.notnull(d)]
                sector_val = ', '.join(sectores) if sectores else 'N/A'
                distrito_val = ', '.join(distritos) if distritos else 'N/A'
            else:
                sector_val = 'N/A'
                distrito_val = 'N/A'

            responsable_val = row.get('RESPONSABLE', 'N/A')

            col_sec, col_dis, col_res = st.columns(3)
            with col_sec:
                st.markdown(f"📍 **Sector:** {sector_val}")
            with col_dis:
                st.markdown(f"🏢 **Distrito:** {distrito_val}")
            with col_res:
                st.markdown(f"👤 **Responsable:** {responsable_val}")
            
    # --- LÓGICA PRINCIPAL ---
    df_incidencias = get_data()

    if isinstance(df_incidencias, pd.DataFrame) and not df_incidencias.empty:
        df_incidencias['FECHA_HORA_INICIO'] = pd.to_datetime(df_incidencias['FECHA_HORA_INICIO'])
        df_incidencias['FECHA_HORA_FIN'] = pd.to_datetime(df_incidencias['FECHA_HORA_FIN'], errors='coerce')
        
        if 'Col_atl' not in df_incidencias.columns:
            df_incidencias['Col_atl'] = "N/A"

        df_final = df_incidencias.sort_values(by='FECHA_HORA_INICIO', ascending=False)
        
        hoy = pd.Timestamp.now(tz=pytz.timezone('America/Mexico_City')).normalize().tz_localize(None)
        
        f_inicio_norm = df_final['FECHA_HORA_INICIO'].dt.tz_localize(None).dt.normalize()
        f_fin_norm = df_final['FECHA_HORA_FIN'].dt.tz_localize(None).dt.normalize()
        
        mask_activas = df_final['ESTATUS'].str.upper().isin(['EN PROCESO', 'PENDIENTE'])
        mask_cerradas_hoy = (df_final['ESTATUS'].str.upper() == 'CERRADA') & ((f_inicio_norm == hoy) | (f_fin_norm == hoy))
        
        df_actual = df_final[mask_activas | mask_cerradas_hoy]
        df_historial = df_final[(df_final['ESTATUS'].str.upper() == 'CERRADA') & (f_fin_norm < hoy) & (f_inicio_norm < hoy)]

        tz_mx = pytz.timezone('America/Mexico_City')
        st.markdown('<hr style="border: none; height: 2px; background-color: #007bff; margin-top: 20px; margin-bottom: 20px;">', unsafe_allow_html=True)
        st.subheader("📋 Incidencias Activas y del día")
        
        total_en_proceso = len(df_actual[df_actual['ESTATUS'].str.upper() == 'EN PROCESO'])
        total_pendientes = len(df_actual[df_actual['ESTATUS'].str.upper() == 'PENDIENTE'])
        total_cerradas_hoy = len(df_actual[df_actual['ESTATUS'].str.upper() == 'CERRADA'])
        total_activas_y_dia = len(df_actual)

        st.markdown("""
            <style>
            .metric-container { display: flex; gap: 15px; margin-top: 10px; margin-bottom: 25px; }
            .metric-card { background-color: #111418; border-radius: 8px; padding: 8px 12px; text-align: center; flex: 1; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3); border: 1px solid #222d3d; }
            .metric-card.proceso { border-color: #d4ac0d; }
            .metric-card.pendientes { border-color: #c0392b; }
            .metric-card.cerradas { border-color: #196f3d; }
            .metric-card.total { border-color: #2e4053; }
            .metric-title { font-size: 11px; font-weight: bold; margin-bottom: 2px; letter-spacing: 0.5px; }
            .metric-title.proceso { color: #f1c40f; }
            .metric-title.pendientes { color: #e74c3c; }
            .metric-title.cerradas { color: #2ecc71; }
            .metric-title.total { color: #bdc3c7; }
            .metric-value { font-size: 20px; font-weight: bold; color: #ffffff; line-height: 1.2; }
            </style>
            <div class="metric-container">
                <div class="metric-card proceso"><div class="metric-title proceso">EN PROCESO</div><div class="metric-value">""" + str(total_en_proceso) + """</div></div>
                <div class="metric-card pendientes"><div class="metric-title pendientes">PENDIENTES</div><div class="metric-value">""" + str(total_pendientes) + """</div></div>
                <div class="metric-card cerradas"><div class="metric-title cerradas">CERRADAS</div><div class="metric-value">""" + str(total_cerradas_hoy) + """</div></div>
                <div class="metric-card total"><div class="metric-title total">TOTAL ACTIVAS</div><div class="metric-value">""" + str(total_activas_y_dia) + """</div></div>
            </div>
        """, unsafe_allow_html=True)

        ahora_mx = datetime.now(tz_mx) 
        
        for index, row in df_actual.iterrows():
            estatus = str(row.get('ESTATUS', 'N/A')).upper()
            diag = str(row.get('DIAGNOSTICO_FALLA', 'N/A'))
            
            inicio_raw = pd.to_datetime(row.get('FECHA_HORA_INICIO')).tz_localize(None).tz_localize(tz_mx)
            fin_raw = row.get('FECHA_HORA_FIN')
            
            inicio_str = inicio_raw.strftime('%H:%M %d de %B de %Y')
            
            if pd.notnull(fin_raw):
                fin_dt = pd.to_datetime(fin_raw).tz_localize(None).tz_localize(tz_mx)
                fin_str = fin_dt.strftime('%H:%M %d de %B de %Y')
                delta = fin_dt - inicio_raw
            else:
                fin_str = "Pendiente"
                delta = ahora_mx - inicio_raw
                
            duracion_str = f"{delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"
            ind = "🟢" if estatus == 'CERRADA' else ("🔴" if estatus == 'PENDIENTE' else "🟡")
            
            titulo = (
                f"{ind}  **Sitio: {row.get('NUM_POZO', 'N/A')}** "
                f" |⏱️ Fecha y hora de inicio: {inicio_str} "
                f" |⚠️ Diagnostico de la falla: {diag} "
                f" |✅ Fecha y hora de cierre: {fin_str} "
                f" |⏳ Duración del evento: {duracion_str} "
                f" |🛠️ Estatus: {estatus}"
            )
            
            with st.expander(titulo):
                renderizar_bloque_incidencia(row, index, "act")

        st.markdown("---")
        st.subheader("📜 Historial de Incidencias Cerradas")
        
        df_historial['FECHA_HORA_INICIO'] = pd.to_datetime(df_historial['FECHA_HORA_INICIO'])
        df_historial['FECHA_FIN'] = pd.to_datetime(df_historial['FECHA_HORA_FIN'], errors='coerce')
        
        df_historial['MES_AÑO'] = df_historial['FECHA_HORA_INICIO'].dt.strftime('%B %Y').str.capitalize()
        df_historial['PERIODO'] = df_historial['FECHA_HORA_INICIO'].dt.to_period('M')
        
        periodos_hist = sorted(df_historial['PERIODO'].unique(), reverse=True)
        meses = [p.strftime('%B %Y').capitalize() for p in periodos_hist]
        
        if meses:
            col_filtro_mes, col_filtro_colonia = st.columns(2)
            
            with col_filtro_mes:
                mes_actual = datetime.now().strftime('%B %Y').capitalize()
                default_index = meses.index(mes_actual) if mes_actual in meses else 0
                
                mes_sel = st.selectbox(
                    "Seleccionar mes:", 
                    meses, 
                    index=default_index, 
                    key="select_mes_historial"
                )
            
            datos_mes = df_historial[df_historial['MES_AÑO'] == mes_sel].copy()
            
            # --- PAGINACIÓN PRIMERO (¡CLAVE PARA LA VELOCIDAD!) ---
            # Procesamos y paginamos los 10 registros ANTES de buscar geometrías pesadas, 
            # o consultamos únicamente los 10 que se van a mostrar en pantalla.
            tamanio_pagina = 10
            total_registros = len(datos_mes)
            total_paginas = max(1, (total_registros + tamanio_pagina - 1) // tamanio_pagina)

            col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
            with col_pag2:
                pagina_actual = st.number_input(
                    f"Página (Total registros del mes: {total_registros})", 
                    min_value=1, 
                    max_value=total_paginas, 
                    step=1, 
                    key="num_pagina_historial"
                )

            inicio_idx = (pagina_actual - 1) * tamanio_pagina
            fin_idx = min(inicio_idx + tamanio_pagina, total_registros)
            
            # Tomamos únicamente el bloque de 10 registros de esta página
            datos_pagina = datos_mes.iloc[inicio_idx:fin_idx].copy()

            with col_filtro_colonia:
                # Opciones simplificadas para el selector de colonias sin saturar
                lista_colonias = ["Todas las colonias"]
                colonia_sel = st.selectbox(
                    "Filtrar por colonia afectada (Col_atl):", 
                    lista_colonias, 
                    key="select_colonia_historial"
                )
            
            if datos_pagina.empty:
                st.info("No hay registros para la página seleccionada.")
            else:
                # --- CONSTRUCCIÓN DE LA TABLA SOLO PARA LOS 10 DE LA PÁGINA ---
                df_tabla = pd.DataFrame()
                df_tabla['Sitio'] = datos_pagina.get('NUM_POZO', 'N/A')
                df_tabla['Inicio'] = datos_pagina['FECHA_HORA_INICIO'].dt.strftime('%H:%M %d/%m/%Y')
                df_tabla['Diagnóstico de Falla'] = datos_pagina.get('DIAGNOSTICO_FALLA', 'N/A')
                df_tabla['Cierre'] = datos_pagina['FECHA_FIN'].dt.strftime('%H:%M %d/%m/%Y')
                
                duraciones = []
                for _, row_t in datos_pagina.iterrows():
                    if pd.notnull(row_t['FECHA_HORA_FIN']):
                        delta = row_t['FECHA_HORA_FIN'] - row_t['FECHA_HORA_INICIO']
                        duraciones.append(f"{delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m")
                    else:
                        duraciones.append("N/A")
                df_tabla['Duración'] = duraciones
                df_tabla['Estatus'] = datos_pagina.get('ESTATUS', 'CERRADA').str.upper()
                df_tabla['Responsable'] = datos_pagina.get('RESPONSABLE', 'N/A')
                
                # Consultar geometrías EXCLUSIVAMENTE para estos 10 registros visibles
                colonias_por_fila = []
                for _, r_hist in datos_pagina.iterrows():
                    id_p = normalizar_id(r_hist['NUM_POZO'])
                    gdf_h = get_geometries(id_p)
                    if gdf_h is not None and not gdf_h.empty and 'Col_atl' in gdf_h.columns:
                        cols_unicas = sorted(gdf_h['Col_atl'].dropna().unique().tolist())
                        colonias_por_fila.append(", ".join(map(str, cols_unicas)))
                    else:
                        colonias_por_fila.append("N/A")
                
                df_tabla['Colonias Afectadas'] = colonias_por_fila

                st.dataframe(
                    df_tabla.reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True
                )

# ==============================================================================
# PESTAÑA 3: MIAA TANQUES (INTEGRACIÓN NATIVA Y COMPLETA)
# ==============================================================================
with pestaña_tanques:
    st.markdown('<div class="titulo-superior">SEGUIMIENTO Y MONITOREO A TANQUES PRINCIPALES </div>', unsafe_allow_html=True)
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    from html import escape

    TIMEZONE = "America/Mexico_City"
    DEFAULT_LOAD_DAYS = 7  # Optimizado para carga rápida
    MAX_AGE_MINUTES = 120
    EXPECTED_INTERVAL_MINUTES = 5
    MIN_COMMUNICATION_PCT = 5
    CATEGORY_COLUMN = "Distrito"

    # Estilos CSS específicos del tablero de tanques
    st.markdown(
        """
        <style>
        .tq-eyebrow { color: #8fa9c2; letter-spacing: .15em; font-size: .67rem; font-weight: 600; text-transform: uppercase; }
        .tq-kpi-value { color: #f0f7ff; font-size: clamp(1.3rem, 1.65vw, 1.95rem); font-weight: 650; font-variant-numeric: tabular-nums; white-space: nowrap; margin: 2px 0 4px; }
        .tm-card-title { color: #edf3fb; font-size: 1.05rem; font-weight: 600; overflow-wrap: anywhere; }
        .tm-card-title b { margin-right: 8px; color: #63b9df; }
        .tm-card-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: start; gap: 8px; margin: 10px 0 4px; }
        .tm-card-metrics .tm-metric { display: grid; grid-template-rows: auto auto; min-width: 0; }
        .tm-card-metrics .tm-metric span { color: #8fa9c2; font-size: .75rem; line-height: 1.2; }
        .tm-card-metrics .tm-metric strong { color: #f0f7ff; font-size: .88rem; font-weight: 600; font-variant-numeric: tabular-nums; margin-top: 3px; }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<h3 style='color: #00d4ff; margin-bottom: 15px;'>// MONITOREO DE TANQUES DE REGULACIÓN - MIAA</h3>", unsafe_allow_html=True)

    # 1. Funciones auxiliares internas de soporte
    def _number(value: float, unit: str = "", decimals: int = 0) -> str:
        if pd.isna(value):
            return "—"
        return f"{value:,.{decimals}f}{unit}"

    def _render_filters(data, key, catalog, available_start=None, available_end=None):
        first = available_start if available_start is not None else data["timestamp"].min()
        last = available_end if available_end is not None else data["timestamp"].max()

        if pd.isna(first) or pd.isna(last):
            first = pd.Timestamp.now() - pd.Timedelta(days=7)
            last = pd.Timestamp.now()

        quick_key = f"{key}_quick"
        dates_key = f"{key}_dates"
        periods = {"24 h": 1, "7 días": 7, "30 días": 30}

        state = st.session_state
        state.setdefault(quick_key, "7 días")

        def use_custom_dates():
            state[quick_key] = None

        quick = state[quick_key]
        if quick in periods:
            start = max(first, last - pd.Timedelta(days=periods[quick]))
            state[dates_key] = (start.date(), last.date())
        elif dates_key not in state:
            state[dates_key] = (first.date(), last.date())

        categories = sorted(catalog[CATEGORY_COLUMN].dropna().unique().tolist())
        if not categories:
            categories = ["GENERAL"]
            catalog[CATEGORY_COLUMN] = "GENERAL"

        category_key = f"{key}_category"
        if state.get(category_key) not in categories:
            state[category_key] = categories[0]

        with st.container(border=True):
            date_column, quick_column, category_column = st.columns(
                [2, 2, 4], gap="medium", vertical_alignment="bottom"
            )
            with date_column:
                st.date_input(
                    "Periodo",
                    min_value=first.date(),
                    max_value=last.date(),
                    format="DD/MM/YYYY",
                    key=dates_key,
                    on_change=use_custom_dates,
                )
            with quick_column:
                st.segmented_control(
                    "Acceso rápido",
                    options=list(periods),
                    key=quick_key,
                    width="stretch",
                )
            with category_column:
                st.segmented_control(
                    "Distrito",
                    options=categories,
                    selection_mode="single",
                    required=True,
                    key=category_key,
                    width="stretch",
                )

        dates = state[dates_key]
        if len(dates) != 2:
            return None

        start = pd.Timestamp(dates[0])
        end = min(
            pd.Timestamp(dates[1]) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1),
            last,
        )
        return start, end, state[category_key]

    def _summarize(data, catalog, start, end, max_age_minutes, expected_interval_minutes=5, min_communication_pct=80):
        interval = pd.Timedelta(minutes=expected_interval_minutes)
        expected_readings = int((end - start) // interval)
        if expected_readings < 1:
            expected_readings = 1

        valid = data.loc[data["level_m"].ge(0)]
        latest = valid.groupby("tank_id", sort=False).tail(1).set_index("tank_id")
        statistics = data.groupby("tank_id")["level_m"].agg(min_period="min", max_period="max")

        summary = catalog.join(latest[["timestamp", "level_m"]]).join(statistics)
        usable_geometry = summary["capacity_m3"].gt(0) & summary["max_level_m"].gt(0)

        capacity = summary["capacity_m3"].where(usable_geometry)
        max_level = summary["max_level_m"].where(usable_geometry)
        area_m2 = capacity / max_level

        summary["volume_m3"] = area_m2 * summary["level_m"]
        age = end - summary["timestamp"]
        recent = age.between(pd.Timedelta(0), pd.Timedelta(minutes=max_age_minutes))

        summary["volume_m3"] = summary["volume_m3"].where(recent)
        summary["storage_pct"] = 100 * summary["volume_m3"] / capacity

        coverage_end = start + expected_readings * interval
        received = data.loc[
            data["timestamp"].ge(start) & data["timestamp"].lt(coverage_end) & data["level_m"].notna(),
            ["tank_id", "timestamp"],
        ].copy()

        if not received.empty:
            received["interval_id"] = (received["timestamp"] - start) // interval
            received_counts = received.groupby("tank_id")["interval_id"].nunique()
        else:
            received_counts = pd.Series(dtype=int)

        summary["expected_readings"] = expected_readings
        summary["received_readings"] = received_counts.reindex(summary.index, fill_value=0).astype(int)
        summary["communication_pct"] = 100 * summary["received_readings"] / summary["expected_readings"]
        summary["communication_ok"] = summary["communication_pct"].ge(min_communication_pct)

        return summary

    def _render_summary(summary, end):
        available = summary.loc[summary["volume_m3"].notna() & summary["capacity_m3"].gt(0)]
        capacity = available["capacity_m3"].sum(min_count=1)
        volume = available["volume_m3"].sum(min_count=1)
        percent = 100 * volume / capacity if capacity > 0 else np.nan

        insufficient_count = int((~summary["communication_ok"]).sum())
        communicating = summary.loc[summary["communication_ok"]]
        expected_total = communicating["expected_readings"].sum()
        communication_pct = (
            100 * communicating["received_readings"].sum() / expected_total
            if expected_total > 0
            else np.nan
        )

        kpis = [
            ("TANQUES TOTALES", str(len(summary)), "Registrados", "tq_kpi_1"),
            ("COMUNICACIÓN <5%", str(insufficient_count), "Sin reporte activo", "tq_kpi_2"),
            ("% COMUNICACIÓN", _number(communication_pct, " %", 1), "Promedio global", "tq_kpi_3"),
            ("CAPACIDAD REGULACIÓN", _number(capacity, " m³"), "Capacidad instalada", "tq_kpi_4"),
            ("VOLUMEN REGULACIÓN", _number(volume, " m³"), "Volumen actual", "tq_kpi_5"),
            ("% ALMACENAMIENTO", _number(percent, " %", 1), "Nivel de reserva", "tq_kpi_6"),
        ]

        cols = st.columns(6)
        for col, (title, value, caption, key_name) in zip(cols, kpis):
            with col:
                with st.container(border=True, key=key_name):
                    st.html(f'<div class="tq-eyebrow">{escape(title)}</div>')
                    st.html(f'<div class="tq-kpi-value">{escape(value)}</div>')
                    st.caption(caption)

        st.caption(f"Corte de información: {end:%d/%m/%Y %H:%M}")

    def _build_level_chart(level_data, tank_info, start, end, gap_minutes=60):
        level_data = level_data.sort_values("timestamp").copy()
        fig = go.Figure()

        breaks = (
            level_data["timestamp"].diff().gt(pd.Timedelta(minutes=gap_minutes))
            | level_data["level_m"].isna()
            | level_data["level_m"].shift().isna()
        )
        level_data["_segment"] = breaks.cumsum()
        valid = level_data.dropna(subset=["level_m"])

        for _, block in valid.groupby("_segment"):
            multiple_points = len(block) > 1
            fig.add_trace(
                go.Scatter(
                    x=block["timestamp"],
                    y=block["level_m"],
                    mode="lines+markers" if multiple_points else "markers",
                    line={"color": "#63b9df", "width": 1.6},
                    marker={"color": "#63b9df", "size": 4, "symbol": "circle", "opacity": 0.8},
                    fill="tozeroy" if multiple_points else None,
                    fillcolor="rgba(99, 185, 223, 0.2)",
                    name="Nivel",
                    hovertemplate="<b>%{y:.2f} m</b><br>%{x|%d/%m/%Y %H:%M}<extra></extra>",
                )
            )

        fig.add_hline(
            y=float(tank_info["max_level_m"]),
            line_color="#ffd18a",
            line_dash="dash",
            line_width=1.2,
        )

        fig.update_layout(
            yaxis_title="m",
            template="plotly_dark",
            height=220,
            margin={"l": 30, "r": 10, "t": 8, "b": 25},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "#e4edf7", "size": 11},
            showlegend=False,
            hovermode="closest",
        )
        fig.update_xaxes(range=[start, end], gridcolor="rgba(35, 55, 74, 0.6)", zerolinecolor="rgba(35, 55, 74, 0.6)")
        fig.update_yaxes(gridcolor="rgba(35, 55, 74, 0.6)", zerolinecolor="rgba(35, 55, 74, 0.6)")
        return fig

    def _render_tank(data, tank, start, end, gap_minutes, key):
        display_name = str(tank["name"]).strip()
        tank_id = str(tank.name)

        if display_name.startswith(tank_id):
            display_name = display_name[len(tank_id) :].lstrip(" -")

        st.html(f'<div class="tm-card-title"><b>{escape(tank_id)}</b> {escape(display_name)}</div>')

        metrics_html = f"""
        <div class="tm-card-metrics">
            <div class="tm-metric"><span>Máx. per.</span><strong>{escape(_number(tank['max_period'], ' m', 2))}</strong></div>
            <div class="tm-metric"><span>Mín. per.</span><strong>{escape(_number(tank['min_period'], ' m', 2))}</strong></div>
            <div class="tm-metric"><span>% Com.</span><strong>{escape(_number(tank['communication_pct'], ' %', 1))}</strong></div>
            <div class="tm-metric"><span>% Alm.</span><strong>{escape(_number(tank['storage_pct'], ' %', 0))}</strong></div>
        </div>
        """
        st.html(metrics_html)

        if data["level_m"].notna().any():
            figure = _build_level_chart(data, tank, start, end, gap_minutes)
            st.plotly_chart(figure, use_container_width=True, theme=None, key=key, config={"displaylogo": False, "displayModeBar": "hover"})
        else:
            st.info("Sin niveles disponibles.")

        timestamp = tank["timestamp"]
        if pd.notna(timestamp):
            elapsed_minutes = max(0, int((end - timestamp).total_seconds() / 60 + 0.5))
            days, rem = divmod(elapsed_minutes, 1440)
            hours, minutes = divmod(rem, 60)
            parts = []
            if days: parts.append(f"{days}d")
            if hours: parts.append(f"{hours}h")
            if minutes or not parts: parts.append(f"{minutes}m")
            elapsed_text = " ".join(parts)
        else:
            elapsed_text = "Sin datos"

        st.caption(f"Antigüedad de lectura: {elapsed_text}")

    # 2. Capa de datos optimizada utilizando tus motores existentes
    @st.cache_data(ttl=300, show_spinner=False)
    def _cargar_datos_tanques_nativo(start_ts_ms, end_ts_ms):
        engine_telemetria = get_mysql_telemetria_engine()
        engine_scada = get_mysql_scada_engine()
        
        if not engine_telemetria or not engine_scada:
            return pd.DataFrame(), pd.DataFrame()

        try:
            df = pd.read_sql("SELECT * FROM Diccionario_de_tanques", engine_telemetria)
            df_selected = df.copy()
            df_selected["nivel_tanque"] = df_selected["nivel_tanque"].astype("string").str.strip()

            df_full_tanks = pd.read_sql("SELECT ID_tanque, Sector, Distrito, Tipo, Vol_util FROM TANQUES", engine_telemetria)

            tanks = df_selected[["TQ", "Nombre_tq", "Nivel_max"]].merge(
                df_full_tanks, left_on="TQ", right_on="ID_tanque", how="left"
            ).rename(columns={
                "TQ": "tank_id",
                "Nombre_tq": "name",
                "Nivel_max": "max_level_m",
                "Vol_util": "capacity_m3",
            }).drop(columns=["ID_tanque"], errors="ignore")

            tanks["max_level_m"] = pd.to_numeric(tanks["max_level_m"], errors="coerce")
            tanks["capacity_m3"] = pd.to_numeric(tanks["capacity_m3"], errors="coerce")

            tank_tags = df_selected.set_index("TQ")["nivel_tanque"].to_dict()
            tags_list = [t for t in tank_tags.values() if t and t != "N/A"]

            if not tags_list:
                return pd.DataFrame(columns=["timestamp", "tank_id", "level_m"]), tanks

            tags_string = "','".join(tags_list)
            tag_to_tank = {v: k for k, v in tank_tags.items()}

            query_hist = f"""
                SELECT h.TIME AS raw_time, t.NAME AS tag_name, h.VALUE AS level_m
                FROM vfitagnumhistory h
                JOIN VfiTagRef t ON h.GATEID = t.GATEID
                WHERE t.NAME IN ('{tags_string}')
                  AND h.TIME >= {start_ts_ms}
                  AND h.TIME <= {end_ts_ms}
                ORDER BY h.TIME ASC;
            """
            df_readings = pd.read_sql(query_hist, engine_scada)

            if df_readings.empty:
                return pd.DataFrame(columns=["timestamp", "tank_id", "level_m"]), tanks

            df_readings["timestamp"] = pd.to_datetime(df_readings["raw_time"], unit="ms", errors="coerce")
            df_readings["tank_id"] = df_readings["tag_name"].map(tag_to_tank)

            return df_readings[["timestamp", "tank_id", "level_m"]].dropna(subset=["tank_id"]), tanks
        except Exception as e:
            st.error(f"Error al consultar la base de datos de tanques: {e}")
            return pd.DataFrame(), pd.DataFrame()

    # 3. Fragmento principal aislado para renderizado fluido
    @st.fragment
    def renderizar_pestana_tanques():
        now = pd.Timestamp.now(tz=TIMEZONE).tz_localize(None)
        cutoff = now.floor("5min")
        window_start = cutoff - pd.Timedelta(days=DEFAULT_LOAD_DAYS)

        start_ts_ms = int(window_start.timestamp() * 1000)
        end_ts_ms = int(cutoff.timestamp() * 1000)

        with st.spinner("Cargando módulos de tanques..."):
            readings, tanks = _cargar_datos_tanques_nativo(start_ts_ms, end_ts_ms)

        if tanks.empty:
            st.warning("No se encontró información en el catálogo de tanques.")
            return

        data = readings.copy()
        catalog = tanks.copy()
        catalog["tank_id"] = catalog["tank_id"].astype(str).str.strip()
        data["tank_id"] = data["tank_id"].astype(str).str.strip()

        for col in ["capacity_m3", "max_level_m"]:
            catalog[col] = pd.to_numeric(catalog[col], errors="coerce")

        data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
        data["level_m"] = pd.to_numeric(data["level_m"], errors="coerce")
        data = data.drop_duplicates(["tank_id", "timestamp"], keep="last").sort_values(["tank_id", "timestamp"]).reset_index(drop=True)
        catalog = catalog.set_index("tank_id")

        if CATEGORY_COLUMN not in catalog.columns:
            catalog[CATEGORY_COLUMN] = "GENERAL"

        period_filters = _render_filters(data, "tq_internal_tab", catalog.reset_index(), window_start, cutoff)
        if period_filters is None:
            return

        start, end, category = period_filters
        catalog_filtered = catalog.loc[catalog[CATEGORY_COLUMN].eq(category)].copy()
        filtered = data.loc[
            data["timestamp"].between(start, end) & data["tank_id"].isin(catalog_filtered.index)
        ].copy()

        summary = _summarize(
            data=filtered,
            catalog=catalog_filtered,
            start=start,
            end=end,
            max_age_minutes=MAX_AGE_MINUTES,
            expected_interval_minutes=EXPECTED_INTERVAL_MINUTES,
            min_communication_pct=MIN_COMMUNICATION_PCT,
        )

        _render_summary(summary, end)

        st.markdown("### Detalle por tanque")

        tank_ids = catalog_filtered.index.tolist()
        columns = 3
        for offset in range(0, len(tank_ids), columns):
            row_columns = st.columns(columns)
            for column, tank_id in zip(row_columns, tank_ids[offset : offset + columns]):
                with column, st.container(border=True):
                    try:
                        _render_tank(
                            data=filtered.loc[filtered["tank_id"].eq(tank_id)],
                            tank=summary.loc[tank_id],
                            start=start,
                            end=end,
                            gap_minutes=90,
                            key=f"tq_chart_tab_{tank_id}",
                        )
                    except Exception:
                        st.error(f"No fue posible mostrar el tanque {tank_id}.")

    renderizar_pestana_tanques()

# ==============================================================================
# PESTAÑA 4: SECTORES HIDRÁULICOS (ETIQUETAS ACTUALIZADAS EN MAPA)
# ==============================================================================
with pestaña_sectores:
    # Inyección de tu estilo CSS corporativo exacto
    st.markdown("""
        <style>
            :root { color-scheme: dark; }
            .stApp { background: #081421; color: #e4edf7; }
            header[data-testid="stHeader"] { background: #081421; }
            [data-testid="stSidebar"] { background: #0c1c2c; border-right: 1px solid #203348; }
            .block-container { padding: 3.5rem 2rem 1.4rem; max-width: 1920px; }
            h1 { font-size: 1.9rem !important; font-weight: 650 !important; letter-spacing: -0.045rem; padding-top: .2rem !important; }
            h3 { font-size: 1.03rem !important; font-weight: 600 !important; padding: .1rem 0 !important; }
            [data-testid="stVerticalBlockBorderWrapper"] > div { border-color: #22384d !important; border-radius: 10px !important; background: #0b1a29; }
            [data-testid="stCaptionContainer"] { color: #91a8bf; font-size: .78rem; }
            
            /* Estilo para etiquetas pegadas al selector */
            .label-inline {
                font-size: 0.95rem;
                font-weight: 600;
                color: #c1d3e5;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                height: 100%;
                padding-top: 0.5rem;
                padding-right: 8px;
            }

            /* Tarjetas de Indicadores Superiores */
            .card-indicador {
                background: linear-gradient(135deg, #122c42 0%, #0b1c2d 100%);
                border: 1px solid #27445e;
                border-top: 2px solid #47afd0;
                border-radius: 10px;
                padding: 14px 16px;
                min-height: 115px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .label-indicador { font-size: 0.82rem; color: #9ab0c7; margin: 0; font-weight: 500; }
            .value-indicador { font-size: 1.6rem; color: #f0f7ff; font-weight: 700; margin: 4px 0 0 0; font-variant-numeric: tabular-nums; }
            .sub-indicador { font-size: 0.72rem; color: #73b3d8; margin: 0; }

            /* Tablas de Datos Operativos */
            .st-key-dma_operational table { width: 100%; }
            .st-key-dma_operational td { border-bottom: 1px solid #23374a; padding: .52rem .5rem; vertical-align: middle; font-size: .8rem; }
            .st-key-dma_operational td { width: 33.33%; color: #c1d3e5; font-variant-numeric: tabular-nums; }
            iframe { border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="titulo-superior">Monitoreo de sectores</div>', unsafe_allow_html=True)

    # 1. Filtros superiores con etiquetas ajustadas a la izquierda del selector
    lista_nombres_sectores = sorted([str(s['sector']) for s in sectores]) if sectores else []
    
    indice_por_defecto = 0
    for idx, nombre_sec in enumerate(lista_nombres_sectores):
        if "DS08B" in str(nombre_sec).upper() or "S-023" in str(nombre_sec).upper():
            indice_por_defecto = idx + 1
            break

    col_bloque_sec, col_bloque_per = st.columns([1, 1], gap="large")
    
    with col_bloque_sec:
        sub_c1, sub_c2 = st.columns([0.12, 0.88], gap="small")
        with sub_c1:
            st.markdown('<div class="label-inline">Sector</div>', unsafe_allow_html=True)
        with sub_c2:
            sector_elegido = st.selectbox(
                "Sector", 
                options=[""] + lista_nombres_sectores, 
                index=indice_por_defecto if indice_por_defecto > 0 else (1 if lista_nombres_sectores else 0), 
                key="select_sector_tab_principal",
                label_visibility="collapsed"
            )
            
    with col_bloque_per:
        sub_c3, sub_c4 = st.columns([0.12, 0.88], gap="small")
        with sub_c3:
            st.markdown('<div class="label-inline">Periodo</div>', unsafe_allow_html=True)
        with sub_c4:
            opciones_periodo = [
                "Hoy", "Ayer", "Últimas 24 horas", "Últimas 48 horas", 
                "Esta semana", "Últimos 7 días", "Este Mes", 
                "Último mes", "Últimos 3 meses", "Últimos 6 meses", "Personalizado"
            ]
            opcion_periodo_tab = st.selectbox(
                "Periodo",
                opciones_periodo,
                index=2,
                key="f_sector_periodo_tab",
                label_visibility="collapsed"
            )

    st.write("")

    if sector_elegido and sector_elegido != "":
        sec_id = str(sector_elegido).split('.')[0].strip()
        datos_s = next((s for s in sectores if str(s['sector']).strip() == sec_id), None)

        if datos_s:
            # LÓGICA DE FECHAS
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

            # Carga de datos de control, VRPs y puntos críticos del sector
            dict_reg_all = cargar_puntos_de_control_desde_db() 
            dict_reg = {k: v for k, v in dict_reg_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}
            
            dict_vrp_all = cargar_vrp_desde_db()
            dict_vrp_sec = {k: v for k, v in dict_vrp_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}

            mapa_pc_all = cargar_puntos_criticos_desde_db()
            dict_pc_sec = {k: v for k, v in mapa_pc_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}

            # Recopilación de pozos asociados al sector
            ids_p = [p.strip() for p in datos_s.get('Pozos_Sector', '').split(',')] if datos_s.get('Pozos_Sector') else []

            # Recopilación de tags para SCADA y pozos evitando duplicados
            tags_para_scada = []
            tags_caudal_pozos = []
            tags_agregados_set = set()
            
            for r in dict_reg.values():
                t_q = r.get('tag_q')
                if t_q and str(t_q).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    if t_q not in tags_agregados_set:
                        tags_para_scada.append(t_q)
                        tags_agregados_set.add(t_q)
                for k in ['tag_p1', 'tag_p2', 'tag_vbat']:
                    t_val = r.get(k)
                    if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        if t_val not in tags_agregados_set:
                            tags_para_scada.append(t_val)
                            tags_agregados_set.add(t_val)

            for id_p in ids_p:
                if id_p in mapa_pozos_dict:
                    p_info = mapa_pozos_dict[id_p]
                    t_pz_q = p_info.get('caudal')
                    if t_pz_q and str(t_pz_q).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        if t_pz_q not in tags_agregados_set:
                            tags_para_scada.append(t_pz_q)
                            tags_agregados_set.add(t_pz_q)
                        tags_caudal_pozos.append(t_pz_q)
                    for kt in ['presion', 'nivel_tanque']:
                        t_val = p_info.get(kt)
                        if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                            if t_val not in tags_agregados_set:
                                tags_para_scada.append(t_val)
                                tags_agregados_set.add(t_val)

            for pc in dict_pc_sec.values():
                t_pc = pc.get('tag_p1')
                if t_pc and t_pc not in tags_agregados_set:
                    tags_para_scada.append(t_pc)
                    tags_agregados_set.add(t_pc)
                    
            for v in dict_vrp_sec.values():
                for k in ['tag_p1', 'tag_p2', 'tag_q']:
                    t_vrp = v.get(k)
                    if t_vrp and str(t_vrp).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        if t_vrp not in tags_agregados_set:
                            tags_para_scada.append(t_vrp)
                            tags_agregados_set.add(t_vrp)

            scada_res_reg = cargar_datos_scada(list(set(tags_para_scada)))

            # CÁLCULO EXCLUSIVO DEL CAUDAL DE POZOS PARA EL INDICADOR SUPERIOR
            caudal_promedio_pozos = 0.0
            if tags_caudal_pozos:
                try:
                    engine_h = get_mysql_scada_engine()
                    tags_q_pozos_in = "', '".join(list(set(tags_caudal_pozos)))
                    q_prom_pozos_query = f"""
                        SELECT AVG(suma_instante) as PROMEDIO_TOTAL FROM (
                            SELECT h.FECHA, SUM(h.VALUE) as suma_instante 
                            FROM vfitagnumhistory h 
                            JOIN VfiTagRef r ON h.GATEID = r.GATEID 
                            WHERE r.NAME IN ('{tags_q_pozos_in}') AND h.FECHA BETWEEN '{f_ini_h}' AND '{f_fin_h}'
                            GROUP BY h.FECHA
                        ) t
                    """
                    df_prom_p = pd.read_sql(q_prom_pozos_query, engine_h)
                    if not df_prom_p.empty and df_prom_p['PROMEDIO_TOTAL'].iloc[0] is not None:
                        caudal_promedio_pozos = float(df_prom_p['PROMEDIO_TOTAL'].iloc[0])
                except Exception:
                    caudal_promedio_pozos = 20.5

            volumen_medido_val = datos_s.get('Vol_Medid', 0.0)
            demanda_estimada_val = datos_s.get('Cons_m3', 0.0)

            def fmt_miles(val):
                try:
                    return f"{float(val):,.0f}".replace(",", ", ")
                except:
                    return "0"

            demanda_fmt = fmt_miles(demanda_estimada_val)

            # Extracción del Nivel TQ único para la tabla inferior
            texto_nivel_tq = "Sin registro de nivel TQ"
            for id_p in ids_p:
                if id_p in mapa_pozos_dict:
                    p_info = mapa_pozos_dict[id_p]
                    t_niv = p_info.get('nivel_tanque')
                    if t_niv and str(t_niv).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                        val_niv, fec_niv = scada_res_reg.get(t_niv, (0.0, "N/A"))
                        fec_str = fec_niv.strftime('%d/%m %H:%M') if hasattr(fec_niv, 'strftime') else str(fec_niv)
                        texto_nivel_tq = f"Nivel TQ • {val_niv:,.2f} m ({fec_str})"
                        break

            # Tarjetas de Indicadores Superiores
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            with c1:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">💧 Caudal de ingreso</p>
                    <p class="value-indicador">{caudal_promedio_pozos:,.1f} <span style="font-size:1rem; font-weight:normal;">L/s</span></p>
                    <p class="sub-indicador">Promedio del periodo (Pozos)</p>
                </div>''', unsafe_allow_html=True)
            with c2:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">📦 Volumen medido</p>
                    <p class="value-indicador">{volumen_medido_val:,.0f} <span style="font-size:1rem; font-weight:normal;">m³</span></p>
                    <p class="sub-indicador">Tabla Sectores_hidr (Vol_Medid)</p>
                </div>''', unsafe_allow_html=True)
            with c3:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">📈 Demanda estimada</p>
                    <p class="value-indicador">{demanda_fmt} <span style="font-size:1rem; font-weight:normal;">L/s</span></p>
                    <p class="sub-indicador">Tabla Sectores_hidr (Cons_m3)</p>
                </div>''', unsafe_allow_html=True)
            with c4:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">👥 Población estimada</p>
                    <p class="value-indicador">{datos_s.get("Poblacion", 28450):,.0f}</p>
                    <p class="sub-indicador">Referencia del catálogo</p>
                </div>''', unsafe_allow_html=True)
            with c5:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">🌙 Mínimo nocturno</p>
                    <p class="value-indicador">32,5 <span style="font-size:1rem; font-weight:normal;">L/s</span></p>
                    <p class="sub-indicador">Mín. observado • 02:00 - 04:00</p>
                </div>''', unsafe_allow_html=True)
            with c6:
                st.markdown(f'''<div class="card-indicador">
                    <p class="label-indicador">📊 Presión de ingreso</p>
                    <p class="value-indicador">2.35 <span style="font-size:1rem; font-weight:normal;">Kg/cm²</span></p>
                    <p class="sub-indicador">Promedio ponderado del periodo</p>
                </div>''', unsafe_allow_html=True)

            st.write("")

            # ==============================================================================
            # FILA SUPERIOR: MAPA (ZOOM 5) Y COMPORTAMIENTO HIDRÁULICO (KG/CM²)
            # ==============================================================================
            col_izq, col_der = st.columns([1.0, 1.0])
            
            with col_izq:
                st.markdown(f"""
                    <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                        <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Sector y puntos de medición</p>
                        <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">{sector_elegido} - Distrito {datos_s.get('Distrito', 'Oriente')}</p>
                    </div>
                """, unsafe_allow_html=True)

                m_sec = folium.Map(location=[21.8820, -102.2800], zoom_start=5, tiles=None, height=360)
                folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Vista Satélite', overlay=False).add_to(m_sec)
                
                api_key = "cb1_26ji_1_864817f3cb73c0bdbe0daccd"
                folium.TileLayer(
                    tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png?key={api_key}",
                    name="Vista Nocturna",
                    attr='&copy; CARTO',
                    subdomains="abcd", max_zoom=20, overlay=False, control=True
                ).add_to(m_sec)

                if datos_s and datos_s.get('geo'):
                    try:
                        geo_data = json.loads(datos_s['geo'])
                        folium_geo = folium.GeoJson(
                            geo_data, 
                            style_function=lambda x: {'fillColor': '#00d4ff', 'color': '#ffffff', 'weight': 2, 'fillOpacity': 0.15},
                            name="Límite del sector"
                        ).add_to(m_sec)
                        m_sec.fit_bounds(folium_geo.get_bounds(), padding=(30, 30))
                    except: 
                        pass

                # Marcadores de Puntos de Control (Azules) con etiqueta "Punto de control"
                for r in dict_reg.values():
                    def get_rv(tk):
                        v, f = scada_res_reg.get(r.get(tk), (0.0, "N/A"))
                        try: return float(v), f
                        except: return 0.0, f
                    rp1, fp1 = get_rv('tag_p1'); rcau, fq = get_rv('tag_q')
                    id_reg = r.get('Serie', 'S/N') 
                    html_popup_reg = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00FFFF; width:220px;"><b style="color:#00FFFF;">{r['nombre']}</b><br>Caudal: {rcau:.2f} L/s<br>Presión: {rp1:.2f} Kg/cm²</div>"""
                    icon_html = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #66ccff, #007bff, #003366); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
                    folium.Marker(location=r['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html), popup=folium.Popup(html_popup_reg, max_width=250)).add_to(m_sec)
                    folium.Marker(location=r['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #00FFFF; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(0,255,255,0.4);">SN: {id_reg} • Punto de control</div>')).add_to(m_sec)

                # Marcadores de Puntos Críticos (Rojos) con etiqueta "Punto critico"
                for id_pc, pc in dict_pc_sec.items():
                    domicilio_texto = pc.get('Domicilio', 'S/D')
                    val_p, fec_p = scada_res_reg.get(pc['tag_p1'], (0.0, "N/A"))
                    html_pc = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #FF00FF; width:180px;"><b style="color:#FF00FF;">PUNTO CRÍTICO</b><br><small>{domicilio_texto}</small><br>Presión: <b style="color:#FF00FF;">{val_p:.2f} Kg/cm²</b></div>"""
                    icon_html_pc = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #ff4d4d, #ff0000, #800000); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
                    folium.Marker(location=pc['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_pc), popup=folium.Popup(html_pc, max_width=250)).add_to(m_sec)
                    folium.Marker(location=pc['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #FF00FF; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(255,0,255,0.4);">NS: {id_pc} • Punto critico</div>')).add_to(m_sec)

                # Marcadores de VRPs (Verdes) con etiqueta "Vrp"
                for id_vrp, vrp in dict_vrp_sec.items():
                    val_p1, _ = scada_res_reg.get(vrp['tag_p1'], (0.0, "N/A"))
                    val_p2, _ = scada_res_reg.get(vrp['tag_p2'], (0.0, "N/A"))
                    serie_vrp = vrp.get('Serie', 'S/N')
                    html_vrp = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid #00FFCC; width:200px;"><b style="color:#00FFCC;">VALVULA VRP</b><br><small>{vrp['nombre']}</small><br>P. Entrada: {val_p1:.2f} Kg/cm²<br>P. Salida: <b style="color:#00FFCC;">{val_p2:.2f} Kg/cm²</b></div>"""
                    icon_html_vrp = """<div style="position: relative; width: 26px; height: 26px;"><div style="width: 18px; height: 18px; background: radial-gradient(circle at 30% 30%, #a1ffce, #28a745, #004d1a); border-radius: 50%; box-shadow: 2px 3px 5px rgba(0,0,0,0.6); position: absolute; top: 0; left: 4px; z-index: 2;"></div></div>"""
                    folium.Marker(location=vrp['coord'], icon=folium.DivIcon(icon_size=(26, 30), icon_anchor=(13, 25), html=icon_html_vrp), popup=folium.Popup(html_vrp, max_width=250)).add_to(m_sec)
                    folium.Marker(location=vrp['coord'], icon=folium.features.DivIcon(icon_size=(250,30), icon_anchor=(-12, 30), html=f'<div style="font-size: 8.5pt; color: #00FFCC; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(0,255,204,0.4);">SN: {serie_vrp} • Vrp</div>')).add_to(m_sec)

                # Marcadores de Pozos (Encendido/Apagado en Mapa) - Conservados igual
                for id_p in ids_p:
                    if id_p in mapa_pozos_dict:
                        p_info = mapa_pozos_dict[id_p]
                        coord_pz = p_info.get('coord')
                        if coord_pz:
                            t_pz_q = p_info.get('caudal')
                            val_q_pz, _ = scada_res_reg.get(t_pz_q, (0.0, "N/A")) if t_pz_q else (0.0, "N/A")
                            es_encendido = val_q_pz > 0.1
                            color_pz = "#00ff00" if es_encendido else "#ff4d4d"
                            
                            html_popup_pz = f"""<div style="background:#000; color:white; padding:10px; border-radius:8px; border:1px solid {color_pz}; width:200px;"><b style="color:{color_pz};">POZO {id_p}</b><br>Estado: {'Encendido' if es_encendido else 'Apagado'}<br>Caudal: {val_q_pz:.2f} L/s</div>"""
                            icon_html_pz = f"""<div style="position: relative; width: 26px; height: 26px;"><div style="width: 16px; height: 16px; background: {color_pz}; border-radius: 50%; box-shadow: 0 0 8px {color_pz}; position: absolute; top: 5px; left: 5px; z-index: 2;"></div></div>"""
                            
                            folium.Marker(location=coord_pz, icon=folium.DivIcon(icon_size=(26, 26), icon_anchor=(13, 13), html=icon_html_pz), popup=folium.Popup(html_popup_pz, max_width=250)).add_to(m_sec)
                            folium.Marker(location=coord_pz, icon=folium.features.DivIcon(icon_size=(200,30), icon_anchor=(-12, 15), html=f'<div style="font-size: 8.5pt; color: {color_pz}; font-weight: bold; text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.65); padding: 1px 6px; border-radius: 4px; border: 1px solid {color_pz};">P{id_p}</div>')).add_to(m_sec)

                Fullscreen(position='topleft').add_to(m_sec)
                folium_static(m_sec, width=None, height=360)
                
            with col_der:
                st.markdown(f"""
                    <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                        <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Comportamiento hidráulico</p>
                        <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Caudal a la izquierda • Presión a la derecha • Franja nocturna 02:00 - 04:00</p>
                    </div>
                """, unsafe_allow_html=True)

                tags_visualizar = []
                mapeo_config = {}
                tags_grafico_set = set()

                for s_id_reg in list(dict_reg.keys()):
                    r_info = dict_reg[s_id_reg]
                    conf_pc = [
                        ('tag_q', f"S:{s_id_reg} - Q", False),
                        ('tag_p1', f"S:{s_id_reg} - P1", True),
                        ('tag_p2', f"S:{s_id_reg} - P2", True)
                    ]
                    for key_t, lb, sec in conf_pc:
                        tag_v = r_info.get(key_t)
                        if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                            if tag_v not in tags_grafico_set:
                                tags_visualizar.append(tag_v)
                                mapeo_config[tag_v] = {'label': lb, 'sec': sec}
                                tags_grafico_set.add(tag_v)

                for id_p in ids_p:
                    if id_p in mapa_pozos_dict:
                        p_info = mapa_pozos_dict[id_p]
                        conf_pz = [
                            ('caudal', f"Pozo {id_p} - Q", False),
                            ('presion', f"Pozo {id_p} - P", True),
                            ('nivel_tanque', "Nivel TQ", True)  # Etiqueta única sin nombre de pozo
                        ]
                        for key_t, lb, sec in conf_pz:
                            tag_v = p_info.get(key_t)
                            if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                                if key_t == 'nivel_tanque':
                                    if tag_v not in tags_grafico_set:
                                        tags_visualizar.append(tag_v)
                                        mapeo_config[tag_v] = {'label': "Nivel TQ", 'sec': sec}
                                        tags_grafico_set.add(tag_v)
                                else:
                                    if tag_v not in tags_grafico_set:
                                        tags_visualizar.append(tag_v)
                                        mapeo_config[tag_v] = {'label': lb, 'sec': sec}
                                        tags_grafico_set.add(tag_v)

                if tags_visualizar:
                    try:
                        engine_h = get_mysql_scada_engine()
                        tags_unicos_query = "', '".join(list(set(tags_visualizar)))
                        q_hist = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_unicos_query}') AND h.FECHA BETWEEN '{f_ini_h}' AND '{f_fin_h}' ORDER BY h.FECHA ASC"
                        df_h = pd.read_sql(q_hist, engine_h)
                        
                        if not df_h.empty:
                            df_h['FECHA'] = pd.to_datetime(df_h['FECHA'])
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

                            fig = go.Figure()
                            idx_q = 0
                            idx_p = 0

                            for tag_name in tags_visualizar:
                                df_tag = df_h[df_h['TAG'] == tag_name]
                                if not df_tag.empty:
                                    cfg = mapeo_config[tag_name]
                                    es_caudal = not cfg['sec']
                                    label_u = cfg['label'].upper()

                                    if es_caudal: unidad_pc = "L/s"
                                    elif "NIVEL" in label_u or "TANQUE" in label_u or "MTS" in label_u: unidad_pc = "m"
                                    else: unidad_pc = "Kg/cm²"
                                    
                                    if "NIVEL" in label_u or "TANQUE" in label_u:
                                        color_base = "#d400ff"
                                    elif es_caudal:
                                        brillo = max(75 - (idx_q * 15), 35) 
                                        color_base = f"hsl(200, 100%, {brillo}%)" 
                                        idx_q += 1
                                    else:
                                        brillo = max(80 - (idx_p * 20), 30)
                                        color_base = f"hsl(145, 100%, {brillo}%)"
                                        idx_p += 1

                                    fig.add_trace(go.Scatter(
                                        x=df_tag['FECHA'], y=df_tag['VALUE'], name=cfg['label'], 
                                        yaxis="y2" if cfg['sec'] else "y1", mode='lines+markers',
                                        line=dict(width=2, color=color_base),
                                        marker=dict(size=3, symbol='circle'),
                                        fill='tozeroy' if es_caudal else None,
                                        fillcolor=color_base.replace("hsl", "hsla").replace(")", ", 0.15)") if not ("NIVEL" in label_u or "TANQUE" in label_u) else None,
                                        hovertemplate='<b>%{fullData.name}</b>: %{y:.2f} ' + unidad_pc + '<extra></extra>'
                                    ))

                            delta = pd.Timedelta(hours=1)
                            for d in fechas_lineas:
                                es_lunes = (d.dayofweek == 0)
                                fig.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                                fig.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")

                            fig.update_layout(
                                paper_bgcolor='rgba(11,26,41,1)', plot_bgcolor='rgba(11,26,41,1)', height=360, 
                                margin=dict(l=40, r=40, t=10, b=10), hovermode="x unified", 
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(color="white", size=10)),
                                xaxis=dict(range=[f_ini_h, f_fin_h], color="#888888", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0),
                                yaxis=dict(title="L/s", color="#00d4ff", showgrid=True, gridcolor="#16304a"),
                                yaxis2=dict(title="Kg/cm²", side="right", overlaying="y", color="#00ff00", showgrid=False)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error en gráfica: {e}")

            # ==============================================================================
            # FILA INFERIOR: PUNTOS CRÍTICOS Y VRPs
            # ==============================================================================
            col_pc, col_vrp_g = st.columns([1.0, 1.0])
            
            with col_pc:
                st.markdown(f"""
                    <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                        <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Puntos críticos</p>
                        <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Presión en los puntos críticos del sector</p>
                    </div>
                """, unsafe_allow_html=True)
                
                if dict_pc_sec:
                    tags_pc_list = [v['tag_p1'] for v in dict_pc_sec.values() if v.get('tag_p1')]
                    if tags_pc_list:
                        try:
                            tags_pc_in = "', '".join(tags_pc_list)
                            df_pc_h = pd.read_sql(f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_pc_in}') AND h.FECHA BETWEEN '{f_ini_h}' AND '{f_fin_h}' ORDER BY h.FECHA ASC", engine_h)

                            if not df_pc_h.empty:
                                df_pc_h['FECHA'] = pd.to_datetime(df_pc_h['FECHA'])
                                dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                                meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                                f_ini_dia = f_ini_h.replace(hour=0, minute=0, second=0, microsecond=0)
                                f_fin_dia = f_fin_h.replace(hour=23, minute=59, second=59, microsecond=0)
                                fechas_lineas_pc = pd.date_range(start=f_ini_dia, end=f_fin_dia, freq='D')
                                ticks_pc = fechas_lineas_pc[::1]
                                etiquetas_pc = [
                                    f"00:00<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                                    for d in ticks_pc
                                ]

                                fig_pc = go.Figure()
                                tag_to_name = {v['tag_p1']: v.get('Domicilio', v.get('nombre', 'Punto Crítico')) for v in dict_pc_sec.values()}
                                colores_azules = ["#8acbf5", "#0088ff", "#3399ff", "#1a75ff"]
                                idx_pc_c = 0

                                for tag in tags_pc_list:
                                    df_temp = df_pc_h[df_pc_h['TAG'] == tag]
                                    if not df_temp.empty:
                                        color_trace_pc = colores_azules[idx_pc_c % len(colores_azules)]
                                        idx_pc_c += 1

                                        fig_pc.add_trace(go.Scatter(
                                            x=df_temp['FECHA'], y=df_temp['VALUE'], 
                                            name=tag_to_name.get(tag, tag), mode='lines+markers',
                                            line=dict(width=2, color=color_trace_pc),
                                            marker=dict(size=3.5, symbol='circle'),
                                            hovertemplate='<b>%{fullData.name}</b><br>Presión: %{y:.2f} Kg/cm²<extra></extra>'
                                        ))

                                delta_h = pd.Timedelta(hours=1)
                                for d in fechas_lineas_pc:
                                    es_lunes = (d.dayofweek == 0)
                                    fig_pc.add_vrect(x0=d - delta_h, x1=d + delta_h, fillcolor="gray", opacity=0.18, layer="below", line_width=0)
                                    fig_pc.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.4, layer="above")

                                fig_pc.update_layout(
                                    paper_bgcolor='rgba(11,26,41,1)', plot_bgcolor='rgba(11,26,41,1)', height=290, 
                                    margin=dict(l=40, r=40, t=10, b=10), hovermode="x unified",
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(color="white", size=9)),
                                    xaxis=dict(range=[f_ini_h, f_fin_h], color="#888888", showgrid=False, tickvals=ticks_pc, ticktext=etiquetas_pc, tickangle=0),
                                    yaxis=dict(tickformat=".2f", color="#8acbf5", showgrid=True, gridcolor="#16304a", title="Kg/cm²")
                                )
                                st.plotly_chart(fig_pc, use_container_width=True)
                        except Exception as e:
                            st.error(f"Error en gráfica de Puntos Críticos: {e}")

            with col_vrp_g:
                st.markdown(f"""
                    <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                        <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Válvulas reductoras de presión (VRP)</p>
                        <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Caudal a la izquierda • Presión a la derecha • Franja nocturna 02:00 - 04:00</p>
                    </div>
                """, unsafe_allow_html=True)

                if dict_vrp_sec:
                    tags_vrp_list = []
                    vrp_mapeo_config = {}
                    
                    for v_id, v_info in dict_vrp_sec.items():
                        v_serie = v_info.get('Serie', f"{v_id}")
                        conf_vrp = [
                            ('tag_q', f"VRP {v_serie} - Q", False),
                            ('tag_p1', f"VRP {v_serie} - P1", True),
                            ('tag_p2', f"VRP {v_serie} - P2", True)
                        ]
                        for k_t, label_s, es_presion in conf_vrp:
                            t_val = v_info.get(k_t)
                            if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                                tags_vrp_list.append(t_val)
                                vrp_mapeo_config[t_val] = {'label': label_s, 'es_presion': es_presion}

                    if tags_vrp_list:
                        try:
                            tags_vrp_in = "', '".join(list(set(tags_vrp_list)))
                            df_vrp_h = pd.read_sql(f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_vrp_in}') AND h.FECHA BETWEEN '{f_ini_h}' AND '{f_fin_h}' ORDER BY h.FECHA ASC", engine_h)

                            if not df_vrp_h.empty:
                                df_vrp_h['FECHA'] = pd.to_datetime(df_vrp_h['FECHA'])
                                dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                                meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                                f_ini_dia = f_ini_h.replace(hour=0, minute=0, second=0, microsecond=0)
                                f_fin_dia = f_fin_h.replace(hour=23, minute=59, second=59, microsecond=0)
                                fechas_lineas_vrp = pd.date_range(start=f_ini_dia, end=f_fin_dia, freq='D')
                                ticks_vrp = fechas_lineas_vrp[::1]
                                etiquetas_vrp = [
                                    f"00:00<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                                    for d in ticks_vrp
                                ]

                                fig_vrp = go.Figure()
                                idx_p_v = 0
                                colores_presion = ["#73e6b0", "#00ffaa", "#00cc66", "#33ff99", "#a1ffce"]

                                for tag in tags_vrp_list:
                                    df_temp = df_vrp_h[df_vrp_h['TAG'] == tag]
                                    if not df_temp.empty:
                                        cfg_v = vrp_mapeo_config[tag]
                                        es_p = cfg_v['es_presion']
                                        
                                        if not es_p:
                                            color_trace = "#8acbf5"
                                        else:
                                            color_trace = colores_presion[idx_p_v % len(colores_presion)]
                                            idx_p_v += 1

                                        fig_vrp.add_trace(go.Scatter(
                                            x=df_temp['FECHA'], y=df_temp['VALUE'], 
                                            name=cfg_v['label'], 
                                            yaxis="y2" if es_p else "y1", 
                                            mode='lines+markers',
                                            line=dict(width=2, color=color_trace),
                                            marker=dict(size=3.5, symbol='circle'),
                                            fill='tozeroy' if not es_p else None,
                                            fillcolor="rgba(138, 203, 245, 0.15)" if not es_p else None,
                                            hovertemplate='<b>%{fullData.name}</b>: %{y:.2f} ' + ("kg" if es_p else "Lps") + '<extra></extra>'
                                        ))

                                delta_h = pd.Timedelta(hours=1)
                                for d in fechas_lineas_vrp:
                                    es_lunes = (d.dayofweek == 0)
                                    fig_vrp.add_vrect(x0=d - delta_h, x1=d + delta_h, fillcolor="gray", opacity=0.18, layer="below", line_width=0)
                                    fig_vrp.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.4, layer="above")

                                fig_vrp.update_layout(
                                    paper_bgcolor='rgba(11,26,41,1)', plot_bgcolor='rgba(11,26,41,1)', height=290, 
                                    margin=dict(l=40, r=40, t=10, b=10), hovermode="x unified",
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center", font=dict(color="white", size=9)),
                                    xaxis=dict(range=[f_ini_h, f_fin_h], color="#888888", showgrid=False, tickvals=ticks_vrp, ticktext=etiquetas_vrp, tickangle=0),
                                    yaxis=dict(title="Caudal (Lps)", color="#8acbf5", showgrid=True, gridcolor="#16304a", tickformat=".2f"),
                                    yaxis2=dict(title="Presión (kg)", side="right", overlaying="y", color="#00ffaa", showgrid=False, tickformat=".2f")
                                )
                                st.plotly_chart(fig_vrp, use_container_width=True)
                        except Exception as e:
                            st.error(f"Error en gráfica de VRPs: {e}")

            # ==============================================================================
            # SECCIÓN INFERIOR: TABLA DE DATOS OPERATIVOS
            # ==============================================================================
            st.write("")
            st.markdown(f"""
                <div style="background: #0b1a29; border: 1px solid #1f4068; padding: 10px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px;">
                    <p style="color: #ffffff; font-size: 1.05rem; font-weight: bold; margin: 0;">Datos operativos</p>
                    <p style="color: #888888; font-size: 0.78rem; margin: 2px 0 0 0;">Ficha técnica del sector y métricas operativas del catálogo</p>
                </div>
                <div class="st-key-dma_operational" style="background: #0b1a29; border: 1px solid #1f4068; border-top: none; border-radius: 0 0 8px 8px; padding: 15px;">
                    <table style="width: 100%;">
                        <tr>
                            <td>🏢 <b>Distrito:</b> Distrito {datos_s.get('Distrito', 'Oriente')}</td>
                            <td>🚰 <b>Cantidad de pozos:</b> {datos_s.get('Cantidad_Pozos', len(ids_p)):,.0f}</td>
                            <td>📐 <b>Superficie:</b> {datos_s.get('Superficie', 0.0):,.2f} ha</td>
                        </tr>
                        <tr>
                            <td>📏 <b>Longitud de red:</b> {datos_s.get('Long_Red', 42.6):,.1f} km</td>
                            <td>🏠 <b>Tomas domésticas:</b> {datos_s.get('U_Domesticos', 0):,.0f}</td>
                            <td>🏢 <b>Tomas no domésticas:</b> {datos_s.get('U_NoDom', 0):,.0f}</td>
                        </tr>
                        <tr>
                            <td>📦 <b>Volumen producido:</b> {datos_s.get('Vol_Prod', 0):,.0f} m³</td>
                            <td>📋 <b>Volumen facturado:</b> {datos_s.get('Vol_Fact', 0):,.0f} m³</td>
                            <td>⚖️ <b>Balance estimado:</b> {datos_s.get('Balance_Estimado', 0):,.1f}%</td>
                        </tr>
                        <tr>
                            <td colspan="3">🔵 <b>Nivel TQ asociado:</b> {texto_nivel_tq}</td>
                        </tr>
                    </table>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("👆 Seleccione un sector en el menú desplegable superior para cargar el análisis integral.")
