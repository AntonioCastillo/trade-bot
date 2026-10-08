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

## 8. Actualizar el bot a mano
```bash
cd /opt/tradebot
sudo -u tradebot git pull
sudo systemctl restart tradebot
```
Si cambian las dependencias: `sudo -u tradebot /opt/tradebot/.venv/bin/pip install -r /opt/tradebot/requirements.txt`

Usa siempre `sudo -u tradebot` para git: si haces `git pull` como root, los ficheros
nuevos quedan a nombre de root y el despliegue automático (§9) deja de poder actualizar.

## 9. Despliegue automático (el VPS consulta GitHub)

El VPS mira GitHub cada 5 minutos; GitHub no entra en el VPS ni guarda ninguna clave suya.

```
rama de trabajo ──PR──▶ main ──tests OK──▶ production ──(≤5 min)──▶ VPS: pull + reinicio + comprobación
        tests en el PR         GitHub Actions            tradebot-autodeploy.timer
```

1. **Tests en GitHub** (`.github/workflows/tests.yml`): corren en cada PR y en cada push a `main`.
2. **Rama `production`**: la mueve la propia Action al commit de `main` que ha pasado los
   tests. Nunca se toca a mano.
3. **El VPS sigue `production`** (`deploy/autodeploy.sh`, cada 5 min). Si hay commit nuevo:
   `git merge --ff-only`, `pip install` si cambió `requirements.txt` o `pyproject.toml`,
   reinicio y comprobación de que aparece `Daemon iniciado` y el servicio sigue vivo 30 s.
4. **Si el bot no arranca**, vuelve al commit anterior, reinicia y no reintenta ese commit.
5. **Aviso por Telegram** de cada despliegue, fallo u omisión (usa el token del `.env` del bot).

Qué **no** hace, a propósito:
- No despliega entre 5 min antes y 10 min después de un cierre de vela de 4 h (00, 04, 08…
  UTC): es cuando el bot compra. Lo aplaza a la siguiente vuelta.
- No despliega si hay ficheros del repo modificados a mano en el VPS: avisa y espera.
- No reinstala los ficheros de `deploy/` (unidades de systemd y el propio script): si
  cambian, el aviso lo dice y hay que repetir el paso 2 de abajo.
- No retrocede: si el VPS va por delante de `production`, no hace nada.

El reinicio es ordenado: el bot atiende la señal de parada, termina el ciclo en curso (no
corta una orden a medias) y sale. Las posiciones abiertas se readoptan al arrancar.

### Instalación (una sola vez, en el VPS)
```bash
# 1. El usuario del bot debe ser dueño del repo y tenerlo limpio
sudo chown -R tradebot:tradebot /opt/tradebot
sudo -u tradebot git -C /opt/tradebot status --short --untracked-files=no   # no debe listar nada

# 2. Script (copiado fuera del repo) y unidades de systemd
sudo install -m 755 /opt/tradebot/deploy/autodeploy.sh /usr/local/sbin/tradebot-autodeploy
sudo cp /opt/tradebot/deploy/tradebot-autodeploy.service /opt/tradebot/deploy/tradebot-autodeploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradebot-autodeploy.timer

# 3. Probar una vuelta a mano y ver qué dice
sudo systemctl start tradebot-autodeploy
journalctl -u tradebot-autodeploy -n 20 --no-pager
systemctl list-timers tradebot-autodeploy.timer
```
Sin commit nuevo no escribe nada: es lo normal.

### Uso
```bash
journalctl -u tradebot-autodeploy -n 50 --no-pager        # historial de despliegues
sudo systemctl disable --now tradebot-autodeploy.timer    # pausar el despliegue automático
sudo systemctl enable --now tradebot-autodeploy.timer     # reanudarlo
sudo rm /var/lib/tradebot-autodeploy/failed               # permitir reintentar un commit que falló
```
Ajustes opcionales en `/etc/tradebot-autodeploy.conf` (formato `VARIABLE=valor`): `BRANCH`,
`GUARD_BEFORE_MIN`, `GUARD_AFTER_MIN`, `HEALTH_WAIT_S`, `HEALTH_HOLD_S`.

Para deshacer un cambio ya desplegado: `git revert` del commit en un PR a `main`; se
despliega como cualquier otro.

> ⚠️ Con esto, **todo lo que entra en `main` y pasa los tests se pone a operar con dinero
> real en minutos**, incluidos los cambios de `config.yaml`. Los tests no cubren la conexión
> real con KuCoin. Protege la cuenta de GitHub con 2FA: quien pueda escribir en `main`
> puede ejecutar código en el VPS con las claves del exchange.

## Notas
- **Firewall:** no requiere puertos entrantes; solo HTTPS saliente (por defecto OK).
- **Reloj:** `chronyd` queda activo; el bot además ajusta la diferencia con KuCoin.
- **SELinux:** el servicio escribe solo en `/opt/tradebot`. Si SELinux bloqueara
  algo, revisa `journalctl -u tradebot` y `ausearch -m avc -ts recent`.
