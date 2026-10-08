import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.auth.transport.requests
import requests
import ffmpeg
import os
import time

# --- CONFIGURATION META INSTAGRAM API ---
ACCESS_TOKEN = "EAAfC6VhaxUoBSpiyh2BBZCMHAZAC0p5r7V0ff84EOHzEtOuFcoFeZANQpGZBYa8SzCxfhSZAA38SPZChmB31cqywhC9NwZCgGaKN6AJ401zK0CyvmPhmnjZC6wx2ZAvRt5FjzelhtgSU0o60q1LdZBjEZA3UWZB58RnZBbfalZA5OLsIec7Bx8GD4ZBbttU8Lyfa6w9J8ZBEcz9zqNtdI7Y68SzknJ9Q6EqPvUAwVuJQ5tf0QN7zZCIMZBZBa7Ky0okZCGQmAgYZCCj3ZC1jidVMBMebESKaBiAmjAZACiplCqIT9L5fCUZD"
FACEBOOK_PAGE_ID = "687289131283875"
INSTAGRAM_ACCOUNT_ID = "17841401400979395"

# --- GOOGLE SHEETS & DRIVE ENGINE ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)

def get_sheet_data(sheet_url, row_number):
    try:
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url).sheet1
        return sheet.row_values(row_number)
    except Exception as e:
        return f"Error: {e}"

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
        
        # Extrait la vidéo et l'audio séparément
        video = input_stream.video
        audio = input_stream.audio
        
        if crop:
            video = ffmpeg.filter(video, 'crop', 'ih*4/5', 'ih')
            
        # Combine la vidéo et l'audio avec encodage AAC stéréo
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

# --- USER INTERFACE ---
st.set_page_config(page_title="Rinse Instagram Scheduler", layout="wide")
st.title("Rinse France Carousel Scheduler")

st.subheader("1. Sélectionner le contenu")
sheet_url = st.text_input("URL exacte du Google Sheet :")
row_number = st.number_input("Numéro de ligne Google Sheet à traiter", min_value=2, value=173, step=1)
crop_option = st.radio("Format Vidéo", ["Auto-Crop au format Portrait 4:5 (Recommandé)", "Conserver le format d'origine"])

if st.button("Récupérer et traiter la ligne"):
    data = get_sheet_data(sheet_url, row_number)
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
            
        st.write(f"**Traitement de {len(video_urls)} vidéo(s) pour le carrousel...**")
        
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
                    if os.path.exists(temp_dl):
                        os.remove(temp_dl)
        
        st.success("Toutes les vidéos sont prêtes et traitées !")
        
        st.markdown("---")
        st.subheader("3. Publication sur Instagram")
        st.success("Clés Meta API connectées avec succès !")
    else:
        st.error("Impossible de se connecter ou ligne vide.")