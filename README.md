# Gestor Ejecutivo de Requerimientos (Correo -> REQ)

Aplicación productiva para registrar y gestionar requerimientos recibidos por correo electrónico.

## Qué hace

- Se conecta por **IMAP** a tu correo corporativo.
- Lee correos **no leídos** y registra cada solicitud como un requerimiento.
- Captura:
  - Solicitante (nombre y correo)
  - Título (asunto)
  - Detalle (cuerpo del correo)
  - Número de requerimiento autogenerado (`REQ-000001`, etc.)
  - Fecha de alta
  - Fecha de vencimiento automática (+48 horas)
  - Asignado (por defecto: `Administrador`)
- Presenta un **reporte ejecutivo** con métricas y estado.
- Permite al resolutor:
  - Cargar respuesta
  - Actualizar estado (`Nuevo`, `En progreso`, `Resuelto`, `Vencido`)
  - Registrar quién resolvió

## Requisitos

- Python 3.10+
- Cuenta de correo con acceso IMAP habilitado
- App Password (recomendado) para seguridad

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Completa `.env` con tus credenciales (Gmail o IMAP).

## Configurar Gmail

La app ya soporta lectura de casilla Gmail de forma nativa.

1. Activa autenticación en dos pasos en tu cuenta Google.
2. Genera una **App Password** (16 caracteres).
3. En `.env` define:

```env
GMAIL_USER=tu_casilla@gmail.com
GMAIL_APP_PASSWORD=tu_app_password_16_caracteres
GMAIL_FOLDER=INBOX
```

Cuando estas variables existen, la app usa automáticamente `imap.gmail.com`.

En Streamlit Cloud, estas variables se cargan en **App settings -> Secrets**.

## Configurar IMAP genérico (alternativa)

```env
IMAP_HOST=imap.tuempresa.com
IMAP_USER=tu_correo@empresa.com
IMAP_PASSWORD=tu_clave_o_app_password
IMAP_FOLDER=INBOX
```

## Publicar en Streamlit Cloud

1. Sube este proyecto a un repositorio de GitHub (sin `.env` ni base local).
2. En [share.streamlit.io](https://share.streamlit.io), crea una app nueva desde ese repo.
3. Configura:
   - Main file path: `app.py`
   - Python version: 3.11 o superior
4. En **App settings -> Secrets**, pega:

```toml
GMAIL_USER = "requerimientosvistamar@gmail.com"
GMAIL_APP_PASSWORD = "TU_APP_PASSWORD_16"
GMAIL_FOLDER = "INBOX"
```

5. Guarda y reinicia la app.

## Ejecución

```bash
streamlit run app.py
```

Abre en navegador la URL que indique Streamlit (normalmente `http://localhost:8501`).

## Operación

1. En la barra lateral, presiona **Sincronizar correos no leídos**.
2. La app creará automáticamente los `REQ` nuevos (evita duplicados por `Message-ID`).
3. Revisa el reporte, filtra por estado y selecciona el `REQ`.
4. Carga respuesta y actualiza estado.

## Base de datos

Se crea automáticamente `req_manager.db` (SQLite) en el directorio del proyecto.

## Sugerencias de producción

- Usar un buzón dedicado (ej. `requerimientos@tuempresa.com`).
- Activar app password y evitar contraseñas principales.
- Ejecutar con `systemd`, Docker o servicio interno para alta disponibilidad.
- Programar sincronización automática (cron) si deseas ingestión periódica sin botón manual.
