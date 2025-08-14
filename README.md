# VM Access Platform  
_Remote VM Management in the Browser_  

---

## 📌 Overview  
The **VM Access Platform** allows users to launch and interact with **fully operable virtual machines directly in their web browser**.  
No local installation is required — just open the app, log in, and start using your VM through a **noVNC-powered graphical desktop**. You can run any operating system supported by QEMU and noVNC, though the available choices on [vmsl.ru](https://vmsl.ru) are currently limited by the hosting server’s hardware and configuration.

**Built for**:
- Safe sandboxing and experimentation with Linux distributions  
- Quick access to Linux environments for OS-specific tasks  

---

## ✨ Features  
- **Fully Operable Remote VMs** – Run Debian, Ubuntu, or other distros with GUI support.  
- **Browser-Based GUI Access** – Real-time VM desktop via **noVNC** (including opening a terminal emulator inside the VM’s GUI).  
- **Custom Authentication** – Planned email-based sign-up & login for enhanced security.  
- **Scalable Architecture** – Tested with up to 100 simultaneous active users (to-do, hope it's gonna workout).  
- **Light/Dark Theme Toggle** – Comfortable, customizable user interface (to-do actually).  

---

## 🛠 Tech Stack  
**Backend:** [FastAPI](https://fastapi.tiangolo.com/), [Unix sockets](https://www.baeldung.com/linux/unix-socket), [Websockify](https://github.com/novnc/websockify)  
**Frontend:** HTML, [Tailwind CSS](https://tailwindcss.com/), JavaScript  
**Virtualization:** [QEMU](https://www.qemu.org/) (KVM optional), [noVNC](https://novnc.com/)  
**Database:** [PostgreSQL](https://www.postgresql.org/)  

---

## 🏗 Architecture  
```mermaid
flowchart LR
    User --> Browser
    Browser --> FastAPI
    FastAPI --> QEMU
    QEMU --> noVNC
    FastAPI --> PostgreSQL
