#!/usr/bin/env bash
# Foto de estado del bot para revisar (o pegar al analista).
# Uso:  bash status.sh    (desde el directorio del bot; si no lees los logs, con sudo)
cd "$(dirname "$0")"

echo "=== ESTADO SERVICIO ==="
systemctl is-active tradebot 2>/dev/null || echo "(sin systemd o servicio no instalado)"

echo
echo "=== INFORME ==="
cat data/report.txt 2>/dev/null || echo "(sin report.txt todavía)"

echo
echo "=== ÚLTIMAS OPERACIONES ==="
grep -E "ABRE|CIERRA" logs/tradebot.log 2>/dev/null | tail -15 || echo "(sin operaciones aún)"

echo
echo "=== HEARTBEAT (equity / estado) ==="
grep "Informe actualizado" logs/tradebot.log 2>/dev/null | tail -3

echo
echo "=== OPERACIONES POR CABEZA ==="
grep -oE "\[[a-z0-9_]+/[a-z_]+\]" logs/tradebot.log 2>/dev/null | sort | uniq -c | sort -rn

echo
echo "=== ERRORES RECIENTES ==="
grep -iE "error|traceback|caíd|falló" logs/tradebot.log 2>/dev/null | tail -10 || echo "(ninguno)"
