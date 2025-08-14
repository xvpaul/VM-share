# /app/methods/auth/email_verification.py
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid, formatdate

class SMTPMailer:
    def __init__(self, host, port=587, username=None, password=None, use_starttls=True, timeout=30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_starttls = use_starttls
        self.timeout = timeout
        self.smtp = None

    def __enter__(self):
        context = ssl.create_default_context()
        self.smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        self.smtp.ehlo()
        if self.use_starttls:
            self.smtp.starttls(context=context)
            self.smtp.ehlo()
        if self.username and self.password:
            self.smtp.login(self.username, self.password)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.smtp:
                self.smtp.quit()
        finally:
            self.smtp = None

    def send(self, subject, sender, recipients, text=None, html=None, attachments=None, reply_to=None, message_id=None):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients) if isinstance(recipients, (list, tuple)) else recipients
        msg["Date"] = formatdate(localtime=True)
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Message-ID"] = message_id or make_msgid(domain=sender.split("@")[-1])

        # Text/HTML bodies (multipart/alternative)
        if html and text:
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
        elif html:
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(text or "")

        # Attachments: list of (filename, bytes, mimetype)
        for att in attachments or []:
            fname, data, mimetype = att
            maintype, subtype = (mimetype.split("/", 1) + ["octet-stream"])[:2]
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

        self.smtp.send_message(msg)
        return msg["Message-ID"]

# Example usage
if __name__ == "__main__":
    with SMTPMailer(
        host="mail.yourdomain.com",
        port=587,                 # or 465 for implicit TLS
        username="you@yourdomain.com",
        password="YOUR_SMTP_PASSWORD",
        use_starttls=True
    ) as mailer:
        mailer.send(
            subject="Hello from my domain",
            sender="you@yourdomain.com",
            recipients=["friend@example.com"],
            text="Plain text body",
            html="<p><b>Hello</b> from my domain!</p>"
        )
