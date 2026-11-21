"""Impresión 3D (7.18 a 7.21, F7): herramientas del grupo `mesh` (`workermesh`, cola `mesh`)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import ToolSpec

UNIT_LABELS = {"mm": ("Milímetros", "Millimetres"), "cm": ("Centímetros", "Centimetres"), "m": ("Metros", "Metres"),
               "in": ("Pulgadas", "Inches")}
Unit = Literal["mm", "cm", "m", "in"]


class MeshOptions(BaseModel):
    """7.18 (F7-A, D-244): unidades de origen [automáticas] y destino [mm], escala [1] y piezas [mantener]."""

    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = opt(
        "auto", "Unidades del original", "Units of the original",
        labels={"auto": ("Las del archivo (o milímetros)", "The file's (or millimetres)"), **UNIT_LABELS})
    unidades_destino: Unit = opt("mm", "Unidades del resultado", "Units of the result", labels=UNIT_LABELS)
    escala: float = opt(1.0, "Escala", "Scale", ge=0.001, le=1000, advanced=True)
    piezas: Literal["mantener", "fusionar", "separar"] = opt("mantener", "Piezas", "Parts", advanced=True, labels={
        "mantener": ("Mantenerlas si el formato lo admite", "Keep them if the format allows it"),
        "fusionar": ("Fusionarlas en una", "Merge into one"),
        "separar": ("Un archivo por pieza (ZIP)", "One file per part (ZIP)")})


class MeshStlOptions(MeshOptions):
    """Las de 7.18 más STL [binario] | ASCII."""

    stl: Literal["binario", "ascii"] = opt("binario", "Tipo de STL", "STL type", advanced=True, labels={
        "binario": ("Binario (más pequeño)", "Binary (smaller)"), "ascii": ("ASCII (texto)", "ASCII (text)")})


class MeshAxesOptions(MeshOptions):
    """Las de 7.18 más conservar los ejes (F7-B, D-248): sin marcar, Y vertical (glTF, FBX, DAE, 3DS) pasa a Z vertical."""

    conservar_ejes: bool = opt(False, "Conservar los ejes del original (no girar de Y vertical a Z vertical)",
                               "Keep the original axes (do not turn Y-up into Z-up)", advanced=True)


class MeshAxesStlOptions(MeshStlOptions):
    conservar_ejes: bool = opt(False, "Conservar los ejes del original (no girar de Y vertical a Z vertical)",
                               "Keep the original axes (do not turn Y-up into Z-up)", advanced=True)


class MeshGlbOptions(BaseModel):
    """A GLB (F7-B, D-248): siempre en metros, como pide glTF; unidades del original, escala, piezas y ejes."""

    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = opt(
        "auto", "Unidades del original", "Units of the original",
        labels={"auto": ("Las del archivo (o milímetros)", "The file's (or millimetres)"), **UNIT_LABELS})
    escala: float = opt(1.0, "Escala", "Scale", ge=0.001, le=1000, advanced=True)
    piezas: Literal["mantener", "fusionar", "separar"] = opt("mantener", "Piezas", "Parts", advanced=True, labels={
        "mantener": ("Mantenerlas", "Keep them"), "fusionar": ("Fusionarlas en una", "Merge into one"),
        "separar": ("Un archivo por pieza (ZIP)", "One file per part (ZIP)")})
    conservar_ejes: bool = opt(False, "Conservar los ejes (no girar de Z vertical a Y vertical)", "Keep the axes (do not turn Z-up into Y-up)",
                               advanced=True)


Y_UP = {"glb", "gltf", "fbx", "dae", "3ds", "wrl", "x3d", "usdz"}
ANY_INPUT = ("stl", "obj", "3mf", "ply", "off", "amf", "glb", "gltf", "fbx", "dae", "3ds", "wrl", "x3d", "usd", "usda", "usdc", "usdz")
OUTPUTS = {"stl": ("STL", "STL"), "obj": ("OBJ (con MTL si hay colores)", "OBJ (with MTL if there are colours)"), "3mf": ("3MF", "3MF"),
           "ply": ("PLY", "PLY"), "off": ("OFF", "OFF"), "amf": ("AMF", "AMF"), "glb": ("GLB (glTF binario)", "GLB (binary glTF)"),
           "x3d": ("X3D", "X3D"), "wrl": ("VRML (WRL)", "VRML (WRL)"), "usdz": ("USDZ (realidad aumentada)", "USDZ (augmented reality)")}


class ConvertirModeloOptions(MeshAxesStlOptions):
    """convertir-modelo-3d (7.18, F7-C, D-250): cualquier entrada de 7.18 a [STL] o a cualquier salida; las opciones de 7.18."""

    formato: Literal["stl", "obj", "3mf", "ply", "off", "amf", "glb", "x3d", "wrl", "usdz"] = opt(
        "stl", "Convertir a", "Convert to", labels=OUTPUTS)
NAMES = {"stl": "STL", "obj": "OBJ", "3mf": "3MF", "ply": "PLY", "amf": "AMF", "glb": "GLB", "gltf": "glTF", "fbx": "FBX",
         "dae": "DAE", "3ds": "3DS", "wrl": "WRL", "x3d": "X3D", "usdz": "USDZ"}
WHAT = {
    "stl": ("el formato de malla de las impresoras 3D", "the mesh format of 3D printers"),
    "obj": ("el formato de modelos 3D de Blender, Maya y los visores", "the 3D model format of Blender, Maya and viewers"),
    "3mf": ("el formato moderno de impresión 3D, con unidades y colores", "the modern 3D printing format, with units and colours"),
    "ply": ("el formato de escáneres 3D y nubes de puntos con color", "the format of 3D scanners and coloured point clouds"),
    "amf": ("el formato XML de fabricación aditiva con unidades y colores", "the additive manufacturing XML format with units and colours"),
    "glb": ("el formato 3D de la web, la realidad aumentada y los visores", "the 3D format of the web, augmented reality and viewers"),
    "wrl": ("el formato VRML de la impresión 3D en color", "the VRML format of full-colour 3D printing"),
    "x3d": ("el estándar abierto ISO para escenas 3D", "the open ISO standard for 3D scenes"),
    "usdz": ("el formato de realidad aumentada del iPhone y el iPad", "the augmented reality format of the iPhone and iPad"),
}


def mesh(src: str, dst: str, related: tuple[str, ...], slug_es: str | None = None, slug_en: str | None = None,
         name_es: str | None = None, name_en: str | None = None, summary_es: str | None = None, summary_en: str | None = None,
         options: type[BaseModel] | None = None) -> ToolSpec:
    a, b = NAMES[src], NAMES[dst]
    return ToolSpec(
        slug_es=slug_es or f"{src}-a-{dst}", slug_en=slug_en or f"{src}-to-{dst}", name_es=name_es or f"{a} a {b}",
        name_en=name_en or f"{a} to {b}", category="3d", where="server", inputs=(src,), outputs=(dst, "zip"),
        options=options or _options(src, dst), worker_group="mesh", cost_class="light",
        impl="tools.mesh.convert:run", precheck="tools.mesh.recuento:precheck", launch=True, phase="F7", time_limit=600,
        max_files=10,
        summary_es=summary_es or f"Convierte modelos {a} a {b}, {WHAT[dst][0]}, con unidades y escala.",
        summary_en=summary_en or f"Convert {a} models to {b}, {WHAT[dst][1]}, with units and scale.", related=related)


def _options(src: str, dst: str) -> type[BaseModel]:
    if dst == "glb":
        return MeshGlbOptions
    if src in Y_UP:
        return MeshAxesStlOptions if dst == "stl" else MeshAxesOptions
    return MeshStlOptions if dst == "stl" else MeshOptions


SPECS = [
    # 7.18 (F7-A, D-244): trimesh para STL, OBJ y PLY; lib3mf para 3MF.
    mesh("stl", "obj", ("obj-a-stl", "stl-a-3mf")),
    mesh("obj", "stl", ("stl-a-obj", "obj-a-3mf")),
    mesh("stl", "3mf", ("3mf-a-stl", "stl-a-obj")),
    mesh("3mf", "stl", ("stl-a-3mf", "3mf-a-obj")),
    mesh("obj", "3mf", ("3mf-a-obj", "obj-a-stl")),
    mesh("3mf", "obj", ("obj-a-3mf", "3mf-a-stl")),
    mesh("stl", "ply", ("ply-a-stl", "stl-a-obj")),
    mesh("ply", "stl", ("stl-a-ply", "stl-a-3mf")),
    mesh("stl", "stl", ("stl-a-3mf", "stl-a-obj"), slug_es="stl-ascii-a-binario", slug_en="stl-ascii-to-binary",
         name_es="STL ASCII a binario", name_en="STL ASCII to binary", options=MeshOptions,
         summary_es="Convierte un STL de texto (ASCII) en STL binario, que ocupa unas cinco veces menos.",
         summary_en="Convert a text (ASCII) STL into binary STL, about five times smaller."),
    # 7.18 (F7-B, D-248): AMF propio, GLB y glTF con trimesh, y FBX, DAE y 3DS con assimp en un proceso hijo.
    mesh("amf", "stl", ("stl-a-amf", "amf-a-3mf")),
    mesh("stl", "amf", ("amf-a-stl", "stl-a-3mf")),
    mesh("amf", "3mf", ("amf-a-stl", "3mf-a-stl")),
    mesh("glb", "stl", ("stl-a-glb", "gltf-a-stl")),
    mesh("stl", "glb", ("glb-a-stl", "stl-a-obj")),
    mesh("gltf", "stl", ("glb-a-stl", "stl-a-glb"), summary_es="Convierte modelos glTF (con sus datos incrustados) a STL para imprimirlos en 3D.",
         summary_en="Convert glTF models (with embedded data) to STL for 3D printing."),
    mesh("fbx", "stl", ("fbx-a-obj", "obj-a-stl")),
    mesh("fbx", "obj", ("fbx-a-stl", "obj-a-3mf")),
    mesh("dae", "stl", ("stl-a-obj", "fbx-a-stl")),
    mesh("3ds", "stl", ("stl-a-obj", "fbx-a-stl")),
    # 7.18 (F7-C, D-250): VRML y X3D propios, USDZ con usd-core y convertir-modelo-3d para el resto de combinaciones.
    mesh("wrl", "stl", ("stl-a-wrl", "x3d-a-stl")),
    mesh("stl", "wrl", ("wrl-a-stl", "stl-a-x3d")),
    mesh("x3d", "stl", ("stl-a-x3d", "wrl-a-stl")),
    mesh("stl", "x3d", ("x3d-a-stl", "stl-a-wrl")),
    mesh("stl", "usdz", ("obj-a-usdz", "stl-a-glb")),
    mesh("obj", "usdz", ("stl-a-usdz", "obj-a-3mf")),
]

# convertir-modelo-3d (7.18, F7-C, D-250): el resto de combinaciones, desde cualquier entrada a cualquier salida.
SPECS.append(ToolSpec(
    slug_es="convertir-modelo-3d", slug_en="3d-model-converter", name_es="Convertir modelo 3D", name_en="3D model converter",
    category="3d", where="server", inputs=ANY_INPUT, outputs=(*OUTPUTS, "zip"), options=ConvertirModeloOptions, worker_group="mesh",
    cost_class="light", impl="tools.mesh.convert:run", precheck="tools.mesh.recuento:precheck", launch=True, phase="F7", time_limit=600,
    max_files=10, summary_es="Convierte modelos 3D entre STL, OBJ, 3MF, PLY, OFF, AMF, GLB, glTF, FBX, DAE, 3DS, VRML, X3D y USD.",
    summary_en="Convert 3D models between STL, OBJ, 3MF, PLY, OFF, AMF, GLB, glTF, FBX, DAE, 3DS, VRML, X3D and USD.",
    related=("stl-a-3mf", "stl-a-obj")))


# ——— F7-F (7.20, D-253): herramientas de mallas ———

MESH_IN = ("stl", "obj", "3mf", "ply", "amf", "glb", "off")
FORMAT_OUT = {"mismo": ("El mismo que el original", "Same as the original"), "stl": ("STL", "STL"), "3mf": ("3MF", "3MF"),
              "obj": ("OBJ", "OBJ")}
ORIGIN = {"auto": ("Las del archivo (o milímetros)", "The file's (or millimetres)"), **UNIT_LABELS}


def _fmt():
    return opt("mismo", "Formato del resultado", "Output format", advanced=True, labels=FORMAT_OUT)


def _origin():
    return opt("auto", "Unidades del original", "Units of the original", advanced=True, labels=ORIGIN)


class RepararOptions(BaseModel):
    """reparar-stl: quitar piezas sueltas pequeñas [sí], unir piezas solapadas [sí] y formato [el mismo]."""

    quitar_sueltas: bool = opt(True, "Quitar restos sueltos pequeños (menos del 1 % de los triángulos o del 2 % del tamaño)",
                               "Remove small loose leftovers (under 1% of the triangles or 2% of the size)")
    unir_solapes: bool = opt(True, "Unir piezas cerradas que se solapan (autointersecciones)", "Merge closed parts that overlap (self-intersections)")
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["mismo", "stl", "3mf", "obj"] = _fmt()


class ReducirOptions(BaseModel):
    """reducir-poligonos: reducción [50 %] o triángulos objetivo, con decimación cuádrica."""

    reduccion: int = opt(50, "Reducir (%)", "Reduce by (%)", ge=5, le=95)
    triangulos: int = opt(0, "O como mucho estos triángulos (0: usar el porcentaje)", "Or at most these triangles (0: use the percentage)",
                          ge=0, le=10_000_000, advanced=True)
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["mismo", "stl", "3mf", "obj"] = _fmt()


class EscalarOptions(BaseModel):
    """escalar-modelo-3d: por un factor [1] (también por eje) o hasta una medida en un eje."""

    modo: Literal["factor", "medida"] = opt("factor", "Escalar por", "Scale by", labels={
        "factor": ("Un factor", "A factor"), "medida": ("Una medida final", "A final size")})
    factor: float = opt(1.0, "Factor (1 = igual, 2 = el doble)", "Factor (1 = same, 2 = double)", ge=0.001, le=1000)
    eje: Literal["mayor", "x", "y", "z"] = opt("mayor", "Eje de la medida", "Axis of the size", labels={
        "mayor": ("El lado más largo", "The longest side"), "x": ("X (ancho)", "X (width)"), "y": ("Y (fondo)", "Y (depth)"),
        "z": ("Z (alto)", "Z (height)")})
    medida_mm: float = opt(100.0, "Medida final (mm)", "Final size (mm)", ge=0.01, le=100000)
    escala_x: float = opt(1.0, "Factor extra en X", "Extra factor in X", ge=0.001, le=1000, advanced=True)
    escala_y: float = opt(1.0, "Factor extra en Y", "Extra factor in Y", ge=0.001, le=1000, advanced=True)
    escala_z: float = opt(1.0, "Factor extra en Z", "Extra factor in Z", ge=0.001, le=1000, advanced=True)
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["mismo", "stl", "3mf", "obj"] = _fmt()


class UnidadesOptions(BaseModel):
    """cambiar-unidades-stl: de [pulgadas] a [milímetros]."""

    de: Unit = opt("in", "El STL está en", "The STL is in", labels=UNIT_LABELS)
    a: Unit = opt("mm", "Pasarlo a", "Convert it to", labels=UNIT_LABELS)


class CortarOptions(BaseModel):
    """cortar-modelo-3d: plano perpendicular a un eje [Z] en una posición [50 %], con la sección tapada si se puede."""

    eje: Literal["x", "y", "z"] = opt("z", "Cortar perpendicular al eje", "Cut perpendicular to the axis", labels={
        "x": ("X", "X"), "y": ("Y", "Y"), "z": ("Z (horizontal)", "Z (horizontal)")})
    unidad_posicion: Literal["porcentaje", "mm"] = opt("porcentaje", "Posición en", "Position in", labels={
        "porcentaje": ("Porcentaje de la altura", "Percentage of the extent"), "mm": ("Milímetros", "Millimetres")})
    posicion: float = opt(50.0, "Posición del corte", "Cut position", ge=-100000, le=100000)
    conservar: Literal["ambas", "debajo", "encima"] = opt("ambas", "Conservar", "Keep", labels={
        "ambas": ("Las dos partes (ZIP)", "Both parts (ZIP)"), "debajo": ("La de debajo", "The lower one"), "encima": ("La de encima", "The upper one")})
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["mismo", "stl", "3mf", "obj"] = _fmt()


class SepararOptions(BaseModel):
    """separar-piezas: una pieza por archivo, sin las de menos de [4] triángulos."""

    minimo_triangulos: int = opt(4, "Ignorar piezas de menos de estos triángulos", "Ignore parts under these triangles", ge=1, le=100000)
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["mismo", "stl", "3mf", "obj"] = _fmt()


class UnirOptions(BaseModel):
    """unir-modelos: en sus posiciones [sí] o uno al lado de otro, unión booleana opcional y formato [3MF]."""

    modo: Literal["mantener", "distribuir"] = opt("mantener", "Posición", "Position", labels={
        "mantener": ("Donde están en cada archivo", "Where they are in each file"),
        "distribuir": ("Uno al lado de otro, apoyados en la cama", "Side by side, resting on the bed")})
    separacion_mm: float = opt(5.0, "Separación entre modelos (mm)", "Gap between models (mm)", ge=0, le=1000, advanced=True)
    fusionar: bool = opt(False, "Fusionarlos en un solo sólido (unión booleana)", "Fuse them into one solid (boolean union)", advanced=True)
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato_salida: Literal["3mf", "stl", "obj"] = opt("3mf", "Formato del resultado", "Output format", labels={
        "3mf": ("3MF (una pieza por modelo)", "3MF (one part per model)"), "stl": ("STL", "STL"), "obj": ("OBJ", "OBJ")})


class AnalizarOptions(BaseModel):
    """analizar-stl: material [PLA], relleno [20 %], paredes [1,2 mm], diámetro [1,75 mm] y formato [texto]."""

    material: Literal["PLA", "PETG", "ABS", "TPU"] = opt("PLA", "Material", "Material", labels={k: (k, k) for k in ("PLA", "PETG", "ABS", "TPU")})
    relleno: int = opt(20, "Relleno (%)", "Infill (%)", ge=0, le=100)
    paredes_mm: float = opt(1.2, "Grosor de paredes, techo y suelo (mm)", "Wall, top and bottom thickness (mm)", ge=0.2, le=20, advanced=True)
    diametro: Literal["1.75", "2.85"] = opt("1.75", "Diámetro del filamento", "Filament diameter", advanced=True,
                                            labels={"1.75": ("1,75 mm", "1.75 mm"), "2.85": ("2,85 mm", "2.85 mm")})
    unidades_origen: Literal["auto", "mm", "cm", "m", "in"] = _origin()
    formato: Literal["txt", "json"] = opt("txt", "Formato del informe", "Report format", advanced=True,
                                          labels={"txt": ("Texto", "Text"), "json": ("JSON", "JSON")})


def op(slug_es, slug_en, name_es, name_en, options, summary_es, summary_en, related, inputs=MESH_IN, outputs=("stl", "obj", "3mf", "ply", "amf", "glb", "off", "zip"),
       impl="tools.mesh.convert:run_ops", max_files=10) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="3d", where="server", inputs=inputs,
                    outputs=outputs, options=options, worker_group="mesh", cost_class="light", impl=impl,
                    precheck="tools.mesh.recuento:precheck", launch=True, phase="F7", time_limit=600, max_files=max_files,
                    summary_es=summary_es, summary_en=summary_en, related=related)


SPECS += [
    op("reparar-stl", "repair-stl", "Reparar STL", "Repair STL", RepararOptions,
       "Cierra huecos, orienta las normales y quita caras rotas y piezas sueltas de un modelo 3D para que se imprima bien.",
       "Close holes, orient normals and remove broken faces and loose parts from a 3D model so it prints well.", ("analizar-stl", "reducir-poligonos")),
    op("reducir-poligonos", "reduce-polygons", "Reducir polígonos", "Reduce polygons", ReducirOptions,
       "Reduce los triángulos de un modelo 3D conservando su forma, para que pese menos y se abra antes.",
       "Reduce a 3D model's triangles while keeping its shape, so it is lighter and opens faster.", ("reparar-stl", "analizar-stl")),
    op("escalar-modelo-3d", "scale-3d-model", "Escalar modelo 3D", "Scale 3D model", EscalarOptions,
       "Cambia el tamaño de un modelo 3D por un factor o hasta una medida exacta en milímetros.",
       "Resize a 3D model by a factor or to an exact size in millimetres.", ("cambiar-unidades-stl", "analizar-stl")),
    op("cambiar-unidades-stl", "change-stl-units", "Cambiar unidades de STL", "Change STL units", UnidadesOptions,
       "Pasa un STL de pulgadas, centímetros o metros a milímetros (o al revés) para que el laminador lo abra a su tamaño.",
       "Turn an STL from inches, centimetres or metres into millimetres (or back) so the slicer opens it at its size.",
       ("escalar-modelo-3d", "stl-a-3mf"), inputs=("stl",), outputs=("stl",)),
    op("cortar-modelo-3d", "cut-3d-model", "Cortar modelo 3D", "Cut 3D model", CortarOptions,
       "Corta un modelo 3D por un plano y tapa la sección, para imprimir piezas grandes en partes o quitar una base.",
       "Cut a 3D model by a plane and cap the section, to print large parts in pieces or remove a base.", ("separar-piezas", "unir-modelos")),
    op("separar-piezas", "split-parts", "Separar piezas", "Split parts", SepararOptions,
       "Separa las piezas sueltas de un modelo 3D en archivos distintos, para imprimirlas o colocarlas por separado.",
       "Split the loose parts of a 3D model into separate files, to print or place them separately.", ("unir-modelos", "cortar-modelo-3d")),
    op("unir-modelos", "join-models", "Unir modelos 3D", "Join 3D models", UnirOptions,
       "Une varios modelos 3D en un solo archivo, en sus posiciones o uno al lado de otro, o en un solo sólido.",
       "Join several 3D models into one file, in their positions or side by side, or into a single solid.", ("separar-piezas", "stl-a-3mf"),
       outputs=("3mf", "stl", "obj", "zip"), impl="tools.mesh.convert:run_join"),
    op("analizar-stl", "analyse-stl", "Analizar STL", "Analyse STL", AnalizarOptions,
       "Mide un modelo 3D: dimensiones, volumen, superficie, si es estanco y una estimación de filamento por material y relleno.",
       "Measure a 3D model: dimensions, volume, surface, whether it is watertight and a filament estimate by material and infill.",
       ("reparar-stl", "escalar-modelo-3d"), outputs=("txt", "json", "zip")),
]


# ——— F7-G (7.20, D-254): generadores ———

IMG_IN = ("png", "jpg", "webp", "bmp", "gif", "tiff")
GEN_FORMAT = {"stl": ("STL", "STL"), "3mf": ("3MF", "3MF"), "obj": ("OBJ", "OBJ")}


def _gen_fmt():
    return opt("stl", "Formato", "Format", advanced=True, labels=GEN_FORMAT)


class ExtrudeOptions(BaseModel):
    """svg-a-stl y dxf-a-stl: altura [5 mm], ancho final [el del dibujo] y placa de base opcional."""

    altura_mm: float = opt(5.0, "Altura de la extrusión (mm)", "Extrusion height (mm)", ge=0.1, le=500)
    ancho_mm: float = opt(0.0, "Ancho final (mm; 0: el del dibujo)", "Final width (mm; 0: the drawing's)", ge=0, le=5000)
    base_mm: float = opt(0.0, "Placa de base (mm; 0: sin placa)", "Base plate (mm; 0: no plate)", ge=0, le=100, advanced=True)
    margen_mm: float = opt(3.0, "Margen de la placa (mm)", "Plate margin (mm)", ge=0, le=100, advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


class LogoOptions(BaseModel):
    """logo-a-stl: umbral [128], invertir, ancho [80 mm], altura [3 mm] y placa opcional."""

    ancho_mm: float = opt(80.0, "Ancho (mm)", "Width (mm)", ge=5, le=1000)
    altura_mm: float = opt(3.0, "Altura del logo (mm)", "Logo height (mm)", ge=0.2, le=100)
    umbral: int = opt(128, "Umbral de oscuro (0-255)", "Darkness threshold (0-255)", ge=1, le=254, advanced=True)
    invertir: bool = opt(False, "Invertir (extruir lo claro)", "Invert (extrude the light parts)")
    base_mm: float = opt(0.0, "Placa de base (mm; 0: sin placa)", "Base plate (mm; 0: no plate)", ge=0, le=50, advanced=True)
    margen_mm: float = opt(3.0, "Margen de la placa (mm)", "Plate margin (mm)", ge=0, le=100, advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


class ImagenRelieveOptions(BaseModel):
    """imagen-a-stl: niveles [4], ancho [100 mm], altura [4 mm], base [1 mm] e invertir."""

    niveles: int = opt(4, "Niveles de altura", "Height levels", ge=2, le=8)
    ancho_mm: float = opt(100.0, "Ancho (mm)", "Width (mm)", ge=10, le=1000)
    altura_mm: float = opt(4.0, "Altura de los niveles (mm)", "Height of the levels (mm)", ge=0.4, le=100)
    base_mm: float = opt(1.0, "Base (mm)", "Base (mm)", ge=0.2, le=50)
    invertir: bool = opt(False, "Invertir (lo claro más alto)", "Invert (light parts higher)", advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


class TextoOptions(BaseModel):
    """texto-a-stl: texto, fuente [sans negrita], tamaño [10 mm], altura [3 mm], alineación y placa opcional."""

    texto: str = opt("Hola", "Texto", "Text", widget="textarea", max_length=300)
    fuente: Literal["sans", "sans-negrita", "serif", "serif-negrita", "mono", "condensada"] = opt("sans-negrita", "Letra", "Font", labels={
        "sans": ("Sans", "Sans"), "sans-negrita": ("Sans negrita", "Sans bold"), "serif": ("Serif", "Serif"),
        "serif-negrita": ("Serif negrita", "Serif bold"), "mono": ("Monoespaciada", "Monospace"), "condensada": ("Condensada negrita", "Condensed bold")})
    tamano_mm: float = opt(10.0, "Altura de las mayúsculas (mm)", "Capital letter height (mm)", ge=1, le=500)
    altura_mm: float = opt(3.0, "Grosor de las letras (mm)", "Letter thickness (mm)", ge=0.2, le=100)
    alineacion: Literal["izquierda", "centro", "derecha"] = opt("izquierda", "Alineación", "Alignment", advanced=True, labels={
        "izquierda": ("Izquierda", "Left"), "centro": ("Centro", "Centre"), "derecha": ("Derecha", "Right")})
    base_mm: float = opt(0.0, "Placa de base (mm; 0: sin placa)", "Base plate (mm; 0: no plate)", ge=0, le=50)
    margen_mm: float = opt(3.0, "Margen de la placa (mm)", "Plate margin (mm)", ge=0, le=100, advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


class LitofaniaOptions(BaseModel):
    """litofania: forma [plana] | curva | cilíndrica, ancho [100 mm], grosores [0,8 y 3 mm], resolución [5 px/mm]."""

    forma: Literal["plana", "curva", "cilindrica"] = opt("plana", "Forma", "Shape", labels={
        "plana": ("Plana", "Flat"), "curva": ("Curva", "Curved"), "cilindrica": ("Cilíndrica (lámpara)", "Cylindrical (lamp)")})
    ancho_mm: float = opt(100.0, "Ancho (mm; en la cilíndrica, el perímetro)", "Width (mm; perimeter for the cylinder)", ge=20, le=500)
    grosor_min: float = opt(0.8, "Grosor mínimo (mm, lo más claro)", "Minimum thickness (mm, lightest)", ge=0.3, le=5)
    grosor_max: float = opt(3.0, "Grosor máximo (mm, lo más oscuro)", "Maximum thickness (mm, darkest)", ge=0.6, le=10)
    angulo: float = opt(120.0, "Ángulo de la curva (grados)", "Curve angle (degrees)", ge=10, le=350, advanced=True)
    resolucion: float = opt(5.0, "Resolución (píxeles por mm)", "Resolution (pixels per mm)", ge=1, le=10, advanced=True)
    espejo: bool = opt(False, "Espejo (para verla por la otra cara)", "Mirror (to view it from the other side)", advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


class MapaAlturasOptions(BaseModel):
    """mapa-de-alturas-a-stl: ancho [100 mm], altura [10 mm], base [2 mm], resolución [5 px/mm] e invertir."""

    ancho_mm: float = opt(100.0, "Ancho (mm)", "Width (mm)", ge=10, le=1000)
    altura_mm: float = opt(10.0, "Altura del relieve (mm, lo más claro)", "Relief height (mm, lightest)", ge=0.2, le=200)
    base_mm: float = opt(2.0, "Base (mm)", "Base (mm)", ge=0.2, le=50)
    resolucion: float = opt(5.0, "Resolución (píxeles por mm)", "Resolution (pixels per mm)", ge=0.5, le=10, advanced=True)
    invertir: bool = opt(False, "Invertir (lo oscuro más alto)", "Invert (dark parts higher)", advanced=True)
    formato_salida: Literal["stl", "3mf", "obj"] = _gen_fmt()


def gen(slug_es, slug_en, name_es, name_en, inputs, options, summary_es, summary_en, related) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="3d", where="server", inputs=inputs,
                    outputs=("stl", "3mf", "obj", "zip"), options=options, worker_group="mesh", cost_class="light",
                    impl="tools.mesh.convert:run_generate", launch=True, phase="F7", time_limit=600, max_files=5 if inputs else None,
                    summary_es=summary_es, summary_en=summary_en, related=related)


SPECS += [
    gen("svg-a-stl", "svg-to-stl", "SVG a STL", "SVG to STL", ("svg",), ExtrudeOptions,
        "Extruye un dibujo SVG (logos, letras, siluetas) en una pieza 3D con la altura que quieras.",
        "Extrude an SVG drawing (logos, letters, silhouettes) into a 3D part at the height you want.", ("logo-a-stl", "dxf-a-stl")),
    gen("dxf-a-stl", "dxf-to-stl", "DXF a STL", "DXF to STL", ("dxf",), ExtrudeOptions,
        "Extruye los contornos cerrados de un plano DXF en una pieza 3D, con sus unidades.",
        "Extrude the closed outlines of a DXF drawing into a 3D part, with its units.", ("svg-a-stl", "dxf-a-pdf")),
    gen("imagen-a-stl", "image-to-stl", "Imagen a STL", "Image to STL", IMG_IN, ImagenRelieveOptions,
        "Convierte una imagen en un relieve 3D por niveles de altura según lo oscuro de cada zona.",
        "Turn an image into a stepped 3D relief whose height follows how dark each area is.", ("mapa-de-alturas-a-stl", "logo-a-stl")),
    gen("logo-a-stl", "logo-to-stl", "Logo a STL", "Logo to STL", IMG_IN, LogoOptions,
        "Vectoriza un logo en blanco y negro y lo extruye en una pieza 3D, con placa de base si quieres.",
        "Vectorise a black-and-white logo and extrude it into a 3D part, with a base plate if you want.", ("svg-a-stl", "imagen-a-stl")),
    gen("texto-a-stl", "text-to-stl", "Texto a STL", "Text to STL", (), TextoOptions,
        "Crea letras, carteles y placas con nombre en 3D a partir de un texto, listos para imprimir.",
        "Create 3D letters, signs and name plates from text, ready to print.", ("logo-a-stl", "svg-a-stl")),
    gen("litofania", "lithophane", "Litofanía", "Lithophane", IMG_IN, LitofaniaOptions,
        "Convierte una foto en una litofanía 3D, plana, curva o cilíndrica, que se ve al ponerle luz detrás.",
        "Turn a photo into a flat, curved or cylindrical 3D lithophane that shows when lit from behind.", ("mapa-de-alturas-a-stl", "imagen-a-stl")),
    gen("mapa-de-alturas-a-stl", "heightmap-to-stl", "Mapa de alturas a STL", "Heightmap to STL", IMG_IN, MapaAlturasOptions,
        "Convierte un mapa de alturas en escala de grises en un relieve 3D: terrenos, texturas y maquetas.",
        "Turn a greyscale heightmap into a 3D relief: terrains, textures and scale models.", ("litofania", "imagen-a-stl")),
]
