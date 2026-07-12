import logging
import sys
from pathlib import Path

# 1. Define base directories for optional physical log file outputs
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE_PATH = LOG_DIR / "medmemory_api.log"

# 2. Design a clean, structured log string layout tracking timestamps and execution context
LOG_FORMAT = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] ➔ %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_centralized_logging():
    """
    Configures structural log managers, binds console stream handlers, 
    and handles file-write log outputs.
    """
    # 3. Create the core logging configuration matrix
    logging.basicConfig(
        level=logging.INFO,  # Captures Info, Warnings, Errors, and Critical events
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=[
            # Console Handler: Outputs logs directly to your terminal screen
            logging.StreamHandler(sys.stdout),
            # File Handler: Permanently saves logs on disk for production audits
            logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
        ]
    )
    
    # 4. Suppress noisy third-party debug logs from external database drivers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("prisma").setLevel(logging.INFO)

# Execute the registration hook when the package initializes
setup_centralized_logging()

# Export a base instantiation handle for app files to inherit
logger = logging.getLogger("MedMemory_Core")
