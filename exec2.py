import io
import os
import subprocess
import threading
import requests
from pathlib import Path
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
import shutil

# ──────────────────────── USER CONFIG ──────────────────────────── #
# Utilisation des chemins relatifs en fonction de l'utilisateur actuel
USER_PROFILE = os.getenv("USERPROFILE")
LOCAL_SKIN_CACHE = os.path.join(USER_PROFILE, "Documents", "skin-cache")  # Répertoire pour les skins téléchargés
GITHUB_ZIP_BASE = "https://raw.githubusercontent.com/darkseal-org/lol-skins/main/skins/"  # Base URL des skins GitHub
# ───────────────────────────────────────────────────────────────── #

# ------------------------- Helpers ---------------------------- #
def fetch_json(url: str):
    """Récupère un fichier JSON depuis une URL"""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()

def normalize_cdragon_path(path: str | None) -> str:
    """Formate l'URL pour qu'elle soit correcte, en fonction de la structure de l'API"""
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    # Ajout d'un slash avant si nécessaire
    if not path.startswith('/'):
        path = '/' + path
    return f"https://raw.communitydragon.org/latest{path}"

def check_url_exists(url: str) -> bool:
    """Vérifie si une URL existe en renvoyant True si le code de statut est 200"""
    try:
        response = requests.get(url, timeout=30)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

# --------------------- Data access ---------------------------- #
def get_champion_summary():
    """Récupère la liste des champions via l'API CommunityDragon"""
    return fetch_json("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json")

def get_champion_detail(cid: int):
    """Récupère les détails d'un champion via l'API CommunityDragon"""
    return fetch_json(f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/{cid}.json")

# ------------------- Télécharger le skin -------------------------- #
def download_zip(champion: str, zip_name: str, target_dir: Path):
    """Télécharge un skin ZIP depuis GitHub dans le répertoire cible"""
    url = f"{GITHUB_ZIP_BASE}{champion}/{zip_name}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    # Sauvegarder le fichier ZIP dans le dossier de cache
    target_file = target_dir / f"{zip_name}"
    with open(target_file, 'wb') as f:
        f.write(response.content)
    return target_file

def open_explorer(path: Path):
    """Ouvre l'explorateur de fichiers dans le répertoire spécifié"""
    if os.name == 'nt':  # Si l'OS est Windows
        subprocess.Popen(f'explorer /select,"{path}"')

# --------------------------- GUI ------------------------------ #

class SkinChangerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LoL Skin Changer – Edu v1.2")
        self.geometry("640x600")
        self.resizable(False, False)

        # Data caches
        self.champions: list[dict] = []
        self.current_champion_data: dict | None = None

        # UI variables
        self.var_champion = tk.StringVar()
        self.var_skin = tk.StringVar()
        self.var_chroma = tk.StringVar()

        # Vérification et création du dossier pour les skins téléchargés
        self._ensure_skin_cache_exists()

        self._build_widgets()
        self._populate_champions_async()

    def _ensure_skin_cache_exists(self):
        """Vérifie si le dossier de cache existe, sinon il est créé."""
        Path(LOCAL_SKIN_CACHE).mkdir(parents=True, exist_ok=True)

    # ---------------- UI -----------------
    def _build_widgets(self):
        padding = {"padx": 10, "pady": 5}

        ttk.Label(self, text="Champion :").grid(row=0, column=0, sticky="w", **padding)
        self.cmb_champion = ttk.Combobox(self, textvariable=self.var_champion, state="readonly", width=30)
        self.cmb_champion.grid(row=0, column=1, **padding)
        self.cmb_champion.bind("<<ComboboxSelected>>", self.on_champion_selected)

        ttk.Label(self, text="Skin :").grid(row=1, column=0, sticky="w", **padding)
        self.cmb_skin = ttk.Combobox(self, textvariable=self.var_skin, state="readonly", width=30)
        self.cmb_skin.grid(row=1, column=1, **padding)
        self.cmb_skin.bind("<<ComboboxSelected>>", self.on_skin_selected)

        ttk.Label(self, text="Chroma :").grid(row=2, column=0, sticky="w", **padding)
        self.cmb_chroma = ttk.Combobox(self, textvariable=self.var_chroma, state="readonly", width=30)
        self.cmb_chroma.grid(row=2, column=1, **padding)
        self.cmb_chroma.bind("<<ComboboxSelected>>", self.on_chroma_selected)

        self.btn_download = ttk.Button(self, text="Télécharger", command=self.download_selected_skin)
        self.btn_download.grid(row=3, column=1, sticky="e", **padding)

        self.btn_open_folder = ttk.Button(self, text="Ouvrir le dossier", command=self.open_skin_folder)
        self.btn_open_folder.grid(row=3, column=0, sticky="w", **padding)

        # Image preview
        self.preview_label = ttk.Label(self)
        self.preview_label.grid(row=4, column=0, columnspan=2, **padding)

        self.var_status = tk.StringVar(value="Chargement des champions…")
        ttk.Label(self, textvariable=self.var_status).grid(row=5, column=0, columnspan=2)

    # --------------- Events -------------------
    def on_champion_selected(self, _):
        champ_name = self.var_champion.get()
        if not champ_name:
            return
        champ = next((c for c in self.champions if c["name"] == champ_name), None)
        if champ is None:
            return
        self.var_status.set("Chargement des skins…")
        threading.Thread(target=self._load_champ_data, args=(champ["id"],), daemon=True).start()

    def on_skin_selected(self, _):
        skin_name = self.var_skin.get()
        if not skin_name or not self.current_champion_data:
            return
        skin = next((s for s in self.current_champion_data["skins"] if s["name"] == skin_name), None)
        if skin is None:
            return
        chroma_names = [c["name"] for c in skin.get("chromas", [])]
        self.cmb_chroma["values"] = chroma_names or ["—"]
        self.var_chroma.set(chroma_names[0] if chroma_names else "—")
        self._show_image_async(skin.get("splashPath"))

    def on_chroma_selected(self, _):
        chroma_name = self.var_chroma.get()
        if chroma_name in ("—", ""):
            return
        skin = next((s for s in self.current_champion_data["skins"] if s["name"] == self.var_skin.get()), None)
        if not skin:
            return
        chroma = next((c for c in skin.get("chromas", []) if c["name"] == chroma_name), None)
        if chroma:
            self._show_image_async(chroma.get("splashPath"))

    # --------------- Async tasks -------------------
    def _populate_champions_async(self):
        def task():
            try:
                self.champions = sorted(get_champion_summary(), key=lambda c: c["name"])
                self.cmb_champion["values"] = [c["name"] for c in self.champions]
                self.var_status.set("Choisissez un champion.")
            except Exception as e:
                self.var_status.set(f"Erreur chargement champions : {e}")
        threading.Thread(target=task, daemon=True).start()

    def _load_champ_data(self, cid: int):
        try:
            self.current_champion_data = get_champion_detail(cid)
            skins = [s["name"] for s in self.current_champion_data["skins"] if not s.get("isBase", False)]
            self.cmb_skin["values"] = skins
            self.var_skin.set("")
            self.cmb_chroma["values"] = []
            self.var_chroma.set("")
            self.var_status.set("Sélectionnez un skin.")
        except Exception as e:
            self.var_status.set(f"Erreur chargement skins : {e}")

    # --------------- Télécharger le skin -------------------
    def download_selected_skin(self):
        champ = self.var_champion.get()
        skin = self.var_skin.get()
        if not champ or not skin:
            messagebox.showwarning("Sélection manquante", "Choisissez un champion et un skin.")
            return

        def task():
            try:
                self.var_status.set("Téléchargement…")
                skin_cache_dir = Path(LOCAL_SKIN_CACHE)
                downloaded_file = download_zip(champ, f"{skin}.zip", skin_cache_dir)
                self.var_status.set("Téléchargement terminé.")
                messagebox.showinfo("Succès", f"Le skin '{skin}' a été téléchargé.")
                open_explorer(downloaded_file)
            except Exception as e:
                self.var_status.set("Erreur téléchargement")
                messagebox.showerror("Erreur", str(e))
        threading.Thread(target=task, daemon=True).start()

    def open_skin_folder(self):
        """Ouvre l'explorateur de fichiers dans le répertoire des skins téléchargés"""
        open_explorer(Path(LOCAL_SKIN_CACHE))

    # --------------- Show image -------------------
    def _show_image_async(self, path: str | None):
        url = normalize_cdragon_path(path)
        if not url or not check_url_exists(url):  # Vérifier si l'URL existe réellement
            self.preview_label.configure(text="[Impossible d'afficher l'image]")
            return

        def task():
            try:
                img_data = requests.get(url, timeout=30)
                img_data.raise_for_status()
                img_pil = Image.open(io.BytesIO(img_data.content)).resize((512, 288))
                photo = ImageTk.PhotoImage(img_pil)
                self.preview_label.image = photo  # préserve la référence
                self.preview_label.configure(image=photo, text="")
            except Exception as e:
                # conserve l’image précédente, affiche juste le message en overlay
                self.preview_label.configure(text=f"[Impossible d'afficher] {e}")
        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    SkinChangerApp().mainloop()
