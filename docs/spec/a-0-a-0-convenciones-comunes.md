### A.0 Convenciones comunes

- **Rangos de páginas:**
  - sintaxis `1-3, 5, 8-` (un final abierto llega hasta la última página);
  - atajos «impares», «pares» y «todas»;
  - se validan en cliente y en servidor.
- **Posición:** rejilla de 9 (arriba, medio o abajo × izquierda, centro o derecha); algunas herramientas usan 6.
- **Color:** selector más opacidad de 0 a 1.
- **Unidades:** mm o pulgadas. Internamente, puntos PDF: 1 mm = 2,8346 pt.
- **Papel:**
  - A0 a A6, Letter y Legal, y Personalizado;
  - las herramientas de impresión añaden A3, A5 y Media carta donde aplica.
- **Fuentes «Sans | Serif | Mono»:** Noto Sans, Noto Serif y Noto Sans Mono (OFL), incrustadas como subconjunto, para que salgan bien tildes, eñes, € y alfabetos no latinos.
- **Lotes:**
  - varios archivos reciben las mismas opciones;
  - la salida es un archivo por entrada más un ZIP con todo, salvo que la herramienta una en un solo archivo.
- **PDF con contraseña:** se pide la contraseña al abrir, nunca se fuerza (`PASSWORD_REQUIRED`).
- **Resultado:**
  - muestra tamaño antes y después, número de páginas y avisos (por ejemplo, «se ha perdido el PDF/A» o «se han quitado las etiquetas de accesibilidad»);
  - siempre ofrece «Seguir con otra herramienta».
