## 10. Firma

- Sello de la plataforma:
  - certificado y clave por PKCS#11 (SoftHSM2 en el VPS, salvo que el propietario aporte un HSM); en desarrollo, uno autofirmado generado por script; nunca en el repositorio;
  - solo `workersign` monta el token (volumen `softhsm`) y conoce `SIGN_PKCS11_PIN`; `workersign` no ejecuta otros motores que pyHanko y tiene el aislamiento de 12.1;
  - cada uso se registra en `seal_signatures` con el sha256 del documento; `SEAL_DAILY_LIMIT` limita los sellos diarios y `SEAL_ENABLED=false` lo apaga al instante;
  - con un token software no hay dispositivo cualificado de creación de sellos, así que el sello no es cualificado y no se anuncia como tal.
- Sello de tiempo RFC 3161 con `TSA_URL`. La TSA de producción la elige el propietario (0.1), porque puede tener coste y ser o no cualificada.
- La interfaz explica que la firma dibujada es simple y que el sello acredita la integridad del documento y el momento, no la identidad del firmante. Añade en `docs/LEGAL.md` que los niveles eIDAS que se prometan deben revisarse con un especialista.
- Certificado propio del usuario o de su empresa: solo con firma interrumpida (A.6). La clave nunca llega al servidor, y el servidor nunca guarda certificados con clave privada.
  - La interfaz no promete «avanzada» ni «cualificada» de antemano.
  - Muestra el nivel que detecta verificar-firmas-pdf sobre el resultado.

---
