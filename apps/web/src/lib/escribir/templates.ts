// escribir-pdf (A.1, F6-O1, D-234): plantillas propias (carta, presupuesto, CV, acta, informe, certificado, folleto y
// solicitud) en HTML del editor, con los huecos entre corchetes para cambiarlos. Cada una sugiere sus opciones de página.

export const TEMPLATE_KEYS = ["blanco", "carta", "presupuesto", "cv", "acta", "informe", "certificado", "folleto", "solicitud"] as const;
export type TemplateKey = (typeof TEMPLATE_KEYS)[number];

export interface Template {
  html: string;
  page?: Record<string, unknown>;
}

const field = (nombre: string, ancho = 60, tipo: "texto" | "casilla" | "fecha" = "texto") =>
  `<span class="campo-editor" data-tipo="${tipo}" data-nombre="${nombre}" data-ancho="${ancho}">${nombre}</span>`;

const ES: Record<TemplateKey, Template> = {
  blanco: { html: "<p></p>" },
  carta: {
    page: { fuente: "serif", numeros_pagina: "ninguno" },
    html: `<p style="text-align: right">[Tu nombre]<br>[Tu dirección]<br>[Código postal y ciudad]<br>[Teléfono · correo]</p>
<p style="text-align: right">[Ciudad], a [fecha]</p>
<p>[Nombre del destinatario]<br>[Empresa u organismo]<br>[Dirección]</p>
<p><strong>Asunto:</strong> [motivo de la carta]</p>
<p>Estimado/a [nombre]:</p>
<p>[Primer párrafo: preséntate y explica el motivo de la carta.]</p>
<p>[Segundo párrafo: los detalles, los hechos o la petición.]</p>
<p>[Despedida: lo que esperas que ocurra y cómo contactarte.]</p>
<p>Atentamente,</p><p></p><p>[Firma]<br>[Tu nombre]</p>`,
  },
  presupuesto: {
    page: { fuente: "sans", numeros_pagina: "pie" },
    html: `<h1>Presupuesto n.º [000]</h1>
<p><strong>Fecha:</strong> [fecha] · <strong>Válido hasta:</strong> [fecha]</p>
<table><tbody><tr><th><p>De</p></th><th><p>Para</p></th></tr><tr><td><p>[Tu empresa]<br>[NIF]<br>[Dirección]</p></td><td><p>[Cliente]<br>[NIF]<br>[Dirección]</p></td></tr></tbody></table>
<h2>Conceptos</h2>
<table><tbody><tr><th><p>Concepto</p></th><th><p>Cantidad</p></th><th><p>Precio</p></th><th><p>Importe</p></th></tr>
<tr><td><p>[Servicio o producto]</p></td><td><p>1</p></td><td><p>0,00 €</p></td><td><p>0,00 €</p></td></tr>
<tr><td><p>[Servicio o producto]</p></td><td><p>1</p></td><td><p>0,00 €</p></td><td><p>0,00 €</p></td></tr>
<tr><td><p><strong>Base imponible</strong></p></td><td><p></p></td><td><p></p></td><td><p>0,00 €</p></td></tr>
<tr><td><p><strong>IVA (21 %)</strong></p></td><td><p></p></td><td><p></p></td><td><p>0,00 €</p></td></tr>
<tr><td><p><strong>Total</strong></p></td><td><p></p></td><td><p></p></td><td><p><strong>0,00 €</strong></p></td></tr></tbody></table>
<h2>Condiciones</h2><ul><li><p>Forma de pago: [transferencia, 30 días].</p></li><li><p>Plazo de entrega: [plazo].</p></li></ul>
<p>Aceptación del cliente: ${field("Nombre y firma", 70)} Fecha: ${field("Fecha de aceptación", 30, "fecha")}</p>`,
  },
  cv: {
    page: { fuente: "sans", numeros_pagina: "ninguno", margenes_mm: 18 },
    html: `<h1>[Nombre y apellidos]</h1>
<p>[Puesto o perfil] · [Ciudad] · [teléfono] · [correo] · [web o LinkedIn]</p>
<h2>Perfil</h2><p>[Dos o tres líneas sobre tu experiencia y lo que aportas.]</p>
<h2>Experiencia</h2>
<h3>[Puesto] — [Empresa]</h3><p><em>[mes año] – [mes año] · [Ciudad]</em></p><ul><li><p>[Logro con un dato medible.]</p></li><li><p>[Responsabilidad principal.]</p></li></ul>
<h3>[Puesto] — [Empresa]</h3><p><em>[mes año] – [mes año] · [Ciudad]</em></p><ul><li><p>[Logro con un dato medible.]</p></li></ul>
<h2>Formación</h2><p><strong>[Título]</strong> — [Centro], [año]</p>
<h2>Idiomas</h2><p>[Idioma]: [nivel] · [Idioma]: [nivel]</p>
<h2>Competencias</h2><p>[Herramienta] · [Herramienta] · [Habilidad]</p>`,
  },
  acta: {
    page: { fuente: "serif", numeros_pagina: "pie" },
    html: `<h1 style="text-align: center">Acta de la reunión de [órgano o equipo]</h1>
<p><strong>Fecha:</strong> [fecha] · <strong>Hora:</strong> [hora] · <strong>Lugar:</strong> [lugar]</p>
<p><strong>Asistentes:</strong> [nombres]. <strong>Excusan su asistencia:</strong> [nombres].</p>
<h2>Orden del día</h2><ol><li><p>Lectura y aprobación del acta anterior.</p></li><li><p>[Asunto].</p></li><li><p>Ruegos y preguntas.</p></li></ol>
<h2>Desarrollo</h2><h3>1. Lectura del acta anterior</h3><p>[Resumen.]</p><h3>2. [Asunto]</h3><p>[Lo que se trató y las posturas.]</p>
<h2>Acuerdos</h2><ul data-type="taskList"><li data-type="taskItem" data-checked="false"><p>[Acuerdo] — responsable: [nombre], fecha: [fecha].</p></li></ul>
<p>Sin más asuntos que tratar, se levanta la sesión a las [hora].</p>
<p>El/la secretario/a: ${field("Firma secretario", 50)} &nbsp; V.º B.º El/la presidente/a: ${field("Firma presidente", 50)}</p>`,
  },
  informe: {
    page: { fuente: "serif", numeros_pagina: "pie", formato_numero: "n_de_total" },
    html: `<h1>[Título del informe]</h1><p>[Autor] · [Departamento] · [fecha]</p>
<nav data-type="indice" class="indice-editor"></nav>
<h2>Resumen</h2><p>[Las conclusiones principales en un párrafo.]</p>
<h2>Introducción</h2><p>[Contexto y objetivo del informe.]</p>
<h2>Metodología</h2><p>[Cómo se obtuvieron los datos.]</p>
<h2>Resultados</h2><p>[Los datos, con tablas o gráficos.]</p>
<table><tbody><tr><th><p>Indicador</p></th><th><p>Valor</p></th><th><p>Variación</p></th></tr><tr><td><p>[Indicador]</p></td><td><p>[valor]</p></td><td><p>[+0 %]</p></td></tr></tbody></table>
<h2>Conclusiones</h2><p>[Qué significan los resultados y qué se recomienda.]</p>`,
  },
  certificado: {
    page: { fuente: "serif", numeros_pagina: "ninguno", orientacion: "horizontal", borde: "doble" },
    html: `<p></p><h1 style="text-align: center">CERTIFICADO</h1>
<p style="text-align: center">Se certifica que</p>
<h2 style="text-align: center">[Nombre y apellidos]</h2>
<p style="text-align: center">ha completado [el curso, la formación o el logro] con una duración de [horas] horas,<br>celebrado en [lugar] del [fecha] al [fecha].</p>
<p></p><p style="text-align: center">[Ciudad], a [fecha]</p><p></p>
<p style="text-align: center">[Nombre de quien firma]<br>[Cargo]</p>`,
  },
  folleto: {
    page: { fuente: "sans", numeros_pagina: "ninguno", margenes_mm: 15 },
    html: `<h1 style="text-align: center">[Nombre del evento o del producto]</h1>
<p style="text-align: center"><strong>[Lema en una línea]</strong></p>
<div class="columnas" data-columnas="2"><h2>¿Qué es?</h2><p>[Descripción breve y atractiva.]</p>
<h2>Para quién</h2><ul><li><p>[Público]</p></li><li><p>[Público]</p></li></ul>
<h2>Cuándo y dónde</h2><p>[Fecha, hora y lugar.]</p>
<h2>Precio</h2><p>[Precio o «gratis».]</p>
<h2>Contacto</h2><p>[Web · teléfono · correo]</p></div>`,
  },
  solicitud: {
    page: { fuente: "serif", numeros_pagina: "ninguno" },
    html: `<h1 style="text-align: center">Solicitud de [objeto]</h1>
<h2>Datos del solicitante</h2>
<p>Nombre y apellidos: ${field("Nombre y apellidos", 100)}</p>
<p>DNI/NIE: ${field("DNI", 40)} &nbsp; Teléfono: ${field("Telefono", 40)}</p>
<p>Correo electrónico: ${field("Correo", 90)}</p>
<p>Domicilio: ${field("Domicilio", 110)}</p>
<h2>Expone</h2><p>[Los hechos y los motivos de la solicitud.]</p>
<h2>Solicita</h2><p>[Lo que se pide, con claridad.]</p>
<p>${field("Acepto la política de privacidad", 4, "casilla")} He leído y acepto el tratamiento de mis datos para gestionar esta solicitud.</p>
<p>En [ciudad], a ${field("Fecha", 35, "fecha")}</p><p>Firma: ${field("Firma", 70)}</p>
<p><strong>A la atención de:</strong> [órgano o empresa]</p>`,
  },
};

const EN: Record<TemplateKey, Template> = {
  blanco: { html: "<p></p>" },
  carta: {
    page: { fuente: "serif", numeros_pagina: "ninguno", idioma: "en" },
    html: `<p style="text-align: right">[Your name]<br>[Your address]<br>[Postcode and city]<br>[Phone · email]</p>
<p style="text-align: right">[Date]</p>
<p>[Recipient's name]<br>[Company or organisation]<br>[Address]</p>
<p><strong>Re:</strong> [subject of the letter]</p>
<p>Dear [name],</p>
<p>[First paragraph: introduce yourself and explain why you are writing.]</p>
<p>[Second paragraph: the details, facts or request.]</p>
<p>[Closing: what you hope will happen and how to reach you.]</p>
<p>Yours sincerely,</p><p></p><p>[Signature]<br>[Your name]</p>`,
  },
  presupuesto: {
    page: { fuente: "sans", numeros_pagina: "pie", idioma: "en" },
    html: `<h1>Quote no. [000]</h1>
<p><strong>Date:</strong> [date] · <strong>Valid until:</strong> [date]</p>
<table><tbody><tr><th><p>From</p></th><th><p>To</p></th></tr><tr><td><p>[Your company]<br>[Tax ID]<br>[Address]</p></td><td><p>[Customer]<br>[Tax ID]<br>[Address]</p></td></tr></tbody></table>
<h2>Items</h2>
<table><tbody><tr><th><p>Item</p></th><th><p>Quantity</p></th><th><p>Price</p></th><th><p>Amount</p></th></tr>
<tr><td><p>[Service or product]</p></td><td><p>1</p></td><td><p>0.00</p></td><td><p>0.00</p></td></tr>
<tr><td><p>[Service or product]</p></td><td><p>1</p></td><td><p>0.00</p></td><td><p>0.00</p></td></tr>
<tr><td><p><strong>Subtotal</strong></p></td><td><p></p></td><td><p></p></td><td><p>0.00</p></td></tr>
<tr><td><p><strong>Tax</strong></p></td><td><p></p></td><td><p></p></td><td><p>0.00</p></td></tr>
<tr><td><p><strong>Total</strong></p></td><td><p></p></td><td><p></p></td><td><p><strong>0.00</strong></p></td></tr></tbody></table>
<h2>Terms</h2><ul><li><p>Payment: [bank transfer, 30 days].</p></li><li><p>Delivery: [timescale].</p></li></ul>
<p>Customer acceptance: ${field("Name and signature", 70)} Date: ${field("Acceptance date", 30, "fecha")}</p>`,
  },
  cv: {
    page: { fuente: "sans", numeros_pagina: "ninguno", margenes_mm: 18, idioma: "en" },
    html: `<h1>[Full name]</h1>
<p>[Role or profile] · [City] · [phone] · [email] · [website or LinkedIn]</p>
<h2>Profile</h2><p>[Two or three lines about your experience and what you bring.]</p>
<h2>Experience</h2>
<h3>[Role] — [Company]</h3><p><em>[month year] – [month year] · [City]</em></p><ul><li><p>[Achievement with a measurable figure.]</p></li><li><p>[Main responsibility.]</p></li></ul>
<h3>[Role] — [Company]</h3><p><em>[month year] – [month year] · [City]</em></p><ul><li><p>[Achievement with a measurable figure.]</p></li></ul>
<h2>Education</h2><p><strong>[Qualification]</strong> — [Institution], [year]</p>
<h2>Languages</h2><p>[Language]: [level] · [Language]: [level]</p>
<h2>Skills</h2><p>[Tool] · [Tool] · [Skill]</p>`,
  },
  acta: {
    page: { fuente: "serif", numeros_pagina: "pie", idioma: "en" },
    html: `<h1 style="text-align: center">Minutes of the [board or team] meeting</h1>
<p><strong>Date:</strong> [date] · <strong>Time:</strong> [time] · <strong>Place:</strong> [place]</p>
<p><strong>Present:</strong> [names]. <strong>Apologies:</strong> [names].</p>
<h2>Agenda</h2><ol><li><p>Approval of the previous minutes.</p></li><li><p>[Item].</p></li><li><p>Any other business.</p></li></ol>
<h2>Discussion</h2><h3>1. Previous minutes</h3><p>[Summary.]</p><h3>2. [Item]</h3><p>[What was discussed and the positions.]</p>
<h2>Actions</h2><ul data-type="taskList"><li data-type="taskItem" data-checked="false"><p>[Action] — owner: [name], due: [date].</p></li></ul>
<p>There being no further business, the meeting closed at [time].</p>
<p>Secretary: ${field("Secretary signature", 50)} &nbsp; Chair: ${field("Chair signature", 50)}</p>`,
  },
  informe: {
    page: { fuente: "serif", numeros_pagina: "pie", formato_numero: "n_de_total", idioma: "en" },
    html: `<h1>[Report title]</h1><p>[Author] · [Department] · [date]</p>
<nav data-type="indice" class="indice-editor"></nav>
<h2>Summary</h2><p>[The main conclusions in one paragraph.]</p>
<h2>Introduction</h2><p>[Background and purpose of the report.]</p>
<h2>Method</h2><p>[How the data was gathered.]</p>
<h2>Results</h2><p>[The data, with tables or charts.]</p>
<table><tbody><tr><th><p>Indicator</p></th><th><p>Value</p></th><th><p>Change</p></th></tr><tr><td><p>[Indicator]</p></td><td><p>[value]</p></td><td><p>[+0%]</p></td></tr></tbody></table>
<h2>Conclusions</h2><p>[What the results mean and what is recommended.]</p>`,
  },
  certificado: {
    page: { fuente: "serif", numeros_pagina: "ninguno", orientacion: "horizontal", borde: "doble", idioma: "en" },
    html: `<p></p><h1 style="text-align: center">CERTIFICATE</h1>
<p style="text-align: center">This is to certify that</p>
<h2 style="text-align: center">[Full name]</h2>
<p style="text-align: center">has completed [the course, training or achievement] lasting [hours] hours,<br>held at [place] from [date] to [date].</p>
<p></p><p style="text-align: center">[City], [date]</p><p></p>
<p style="text-align: center">[Signatory's name]<br>[Position]</p>`,
  },
  folleto: {
    page: { fuente: "sans", numeros_pagina: "ninguno", margenes_mm: 15, idioma: "en" },
    html: `<h1 style="text-align: center">[Event or product name]</h1>
<p style="text-align: center"><strong>[One-line tagline]</strong></p>
<div class="columnas" data-columnas="2"><h2>What is it?</h2><p>[A short, appealing description.]</p>
<h2>Who is it for?</h2><ul><li><p>[Audience]</p></li><li><p>[Audience]</p></li></ul>
<h2>When and where</h2><p>[Date, time and place.]</p>
<h2>Price</h2><p>[Price or “free”.]</p>
<h2>Contact</h2><p>[Website · phone · email]</p></div>`,
  },
  solicitud: {
    page: { fuente: "serif", numeros_pagina: "ninguno", idioma: "en" },
    html: `<h1 style="text-align: center">Application for [subject]</h1>
<h2>Applicant details</h2>
<p>Full name: ${field("Full name", 100)}</p>
<p>ID number: ${field("ID number", 40)} &nbsp; Phone: ${field("Phone", 40)}</p>
<p>Email: ${field("Email", 90)}</p>
<p>Address: ${field("Address", 110)}</p>
<h2>Statement</h2><p>[The facts and reasons for the application.]</p>
<h2>Request</h2><p>[What is being requested, clearly.]</p>
<p>${field("I accept the privacy policy", 4, "casilla")} I have read and accept the processing of my data to handle this application.</p>
<p>Date: ${field("Date", 35, "fecha")}</p><p>Signature: ${field("Signature", 70)}</p>
<p><strong>For the attention of:</strong> [body or company]</p>`,
  },
};

export function template(key: TemplateKey, locale: "es" | "en"): Template {
  return (locale === "en" ? EN : ES)[key];
}
