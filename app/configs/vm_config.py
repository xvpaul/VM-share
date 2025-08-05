# VM_share/app/configs/vm_config.py
from pathlib import Path

# VM_SHARE_ROOT = Path(__file__).resolve().parents[0]  
ALPINE_IMAGE_NAME = 'alpine.qcow2'
ALPINE_IMAGE_PATH = str("/root" / "base_images" / "Alpine_Linux")
ALPINE_OVERLAYS_DIR = str("/root"  / "overlays" / "Alpine_Linux")
ALPINE_MEMORY = 512

NOVNC_PROXY = str(Path.home() / "noVNC/utils/novnc_proxy")
NOVNC_WEB = str(Path.home() / "noVNC")
