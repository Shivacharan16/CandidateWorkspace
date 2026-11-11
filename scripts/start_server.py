import sys
from pathlib import Path

# Add project root to sys.path first
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from backend.config import API_HOST, API_PORT
from backend.storage.db import init_db

def main():
    print("[*] Initializing Database Schema...")
    init_db()
    print(f"[*] Starting CDC Pipeline Server on http://{API_HOST}:{API_PORT}")
    print(f"[*] Open http://localhost:{API_PORT} in your browser to view the Operations Dashboard.")
    uvicorn.run("backend.api.routes:app", host=API_HOST, port=API_PORT, reload=False)

if __name__ == "__main__":
    main()
