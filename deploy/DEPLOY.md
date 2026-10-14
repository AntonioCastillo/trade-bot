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

### Pausar una cabeza a mano
```bash
cd /opt/tradebot
sudo -u tradebot .venv/bin/python scripts/manage.py pauses                       # qué está en pausa
sudo -u tradebot .venv/bin/python scripts/manage.py pause grid_lateral --days 15 # 15 días
sudo -u tradebot .venv/bin/python scripts/manage.py pause grid_lateral           # hasta que la reanudes
sudo -u tradebot .venv/bin/python scripts/manage.py resume grid_lateral          # levanta la manual y la de strikes
```
Surte efecto sin reiniciar. Solo bloquea entradas nuevas: las posiciones abiertas se siguen
gestionando. Se ve en el gist (`paused_heads`) y en el informe de Telegram.

### Stops de emergencia en el exchange
Por defecto están apagados (`engine.exchange_stops: false`). Protegen las posiciones si el
bot o el servidor se caen: una orden de stop en KuCoin por posición, un 2% por debajo del
stop del bot. Para activarlos:

1. Comprobar que las llamadas funcionan con tu cuenta (no compra ni vende nada: pone una
   orden de stop mínima con el disparo un 50% por debajo del precio y la cancela):
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-stops
   ```
2. Solo si termina con «todo correcto», poner `exchange_stops: true` en `config.yaml`
   (por PR, como cualquier cambio).
3. Tras el despliegue, el log debe decir `Stops de emergencia en el exchange ACTIVOS` y cada
   posición del gist debe traer `exchange_stop` con su precio de disparo.

Si alguna vez llega el aviso «Órdenes de stop sin posición que no puedo cancelar»,
cancélalas a mano en KuCoin: podrían vender una compra posterior de esa moneda.

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

## 10. Exchange: Bybit EU (migración desde KuCoin, octubre de 2026)

KuCoin global no tiene autorización para dar servicio en España desde el fin del periodo
transitorio de MiCA (1 de julio de 2026) y puede restringir la cuenta sin aviso. Desde la
migración, `config.yaml` opera en Bybit EU: USDC en vez de USDT, sin ETC (no cotiza contra
USDC) y con la comisión real de la cuenta (0,25%). Claves en `.env`: `BYBIT_API_KEY` y
`BYBIT_API_SECRET`, de una clave sin permiso de retirada y limitada a la IP del VPS.

### Verificaciones (hechas el 2026-10-14 con la cuenta real)
Sin operar (`verify-account`), compra y venta real de 5 USDC (`verify-api`) y órdenes de stop
(`verify-stops`, siete de siete). Para repetirlas, por ejemplo con claves nuevas:
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-account
```
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-api --usd 5
```
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-stops
```

### El cambio
1. Pausar las cuatro cabezas en KuCoin y esperar a que las posiciones abiertas se cierren solas
   (hecho el 2026-10-14):
   ```bash
   cd /opt/tradebot && for h in tendencia_alcista volumen_explosivo grid_lateral capitulacion; do sudo -u tradebot .venv/bin/python scripts/manage.py pause $h; done
   ```
2. Sin posiciones abiertas, mover el saldo a Bybit EU en USDC (lo hace el operador).
3. Si el saldo que llega es claramente menor que el máximo histórico de equity del bot,
   borrarlo antes del paso 4, o el disyuntor global (15%) lo cerraría todo al arrancar:
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/reset_ath.py
   ```
4. Fusionar el PR que pone `config.yaml` en Bybit EU. El despliegue automático reinicia el bot.
5. Comprobar el arranque: el log debe decir `Stops de emergencia en el exchange ACTIVOS` y el
   gist `"exchange": "bybiteu"` y `"quote": "USDC"`.
6. Levantar las pausas (viven en la base de datos y sobreviven al cambio):
   ```bash
   cd /opt/tradebot && for h in tendencia_alcista volumen_explosivo grid_lateral capitulacion; do sudo -u tradebot .venv/bin/python scripts/manage.py resume $h; done
   ```

**Protección:** si al arrancar en Bybit quedan posiciones registradas en USDT, el bot **no
arranca** (reconciliarlas contra la cuenta nueva las daría por vendidas) y el despliegue
automático vuelve a la versión anterior. Mientras tanto llegarán varios avisos de «Bot CAÍDO».

**Volver a KuCoin:** revertir ese PR, con las posiciones de Bybit cerradas y el saldo de vuelta.

**Simulaciones:** `scripts/livesim.py` usa las velas del exchange de `config.yaml`, que en
Bybit EU solo llegan a octubre de 2025. Para estudios largos: `--exchange kucoin --quote USDT`.

## 11. OKX Europa con señales de otro exchange (preparado, sin activar)

OKX Europa cobra menos que Bybit EU (al contado, a mercado: 0,10% con la cuenta de derivados
X-Perps abierta, 0,20% sin ella), pero su volumen en USDC es muy bajo y las cabezas que miran
el volumen (`volumen_explosivo`, `capitulacion`) ven picos donde no los hay. Por eso el bot
puede sacar las velas de las señales de un mercado líquido (`data_exchange`, solo datos
públicos) y operar en OKX: órdenes, saldos y precios de las salidas siguen siendo de OKX.

### Verificar la cuenta (sin tocar el bot real)
1. Abrir la cuenta en OKX Europa y, si se quiere el 0,10%, la cuenta de derivados X-Perps
   (pide un test de conveniencia). El bot no opera derivados.
2. Clave de API con **lectura y trading, sin retirada**, limitada a la IP del VPS. OKX pide
   además una passphrase que eliges al crearla. En `.env`:
   `OKX_API_KEY=...`, `OKX_API_SECRET=...` y `OKX_API_PASSPHRASE=...`.
3. Las tres verificaciones, con la configuración actual pero contra OKX:
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-account --exchange myokx
   ```
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-api --usd 10 --exchange myokx
   ```
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-stops --exchange myokx
   ```
   Las órdenes de stop de OKX son de otro tipo (algo "conditional") y no se han probado en
   real: si `verify-stops` falla, hay que corregir el código antes de seguir.

### El cambio
Igual que en la sección 10 (pausar, cerrar posiciones, mover el saldo), con un PR que ponga en
`config.yaml`: `exchange: myokx`, `engine.fee_pct` con la comisión que muestre
`verify-account`, y la fuente de señales con su respaldo:
```yaml
data_exchange: kucoin            # principal: con la que se ajustó la configuración
data_quote: USDT
data_fallback_exchange: binance  # si KuCoin deja de responder
data_fallback_quote: USDT
```
Si KuCoin falla 3 veces seguidas, las velas salen de Binance durante 30 minutos y luego se
vuelve a probar KuCoin; llega un aviso por Telegram en cada cambio y el gist muestra la fuente
activa (`data_source`). Cambiar de fuente cambia algunas señales (en `volumen_explosivo`,
aproximadamente la mitad de las compras); las ventas no dependen de la fuente.

**Simular antes:** `python scripts/livesim.py --combined --signal-exchange binance --signal-quote USDT`
(con `--exchange myokx --quote USDC` para usar sus precios).

## Notas
- **Firewall:** no requiere puertos entrantes; solo HTTPS saliente (por defecto OK).
- **Reloj:** `chronyd` queda activo; el bot además ajusta la diferencia con el exchange.
- **SELinux:** el servicio escribe solo en `/opt/tradebot`. Si SELinux bloqueara
  algo, revisa `journalctl -u tradebot` y `ausearch -m avc -ts recent`.
