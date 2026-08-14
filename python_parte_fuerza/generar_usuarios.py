import sqlite3
from pathlib import Path

base = Path(__file__).parent
conn = sqlite3.connect(base / "parte_fuerza.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT nombre, email, password, rol FROM usuarios ORDER BY rol, nombre"
).fetchall()

lines = ["USUARIOS DEL SISTEMA PARTE DE FUERZA", ""]
for row in rows:
    lines.append(
        f"{row['nombre']} - Usuario: {row['email']} - Clave: {row['password']} - Rol: {row['rol']}"
    )

(base / "usuarios_unidades.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
