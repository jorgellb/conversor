#!/bin/sh
# workerutils (5.4): KoSIT en modo servicio en 127.0.0.1:8081 dentro del mismo contenedor y después el worker de Celery.
# Las tres configuraciones se cargan juntas; KoSIT no elige escenario si coincide más de uno (D-191).
#
# Supervisión (D-191): si la JVM termina (por ejemplo, por OutOfMemoryError, que con ExitOnOutOfMemoryError la hace salir
# en lugar de quedarse colgada con /server/health en UP), se para el worker y el contenedor sale con error para que Docker
# lo reinicie; el trabajo en curso vuelve a la cola (5.3). SIGTERM llega al worker (parada en caliente) y después a KoSIT.
set -eu
K=/opt/kosit
OPTS=${KOSIT_JAVA_OPTS:--Xmx1g -XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp}
# shellcheck disable=SC2086 # OPTS son varias opciones
java $OPTS -cp "$K/validator/validator-1.6.3.jar:$K/validator/libs/*" \
  de.kosit.validationtool.cmd.CommandLineApplication \
  -s "$K/xrechnung/scenarios.xml" -r "$K/xrechnung" -s "$K/bis/scenarios.xml" -r "$K/bis" -s "$K/conversor/scenarios.xml" -r "$K" \
  -D -G -H 127.0.0.1 -P 8081 &
KOSIT=$!
i=0
until curl -sf --max-time 2 http://127.0.0.1:8081/server/health >/dev/null 2>&1; do
  kill -0 "$KOSIT" 2>/dev/null || { echo "KoSIT ha terminado al arrancar" >&2; exit 1; }
  i=$((i + 1)); [ "$i" -gt 120 ] && { echo "KoSIT no arranca" >&2; kill "$KOSIT"; exit 1; }; sleep 1
done
"$@" &
APP=$!
stopping=0
trap 'stopping=1; kill -TERM "$APP" 2>/dev/null || true' TERM INT
while kill -0 "$KOSIT" 2>/dev/null && kill -0 "$APP" 2>/dev/null; do
  sleep 2 &
  wait $! || true
done
code=0
if ! kill -0 "$KOSIT" 2>/dev/null && [ "$stopping" -eq 0 ]; then
  echo "KoSIT ha terminado; se para el worker para reiniciar el contenedor" >&2
  kill -TERM "$APP" 2>/dev/null || true
  code=1
fi
set +e
wait "$APP"
app=$?
set -e
[ "$code" -ne 0 ] || code=$app
kill -TERM "$KOSIT" 2>/dev/null || true
wait "$KOSIT" 2>/dev/null || true
exit "$code"
