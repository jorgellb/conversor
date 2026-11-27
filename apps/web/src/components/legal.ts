// Textos legales base (RGPD, LSSI-CE). Los datos entre corchetes los aporta el propietario (0.1) y los revisa un profesional.
type Page = { title: string; body: (product: string, email: string) => string[] };

// El titular es un autónomo (D-273): nombre, NIF y domicilio, sin datos registrales.
const OWNER = "[Nombre y apellidos del titular] · NIF [NIF] · [Domicilio]";
const OWNER_EN = "[Owner's full name] · Tax ID [NIF] · [Address]";

export const LEGAL: Partial<Record<string, Record<"es" | "en", Page>>> = {
  privacidad: {
    es: {
      title: "Política de privacidad",
      body: (p, email) => [
        `## Responsable`,
        `${OWNER}. Contacto para protección de datos: ${email}.`,
        `## Qué datos tratamos y para qué`,
        `Archivos que subes a las herramientas de servidor: solo para hacer la tarea que pides. Se borran automáticamente al vencer el plazo de tu plan (1 hora sin cuenta y 24 horas con cuenta) y nadie los revisa. Las herramientas marcadas «Tu archivo no sale de tu dispositivo» funcionan en tu navegador y no nos envían el archivo.`,
        `Cuenta: correo, nombre y contraseña cifrada para darte acceso, historial de tareas (solo metadatos: herramienta, fecha, tamaño y estado) y pases comprados.`,
        `Pagos: los gestiona PayPal (PayPal (Europe) S.à r.l. et Cie, S.C.A.), con tu cuenta de PayPal o con tarjeta a través de PayPal; no vemos ni guardamos los datos de tu tarjeta. Guardamos el pedido, el correo que nos da PayPal y la factura, y los datos de facturación que añadas (nombre, NIF y dirección).`,
        `Seguridad y prevención del abuso: dirección IP resumida (cifrada con una clave) y la comprobación de Cloudflare Turnstile.`,
        `Herramientas de IA (marcadas «Beta»): solo si las usas y después de aceptar el aviso, el texto del documento se envía a un modelo de IA a través de OpenRouter. Guardamos el texto extraído y el resultado mientras duran tus archivos, para no repetir peticiones, y de cada petición solo el modelo, los tokens, el tiempo y el resultado (nunca el contenido). Las herramientas de firma, certificados, contactos, calendario y correo no envían nada a la IA.`,
        `## Base legal`,
        `Ejecución del servicio que pides (art. 6.1.b RGPD), obligaciones legales de facturación (art. 6.1.c), consentimiento para las herramientas de IA (art. 6.1.a, que puedes retirar dejando de usarlas) e interés legítimo en la seguridad del servicio (art. 6.1.f).`,
        `## Encargados y transferencias`,
        `Proveedor del servidor en la Unión Europea, Cloudflare (red y antiabuso), PayPal (pagos, responsable de sus propios tratamientos) y el proveedor de correo. Si alguno trata datos fuera del EEE, lo hace con cláusulas contractuales tipo.`,
        `IA: OpenRouter (Estados Unidos) y los proveedores de modelos a los que dirige cada petición, que pueden estar fuera de la Unión Europea. Solo usamos proveedores que declaran no recoger los datos para entrenar (data_collection «deny»), aunque pueden conservarlos un tiempo según su política. Políticas: openrouter.ai/privacy y la de cada proveedor, enlazada desde openrouter.ai.`,
        `## Conservación`,
        `Archivos, texto extraído para la IA y sus resultados: el plazo indicado arriba. Registro de peticiones de IA (sin contenido) y uso diario: 90 días. Cuenta: mientras no la borres. Facturas: el plazo que exige la ley. Copias de seguridad: se rotan en un máximo de 6 meses.`,
        `## Tus derechos`,
        `Acceso, rectificación, supresión, oposición, limitación y portabilidad escribiendo a ${email}. Desde «Mi cuenta» puedes descargar tus datos y borrar tu cuenta. También puedes reclamar ante la Agencia Española de Protección de Datos (aepd.es).`,
        `## Cookies`,
        `${p} solo usa cookies técnicas para mantener la sesión iniciada. No usamos cookies de publicidad ni de analítica de terceros.`,
      ],
    },
    en: {
      title: "Privacy policy",
      body: (p, email) => [
        `## Controller`,
        `${OWNER_EN}. Data protection contact: ${email}.`,
        `## What we process and why`,
        `Files you upload to server tools: only to carry out the task you request. They are deleted automatically when your plan's time limit expires (1 hour without an account, 24 hours with one) and nobody looks at them. Tools marked “Your file never leaves your device” run in your browser and never send us the file.`,
        `Account: email, name and hashed password to give you access, task history (metadata only: tool, date, size and status) and the passes you buy.`,
        `Payments: handled by PayPal (PayPal (Europe) S.à r.l. et Cie, S.C.A.), with your PayPal account or by card through PayPal; we never see or store your card details. We keep the order, the email PayPal gives us and the invoice, plus any billing details you add (name, tax ID and address).`,
        `Security and abuse prevention: a keyed hash of your IP address and the Cloudflare Turnstile check.`,
        `AI tools (marked “Beta”): only if you use them and after you accept the notice, the document's text is sent to an AI model through OpenRouter. We keep the extracted text and the result while your files last, so requests are not repeated, and for each request only the model, tokens, time and outcome (never the content). Signature, certificate, contact, calendar and email tools never send anything to AI.`,
        `## Legal basis`,
        `Performance of the service you request (Art. 6(1)(b) GDPR), legal invoicing obligations (Art. 6(1)(c)), consent for the AI tools (Art. 6(1)(a), which you can withdraw by no longer using them) and legitimate interest in keeping the service secure (Art. 6(1)(f)).`,
        `## Processors and transfers`,
        `Server provider in the European Union, Cloudflare (network and anti-abuse), PayPal (payments, controller of its own processing) and the email provider. Any processing outside the EEA relies on standard contractual clauses.`,
        `AI: OpenRouter (United States) and the model providers each request is routed to, which may be outside the European Union. We only use providers that state they do not collect data for training (data_collection “deny”), although they may keep it for a while according to their policy. Policies: openrouter.ai/privacy and each provider's own, linked from openrouter.ai.`,
        `## Retention`,
        `Files, text extracted for AI and its results: the period above. AI request log (no content) and daily usage: 90 days. Account: until you delete it. Invoices: as long as the law requires. Backups: rotated within 6 months at most.`,
        `## Your rights`,
        `Access, rectification, erasure, objection, restriction and portability by writing to ${email}. From “My account” you can download your data and delete your account. You may also complain to the Spanish Data Protection Agency (aepd.es).`,
        `## Cookies`,
        `${p} only uses technical cookies to keep you signed in. We do not use advertising or third-party analytics cookies.`,
      ],
    },
  },
  terminos: {
    es: {
      title: "Términos de uso",
      body: (p, email) => [
        `## Servicio`,
        `${p} ofrece herramientas para trabajar con PDF y convertir archivos. Las herramientas ligeras son gratuitas, con límites diarios. Las que usan mucha potencia de servidor (las marcadas «Pase 24 h») necesitan el pase de 24 horas.`,
        `## Uso aceptable`,
        `No subas contenido ilícito ni archivos sobre los que no tengas derechos, no intentes saltarte los límites ni atacar el servicio. Podemos bloquear el acceso ante un uso abusivo.`,
        `## Tus archivos`,
        `Sigues siendo el titular de tus archivos. Solo los tratamos para hacer la tarea y se borran al vencer el plazo de tu plan. Guarda tus resultados: no hacemos copia de ellos.`,
        `## Pase de 24 horas`,
        `El pase cuesta 1 € (IVA incluido) y da acceso a todas las herramientas avanzadas durante 24 horas desde el pago, con los límites ampliados que se indican en «Precios». Es un pago único: no es una suscripción y no se renueva. Si compras otro con uno activo, el nuevo empieza cuando acaba el anterior.`,
        `Se paga solo con PayPal (cuenta de PayPal o tarjeta a través de PayPal) y hace falta una cuenta. La factura queda en «Mi cuenta»; si añades nombre, NIF y dirección antes de pagar, es completa.`,
        `Desistimiento: el pase es un contenido digital que se presta en cuanto pagas. Al comprarlo das tu consentimiento expreso para que empiece de inmediato y aceptas que pierdes el derecho de desistimiento (art. 103.m del Texto refundido de la Ley General para la Defensa de los Consumidores y Usuarios). Si el servicio no ha funcionado por causa nuestra, te devolvemos el importe.`,
        `## Responsabilidad`,
        `Hacemos lo posible por que las herramientas funcionen bien, pero revisa el resultado antes de usarlo para algo importante. No respondemos de pérdidas indirectas salvo dolo o culpa grave.`,
        `## Contacto y ley aplicable`,
        `Escríbenos a ${email}. Se aplica la ley española; si eres consumidor, mantienes los derechos y tribunales que te reconoce la ley de tu residencia.`,
      ],
    },
    en: {
      title: "Terms of use",
      body: (p, email) => [
        `## Service`,
        `${p} provides tools to work with PDFs and convert files. Light tools are free, with daily limits. The ones that use a lot of server power (marked “24-hour pass”) need the 24-hour pass.`,
        `## Acceptable use`,
        `Do not upload unlawful content or files you have no rights to, and do not try to bypass the limits or attack the service. We may block access in case of abuse.`,
        `## Your files`,
        `You keep ownership of your files. We only process them to carry out the task and they are deleted when your plan's time limit expires. Keep your results: we do not back them up.`,
        `## 24-hour pass`,
        `The pass costs €1 (VAT included) and gives access to every advanced tool for 24 hours from payment, with the higher limits listed under “Pricing”. It is a one-off payment: not a subscription, and it does not renew. If you buy another while one is active, the new one starts when the current one ends.`,
        `It is paid only with PayPal (PayPal account or card through PayPal) and requires an account. The invoice stays in “My account”; if you add your name, tax ID and address before paying, it is a full invoice.`,
        `Withdrawal: the pass is digital content supplied as soon as you pay. By buying it you expressly consent to it starting immediately and accept that you lose the right of withdrawal (Art. 103(m) of the Spanish consumer protection act). If the service did not work because of us, we refund you.`,
        `## Liability`,
        `We do our best to make the tools work well, but check the result before relying on it for anything important. We are not liable for indirect losses except in cases of wilful misconduct or gross negligence.`,
        `## Contact and governing law`,
        `Write to ${email}. Spanish law applies; consumers keep the rights and courts granted by the law of their place of residence.`,
      ],
    },
  },
  avisoLegal: {
    es: {
      title: "Aviso legal",
      body: (p, email) => [
        `En cumplimiento de la Ley 34/2002 de servicios de la sociedad de la información (LSSI-CE): el titular de ${p} es ${OWNER}. Correo de contacto: ${email}.`,
        `Los contenidos, el diseño y el código de este sitio son del titular o de sus licenciantes. Las marcas de terceros que se citan para describir formatos de archivo pertenecen a sus dueños.`,
      ],
    },
    en: {
      title: "Legal notice",
      body: (p, email) => [
        `Under Spanish Law 34/2002 on information society services (LSSI-CE): ${p} is operated by ${OWNER_EN}. Contact email: ${email}.`,
        `The content, design and code of this site belong to the operator or its licensors. Third-party trademarks mentioned to describe file formats belong to their owners.`,
      ],
    },
  },
  ayuda: {
    es: {
      title: "Ayuda",
      body: (p, email) => [
        `## ¿Dónde se procesa mi archivo?`,
        `Las herramientas que muestran «Tu archivo no sale de tu dispositivo» trabajan en tu navegador. El resto suben el archivo cifrado a nuestro servidor y lo borran al vencer el plazo de tu plan.`,
        `## Mi PDF tiene contraseña`,
        `Usa «Desbloquear PDF» con la contraseña de apertura. Nunca intentamos adivinarla.`,
        `## He llegado al límite diario`,
        `Los límites se reinician cada día a medianoche (hora de Madrid). Con una cuenta gratuita tienes más tareas, y el pase de 24 horas (1 €) amplía los límites y abre las herramientas avanzadas.`,
        `## Algo no funciona`,
        `Usa «Informar de un problema» al final de cada herramienta o escribe a ${email}. ${p} nunca te pedirá tu contraseña por correo.`,
      ],
    },
    en: {
      title: "Help",
      body: (p, email) => [
        `## Where is my file processed?`,
        `Tools showing “Your file never leaves your device” work in your browser. The others upload the file encrypted to our server and delete it when your plan's time limit expires.`,
        `## My PDF has a password`,
        `Use “Unlock PDF” with the open password. We never try to guess it.`,
        `## I reached the daily limit`,
        `Limits reset every day at midnight (Madrid time). A free account gives you more tasks, and the 24-hour pass (€1) raises the limits and unlocks the advanced tools.`,
        `## Something does not work`,
        `Use “Report a problem” at the end of each tool or write to ${email}. ${p} will never ask for your password by email.`,
      ],
    },
  },
  contacto: {
    es: { title: "Contacto", body: (p, email) => [`Para cualquier duda sobre ${p}, escríbenos a ${email}. Respondemos en días laborables.`] },
    en: { title: "Contact", body: (p, email) => [`For any question about ${p}, write to ${email}. We answer on working days.`] },
  },
};
