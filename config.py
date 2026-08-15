import os
from dotenv import load_dotenv
from supabase import create_client
import google.generativeai as genai

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Use the service_role key on the backend: Flask already handles login/session
# security itself, so the server is trusted to bypass Storage/DB RLS policies.
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Separate client using the anon key, kept for auth calls (signup/login) only.
supabase_auth_client = create_client(SUPABASE_URL, SUPABASE_KEY)

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

STORAGE_BUCKET = "documents"  # create this bucket in Supabase Storage dashboard