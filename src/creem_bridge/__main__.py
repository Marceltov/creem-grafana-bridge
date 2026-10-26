import logging
import os
import sys

from .config import Config
from .server import make_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
try:
    cfg = Config.from_env(os.environ)
except ValueError as e:
    sys.exit(f"creem-grafana-bridge: {e}")
logging.info("serving %d store(s) on port %d", len(cfg.stores), cfg.port)
make_server(cfg).serve_forever()
