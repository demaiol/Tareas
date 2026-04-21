from __future__ import annotations

from dotenv import load_dotenv

from req_manager.db import create_requirement, ensure_schema
from req_manager.email_ack import EmailAckConfigError, send_acknowledgement
from req_manager.email_ingest import EmailConfigError, sync_unseen_emails


def main() -> int:
    load_dotenv()
    ensure_schema()

    try:
        items = sync_unseen_emails()
    except EmailConfigError as exc:
        print(f"[ERROR] Configuración de correo inválida: {exc}")
        return 1

    created = 0
    ack_sent = 0

    for item in items:
        req_code = create_requirement(item, actor="Sync automático")
        if not req_code:
            continue
        created += 1
        try:
            send_acknowledgement(item, req_code)
            ack_sent += 1
        except EmailAckConfigError as exc:
            print(f"[WARN] No se pudo enviar acuse de {req_code}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Error enviando acuse de {req_code}: {exc}")

    print(
        f"[OK] Correos leídos: {len(items)} | Requerimientos creados: {created} | Acuses enviados: {ack_sent}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
