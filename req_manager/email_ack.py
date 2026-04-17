from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from req_manager.db import EmailRequest


class EmailAckConfigError(RuntimeError):
    pass


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _resolve_smtp_config() -> tuple[str, int, str, str, bool]:
    # Modo Gmail directo.
    gmail_user = _optional_env("GMAIL_USER")
    gmail_password = _optional_env("GMAIL_APP_PASSWORD")
    if gmail_user and gmail_password:
        return ("smtp.gmail.com", 465, gmail_user, gmail_password, True)

    # Modo SMTP genérico.
    host = _optional_env("SMTP_HOST")
    user = _optional_env("SMTP_USER")
    password = _optional_env("SMTP_PASSWORD")
    port = int(_optional_env("SMTP_PORT") or "465")
    use_ssl = (_optional_env("SMTP_SSL") or "true").lower() in {
        "1",
        "true",
        "yes",
    }

    if not host or not user or not password:
        raise EmailAckConfigError(
            "No hay configuración SMTP para enviar acuses. "
            "Configura GMAIL_USER/GMAIL_APP_PASSWORD o SMTP_HOST/SMTP_USER/SMTP_PASSWORD."
        )

    return (host, port, user, password, use_ssl)


def _build_ack_message(to_name: str, to_email: str, req_code: str, title: str) -> EmailMessage:
    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = f"Recepción de requerimiento {req_code}"

    greeting_name = to_name.strip() if to_name.strip() else "solicitante"
    message.set_content(
        (
            f"Estimado/a {greeting_name},\n\n"
            "Gracias por tu requerimiento.\n"
            f"Hemos registrado tu solicitud con el número {req_code}.\n"
            "Nuestro equipo la revisará y gestionará a la brevedad.\n\n"
            "Saludos,\n"
            "Administracion Comunidad Vistamar"
        )
    )

    message.add_alternative(
        (
            f"<p>Estimado/a <strong>{greeting_name}</strong>,</p>"
            "<p>Gracias por tu requerimiento.</p>"
            f"<p>Hemos registrado tu solicitud con el número <strong>{req_code}</strong>.</p>"
            "<p>Nuestro equipo la revisará y gestionará a la brevedad.</p>"
            "<p>Saludos,<br/>Administracion Comunidad Vistamar</p>"
            f"<hr/><p><small>Título recibido: {title}</small></p>"
        ),
        subtype="html",
    )

    return message


def send_acknowledgement(request: EmailRequest, req_code: str) -> None:
    if not request.requester_email or "@" not in request.requester_email:
        return

    host, port, smtp_user, smtp_password, use_ssl = _resolve_smtp_config()
    msg = _build_ack_message(
        to_name=request.requester_name,
        to_email=request.requester_email,
        req_code=req_code,
        title=request.title,
    )
    msg["From"] = smtp_user

    if use_ssl:
        with smtplib.SMTP_SSL(host=host, port=port, timeout=30) as smtp:
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host=host, port=port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
