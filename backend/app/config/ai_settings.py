import os
import logging
from app.config import settings

logger = logging.getLogger("jam_analyzer")

# ── Centralized AI Model Configurations ─────────────────────────────────────────

# Centralized Groq configurations
DEFAULT_GROQ_MODEL = settings.GROQ_MODEL or "openai/gpt-oss-120b"
TOPIC_GENERATOR_MODEL = settings.TOPIC_GENERATOR_MODEL or "openai/gpt-oss-120b"

# Centralized Fallback sequence when primary model fails
GROQ_FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant"
]
