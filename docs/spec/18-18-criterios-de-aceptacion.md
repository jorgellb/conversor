## 18. Criterios de aceptación

- `docker compose up` arranca todo en local solo con `.env.example` y los dobles de 0.1.
- El cierre técnico de cada fase está en verde en la CI, y el operativo está hecho o figura como pendiente en `docs/PROGRESS.md`, con sus pasos en `docs/DEPLOY-CHECKLIST.md`.
- Con las entradas de 0.1, el repositorio se despliega en un único VPS con Coolify v4 con todos los healthchecks en verde.
- No existe ninguna dependencia ni variable de S3: todo el almacenamiento está en disco del VPS.
- Cada herramienta habilitada tiene páginas es y en, funciona de extremo a extremo y su prueba pasa; las desactivadas cumplen 1.7.
- Cada herramienta expone como mínimo las opciones del Anexo A, con sus valores por defecto y rangos.
- Las herramientas cliente no envían el archivo a la red.
- La IA solo usa modelos gratuitos de OpenRouter con `data_collection: "deny"`, nunca supera 18 peticiones por minuto ni `AI_DAILY_BUDGET` al día, y exige consentimiento.
- Ninguna dependencia AGPL enlazada o empaquetada y ningún paquete GPL importado, comprobado en la CI.
- Ningún worker sale a internet salvo por los proxies de 12.2, y ningún contenedor ve secretos que no le tocan.
- Los archivos y el contenido derivado desaparecen al vencer su plazo.
- Las guardas de disco y de colas funcionan y avisan al administrador.
- La copia remota existe y la restauración está probada (16.7).
- Ningún secreto en el repositorio ni en los logs.
- `docs/` completo: PLAN, PROGRESS, DECISIONS, ARCHITECTURE, TOOLS, LICENSES, LEGAL, SECURITY, DEPLOY, DEPLOY-CHECKLIST, OPERATIONS, ERRORS y `spec/`.

---
