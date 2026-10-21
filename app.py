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
import gc
import google.generativeai as genai

# --- CONFIGURATION META, CLOUDINARY & GEMINI API ---
ACCESS_TOKEN = st.secrets.get("META_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID = "687289131283875"
INSTAGRAM_ACCOUNT_ID = "17841401400979395"

if "CLOUDINARY_CLOUD_NAME" in st.secrets:
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"]
    )

# Configuration Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.warning("⚠️ Clé GEMINI_API_KEY manquante dans secrets.toml. La génération par IA sera désactivée.")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

if "gcp_service_account" in st.secrets:
    gcp_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in gcp_dict:
        gcp_dict["private_key"] = gcp_dict["private_key"].replace("\n", "\n")
    creds = Credentials.from_service_account_info(gcp_dict, scopes=SCOPES)
else:
    st.error("Missing [gcp_service_account] in Streamlit Secrets!")


# --- FONCTIONS DE BASE ---
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

# --- FONCTION IA GEMINI CORRIGÉE ---
def generate_insta_captions(raw_text, artist_name):
    prompt = f"""Tu es le CM de Rinse France.
Génère 3 variations de caption Instagram pour un post collaboratif avec l'artiste.

RÈGLES STRICTES :
1. ZÉRO HASHTAG.
2. DU POINT DE VUE DE RINSE FRANCE (3ème personne, ex: "@{artist_name} prend le contrôle...", ne dis pas "je").
3. TRÈS FIDÈLE AU TEXTE ORIGINAL : Garde l'esprit du texte fourni par l'artiste.
4. MISE EN PAGE IMPECCABLE : Sauts de ligne clairs, aérés (notamment s'il y a une tracklist ou une liste de guests).
5. Pas de redondances inutiles.
6. Termine avec le CTA : "Retrouvez l’émission dans son intégralité sur rinse.fr et notre app 📲" (une seule fois).

Texte brut de l'artiste :
{raw_text}

Réponds au format JSON strict :
{{
  "opt1": "Variation 1 (Clean & Fidèle)",
  "opt2": "Variation 2 (Focus Invités / Énergie)",
  "opt3": "Variation 3 (Formaté aérés / Tracklist)"
}}
"""
    # Liste de modèles avec repli automatique
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-pro']
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            import json
            import re
            text = response.text
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                clean_json = match.group(0)
                return json.loads(clean_json)
            return {"opt1": text, "opt2": "Erreur de formatage", "opt3": "Erreur de formatage"}
        except Exception as e:
            last_error = str(e)
            continue
            
    return {"opt1": f"Erreur IA: {last_error}", "opt2": "", "opt3": ""}


# --- INTERFACE UTILISATEUR (UI) & STYLES ---
st.set_page_config(page_title="Rinse Instagram Scheduler", layout="wide", page_icon="📻")

# Injection CSS pour le branding Rinse
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

    :root {
        --rinse-bg: #0A0A0C;
        --rinse-card: #121215;
        --rinse-border: #222228;
        --rinse-text: #FFFFFF;
        --rinse-muted: #8E8E9A;
        --rinse-accent: #FFFFFF;
    }

    html, body, [class*="css"]  {
        font-family: 'Space Grotesk', -apple-system, sans-serif !important;
    }

    /* Titres centrés */
    h1, h2, h3, .st-emotion-cache-10trblm {
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        text-align: center;
    }

    .stButton>button {
        background-color: var(--rinse-accent) !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
        text-transform: uppercase;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        opacity: 0.8 !important;
        transform: scale(0.98);
    }
    
    .btn-secondary>button {
        background-color: transparent !important;
        color: var(--rinse-text) !important;
        border: 1px solid var(--rinse-border) !important;
    }
    .btn-secondary>button:hover {
        background-color: var(--rinse-border) !important;
    }
</style>
""", unsafe_allow_html=True)

# En-tête : Logo centré au-dessus du titre
logo_file = None
possible_logos = ["Rinse_MasterLogo2021_RGB_Black.png", "logo.png", "logo.jpg", "logo.jpeg", "rinse_logo.png", "RinseLogo.png"]
for f in possible_logos:
    if os.path.exists(f):
        logo_file = f
        break

if logo_file:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.image(logo_file, use_container_width=True)

st.title("Rinse France Instagram Carroussel Scheduler")

st.markdown("---")

# Initialisation des variables de mémoire (State)
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'cloudinary_urls' not in st.session_state:
    st.session_state.cloudinary_urls = []
if 'video_urls' not in st.session_state:
    st.session_state.video_urls = []
if 'ai_options' not in st.session_state:
    st.session_state.ai_options = None
if 'final_caption' not in st.session_state:
    st.session_state.final_caption = ""

st.subheader("1. Sélectionner le contenu")
sheet_url = st.text_input("URL exacte du Google Sheet :", value=st.session_state.get('sheet_url', ''))
row_number = st.number_input("Numéro de ligne Google Sheet à traiter", min_value=2, value=st.session_state.get('row_number', 5), step=1)
crop_option = st.radio("Format Vidéo", ["Auto-Crop au format Portrait 4:5 (Recommandé)", "Conserver le format d'origine"])

# Bouton de lancement principal
if not st.session_state.is_processing and st.button("RÉCUPÉRER ET TRAITER LA LIGNE"):
    sheet, data = get_sheet_data(sheet_url, row_number)
    if isinstance(data, list) and len(data) >= 8:
        st.session_state.sheet_url = sheet_url
        st.session_state.row_number = row_number
        st.session_state.artist_name = data[1]
        st.session_state.caption_text = data[7] if len(data) > 7 else ""
        st.session_state.final_caption = data[7] if len(data) > 7 else ""
        st.session_state.schedule_date = data[8] if len(data) > 8 else "Pas de date"
        st.session_state.schedule_time = data[9] if len(data) > 9 else "Pas d'heure"
        st.session_state.video_urls = [url.strip() for url in data[4].split(',') if url.strip()]
        st.session_state.should_crop = (crop_option == "Auto-Crop au format Portrait 4:5 (Recommandé)")
        
        st.session_state.ai_options = None
        
        st.session_state.is_processing = True
        st.session_state.current_index = 0
        st.session_state.cloudinary_urls = []
        st.rerun() 

# Boucle de traitement des vidéos par étapes
if st.session_state.is_processing:
    st.markdown("---")
    st.subheader(f"2. Encodage Vidéo : {st.session_state.artist_name}")
    
    total_videos = len(st.session_state.video_urls)
    current = st.session_state.current_index
    
    st.write(f"**Traitement en cours : Vidéo {current + 1} sur {total_videos}... (Le rafraîchissement est normal)**")
    st.progress(current / total_videos if total_videos > 0 else 0)
    
    if current < total_videos:
        url = st.session_state.video_urls[current]
        
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
                    
                    if os.path.exists(temp_dl): os.remove(temp_dl)
                    if os.path.exists(final_vid): os.remove(final_vid)
                    gc.collect() 
                    
        st.session_state.current_index += 1
        st.rerun() 
        
    else:
        st.session_state.is_processing = False
        st.success("Toutes les vidéos sont prêtes, recadrées et hébergées !")
        st.rerun() 

# Section Édition Caption et Publication
if not st.session_state.is_processing and st.session_state.get('cloudinary_urls'):
    st.markdown("---")
    st.subheader(f"3. Studio d'Édition : {st.session_state.artist_name}")
    
    st.info(f"📅 **Programmé pour :** {st.session_state.schedule_date} à {st.session_state.schedule_time}")
    
    st.write("### 📝 Gestion de la Caption")
    
    col_raw, col_ai = st.columns([1, 1])
    
    with col_raw:
        st.text_area("Texte Brut fourni par l'artiste (Lu depuis le Sheet)", value=st.session_state.caption_text, height=200, disabled=True)
        
        st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
        if st.button("✨ GÉNÉRER 3 OPTIONS INSTA VIA IA"):
            with st.spinner("L'IA Gemini analyse le texte..."):
                options = generate_insta_captions(st.session_state.caption_text, st.session_state.artist_name)
                st.session_state.ai_options = options
        st.markdown('</div>', unsafe_allow_html=True)

    with col_ai:
        if st.session_state.ai_options:
            tab1, tab2, tab3 = st.tabs(["Option 1 (Clean)", "Option 2 (Énergie)", "Option 3 (Tracklist)"])
            with tab1:
                st.write(st.session_state.ai_options.get('opt1', ''))
                if st.button("Choisir Option 1", key="btn_opt1"):
                    st.session_state.final_caption = st.session_state.ai_options.get('opt1', '')
            with tab2:
                st.write(st.session_state.ai_options.get('opt2', ''))
                if st.button("Choisir Option 2", key="btn_opt2"):
                    st.session_state.final_caption = st.session_state.ai_options.get('opt2', '')
            with tab3:
                st.write(st.session_state.ai_options.get('opt3', ''))
                if st.button("Choisir Option 3", key="btn_opt3"):
                    st.session_state.final_caption = st.session_state.ai_options.get('opt3', '')
        else:
            st.info("Cliquez sur le bouton pour générer des options.")

    st.write("---")
    
    st.write("### ✂️ Caption Finale (Modifiable avant publication)")
    edited_caption = st.text_area("C'est ce texte qui sera publié ou programmé", value=st.session_state.final_caption, height=250)
    st.session_state.final_caption = edited_caption

    st.markdown("---")
    st.subheader("4. Action Finale")
    
    col_pub, col_prog = st.columns(2)
    with col_pub:
        if st.button("🚀 PUBLIER IMMÉDIATEMENT"):
            with st.spinner("Publication directe en cours sur Instagram..."):
                success, result = publish_now_to_instagram(st.session_state.cloudinary_urls, st.session_state.final_caption)
                if success:
                    sheet, _ = get_sheet_data(st.session_state.sheet_url, st.session_state.row_number)
                    urls_str = ",".join(st.session_state.cloudinary_urls)
                    sheet.update_cell(st.session_state.row_number, 12, urls_str)
                    sheet.update_cell(st.session_state.row_number, 13, "Publié")
                    sheet.update_cell(st.session_state.row_number, 8, st.session_state.final_caption)
                    st.balloons()
                    st.success(f"🎉 Publication réussie ! ID du post : {result}")
                else:
                    st.error(f"❌ Échec de la publication : {result}")
                    
    with col_prog:
        if st.button("📅 PROGRAMMER (GITHUB)"):
            try:
                sheet, _ = get_sheet_data(st.session_state.sheet_url, st.session_state.row_number)
                urls_str = ",".join(st.session_state.cloudinary_urls)
                sheet.update_cell(st.session_state.row_number, 12, urls_str)
                sheet.update_cell(st.session_state.row_number, 13, "Programmé")
                sheet.update_cell(st.session_state.row_number, 8, st.session_state.final_caption)
                st.balloons()
                st.success("🎉 Le post est programmé et le texte final a été sauvegardé dans le Google Sheet !")
            except Exception as e:
                st.error(f"Erreur de mise à jour du Sheet : {e}")