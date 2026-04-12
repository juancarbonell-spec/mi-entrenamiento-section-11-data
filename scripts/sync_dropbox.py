"""
sync_dropbox.py
===============
Descarga desde Dropbox los .fit nuevos que aún no están en FIT/ del repo.
El token viene del Secret DROPBOX_TOKEN de GitHub.

Dependencias: requests (sin librerías extra)
"""

import os
import requests
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
DROPBOX_FOLDER = "/fit"       # ruta en Dropbox (en minúsculas)
LOCAL_FIT_DIR  = Path("FIT")
# ─────────────────────────────────────────────────────────────────────────────


def listar_fits(token: str) -> list[dict]:
    """Lista todos los .fit dentro de la carpeta de Dropbox."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"path": DROPBOX_FOLDER, "limit": 2000}

    r = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers=headers,
        json=payload,
    )
    if r.status_code != 200:
        raise Exception(f"Error listando Dropbox: {r.status_code} {r.text}")

    entries = r.json().get("entries", [])
    return [e for e in entries if e[".tag"] == "file" and e["name"].lower().endswith(".fit")]


def descargar_fit(token: str, path_dropbox: str, dest: Path):
    """Descarga un archivo de Dropbox."""
    headers = {
        "Authorization":   f"Bearer {token}",
        "Dropbox-API-Arg": f'{{"path": "{path_dropbox}"}}',
    }
    r = requests.post(
        "https://content.dropboxapi.com/2/files/download",
        headers=headers,
        stream=True,
    )
    if r.status_code != 200:
        raise Exception(f"Error descargando {path_dropbox}: {r.status_code} {r.text}")

    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def main():
    token = os.environ.get("DROPBOX_TOKEN")
    if not token:
        raise EnvironmentError("Secret DROPBOX_TOKEN no encontrado.")

    LOCAL_FIT_DIR.mkdir(exist_ok=True)

    # FIT en Dropbox
    print("Conectando con Dropbox...")
    en_dropbox = listar_fits(token)
    print(f"FIT en Dropbox  : {len(en_dropbox)}")

    # FIT ya en el repo
    ya_en_repo = {f.name for f in LOCAL_FIT_DIR.glob("*.fit")}
    print(f"FIT en repo     : {len(ya_en_repo)}")

    # Solo los nuevos
    nuevos = [f for f in en_dropbox if f["name"] not in ya_en_repo]
    print(f"FIT nuevos      : {len(nuevos)}")

    if not nuevos:
        print("\nTodo al dia. Nada que descargar.")
        return

    for i, archivo in enumerate(sorted(nuevos, key=lambda x: x["name"]), 1):
        dest = LOCAL_FIT_DIR / archivo["name"]
        print(f"  [{i}/{len(nuevos)}] {archivo['name']}...")
        descargar_fit(token, archivo["path_lower"], dest)
        print(f"         OK")

    print(f"\n{len(nuevos)} archivo(s) descargado(s).")


if __name__ == "__main__":
    main()
