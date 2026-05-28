import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import psycopg2
import json
import urllib.parse
from datetime import datetime, timedelta
import plotly.graph_objects as go
import time
import pytz

# Configuración de página optimizada para móviles
st.set_page_config(
    page_title="Sistema Scada Móvil", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

import streamlit.components.v1 as components
components.html(
    """
    <script>
        // Usamos setInterval para asegurar que el script se aplique aunque Streamlit tarde en cargar
        var interval = setInterval(function() {
            var elements = window.parent.document.querySelectorAll('button[data-testid="stExpander"]');
            if (elements.length > 0) {
                elements.forEach(function(el) {
                    el.style.color = "#00d4ff";
                    el.style.fontWeight = "bold";
                });
                clearInterval(interval); // Detener el bucle una vez aplicado
            }
        }, 500);
    </script>
    """,
    height=0
)

# Autorrefresco automático cada 5 minutos (300 segundos)
if 'scada_refresh' not in st.session_state:
    st.session_state.scada_refresh = 0

# 0. SECCION ---------------------------------------- SISTEMA DE AUTENTICACIÓN HUD DEFINITIVO --------------------------------------------------------------------
if 'autenticado' not in st.session_state:
    query_params = st.query_params
    if query_params.get("access") == "granted":
        st.session_state.autenticado = True
        st.session_state.rol = query_params.get("role", "usuario")
    else:
        st.session_state.autenticado = False

if 'fase_carga' not in st.session_state:
    st.session_state.fase_carga = False

@st.cache_resource
def get_mysql_telemetria_engine():
    try:
        c = st.secrets["mysql_telemetria"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(
            f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}",
            pool_recycle=3600,
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        st.error(f"⚠️ ERROR CRÍTICO DE CONEXIÓN TELEMETRÍA: {e}")
        return None

@st.cache_resource
def get_mysql_scada_engine():
    try:
        c = st.secrets["mysql_scada"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(
            f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}",
            pool_recycle=3600,
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        st.error(f"⚠️ ERROR CRÍTICO DE CONEXIÓN SCADA: {e}")
        return None

@st.cache_resource
def get_postgres_engine():
    try: 
        # Simplemente crea y retorna el objeto de conexión
        conn = psycopg2.connect(**st.secrets["postgres"])
        return conn
    except Exception as e: 
        st.error(f"Error de conexión Postgres: {e}")
        return None

def verificar_credenciales(usuario_input, password_input):
    try:
        engine = get_mysql_telemetria_engine()
        if engine is None: return None
        query = f"SELECT password, tipo_usuario FROM usuarios WHERE usuario = '{usuario_input}'"
        df_user = pd.read_sql(query, engine)
        if not df_user.empty and str(password_input) == str(df_user['password'].iloc[0]):
            return df_user['tipo_usuario'].iloc[0]
        return None
    except Exception as e:
        st.error(f"Error al consultar usuario: {e}")
        return None

#1. SECCION -------------------------------------------------------ESTILO VISUAL HUD AJUSTADO PARA MÓVIL ----------------------------------------------------------------------------------
st.markdown("""
<style>
  
    .stApp { background-color: #050a10 !important; }
    .block-container { padding: 10px !important; max-width: 100% !important; }
    header, footer { visibility: hidden !important; }
    
    .visual-core { position: relative; width: 280px; height: 280px; margin: auto; }
    .ring { position: absolute; border-radius: 50%; border: 4px solid transparent; animation: spin var(--d) linear infinite; }
    .r1 { width: 100%; height: 100%; border-top: 6px solid #00d4ff; border-bottom: 6px solid #00d4ff; --d: 4s; }
    .r2 { width: 78%; height: 78%; top: 11%; left: 11%; border: 2px dashed #00d4ff; --d: 8s; animation-direction: reverse; }
    .center-logo { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
    .logo-miaa { width: 130px; filter: drop-shadow(0 0 10px #00d4ff); }
    
    .login-box { 
        background: rgba(0, 212, 255, 0.05); 
        border-left: 6px solid #00d4ff; 
        padding: 20px; 
        margin-top: 20px;
        width: 100%;
    }
    
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .stTextInput input { background-color: #0d1b2a !important; color: #00d4ff !important; border: 1px solid #1f4068 !important; }
    .stButton button, div[data-testid="stForm"] button { 
        background: #00d4ff !important; 
        color: #050a10 !important; 
        font-weight: bold !important; 
        width: 100%; 
        height: 45px; 
        border: none !important;
    }
    div[data-testid="stForm"] { border: none !important; padding: 0 !important; }
    
    /* Tarjetas de indicadores de sectores */
    .card-indicador {
        background: #0d1f2d;
        border: 1px solid #00d4ff;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 8px;
    }
    .label-indicador { color: #888; font-size: 11px; margin: 0; }
    .value-indicador { color: #00d4ff; font-size: 16px; font-weight: bold; margin: 0; }
    
    /* Cambiar el color de los labels de los selectbox */
    div[data-testid="stSelectbox"] label {
        color: #00d4ff !important;
        font-weight: bold !important;
    }

    /* Estilo exclusivo para el logo principal dentro de la App */
    .logo-header {
        width: 200px; /* Cambia este valor al tamaño que desees para el logo interno */
        height: auto;
        display: block;
        margin: 0 auto 20px auto; /* Centrado y con margen inferior */
    }

     /* Solo afecta a los elementos dentro de .kpi-pozo-container */
    .kpi-pozo-container [data-testid="column"] {
        width: calc(33.33% - 1rem) !important;
        flex: 1 1 calc(33.33% - 1rem) !important;
        min-width: 80px !important;
    }

    /* Esto afectará a TODOS los checkboxes, asegurando que se vean azules */
    div[data-testid="stCheckbox"] label p {
        font-size: 1.1rem !important; /* Prueba con 1.5rem o 20px */
        color: #00d4ff !important;
        font-weight: bold !important;
    } 

    /* 1. Seleccionamos el contenedor del Toggle */
    div[data-testid="stToggle"] {
        width: 100% !important;
        max-width: 100% !important;
        border: 2px solid white !important;
        border-radius: 10px !important;
        padding: 10px !important;
    }
    
    /* 2. Seleccionamos el texto del Toggle */
    div[data-testid="stToggle"] label p {
        color: #00d4ff !important;
        font-size: 1.5rem !important;
        font-weight: bold !important;
    }

    
</style>
""", unsafe_allow_html=True)



if not st.session_state.autenticado:
    col_vis, col_log = st.columns([1, 1])
    with col_vis:
        st.markdown('<div style="height: 5vh;"></div>', unsafe_allow_html=True)
        st.markdown('''
        <div class="visual-core">
            <div class="ring r1"></div><div class="ring r2"></div>
            <div class="center-logo">
                <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-miaa">
            </div>
        </div>
        ''', unsafe_allow_html=True)

    with col_log:
        if not st.session_state.fase_carga:
            st.markdown('<div class="login-box">', unsafe_allow_html=True)
            st.markdown('<h2 style="color:#00d4ff; font-size:16px;">// CREDENCIALES SCADA</h2>', unsafe_allow_html=True)
            with st.form("login_form"):
                u = st.text_input("USUARIO")
                p = st.text_input("PASSWORD", type="password")
                if st.form_submit_button("ACCEDER"):
                    rol = verificar_credenciales(u, p)
                    if rol:
                        st.session_state.temp_rol = rol
                        st.session_state.fase_carga = True
                        st.rerun()
                    else:
                        st.error("❌ ACCESO DENEGADO")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="login-box">', unsafe_allow_html=True)
            st.markdown('<h2 style="color:#00d4ff; font-size:16px;">// CONFIGURANDO ENTORNO MÓVIL...</h2>', unsafe_allow_html=True)
            st.session_state.autenticado = True
            st.session_state.rol = st.session_state.temp_rol
            st.session_state.fase_carga = False
            st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# 2. SECCION -----------------------------------------------   FUNCIONES DE EXTRACCIÓN DE DATOS SCADA & POSTGRES -----------------------------------------------------------
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
        return {row['NAME']: (row['VALUE'], row['FECHA'].strftime('%d/%m/%Y %H:%M') if row['FECHA'] else "N/A") for _, row in df.iterrows()}
    except:
        return {}

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

# 2. Función de sectores corregida
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

@st.cache_data(ttl=3600) 
def cargar_mapa_pozos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_pozos = pd.read_sql("SELECT * FROM Diccionario_de_pozos", engine)
        nuevo_mapa = {}
        for _, row in df_pozos.iterrows():
            nuevo_mapa[row['Pozos']] = {
                "bomba": row['bomba'], "caudal": row['caudal'], "presion": row['presion'],
                "sumergencia": row['sumergencia'], "nivel_dinamico": row['nivel_dinamico'],
                "nivel_tanque": row['nivel_tanque'], "columna": row['columna'],
                "h_arranque": row['H_arranque'], "h_paro": row['H_paro'],
                "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']],
                "totalizado": row['totalizado']
            }
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
            n_max = float(row['Nivel_max']) if row.get('Nivel_max') is not None else 1.0
            if n_max <= 0: n_max = 1.0
            nuevo_mapa_tq[row['Nombre_tq']] = {
                "nombre": row['Nombre_tq'], "tag_nivel": row['nivel_tanque'], "nivel_max": n_max, "sitios": row['Sitios']
            }
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
            nuevo_mapa_rb[row['Rebombeo']] = {
                "nombre": row['Nombre_rebombeo'], "telemetria": row['Telemetria'], "presion": row['presion'], "nivel_tanque": row['nivel_tanque'],
                "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']]
            }
        return nuevo_mapa_rb
    except: return {}

@st.cache_data(ttl=3600)
def cargar_puntos_de_control_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_de_control", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_reg_val = r.get('Serie', r.get('Registrador', 'ID'))
            d_res[str(id_reg_val)] = {
                "nombre": str(r.get('Domicilio', r.get('Nombre_registrador', 'S/N'))),
                "sector": str(r['Sector']).split('.')[0].strip(),
                "tag_p1": r.get('Presion_1'), "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'),
                "tag_vbat": r.get('bateria'), "tag_idx": r.get('indice'), "Serie": str(id_reg_val)
            }
        return d_res
    except: return {}

@st.cache_data(ttl=3600)
def cargar_puntos_criticos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_criticos", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_reg = r.get('Serie', r.get('Registrador', 'ID'))
            d_res[str(id_reg)] = {
                "nombre": str(r.get('Colonia', 'S/C')), "Domicilio": str(r.get('Domicilio', 'Sin Domicilio')),
                "sector": str(r['Sector']).split('.')[0].strip(), "tag_p1": r.get('Presion_1'), "tag_q": r.get('Caudal')
            }
        return d_res
    except: return {}

@st.cache_data(ttl=3600)
def cargar_vrp_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_vrp", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_val = r.get('Serie', 'ID_VRP')
            d_res[str(id_val)] = {
                "nombre": str(r.get('Domicilio', 'S/N')), "sector": str(r['Sector']).split('.')[0].strip(),
                "tag_p1": r.get('Presion_1'), "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'), "Serie": str(id_val)
            }
        return d_res
    except: return {}

# 3. SECCION --------------------------------------------------------- PROCESAMIENTO E INTERFAZ DE ACTIVOS -----------------------------------------------------------------------
sectores = cargar_sectores_poligonos()
mapa_pozos_dict = cargar_mapa_pozos_desde_db()
mapa_tanques_dict = cargar_tanques_desde_db()
mapa_rebombeos_dict = cargar_rebombeos_desde_db()

# Callbacks para mantener la exclusividad mutua de selección en pantalla móvil
def reset_pozo():
    if st.session_state.opt_pozo != "-- Seleccionar --":
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Pozo"
        st.session_state.activo_id = st.session_state.opt_pozo

def reset_tanque():
    if st.session_state.opt_tanque != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Tanque"
        st.session_state.activo_id = st.session_state.opt_tanque

def reset_rebombeo():
    if st.session_state.opt_rebombeo != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Rebombeo"
        st.session_state.activo_id = st.session_state.opt_rebombeo

def reset_sector():
    if st.session_state.opt_sector != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.activo_tipo = "Sector"
        st.session_state.activo_id = st.session_state.opt_sector

if 'activo_tipo' not in st.session_state:
    st.session_state.activo_tipo = None
    st.session_state.activo_id = None

# LOGOTIPO EN LA PARTE SUPERIOR DE LA APLICACIÓN
st.markdown('''
    <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-header">
''', unsafe_allow_html=True)

# PANEL DE CONTROL HUD SUPERIOR - SELECTORES MÓVILES
st.markdown('<h2 style="color:#00d4ff; font-size:18px; margin-bottom:12px;">🖥️ Panel Scada</h2>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.selectbox("💧 Pozos", ["-- Seleccionar --"] + sorted(list(mapa_pozos_dict.keys())), key="opt_pozo", on_change=reset_pozo)
    st.selectbox("🛢️  Tanques", ["-- Seleccionar --"] + sorted(list(mapa_tanques_dict.keys())), key="opt_tanque", on_change=reset_tanque)

with c2:
    st.selectbox("🧊 Rebombeos", ["-- Seleccionar --"] + sorted(list(mapa_rebombeos_dict.keys())), key="opt_rebombeo", on_change=reset_rebombeo)
    st.selectbox("🏘️ Sectores Hidráulicos", ["-- Seleccionar --"] + sorted([s['sector'] for s in sectores if s.get('sector')]), key="opt_sector", on_change=reset_sector)

st.divider()

# 4. SECCION ----------------------------------------- RENDERIZADO DE GRÁFICOS Y MÉTRICAS SEGÚN LA SELECCIÓN ACTIVA -------------------------------------------------------------
def renderizar_tarjeta_kpi(col, titulo, valor, unidad, color):
    col.markdown(f'''
        <div style="border: 2px solid {color}; padding: 8px; border-radius: 8px; text-align: center; margin-bottom: 10px; background: rgba(0,0,0,0.2);">
            <p style="color: #ccc; font-size: 9px; margin: 0; text-transform: uppercase; font-weight: bold;">{titulo}</p>
            <p style="color: {color}; font-size: 16px; font-weight: bold; margin: 0;">{valor} <span style="font-size: 10px; color: white;">{unidad}</span></p>
        </div>
    ''', unsafe_allow_html=True)

if st.session_state.activo_tipo == "Pozo" and st.session_state.activo_id != "-- Seleccionar --":
    id_pozo = st.session_state.activo_id
    info_p = mapa_pozos_dict.get(id_pozo)

    # 1. Definir zona horaria de México
    mexico_tz = pytz.timezone('America/Mexico_City')

    # 2. Obtener fechas de todos los voltajes disponibles
    tags_voltaje = [v for v in info_p.get('voltajes_l', []) if v and v != 'N/A']
    data_voltaje = cargar_datos_scada(tags_voltaje)
    
    fechas_lectura = []
    for tag in tags_voltaje:
        _, fecha_str = data_voltaje.get(tag, (0.0, None))
        if fecha_str and fecha_str != "N/A":
            try:
                dt = datetime.strptime(fecha_str, '%d/%m/%Y %H:%M')
                fechas_lectura.append(dt)
            except:
                continue
    
    # 3. Determinar estado de comunicación
    if fechas_lectura:
        ultima_fecha_db = max(fechas_lectura) # La fecha más reciente encontrada
        ahora = datetime.now(mexico_tz).replace(tzinfo=None) # Tiempo actual ajustado
        
        # Si la diferencia es mayor a 3 horas, es falla
        es_falla = (ahora - ultima_fecha_db) > timedelta(hours=3)
        fecha_ultima_valida = ultima_fecha_db.strftime('%d/%m/%Y %H:%M')
    else:
        es_falla = True
        fecha_ultima_valida = "Sin datos"

    # 4. Estado de la bomba (para cuando SI hay comunicación)
    data_bomba = cargar_datos_scada([info_p['bomba']])
    val_bomba, _ = data_bomba.get(info_p['bomba'], (0.0, "N/A"))

    # 5. Definición de colores y textos
    if es_falla:
        estado_texto = "FALLA DE COMUNICACIÓN"
        color_bomba = "#ffaa00"
        glow_bomba = "0 0 15px #ffaa00"
    else:
        estado_texto = "Bomba Encendida" if float(val_bomba) > 0 else "Bomba Apagada"
        color_bomba = "#00ff00" if float(val_bomba) > 0 else "#ff4b4b"
        glow_bomba = "0 0 15px #00ff00" if float(val_bomba) > 0 else "0 0 15px #ff4b4b"

    # Renderizado
    st.markdown(f"<h3 style='color:#00d4ff;'>↕️ Detalle de Pozo: {id_pozo}</h3>", unsafe_allow_html=True)
    st.markdown(f'''
        <div style="border: 2px solid {color_bomba}; padding: 8px; border-radius: 8px; text-align: center; margin-bottom: 20px; box-shadow: {glow_bomba};">
            <p style="color: white; font-size: 10px; margin: 0; text-transform: uppercase;">Estado del Pozo</p>
            <p style="color: {color_bomba}; font-size: 20px; font-weight: bold; margin: 0;">{estado_texto}</p>
            <p style="color: white; font-size: 12px; margin-top: 5px;">Última actualización: {fecha_ultima_valida}</p>
        </div>
    ''', unsafe_allow_html=True)

    opciones = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
    opcion_fecha = st.selectbox("Rango de tiempo:", opciones, index=2, key="sel_rango_pozo")
    
    hoy_dt = datetime.now()
    if opcion_fecha == "Hoy": f_ini = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Ayer": f_ini = hoy_dt - timedelta(days=1)
    elif opcion_fecha == "Últimos 7 días": f_ini = hoy_dt - timedelta(days=7)
    elif opcion_fecha == "Últimos 14 días": f_ini = hoy_dt - timedelta(days=14)
    elif opcion_fecha == "Este Mes": f_ini = hoy_dt.replace(day=1)
    elif opcion_fecha == "Último Mes": f_ini = (hoy_dt.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif opcion_fecha == "Últimos 6 meses": f_ini = hoy_dt - timedelta(days=180)
    else: 
        rango = st.date_input("Selecciona rango:", [hoy_dt - timedelta(days=7), hoy_dt], key="date_pozo")
        f_ini = rango[0] if len(rango) == 2 else hoy_dt - timedelta(days=7)

  
    tags_consulta = [info_p['caudal'], info_p['presion'], info_p['nivel_dinamico'], info_p['sumergencia'], info_p['nivel_tanque']]
    tags_consulta.extend([v for v in info_p['voltajes_l'] if v and v != 'N/A'])
    tags_consulta.extend([a for a in info_p['amperajes_l'] if a and a != 'N/A'])
    
    engine = get_mysql_scada_engine()
    tags_str = "','".join(list(set([t for t in tags_consulta if t])))
    q = f"SELECT r.NAME as TagName, h.VALUE FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA BETWEEN '{f_ini}' AND '{hoy_dt}'"
    df = pd.read_sql(q, engine)
    
    def get_avg(tag, df_loc):
        d = df_loc[df_loc['TagName'] == tag]['VALUE']
        return d.mean() if not d.empty else 0.0

    # 3. Renderizado de KPIs
    # Obtenemos el último nivel del tanque por separado como pediste
    data_tq = cargar_datos_scada([info_p['nivel_tanque']])
    val_nivel_tq = float(data_tq.get(info_p['nivel_tanque'], (0.0, ""))[0])
    
    if 'mostrar_ind' not in st.session_state:
        st.session_state.mostrar_ind = False
        
    st.session_state.mostrar_ind = st.toggle("Indicadores de Operación", value=st.session_state.mostrar_ind)
# Aquí inicia el botón desplegable para los indicadores
    if st.session_state.mostrar_ind:
        # Fila 1: 3 elementos principales
        f1 = st.columns(3)
        renderizar_tarjeta_kpi(f1[0], "Caudal Prom", f"{get_avg(info_p['caudal'], df):,.2f}", "Lps", "#00d4ff")
        renderizar_tarjeta_kpi(f1[1], "Presión Prom", f"{get_avg(info_p['presion'], df):,.2f}", "Kg/cm²", "#00ff00")
        renderizar_tarjeta_kpi(f1[2], "Nivel de tanque actual", f"{val_nivel_tq:,.2f}", "Mts", "#00ffcc")
        
        # Fila 2: Niveles de pozo
        f2 = st.columns(2)
        renderizar_tarjeta_kpi(f2[0], "Nivivel Dinamico Prom.", f"{get_avg(info_p['nivel_dinamico'], df):,.2f}", "Mts", "#ff00b4")
        renderizar_tarjeta_kpi(f2[1], "Sumergencia de la bomba Prom.", f"{get_avg(info_p['sumergencia'], df):,.2f}", "Mts", "#a800ff")
        
        # Fila 3: Eléctricos
        f3 = st.columns(2)
        v_tags = [v for v in info_p['voltajes_l'] if v and v != 'N/A']
        v_prom = sum([get_avg(v, df) for v in v_tags]) / len(v_tags) if v_tags else 0
        renderizar_tarjeta_kpi(f3[0], "Voltaje Prom", f"{v_prom:,.1f}", "Volt", "#fffb00")
        
        a_tags = [a for a in info_p['amperajes_l'] if a and a != 'N/A']
        a_prom = sum([get_avg(a, df) for a in a_tags]) / len(a_tags) if a_tags else 0
        renderizar_tarjeta_kpi(f3[1], "Amperaje Prom", f"{a_prom:,.1f}", "Amp", "#ff8000")
    

    # Configuración de Ejes y Colores (Orden Fijo)
    config_visual = [
        ('caudal', "Caudal (Lps)", 'y', '#00d4ff'), 
        ('nivel_tanque', "Nivel Tanque (m)", 'y5', '#00ffcc'),
        ('presion', "Presión (Kg/cm²)", 'y2', '#00ff00'),
        ('nivel_dinamico', "Nivel Dinámico (m)", 'y3', '#ff00b4'),
        ('sumergencia', "Sumergencia (m)", 'y3', '#a800ff')
    ]
    for i, t in enumerate(info_p.get('voltajes_l', [])):
        if t and t != 'N/A': config_visual.append((t, f"V L{i+1}", 'y4', '#fffb00'))
    for i, t in enumerate(info_p.get('amperajes_l', [])):
        if t and t != 'N/A': config_visual.append((t, f"Amp L{i+1}", 'y4', '#ff8000'))

    # Preparar Tags para consulta
    tags_grafico = []
    for item in config_visual:
        real_t = info_p.get(item[0], item[0])
        if real_t and real_t != 'N/A': 
            tags_grafico.append({'tag': real_t, 'label': item[1], 'axis': item[2], 'color': item[3]})
    
    engine = get_mysql_scada_engine()
    tags_str = "','".join(list(set([t['tag'] for t in tags_grafico])))
    q = f"SELECT r.NAME as TagName, h.VALUE, h.FECHA FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA BETWEEN '{f_ini}' AND '{hoy_dt}' ORDER BY h.FECHA ASC"
    df = pd.read_sql(q, engine)
    
# --- ESTRUCTURA DE GRUPOS ---
    grupos = [
        {"titulo": "Caudal y Presión", "icono": "💧", "tags": [('caudal', "Caudal (Lps)", '#00d4ff'), ('presion', "Presión (Kg/cm²)", '#00ff00')]},
        {"titulo": "Voltaje y Amperaje", "icono": "⚡", "tags": [(t, f"V L{i+1}", '#fffb00') for i, t in enumerate(info_p.get('voltajes_l', [])) if t != 'N/A'] + [(t, f"Amp L{i+1}", '#ff8000') for i, t in enumerate(info_p.get('amperajes_l', [])) if t != 'N/A']},
        {"titulo": "Nivel Tanque", "icono": "🛢️", "tags": [('nivel_tanque', "Tanque (m)", '#00ffcc')]},
        {"titulo": "Niveles de Pozo", "icono": "🌀", "tags": [('nivel_dinamico', "Dinámico (m)", '#ff00b4'), ('sumergencia', "Sumergencia (m)", '#a800ff')]}
    ]

    for grupo in grupos:
        tags_en_grupo = [t for t in grupo['tags'] if info_p.get(t[0], t[0]) in df['TagName'].values]
        if not tags_en_grupo: continue


        
        st.markdown(f'<h3 style="color: white;">{grupo["icono"]} {grupo["titulo"]}</h3>', unsafe_allow_html=True)
        fig = go.Figure()
        
        for key, label, color in tags_en_grupo:
            tag_name = info_p.get(key, key)
            dft = df[df['TagName'] == tag_name].sort_values('FECHA')
            
            fig.add_trace(go.Scatter(
                x=dft['FECHA'],
                y=dft['VALUE'],
                name=label, 
                mode='lines+markers',
                line=dict(color=color, width=2),
                marker=dict(size=4),
                hovertemplate=f"<span style='color:{color};'>■</span> <b>{label}</b>: %{{y:,.2f}}<extra></extra>"))
        
        fig.update_layout(
            template="plotly_dark", 
            height=300, 
            margin=dict(t=60, b=80, l=10, r=10),
            hovermode="x unified", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=True,
            # Configuración de ejes en blanco
            xaxis=dict(
                title_font=dict(color='white'), 
                tickfont=dict(color='white'), 
                linecolor='white',
                gridcolor='rgba(255,255,255,0.1)'
            ),
            yaxis=dict(
                title_font=dict(color='white'), 
                tickfont=dict(color='white'), 
                linecolor='white',
                gridcolor='rgba(255,255,255,0.1)'
            ),
            legend=dict(
                orientation="h", 
                y=1.2, 
                x=0.5, 
                xanchor="center",
                yanchor="top",
                font=dict(size=9, color='white') # También agregué color a la leyenda
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(
            """
            <hr style='border: 0.5px solid #00d4ff; margin-top: -30px; margin-bottom: 20px;'>
            """, 
            unsafe_allow_html=True
        )


# ------------------------------------------------------------------------------ seccion de tanques ------------------------------------------------------------------------

elif st.session_state.activo_tipo == "Tanque" and st.session_state.activo_id != "-- Seleccionar --":
    id_tq = st.session_state.activo_id
    info_t = mapa_tanques_dict.get(id_tq)
    
    st.markdown(f"<h3 style='color:#00d4ff;'>🛢️  Análisis de Nivel: {info_t['nombre']}</h3>", unsafe_allow_html=True)

    # --- OBTENER DATOS ---
    data_tq = cargar_datos_scada([info_t['tag_nivel']])
    ultimo_nivel, fecha_lectura = data_tq.get(info_t['tag_nivel'], (0.0, "N/A"))
    nivel_max = info_t.get('nivel_max', 0.0)
    
    # Renderizar el indicador visual incluyendo el límite máximo
    st.markdown(f'''
        <div style="border: 2px solid #00d4ff; padding: 10px; border-radius: 12px; text-align: center; margin-bottom: 20px; background: rgba(0, 212, 255, 0.05);">
            <p style="color: white; font-size: 12px; margin: 0; font-weight: bold;">Nivel de tanque actual</p>
            <p style="color: white; font-size: 32px; font-weight: bold; margin: 0;">{float(ultimo_nivel):,.2f} <span style="font-size: 18px; color: #00d4ff;">Mts</span></p>
            <p style="color: #cccccc; font-size: 11px; margin-top: 5px;">
                Nivel Máximo: <span style="color: #00d4ff; font-weight: bold;">{float(nivel_max):,.2f} Mts</span>
            </p>
            <p style="color: white; font-size: 10px; margin-top: 5px;">Última lectura: {fecha_lectura}</p>
        </div>
    ''', unsafe_allow_html=True)
    
# 1. Definición de opciones
    opciones = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
    opcion_fecha = st.selectbox("Selecciona rango:", opciones, index=2) # Index 0 para empezar en 'Hoy'
    
    hoy_dt = datetime.now()
    f_fin = hoy_dt
    
    # 2. Lógica extendida para calcular fechas
    if opcion_fecha == "Hoy":
        f_ini = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Ayer":
        f_ini = hoy_dt - timedelta(days=1)
    elif opcion_fecha == "Últimos 7 días":
        f_ini = hoy_dt - timedelta(days=7)
    elif opcion_fecha == "Últimos 14 días":
        f_ini = hoy_dt - timedelta(days=14)
    elif opcion_fecha == "Este Mes":
        f_ini = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Último Mes":
        # Primer día del mes actual menos un día nos da el mes anterior
        primer_dia_actual = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        f_ini = (primer_dia_actual - timedelta(days=1)).replace(day=1)
        f_fin = primer_dia_actual - timedelta(seconds=1)
    elif opcion_fecha == "Últimos 6 meses":
        f_ini = hoy_dt - timedelta(days=180)
    elif opcion_fecha == "Personalizado":
        rango = st.date_input("Selecciona rango:", [hoy_dt - timedelta(days=7), hoy_dt])
        if len(rango) == 2:
            f_ini, f_fin = rango[0], rango[1]
        else:
            f_ini = hoy_dt - timedelta(days=7)

    # 3. Consulta SQL ajustada con las nuevas variables
    try:
        engine = get_mysql_scada_engine()
        # Convertimos las fechas a string con formato explícito para evitar errores de interpretación
        f_ini_str = f_ini.strftime('%Y-%m-%d %H:%M:%S')
        f_fin_str = f_fin.strftime('%Y-%m-%d %H:%M:%S') if isinstance(f_fin, datetime) else f_fin.strftime('%Y-%m-%d %H:%M:%S')
        
        query = f"""
            SELECT h.FECHA, h.VALUE FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME = '{info_t['tag_nivel']}' 
            AND h.FECHA BETWEEN '{f_ini_str}' AND '{f_fin_str}'
            ORDER BY h.FECHA ASC
        """
        df_hist = pd.read_sql(query, engine)
        
        if not df_hist.empty:
            df_hist['FECHA'] = pd.to_datetime(df_hist['FECHA'])
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_hist['FECHA'],
                y=df_hist['VALUE'],
                name="Nivel Tq",
                mode='lines+markers', # Cambio realizado: líneas y puntos
                line=dict(color='#00ffcc', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 204, 0.1)',
                hovertemplate="<b>Nivel</b>: %{y:.2f} m<extra></extra>"
            ))
            
            fig.update_layout(
                template="plotly_dark",
                height=300,
                margin=dict(t=60, b=80, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                hovermode="x unified",
                showlegend=True,
                legend=dict(
                    orientation="h",
                    y=1.2,
                    x=0.5,
                    xanchor="center",
                    font=dict(size=10, color='white')
                ),    
                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', color='white'),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', color='white')
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Sin datos para este tanque en el periodo elegido.")
    except Exception as e:
        st.error(f"Error cargando tanque: {e}")

# ------------------------------------------------------------------------------ seccion de rebombeos ------------------------------------------------------------------------

elif st.session_state.activo_tipo == "Rebombeo" and st.session_state.activo_id != "-- Seleccionar --":
    id_rb = st.session_state.activo_id
    info_rb = mapa_rebombeos_dict.get(id_rb)
    
    st.markdown(f"<h3 style='color:#00d4ff;'>🧊  Estación de Rebombeo: {info_rb['nombre']}</h3>", unsafe_allow_html=True)
    
    # Consulta de estados inmediatos
    tags_rb = [info_rb.get('presion'), info_rb.get('nivel_tanque')]
    data_scada_rb = cargar_datos_scada([t for t in tags_rb if t])
    
    p_rb, _ = data_scada_rb.get(info_rb.get('presion'), (0.0, "N/A"))
    n_rb, _ = data_scada_rb.get(info_rb.get('nivel_tanque'), (0.0, "N/A"))
    
    rc1, rc2 = st.columns(2)
    rc1.metric("Presión Actual", f"{float(p_rb):.2f} Kg/cm²")
    rc2.metric("Nivel de Succión", f"{float(n_rb):.2f} m")
    
    # Gráfico histórico rápido de presión de Rebombeo
    st.markdown("<h4 style='color:#00d4ff; font-size:14px;'>Histórico de Presión (Últimos 7 días)</h4>", unsafe_allow_html=True)
    df_p_rb = obtener_historia_7_dias(info_rb.get('presion'))
    if not df_p_rb.empty:
        fig_rb = go.Figure(go.Scatter(x=df_p_rb['FECHA'], y=df_p_rb['VALUE'], mode='lines', line=dict(color='#00ff00', width=2)))
        fig_rb.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_rb, use_container_width=True)

# ------------------------------------------------------------------------------ seccion de sectores ------------------------------------------------------------------------

elif st.session_state.activo_tipo == "Sector" and st.session_state.activo_id != "-- Seleccionar --":
    sec_id = st.session_state.activo_id
    datos_s = next((s for s in sectores if s['sector'] == sec_id), None)
    
    if datos_s:
        st.markdown(f"<h3 style='color:#00d4ff;'>🏘️ Sector Hidráulico: {sec_id}</h3>", unsafe_allow_html=True)
        
        # Grid compacto de Tarjetas de Información Técnica del Sector (KPIs)
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Superficie</p><p class="value-indicador">{datos_s.get("Superficie",0):,.1f} ha</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Tomas Totales</p><p class="value-indicador">{datos_s.get("U_Tot",0):,.0f}</p></div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Longitud de Red</p><p class="value-indicador">{datos_s.get("Long_Red",0):,.1f} m</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Población</p><p class="value-indicador">{datos_s.get("Poblacion",0):,.0f} hab</p></div>', unsafe_allow_html=True)
        with sc3:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Consumo Mensual</p><p class="value-indicador">{datos_s.get("Cons_m3",0):,.1f} m³</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Eficiencia / Balance</p><p class="value-indicador">{datos_s.get("Balance_Estimado",0):,.1f}%</p></div>', unsafe_allow_html=True)
            
        # Gráficos Históricos del Sector
        st.markdown("<h4 style='color:#00d4ff;'>📈 Comportamiento de Presiones y Caudales</h4>", unsafe_allow_html=True)
        
        # Cargar Puntos de control asignados al sector
        dict_reg_all = cargar_puntos_de_control_desde_db()
        dict_reg = {k: v for k, v in dict_reg_all.items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        
        if dict_reg:
            tags_sector = []
            for r in dict_reg.values():
                if r.get('tag_p1'): tags_sector.append(r.get('tag_p1'))
                if r.get('tag_q'): tags_sector.append(r.get('tag_q'))
                
            if tags_sector:
                engine_h = get_mysql_scada_engine()
                tags_unicos = "', '".join(list(set(tags_sector)))
                q_sec = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_unicos}') AND h.FECHA >= DATE_SUB(NOW(), INTERVAL 3 DAY) ORDER BY h.FECHA ASC"
                df_sec = pd.read_sql(q_sec, engine_h)
                
                if not df_sec.empty:
                    df_sec['FECHA'] = pd.to_datetime(df_sec['FECHA'])
                    fig_sec = go.Figure()
                    
                    for r_id, r_info in dict_reg.items():
                        df_p1 = df_sec[df_sec['TAG'] == r_info.get('tag_p1')]
                        if not df_p1.empty:
                            fig_sec.add_trace(go.Scatter(x=df_p1['FECHA'], y=df_p1['VALUE'], name=f"{r_info['nombre']} - Presión", mode='lines'))
                            
                    fig_sec.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified")
                    st.plotly_chart(fig_sec, use_container_width=True)
                else:
                    st.info("Sin registros telemétricos en los últimos 3 días para este sector.")
        else:
            st.info("No hay registradores vinculados a este sector.")
else:
    # Vista Default (HUD de Bienvenida) cuando no hay ningún elemento activo seleccionado
    st.markdown("""
    <div style="text-align: center; margin-top: 40px; padding: 20px; background: rgba(0,212,255,0.02); border: 1px dashed #1f4068; border-radius: 10px;">
        <p style="color: #00d4ff; font-family: 'Orbitron', sans-serif; font-size: 14px; margin: 0;">
            Sistema visual Scada. Seleccione una opcion superior para generar el grafico.
        </p>
    </div>
    """, unsafe_allow_html=True)
