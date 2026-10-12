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

# Load credentials directly from [gcp_service_account] in Streamlit Secrets
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
            acodec='aac', 
            audio_bitrate='192k', 
            ar='44100', 
            ac=2
        )
        ffmpeg.run(output, overwrite_output=True, quiet=True)
        return "Success"
    except Exception as e:
        return f"Error: {e}"

def publish_now_to_instagram(cloudinary_urls, caption):
    container_ids = []
    for index, url_val in enumerate(cloudinary_urls):
        st.write(f"Création du conteneur vidéo {index + 1}/{len(cloudinary_urls)} sur Instagram...")
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
            return False, f"Erreur Création Conteneur Vidéo : {r}"
            
    st.write("Attente du traitement vidéo par les serveurs Meta (15 secondes)...")
    time.sleep(15)
    
    st.write("Création du carrousel principal...")
    url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media"
    payload = {
        'media_type': 'CAROUSEL',
        'children': ','.join(container_ids),
        'caption': caption,
        'access_token': ACCESS_TOKEN
    }
    r = requests.post(url, data=payload).json()
    if 'id' not in r:
        return False, f"Erreur Création Carrousel : {r}"
        
    carousel_id = r['id']
    time.sleep(5)
    
    st.write("Publication en cours sur le compte Instagram Rinse France...")
    pub_url = f"https://graph.facebook.com/v26.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    pub_payload = {
        'creation_id': carousel_id,
        'access_token': ACCESS_TOKEN
    }
    pub_r = requests.post(pub_url, data=pub_payload).json()
    
    if 'id' in pub_r:
        return True, pub_r['id']
    else:
        return False, f"Erreur Publication : {pub_r}"

# --- USER INTERFACE ---
st.set_page_config(page_title="Rinse Instagram Scheduler", layout="wide")
st.title("Rinse France Carousel Scheduler")

st.subheader("1. Sélectionner le contenu")
sheet_url = st.text_input("URL exacte du Google Sheet :")
row_number = st.number_input("Numéro de ligne Google Sheet à traiter", min_value=2, value=5, step=1)
crop_option = st.radio("Format Vidéo", ["Auto-Crop au format Portrait 4:5 (Recommandé)", "Conserver le format d'origine"])

if st.button("Récupérer et traiter la ligne"):
    sheet, data = get_sheet_data(sheet_url, row_number)
    if isinstance(data, list) and len(data) >= 8:
        artist_name = data[1]
        raw_urls = data[4]
        caption_text = data[7] if len(data) > 7 else ""
        schedule_date = data[8] if len(data) > 8 else "Pas de date"
        schedule_time = data[9] if len(data) > 9 else "Pas d'heure"
        
        video_urls = [url.strip() for url in raw_urls.split(',') if url.strip()]
        should_crop = (crop_option == "Auto-Crop au format Portrait 4:5 (Recommandé)")
        
        st.markdown("---")
        st.subheader(f"2. Prévisualisation du Post : {artist_name}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info("**Programmé pour :**\n\n" + f"{schedule_date} à {schedule_time}")
        with col2:
            st.info("**Légende (Caption) :**\n\n" + caption_text)
            
        st.write(f"**Traitement et hébergement de {len(video_urls)} vidéo(s)...**")
        
        processed_files = []
        cloudinary_urls = []
        for index, url in enumerate(video_urls):
            try:
                file_id = url.split("id=")[1]
            except IndexError:
                continue
                
            temp_dl = f"temp_download_{index}.mp4"
            final_vid = f"final_video_{index}.mp4"
            dl_status = download_drive_video(file_id, temp_dl)
            
            if dl_status == "Success":
                process_status = process_video(temp_dl, final_vid, should_crop)
                if process_status == "Success":
                    st.video(final_vid)
                    processed_files.append(final_vid)
                    
                    upload_result = cloudinary.uploader.upload(final_vid, resource_type="video")
                    cloudinary_urls.append(upload_result.get("secure_url"))
                    
                    if os.path.exists(temp_dl):
                        os.remove(temp_dl)
        
        st.session_state['processed_files'] = processed_files
        st.session_state['cloudinary_urls'] = cloudinary_urls
        st.session_state['caption_text'] = caption_text
        st.session_state['sheet_url'] = sheet_url
        st.session_state['row_number'] = row_number
        st.success("Toutes les vidéos sont prêtes, recadrées et hébergées !")

if 'cloudinary_urls' in st.session_state and st.session_state['cloudinary_urls']:
    st.markdown("---")
    st.subheader("3. Action de Publication")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        if st.button("🚀 Publier immédiatement sur Instagram"):
            with st.spinner("Publication directe en cours sur Instagram..."):
                success, result = publish_now_to_instagram(
                    st.session_state['cloudinary_urls'], 
                    st.session_state['caption_text']
                )
                if success:
                    sheet, _ = get_sheet_data(st.session_state['sheet_url'], st.session_state['row_number'])
                    urls_str = ",".join(st.session_state['cloudinary_urls'])
                    sheet.update_cell(st.session_state['row_number'], 12, urls_str)
                    sheet.update_cell(st.session_state['row_number'], 13, "Publié")
                    st.balloons()
                    st.success(f"🎉 Publication réussie ! ID du post : {result}")
                else:
                    st.error(f"❌ Échec de la publication : {result}")
                    
    with col_b:
        if st.button("📅 Programmer pour publication automatique (11h / 17h)"):
            try:
                sheet, _ = get_sheet_data(st.session_state['sheet_url'], st.session_state['row_number'])
                urls_str = ",".join(st.session_state['cloudinary_urls'])
                sheet.update_cell(st.session_state['row_number'], 12, urls_str)
                sheet.update_cell(st.session_state['row_number'], 13, "Programmé")
                st.balloons()
                st.success("🎉 Le post est programmé ! Il sera publié automatiquement sur Instagram à 11h00 ou 17h00.")
            except Exception as e:
                st.error(f"Erreur de mise à jour du Sheet : {e}")