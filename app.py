import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date
from streamlit_google_auth import Authenticate

st.set_page_config(page_title="PPL Monitoring - Koordinator View", page_icon="📝", layout="wide")

# =============================================================================
# 1. GOOGLE AUTHENTICATION LAYER
# =============================================================================
auth = Authenticate(secret_credentials_path=None)
auth.check_authentification()

if not st.session_state.get("connected", False):
    st.title("🔐 Monitoring Progres Lapangan")
    st.info("Silahkan login menggunakan Akun Google Koordinator Anda untuk mengakses sistem.")
    st.stop()

user_email = st.session_state.get("user_info", {}).get("email", "").lower().strip()
user_name = st.session_state.get("user_info", {}).get("name", "")

# =============================================================================
# 2. DATABASE CONNECTION (GOOGLE SHEETS)
# =============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)
TRACKING_SHEET = "Progress"
USER_SHEET = "user"

try:
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

# Get the clean identity name of the Koordinator
nama_koordinator = koordinator_matches.iloc[0]['Koordinator']

with st.sidebar:
    st.subheader("Profil Koordinator")
    st.write(f"Nama: **{nama_koordinator}**")
    st.write(f"Email: *{user_email}*")
    st.markdown("---")
    if st.button("🚪 Keluar / Log Out", use_container_width=True):
        auth.logout()
        st.rerun()

st.title(f"📊 Panel Input Koordinator: {nama_koordinator}")
st.markdown("Silahkan tentukan PML dan PPL untuk menginput progres harian.")

# Filter hierarchy dynamically based on this Koordinator
filtered_users = df_users[df_users['Koordinator'] == nama_koordinator]
available_pml = sorted(filtered_users['PML'].dropna().unique().tolist())

# =============================================================================
# 4. INTERACTIVE ENTRY FORM
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
            # Locate the PPL row coordinate in the tracking sheet matrix (Column 3 = Nama PPL)
            ppl_match = df_raw[df_raw[3].astype(str).str.upper().str.strip() == selected_ppl.upper().strip()]
            
            if ppl_match.empty:
                st.error(f"❌ Nama PPL '{selected_ppl}' tidak ditemukan di lembar data '{TRACKING_SHEET}'.")
            else:
                target_row = ppl_match.index[0]
                row_1_dates = df_raw.iloc[1].astype(str).tolist()
                date_col_idx = next((i for i, cell in enumerate(row_1_dates) if today_str in cell), None)
                
                if date_col_idx is None:
                    st.error(f"❌ Kolom tanggal harian untuk **{today_str}** belum dibuat oleh Admin di Google Sheet.")
                else:
                    # Update cell coordinates
                    df_raw.iloc[target_row, date_col_idx] = int(jumlah_input)
                    df_raw.iloc[target_row, date_col_idx + 1] = alasan_input.strip() if jumlah_input < 13 else "-"
                    
                    try:
                        conn.update(worksheet=TRACKING_SHEET, data=df_raw)
                        st.success(f"🎉 Sukses! Progres harian untuk PPL **{selected_ppl}** berhasil disimpan.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Terjadi kesalahan saat memperbarui database: {e}")