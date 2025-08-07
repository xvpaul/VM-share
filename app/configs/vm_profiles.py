# configs/vm_profiles.py
from pathlib import Path

VM_PROFILES = {
    "alpine": {
        "overlay_dir": Path("/root/myapp/overlays/Alpine_Linux"),
        "overlay_prefix": "alpine",
        "base_image": Path("/root/myapp/base_images/Alpine_Linux/alpine.qcow2"),
        "default_memory": 1024,
    },
    "debian": {
        "overlay_dir": Path("/root/myapp/overlays/Debian"),
        "overlay_prefix": "debian",
        "base_image": Path("/root/myapp/images/debian_base.qcow2"),
        "default_memory": 1536,
    },
}
