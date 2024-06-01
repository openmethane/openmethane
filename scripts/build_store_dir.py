import os

import dotenv
from pathlib import Path

dotenv.load_dotenv()

def main():
    store_dir = Path(os.getenv('STORE_DIR'))

    (store_dir / "archive").mkdir(exist_ok=True, parents=True)
    (store_dir / "inputs").mkdir(exist_ok=True, parents=True)
    (store_dir / "templates").mkdir(exist_ok=True, parents=True)

    # symlink in the mcip directory
    os.symlink(store_dir / "mcip", os.environ["MCIP_PATH"])

