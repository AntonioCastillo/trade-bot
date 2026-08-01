#!/usr/bin/env bash
# Instalación del bot en Rocky Linux 9 (RHEL-compatible).
# Ejecutar en el VPS como usuario con sudo. Deja el bot listo para el servicio.
#
# Uso:
#   sudo bash deploy/setup_rocky.sh
#
# Asume que el código del bot ya está en APP_DIR (git clone o scp). Ver DEPLOY.md.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tradebot}"
APP_USER="${APP_USER:-tradebot}"
PYBIN="${PYBIN:-python3.11}"

echo ">>> Instalando dependencias del sistema (Python, git, chrony)..."
dnf install -y "${PYBIN}" git chrony
# pip: ensurepip (viene con el venv) o el paquete del sistema como respaldo.
"${PYBIN}" -m ensurepip --upgrade >/dev/null 2>&1 || dnf install -y "${PYBIN}-pip" || true

echo ">>> Sincronizando el reloj (crítico para firmar peticiones a KuCoin)..."
systemctl enable --now chronyd
chronyc makestep || true

echo ">>> Creando usuario de servicio '${APP_USER}' (si no existe)..."
id -u "${APP_USER}" >/dev/null 2>&1 || useradd --system --create-home --shell /sbin/nologin "${APP_USER}"

echo ">>> Preparando ${APP_DIR}..."
if [ ! -f "${APP_DIR}/requirements.txt" ]; then
  echo "ERROR: no encuentro el código en ${APP_DIR}. Cópialo primero (git clone o scp)."
  exit 1
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
mkdir -p "${APP_DIR}/logs" "${APP_DIR}/data"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/logs" "${APP_DIR}/data"

echo ">>> Creando entorno virtual e instalando dependencias..."
sudo -u "${APP_USER}" "${PYBIN}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo ""
echo ">>> LISTO. Siguientes pasos:"
echo "  1) Crea ${APP_DIR}/.env con tus claves (chmod 600)."
echo "  2) Revisa ${APP_DIR}/config.yaml (mode: paper por defecto)."
echo "  3) Instala el servicio: sudo cp deploy/tradebot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now tradebot"
echo "  4) Logs: journalctl -u tradebot -f   y   tail -f ${APP_DIR}/logs/tradebot.log"
