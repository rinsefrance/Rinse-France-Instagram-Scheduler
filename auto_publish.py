import gspread
from google.oauth2.service_account import Credentials
import requests
import time
import toml
import os
import pytz
from datetime import datetime

print("Démarrage du script de publication automatique...")

# 1. Chargement des secrets
try:
    with open(".streamlit/secrets.toml", "r") as f:
        secrets = toml.load(f)
except FileNotFoundError:
    print("Erreur : Fichier de secrets introuvable.")
    exit(1)

META_ACCESS_TOKEN = secrets["META_ACCESS_TOKEN"]
INSTAGRAM_ACCOUNT_ID = "17841401400979395"
SHEET_URL = secrets.get("GOOGLE_SHEET_URL", "")

if not SHEET_URL:
    print("Erreur : GOOGLE_SHEET_URL manquant dans les secrets.")
    exit(1)

# 2. Connexion au Google Sheet
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
gcp_dict = secrets["gcp_service_account"]
gcp_dict["private_key"] = gcp_dict["private_key"].replace("\\n", "\n")
creds = Credentials.from_service_account_info(gcp_dict, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_url(SHEET_URL).sheet1
all_data = sheet.get_all_values()

# 3. Récupérer l'heure actuelle à Paris
paris_tz = pytz.timezone("Europe/Paris")
now = datetime.now(paris_tz)
current_hour = now.hour # ex: 11 ou 17
print(f"Heure actuelle (Paris) : {now.strftime('%H:%M')} (Heure: {current_hour}h)")

# 4. Parcourir les lignes du tableau
for row_idx, row in enumerate(all_data):
    row_number = row_idx + 1
    if len(row) < 13:
        continue
        
    status = row[12].strip() # Colonne 13 (M)
    if status == "Programmé":
        caption = row[7] if len(row) > 7 else ""
        schedule_time = row[9].lower() if len(row) > 9 else ""
        urls_str = row[11]
        
        # On vérifie si l'heure du serveur correspond à l'heure programmée (ex: "11" est dans "11h")
        if str(current_hour) not in schedule_time and schedule_time != "":
            print(f"Ligne {row_number} ignorée : prévue pour {schedule_time}, il est actuellement {current_hour}h.")
            continue

        cloudinary_urls = [u.strip() for u in urls_str.split(',') if u.strip()]
        if not cloudinary_urls:
            continue
            
        print(f"\n--- Publication de la ligne {row_number} ---")
        try:
            # Création des conteneurs
            container_ids = []
            for url_val in cloudinary_urls:
                payload = {'media_type': 'VIDEO', 'video_url': url_val, 'is_carousel_item': 'true', 'access_token': META_ACCESS_TOKEN}
                r = requests.post(f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media", data=payload).json()
                if 'id' in r: container_ids.append(r['id'])
                else: raise Exception(f"Erreur création: {r}")
            
            # Validation des vidéos par Meta (Polling actif)
            print("⏳ Attente validation vidéos par Meta...")
            for c_id in container_ids:
                c_status, retries = "IN_PROGRESS", 0
                while c_status == "IN_PROGRESS" and retries < 30:
                    time.sleep(5)
                    res = requests.get(f"https://graph.facebook.com/v20.0/{c_id}?fields=status_code&access_token={META_ACCESS_TOKEN}").json()
                    c_status = res.get("status_code", "ERROR")
                    retries += 1
                if c_status != "FINISHED": raise Exception(f"Vidéo {c_id} échouée ({c_status}).")
            
            # Création carrousel
            print("Création du carrousel principal...")
            payload = {'media_type': 'CAROUSEL', 'children': ','.join(container_ids), 'caption': caption, 'access_token': META_ACCESS_TOKEN}
            r = requests.post(f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media", data=payload).json()
            if 'id' not in r: raise Exception(f"Erreur carrousel: {r}")
            carousel_id = r['id']
            
            # Validation finale du carrousel complet par Meta
            print("⏳ Attente validation finale du carrousel complet...")
            c_status, retries = "IN_PROGRESS", 0
            while c_status == "IN_PROGRESS" and retries < 30:
                time.sleep(5)
                res = requests.get(f"https://graph.facebook.com/v20.0/{carousel_id}?fields=status_code&access_token={META_ACCESS_TOKEN}").json()
                c_status = res.get("status_code", "ERROR")
                retries += 1
            if c_status != "FINISHED": raise Exception(f"Carrousel échoué ({c_status}).")
                
            # Publication
            print("🚀 Publication en cours sur le compte Instagram Rinse France...")
            pub_payload = {'creation_id': carousel_id, 'access_token': META_ACCESS_TOKEN}
            pub_r = requests.post(f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media_publish", data=pub_payload).json()
            
            if 'id' in pub_r:
                print(f"✅ Publication réussie ! (ID: {pub_r['id']})")
                sheet.update_cell(row_number, 13, "Publié")
            else:
                raise Exception(f"Erreur publication: {pub_r}")
                
        except Exception as e:
            print(f"❌ Erreur sur la ligne {row_number}: {e}")
            sheet.update_cell(row_number, 13, f"Erreur de publication")

print("\nFin du script.")