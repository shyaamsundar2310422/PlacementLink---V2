import smtplib
from email.message import EmailMessage

from config import Config


def is_email_configured():
    return bool(Config.SMTP_HOST and Config.SMTP_PORT and Config.SMTP_USER and Config.SMTP_PASSWORD and Config.MAIL_FROM)


def send_email(recipient, subject, body):
    if not recipient or not is_email_configured():
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = Config.MAIL_FROM
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return False


def send_application_status_email(recipient, student_name, company_name, job_title, new_stage):
    subject = f"Application Status Update: {company_name} - {job_title}"
    body = (
        f"Hello {student_name},\n\n"
        f"Your application status has been updated by the placement team.\n\n"
        f"Company: {company_name}\n"
        f"Role: {job_title}\n"
        f"New Status: {new_stage}\n\n"
        f"Please log in to PlacementLink to view the latest details.\n\n"
        f"Regards,\n"
        f"Placement Cell"
    )
    return send_email(recipient, subject, body)
