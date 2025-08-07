# configs/vm_profiles.py

from pathlib import Path

VM_PROFILES = {
    "alpine": {
        "base_image": Path("/root/myapp/base_images/alpine.qcow2"),
        "overlay_dir": Path("/root/myapp/overlays/Alpine_Linux"),
        "overlay_prefix": "alpine",
        "default_memory": 512,
    },
    "ubuntu": {
        "base_image": Path("/root/myapp/base_images/alpine.qcow2"),
        "overlay_dir": Path("/root/myapp/overlays/Alpine_Linux"),
        "overlay_prefix": "ubuntu",
        "default_memory": 2048,
    },
}
