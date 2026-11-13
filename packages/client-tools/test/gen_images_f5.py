# Genera images-f5.fixture.ts: ejecutar con el Python del proyecto (.venv/bin/python gen_images_f5.py) desde esta carpeta.
import base64, io, struct
from PIL import Image, ExifTags, PngImagePlugin

XMP = (b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
       b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
       b'exif:GPSLatitude="40,25.0N" exif:GPSLongitude="3,42.0W"><dc:creator>Autor Demo</dc:creator>'
       b'<exif:GPSAltitude>657/1</exif:GPSAltitude></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')

def exif(orientation=6):
    e = Image.Exif()
    e[0x010F] = "Camara de prueba"
    e[0x0112] = orientation
    e[ExifTags.IFD.GPSInfo] = {1: "N", 2: (40.0, 25.0, 0.0), 3: "W", 4: (3.0, 42.0, 0.0)}
    return e

def gradient(w, h, alpha=False):
    img = Image.new("RGBA" if alpha else "RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            v = (x * 255 // max(1, w - 1), y * 255 // max(1, h - 1), 128)
            px[x, y] = v + ((255 if x < w // 2 else 0),) if alpha else v
    return img

out = {}
# JPEG con EXIF (orientación 6 y GPS), XMP con GPS, comentario y cola tras el EOI con un átomo ©xyz.
buf = io.BytesIO()
gradient(64, 48).save(buf, "JPEG", quality=90, exif=exif(), comment=b"comentario privado")
jpg = buf.getvalue()
# Inserta el XMP tras el APP1 del EXIF.
i = 2
while True:
    marker = jpg[i + 1]
    length = struct.unpack(">H", jpg[i + 2:i + 4])[0]
    if marker == 0xE1:
        i += 2 + length
        break
    i += 2 + length
payload = b"http://ns.adobe.com/xap/1.0/\x00" + XMP
app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
jpg = jpg[:i] + app1 + jpg[i:]
text = b"+40.4168-003.7038/"
atom = struct.pack(">I", 12 + len(text)) + b"\xa9xyz" + struct.pack(">H", len(text)) + b"\x15\xc7" + text
jpg += b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 12 + atom
out["JPEG_GPS"] = jpg

# PNG con alfa, eXIf (GPS), XMP en iTXt y comentario en tEXt.
info = PngImagePlugin.PngInfo()
info.add_text("Comment", "comentario privado")
info.add_itxt("XML:com.adobe.xmp", XMP.decode("utf-8"))
buf = io.BytesIO()
gradient(40, 30, alpha=True).save(buf, "PNG", pnginfo=info, exif=exif(1))
out["PNG_GPS"] = buf.getvalue()

# WebP sin pérdida con EXIF y XMP.
buf = io.BytesIO()
gradient(32, 24).save(buf, "WEBP", lossless=True, exif=exif(1), xmp=XMP)
out["WEBP_GPS"] = buf.getvalue()

# TIFF de dos páginas (LZW) de tamaños distintos.
p1 = gradient(30, 20)
p2 = Image.new("RGB", (16, 8), (200, 30, 30))
buf = io.BytesIO()
p1.save(buf, "TIFF", compression="tiff_lzw", save_all=True, append_images=[p2])
out["TIFF_2P"] = buf.getvalue()

# GIF animado de dos fotogramas.
f1 = Image.new("RGB", (10, 10), (255, 0, 0))
f2 = Image.new("RGB", (10, 10), (0, 0, 255))
buf = io.BytesIO()
f1.save(buf, "GIF", save_all=True, append_images=[f2], duration=100, loop=0)
out["GIF_ANIM"] = buf.getvalue()

with open("images-f5.fixture.ts", "w") as f:
    f.write("// Imágenes de prueba de F5 lote B1 generadas con Pillow (generadas con Pillow por gen_images_f5.py; sin derechos de terceros).\n")
    for k, v in out.items():
        f.write(f'export const {k} = "{base64.b64encode(v).decode()}";\n')
for k, v in out.items():
    print(k, len(v))
