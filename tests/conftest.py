
import sys
from pathlib import Path

SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "customer_profile"
)

sys.path.insert(0, str(SERVICE_PATH))
