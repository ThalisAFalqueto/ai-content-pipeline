import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ["ELEVENLABS_VOICE_ID"]

YOUTUBE_OAUTH_CLIENT_SECRET_FILE = ROOT_DIR / os.environ["YOUTUBE_OAUTH_CLIENT_SECRET_FILE"]
YOUTUBE_OAUTH_TOKEN_FILE = ROOT_DIR / os.environ["YOUTUBE_OAUTH_TOKEN_FILE"]

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = DATA_DIR / "output"
TOPICS_FILE = DATA_DIR / "topics.md"
IDEATION_PROMPT_FILE = ROOT_DIR / "prompts" / "ideation_system_prompt.md"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
