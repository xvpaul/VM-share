# VM_share
uvicorn main:app --reload
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
