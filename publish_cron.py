import os
import time
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pytz # Pour gérer le fuseau horaire de Paris

ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = "17841401400979395"
SHEET_URL = os.environ.get("GOOGLE_SHEET_URL")

gcp_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(gcp_info, scopes=SCOPES)
client = gspread.authorize(creds)

# --- SECURITÉ : CALCUL DE LA DATE ET L'HEURE À PARIS ---
paris_tz = pytz.timezone("Europe/Paris")
now_paris = datetime.now(paris_tz)
current_date_str = now_paris.strftime("%d/%m/%Y") # Format "17/10/2026"
current_hour = now_paris.hour # Donne un chiffre (ex: 11, 12, 17)
# --------------------------------------------------------

if SHEET_URL:
    sheet = client.open_by_url(SHEET_URL).sheet1
    all_rows = sheet.get_all_values()
    
    for row_idx, row in enumerate(all_rows[1:], start=2):
        # Colonne I (index 8) = Date (ex: 17/10/2026)
        # Colonne J (index 9) = Heure (ex: 11:00 ou 17:00)
        # Colonne M (index 12) = Statut (doit être "Programmé")
        
        if len(row) >= 13 and row[12] == "Programmé":
            row_date = row[8].strip()
            row_time = row[9].strip()
            
            # 1. Vérification de la DATE
            if row_date != current_date_str:
                print(f"Ligne {row_idx} ignorée : La date de programmation ({row_date}) ne correspond pas à aujourd'hui ({current_date_str}).")
                continue # On passe à la ligne suivante
                
            # 2. Vérification de l'HEURE (Simplifiée pour 11h ou 17h)
            should_publish = False
            if "11" in row_time and current_hour >= 11 and current_hour < 16:
                should_publish = True
            elif "17" in row_time and current_hour >= 17:
                should_publish = True
                
            if not should_publish:
                print(f"Ligne {row_idx} ignorée : Il n'est pas encore l'heure de publier (Post prévu à {row_time}, heure actuelle Paris: {current_hour}h).")
                continue # On passe à la ligne suivante

            # --- SI LA DATE ET L'HEURE SONT VALIDES, ON PUBLIE ---
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
                print("Attente de l'encodage Meta (30s)...")
                time.sleep(30) # On laisse un peu plus de temps de sécurité à Meta
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
                    print("Attente validation finale carrousel (20s)...")
                    time.sleep(20)
                    pub_url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
                    pub_r = requests.post(pub_url, data={'creation_id': carousel_id, 'access_token': ACCESS_TOKEN}).json()
                    
                    if 'id' in pub_r:
                        print(f"Ligne {row_idx} publiée avec succès !")
                        sheet.update_cell(row_idx, 13, "Publié")