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

# Explicit multi-line PEM formatting guarantees zero encoding errors
key_lines = [
    "-----BEGIN PRIVATE KEY-----",
    "MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQD5yG3yG29SRHsP",
    "YGJUb45E6xoJvdk/IpEANWreOicoTLi8aJOPwhRf7aPI7Pdknv4f3CnTq//jXqES",
    "V2FOhZknPQb/O7QKetbYQx8hj6Q5sJwP0D1o1x2cAEzLRMUIhfGkhxFTvkV+4yJy",
    "kfEvbs3jy8Y2k0VZ7esc/om7O58M6BFfeawLRLiNa+HHU1VoEE6ryDiEH06flLxK",
    "CZU6D/sp1uR503LMKZkjHuj/ecilrBA1dKKcSDWWKka1AC3Gu3jTBWq9YDVB3uUI",
    "91ih3GkjLCyRPa4jOMfPkPu2UuzikKeHbx8IxBiiY0OhgJ9Nv+ciX6n6+GYEEez/",
    "s2P7pz1lAgMBAAECggEAdzZsFu12G3b4nrWbKH5Xkdf9ROH5ohLOzqEwAKETmD3J",
    "u45TwvxXehMypM5IIptpYO5UfiRsi+lZiaXvmKjVmC8dvEoT2x6WlH+wh3WFZU0/",
    "pqJ19Kgahx5ziF4phbBbzHD0WZoJlA42niS+Tiudk1dpohl2s32ERYHMXXKOrfrR",
    "Exk/25TOZ3VhbXts2NEDNeFtJWMpLPRtf0pO5tcPrgICjmLZ5fq0eJBTE+/0THc/",
    "WcuatHd3YDVujtYkv72eCv30b7L44V+cTIXCrkIDmYdbTfZhSDZ0e2WhTLbhul1a",
    "R/OGyMPXUSnIqxXPYeFBdOCLz33VqfzwXp7OMRehPwKBgQD9FNQZ1DaNoDaAP9SW",
    "1AVsF/sg127v0mC6aL3U8akKWVk8Mhrm18EEjCqBr+b0bqPgpy2dlU9bwBApqJcu",
    "s44ZxveJTEV4b5rwBllBiauIwvzCuNALT0yFAYZYhf2+O7lZxeKOjOj/MphRlwWM",
    "pYFJlp7Z2mjUfXJz6NpnlkeRUwKBgQD8qdzteE0WH5kvI2IQKfKRjzupR2tPBmIx",
    "bSR/GqN6OVl9Rn50YngeglkD0DnbZtIzusK/1aed2baEjERuZ+/39Crsjh6PIee4",
    "VDiRTDKtoI2HX2PGmPril76SpzlSklaOQo4oj/fkUrdj0LPDabjHdTRrA99xtLJq",
    "0rfU98OHZwKBgQC5wdr4ZlnwU+MM+SyntKHLZRksHqsMx9Cy9+6BvmYgR6",
    "4WvMEbF1ZQ4I5ViloS+LFbec6XkziooE/kfTxcWU4gWvo4M+n/pNb2YXSL9LkWkq",
    "k/bfPUJFoXugcKfYK7Xh2a1++rzwTgAFvskJoWNRFc2SAc3LI+OC2rwG/wKBgQDZ",
    "KAlZFId0l03qZMfYyqTQFEIb2OVS81Kb1omCsNuGphnTAS6YSzWgSznEfEft2W6a",
    "xU6y4CgDFGa5f3ElTzHBc9scm32KWYK2O7SutMXt0ssxaXvw6fTfobpKg21SGbJI",
    "7M0P8cUGOU2jfXGzZ39H9uVJgPef28Vo6JjVculbywKBgQCgY7vsQBxbJXoYpHUN",
    "oAsuJOh0rf5W+q78QfF3i+WgHpViN3f1vT4UbivixUrEhGp37V2vyZa96lpVpaih",
    "NEyhX41yRgtnhnoB7cVhwi0IgHb0X0M29IoMwySgomyIx0r/D1mi5Rndsr0DB+vh",
    "BskD0tXj2itqXCC2HRM2t8Bzyg==",
    "-----END PRIVATE KEY-----"
]

formatted_private_key = "\n".join(key_lines) + "\n"

gcp_info = {
    "type": "service_account",
    "project_id": "rinse-france-ig-scheduler",
    "private_key_id": "914491679f4c7b1fd201b473df8945b6459f0019",
    "private_key": formatted_private_key,
    "client_email": "sheet-reader@rinse-france-ig-scheduler.iam.gserviceaccount.com",
    "client_id": "114718124634511508512",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/sheet-reader%40rinse-france-ig-scheduler.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

creds = Credentials.from_service_account_info(gcp_info, scopes=SCOPES)

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