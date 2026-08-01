# Despliegue en Rocky Linux (VPS) con systemd

Guía para dejar el bot corriendo 24/7 en un VPS Rocky Linux 9. El bot solo hace
peticiones **salientes** a KuCoin: **no hay que abrir ningún puerto**.

## 1. Copiar el código al VPS

> ⚠️ **No subas `.env` ni un `.env.example` con claves reales.** Las credenciales
> van solo en `.env` (que se crea en el VPS, paso 3). Si usas git, revisa que
> `.env.example` esté vacío de secretos antes de hacer commit.

**Opción A — `scp` (viene en Windows 10/11, PowerShell):**
```powershell
scp -r C:\entornoweb\workspace\trade-bot usuario@TU_VPS:~/tradebot-upload
```
En el VPS, limpia runtime y mueve a `/opt`:
```bash
rm -rf ~/tradebot-upload/.venv ~/tradebot-upload/data ~/tradebot-upload/logs
find ~/tradebot-upload -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
sudo mkdir -p /opt/tradebot && sudo cp -r ~/tradebot-upload/. /opt/tradebot/
```

**Opción B — git (repo PRIVADO; ideal para actualizar).** El `.gitignore` ya
excluye `.env`, `data`, `logs`, `.venv`:
```bash
sudo dnf install -y git && sudo git clone <tu-repo-privado> /opt/tradebot
```

**Opción C — WinSCP:** cliente gráfico SFTP (arrastrar y soltar).

## 2. Instalar (en el VPS)
```bash
cd /opt/tradebot
sudo bash deploy/setup_rocky.sh
```
Instala Python 3.11, crea el usuario de servicio `tradebot`, el entorno virtual,
las dependencias, y **sincroniza el reloj** (chrony — clave para firmar KuCoin).

## 3. Credenciales y config
```bash
sudo -u tradebot cp /opt/tradebot/.env.example /opt/tradebot/.env
sudo -u tradebot nano /opt/tradebot/.env       # pon tus claves KuCoin + Telegram
sudo chmod 600 /opt/tradebot/.env
sudo -u tradebot nano /opt/tradebot/config.yaml # revisa (mode: paper por defecto)
```

## 4. Instalar el servicio
```bash
sudo cp /opt/tradebot/deploy/tradebot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradebot
```

Arranca en **PAPER** (simulación) por defecto. Se reinicia solo si cae.

## 5. Monitorizar
```bash
systemctl status tradebot                 # estado
journalctl -u tradebot -f                 # salida en vivo (stdout)
tail -f /opt/tradebot/logs/tradebot.log   # log del bot
tail -f /opt/tradebot/logs/heads/*.log    # log por cabeza
cat /opt/tradebot/data/report.txt         # informe con métricas
```

## 6. Parar / reiniciar
```bash
sudo systemctl stop tradebot
sudo systemctl restart tradebot
```

## 7. Pasar a REAL (headless)
En un VPS no hay teclado para la confirmación, así que se usa una variable de
entorno **con la frase exacta**. Solo hazlo cuando quieras operar con dinero:

1. Pon `mode: live` en `config.yaml` y asegúrate de tener las 3 claves en `.env`.
2. Edita el servicio y descomenta la línea de confirmación:
   ```bash
   sudo systemctl edit --full tradebot
   # descomenta:  Environment=TRADEBOT_LIVE_CONFIRM=SI OPERAR EN REAL
   sudo systemctl daemon-reload && sudo systemctl restart tradebot
   ```
   Sin esa variable, **siempre arranca en PAPER** (seguro por defecto).

## 8. Actualizar el bot
```bash
# En tu PC: rsync de nuevo (paso 1). En el VPS:
sudo systemctl restart tradebot
```
Si cambian las dependencias: `sudo -u tradebot /opt/tradebot/.venv/bin/pip install -r /opt/tradebot/requirements.txt`

## Notas
- **Firewall:** no requiere puertos entrantes; solo HTTPS saliente (por defecto OK).
- **Reloj:** `chronyd` queda activo; el bot además ajusta la diferencia con KuCoin.
- **SELinux:** el servicio escribe solo en `/opt/tradebot`. Si SELinux bloqueara
  algo, revisa `journalctl -u tradebot` y `ausearch -m avc -ts recent`.
