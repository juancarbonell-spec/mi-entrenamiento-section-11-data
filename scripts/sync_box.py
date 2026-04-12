"""
sync_box.py
===========
Descarga desde Box los .fit nuevos que aún no están en FIT/ del repo.
Usa Client Credentials Grant — las credenciales vienen de los Secrets de GitHub.

Dependencias: requests (ya instalado normalmente)
"""

import os
import requests
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOX_FOLDER_PATH = ["health sync actividades"]   # ruta desde la raíz de Box
LOCAL_FIT_DIR   = Path("FIT")
# ─────────────────────────────────────────────────────────────────────────────


def get_token(client_id: str, client_secret: str) -> str:
    """Obtiene un access token via Client Credentials Grant."""
    # Paso 1: token inicial para saber el user_id
    r = requests.post("https://api.box.com/oauth2/token", data={
        "grant_type":       "client_credentials",
        "client_id":        client_id,
        "client_secret":    client_secret,
        "box_subject_type": "enterprise",
        "box_subject_id":   "0",
    })

    # Si falla enterprise, intentamos como user
    if r.status_code != 200:
        # Obtener user_id con token temporal
        r2 = requests.post("https://api.box.com/oauth2/token", data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        })
        if r2.status_code != 200:
            raise Exception(f"Error autenticando en Box: {r2.status_code} {r2.text}")
        token_tmp = r2.json()["access_token"]

        # Obtener user_id
        me = requests.get(
            "https://api.box.com/2.0/users/me",
            headers={"Authorization": f"Bearer {token_tmp}"}
        ).json()
        user_id = me["id"]

        # Token final como user
        r3 = requests.post("https://api.box.com/oauth2/token", data={
            "grant_type":       "client_credentials",
            "client_id":        client_id,
            "client_secret":    client_secret,
            "box_subject_type": "user",
            "box_subject_id":   user_id,
        })
        if r3.status_code != 200:
            raise Exception(f"Error obteniendo token de usuario: {r3.status_code} {r3.text}")
        return r3.json()["access_token"]

    return r.json()["access_token"]


def buscar_carpeta(token: str, nombre: str, parent_id: str = "0") -> str:
    """Devuelve el ID de una carpeta por nombre dentro de parent_id."""
    headers = {"Authorization": f"Bearer {token}"}
    url     = f"https://api.box.com/2.0/folders/{parent_id}/items"
    params  = {"fields": "id,name,type", "limit": 1000}

    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        raise Exception(f"Error listando carpeta {parent_id}: {r.status_code} {r.text}")

    for item in r.json().get("entries", []):
        if item["type"] == "folder" and item["name"].lower() == nombre.lower():
            return item["id"]

    raise Exception(f"Carpeta '{nombre}' no encontrada dentro de '{parent_id}'")


def listar_fits(token: str, folder_id: str) -> list[dict]:
    """Lista todos los .fit dentro de una carpeta de Box."""
    headers = {"Authorization": f"Bearer {token}"}
    url     = f"https://api.box.com/2.0/folders/{folder_id}/items"
    params  = {"fields": "id,name,type", "limit": 1000}

    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        raise Exception(f"Error listando FITs: {r.status_code} {r.text}")

    return [
        item for item in r.json().get("entries", [])
        if item["type"] == "file" and item["name"].lower().endswith(".fit")
    ]


def descargar_fit(token: str, file_id: str, dest: Path):
    """Descarga un archivo de Box."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"https://api.box.com/2.0/files/{file_id}/content",
        headers=headers,
        stream=True,
        allow_redirects=True,
    )
    if r.status_code != 200:
        raise Exception(f"Error descargando {file_id}: {r.status_code}")

    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def main():
    client_id     = os.environ["BOX_CLIENT_ID"]
    client_secret = os.environ["BOX_CLIENT_SECRET"]

    LOCAL_FIT_DIR.mkdir(exist_ok=True)

    print("Autenticando en Box...")
    token = get_token(client_id, client_secret)
    print("OK")

    # Navegar hasta la carpeta de los FIT
    folder_id = "0"
    for nombre in BOX_FOLDER_PATH:
        print(f"Buscando carpeta '{nombre}'...")
        folder_id = buscar_carpeta(token, nombre, folder_id)
        print(f"  ID: {folder_id}")

    # FIT en Box
    en_box = listar_fits(token, folder_id)
    print(f"\nFIT en Box      : {len(en_box)}")

    # FIT ya en el repo
    ya_en_repo = {f.name for f in LOCAL_FIT_DIR.glob("*.fit")}
    print(f"FIT en repo     : {len(ya_en_repo)}")

    # Solo los nuevos
    nuevos = [f for f in en_box if f["name"] not in ya_en_repo]
    print(f"FIT nuevos      : {len(nuevos)}")

    if not nuevos:
        print("\nTodo al dia. Nada que descargar.")
        return

    for i, archivo in enumerate(sorted(nuevos, key=lambda x: x["name"]), 1):
        dest = LOCAL_FIT_DIR / archivo["name"]
        print(f"  [{i}/{len(nuevos)}] {archivo['name']}...")
        descargar_fit(token, archivo["id"], dest)
        print(f"         OK")

    print(f"\n{len(nuevos)} archivo(s) descargado(s).")


if __name__ == "__main__":
    main()
