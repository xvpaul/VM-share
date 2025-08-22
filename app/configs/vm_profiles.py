# app/configs/vm_profiles.py
from pathlib import Path

VM_PROFILES = {
    "alpine": {
        "overlay_dir": Path("/root/myapp/overlays/Alpine"),
        "overlay_prefix": "alpine",
        "base_image": Path("/root/myapp/base_images/Alpine/alpine-base.qcow2"),
        "default_memory": 1024,
    },
    "lubuntu": {
        "overlay_dir": Path("/root/myapp/overlays/lubuntu"),
        "overlay_prefix": "lubuntu",
        "base_image": Path("/root/myapp/base_images/Lubuntu/lubuntu-base.qcow2"),
        "default_memory": 2048,
    },
    "ubuntu": {
        "overlay_dir": Path("/root/myapp/overlays/Ubuntu"),
        "overlay_prefix": "ubuntu",
        "base_image": Path("/root/myapp/base_images/Ubuntu/ubuntu20-base.qcow2"),
        "default_memory": 2048,
    },
    "custom": {
        "base_image": Path("/Users/soledaco/Desktop/storage/{uid}.iso"),
    }
}
