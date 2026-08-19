import json
import hashlib
import html
import os
import re
import secrets
import sqlite3
import struct
import time
import unicodedata
import zlib
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = Path("/var/data") if Path("/var/data").exists() else BASE_DIR
DATA_DIR = Path(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "parte_fuerza.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
STATIC_DIR = BASE_DIR / "static"
SOURCE_XLSX = BASE_DIR.parent / "personal del distrito.xlsx"
SOURCE_SEED = BASE_DIR / "personal_seed.json"
VIDEO_FONDO = Path(r"C:\Users\juanc\Documents\JUAN POLICIA\210797_WxilRM9i.mp4")
SESSIONS = {}
LOGIN_ATTEMPTS = {}
ADMIN_USER = "DetolPurificacion"
ADMIN_PASSWORD = "Distrito4**"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 600
LOGIN_BLOCK_SECONDS = 900
try:
    APP_TZ = ZoneInfo("America/Bogota")
except Exception:
    APP_TZ = timezone(timedelta(hours=-5))

CATEGORIAS = {
    "oficiales": "Oficiales",
    "nivel_ejecutivo": "Mandos del Nivel Ejecutivo",
    "patrulleros": "Patrulleros",
    "patrulleros_policia": "Patrulleros de Polic\u00eda",
    "auxiliares": "Auxiliares de Polic\u00eda",
}

CATEGORIA_ORDEN = [
    "oficiales",
    "nivel_ejecutivo",
    "patrulleros",
    "patrulleros_policia",
    "auxiliares",
]

TIPOS_NOVEDAD = [
    "Permiso",
    "Excusa m\u00e9dica",
    "Vacaciones",
    "Franquicia",
    "Incapacidad",
    "Comisi\u00f3n",
    "Curso",
    "Licencia",
    "Suspensi\u00f3n",
    "Otra novedad",
]

ORDEN_UNIDADES = [
    "DISTRITO CUATRO DE POLICIA PURIFICACION",
    "ESTACION DE POLICIA PURIFICACION",
    "ESTACION DE POLICIA PRADO",
    "PUESTO DE POLICIA HIDROPRADO",
    "ESTACION DE POLICIA DOLORES",
    "ESTACION DE POLICIA ALPUJARRA",
    "SUBESTACION DE POLICIA LA ARADA",
    "ESTACION DE POLICIA SALDANA",
    "ESTACION DE POLICIA COYAIMA",
    "ESTACION DE POLICIA NATAGAIMA",
    "PUESTO DE POLICIA VELU",
]

GRADO_CATEGORIA = {
    "MY": "oficiales",
    "CT": "oficiales",
    "ST": "oficiales",
    "IT": "nivel_ejecutivo",
    "IJ": "nivel_ejecutivo",
    "SI": "nivel_ejecutivo",
    "PT": "patrulleros",
    "PP": "patrulleros_policia",
    "AXP": "auxiliares",
}

GRADO_ORDEN = [
    "MY",
    "CT",
    "ST",
    "IT",
    "IJ",
    "SI",
    "PT",
    "PP",
    "AXP",
]


def texto_orden(value):
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip().upper()


def ordenar_unidades(unidades, solo_operativas=False):
    orden = {texto_orden(nombre): index for index, nombre in enumerate(ORDEN_UNIDADES)}
    if solo_operativas:
        unidades = [unidad for unidad in unidades if texto_orden(unidad["nombre"]) in orden]
    return sorted(unidades, key=lambda unidad: (orden.get(texto_orden(unidad["nombre"]), 999), texto_orden(unidad["nombre"])))


def ordenar_funcionarios(funcionarios, por_unidad=False):
    orden_unidades = {texto_orden(nombre): index for index, nombre in enumerate(ORDEN_UNIDADES)}
    orden_categorias = {categoria: index for index, categoria in enumerate(CATEGORIA_ORDEN)}
    orden_grados = {grado: index for index, grado in enumerate(GRADO_ORDEN)}

    def clave(funcionario):
        unidad = funcionario["unidad_nombre"] if "unidad_nombre" in funcionario.keys() else funcionario.get("unidad", "")
        unidad_key = orden_unidades.get(texto_orden(unidad), 999) if por_unidad else 0
        grado = texto_orden(funcionario["grado"])
        return (
            unidad_key,
            orden_categorias.get(funcionario["categoria"], 999),
            orden_grados.get(grado, 999),
            texto_orden(funcionario["apellidos"]),
            texto_orden(funcionario["nombres"]),
        )

    return sorted(funcionarios, key=clave)


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password, stored):
    stored = stored or ""
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, salt, digest = stored.split("$", 2)
        except ValueError:
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
        return secrets.compare_digest(check, digest)
    return secrets.compare_digest(password, stored)


def find_user_by_login(conn, login):
    login = (login or "").strip()
    if texto_orden(login) == texto_orden(ADMIN_USER):
        login = ADMIN_USER
    return conn.execute(
        "SELECT * FROM usuarios WHERE UPPER(email) = UPPER(?)",
        (login,),
    ).fetchone()


def record_security_event(ip, usuario, evento, detalle):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO security_events (fecha, ip, usuario, evento, detalle)
            VALUES (?, ?, ?, ?, ?)
            """,
            (datetime.now().isoformat(timespec="seconds"), ip[:80], (usuario or "")[:120], evento[:80], detalle[:500]),
        )


def record_login(user, ip, user_agent, device_name):
    unidad = get_unit_name(user.get("unidad_id")) if user.get("unidad_id") else "ADMINISTRADOR GENERAL"
    with db() as conn:
        conn.execute(
            """
            INSERT INTO login_logs (fecha, usuario, rol, unidad, ip, equipo_nombre, equipo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                (user.get("email") or "")[:120],
                (user.get("rol") or "")[:50],
                unidad[:160],
                ip[:80],
                (device_name or "No informado")[:160],
                (user_agent or "")[:500],
            ),
        )


def is_suspicious_path(path, query=""):
    value = f"{path}?{query}".lower()
    patterns = [
        "../",
        "..%2f",
        "%2e%2e",
        ".env",
        ".git",
        "wp-admin",
        "wp-login",
        "phpmyadmin",
        "<script",
        "%3cscript",
        "union%20select",
        "select%20",
        "/etc/passwd",
    ]
    return any(pattern in value for pattern in patterns)


def is_postgres_conn(conn):
    return isinstance(conn, PostgresConnection)


def translate_postgres_sql(sql):
    sql = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"INSERT INTO \1",
        sql,
        flags=re.IGNORECASE,
    )
    if re.match(r"\s*INSERT\s+INTO\s+\w+", sql, re.IGNORECASE) and "ON CONFLICT" not in sql.upper():
        if "INSERT INTO" in sql.upper() and "RETURNING" not in sql.upper():
            sql = sql.rstrip() + " ON CONFLICT DO NOTHING"
    return sql.replace("?", "%s")


class PostgresCursor:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class PostgresConnection:
    def __init__(self):
        if psycopg is None:
            raise RuntimeError("Falta instalar psycopg para conectar PostgreSQL.")
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.conn.__exit__(exc_type, exc, tb)

    def execute(self, sql, params=None):
        returning_last_id = bool(re.match(r"\s*INSERT\s+INTO\s+partes\b", sql, re.IGNORECASE)) and "RETURNING" not in sql.upper()
        pg_sql = translate_postgres_sql(sql)
        if returning_last_id:
            pg_sql = pg_sql.rstrip()
            if pg_sql.upper().endswith("ON CONFLICT DO NOTHING"):
                pg_sql = pg_sql[: -len("ON CONFLICT DO NOTHING")].rstrip()
            pg_sql += " RETURNING id"
        cursor = self.conn.execute(pg_sql, params or ())
        lastrowid = None
        if returning_last_id:
            row = cursor.fetchone()
            lastrowid = row["id"] if row else None
        return PostgresCursor(cursor, lastrowid)

    def executemany(self, sql, seq_of_params):
        pg_sql = translate_postgres_sql(sql)
        with self.conn.cursor() as cursor:
            cursor.executemany(pg_sql, seq_of_params)

    def executescript(self, script):
        for statement in [part.strip() for part in script.split(";") if part.strip()]:
            self.execute(statement)


def db():
    if USE_POSTGRES:
        return PostgresConnection()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        schema = """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                password_plano TEXT,
                rol TEXT NOT NULL DEFAULT 'unidad',
                unidad_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS unidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                estado TEXT NOT NULL DEFAULT 'activa'
            );

            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cedula TEXT UNIQUE,
                grado TEXT NOT NULL,
                nombres TEXT NOT NULL,
                apellidos TEXT NOT NULL,
                categoria TEXT NOT NULL,
                unidad_id INTEGER NOT NULL,
                cargo TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            );

            CREATE TABLE IF NOT EXISTS partes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unidad_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora_parte TEXT NOT NULL,
                turno TEXT,
                comandante TEXT NOT NULL,
                fuerza_efectiva_oficiales INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_nivel_ejecutivo INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_patrulleros INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_patrulleros_policia INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_auxiliares INTEGER NOT NULL DEFAULT 0,
                observaciones TEXT,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS novedades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parte_id INTEGER NOT NULL,
                funcionario_id INTEGER NOT NULL,
                tipo_novedad TEXT NOT NULL,
                fecha_inicio TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                hora_fin TEXT NOT NULL,
                dias_calculados REAL NOT NULL,
                observaciones TEXT,
                estado TEXT NOT NULL DEFAULT 'activa'
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                ip TEXT NOT NULL,
                usuario TEXT,
                evento TEXT NOT NULL,
                detalle TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario TEXT NOT NULL,
                rol TEXT NOT NULL,
                unidad TEXT,
                ip TEXT NOT NULL,
                equipo_nombre TEXT,
                equipo TEXT NOT NULL
            );
            """
        if USE_POSTGRES:
            schema = """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                password_plano TEXT,
                rol TEXT NOT NULL DEFAULT 'unidad',
                unidad_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS unidades (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                estado TEXT NOT NULL DEFAULT 'activa'
            );

            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                cedula TEXT UNIQUE,
                grado TEXT NOT NULL,
                nombres TEXT NOT NULL,
                apellidos TEXT NOT NULL,
                categoria TEXT NOT NULL,
                unidad_id INTEGER NOT NULL,
                cargo TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            );

            CREATE TABLE IF NOT EXISTS partes (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                unidad_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora_parte TEXT NOT NULL,
                turno TEXT,
                comandante TEXT NOT NULL,
                fuerza_efectiva_oficiales INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_nivel_ejecutivo INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_patrulleros INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_patrulleros_policia INTEGER NOT NULL DEFAULT 0,
                fuerza_efectiva_auxiliares INTEGER NOT NULL DEFAULT 0,
                observaciones TEXT,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS novedades (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                parte_id INTEGER NOT NULL,
                funcionario_id INTEGER NOT NULL,
                tipo_novedad TEXT NOT NULL,
                fecha_inicio TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                hora_fin TEXT NOT NULL,
                dias_calculados REAL NOT NULL,
                observaciones TEXT,
                solicitud_psi TEXT,
                estado TEXT NOT NULL DEFAULT 'activa'
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                fecha TEXT NOT NULL,
                ip TEXT NOT NULL,
                usuario TEXT,
                evento TEXT NOT NULL,
                detalle TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                fecha TEXT NOT NULL,
                usuario TEXT NOT NULL,
                rol TEXT NOT NULL,
                unidad TEXT,
                ip TEXT NOT NULL,
                equipo_nombre TEXT,
                equipo TEXT NOT NULL
            );
            """
        conn.executescript(schema)

        ensure_column(conn, "usuarios", "rol", "TEXT NOT NULL DEFAULT 'unidad'")
        ensure_column(conn, "usuarios", "unidad_id", "INTEGER")
        ensure_column(conn, "usuarios", "password_plano", "TEXT")
        ensure_column(conn, "funcionarios", "cedula", "TEXT")
        ensure_column(conn, "funcionarios", "cargo", "TEXT")
        ensure_column(conn, "novedades", "solicitud_psi", "TEXT")
        ensure_column(conn, "login_logs", "equipo_nombre", "TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unidades_nombre ON unidades(nombre)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_funcionarios_cedula ON funcionarios(cedula)")

        if USE_POSTGRES:
            conn.execute(
                """
                INSERT INTO usuarios (nombre, email, password, password_plano, rol, unidad_id)
                VALUES ('Administrador', ?, ?, ?, 'admin', NULL)
                ON CONFLICT (email) DO UPDATE SET
                    nombre = excluded.nombre,
                    password = excluded.password,
                    password_plano = excluded.password_plano,
                    rol = 'admin',
                    unidad_id = NULL
                """,
                (ADMIN_USER, hash_password(ADMIN_PASSWORD), ADMIN_PASSWORD),
            )
            conn.execute(
                "INSERT INTO unidades (nombre, estado) VALUES ('DISTRITO CUATRO DE POLICIA PURIFICACION', 'activa') ON CONFLICT (nombre) DO NOTHING"
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO usuarios (id, nombre, email, password, password_plano, rol, unidad_id) VALUES (1, 'Administrador', ?, ?, ?, 'admin', NULL)",
                (ADMIN_USER, hash_password(ADMIN_PASSWORD), ADMIN_PASSWORD),
            )
            conn.execute(
                "UPDATE usuarios SET nombre = 'Administrador', email = ?, password = ?, password_plano = ?, rol = 'admin', unidad_id = NULL WHERE id = 1",
                (ADMIN_USER, hash_password(ADMIN_PASSWORD), ADMIN_PASSWORD),
            )
            conn.execute(
                "INSERT OR IGNORE INTO unidades (id, nombre, estado) VALUES (1, 'DISTRITO CUATRO DE POLICIA PURIFICACION', 'activa')"
            )

        import_excel_personal(conn)
        normalizar_unidad_distrito(conn)

        if conn.execute("SELECT COUNT(*) total FROM funcionarios").fetchone()["total"] == 0:
            funcionarios = [
                ("Subintendente", "Juan", "P&eacute;rez", "nivel_ejecutivo", 1),
                ("Intendente", "Mar&iacute;a Fernanda", "G&oacute;mez", "nivel_ejecutivo", 1),
                ("Patrullero", "Carlos", "Rodr&iacute;guez", "patrulleros", 1),
                ("Patrullero", "Andr&eacute;s Felipe", "Morales", "patrulleros", 1),
                ("Patrullero", "Laura Natalia", "Su&aacute;rez", "patrulleros", 1),
                ("Patrullera de Polic&iacute;a", "Diana Carolina", "Rojas", "patrulleros_policia", 1),
                ("Patrullero de Polic&iacute;a", "Miguel &Aacute;ngel", "Torres", "patrulleros_policia", 1),
                ("Auxiliar de Polic&iacute;a", "Santiago", "L&oacute;pez", "auxiliares", 1),
            ]
            conn.executemany(
                "INSERT INTO funcionarios (grado, nombres, apellidos, categoria, unidad_id) VALUES (?, ?, ?, ?, ?)",
                funcionarios,
            )


def ensure_column(conn, table, column, definition):
    if is_postgres_conn(conn):
        columns = [
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                (table,),
            )
        ]
    else:
        columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_dict(row):
    return dict(row) if row else None


def rows_dict(rows):
    return [dict(row) for row in rows]


def h(value):
    return html.escape(str(value or ""))


def tipo_novedad_text(novedad):
    tipo = novedad.get("tipo_novedad", "")
    detalle = str(novedad.get("observaciones") or "").strip()
    if tipo == "Otra novedad" and detalle:
        return f"{tipo}: {detalle}"
    return tipo


def get_unit_name(unidad_id):
    if not unidad_id:
        return ""
    with db() as conn:
        row = conn.execute("SELECT nombre FROM unidades WHERE id = ?", (unidad_id,)).fetchone()
    return row["nombre"] if row else ""


def visible_unit_clause(user, alias=""):
    prefix = f"{alias}." if alias else ""
    if user and user.get("rol") == "unidad":
        return f" AND {prefix}unidad_id = ? ", [user.get("unidad_id")]
    return "", []


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def excel_column(cell_ref):
    return re.sub(r"\d+", "", cell_ref)


def column_number(col):
    number = 0
    for char in col:
        number = number * 26 + (ord(char.upper()) - 64)
    return number - 1


def read_xlsx_rows(path):
    if not path.exists():
        return []

    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//a:t", ns)))

        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            values = {}
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "")
                index = column_number(excel_column(ref))
                value_node = cell.find("a:v", ns)
                inline_node = cell.find("a:is/a:t", ns)
                value = ""
                if inline_node is not None:
                    value = inline_node.text or ""
                elif value_node is not None:
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s" and value.isdigit():
                        value = shared[int(value)]
                values[index] = clean_text(value)
            if values:
                max_index = max(values)
                rows.append([values.get(i, "") for i in range(max_index + 1)])

    if not rows:
        return []

    headers = [clean_text(header).upper() for header in rows[0]]
    result = []
    for row in rows[1:]:
        item = {}
        for index, header in enumerate(headers):
            if header:
                item[header] = clean_text(row[index] if index < len(row) else "")
        if any(item.values()):
            result.append(item)
    return result


def unit_credentials(unit_name):
    normalized = unicodedata.normalize("NFKD", unit_name.upper()).encode("ascii", "ignore").decode("ascii")
    words = [word for word in re.sub(r"[^A-Z0-9 ]", " ", normalized).split() if word not in {"DE", "DEL", "LA", "EL", "LOS", "LAS", "POLICIA", "CUATRO"}]
    if not words:
        words = ["UNIDAD"]
    prefix = words[0]
    place = words[-1]
    username = f"{prefix}{place}"
    password = f"{place}2026"
    return username, password


def import_excel_personal(conn):
    rows = read_xlsx_rows(SOURCE_XLSX)
    if not rows and SOURCE_SEED.exists():
        rows = json.loads(SOURCE_SEED.read_text(encoding="utf-8"))
    if not rows:
        return

    unidades = sorted({row.get("UNIDAD", "") for row in rows if row.get("UNIDAD", "")})
    for unidad in unidades:
        conn.execute("INSERT OR IGNORE INTO unidades (nombre, estado) VALUES (?, 'activa')", (unidad,))

    unidad_ids = {
        row["nombre"]: row["id"]
        for row in conn.execute("SELECT id, nombre FROM unidades")
    }

    for row in rows:
        unidad = row.get("UNIDAD", "")
        grado = row.get("GRADO", "")
        nombres = row.get("NOMBRES", "")
        apellidos = row.get("APELLIDOS", "")
        cedula = row.get("CEDULA", "")
        if not unidad or not grado or not nombres or not apellidos:
            continue
        if not cedula:
            cedula = texto_orden(f"{unidad}-{grado}-{nombres}-{apellidos}")
        categoria = GRADO_CATEGORIA.get(grado.upper(), "patrulleros")
        conn.execute(
            """
            INSERT OR IGNORE INTO funcionarios
                (cedula, grado, nombres, apellidos, categoria, unidad_id, cargo, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')
            """,
            (cedula, grado, nombres, apellidos, categoria, unidad_ids[unidad], row.get("CARGO", "")),
        )

    for unidad in unidades:
        username, password = unit_credentials(unidad)
        conn.execute(
            """
            INSERT OR IGNORE INTO usuarios (nombre, email, password, password_plano, rol, unidad_id)
            VALUES (?, ?, ?, ?, 'unidad', ?)
            """,
            (unidad, username, hash_password(password), password, unidad_ids[unidad]),
        )
        conn.execute(
            """
            UPDATE usuarios
            SET password_plano = ?
            WHERE email = ? AND (password_plano IS NULL OR password_plano = '')
            """,
            (password, username),
        )


def normalizar_unidad_distrito(conn):
    correcta = "DISTRITO CUATRO DE POLICIA PURIFICACION"
    malas = [
        "Distrito Cuatro de Polic&iacute;a Purificación",
        "Distrito Cuatro de Policía Purificación",
    ]
    conn.execute("INSERT OR IGNORE INTO unidades (nombre, estado) VALUES (?, 'activa')", (correcta,))
    correcta_id = conn.execute("SELECT id FROM unidades WHERE nombre = ?", (correcta,)).fetchone()["id"]
    for mala in malas:
        row = conn.execute("SELECT id FROM unidades WHERE nombre = ?", (mala,)).fetchone()
        if not row or int(row["id"]) == int(correcta_id):
            continue
        mala_id = row["id"]
        conn.execute("UPDATE partes SET unidad_id = ? WHERE unidad_id = ?", (correcta_id, mala_id))
        conn.execute("UPDATE funcionarios SET unidad_id = ? WHERE unidad_id = ?", (correcta_id, mala_id))
        conn.execute("UPDATE usuarios SET unidad_id = ? WHERE unidad_id = ?", (correcta_id, mala_id))
        conn.execute("DELETE FROM unidades WHERE id = ?", (mala_id,))


def parse_dt(fecha, hora):
    return datetime.fromisoformat(f"{fecha}T{hora}")


def calcular_dias(fecha_inicio, hora_inicio, fecha_fin, hora_fin):
    inicio = parse_dt(fecha_inicio, hora_inicio)
    fin = parse_dt(fecha_fin, hora_fin)
    if fin <= inicio:
        raise ValueError("La fecha final debe ser posterior a la fecha inicial.")
    return round((fin - inicio).total_seconds() / 86400, 2)


def parte_efectiva(data):
    return {
        "oficiales": int(data.get("fuerza_efectiva_oficiales") or 0),
        "nivel_ejecutivo": int(data.get("fuerza_efectiva_nivel_ejecutivo") or 0),
        "patrulleros": int(data.get("fuerza_efectiva_patrulleros") or 0),
        "patrulleros_policia": int(data.get("fuerza_efectiva_patrulleros_policia") or 0),
        "auxiliares": int(data.get("fuerza_efectiva_auxiliares") or 0),
    }


def fuerza_efectiva_por_unidad(unidad_id):
    conteo = {key: 0 for key in CATEGORIAS}
    if not unidad_id:
        return conteo
    with db() as conn:
        rows = rows_dict(
            conn.execute(
                """
                SELECT categoria, COUNT(*) cantidad
                FROM funcionarios
                WHERE unidad_id = ? AND estado = 'activo'
                GROUP BY categoria
                """,
                (unidad_id,),
            )
        )
    for row in rows:
        if row["categoria"] in conteo:
            conteo[row["categoria"]] = int(row["cantidad"] or 0)
    return conteo


def aplicar_fuerza_efectiva_unidad(data):
    efectiva = fuerza_efectiva_por_unidad(data.get("unidad_id"))
    data["fuerza_efectiva_oficiales"] = efectiva["oficiales"]
    data["fuerza_efectiva_nivel_ejecutivo"] = efectiva["nivel_ejecutivo"]
    data["fuerza_efectiva_patrulleros"] = efectiva["patrulleros"]
    data["fuerza_efectiva_patrulleros_policia"] = efectiva["patrulleros_policia"]
    data["fuerza_efectiva_auxiliares"] = efectiva["auxiliares"]
    return data


def fecha_hora_actual():
    now = datetime.now(APP_TZ)
    return now.date().isoformat(), now.strftime("%H:%M")


def aplicar_fecha_hora_actual(data):
    fecha, hora = fecha_hora_actual()
    data["fecha"] = fecha
    data["hora_parte"] = hora
    return data


def novedades_vigentes(fecha, hora, unidad_id):
    if not fecha or not hora or not unidad_id:
        return []
    target = f"{fecha}T{hora}"
    with db() as conn:
        rows = rows_dict(
            conn.execute(
                """
                SELECT
                    n.id,
                    n.funcionario_id,
                    n.tipo_novedad,
                    n.fecha_inicio,
                    n.hora_inicio,
                    n.fecha_fin,
                    n.hora_fin,
                    n.dias_calculados,
                    n.observaciones,
                    n.solicitud_psi,
                    f.grado,
                    f.nombres,
                    f.apellidos,
                    f.categoria,
                    f.unidad_id,
                    uf.nombre unidad_nombre,
                    up.nombre unidad_reporta,
                    p.comandante
                FROM novedades n
                JOIN partes p ON p.id = n.parte_id
                JOIN funcionarios f ON f.id = n.funcionario_id
                JOIN unidades uf ON uf.id = f.unidad_id
                JOIN unidades up ON up.id = p.unidad_id
                WHERE n.estado = 'activa'
                  AND f.estado = 'activo'
                  AND f.unidad_id = ?
                  AND (n.fecha_inicio || 'T' || n.hora_inicio) <= ?
                  AND (n.fecha_fin || 'T' || n.hora_fin) >= ?
                ORDER BY n.id DESC
                """,
                (unidad_id, target, target),
            )
        )
    seen = set()
    vigentes = []
    for row in rows:
        funcionario_id = int(row["funcionario_id"])
        if funcionario_id in seen:
            continue
        seen.add(funcionario_id)
        vigentes.append(
            {
                "origen_novedad_id": row["id"],
                "automatica": True,
                "unidad_id": str(row["unidad_id"]),
                "unidad_nombre": row["unidad_nombre"],
                "unidad_reporta": row["unidad_reporta"],
                "comandante_origen": row["comandante"],
                "tipo_novedad": row["tipo_novedad"],
                "funcionario_id": str(row["funcionario_id"]),
                "funcionario": f"{row['nombres']} {row['apellidos']}",
                "grado": row["grado"],
                "categoria": row["categoria"],
                "categoria_nombre": CATEGORIAS.get(row["categoria"], row["categoria"]),
                "fecha_inicio": row["fecha_inicio"],
                "hora_inicio": row["hora_inicio"],
                "fecha_fin": row["fecha_fin"],
                "hora_fin": row["hora_fin"],
                "dias_calculados": float(row["dias_calculados"] or 0),
                "observaciones": row.get("observaciones") or "",
                "solicitud_psi": row.get("solicitud_psi") or "",
            }
        )
    return vigentes


def validar_novedades(data, novedades):
    if not data.get("unidad_id"):
        raise ValueError("Debe seleccionar la unidad que reporta el parte.")
    if not data.get("fecha") or not data.get("hora_parte"):
        raise ValueError("Debe seleccionar fecha y hora del parte.")
    if not data.get("comandante"):
        raise ValueError("Debe ingresar el comandante que reporta.")

    efectiva = parte_efectiva(data)
    ocupacion = {key: 0 for key in CATEGORIAS}
    rangos = {}

    with db() as conn:
        for novedad in novedades:
            required = ["tipo_novedad", "funcionario_id", "fecha_inicio", "hora_inicio", "fecha_fin", "hora_fin"]
            if any(not novedad.get(field) for field in required):
                raise ValueError("Todas las novedades deben tener tipo, funcionario, inicio y finalizaci&oacute;n.")
            if novedad["tipo_novedad"] not in TIPOS_NOVEDAD:
                raise ValueError("Tipo de novedad no v&aacute;lido.")
            if novedad["tipo_novedad"] in ("Permiso", "Franquicia") and not novedad.get("solicitud_psi"):
                raise ValueError("Debe indicar si la solicitud de permiso es por PSI (Sí o No).")
            if novedad["tipo_novedad"] == "Otra novedad" and not str(novedad.get("observaciones") or "").strip():
                raise ValueError("Debe escribir qu&eacute; novedad tiene el funcionario.")
            if novedad.get("solicitud_psi") and novedad["solicitud_psi"] not in ("Si", "No"):
                raise ValueError("La solicitud por PSI debe ser Sí o No.")

            funcionario = conn.execute(
                "SELECT * FROM funcionarios WHERE id = ? AND estado = 'activo'",
                (novedad["funcionario_id"],),
            ).fetchone()
            if not funcionario:
                raise ValueError("Funcionario no v&aacute;lido.")

            inicio = parse_dt(novedad["fecha_inicio"], novedad["hora_inicio"])
            fin = parse_dt(novedad["fecha_fin"], novedad["hora_fin"])
            if fin <= inicio:
                raise ValueError("La fecha final debe ser posterior a la fecha inicial.")

            funcionario_id = int(novedad["funcionario_id"])
            for ini, end in rangos.get(funcionario_id, []):
                if inicio < end and fin > ini:
                    raise ValueError("Ya existe una novedad simult&aacute;nea para este funcionario.")
            rangos.setdefault(funcionario_id, []).append((inicio, fin))

            categoria = funcionario["categoria"]
            ocupacion[categoria] += 1
            if ocupacion[categoria] > efectiva[categoria]:
                raise ValueError(
                    f"No es posible registrar esta novedad. La unidad solamente cuenta con "
                    f"{efectiva[categoria]} funcionarios de {CATEGORIAS[categoria]}."
                )


def page_shell(title, body):
    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="stylesheet" href="/static/app.css">
</head>
<body>
{body}
</body>
</html>"""


def reporte_data(parte_id):
    with db() as conn:
        parte = row_dict(
            conn.execute(
                """
                SELECT p.*, u.nombre unidad
                FROM partes p
                JOIN unidades u ON u.id = p.unidad_id
                WHERE p.id = ?
                """,
                (parte_id,),
            ).fetchone()
        )
        if not parte:
            return None
        novedades = rows_dict(
            conn.execute(
                """
                SELECT n.*, f.grado, f.nombres, f.apellidos, f.categoria, f.cargo, u.nombre unidad_funcionario
                FROM novedades n
                JOIN funcionarios f ON f.id = n.funcionario_id
                JOIN unidades u ON u.id = f.unidad_id
                WHERE n.parte_id = ?
                ORDER BY n.fecha_inicio, n.hora_inicio
                """,
                (parte_id,),
            )
        )
    efectiva = parte_efectiva(parte)
    en_novedad = {key: 0 for key in CATEGORIAS}
    for novedad in novedades:
        en_novedad[novedad["categoria"]] = en_novedad.get(novedad["categoria"], 0) + 1
    disponible = {key: max(0, efectiva[key] - en_novedad[key]) for key in CATEGORIAS}
    return {"parte": parte, "novedades": novedades, "efectiva": efectiva, "en_novedad": en_novedad, "disponible": disponible}


def reportes_filtrados(query, user=None):
    user = user or {}
    params = parse_qs(query)
    fecha = params.get("fecha", [""])[0]
    unidad_id = params.get("unidad_id", [""])[0]
    where = []
    values = []
    if user.get("rol") == "unidad":
        where.append("unidad_id = ?")
        values.append(user.get("unidad_id"))
    elif unidad_id:
        where.append("unidad_id = ?")
        values.append(unidad_id)
    if fecha:
        where.append("fecha = ?")
        values.append(fecha)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        ids = [row["id"] for row in conn.execute(f"SELECT id FROM partes {where_sql} ORDER BY fecha DESC, id DESC", values)]
    return [reporte_data(parte_id) for parte_id in ids if reporte_data(parte_id)]


def reporte_general_data(fecha):
    with db() as conn:
        partes = rows_dict(
            conn.execute(
                """
                SELECT p.id
                FROM partes p
                WHERE p.fecha = ?
                ORDER BY p.fecha DESC, p.id DESC
                """,
                (fecha,),
            )
        )
    reportes = [reporte_data(parte["id"]) for parte in partes]
    reportes = [reporte for reporte in reportes if reporte]
    efectiva = {key: 0 for key in CATEGORIAS}
    en_novedad = {key: 0 for key in CATEGORIAS}
    disponible = {key: 0 for key in CATEGORIAS}
    novedades = []
    unidades = []
    for reporte in reportes:
        parte = reporte["parte"]
        total_efectiva = sum(reporte["efectiva"].values())
        total_novedades = sum(reporte["en_novedad"].values())
        total_disponible = sum(reporte["disponible"].values())
        unidades.append(
            {
                "fecha": parte["fecha"],
                "hora": parte["hora_parte"],
                "unidad": parte["unidad"],
                "comandante": parte["comandante"],
                "efectiva": total_efectiva,
                "novedades": total_novedades,
                "disponible": total_disponible,
            }
        )
        for key in CATEGORIAS:
            efectiva[key] += reporte["efectiva"][key]
            en_novedad[key] += reporte["en_novedad"][key]
            disponible[key] += reporte["disponible"][key]
        for novedad in reporte["novedades"]:
            item = dict(novedad)
            item["unidad_reporta"] = parte["unidad"]
            item["comandante"] = parte["comandante"]
            novedades.append(item)
    return {
        "fecha": fecha,
        "reportes": reportes,
        "unidades": unidades,
        "novedades": novedades,
        "efectiva": efectiva,
        "en_novedad": en_novedad,
        "disponible": disponible,
    }


def pdf_escape(text):
    return str(text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@lru_cache(maxsize=2)
def _logo_rgb(max_width=120):
    path = STATIC_DIR / "logo_policia.png"
    data = path.read_bytes()
    pos = 8
    idat = b""
    width = height = bit_depth = color_type = None
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if ctype == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
            bit_depth, color_type = chunk[8], chunk[9]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if bit_depth != 8 or color_type not in (2, 6):
        return None
    bpp = 3 if color_type == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * bpp
    rows = bytearray()
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        filt = raw[p]
        p += 1
        line = bytearray(raw[p : p + stride])
        p += stride
        if filt == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 0xFF
        rows += line
        prev = line

    target_w = max_width
    target_h = max(1, round(height * target_w / width))
    rgb = bytearray()
    for ty in range(target_h):
        sy = ty * height // target_h
        for tx in range(target_w):
            sx = tx * width // target_w
            idx = (sy * width + sx) * bpp
            r, g, b = rows[idx], rows[idx + 1], rows[idx + 2]
            if color_type == 6:
                a = rows[idx + 3]
                if a < 255:
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
            rgb += bytes((r, g, b))
    return bytes(rgb), target_w, target_h


class PdfBuilder:
    PAGE_W = 612
    PAGE_H = 792
    MARGIN = 36

    def __init__(self):
        self.pages = []
        self.content = None
        self.images = []
        self.y = 0.0
        self.new_page()

    def new_page(self):
        self.pages.append([])
        self.content = self.pages[-1]
        self.y = self.PAGE_H - self.MARGIN

    def ensure(self, height):
        if self.y - height < self.MARGIN:
            self.new_page()

    def text(self, x, y, string, font="F1", size=10, align="l", color=None):
        if align == "r":
            x = x - self.text_width(string, size)
        elif align == "c":
            x = x - self.text_width(string, size) / 2
        prefix = f"{color} rg " if color else "0 0 0 rg "
        self.content.append(
            f"BT {prefix}/{font} {size} Tf 1 0 0 1 {x:.1f} {y:.1f} Tm ({pdf_escape(string)}) Tj ET"
        )

    def circle(self, cx, cy, r, fill="1 1 1"):
        k = r * 0.5523
        self.content.append(
            f"{fill} rg {cx + r:.1f} {cy:.1f} m {cx + r:.1f} {cy + k:.1f} {cx + k:.1f} {cy + r:.1f} {cx:.1f} {cy + r:.1f} c "
            f"{cx - k:.1f} {cy + r:.1f} {cx - r:.1f} {cy + k:.1f} {cx - r:.1f} {cy:.1f} c "
            f"{cx - r:.1f} {cy - k:.1f} {cx - k:.1f} {cy - r:.1f} {cx:.1f} {cy - r:.1f} c "
            f"{cx + k:.1f} {cy - r:.1f} {cx + r:.1f} {cy - k:.1f} {cx + r:.1f} {cy:.1f} c h f"
        )

    def label_text(self, x, y, label, value, size=10):
        self.text(x, y, label, "F2", size)
        self.text(x + self.text_width(label, size) + 12, y, value, "F1", size)

    def line(self, x1, y1, x2, y2, width=0.8):
        self.content.append(f"{width:.2f} w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def rect(self, x, y_top, width, height, fill=None):
        bottom = y_top - height
        if fill:
            self.content.append(f"{fill} rg {x:.1f} {bottom:.1f} {width:.1f} {height:.1f} re f")
        else:
            self.content.append(f"0.8 w {x:.1f} {bottom:.1f} {width:.1f} {height:.1f} re S")

    def add_image(self, rgb_data, width, height):
        self.images.append((rgb_data, width, height))
        return len(self.images) - 1

    def image(self, index, x, y_top, width, height):
        self.content.append(f"q {width:.1f} 0 0 {height:.1f} {x:.1f} {y_top - height:.1f} cm /Im{index} Do Q")

    def text_width(self, text, size):
        return len(str(text)) * size * 0.53

    def wrap(self, text, size, width):
        text = " ".join(("" if text is None else str(text)).split())
        words = text.split()
        if not words:
            return [""]
        lines, current = [], ""
        for word in words:
            trial = (current + " " + word).strip()
            if self.text_width(trial, size) <= width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def heading(self, text):
        self.ensure(22)
        self.y -= 8
        self.text(self.MARGIN, self.y, text.upper(), "F2", 12)
        self.y -= 16

    def table(self, headers, rows, col_widths, fill="0.929 0.961 0.941", hs=9, cs=9):
        pad = 4
        x0 = self.MARGIN
        max_width = self.PAGE_W - 2 * self.MARGIN
        total_width = sum(col_widths)
        if total_width > max_width:
            scale = max_width / total_width
            col_widths = [width * scale for width in col_widths]
        x1 = x0 + sum(col_widths)
        col_xs = [x0 + sum(col_widths[: i + 1]) for i in range(len(col_widths))]
        aligns = ["l"] + ["c"] * (len(col_widths) - 1)

        def prepare(values, size):
            return [self.wrap(value, size, col_widths[j] - 2 * pad) for j, value in enumerate(values)]

        header_cells = prepare(headers, hs)
        header_h = 8 + max(len(c) for c in header_cells) * (hs + 3)

        data = []
        for row in rows:
            cells = prepare(row, cs)
            h = 8 + max(len(c) for c in cells) * (cs + 3)
            data.append((cells, h))

        available = self.PAGE_H - 2 * self.MARGIN
        chunks = []
        chunk = {"rows": [], "used": header_h}
        for cells, h in data:
            if chunk["used"] + h > available:
                chunks.append(chunk)
                chunk = {"rows": [], "used": header_h}
            chunk["rows"].append((cells, h))
            chunk["used"] += h
        if chunk["rows"]:
            chunks.append(chunk)
        if not chunks:
            chunks = [chunk]

        def draw_row(cells, h, top, header=False):
            if header and fill:
                self.rect(x0, top, x1 - x0, h, fill=fill)
            size = hs if header else cs
            font = "F2" if header else "F1"
            line_h = size + 3
            for j, lines in enumerate(cells):
                total_text_h = len(lines) * line_h
                yy = top - ((h - total_text_h) / 2) - size
                for line in lines:
                    if aligns[j] == "c":
                        x = col_xs[j] - col_widths[j] + (col_widths[j] - self.text_width(line, size)) / 2
                    else:
                        x = col_xs[j] - col_widths[j] + pad
                    self.text(x, yy, line, font, size)
                    yy -= line_h

        first = True
        for chunk in chunks:
            if not first:
                self.new_page()
            first = False
            self.ensure(chunk["used"])
            top = self.y
            draw_row(header_cells, header_h, top, header=True)
            top -= header_h
            for cells, h in chunk["rows"]:
                draw_row(cells, h, top)
                top -= h
            bottom = top
            self.rect(x0, self.y, x1 - x0, self.y - bottom)
            boundaries = [self.y - header_h]
            yy = self.y - header_h
            for cells, h in chunk["rows"]:
                yy -= h
                boundaries.append(yy)
            for b in boundaries[:-1]:
                self.line(x0, b, x1, b, 0.5)
            for x in col_xs[1:]:
                self.line(x, self.y, x, bottom, 0.5)
            self.y = bottom - 16

    def build(self):
        objects = []
        page_refs = []
        font_obj = 3 + len(self.pages)
        image_obj_start = font_obj + 2
        content_start = image_obj_start + len(self.images)

        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(None)
        for index in range(len(self.pages)):
            page_obj = 3 + index
            content_obj = content_start + index
            page_refs.append(f"{page_obj} 0 R")
            xobj = "".join(f"/Im{i} {image_obj_start + i} 0 R " for i in range(len(self.images)))
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.PAGE_W} {self.PAGE_H}] /Resources << /Font << /F1 {font_obj} 0 R /F2 {font_obj + 1} 0 R >> /XObject << {xobj}>> >> /Contents {content_obj} 0 R >>".encode("cp1252")
            )
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(self.pages)} >>".encode("cp1252")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        for rgb, width, height in self.images:
            stream = zlib.compress(bytes(rgb))
            objects.append(
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(stream)} >>\nstream\n".encode("latin-1")
                + stream
                + b"\nendstream"
            )

        for content in self.pages:
            stream = "\n".join(content).encode("cp1252", "replace")
            objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")

        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("latin-1"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("latin-1"))
        return bytes(pdf)


def render_report(pdf, reporte):
    parte = reporte["parte"]
    x0 = pdf.MARGIN
    x1 = pdf.PAGE_W - pdf.MARGIN
    center_x = pdf.PAGE_W / 2

    banner_h = 92
    top = pdf.PAGE_H - pdf.MARGIN
    pdf.rect(x0, top, x1 - x0, banner_h, fill="0.004 0.208 0.106")
    pdf.rect(x0, top, x1 - x0, banner_h * 0.45, fill="0.027 0.392 0.196")
    pdf.line(x0, top - banner_h, x1, top - banner_h, 1.6)

    logo = _logo_rgb()
    if logo:
        rgb, w, h = logo
        img = pdf.add_image(rgb, w, h)
        cy = top - banner_h / 2
        pdf.circle(x0 + 44, cy, 34)
        img_w, img_h = 50, 27
        pdf.image(img, x0 + 44 - img_w / 2, cy + img_h / 2, img_w, img_h)

    pdf.text(x0 + 90, top - 32, "POLICIA NACIONAL", "F2", 11, color="1 1 1")
    pdf.text(x0 + 90, top - 47, parte["unidad"], "F1", 8, color="1 1 1")

    pdf.text(x0 + 370, top - 34, "PARTE DE FUERZA", "F2", 22, align="c", color="1 1 1")
    pdf.text(x0 + 370, top - 52, "FUERZA EFECTIVA, DISPONIBLE Y NOVEDADES", "F1", 8, align="c", color="1 1 1")

    pdf.y = top - banner_h - 16

    meta_h = 58
    pdf.rect(x0, pdf.y, x1 - x0, meta_h, fill="0.933 0.973 0.949")
    pdf.rect(x0, pdf.y, x1 - x0, meta_h)
    inner = x0 + 12
    pdf.label_text(inner, pdf.y - 18, "Unidad:", parte["unidad"], 10)
    pdf.label_text(inner, pdf.y - 34, "Fecha:", f"{parte['fecha']}", 10)
    pdf.label_text(inner + 220, pdf.y - 34, "Hora:", parte["hora_parte"], 10)
    pdf.label_text(inner, pdf.y - 50, "Comandante:", parte["comandante"], 10)
    pdf.y -= meta_h + 12

    pdf.heading("Fuerza disponible")
    fuerza_rows = [
        [CATEGORIAS[key], reporte["efectiva"][key], reporte["en_novedad"][key], reporte["disponible"][key]]
        for key in CATEGORIAS
    ]
    pdf.table(["Categor\u00eda", "Efectiva", "En novedades", "Disponible"], fuerza_rows, [240, 100, 100, 100], hs=10, cs=10)

    pdf.heading("Novedades")
    nov_rows = []
    for novedad in reporte["novedades"]:
        funcionario = f"{novedad['grado']} {novedad['nombres']} {novedad['apellidos']}"
        nov_rows.append([
            tipo_novedad_text(novedad),
            funcionario,
            novedad.get("cargo") or "Sin cargo registrado",
            f"{novedad['fecha_inicio']} {novedad['hora_inicio']}",
            f"{novedad['fecha_fin']} {novedad['hora_fin']}",
            novedad["dias_calculados"],
            novedad.get("solicitud_psi") or "-",
        ])
    if not nov_rows:
        nov_rows = [["Sin novedades registradas.", "", "", "", "", "", ""]]
    pdf.table(["Tipo", "Funcionario", "Cargo", "Inicio", "Fin", "D\u00edas", "PSI"], nov_rows, [58, 170, 110, 62, 62, 38, 40], hs=8, cs=7)

    pdf.heading("Observaciones")
    pdf.ensure(20)
    for line in pdf.wrap(parte.get("observaciones") or "Sin observaciones.", 10, x1 - x0):
        pdf.text(x0, pdf.y, line, "F1", 10)
        pdf.y -= 14


def reporte_pdf(reporte):
    pdf = PdfBuilder()
    render_report(pdf, reporte)
    return pdf.build()


def pdf_todos(reportes):
    pdf = PdfBuilder()
    if not reportes:
        pdf.text(pdf.MARGIN, pdf.y, "Sin reportes para los filtros seleccionados.", "F1", 11)
        return pdf.build()
    for index, reporte in enumerate(reportes):
        if index:
            pdf.new_page()
        render_report(pdf, reporte)
    return pdf.build()


def pdf_reporte_general(data):
    pdf = PdfBuilder()
    x0 = pdf.MARGIN
    x1 = pdf.PAGE_W - pdf.MARGIN
    total_efectiva = sum(data["efectiva"].values())
    total_novedades = sum(data["en_novedad"].values())
    total_disponible = sum(data["disponible"].values())

    pdf.text(x0, pdf.y, "REPORTE GENERAL DEL DIA", "F2", 18)
    pdf.y -= 20
    pdf.label_text(x0, pdf.y, "Fecha:", data["fecha"], 11)
    pdf.y -= 24
    pdf.rect(x0, pdf.y, x1 - x0, 42, fill="0.933 0.973 0.949")
    pdf.rect(x0, pdf.y, x1 - x0, 42)
    pdf.label_text(x0 + 14, pdf.y - 16, "Fuerza efectiva total:", total_efectiva, 10)
    pdf.label_text(x0 + 210, pdf.y - 16, "Total en novedades:", total_novedades, 10)
    pdf.label_text(x0 + 400, pdf.y - 16, "Fuerza disponible:", total_disponible, 10)
    pdf.y -= 62

    pdf.heading("Partes reportados por unidades")
    unidades_rows = [
        [item["fecha"], item["hora"], item["unidad"], item["comandante"], item["efectiva"], item["novedades"], item["disponible"]]
        for item in data["unidades"]
    ] or [["-", "-", "Sin partes guardados para esta fecha", "-", "-", "-", "-"]]
    pdf.table(
        ["Fecha", "Hora", "Unidad", "Comandante", "Efectiva", "Novedades", "Disponible"],
        unidades_rows,
        [58, 45, 145, 135, 55, 60, 60],
        hs=8,
        cs=8,
    )

    pdf.heading("Fuerza disponible consolidada")
    fuerza_rows = [
        [CATEGORIAS[key], data["efectiva"][key], data["en_novedad"][key], data["disponible"][key]]
        for key in CATEGORIAS
    ]
    fuerza_rows.append(["Total Distrito", total_efectiva, total_novedades, total_disponible])
    pdf.table(["Categoria", "Efectiva", "En novedades", "Disponible"], fuerza_rows, [240, 100, 100, 100], hs=9, cs=9)

    pdf.heading("Novedades del dia")
    nov_rows = []
    for novedad in data["novedades"]:
        funcionario = f"{novedad['grado']} {novedad['nombres']} {novedad['apellidos']}"
        nov_rows.append(
            [
                novedad["unidad_reporta"],
                tipo_novedad_text(novedad),
                funcionario,
                novedad.get("cargo") or "Sin cargo registrado",
                novedad["unidad_funcionario"],
                f"{novedad['fecha_inicio']} {novedad['hora_inicio']}",
                f"{novedad['fecha_fin']} {novedad['hora_fin']}",
                novedad["dias_calculados"],
                novedad.get("solicitud_psi") or "-",
            ]
        )
    if not nov_rows:
        nov_rows = [["Sin novedades registradas para esta fecha", "-", "-", "-", "-", "-", "-", "-", "-"]]
    pdf.table(
        ["Unidad reporta", "Tipo", "Funcionario", "Cargo", "Unidad funcionario", "Inicio", "Fin", "Dias", "PSI"],
        nov_rows,
        [75, 45, 105, 90, 75, 55, 55, 25, 20],
        hs=6,
        cs=6,
    )
    return pdf.build()


def layout(content, user=None):
    user = user or {}
    unit_name = get_unit_name(user.get("unidad_id")) if user.get("rol") == "unidad" else "ADMINISTRADOR GENERAL"
    novedades_link = '<a class="nav-link" href="/novedades"><span class="nav-ico">NV</span><span>Novedades</span></a>' if user.get("rol") == "admin" else ""
    general_link = '<a class="nav-link" href="/reporte-general"><span class="nav-ico">RG</span><span>Reporte General</span></a>' if user.get("rol") == "admin" else ""
    report_label = "Reportes de Unidades" if user.get("rol") == "admin" else "Reportes Guardados"
    report_link = f'<a class="nav-link" href="/historial"><span class="nav-ico">RP</span><span>{report_label}</span></a>'
    users_link = '<a class="nav-link" href="/usuarios"><span class="nav-ico">US</span><span>Usuarios</span></a>' if user.get("rol") == "admin" else ""
    ingresos_link = '<a class="nav-link" href="/ingresos"><span class="nav-ico">IN</span><span>Ingresos</span></a>' if user.get("rol") == "admin" else ""
    security_link = '<a class="nav-link" href="/seguridad"><span class="nav-ico">SG</span><span>Seguridad</span></a>' if user.get("rol") == "admin" else ""
    return page_shell(
        "Parte de Fuerza",
        f"""
<header class="topbar no-print">
    <video class="topbar-video" autoplay muted loop playsinline preload="auto" src="/video-fondo"></video>
    <div class="brand">
        <img class="logo-img" src="/static/logo_policia.png" alt="Polic&iacute;a Nacional">
        <div><strong>POLIC&Iacute;A NACIONAL</strong><span>{h(unit_name)}</span></div>
    </div>
    <div class="title-block"><h1>PARTE DE FUERZA</h1><p>FUERZA EFECTIVA, DISPONIBLE Y NOVEDADES</p></div>
</header>
<div class="app-shell">
    <aside class="sidebar no-print">
        <a class="nav-link active" href="/parte"><span class="nav-ico">PF</span><span>Parte de Fuerza</span></a>
        {novedades_link}
        <a class="nav-link" href="/funcionarios"><span class="nav-ico">FN</span><span>Funcionarios</span></a>
        {general_link}
        {report_link}
        {users_link}
        {ingresos_link}
        {security_link}
        <a class="nav-link logout-link" href="/logout"><span class="nav-ico">CS</span><span>Cerrar Sesi&oacute;n</span></a>
    </aside>
    <main class="content">{content}</main>
</div>
""",
    )


def login_page(error=""):
    alert = f"<div class='alert danger'>{error}</div>" if error else ""
    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Ingreso - Parte de Fuerza</title>
    <link rel="stylesheet" href="/static/app.css">
</head>
<body class="login-page">
    <form method="POST" action="/login" class="login-card" novalidate>
        <img class="login-hero" src="/static/login_parte_fuerza.png" alt="Parte de Fuerza">
        {alert}
        <label>Usuario<input type="text" name="email" value="" autocomplete="username" required></label>
        <label>Contrase&ntilde;a<input type="password" name="password" required></label>
        <button class="btn primary full">Ingresar</button>
    </form>
</body>
</html>"""

def parte_page(user=None):
    user = user or {}
    fecha_default, _hora_actual = fecha_hora_actual()
    hora_default = "07:00"
    with db() as conn:
        unidades = ordenar_unidades(rows_dict(conn.execute("SELECT * FROM unidades WHERE estado = 'activa'")), solo_operativas=True)
        funcionarios = ordenar_funcionarios(rows_dict(
            conn.execute(
                """
                SELECT f.*, u.nombre unidad_nombre
                FROM funcionarios f
                JOIN unidades u ON u.id = f.unidad_id
                WHERE f.estado = 'activo'
                """
            )
        ), por_unidad=True)

    selected_unidad_id = str(user.get("unidad_id") or "") if user.get("rol") == "unidad" else ""
    efectiva_inicial = {key: 0 for key in CATEGORIAS}
    if selected_unidad_id:
        efectiva_inicial = fuerza_efectiva_por_unidad(selected_unidad_id)

    unidad_options = f"<option value='' {'selected' if not selected_unidad_id else ''}>Seleccione unidad...</option>"
    unidad_options += "".join(
        f"<option value='{u['id']}' {'selected' if str(u['id']) == selected_unidad_id else ''}>{h(u['nombre'])}</option>"
        for u in unidades
    )
    tipos_options = "".join(f"<option>{tipo}</option>" for tipo in TIPOS_NOVEDAD)
    report_button_label = "Reportes de Unidades" if user.get("rol") == "admin" else "Reportes Guardados"
    report_button = f'<a class="btn outline full" href="/historial">{report_button_label}</a>'

    content = f"""
<form id="parteForm" class="parte-form">
    <section class="panel general-panel">
        <h2>Informaci&oacute;n general</h2>
        <div class="grid two">
            <label>Unidad<select id="unidad_id">{unidad_options}</select></label>
            <label>Comandante que reporta<input id="comandante" placeholder="Ejemplo: Cap. YESICA LICETH GOMEZ TRUJILLO"></label>
            <input type="hidden" id="fecha" value="{fecha_default}">
            <input type="hidden" id="hora_parte" value="{hora_default}">
        </div>
    </section>

    <div class="grid main-grid">
        <div class="left-stack">
            <section class="panel">
                <h2>1. Fuerza efectiva <small>(total unidad)</small></h2>
                <table class="data-table">
                    <thead><tr><th>Categor&iacute;a</th><th>Cantidad</th></tr></thead>
                    <tbody>
                        <tr><td>Oficiales</td><td><strong class="qty-display" id="efectiva_oficiales_text">{efectiva_inicial['oficiales']}</strong><input class="efectiva" id="efectiva_oficiales" type="hidden" value="{efectiva_inicial['oficiales']}"></td></tr>
                        <tr><td>Nivel Ejecutivo</td><td><strong class="qty-display" id="efectiva_nivel_ejecutivo_text">{efectiva_inicial['nivel_ejecutivo']}</strong><input class="efectiva" id="efectiva_nivel_ejecutivo" type="hidden" value="{efectiva_inicial['nivel_ejecutivo']}"></td></tr>
                        <tr><td>Patrulleros</td><td><strong class="qty-display" id="efectiva_patrulleros_text">{efectiva_inicial['patrulleros']}</strong><input class="efectiva" id="efectiva_patrulleros" type="hidden" value="{efectiva_inicial['patrulleros']}"></td></tr>
                        <tr><td>Patrulleros de Polic&iacute;a</td><td><strong class="qty-display" id="efectiva_patrulleros_policia_text">{efectiva_inicial['patrulleros_policia']}</strong><input class="efectiva" id="efectiva_patrulleros_policia" type="hidden" value="{efectiva_inicial['patrulleros_policia']}"></td></tr>
                        <tr><td>Auxiliares de Polic&iacute;a</td><td><strong class="qty-display" id="efectiva_auxiliares_text">{efectiva_inicial['auxiliares']}</strong><input class="efectiva" id="efectiva_auxiliares" type="hidden" value="{efectiva_inicial['auxiliares']}"></td></tr>
                    </tbody>
                    <tfoot><tr><th>Total fuerza efectiva</th><th id="total_efectiva">0</th></tr></tfoot>
                </table>
            </section>

            <section class="panel">
                <h2>3. Fuerza disponible <small>(despu&eacute;s de novedades)</small></h2>
                <table class="data-table">
                    <thead><tr><th>Categor&iacute;a</th><th>Efectiva</th><th>En novedades</th><th>Disponible</th></tr></thead>
                    <tbody>
                        {"".join(f"<tr><td>{label}</td><td id='ef_{key}'>0</td><td id='nov_{key}'>0</td><td id='disp_{key}'>0</td></tr>" for key, label in CATEGORIAS.items())}
                    </tbody>
                    <tfoot><tr><th>Total</th><th id="total_efectiva_2">0</th><th id="total_novedades">0</th><th id="total_disponible">0</th></tr></tfoot>
                </table>
            </section>
        </div>

        <div class="flow-arrow no-mobile"><span>OK</span><small>C&aacute;lculo<br>Autom&aacute;tico</small></div>

        <section class="panel" id="novedades">
            <div class="section-head"><h2>2. Novedades del personal</h2><button type="button" class="btn primary" id="toggleNovedad">+ Registrar Novedad</button></div>
            <div class="subpanel" id="novedadForm">
                <h3>Registrar novedad</h3>
                <div class="grid three">
                    <label>Unidad<select id="unidad_novedad_id">{unidad_options}</select></label>
                    <label>Tipo de novedad<select id="tipo_novedad"><option value="">Seleccione...</option>{tipos_options}</select></label>
                    <label>Funcionario<select id="funcionario_id"><option value="">Seleccione...</option></select></label>
                </div>
                <div class="cargo-funcionario" id="cargoFuncionario" style="display:none;">
                    <span>Cargo que ocupa</span>
                    <strong id="cargoFuncionarioTexto"></strong>
                </div>
                <div class="psi-field" id="psiField" style="display:none;">
                    <label>Solicito permiso por PSI
                        <select id="solicitud_psi">
                            <option value="">Seleccione...</option>
                            <option value="Si">S&iacute;</option>
                            <option value="No">No</option>
                        </select>
                    </label>
                    <div class="alert info compact-alert">Este campo es obligatorio cuando el tipo de novedad es Permiso o Franquicia.</div>
                </div>
                <div class="other-field" id="otraNovedadField" style="display:none;">
                    <label>Qu&eacute; novedad tiene
                        <input type="text" id="otra_novedad_detalle" maxlength="255" placeholder="Escriba la novedad del funcionario">
                    </label>
                    <div class="alert info compact-alert">Este campo es obligatorio cuando el tipo es Otra novedad.</div>
                </div>
                <div class="grid four compact">
                    <label>Fecha inicio<input type="date" id="fecha_inicio" value="{fecha_default}"></label>
                    <label>Hora inicio<input type="time" id="hora_inicio" value="06:00"></label>
                    <label>Fecha fin<input type="date" id="fecha_fin" value="{fecha_default}"></label>
                    <label>Hora fin<input type="time" id="hora_fin" value="18:00"></label>
                </div>
                <div class="novedad-actions">
                    <div class="duration-box">D&iacute;as calculados: <strong id="diasTexto">0 d&iacute;as</strong></div>
                    <div class="actions-inline">
                        <button type="button" class="btn outline" id="cancelarNovedad">Cancelar</button>
                        <button type="button" class="btn primary" id="guardarNovedad">Guardar Novedad</button>
                    </div>
                </div>
                <div class="alert info">El c&aacute;lculo de d&iacute;as se realiza autom&aacute;ticamente.</div>
            </div>
            <table class="data-table">
                <thead><tr><th>Tipo</th><th>Funcionario</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th><th>Acci&oacute;n</th></tr></thead>
                <tbody id="novedadesBody"></tbody>
                <tfoot><tr><th colspan="4">Total funcionarios en novedades:</th><th id="totalNovedadesTabla">0</th><th></th><th></th></tr></tfoot>
            </table>
        </section>
    </div>

    <div class="grid lower-grid summary-row">
        <aside class="panel summary-card">
            <h2>Resumen del parte</h2>
            <div class="metric"><span>Fuerza Efectiva Total:</span><strong id="res_efectiva">0</strong></div>
            <div class="metric"><span>Total en Novedades:</span><strong id="res_novedades">0</strong></div>
            <div class="metric green"><span>Fuerza Disponible:</span><strong id="res_disponible">0</strong></div>
            <div class="metric"><span>Porcentaje Disponible:</span><strong id="porcentaje_disponible">0%</strong></div>
        </aside>
    </div>

    <div class="grid lower-grid">
        <section class="panel"><h2>Observaciones del comandante</h2><textarea id="observaciones" rows="5"></textarea></section>
        <section class="panel actions-panel no-print">
            <h2>Acciones</h2>
            <button class="btn primary full" id="guardarParteBtn" type="button">Guardar Parte de Fuerza</button>
            <button class="btn outline full" type="button" onclick="window.print()">Imprimir Parte</button>
            {report_button}
        </section>
    </div>
</form>
<script>
window.ParteFuerza = {{
    categorias: {json.dumps(CATEGORIAS, ensure_ascii=False)},
    funcionarios: {json.dumps(funcionarios, ensure_ascii=False)}
}};
</script>
<script src="/static/app.js"></script>
"""
    return layout(content, user)


def funcionarios_page(user=None):
    user = user or {}
    with db() as conn:
        if user.get("rol") == "unidad":
            funcionarios = ordenar_funcionarios(rows_dict(conn.execute("SELECT f.*, u.nombre unidad FROM funcionarios f JOIN unidades u ON u.id = f.unidad_id WHERE f.unidad_id = ?", (user.get("unidad_id"),))))
            unidades = ordenar_unidades(rows_dict(conn.execute("SELECT * FROM unidades WHERE id = ?", (user.get("unidad_id"),))))
        else:
            funcionarios = ordenar_funcionarios(rows_dict(conn.execute("SELECT f.*, u.nombre unidad FROM funcionarios f JOIN unidades u ON u.id = f.unidad_id")), por_unidad=True)
            unidades = ordenar_unidades(rows_dict(conn.execute("SELECT * FROM unidades")))

    rows = "".join(
        f"<tr><td>{h(f['grado'])}</td><td>{h(f['nombres'])} {h(f['apellidos'])}</td><td>{h(CATEGORIAS[f['categoria']])}</td><td>{h(f.get('cargo') or 'Sin cargo registrado')}</td><td>{h(f['unidad'])}</td><td>{h(f['estado'])}</td></tr>"
        for f in funcionarios
    )
    unidad_options = "".join(f"<option value='{u['id']}'>{h(u['nombre'])}</option>" for u in unidades)
    categoria_options = "".join(f"<option value='{k}'>{v}</option>" for k, v in CATEGORIAS.items())

    content = f"""
<section class="panel">
    <h2>Registrar funcionario</h2>
    <form method="POST" action="/funcionarios" class="grid seven">
        <input name="grado" placeholder="Grado" required>
        <input name="nombres" placeholder="Nombres" required>
        <input name="apellidos" placeholder="Apellidos" required>
        <input name="cargo" placeholder="Cargo que ocupa" required>
        <select name="categoria">{categoria_options}</select>
        <select name="unidad_id">{unidad_options}</select>
        <button class="btn primary">Guardar</button>
    </form>
</section>
<section class="panel">
    <h2>Funcionarios</h2>
    <table class="data-table"><thead><tr><th>Grado</th><th>Funcionario</th><th>Categor&iacute;a</th><th>Cargo</th><th>Unidad</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""
    return layout(content, user)


def usuarios_page(user=None, error=""):
    user = user or {}
    if user.get("rol") != "admin":
        return layout("<section class='panel'>No autorizado.</section>", user)
    with db() as conn:
        usuarios = rows_dict(
            conn.execute(
                """
                SELECT us.*, un.nombre unidad
                FROM usuarios us
                LEFT JOIN unidades un ON un.id = us.unidad_id
                ORDER BY CASE WHEN us.rol = 'admin' THEN 0 ELSE 1 END, un.nombre, us.email
                """
            )
        )
        unidades = ordenar_unidades(rows_dict(conn.execute("SELECT * FROM unidades WHERE estado = 'activa'")))

    rol_options = {
        "admin": "Administrador",
        "unidad": "Unidad",
    }

    def unidad_options(selected_id):
        options = "<option value='' " + ("selected" if not selected_id else "") + ">Sin unidad</option>"
        for unidad in unidades:
            selected = "selected" if str(unidad["id"]) == str(selected_id or "") else ""
            options += f"<option value='{unidad['id']}' {selected}>{h(unidad['nombre'])}</option>"
        return options

    def rol_select(selected):
        return "".join(
            f"<option value='{value}' {'selected' if value == selected else ''}>{label}</option>"
            for value, label in rol_options.items()
        )

    rows = ""
    for item in usuarios:
        password_visible = item.get("password_plano") or ""
        rows += f"""
        <tr>
            <td colspan="6">
                <form method="POST" action="/usuarios" class="user-edit-row">
                    <input type="hidden" name="id" value="{item['id']}">
                    <label>Nombre<input name="nombre" value="{h(item['nombre'])}" required></label>
                    <label>Usuario<input name="email" value="{h(item['email'])}" required></label>
                    <label>Contrase&ntilde;a<input name="password_plano" value="{h(password_visible)}" required></label>
                    <label>Rol<select name="rol">{rol_select(item['rol'])}</select></label>
                    <label>Unidad<select name="unidad_id">{unidad_options(item.get('unidad_id'))}</select></label>
                    <button class="btn primary" type="submit">Guardar</button>
                </form>
            </td>
        </tr>"""

    new_unit_options = unidad_options("")
    alert = f"<div class='alert danger'>{h(error)}</div>" if error else ""
    content = f"""
<section class="panel">
    <div class="section-head"><h2>Usuarios y contrase&ntilde;as</h2><span class="security-badge">Solo administrador</span></div>
    <div class="alert info">Desde aqu&iacute; el administrador puede ver y modificar los usuarios de cada unidad. La contrase&ntilde;a se guarda visible solo para esta pantalla administrativa y se usa cifrada para iniciar sesi&oacute;n.</div>
    {alert}
    <h3>Crear usuario</h3>
    <form method="POST" action="/usuarios" class="grid six">
        <input type="hidden" name="id" value="">
        <input name="nombre" placeholder="Nombre visible" required>
        <input name="email" placeholder="Usuario" required>
        <input name="password_plano" placeholder="Contrase&ntilde;a" required>
        <select name="rol"><option value="unidad">Unidad</option><option value="admin">Administrador</option></select>
        <select name="unidad_id">{new_unit_options}</select>
        <button class="btn primary">Crear</button>
    </form>
</section>
<section class="panel">
    <h2>Usuarios registrados</h2>
    <table class="data-table"><thead><tr><th>Editar usuarios</th></tr></thead><tbody>{rows or '<tr><td>No hay usuarios registrados.</td></tr>'}</tbody></table>
</section>
"""
    return layout(content, user)


def novedades_page(user=None, query=""):
    user = user or {}
    params = parse_qs(query)
    fecha = params.get("fecha", [""])[0] or datetime.now().date().isoformat()
    where = ["n.estado = 'activa'", "n.fecha_inicio <= ?", "n.fecha_fin >= ?"]
    values = [fecha, fecha]
    if user.get("rol") == "unidad":
        where.append("p.unidad_id = ?")
        values.append(user.get("unidad_id"))
    where_sql = " AND ".join(where)

    with db() as conn:
        novedades = rows_dict(
            conn.execute(
                f"""
                SELECT
                    p.fecha parte_fecha,
                    p.hora_parte,
                    p.comandante,
                    up.nombre unidad_parte,
                    n.tipo_novedad,
                    n.observaciones,
                    n.fecha_inicio,
                    n.hora_inicio,
                    n.fecha_fin,
                    n.hora_fin,
                    n.dias_calculados,
                    n.solicitud_psi,
                    f.grado,
                    f.nombres,
                    f.apellidos,
                    f.categoria,
                    f.cargo,
                    uf.nombre unidad_funcionario
                FROM novedades n
                JOIN partes p ON p.id = n.parte_id
                JOIN unidades up ON up.id = p.unidad_id
                JOIN funcionarios f ON f.id = n.funcionario_id
                JOIN unidades uf ON uf.id = f.unidad_id
                WHERE {where_sql}
                ORDER BY up.nombre, f.categoria, f.grado, f.apellidos, f.nombres
                """,
                values,
            )
        )

    rows = ""
    for novedad in novedades:
        funcionario = f"{novedad['grado']} {novedad['nombres']} {novedad['apellidos']}"
        rows += f"""
        <tr>
            <td>{h(novedad['unidad_parte'])}</td>
            <td>{h(novedad['comandante'])}</td>
            <td>{h(novedad['tipo_novedad'])}{('<br><small>' + h(novedad.get('observaciones')) + '</small>') if novedad['tipo_novedad'] == 'Otra novedad' and novedad.get('observaciones') else ''}</td>
            <td>{h(funcionario)}</td>
            <td>{h(novedad.get('cargo') or 'Sin cargo registrado')}</td>
            <td>{h(novedad['unidad_funcionario'])}</td>
            <td>{h(novedad['fecha_inicio'])} {h(novedad['hora_inicio'])}</td>
            <td>{h(novedad['fecha_fin'])} {h(novedad['hora_fin'])}</td>
            <td>{h(novedad['dias_calculados'])}</td>
            <td>{h(novedad.get('solicitud_psi') or '-')}</td>
        </tr>
        """

    content = f"""
<section class="panel">
    <div class="section-head"><h2>Novedades por fecha</h2><span class="security-badge">{len(novedades)} funcionarios en novedad</span></div>
    <form method="GET" action="/novedades" class="filters">
        <label>Fecha a consultar<input type="date" name="fecha" value="{h(fecha)}"></label>
        <button class="btn primary">Buscar novedades</button>
    </form>
    <div class="alert info">La consulta muestra las novedades vigentes para la fecha seleccionada seg&uacute;n los partes guardados por los comandantes.</div>
    <table class="data-table"><thead><tr><th>Unidad que reporta</th><th>Comandante</th><th>Tipo</th><th>Funcionario</th><th>Cargo</th><th>Unidad funcionario</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th></tr></thead><tbody>{rows or '<tr><td colspan="10">No hay funcionarios en novedad para esta fecha.</td></tr>'}</tbody></table>
</section>
"""
    return layout(content, user)


def historial_page(user=None, query=""):
    user = user or {}
    params = parse_qs(query)
    fecha = params.get("fecha", [""])[0]
    unidad_id = params.get("unidad_id", [""])[0]

    where = []
    values = []
    if user.get("rol") == "unidad":
        where.append("p.unidad_id = ?")
        values.append(user.get("unidad_id"))
    elif unidad_id:
        where.append("p.unidad_id = ?")
        values.append(unidad_id)
    if fecha:
        where.append("p.fecha = ?")
        values.append(fecha)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        partes = rows_dict(
            conn.execute(
                f"""
                SELECT p.*, u.nombre unidad,
                (SELECT COUNT(*) FROM novedades n WHERE n.parte_id = p.id) novedades
                FROM partes p JOIN unidades u ON u.id = p.unidad_id
                {where_sql}
                ORDER BY p.fecha DESC, p.id DESC
                """,
                values,
            )
        )
        unidades = ordenar_unidades(rows_dict(conn.execute("SELECT * FROM unidades")))

    unidad_options = "<option value=''>Todas las unidades</option>" + "".join(
        f"<option value='{u['id']}' {'selected' if str(u['id']) == unidad_id else ''}>{h(u['nombre'])}</option>" for u in unidades
    )
    rows = ""
    for parte in partes:
        efectiva = sum(parte_efectiva(parte).values())
        disponible = max(0, efectiva - parte["novedades"])
        delete_action = ""
        if user.get("rol") == "admin":
            delete_action = f"""
                <form method="POST" action="/eliminar-parte" onsubmit="return confirm('¿Eliminar este parte y sus novedades?')">
                    <input type="hidden" name="id" value="{parte['id']}">
                    <button class="btn small danger" type="submit">Eliminar</button>
                </form>
            """
        rows += f"""
        <tr>
            <td>{h(parte['fecha'])}<br><small>{h(parte['hora_parte'])}</small></td><td>{h(parte['unidad'])}</td><td>{h(parte['comandante'])}</td><td>{efectiva}</td><td>{parte['novedades']}</td><td>{disponible}</td>
            <td class="actions-inline">
                <a class="btn small outline" href="/reporte?id={parte['id']}">Ver</a>
                <a class="btn small primary" href="/pdf?id={parte['id']}">PDF</a>
                {delete_action}
            </td>
        </tr>"""

    unit_filter = ""
    if user.get("rol") == "admin":
        unit_filter = f"<label>Unidad<select name=\"unidad_id\">{unidad_options}</select></label>"
    filters = f"""
    <form class="filters" method="GET" action="/historial">
        <label>Seleccione la fecha que desea verificar<input type="date" name="fecha" value="{h(fecha)}"></label>
        {unit_filter}
        <button class="btn outline" type="submit">Filtrar</button>
        <a class="btn primary" href="/pdf-todos?fecha={h(fecha)}&unidad_id={h(unidad_id)}">Descargar todo en PDF</a>
    </form>
    """
    general_report_link = '<a class="btn outline" href="/reporte-general">Reporte General</a>' if user.get("rol") == "admin" else ""
    content = f"""
<section class="panel">
    <div class="section-head"><h2>Reportes de partes</h2><div class="actions-inline">{general_report_link}<a class="btn primary" href="/parte">Nuevo Parte</a></div></div>
    {filters}
    <table class="data-table"><thead><tr><th>Fecha y hora</th><th>Unidad</th><th>Comandante quien reporta</th><th>Fuerza efectiva</th><th>Novedades</th><th>Disponible</th><th>Acci&oacute;n</th></tr></thead><tbody>{rows or '<tr><td colspan="7">No hay partes guardados.</td></tr>'}</tbody></table>
</section>
"""
    return layout(content, user)


def reporte_general_page(user=None, query=""):
    user = user or {}
    if user.get("rol") != "admin":
        return layout("<section class='panel'>No autorizado.</section>", user)
    params = parse_qs(query)
    fecha = params.get("fecha", [""])[0] or datetime.now().strftime("%Y-%m-%d")
    data = reporte_general_data(fecha)

    total_efectiva = sum(data["efectiva"].values())
    total_novedades = sum(data["en_novedad"].values())
    total_disponible = sum(data["disponible"].values())

    unidades_rows = ""
    for item in data["unidades"]:
        unidades_rows += f"""
        <tr>
            <td>{h(item['fecha'])}</td>
            <td>{h(item['hora'])}</td>
            <td>{h(item['unidad'])}</td>
            <td>{h(item['comandante'])}</td>
            <td>{item['efectiva']}</td>
            <td>{item['novedades']}</td>
            <td>{item['disponible']}</td>
        </tr>"""
    if not unidades_rows:
        unidades_rows = "<tr><td colspan='7'>No hay partes guardados para esta fecha.</td></tr>"

    fuerza_rows = "".join(
        f"<tr><td>{label}</td><td>{data['efectiva'][key]}</td><td>{data['en_novedad'][key]}</td><td>{data['disponible'][key]}</td></tr>"
        for key, label in CATEGORIAS.items()
    )
    fuerza_rows += f"<tr class='total-row'><td>Total Distrito</td><td>{total_efectiva}</td><td>{total_novedades}</td><td>{total_disponible}</td></tr>"

    nov_rows = ""
    for novedad in data["novedades"]:
        funcionario = f"{novedad['grado']} {novedad['nombres']} {novedad['apellidos']}"
        nov_rows += f"""
        <tr>
            <td>{h(novedad['unidad_reporta'])}</td>
            <td>{h(novedad['comandante'])}</td>
            <td>{h(novedad['tipo_novedad'])}{('<br><small>' + h(novedad.get('observaciones')) + '</small>') if novedad['tipo_novedad'] == 'Otra novedad' and novedad.get('observaciones') else ''}</td>
            <td>{h(funcionario)}</td>
            <td>{h(novedad.get('cargo') or 'Sin cargo registrado')}</td>
            <td>{h(novedad['unidad_funcionario'])}</td>
            <td>{h(novedad['fecha_inicio'])} {h(novedad['hora_inicio'])}</td>
            <td>{h(novedad['fecha_fin'])} {h(novedad['hora_fin'])}</td>
            <td>{h(novedad['dias_calculados'])}</td>
            <td>{h(novedad.get('solicitud_psi') or '-')}</td>
        </tr>"""
    if not nov_rows:
        nov_rows = "<tr><td colspan='10'>No hay novedades registradas para esta fecha.</td></tr>"

    content = f"""
<section class="panel report-view">
    <div class="section-head">
        <h2>Reporte general del d&iacute;a</h2>
        <a class="btn primary" href="/pdf-general?fecha={h(fecha)}">Descargar PDF general</a>
    </div>
    <form class="filters" method="GET" action="/reporte-general">
        <label>Fecha del reporte<input type="date" name="fecha" value="{h(fecha)}"></label>
        <button class="btn outline" type="submit">Consultar d&iacute;a</button>
    </form>
    <div class="summary-grid">
        <div class="summary-item"><span>Fuerza efectiva total</span><strong>{total_efectiva}</strong></div>
        <div class="summary-item"><span>Total en novedades</span><strong>{total_novedades}</strong></div>
        <div class="summary-item success"><span>Fuerza disponible</span><strong>{total_disponible}</strong></div>
    </div>
    <h2>Partes reportados por unidades</h2>
    <table class="data-table"><thead><tr><th>Fecha</th><th>Hora</th><th>Unidad</th><th>Comandante quien reporta</th><th>Efectiva</th><th>Novedades</th><th>Disponible</th></tr></thead><tbody>{unidades_rows}</tbody></table>
    <h2>Fuerza disponible consolidada</h2>
    <table class="data-table"><thead><tr><th>Categor&iacute;a</th><th>Efectiva</th><th>En novedades</th><th>Disponible</th></tr></thead><tbody>{fuerza_rows}</tbody></table>
    <h2>Novedades del d&iacute;a</h2>
    <table class="data-table"><thead><tr><th>Unidad que reporta</th><th>Comandante</th><th>Tipo</th><th>Funcionario</th><th>Cargo</th><th>Unidad funcionario</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th></tr></thead><tbody>{nov_rows}</tbody></table>
</section>
"""
    return layout(content, user)


def reporte_page(parte_id, user=None):
    user = user or {}
    reporte = reporte_data(parte_id)
    if not reporte:
        return layout("<section class='panel'>Reporte no encontrado.</section>", user)
    parte = reporte["parte"]
    if user.get("rol") == "unidad" and int(parte["unidad_id"]) != int(user.get("unidad_id")):
        return layout("<section class='panel'>No autorizado.</section>", user)

    fuerza_rows = "".join(
        f"<tr><td>{label}</td><td>{reporte['efectiva'][key]}</td><td>{reporte['en_novedad'][key]}</td><td>{reporte['disponible'][key]}</td></tr>"
        for key, label in CATEGORIAS.items()
    )
    nov_rows = ""
    for novedad in reporte["novedades"]:
        funcionario = f"{novedad['grado']} {novedad['nombres']} {novedad['apellidos']}"
        cargo = novedad.get("cargo") or "Sin cargo registrado"
        tipo = f"{h(novedad['tipo_novedad'])}{('<br><small>' + h(novedad.get('observaciones')) + '</small>') if novedad['tipo_novedad'] == 'Otra novedad' and novedad.get('observaciones') else ''}"
        nov_rows += f"<tr><td>{tipo}</td><td>{h(funcionario)}</td><td>{h(cargo)}</td><td>{h(novedad['fecha_inicio'])} {h(novedad['hora_inicio'])}</td><td>{h(novedad['fecha_fin'])} {h(novedad['hora_fin'])}</td><td>{h(novedad['dias_calculados'])}</td><td>{h(novedad.get('solicitud_psi') or '-')}</td></tr>"
    if not nov_rows:
        nov_rows = "<tr><td colspan='7'>Sin novedades registradas.</td></tr>"

    content = f"""
<section class="panel report-view">
    <div class="section-head"><h2>Reporte del parte</h2><a class="btn primary" href="/pdf?id={parte['id']}">Descargar PDF</a></div>
    <div class="report-meta">
        <strong>Unidad:</strong> {h(parte['unidad'])}<br>
        <strong>Fecha:</strong> {h(parte['fecha'])} <strong>Hora:</strong> {h(parte['hora_parte'])}<br>
        <strong>Comandante:</strong> {h(parte['comandante'])}
    </div>
    <h2>Fuerza disponible</h2>
    <table class="data-table"><thead><tr><th>Categor&iacute;a</th><th>Efectiva</th><th>En novedades</th><th>Disponible</th></tr></thead><tbody>{fuerza_rows}</tbody></table>
    <h2>Novedades</h2>
    <table class="data-table"><thead><tr><th>Tipo</th><th>Funcionario</th><th>Cargo</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th></tr></thead><tbody>{nov_rows}</tbody></table>
    <h2>Observaciones</h2>
    <p>{h(parte.get('observaciones') or 'Sin observaciones.')}</p>
</section>
"""
    return layout(content, user)


def diagnostico_data():
    with db() as conn:
        detalle = rows_dict(
            conn.execute(
                """
                SELECT u.nombre, COUNT(f.id) funcionarios
                FROM unidades u
                LEFT JOIN funcionarios f ON f.unidad_id = u.id
                GROUP BY u.id
                ORDER BY u.nombre
                """
            )
        )
        total_funcionarios = conn.execute("SELECT COUNT(*) total FROM funcionarios").fetchone()["total"]
        total_unidades = conn.execute("SELECT COUNT(*) total FROM unidades").fetchone()["total"]
    return {
        "funcionarios": total_funcionarios,
        "unidades": total_unidades,
        "excel": SOURCE_XLSX.exists(),
        "seed": SOURCE_SEED.exists(),
        "motor": "PostgreSQL" if USE_POSTGRES else "SQLite",
        "base_datos": "PostgreSQL conectado por DATABASE_URL" if USE_POSTGRES else str(DB_PATH),
        "carpeta_datos": "No aplica en PostgreSQL" if USE_POSTGRES else str(DATA_DIR),
        "persistencia_render": True if USE_POSTGRES else str(DATA_DIR).replace("\\", "/").startswith("/var/data"),
        "detalle": detalle,
    }


def seguridad_page(user=None):
    user = user or {}
    if user.get("rol") != "admin":
        return layout("<section class='panel'>No autorizado.</section>", user)
    with db() as conn:
        eventos = rows_dict(
            conn.execute(
                """
                SELECT fecha, ip, usuario, evento, detalle
                FROM security_events
                ORDER BY id DESC
                LIMIT 100
                """
            )
        )
    rows = "".join(
        f"<tr><td>{h(e['fecha'])}</td><td>{h(e['ip'])}</td><td>{h(e['usuario'])}</td><td>{h(e['evento'])}</td><td>{h(e['detalle'])}</td></tr>"
        for e in eventos
    )
    content = f"""
<section class="panel">
    <div class="section-head"><h2>Seguridad del sistema</h2><span class="security-badge">{len(eventos)} eventos recientes</span></div>
    <div class="alert info">Aqu&iacute; se registran intentos fallidos, bloqueos temporales, rutas sospechosas y accesos no autorizados.</div>
    <table class="data-table"><thead><tr><th>Fecha</th><th>IP</th><th>Usuario</th><th>Evento</th><th>Detalle</th></tr></thead><tbody>{rows or '<tr><td colspan="5">No hay eventos de seguridad registrados.</td></tr>'}</tbody></table>
</section>
"""
    return layout(content, user)


def ingresos_page(user=None):
    user = user or {}
    if user.get("rol") != "admin":
        return layout("<section class='panel'>No autorizado.</section>", user)
    with db() as conn:
        ingresos = rows_dict(
            conn.execute(
                """
                SELECT fecha, usuario, rol, unidad, ip, equipo_nombre, equipo
                FROM login_logs
                ORDER BY id DESC
                LIMIT 200
                """
            )
    )
    rows = "".join(
        f"<tr><td>{h(i['fecha'])}</td><td>{h(i['usuario'])}</td><td>{h(i['rol'])}</td><td>{h(i['unidad'])}</td><td>{h(i['ip'])}</td><td>{h(i.get('equipo_nombre') or 'No informado')}</td><td>{h(i['equipo'])}</td></tr>"
        for i in ingresos
    )
    content = f"""
<section class="panel">
    <div class="section-head"><h2>Ingresos al sistema</h2><span class="security-badge">{len(ingresos)} ingresos recientes</span></div>
    <div class="alert info">Este registro muestra qui&eacute;n ingres&oacute;, desde qu&eacute; direcci&oacute;n IP, nombre de equipo reportado y navegador usado.</div>
    <table class="data-table"><thead><tr><th>Fecha</th><th>Usuario</th><th>Rol</th><th>Unidad</th><th>IP</th><th>Nombre del equipo</th><th>Navegador / dispositivo</th></tr></thead><tbody>{rows or '<tr><td colspan="7">No hay ingresos registrados.</td></tr>'}</tbody></table>
</section>
"""
    return layout(content, user)



class Handler(BaseHTTPRequestHandler):
    def client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else ""

    def add_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'",
        )

    def is_login_blocked(self, ip):
        now = time.time()
        attempts = [item for item in LOGIN_ATTEMPTS.get(ip, []) if now - item < LOGIN_WINDOW_SECONDS]
        LOGIN_ATTEMPTS[ip] = attempts
        return len(attempts) >= MAX_LOGIN_ATTEMPTS

    def register_login_failure(self, ip):
        now = time.time()
        attempts = [item for item in LOGIN_ATTEMPTS.get(ip, []) if now - item < LOGIN_WINDOW_SECONDS]
        attempts.append(now)
        LOGIN_ATTEMPTS[ip] = attempts

    def valid_post_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        parsed = urlparse(origin)
        return parsed.netloc == host

    def is_logged(self):
        cookie = cookies.SimpleCookie(self.headers.get("Cookie"))
        token = cookie.get("session")
        return token and token.value in SESSIONS

    def current_user(self):
        cookie = cookies.SimpleCookie(self.headers.get("Cookie"))
        token = cookie.get("session")
        if token and token.value in SESSIONS:
            return SESSIONS[token.value]
        return None

    def send_html(self, html, status=200, headers=None):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.add_security_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.add_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_pdf(self, pdf, filename):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.add_security_headers()
        self.end_headers()
        self.wfile.write(pdf)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.add_security_headers()
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if is_suspicious_path(path, parsed.query):
            record_security_event(self.client_ip(), "", "Ruta sospechosa", self.path)
            return self.send_html("No encontrado", 404)
        if path == "/up":
            return self.send_json({"status": "ok"})
        if path.startswith("/static/"):
            return self.static(path)
        if path == "/logout":
            return self.send_html("", 302, {"Set-Cookie": "session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict", "Location": "/"})
        if not self.is_logged() and path != "/":
            return self.redirect("/")
        user = self.current_user()
        if path == "/":
            return self.send_html(login_page() if not self.is_logged() else parte_page(user))
        if path == "/parte":
            return self.send_html(parte_page(user))
        if path == "/novedades":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_html(novedades_page(user, parsed.query))
        if path == "/funcionarios":
            return self.send_html(funcionarios_page(user))
        if path == "/usuarios":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_html(usuarios_page(user))
        if path == "/diagnostico":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_json(diagnostico_data())
        if path == "/api/novedades-vigentes":
            params = parse_qs(parsed.query)
            fecha = params.get("fecha", [""])[0]
            hora = params.get("hora", ["07:00"])[0]
            unidad_id = params.get("unidad_id", [""])[0]
            if user.get("rol") == "unidad" and str(user.get("unidad_id")) != str(unidad_id):
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.send_json({"error": "No autorizado"}, 403)
            return self.send_json({"novedades": novedades_vigentes(fecha, hora, unidad_id)})
        if path == "/historial":
            return self.send_html(historial_page(user, parsed.query))
        if path == "/reporte-general":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_html(reporte_general_page(user, parsed.query))
        if path == "/ingresos":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_html(ingresos_page(user))
        if path == "/seguridad":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            return self.send_html(seguridad_page(user))
        if path == "/reporte":
            parte_id = parse_qs(parsed.query).get("id", [""])[0]
            return self.send_html(reporte_page(parte_id, user))
        if path == "/pdf":
            parte_id = parse_qs(parsed.query).get("id", [""])[0]
            reporte = reporte_data(parte_id)
            if not reporte:
                return self.send_html("Reporte no encontrado", 404)
            if user.get("rol") == "unidad" and int(reporte["parte"]["unidad_id"]) != int(user.get("unidad_id")):
                return self.send_html("No autorizado", 403)
            return self.send_pdf(reporte_pdf(reporte), f"parte_{parte_id}.pdf")
        if path == "/video-fondo":
            return self.send_video()
        if path == "/pdf-todos":
            reportes = reportes_filtrados(parsed.query, user)
            return self.send_pdf(pdf_todos(reportes), "reportes_partes.pdf")
        if path == "/pdf-general":
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", path)
                return self.redirect("/parte")
            fecha = parse_qs(parsed.query).get("fecha", [""])[0] or datetime.now().strftime("%Y-%m-%d")
            return self.send_pdf(pdf_reporte_general(reporte_general_data(fecha)), f"reporte_general_{fecha}.pdf")
        return self.send_html("No encontrado", 404)

    def send_video(self):
        path = VIDEO_FONDO
        if not path.exists():
            return self.send_html("Video no encontrado", 404)
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
                end = min(end, size - 1)
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.add_security_headers()
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self.valid_post_origin():
            record_security_event(self.client_ip(), "", "Origen POST bloqueado", self.headers.get("Origin", ""))
            return self.send_html("No autorizado", 403)
        if parsed.path == "/login":
            ip = self.client_ip()
            form = parse_qs(self.read_body())
            email = form.get("email", [""])[0].strip()
            password = form.get("password", [""])[0]
            if self.is_login_blocked(ip):
                record_security_event(ip, email, "Login bloqueado", "Demasiados intentos fallidos.")
                return self.send_html(login_page("Acceso bloqueado temporalmente por varios intentos fallidos."), 429)
            with db() as conn:
                user = find_user_by_login(conn, email)
            if not user or not verify_password(password, user["password"]):
                self.register_login_failure(ip)
                record_security_event(ip, email, "Login fallido", "Usuario o contrasena incorrectos.")
                return self.send_html(login_page("Credenciales no v&aacute;lidas."))
            LOGIN_ATTEMPTS.pop(ip, None)
            token = secrets.token_urlsafe(24)
            SESSIONS[token] = row_dict(user)
            record_login(row_dict(user), ip, self.headers.get("User-Agent", ""), "Automático")
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
            return self.send_html("", 302, {"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Strict{secure}", "Location": "/parte"})

        if not self.is_logged():
            return self.send_json({"error": "No autenticado"}, 401)

        if parsed.path == "/eliminar-parte":
            user = self.current_user()
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", parsed.path)
                return self.send_html("No autorizado", 403)
            form = parse_qs(self.read_body())
            parte_id = form.get("id", [""])[0]
            with db() as conn:
                conn.execute("DELETE FROM novedades WHERE parte_id = ?", (parte_id,))
                conn.execute("DELETE FROM partes WHERE id = ?", (parte_id,))
            return self.redirect("/historial")

        if parsed.path == "/funcionarios":
            form = parse_qs(self.read_body())
            user = self.current_user()
            unidad_id = user.get("unidad_id") if user.get("rol") == "unidad" else form.get("unidad_id", ["1"])[0]
            with db() as conn:
                conn.execute(
                    "INSERT INTO funcionarios (grado, nombres, apellidos, cargo, categoria, unidad_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        form.get("grado", [""])[0],
                        form.get("nombres", [""])[0],
                        form.get("apellidos", [""])[0],
                        form.get("cargo", [""])[0],
                        form.get("categoria", [""])[0],
                        unidad_id,
                    ),
                )
            return self.redirect("/funcionarios")

        if parsed.path == "/usuarios":
            user = self.current_user()
            if user.get("rol") != "admin":
                record_security_event(self.client_ip(), user.get("email", ""), "Acceso no autorizado", parsed.path)
                return self.send_html("No autorizado", 403)
            form = parse_qs(self.read_body())
            user_id = form.get("id", [""])[0].strip()
            nombre = form.get("nombre", [""])[0].strip()
            email = form.get("email", [""])[0].strip()
            password_plano = form.get("password_plano", [""])[0].strip()
            rol = form.get("rol", ["unidad"])[0].strip()
            unidad_id = form.get("unidad_id", [""])[0].strip() or None
            if rol not in {"admin", "unidad"}:
                rol = "unidad"
            if rol == "admin":
                unidad_id = None
            if not nombre or not email or not password_plano:
                return self.send_html(usuarios_page(user, "Debe diligenciar nombre, usuario y contrase&ntilde;a."), 422)
            try:
                with db() as conn:
                    if user_id:
                        conn.execute(
                            """
                            UPDATE usuarios
                            SET nombre = ?, email = ?, password = ?, password_plano = ?, rol = ?, unidad_id = ?
                            WHERE id = ?
                            """,
                            (nombre, email, hash_password(password_plano), password_plano, rol, unidad_id, user_id),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO usuarios (nombre, email, password, password_plano, rol, unidad_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (nombre, email, hash_password(password_plano), password_plano, rol, unidad_id),
                        )
            except sqlite3.IntegrityError:
                return self.send_html(usuarios_page(user, "No se pudo guardar: ese usuario ya existe."), 422)
            return self.redirect("/usuarios")

        if parsed.path == "/api/partes":
            try:
                data = aplicar_fuerza_efectiva_unidad(aplicar_fecha_hora_actual(json.loads(self.read_body())))
                user = self.current_user()
                novedades = data.get("novedades", [])
                validar_novedades(data, novedades)
                with db() as conn:
                    cur = conn.execute(
                        """
                        INSERT INTO partes (
                            unidad_id, fecha, hora_parte, turno, comandante,
                            fuerza_efectiva_oficiales, fuerza_efectiva_nivel_ejecutivo,
                            fuerza_efectiva_patrulleros, fuerza_efectiva_patrulleros_policia,
                            fuerza_efectiva_auxiliares, observaciones, creado_en
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            data["unidad_id"],
                            data["fecha"],
                            data["hora_parte"],
                            data["turno"],
                            data["comandante"],
                            data["fuerza_efectiva_oficiales"],
                            data["fuerza_efectiva_nivel_ejecutivo"],
                            data["fuerza_efectiva_patrulleros"],
                            data["fuerza_efectiva_patrulleros_policia"],
                            data["fuerza_efectiva_auxiliares"],
                            data.get("observaciones", ""),
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    parte_id = cur.lastrowid
                    for novedad in novedades:
                        dias = calcular_dias(
                            novedad["fecha_inicio"],
                            novedad["hora_inicio"],
                            novedad["fecha_fin"],
                            novedad["hora_fin"],
                        )
                        conn.execute(
                            """
                            INSERT INTO novedades (
                                parte_id, funcionario_id, tipo_novedad, fecha_inicio,
                                hora_inicio, fecha_fin, hora_fin, dias_calculados,
                                observaciones, solicitud_psi, estado
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa')
                            """,
                            (
                                parte_id,
                                novedad["funcionario_id"],
                                novedad["tipo_novedad"],
                                novedad["fecha_inicio"],
                                novedad["hora_inicio"],
                                novedad["fecha_fin"],
                                novedad["hora_fin"],
                                dias,
                                novedad.get("observaciones", ""),
                                novedad.get("solicitud_psi", ""),
                            ),
                        )
                return self.send_json({"message": "Parte guardado correctamente.", "id": parte_id})
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 422)

        return self.send_json({"error": "No encontrado"}, 404)

    def static(self, path):
        file_path = STATIC_DIR / path.replace("/static/", "")
        if not file_path.exists():
            return self.send_html("No encontrado", 404)
        content_types = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        content_type = content_types.get(file_path.suffix.lower(), "application/octet-stream")
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.add_security_headers()
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Sistema Parte de Fuerza en http://0.0.0.0:{port}")
    if USE_POSTGRES:
        print("Base de datos: PostgreSQL conectado por DATABASE_URL")
    else:
        print(f"Base de datos: {DB_PATH}")
        print(f"Carpeta de datos: {DATA_DIR}")
    print(f"Admin: {ADMIN_USER} | Clave: {ADMIN_PASSWORD}")
    print("Unidad ejemplo: ESTACIONPURIFICACION | Clave: PURIFICACION2026")
    server.serve_forever()
