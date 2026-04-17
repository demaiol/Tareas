from __future__ import annotations

import email
import imaplib
import os
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr
from typing import Iterable

from req_manager.db import EmailRequest

try:
    import streamlit as st
except Exception:  # noqa: BLE001
    st = None


class EmailConfigError(RuntimeError):
    pass


def _optional_env(name: str) -> str | None:
    value = _get_config_value(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_config_value(name: str) -> str | None:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    if st is not None:
        try:
            secret_value = st.secrets.get(name)
            if secret_value is not None:
                return str(secret_value)
        except Exception:  # noqa: BLE001
            return None

    return None


def _resolve_imap_config() -> tuple[str, str, str, str, str]:
    # Modo Gmail directo (preferido cuando están definidas estas variables).
    gmail_user = _optional_env("GMAIL_USER")
    gmail_password = _optional_env("GMAIL_APP_PASSWORD")
    gmail_folder = _optional_env("GMAIL_FOLDER") or "INBOX"
    if gmail_user and gmail_password:
        return ("Gmail", "imap.gmail.com", gmail_user, gmail_password, gmail_folder)

    # Modo IMAP genérico.
    host = _env("IMAP_HOST")
    user = _env("IMAP_USER")
    password = _env("IMAP_PASSWORD")
    folder = _optional_env("IMAP_FOLDER") or "INBOX"
    return ("IMAP", host, user, password, folder)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _extract_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
        return ""

    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def _build_request(msg: Message) -> EmailRequest:
    sender_name, sender_email = parseaddr(msg.get("From", ""))
    sender_name = _decode_header(sender_name) or sender_email.split("@")[0]
    subject = _decode_header(msg.get("Subject", "(Sin asunto)"))
    body = _extract_body(msg)

    # Limitamos para mantener performance del reporte.
    detail = body[:8000] if body else "No se recibió detalle en el cuerpo del correo."

    return EmailRequest(
        requester_name=sender_name,
        requester_email=sender_email or "desconocido@desconocido",
        title=subject,
        detail=detail,
        source_message_id=msg.get("Message-ID"),
    )


def _env(name: str) -> str:
    value = (_get_config_value(name) or "").strip()
    if not value:
        raise EmailConfigError(
            f"Falta {name}. Revisa .env o Streamlit Secrets."
        )
    return value


def sync_unseen_emails() -> list[EmailRequest]:
    provider, host, user, password, folder = _resolve_imap_config()

    imap = imaplib.IMAP4_SSL(host)
    try:
        imap.login(user, password)
    except imaplib.IMAP4.error as e:
        raise EmailConfigError(
            f"No fue posible autenticarse en {provider}. Verifica usuario/clave y configuración IMAP."
        ) from e

    try:
        status, _ = imap.select(folder)
        if status != "OK":
            raise RuntimeError(f"No se pudo abrir la bandeja {folder}")

        status, msg_nums = imap.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("No se pudo consultar correos no leídos")

        parsed_requests: list[EmailRequest] = []
        for num in _iter_message_numbers(msg_nums):
            status, data = imap.fetch(num, "(RFC822)")
            if status != "OK" or not data:
                continue

            for part in data:
                if isinstance(part, tuple):
                    raw_email = part[1]
                    msg = email.message_from_bytes(raw_email)
                    parsed_requests.append(_build_request(msg))

            imap.store(num, "+FLAGS", "\\Seen")

        return parsed_requests
    finally:
        imap.close()
        imap.logout()


def _iter_message_numbers(msg_nums: Iterable[bytes]) -> Iterable[bytes]:
    for chunk in msg_nums:
        for num in chunk.split():
            if num.strip():
                yield num
