import json
import html
import os
import re
import secrets
import sqlite3
import struct
import unicodedata
import zlib
from datetime import datetime
from functools import lru_cache
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "parte_fuerza.db"
STATIC_DIR = BASE_DIR / "static"
SOURCE_XLSX = BASE_DIR.parent / "personal del distrito.xlsx"
SOURCE_SEED = BASE_DIR / "personal_seed.json"
VIDEO_FONDO = Path(r"C:\Users\juanc\Documents\JUAN POLICIA\210797_WxilRM9i.mp4")
SESSIONS = {}

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


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
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
            """
        )

        ensure_column(conn, "usuarios", "rol", "TEXT NOT NULL DEFAULT 'unidad'")
        ensure_column(conn, "usuarios", "unidad_id", "INTEGER")
        ensure_column(conn, "funcionarios", "cedula", "TEXT")
        ensure_column(conn, "funcionarios", "cargo", "TEXT")
        ensure_column(conn, "novedades", "solicitud_psi", "TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unidades_nombre ON unidades(nombre)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_funcionarios_cedula ON funcionarios(cedula)")

        conn.execute(
            "INSERT OR IGNORE INTO usuarios (id, nombre, email, password, rol, unidad_id) VALUES (1, 'Administrador', 'admin', 'admin2026', 'admin', NULL)"
        )
        conn.execute(
            "UPDATE usuarios SET nombre = 'Administrador', email = 'admin', password = 'admin2026', rol = 'admin', unidad_id = NULL WHERE id = 1"
        )
        conn.execute(
            "INSERT OR IGNORE INTO unidades (id, nombre, estado) VALUES (1, 'Distrito Cuatro de Polic&iacute;a Purificación', 'activa')"
        )

        import_excel_personal(conn)

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
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_dict(row):
    return dict(row) if row else None


def rows_dict(rows):
    return [dict(row) for row in rows]


def h(value):
    return html.escape(str(value or ""))


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
    conn.execute("DELETE FROM funcionarios")
    conn.execute("DELETE FROM usuarios WHERE rol = 'unidad'")
    for unidad in unidades:
        conn.execute("INSERT OR IGNORE INTO unidades (nombre, estado) VALUES (?, 'activa')", (unidad,))

    placeholders = ",".join("?" for _ in unidades)
    if unidades:
        conn.execute(
            f"DELETE FROM unidades WHERE nombre NOT IN ({placeholders}) AND id NOT IN (SELECT unidad_id FROM partes)",
            unidades,
        )

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
            INSERT INTO funcionarios (cedula, grado, nombres, apellidos, categoria, unidad_id, cargo, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')
            ON CONFLICT(cedula) DO UPDATE SET
                grado = excluded.grado,
                nombres = excluded.nombres,
                apellidos = excluded.apellidos,
                categoria = excluded.categoria,
                unidad_id = excluded.unidad_id,
                cargo = excluded.cargo,
                estado = 'activo'
            """,
            (cedula, grado, nombres, apellidos, categoria, unidad_ids[unidad], row.get("CARGO", "")),
        )

    for unidad in unidades:
        username, password = unit_credentials(unidad)
        conn.execute(
            """
            INSERT INTO usuarios (nombre, email, password, rol, unidad_id)
            VALUES (?, ?, ?, 'unidad', ?)
            ON CONFLICT(email) DO UPDATE SET nombre = excluded.nombre, password = excluded.password, rol = 'unidad', unidad_id = excluded.unidad_id
            """,
            (unidad, username, password, unidad_ids[unidad]),
        )


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
                SELECT n.*, f.grado, f.nombres, f.apellidos, f.categoria, u.nombre unidad_funcionario
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


def reportes_filtrados(query):
    params = parse_qs(query)
    fecha_desde = params.get("fecha_desde", [""])[0]
    fecha_hasta = params.get("fecha_hasta", [""])[0]
    unidad_id = params.get("unidad_id", [""])[0]
    where = []
    values = []
    if unidad_id:
        where.append("unidad_id = ?")
        values.append(unidad_id)
    if fecha_desde:
        where.append("fecha >= ?")
        values.append(fecha_desde)
    if fecha_hasta:
        where.append("fecha <= ?")
        values.append(fecha_hasta)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        ids = [row["id"] for row in conn.execute(f"SELECT id FROM partes {where_sql} ORDER BY fecha DESC, id DESC", values)]
    return [reporte_data(parte_id) for parte_id in ids if reporte_data(parte_id)]


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
            novedad["tipo_novedad"],
            funcionario,
            CATEGORIAS.get(novedad["categoria"], novedad["categoria"]),
            f"{novedad['fecha_inicio']} {novedad['hora_inicio']}",
            f"{novedad['fecha_fin']} {novedad['hora_fin']}",
            novedad["dias_calculados"],
            novedad.get("solicitud_psi") or "-",
        ])
    if not nov_rows:
        nov_rows = [["Sin novedades registradas.", "", "", "", "", "", ""]]
    pdf.table(["Tipo", "Funcionario", "Categor\u00eda", "Inicio", "Fin", "D\u00edas", "PSI"], nov_rows, [80, 150, 80, 80, 80, 45, 45], hs=10, cs=10)

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


def layout(content, user=None):
    user = user or {}
    unit_name = get_unit_name(user.get("unidad_id")) if user.get("rol") == "unidad" else "ADMINISTRADOR GENERAL"
    report_link = '<a class="nav-link" href="/historial"><span class="nav-ico">RP</span><span>Reportes de Unidades</span></a>' if user.get("rol") == "admin" else ""
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
        <a class="nav-link" href="/parte#novedades"><span class="nav-ico">NV</span><span>Novedades</span></a>
        <a class="nav-link" href="/funcionarios"><span class="nav-ico">FN</span><span>Funcionarios</span></a>
        {report_link}
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
        <img class="login-logo" src="/static/logo_policia.png" alt="Polic&iacute;a Nacional">
        <h1>POLIC&Iacute;A NACIONAL</h1>
        <p>Sistema Parte de Fuerza</p>
        {alert}
        <label>Usuario<input type="text" name="email" value="" autocomplete="username" required></label>
        <label>Contrase&ntilde;a<input type="password" name="password" required></label>
        <button class="btn primary full">Ingresar</button>
    </form>
</body>
</html>"""

def parte_page(user=None):
    user = user or {}
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

    unidad_options = "<option value='' selected>Seleccione unidad...</option>"
    unidad_options += "".join(f"<option value='{u['id']}'>{h(u['nombre'])}</option>" for u in unidades)
    tipos_options = "".join(f"<option>{tipo}</option>" for tipo in TIPOS_NOVEDAD)
    report_button = '<a class="btn outline full" href="/historial">Reportes Guardados</a>' if user.get("rol") == "admin" else ""

    content = f"""
<form id="parteForm" class="parte-form">
    <section class="panel general-panel">
        <h2>Informaci&oacute;n general</h2>
        <div class="grid four">
            <label>Unidad<select id="unidad_id">{unidad_options}</select></label>
            <label>Comandante que reporta<input id="comandante" placeholder="Ejemplo: Cap. YESICA LICETH GOMEZ TRUJILLO"></label>
            <label>Fecha del parte<input type="date" id="fecha" value="2026-08-05"></label>
            <label>Hora del parte<input type="time" id="hora_parte" value="12:00"></label>
        </div>
    </section>

    <div class="grid main-grid">
        <section class="panel">
            <h2>1. Fuerza efectiva <small>(total unidad)</small></h2>
            <table class="data-table">
                <thead><tr><th>Categor&iacute;a</th><th>Cantidad</th></tr></thead>
                <tbody>
                    <tr><td>Oficiales</td><td><input class="qty efectiva" id="efectiva_oficiales" type="number" min="0" value="0"></td></tr>
                    <tr><td>Nivel Ejecutivo</td><td><input class="qty efectiva" id="efectiva_nivel_ejecutivo" type="number" min="0" value="0"></td></tr>
                    <tr><td>Patrulleros</td><td><input class="qty efectiva" id="efectiva_patrulleros" type="number" min="0" value="0"></td></tr>
                    <tr><td>Patrulleros de Polic&iacute;a</td><td><input class="qty efectiva" id="efectiva_patrulleros_policia" type="number" min="0" value="0"></td></tr>
                    <tr><td>Auxiliares de Polic&iacute;a</td><td><input class="qty efectiva" id="efectiva_auxiliares" type="number" min="0" value="0"></td></tr>
                </tbody>
                <tfoot><tr><th>Total fuerza efectiva</th><th id="total_efectiva">0</th></tr></tfoot>
            </table>
        </section>

        <div class="flow-arrow no-mobile"><span>OK</span><small>C&aacute;lculo<br>Autom&aacute;tico</small></div>

        <section class="panel" id="novedades">
            <div class="section-head"><h2>2. Novedades del personal</h2><button type="button" class="btn primary" id="toggleNovedad">+ Registrar Novedad</button></div>
            <table class="data-table">
                <thead><tr><th>Tipo</th><th>Funcionario</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th><th>Acci&oacute;n</th></tr></thead>
                <tbody id="novedadesBody"></tbody>
                <tfoot><tr><th colspan="4">Total funcionarios en novedades:</th><th id="totalNovedadesTabla">0</th><th></th><th></th></tr></tfoot>
            </table>

            <div class="subpanel" id="novedadForm">
                <h3>Registrar novedad</h3>
                <div class="grid three">
                    <label>Unidad<select id="unidad_novedad_id">{unidad_options}</select></label>
                    <label>Tipo de novedad<select id="tipo_novedad"><option value="">Seleccione...</option>{tipos_options}</select></label>
                    <label>Funcionario<select id="funcionario_id"><option value="">Seleccione...</option></select></label>
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
                <div class="grid four compact">
                    <label>Fecha inicio<input type="date" id="fecha_inicio" value="2026-08-05"></label>
                    <label>Hora inicio<input type="time" id="hora_inicio" value="06:00"></label>
                    <label>Fecha fin<input type="date" id="fecha_fin" value="2026-08-05"></label>
                    <label>Hora fin<input type="time" id="hora_fin" value="18:00"></label>
                </div>
                <div class="novedad-actions">
                    <div class="duration-box">D&iacute;as calculados: <strong id="diasTexto">0 d&iacute;as</strong></div>
                    <button type="button" class="btn primary" id="guardarNovedad">Guardar Novedad</button>
                </div>
                <div class="alert info">El c&aacute;lculo de d&iacute;as se realiza autom&aacute;ticamente.</div>
            </div>
        </section>
    </div>

    <div class="grid lower-grid">
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
            <button class="btn primary full" type="submit">Guardar Parte de Fuerza</button>
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
        f"<tr><td>{f['grado']}</td><td>{f['nombres']} {f['apellidos']}</td><td>{CATEGORIAS[f['categoria']]}</td><td>{f['unidad']}</td><td>{f['estado']}</td></tr>"
        for f in funcionarios
    )
    unidad_options = "".join(f"<option value='{u['id']}'>{h(u['nombre'])}</option>" for u in unidades)
    categoria_options = "".join(f"<option value='{k}'>{v}</option>" for k, v in CATEGORIAS.items())

    content = f"""
<section class="panel">
    <h2>Registrar funcionario</h2>
    <form method="POST" action="/funcionarios" class="grid six">
        <input name="grado" placeholder="Grado" required>
        <input name="nombres" placeholder="Nombres" required>
        <input name="apellidos" placeholder="Apellidos" required>
        <select name="categoria">{categoria_options}</select>
        <select name="unidad_id">{unidad_options}</select>
        <button class="btn primary">Guardar</button>
    </form>
</section>
<section class="panel">
    <h2>Funcionarios</h2>
    <table class="data-table"><thead><tr><th>Grado</th><th>Funcionario</th><th>Categor&iacute;a</th><th>Unidad</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""
    return layout(content, user)


def historial_page(user=None, query=""):
    user = user or {}
    params = parse_qs(query)
    fecha_desde = params.get("fecha_desde", [""])[0]
    fecha_hasta = params.get("fecha_hasta", [""])[0]
    unidad_id = params.get("unidad_id", [""])[0]

    where = []
    values = []
    if user.get("rol") == "unidad":
        where.append("p.unidad_id = ?")
        values.append(user.get("unidad_id"))
    elif unidad_id:
        where.append("p.unidad_id = ?")
        values.append(unidad_id)
    if fecha_desde:
        where.append("p.fecha >= ?")
        values.append(fecha_desde)
    if fecha_hasta:
        where.append("p.fecha <= ?")
        values.append(fecha_hasta)

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
        rows += f"""
        <tr>
            <td>{h(parte['fecha'])}</td><td>{h(parte['unidad'])}</td><td>{efectiva}</td><td>{parte['novedades']}</td><td>{disponible}</td>
            <td class="actions-inline">
                <a class="btn small outline" href="/reporte?id={parte['id']}">Ver</a>
                <a class="btn small primary" href="/pdf?id={parte['id']}">PDF</a>
                <form method="POST" action="/eliminar-parte" onsubmit="return confirm('¿Eliminar este parte y sus novedades?')">
                    <input type="hidden" name="id" value="{parte['id']}">
                    <button class="btn small danger" type="submit">Eliminar</button>
                </form>
            </td>
        </tr>"""

    filters = f"""
    <form class="filters" method="GET" action="/historial">
        <label>Desde<input type="date" name="fecha_desde" value="{h(fecha_desde)}"></label>
        <label>Hasta<input type="date" name="fecha_hasta" value="{h(fecha_hasta)}"></label>
        <label>Unidad<select name="unidad_id">{unidad_options}</select></label>
        <button class="btn outline" type="submit">Filtrar</button>
        <a class="btn primary" href="/pdf-todos?fecha_desde={h(fecha_desde)}&fecha_hasta={h(fecha_hasta)}&unidad_id={h(unidad_id)}">Descargar todo en PDF</a>
    </form>
    """
    content = f"""
<section class="panel">
    <div class="section-head"><h2>Reportes de partes</h2><a class="btn primary" href="/parte">Nuevo Parte</a></div>
    {filters}
    <table class="data-table"><thead><tr><th>Fecha</th><th>Unidad</th><th>Fuerza efectiva</th><th>Novedades</th><th>Disponible</th><th>Acci&oacute;n</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No hay partes guardados.</td></tr>'}</tbody></table>
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
        nov_rows += f"<tr><td>{h(novedad['tipo_novedad'])}</td><td>{h(funcionario)}</td><td>{h(CATEGORIAS.get(novedad['categoria'], novedad['categoria']))}</td><td>{h(novedad['fecha_inicio'])} {h(novedad['hora_inicio'])}</td><td>{h(novedad['fecha_fin'])} {h(novedad['hora_fin'])}</td><td>{h(novedad['dias_calculados'])}</td><td>{h(novedad.get('solicitud_psi') or '-')}</td></tr>"
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
    <table class="data-table"><thead><tr><th>Tipo</th><th>Funcionario</th><th>Categor&iacute;a</th><th>Inicio</th><th>Fin</th><th>D&iacute;as</th><th>PSI</th></tr></thead><tbody>{nov_rows}</tbody></table>
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
        "detalle": detalle,
    }



class Handler(BaseHTTPRequestHandler):
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
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_pdf(self, pdf, filename):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'inline; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(pdf)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/up":
            return self.send_json({"status": "ok"})
        if path == "/diagnostico":
            return self.send_json(diagnostico_data())
        if path.startswith("/static/"):
            return self.static(path)
        if path == "/logout":
            return self.send_html("", 302, {"Set-Cookie": "session=; Max-Age=0; Path=/", "Location": "/"})
        if not self.is_logged() and path != "/":
            return self.redirect("/")
        user = self.current_user()
        if path == "/":
            return self.send_html(login_page() if not self.is_logged() else parte_page(user))
        if path == "/parte":
            return self.send_html(parte_page(user))
        if path == "/funcionarios":
            return self.send_html(funcionarios_page(user))
        if path == "/historial":
            if user.get("rol") != "admin":
                return self.redirect("/parte")
            return self.send_html(historial_page(user, parsed.query))
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
            if user.get("rol") != "admin":
                return self.redirect("/parte")
            reportes = reportes_filtrados(parsed.query)
            return self.send_pdf(pdf_todos(reportes), "reportes_partes.pdf")
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
        if parsed.path == "/login":
            form = parse_qs(self.read_body())
            email = form.get("email", [""])[0].strip().upper()
            if email == "ADMIN":
                email = "admin"
            password = form.get("password", [""])[0]
            with db() as conn:
                user = conn.execute("SELECT * FROM usuarios WHERE email = ? AND password = ?", (email, password)).fetchone()
            if not user:
                return self.send_html(login_page("Credenciales no v&aacute;lidas."))
            token = secrets.token_urlsafe(24)
            SESSIONS[token] = row_dict(user)
            return self.send_html("", 302, {"Set-Cookie": f"session={token}; Path=/; HttpOnly", "Location": "/parte"})

        if not self.is_logged():
            return self.send_json({"error": "No autenticado"}, 401)

        if parsed.path == "/eliminar-parte":
            user = self.current_user()
            if user.get("rol") != "admin":
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
                    "INSERT INTO funcionarios (grado, nombres, apellidos, categoria, unidad_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        form.get("grado", [""])[0],
                        form.get("nombres", [""])[0],
                        form.get("apellidos", [""])[0],
                        form.get("categoria", [""])[0],
                        unidad_id,
                    ),
                )
            return self.redirect("/funcionarios")

        if parsed.path == "/api/partes":
            try:
                data = json.loads(self.read_body())
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
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Sistema Parte de Fuerza en http://0.0.0.0:{port}")
    print("Admin: admin | Clave: admin2026")
    print("Unidad ejemplo: ESTACIONPURIFICACION | Clave: PURIFICACION2026")
    server.serve_forever()
