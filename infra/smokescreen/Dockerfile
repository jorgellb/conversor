# Smokescreen de Stripe (MIT) compilado desde su etiqueta v0.1.0 (D-155): Stripe no publica ninguna imagen de contenedor
# (ghcr.io/stripe/smokescreen da «denied»). Lo usan egressweb y egressai (12.2). El código fuente trae sus dependencias
# en vendor/, así que la compilación no descarga módulos; la etiqueta se comprueba contra su commit.
ARG GO_IMAGE=golang:1.25.14-bookworm
FROM ${GO_IMAGE} AS build
ARG SMOKESCREEN_TAG=v0.1.0
ARG SMOKESCREEN_COMMIT=609eb8931420453daf5893509be0b25b21bd9edb
WORKDIR /src
RUN git clone --depth 1 --branch "${SMOKESCREEN_TAG}" https://github.com/stripe/smokescreen.git . \
 && test "$(git rev-parse HEAD)" = "${SMOKESCREEN_COMMIT}" \
 && CGO_ENABLED=0 GOFLAGS=-mod=vendor go build -trimpath -ldflags="-s -w" -o /out/smokescreen . \
 && cp LICENSE.txt /out/LICENSE.txt

# Binario estático sin sistema operativo: sin intérprete ni utilidades dentro del contenedor del proxy.
FROM scratch
COPY --from=build /out/smokescreen /smokescreen
COPY --from=build /out/LICENSE.txt /LICENSE.txt
USER 65534:65534
EXPOSE 4750
ENTRYPOINT ["/smokescreen"]
