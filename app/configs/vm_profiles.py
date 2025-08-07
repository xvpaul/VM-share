# configs/vm_profiles.py
from pathlib import Path

VM_PROFILES = {
    "alpine": {
        "overlay_dir": Path("/root/myapp/overlays/Alpine_Linux"),
        "overlay_prefix": "alpine",
        "base_image": Path("/root/myapp/base_images/Alpine_Linux/alpine.qcow2"),
        "default_memory": 1024,
    },
    "tiny": {
        "overlay_dir": Path("/root/myapp/overlays/Tiny"),
        "overlay_prefix": "tiny",
        "base_image": Path("/root/myapp/base_images/Tiny/tinycore_base.qcow2"),
        "default_memory": 1024,
    },
}
