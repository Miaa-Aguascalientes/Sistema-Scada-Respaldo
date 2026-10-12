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

st.set_page_config(
    page_title="Sistema Scada", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="collapsed"
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
                id
