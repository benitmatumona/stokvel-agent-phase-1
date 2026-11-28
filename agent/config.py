import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

TEST_MODE = os.getenv("STOKVEL_TEST_MODE", "0") == "1"
ANCHOR_TEST_COMMAND = os.getenv("ANCHOR_TEST_COMMAND", "anchor test")
DEPLOY_COMMAND = os.getenv("DEPLOY_COMMAND", "yarn -s ts-node scripts/deploy_group.ts")

# Optional persistence. Without both values, sessions live in memory only.
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # service_role key; server-side only
