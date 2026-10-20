import os
import time
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pytz
import toml 

# --- LECTURE DES SECRETS DEPUIS LE FICHIER TOML ---
secrets_path = ".streamlit/secrets.toml"
if os.path.exists(secrets_path):
    secrets = toml.load(secrets_path)
    ACCESS_TOKEN = secrets.get("META_ACCESS_TOKEN")
    SHEET_URL = secrets.get("GOOGLE_SHEET_URL")
    # GCP info est un dictionnaire dans le TOML
    gcp_info = secrets.get("gcp_service_account", {}) 
    if "private_key" in gcp_info:
        gcp_info["private_key"] = gcp_info["private_key"].replace("\\n", "\n")
else:
    # Fallback au cas où on teste en local
    ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
    SHEET_URL = os.environ.get("GOOGLE_SHEET_URL")
    gcp_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT", "{}"))

INSTAGRAM_ACCOUNT_ID = "17841401400979395"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(gcp_info, scopes=SCOPES)
client = gspread.authorize(creds)

# --- SECURITÉ : CALCUL DE LA DATE ET L'HEURE À PARIS ---
paris_tz = pytz.timezone("Europe/Paris")
now_paris = datetime.now(paris_tz)
current_date_str = now_paris.strftime("%d/%m/%Y")
current_hour = now_paris.hour
# --------------------------------------------------------

if SHEET_URL:
    sheet = client.open_by_url(SHEET_URL).sheet1
    all_rows = sheet.get_all_values()
    
    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 13 and row[12] == "Programmé":
            row_date = row[8].strip()
            row_time = row[9].strip()
            
            # 1. Vérification de la DATE
            if row_date != current_date_str:
                print(f"Ligne {row_idx} ignorée : La date ({row_date}) n'est pas aujourd'hui ({current_date_str}).")
                continue
                
            # 2. Vérification de l'HEURE
            should_publish = False
            if "11" in row_time and current_hour >= 11 and current_hour < 16:
                should_publish = True
            elif "17" in row_time and current_hour >= 17:
                should_publish = True
                
            if not should_publish:
                print(f"Ligne {row_idx} ignorée : Pas l'heure (Prévu à {row_time}, Actuel: {current_hour}h).")
                continue

            # --- PUBLICATION ---
            cloudinary_urls = [u.strip() for u in row[11].split(",") if u.strip()]
            caption = row[7] if len(row) > 7 else ""
            
            print(f"Publication de la ligne {row_idx} autorisée...")
            container_ids = []
            
            for url_val in cloudinary_urls:
                url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media"
                payload = {
                    'media_type': 'VIDEO',
                    'video_url': url_val,
                    'is_carousel_item': 'true',
                    'access_token': ACCESS_TOKEN
                }
                r = requests.post(url, data=payload).json()
                if 'id' in r:
                    container_ids.append(r['id'])
                else:
                    print(f"Error container: {r}")
            
            if container_ids:
                print("Attente de l'encodage Meta (180s pour 10 vidéos)...")
                time.sleep(180) # <-- 3 minutes d'attente
                
                url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media"
                payload = {
                    'media_type': 'CAROUSEL',
                    'children': ','.join(container_ids),
                    'caption': caption,
                    'access_token': ACCESS_TOKEN
                }
                r = requests.post(url, data=payload).json()
                
                if 'id' in r:
                    carousel_id = r['id']
                    print("Attente validation finale carrousel (120s)...")
                    time.sleep(120) # <-- 2 minutes d'attente
                    
                    pub_url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
                    pub_r = requests.post(pub_url, data={'creation_id': carousel_id, 'access_token': ACCESS_TOKEN}).json()
                    
                    if 'id' in pub_r:
                        print(f"Ligne {row_idx} publiée avec succès !")
                        sheet.update_cell(row_idx, 13, "Publié")
                    else:
                        print(f"ERREUR META LORS DE LA PUBLICATION : {pub_r}")