#!/usr/bin/env bash
# Despliegue automático: el VPS consulta GitHub y, si la rama `production` tiene un
# commit nuevo, actualiza el código, reinicia el bot y comprueba que arranca. Si no
# arranca, vuelve al commit anterior. Avisa por Telegram de cada despliegue o fallo.
#
# Lo lanza tradebot-autodeploy.timer cada 5 min, como root (necesita reiniciar el
# servicio); git y pip corren como el usuario del bot. Instalación: deploy/DEPLOY.md §9.
#
# Se instala COPIADO en /usr/local/sbin (no se ejecuta desde el repo): así un
# despliegue no puede cambiar el script que root está ejecutando.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tradebot}"
APP_USER="${APP_USER:-tradebot}"
SERVICE="${SERVICE:-tradebot}"
REPO_URL="${REPO_URL:-https://github.com/AntonioCastillo/trade-bot.git}"
BRANCH="${BRANCH:-production}"
CANDLE_HOURS="${CANDLE_HOURS:-4}"            # las cabezas operan al cierre de vela de 4 h
GUARD_BEFORE_MIN="${GUARD_BEFORE_MIN:-5}"    # no reiniciar desde 5 min antes del cierre…
GUARD_AFTER_MIN="${GUARD_AFTER_MIN:-10}"     # …hasta 10 min después (el bot está comprando)
HEALTH_WAIT_S="${HEALTH_WAIT_S:-150}"        # plazo para ver "Daemon iniciado"
HEALTH_HOLD_S="${HEALTH_HOLD_S:-30}"         # y debe seguir vivo este tiempo después
STATE_DIR="${STATE_DIR:-/var/lib/tradebot-autodeploy}"
LOG_FILE="${APP_DIR}/logs/tradebot.log"

log() { echo "[autodeploy] $*"; }

html() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }   # texto seguro para Telegram

as_app() { runuser -u "$APP_USER" -- "$@"; }

git_app() { as_app git -C "$APP_DIR" -c core.fileMode=false "$@"; }

env_value() {  # lee una variable del .env del bot sin ejecutarlo
    grep -E "^$1=" "$APP_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '"'"'"'\r'
}

notify() {
    local token chat
    token="$(env_value TELEGRAM_BOT_TOKEN)"; chat="$(env_value TELEGRAM_CHAT_ID)"
    [ -n "$token" ] && [ -n "$chat" ] || return 0
    curl -fsS -m 15 -o /dev/null "https://api.telegram.org/bot${token}/sendMessage" \
        --data-urlencode "chat_id=${chat}" --data-urlencode "parse_mode=HTML" \
        --data-urlencode "text=$1" || log "no pude avisar por Telegram"
}

notify_once() {  # mismo aviso una sola vez por commit (el timer corre cada 5 min)
    local key="$1" marker="$STATE_DIR/notified_$1"
    [ -f "$marker" ] && return 0
    notify "$2"; : > "$marker"
}

in_candle_guard() {
    local now=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M)))
    local into=$((now % (CANDLE_HOURS * 60)))
    [ "$into" -lt "$GUARD_AFTER_MIN" ] || [ "$into" -ge $((CANDLE_HOURS * 60 - GUARD_BEFORE_MIN)) ]
}

log_size() { stat -c %s "$LOG_FILE" 2>/dev/null || echo 0; }

started_since() {  # ¿aparece "Daemon iniciado" en lo escrito desde el reinicio?
    local offset="$1" size
    size="$(log_size)"
    [ "$size" -lt "$offset" ] && offset=0          # el log rotó
    tail -c "+$((offset + 1))" "$LOG_FILE" 2>/dev/null | grep -q "Daemon iniciado"
}

restart_and_check() {
    local offset pid waited=0
    offset="$(log_size)"
    systemctl restart "$SERVICE"
    while [ "$waited" -lt "$HEALTH_WAIT_S" ]; do
        sleep 5; waited=$((waited + 5))
        if systemctl is-active --quiet "$SERVICE" && started_since "$offset"; then
            pid="$(systemctl show -p MainPID --value "$SERVICE")"
            sleep "$HEALTH_HOLD_S"
            systemctl is-active --quiet "$SERVICE" \
                && [ "$(systemctl show -p MainPID --value "$SERVICE")" = "$pid" ]
            return
        fi
    done
    return 1
}

install_requirements() {
    as_app "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
}

main() {
    mkdir -p "$STATE_DIR"
    exec 9>"$STATE_DIR/lock"
    flock -n 9 || { log "ya hay un despliegue en curso"; exit 0; }

    if ! git_app rev-parse HEAD >/dev/null 2>&1; then
        log "el usuario $APP_USER no puede usar el repo de $APP_DIR (¿permisos?)"
        notify_once "perms" "⚠️ <b>Despliegue automático parado</b>
El usuario <code>$APP_USER</code> no puede leer el repositorio de <code>$APP_DIR</code>. Revisa los permisos."
        exit 1
    fi
    if ! git_app fetch --quiet "$REPO_URL" "$BRANCH"; then
        log "no pude consultar $BRANCH en GitHub; lo reintento en la próxima vuelta"
        exit 0
    fi
    local cur new short subject
    cur="$(git_app rev-parse HEAD)"
    new="$(git_app rev-parse FETCH_HEAD)"
    [ "$cur" = "$new" ] && exit 0
    short="${new:0:7}"

    if git_app merge-base --is-ancestor "$new" "$cur"; then
        exit 0                                       # el VPS ya va por delante de production
    fi
    if [ "$(cat "$STATE_DIR/failed" 2>/dev/null)" = "$new" ]; then
        exit 0                                       # ya falló: espera a un commit nuevo
    fi
    if ! git_app merge-base --is-ancestor "$cur" "$new"; then
        log "el commit desplegado ($cur) no es antecesor de $BRANCH ($new): no toco nada"
        notify_once "diverged_$short" "⚠️ <b>Despliegue omitido</b>
El código del VPS y la rama <code>$BRANCH</code> han divergido. Revísalo a mano."
        exit 1
    fi
    local dirty
    dirty="$(git_app status --porcelain --untracked-files=no | html)"
    if [ -n "$dirty" ]; then
        log "hay cambios locales sin commit en el VPS: no despliego"
        notify_once "dirty_$short" "⚠️ <b>Despliegue omitido</b> (<code>$short</code>)
Hay ficheros modificados a mano en el VPS:
<pre>$dirty</pre>"
        exit 1
    fi
    if in_candle_guard; then
        log "cierre de vela de ${CANDLE_HOURS} h cerca: aplazo el despliegue de $short"
        exit 0
    fi

    subject="$(git_app log -1 --format=%s "$new" | html)"
    log "desplegando $short: $subject"
    local deps=0 units=""
    git_app diff --quiet "$cur" "$new" -- requirements.txt pyproject.toml || deps=1
    units="$(git_app diff --name-only "$cur" "$new" -- deploy/ | tr '\n' ' ')"

    git_app merge --quiet --ff-only "$new"
    local ok=1
    if [ "$deps" = 1 ] && ! install_requirements; then
        ok=0
        log "falló la instalación de dependencias"
    fi
    if [ "$ok" = 1 ] && restart_and_check; then
        log "desplegado $short"
        notify "🚀 <b>Desplegado</b> <code>$short</code>
$subject${units:+
ℹ️ Cambió <code>deploy/</code> (${units}): los ficheros de systemd y este script no se reinstalan solos.}"
        exit 0
    fi

    log "el bot no arrancó con $short: vuelvo a ${cur:0:7}"
    echo "$new" > "$STATE_DIR/failed"
    git_app reset --quiet --hard "$cur"              # árbol limpio comprobado arriba
    [ "$deps" = 1 ] && { install_requirements || log "no pude restaurar las dependencias"; }
    if restart_and_check; then
        notify "❌ <b>Despliegue fallido</b> <code>$short</code>
$subject
El bot no arrancó; he vuelto a <code>${cur:0:7}</code> y está funcionando."
    else
        notify "🆘 <b>Despliegue fallido y el bot NO arranca</b>
Ni <code>$short</code> ni el anterior <code>${cur:0:7}</code>. Revisa el VPS: <code>journalctl -u $SERVICE -n 50</code>"
    fi
    exit 1
}

main "$@"
