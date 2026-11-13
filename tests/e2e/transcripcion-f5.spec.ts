import { expect, test } from "@playwright/test";

// F5, lote E: las páginas de transcribir-audio y video-a-subtitulos (la transcripción real con faster-whisper la prueba
// pytest con el modelo tiny, y el proyecto «servidor», con la pila completa).

test("transcribir-audio: audio y vídeo admitidos, idioma, formato y minuto de cada párrafo según el formato", async ({ page }) => {
  await page.goto("/es/transcribir-audio");
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", /\.mp3.*\.ogg.*\.m4a.*\.mp4.*\.webm/);
  await expect(page.getByLabel("Idioma del audio")).toHaveValue("auto");
  await expect(page.getByLabel("Idioma del audio").locator("option")).toHaveCount(21);
  await expect(page.getByLabel("Formato")).toHaveValue("txt");
  await expect(page.getByLabel("Minuto de cada párrafo")).toBeVisible();
  await page.getByLabel("Formato").selectOption("srt");
  await expect(page.getByLabel("Minuto de cada párrafo")).toHaveCount(0);
  await page.getByLabel("Formato").selectOption("todos");
  await expect(page.getByLabel("Minuto de cada párrafo")).toBeVisible();
});

test("video-a-subtitulos: vídeos admitidos, SRT o VTT y ancho de línea en las opciones adicionales", async ({ page }) => {
  await page.goto("/en/video-to-subtitles");
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".mp4,.mov,.mkv,.webm,.avi");
  await expect(page.getByLabel("Video language")).toHaveValue("auto");
  await expect(page.getByLabel("Format")).toHaveValue("srt");
  await page.getByText("More options").click();
  await expect(page.getByLabel("Characters per line (two lines at most)")).toHaveValue("42");
  await expect(page.getByLabel("Accuracy")).toHaveValue("normal");
});
