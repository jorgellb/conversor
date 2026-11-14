# Perfil CMYK FOGRA39 (D-60 y D-154)

`FOGRA39L_coated.icc` es el perfil del proyecto colord (Richard Hughes, 2012), con licencia **CC0-1.0**
(`data/profiles/*` en el `copyright` del paquete de Debian). Se copió de `colord-data` 1.4.7-3 de Debian 13.

La imagen base de los workers (Debian 12, bookworm) trae `colord-data` 1.4.6, que ya no incluye los perfiles
de impresión, así que `workers/Dockerfile` copia este archivo a `/usr/share/color/icc/colord/` y comprueba su
SHA-256:

```
b62f5c72561c15ae2e0072b92ce9df42662f76915d75fac8ca2f6be033ac74fe  FOGRA39L_coated.icc
```
