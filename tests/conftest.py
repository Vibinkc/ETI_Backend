import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve the env file against the backend root rather than the working
# directory, so the suite behaves the same whether pytest is invoked from
# eti_backend/ or from the repository root (as pre-commit does).
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Load .env.test instead of .env when testing
env_file = ".env.test" if os.getenv("ENV_MODE") == "test" else ".env"
load_dotenv(BACKEND_ROOT / env_file)  # Overrides system env vars with file contents
