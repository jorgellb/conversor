# tusd (4.2)

Imagen oficial `tusproject/tusd:v2.10.1`, con estos flags en `command:` (los dos Compose):

- `-upload-dir=/srv/files/uploads`, `-base-path=/files/`, `-behind-proxy`, `-max-size` igual al máximo del plan Pro;
- `-disable-download`: tusd nunca sirve lo subido (las descargas van por `files` con token firmado);
- ganchos HTTP bloqueantes: `-hooks-http=http://apiint:8001/tusd-hooks`,
  `-hooks-http-forward-headers=Authorization,Accept-Language,CF-Connecting-IP,X-Forwarded-For` y
  `-hooks-enabled-events=pre-create,pre-finish,post-terminate`;
- CORS solo para la web: `-cors-allow-origin=^https://{{DOMINIO}}$` y `-cors-allow-headers=Authorization,Accept-Language`.

El contenedor corre con el usuario 10001, el mismo que la API y los workers, para que el `rename` de
`uploads/` a `jobs/<id>/in/` funcione sin cambiar permisos. Comprueba los nombres de los flags al subir de versión
(`tusd -help`).
