#!/bin/sh
# CPU, RAM y disco durante la prueba de carga k6 (16.1). Se ejecuta en el servidor mientras dura k6.js y se para con
# Ctrl+C (o kill). Escribe una fila por contenedor cada INTERVALO segundos:
#   fecha,contenedor,cpu,memoria,disco_usado_bytes,disco_libre_bytes
# Uso: DATOS=/srv/files INTERVALO=5 sh tests/load/recursos.sh recursos-k6.csv
set -eu
SALIDA=${1:-recursos-k6.csv}
DATOS=${DATOS:-/srv/files}
INTERVALO=${INTERVALO:-5}
command -v docker >/dev/null || { echo "recursos.sh: hace falta la orden docker en el servidor" >&2; exit 1; }
[ -d "$DATOS" ] || { echo "recursos.sh: no existe $DATOS (DATOS=ruta del volumen de archivos)" >&2; exit 1; }
echo "fecha,contenedor,cpu,memoria,disco_usado_bytes,disco_libre_bytes" > "$SALIDA"
while :; do
  ahora=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  disco=$(df -B1 --output=used,avail "$DATOS" | tail -n 1 | awk '{print $1 "," $2}')
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | while IFS= read -r fila; do
    echo "$ahora,$fila,$disco"
  done >> "$SALIDA"
  sleep "$INTERVALO"
done
