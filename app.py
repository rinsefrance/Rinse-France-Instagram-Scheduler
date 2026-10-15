import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.auth.transport.requests
import requests
import ffmpeg
import os
import time
import cloudinary
import cloudinary.uploader
import gc  # Ajout du Garbage Collector pour purger la mémoire

# --- CONFIGURATION META & CLOUDINARY API ---
ACCESS_TOKEN = st.secrets.get("META_ACCESS_TOKEN", "EAAfC6VhaxUoBO9ZB1ZC4R4ZA93ZBH2R5L7yZAUc6XqZB3L9k8YmS8Xp3qL0yX1W9ZBZCQv8yZB92X8V8yZB0ZCZCQ9v8yZB8ZAZC7X9ZBZBQ0yX1W9ZBZCQv8yZB92X8V8yZB0ZCZCQ9v8yZB8ZAZC7X9ZBZBQ")
FACEBOOK_PAGE_ID = "687289131283875"
INSTAGRAM_ACCOUNT_ID = "17841401400979395"

if "CLOUDINARY_CLOUD_NAME" in st.secrets:
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"]
    )

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

if "gcp_service_account" in st.secrets:
    gcp_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in gcp_dict:
        gcp_dict["private_key"] = gcp_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(gcp_dict, scopes=SCOPES)
else:
    st.error("Missing [gcp_service_account] in Streamlit Secrets!")

def get_sheet_data(sheet_url, row_number):
    try:
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url).sheet1
        return sheet, sheet.row_values(row_number)
    except Exception as e:
        return None, f"Error: {e}"

def download_drive_video(file_id, output_filename):
    try:
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        headers = {"Authorization": f"Bearer {creds.token}"}
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            with open(output_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            return "Success"
        else:
            return f"API Error: {response.text}"
    except Exception as e:
        return f"Error: {e}"

def process_video(input_filename, output_filename, crop):
    try:
        input_stream = ffmpeg.input(input_filename)
        video = input_stream.video
        audio = input_stream.audio
        
        if crop:
            video = ffmpeg.filter(video, 'crop', 'ih*4/5', 'ih')
            
        output = ffmpeg.output(
            video, 
            audio, 
            output_filename, 
            vcodec='libx264',
            preset='ultrafast',
            threads=1,
            acodec='aac', 
            audio_bitrate='192k', 
            ar='44100', 
            ac=2,
            t='59.5'
        )
        ffmpeg.run(output, overwrite_output=True, quiet=True)
        return "Success"
    except Exception as e:
        return f"Error: {e}"

def attendre_traitement_conteneur(container_id, access_token, nom="conteneur", max_retries=30, delay=5):
    status = "IN_PROGRESS"
    retries = 0
    status_placeholder = st.empty()
    while status == "IN_PROGRESS" and retries < max_retries:
        time.sleep(delay)
        url = f"https://graph.facebook.com/v20.0/{container_id}?fields=status_code&access_token={access_token}"
        res = requests.get(url).json()
        status = res.get("status_code", "ERROR")
        retries += 1
        status_placeholder.write(f"⏳ Traitement {nom} : statut {status} (essai {retries}/{max_retries})")
    if status != "FINISHED":
        raise Exception(f"Le {nom} ({container_id}) n'a pas pu être validé par Meta (statut: {status}).")
    status_placeholder.write(f"✅ {nom.capitalize()} prêt !")

def publish_now_to_instagram(cloudinary_urls, caption):
    container_ids = []
    for index, url_val in enumerate(cloudinary_urls):
        st.write(f"Création du conteneur vidéo {index + 1}/{len(cloudinary_urls)} sur Instagram...")
        url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media"
        payload = {'media_type': 'VIDEO', 'video_url': url_val, 'is_carousel_item': 'true', 'access_token': ACCESS_TOKEN}
        r = requests.post(url, data=payload).json()
        if 'id' in r:
            container_ids.append(r['id'])
        else:
            return False, f"Erreur Création Conteneur : {r}"
            
    st.write("⏳ Attente de l'encodage par Meta...")
    try:
        for idx, c_id in enumerate(container_ids, start=1):
            attendre_traitement_conteneur(c_id, ACCESS_TOKEN, nom=f"vidéo {idx}/{len(container_ids)}")
    except Exception as e:
        return False, str(e)
    
    st.write("Création du carrousel principal...")
    url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media"
    payload = {'media_type': 'CAROUSEL', 'children': ','.join(container_ids), 'caption': caption, 'access_token': ACCESS_TOKEN}
    r = requests.post(url, data=payload).json()
    if 'id' not in r: return False, f"Erreur Création Carrousel : {r}"
    carousel_id = r['id']
    
    st.write("⏳ Validation finale par Meta...")
    try:
        attendre_traitement_conteneur(carousel_id, ACCESS_TOKEN, nom="carrousel assemblé", delay=5)
    except Exception as e:
        return False, str(e)
    
    pub_url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    pub_payload = {'creation_id': carousel_id, 'access_token': ACCESS_TOKEN}
    pub_r = requests.post(pub_url, data=pub_payload).json()
    
    if 'id' in pub_r: return True, pub_r['id']
    else: return False, f"Erreur Publication : {pub_r}"

# --- USER INTERFACE & STATE MACHINE ---
st.set_page_config(page_title="Rinse Instagram Scheduler", layout="wide")
st.title("Rinse France Carousel Scheduler")

# Initialisation des variables de mémoire (State)
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'cloudinary_urls' not in st.session_state:
    st.session_state.cloudinary_urls = []
if 'video_urls' not in st.session_state:
    st.session_state.video_urls = []

st.subheader("1. Sélectionner le contenu")
sheet_url = st.text_input("URL exacte du Google Sheet :", value=st.session_state.get('sheet_url', ''))
row_number = st.number_input("Numéro de ligne Google Sheet à traiter", min_value=2, value=st.session_state.get('row_number', 5), step=1)
crop_option = st.radio("Format Vidéo", ["Auto-Crop au format Portrait 4:5 (Recommandé)", "Conserver le format d'origine"])

# Bouton de lancement
if not st.session_state.is_processing and st.button("Récupérer et traiter la ligne"):
    sheet, data = get_sheet_data(sheet_url, row_number)
    if isinstance(data, list) and len(data) >= 8:
        # Configuration des données dans la mémoire
        st.session_state.sheet_url = sheet_url
        st.session_state.row_number = row_number
        st.session_state.artist_name = data[1]
        st.session_state.caption_text = data[7] if len(data) > 7 else ""
        st.session_state.schedule_date = data[8] if len(data) > 8 else "Pas de date"
        st.session_state.schedule_time = data[9] if len(data) > 9 else "Pas d'heure"
        st.session_state.video_urls = [url.strip() for url in data[4].split(',') if url.strip()]
        st.session_state.should_crop = (crop_option == "Auto-Crop au format Portrait 4:5 (Recommandé)")
        
        # Lancement du mode traitement
        st.session_state.is_processing = True
        st.session_state.current_index = 0
        st.session_state.cloudinary_urls = []
        st.rerun() # Rafraîchit l'app pour démarrer la boucle par étapes

# Boucle de traitement par étapes (Contournement du Timeout Serveur)
if st.session_state.is_processing:
    st.markdown("---")
    st.subheader(f"2. Prévisualisation du Post : {st.session_state.artist_name}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Programmé pour :**\n\n{st.session_state.schedule_date} à {st.session_state.schedule_time}")
    with col2:
        st.info(f"**Légende (Caption) :**\n\n{st.session_state.caption_text}")
        
    total_videos = len(st.session_state.video_urls)
    current = st.session_state.current_index
    
    st.write(f"**Traitement en cours : Vidéo {current + 1} sur {total_videos}... (Le rafraîchissement automatique est normal)**")
    st.progress(current / total_videos if total_videos > 0 else 0)
    
    if current < total_videos:
        url = st.session_state.video_urls[current]
        
        # Extraction de l'ID Google Drive
        file_id = None
        try:
            if "id=" in url:
                file_id = url.split("id=")[1].split("&")[0]
            elif "/file/d/" in url:
                file_id = url.split("/file/d/")[1].split("/")[0]
        except Exception:
            pass
            
        if not file_id:
            st.warning(f"Lien ignoré (format non reconnu) : {url}")
            st.session_state.current_index += 1
            time.sleep(1)
            st.rerun()
            
        temp_dl = f"temp_download_{current}.mp4"
        final_vid = f"final_video_{current}.mp4"
        
        with st.spinner(f"Encodage de la vidéo {current + 1} en cours..."):
            dl_status = download_drive_video(file_id, temp_dl)
            if dl_status == "Success":
                process_status = process_video(temp_dl, final_vid, st.session_state.should_crop)
                if process_status == "Success":
                    upload_result = cloudinary.uploader.upload(final_vid, resource_type="video")
                    st.session_state.cloudinary_urls.append(upload_result.get("secure_url"))
                    
                    # Nettoyage profond pour ne jamais saturer la RAM
                    if os.path.exists(temp_dl): os.remove(temp_dl)
                    if os.path.exists(final_vid): os.remove(final_vid)
                    gc.collect() 
                    
        # On incrémente et ON REDÉMARRE L'APP pour remettre à zéro le compteur de timeout !
        st.session_state.current_index += 1
        st.rerun() 
        
    else:
        # Fin de la boucle
        st.session_state.is_processing = False
        st.success("Toutes les vidéos sont prêtes, recadrées et hébergées !")
        st.rerun() # Affichage final de la section 3

# Section de publication (S'affiche uniquement si on n'est pas en train de traiter)
if not st.session_state.is_processing and st.session_state.get('cloudinary_urls'):
    st.markdown("---")
    st.subheader("3. Action de Publication")
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🚀 Publier immédiatement sur Instagram"):
            with st.spinner("Publication directe en cours sur Instagram..."):
                success, result = publish_now_to_instagram(st.session_state.cloudinary_urls, st.session_state.caption_text)
                if success:
                    sheet, _ = get_sheet_data(st.session_state.sheet_url, st.session_state.row_number)
                    urls_str = ",".join(st.session_state.cloudinary_urls)
                    sheet.update_cell(st.session_state.row_number, 12, urls_str)
                    sheet.update_cell(st.session_state.row_number, 13, "Publié")
                    st.balloons()
                    st.success(f"🎉 Publication réussie ! ID du post : {result}")
                else:
                    st.error(f"❌ Échec de la publication : {result}")
                    
    with col_b:
        if st.button("📅 Programmer pour publication automatique (11h / 17h)"):
            try:
                sheet, _ = get_sheet_data(st.session_state.sheet_url, st.session_state.row_number)
                urls_str = ",".join(st.session_state.cloudinary_urls)
                sheet.update_cell(st.session_state.row_number, 12, urls_str)
                sheet.update_cell(st.session_state.row_number, 13, "Programmé")
                st.balloons()
                st.success("🎉 Le post est programmé ! Il sera publié automatiquement sur Instagram à 11h00 ou 17h00.")
            except Exception as e:
                st.error(f"Erreur de mise à jour du Sheet : {e}")