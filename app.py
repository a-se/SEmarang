import streamlit as st
import pandas as pd
from datetime import date
import requests
from streamlit_gsheets import GSheetsConnection  # 1. Pastikan library ini di-import langsung

st.set_page_config(page_title="PPL Monitoring - Koordinator View", page_icon="📝", layout="wide")

# =============================================================================
# 1. FIXED GOOGLE OAUTH SECURITY LAYER (DIRECT EXCHANGE)
# =============================================================================
client_id = st.secrets["google_auth"]["client_id"]
client_secret = st.secrets["google_auth"]["client_secret"]
redirect_uri = st.secrets["google_auth"]["redirect_uri"]

# Handle OAuth Callback Code from URL
query_params = st.query_params
if "code" in query_params and "user_email" not in st.session_state:
    auth_code = query_params["code"]
    
    # Direct HTTP POST Exchange to avoid PKCE "Missing code verifier" mismatch
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        token_response = requests.post(token_url, data=payload).json()
        
        if "access_token" in token_response:
            access_token = token_response["access_token"]
            
            # Fetch user profile attributes using the access token
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info = requests.get(userinfo_url, headers=headers).json()
            
            st.session_state["user_email"] = user_info["email"].lower().strip()
            st.session_state["user_name"] = user_info["name"]
        else:
            st.error(f"OAuth Exchange Error: {token_response.get('error_description', 'Token request failed')}")
            
    except Exception as e:
        st.error(f"Gagal memproses login Google: {e}")
    finally:
        # Clear code from URL parameter bar to keep history clean
        st.query_params.clear()

# Enforce Authentication Guardrail
if "user_email" not in st.session_state:
    st.title("🔐 Monitoring Progres Lapangan")
    st.write("Silahkan login menggunakan Akun Google Koordinator Anda untuk mengakses sistem.")
    
    # Build direct authorization link parameters
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    scopes = "openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email"
    
    login_url = f"{auth_uri}?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope={scopes}&prompt=select_account"
    
    st.link_button("🔑 Login dengan Akun Google", login_url, type="primary")
    st.stop()

user_email = st.session_state["user_email"]
user_name = st.session_state["user_name"]

# Sidebar User Control Drawer
with st.sidebar:
    st.subheader("Profil Koordinator")
    st.write(f"Nama: **{user_name}**")
    st.write(f"Email: *{user_email}*")
    st.markdown("---")
    if st.button("🚪 Keluar / Log Out", use_container_width=True):
        del st.session_state["user_email"]
        del st.session_state["user_name"]
        st.rerun()

# =============================================================================
# 2. DATABASE CONNECTION (GOOGLE SHEETS)
# =============================================================================
# 2. Inisialisasi koneksi gsheets menggunakan class GSheetsConnection secara langsung
conn = st.connection("gsheets", type=GSheetsConnection)
TRACKING_SHEET = "Progress"
USER_SHEET = "user"

try:
    # Membaca sheet progress secara mentah tanpa header otomatis agar sel gabungan (merged) aman diproses manual
    df_raw = conn.read(worksheet=TRACKING_SHEET, header=None, ttl=0)
    df_users = conn.read(worksheet=USER_SHEET, ttl=60)
    df_users['email'] = df_users['email'].str.lower().str.strip()
except Exception as e:
    st.error(f"Gagal memuat database Google Sheets: {e}")
    st.stop()

# =============================================================================
# 3. HIERARCHY RESOLUTION FOR LOGGED IN KOORDINATOR
# =============================================================================
koordinator_matches = df_users[df_users['email'] == user_email]

if koordinator_matches.empty:
    st.error(f"❌ Akses Ditolak: Email Anda ({user_email}) tidak terdaftar sebagai Koordinator.")
    st.stop()

nama_koordinator = koordinator_matches.iloc[0]['Koordinator']

st.title(f"📊 Panel Input Koordinator: {nama_koordinator}")
st.markdown("Silahkan tentukan PML dan PPL untuk menginput progres harian.")

# Filter hierarchy dynamic options arrays
filtered_users = df_users[df_users['Koordinator'] == nama_koordinator]
available_pml = sorted(filtered_users['PML'].dropna().unique().tolist())

# =============================================================================
# 4. INTERACTIVE ENTRY FORM GRID
# =============================================================================
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📍 Pilihan Target")
    selected_pml = st.selectbox("1. Pilih PML", ["-- Pilih PML --"] + available_pml)
    
    if selected_pml != "-- Pilih PML --":
        available_ppl = sorted(filtered_users[filtered_users['PML'] == selected_pml]['PPL'].dropna().unique().tolist())
    else:
        available_ppl = []
        
    selected_ppl = st.selectbox("2. Pilih PPL", ["-- Pilih PPL --"] + available_ppl, disabled=(selected_pml == "-- Pilih PML --"))

with col2:
    st.subheader("📝 Input Data Progres")
    today_str = str(date.today())
    
    with st.form("koordinator_input_form"):
        st.info(f"📅 Tanggal Input: **{today_str}**")
        
        jumlah_input = st.number_input(
            "Jumlah Capaian Progres Hari Ini", 
            min_value=0, 
            step=1, 
            disabled=(selected_ppl == "-- Pilih PPL --")
        )
        
        alasan_input = st.text_area(
            "Alasan Kendala (Wajib jika progres < 13)", 
            placeholder="Tulis alasan jika target minimal harian tidak terpenuhi...",
            disabled=(selected_ppl == "-- Pilih PPL --")
        )
        
        submit_btn = st.form_submit_button("Simpan Progres PPL", use_container_width=True, disabled=(selected_ppl == "-- Pilih PPL --"))

    if submit_btn:
        if jumlah_input < 13 and not alasan_input.strip():
            st.error("❌ Gagal Mengirim: Karena progres di bawah target (< 13), kolom **Alasan** wajib diisi.")
        else:
            # Kolom 3 (indeks 3) di df_raw adalah nama PPL
            ppl_match = df_raw[df_raw[3].astype(str).str.upper().str.strip() == selected_ppl.upper().strip()]
            
            if ppl_match.empty:
                st.error(f"❌ Nama PPL '{selected_ppl}' tidak ditemukan di lembar data '{TRACKING_SHEET}'.")
            else:
                target_row = ppl_match.index[0]
                
                # 3. PENANGANAN HEADER TANGGAL (MERGED CELL)
                # Pada skenario multi-row header Anda:
                # Baris 0 (indeks ke-0) adalah baris gabungan ("date" / Tanggal)
                # Baris 1 (indeks ke-1) adalah baris anak sub-kolom ("jumlah" dan "alasan")
                row_0_dates = df_raw.iloc[0].ffill().astype(str).tolist() # Mengisi sel kosong karena merged cell dengan ffill()
                row_1_subheaders = df_raw.iloc[1].astype(str).str.strip().str.lower().tolist()
                
                date_col_idx = None
                
                # Cari kolom yang memiliki tanggal hari ini pada Baris 0 DAN bernilai "jumlah" pada Baris 1
                for i in range(len(row_0_dates)):
                    if today_str in row_0_dates[i] and "jumlah" in row_1_subheaders[i]:
                        date_col_idx = i
                        break
                
                if date_col_idx is None:
                    st.error(f"❌ Kolom tanggal harian untuk **{today_str}** dengan sub-kolom 'jumlah' belum dibuat oleh Admin di Google Sheet.")
                else:
                    # Update nilai "jumlah" di kolom ke-i (date_col_idx)
                    df_raw.iloc[target_row, date_col_idx] = int(jumlah_input)
                    
                    # Update nilai "alasan" di kolom tepat di kanannya (indeks + 1)
                    # Pastikan kolom di kanannya benar-benar adalah kolom "alasan"
                    if date_col_idx + 1 < len(row_1_subheaders) and "alasan" in row_1_subheaders[date_col_idx + 1]:
                        df_raw.iloc[target_row, date_col_idx + 1] = alasan_input.strip() if jumlah_input < 13 else "-"
                    else:
                        st.warning("⚠️ Kolom alasan setelah kolom jumlah tidak ditemukan sesuai format.")
                    
                    try:
                        conn.update(worksheet=TRACKING_SHEET, data=df_raw)
                        st.success(f"🎉 Sukses! Progres harian untuk PPL **{selected_ppl}** berhasil disimpan.")
                    except Exception as e:
                        st.error(f"Terjadi kesalahan saat memperbarui database: {e}")
