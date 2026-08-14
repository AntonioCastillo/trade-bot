import sqlite3
from pathlib import Path

def main():
    data_dir = Path("data")
    for db_path in data_dir.glob("*.db"):
        print(f"Comprobando base de datos: {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            # Eliminar la clave ath_equity
            conn.execute("DELETE FROM state WHERE key='ath_equity'")
            conn.commit()
            print(f"[OK] ath_equity eliminado de {db_path.name}")
            conn.close()
        except sqlite3.OperationalError as e:
            print(f"[Aviso] No se pudo procesar {db_path.name}: {e} (normal si la tabla state no existe)")

if __name__ == "__main__":
    main()
