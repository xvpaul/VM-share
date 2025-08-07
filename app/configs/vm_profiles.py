# configs/vm_profiles.py

VM_PROFILES = {
    "alpine": {
        "base_image": "/root/myapp/base_images/alpine.qcow2",
        "overlay_dir": "/root/myapp/overlays/Alpine_Linux",
        "overlay_prefix": "alpine",
        "default_memory": 512,
    },
    "ubuntu": {
        "base_image": "/root/myapp/base_images/alpine.qcow2",
        "overlay_dir": "/root/myapp/overlays/Alpine_Linux",
        "overlay_prefix": "ubuntu",
        "default_memory": 2048,
    },
    "peppermint": {
    "base_image": "/root/myapp/base_images/Peppermint/peppermint.qcow2",
    "overlay_dir": "/root/myapp/overlays/Peppermint",
    "overlay_prefix": "peppermint",
    "default_memory": 1024,
    }
}
