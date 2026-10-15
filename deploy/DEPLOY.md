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

## 10. Bybit EU (alternativa verificada) y pasos para cambiar de exchange

KuCoin global no tiene autorización para dar servicio en España desde el fin del periodo
transitorio de MiCA (1 de julio de 2026) y puede restringir la cuenta sin aviso. El bot opera
en OKX Europa (sección 11). Bybit EU queda como alternativa preparada y verificada con la
cuenta real el 2026-10-14: `config.bybiteu.yaml` es la misma configuración en USDC, sin ETC, con
su comisión (0,25%) y sin fuente de señales separada (su volumen basta). Los pasos C de esta
sección son los de cualquier cambio de exchange.

### A. Comprobar la cuenta (el bot real sigue en KuCoin, sin tocarlo)
1. En Bybit EU, crea una clave de API con permiso de **lectura y trading al contado, sin
   retirada**, y limítala a la IP del VPS.
2. Añade al `.env` del VPS (sin quitar las de KuCoin):
   ```bash
   sudo -u tradebot nano /opt/tradebot/.env    # BYBIT_API_KEY=...  y  BYBIT_API_SECRET=...
   ```
3. Cuenta, saldo y comisión, **sin operar**:
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-account --config config.bybiteu.yaml
   ```
   La comisión debe coincidir con `engine.fee_pct` de `config.bybiteu.yaml`. La cuenta
   paga un 0,25% en los 17 pares, a mercado y con orden limitada (comprobado el
   2026-10-14); con esa comisión la simulación desde 2022 da +119%, frente a +161% al 0,10%.
4. Con unos 20 USDC en la cuenta, compra y venta **real** de 5 USDC (pide confirmación):
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-api --usd 5 --config config.bybiteu.yaml
   ```
5. Órdenes de stop (pone una orden mínima con el disparo un 50% por debajo y la cancela):
   ```bash
   cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-stops --config config.bybiteu.yaml
   ```
   Si Bybit interpretara mal la orden y la disparase al momento, vendería esa cantidad
   mínima de ETH si la hubiera en la cuenta; el script lo detectaría en el paso del listado.

Si algo falla, no sigas: hay que corregir el código antes.

### B. Simulado en paralelo (opcional)
En **otra carpeta** (el simulado escribiría los mismos ficheros de estado que el bot real):
```bash
git clone https://github.com/AntonioCastillo/trade-bot.git ~/tradebot-bybit && cd ~/tradebot-bybit
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run.py config.bybiteu.yaml      # sin TRADEBOT_LIVE_CONFIRM arranca en simulado
```

### C. El cambio
1. Pausa las cuatro cabezas en KuCoin y espera a que las posiciones abiertas se cierren solas:
   ```bash
   cd /opt/tradebot && for h in tendencia_alcista volumen_explosivo grid_lateral capitulacion; do sudo -u tradebot .venv/bin/python scripts/manage.py pause $h; done
   ```
2. Sin posiciones abiertas, mueve el saldo a Bybit EU en USDC. Eso lo haces tú.
3. PR que sustituye `config.yaml` por el contenido de `config.bybiteu.yaml` (con
   `mode: live`, y `exchange_stops: true` si el paso A.5 salió bien) y borra
   `config.bybiteu.yaml`. Al fusionarlo, el despliegue automático reinicia el bot en Bybit EU.
4. Levanta las pausas (se guardan en la base de datos y sobreviven al cambio):
   ```bash
   cd /opt/tradebot && for h in tendencia_alcista volumen_explosivo grid_lateral capitulacion; do sudo -u tradebot .venv/bin/python scripts/manage.py resume $h; done
   ```
5. Si el saldo que llega a Bybit es menor que el máximo histórico de equity del bot, bórralo
   antes del paso 3 (`sudo -u tradebot .venv/bin/python scripts/reset_ath.py`): el
   disyuntor global cierra todo si el equity cae un 15% desde ese máximo.

**Protección:** si al arrancar en Bybit quedan posiciones registradas en USDT, el bot **no
arranca** (reconciliarlas contra la cuenta nueva las daría por vendidas) y el despliegue
automático vuelve a la versión anterior. Mientras tanto llegarán varios avisos de «Bot CAÍDO».

**Incógnita que no resuelve la migración:** `volumen_explosivo` se dispara con el volumen
de cada exchange. En Bybit EU, de enero a octubre de 2026, solo 14 de sus 44 entradas
coincidieron con las de KuCoin; el resultado fue parecido, pero son nueve meses.

## 11. OKX Europa con señales de otro exchange (el exchange actual)

Desde octubre de 2026, `config.yaml` opera en OKX Europa. Cobra lo mismo que KuCoin (0,10% a
mercado, con la cuenta de derivados X-Perps abierta; 0,20% sin ella), pero su volumen en USDC
es muy bajo y las cabezas que miran el volumen (`volumen_explosivo`, `capitulacion`) verían
picos donde no los hay. Por eso las velas de las señales salen de KuCoin (solo datos públicos)
y, si deja de responder, de Binance. Órdenes, saldos y precios de las salidas: siempre de OKX.

### Verificaciones (hechas el 2026-10-15 con la cuenta real)
Comisión (`fees`: 0,100% a mercado y 0,080% limitada en los 17 pares), cuenta
(`verify-account`), compra y venta real de 10 USDC (`verify-api`) y órdenes de stop
(`verify-stops`, siete de siete). Para repetirlas, por ejemplo con claves nuevas:
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py fees
```
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-account
```
```bash
cd /opt/tradebot && sudo -u tradebot .venv/bin/python scripts/manage.py verify-stops
```
- **Claves:** `OKX_API_KEY`, `OKX_API_SECRET` y `OKX_API_PASSPHRASE`, de una clave con lectura
  y trading, sin retirada. En su lista de IP van **la IPv4 y la IPv6** del VPS: el VPS conecta con
  OKX por IPv6 (con solo la IPv4, OKX responde 50110).
- **`verify-stops` necesita tener la moneda** (0,002 ETH con ETH/USDC): OKX solo acepta la orden
  de stop si hay saldo para venderla, y **lo bloquea mientras la orden está viva**. El bot retira
  su orden antes de vender o de reponerla, y si no puede retirarla espera al siguiente sondeo.

### El cambio
Los pasos de la sección 10 (pausar, cerrar posiciones, mover el saldo, `reset_ath.py` si
hace falta, fusionar, comprobar el arranque y `resume`), con el PR que pone `config.yaml` en
OKX. Si KuCoin falla 3 veces seguidas, las velas salen de Binance durante 30 minutos y luego se
vuelve a probar KuCoin; llega un aviso por Telegram en cada cambio y el gist muestra la fuente
activa (`data_source`). Cambiar de fuente cambia algunas señales (en `volumen_explosivo`,
aproximadamente la mitad de las compras); las ventas no dependen de la fuente.

**Volver a Bybit EU** (alternativa verificada): un PR que ponga en `config.yaml` el contenido de
`config.bybiteu.yaml` en real, con las posiciones de OKX cerradas y el saldo movido.

**Simular:** `python scripts/livesim.py --combined` usa los precios de OKX (historia desde
octubre de 2025) y las señales de KuCoin. Para estudios largos: `--exchange kucoin --quote USDT`.

## Notas
- **Firewall:** no requiere puertos entrantes; solo HTTPS saliente (por defecto OK).
- **Reloj:** `chronyd` queda activo; el bot además ajusta la diferencia con el exchange.
- **SELinux:** el servicio escribe solo en `/opt/tradebot`. Si SELinux bloqueara
  algo, revisa `journalctl -u tradebot` y `ausearch -m avc -ts recent`.
