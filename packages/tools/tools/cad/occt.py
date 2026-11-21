"""STEP, IGES y BREP con OpenCascade (cadquery-ocp-novtk, Apache-2.0 con OCCT LGPL-2.1 con excepción) (7.19, F7-D, D-251).

- Lectura con XCAF (STEPCAFControl e IGESCAFControl): las formas libres con su nombre y su color, también el de cada cara
  (`XCAFDoc_ColorSurf`); OpenCascade pasa las unidades del archivo a milímetros. BREP no guarda unidades.
- Teselado con `BRepMesh_IncrementalMesh` y una calidad elegible: la desviación lineal es una fracción de la diagonal de
  la caja (baja 1/500, media 1/2000, alta 1/8000) y la angular, 0,5, 0,3 o 0,15 radianes. Cada cara con su ubicación y
  su orientación (una cara invertida gira sus triángulos).
- STEP a partir de una malla: un sólido facetado (cada triángulo una cara plana, cosidas): no recupera superficies
  paramétricas y se avisa; el cosido crece casi con el cuadrado, así que como mucho 50 000 triángulos.
- IGES a STEP sin teselar: la geometría exacta pasa de un formato a otro.
Todo se ejecuta en el proceso hijo de las mallas (D-249): OpenCascade es C++ que analiza archivos de usuario.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.errors import ErrorCode, ToolError
from tools.mesh.formats import Model, Part

QUALITY = {"baja": (1 / 500, 0.5), "media": (1 / 2000, 0.3), "alta": (1 / 8000, 0.15)}
MAX_STEP_TRIANGLES = 50_000
CAD_EXTS = ("step", "stp", "iges", "igs", "brep")


def _quiet() -> None:
    """Sin los mensajes de progreso de OpenCascade en la salida estándar."""
    try:
        from OCP.Message import Message
        from OCP.Message import Message_Gravity

        for printer in Message.DefaultMessenger_s().Printers():
            printer.SetTraceLevel(Message_Gravity.Message_Fail)
    except Exception:  # noqa: BLE001
        pass


def _document(path: Path, ext: str):
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    _quiet()
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    if ext in ("step", "stp"):
        from OCP.STEPCAFControl import STEPCAFControl_Reader

        reader = STEPCAFControl_Reader()
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Reader

        reader = IGESCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    status = reader.ReadFile(str(path))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone or not reader.Transfer(doc):
        raise ToolError(ErrorCode.CORRUPT_FILE, f"{ext.upper()} ilegible")
    return doc


def read_shapes(path: Path, ext: str, keep: list | None = None) -> list[tuple[str, object, tuple[int, int, int, int] | None, object]]:
    """[(nombre, forma, color, herramienta de colores)] de las formas libres del archivo. El documento XCAF se guarda en
    `keep`: si se libera, la herramienta de colores apunta a memoria liberada y OpenCascade se cae (D-251)."""
    if ext == "brep":
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Shape

        _quiet()
        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, str(path), BRep_Builder()) or shape.IsNull():
            raise ToolError(ErrorCode.CORRUPT_FILE, "BREP ilegible")
        return [(path.stem or "pieza", shape, None, None)]
    from OCP.collections import Sequence_TDF_Label
    from OCP.Quantity import Quantity_Color
    from OCP.TDataStd import TDataStd_Name
    from OCP.XCAFDoc import XCAFDoc_ColorTool, XCAFDoc_ColorType, XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    doc = _document(path, ext)
    if keep is not None:
        keep.append(doc)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    from OCP.TopLoc import TopLoc_Location

    def name_of(label) -> str:
        attr = TDataStd_Name()
        return attr.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attr) else ""

    def color_of(label):
        for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
            col = Quantity_Color()
            try:
                found = XCAFDoc_ColorTool.GetColor_s(label, kind, col)
            except Exception:  # noqa: BLE001 - Standard_NullObject
                found = False
            if found:
                return (round(col.Red() * 255), round(col.Green() * 255), round(col.Blue() * 255), 255)
        return None

    out: list = []

    def collect(label, location, name: str, color, depth: int) -> None:
        """Ensamblajes (D-256): cada componente es una referencia a una pieza con su ubicación; el nombre y el color se
        toman de la pieza referida y la instancia puede sobrescribirlos."""
        if depth > 32 or len(out) > 10_000:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "cad_assembly")
        if XCAFDoc_ShapeTool.IsReference_s(label):
            from OCP.TDF import TDF_Label

            referred = TDF_Label()
            if XCAFDoc_ShapeTool.GetReferredShape_s(label, referred):
                inner = location.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label))
                collect(referred, inner, name_of(referred) or name_of(label) or name, color_of(label) or color_of(referred) or color,
                        depth + 1)
            return
        if XCAFDoc_ShapeTool.IsAssembly_s(label):
            components = Sequence_TDF_Label()
            XCAFDoc_ShapeTool.GetComponents_s(label, components, False)
            for i in range(1, components.Length() + 1):
                collect(components.Value(i), location, name, color_of(label) or color, depth + 1)
            return
        shape = shapes.GetShape_s(label)
        if shape.IsNull():
            return
        own = name_of(label)
        out.append((own or name or f"pieza-{len(out) + 1}", shape.Moved(location) if not location.IsIdentity() else shape,
                    color_of(label) or color, colors))

    labels = Sequence_TDF_Label()
    shapes.GetFreeShapes(labels)
    for i in range(1, labels.Length() + 1):
        label = labels.Value(i)
        collect(label, TopLoc_Location(), name_of(label) or f"pieza-{i}", color_of(label), 0)
    if not out:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"El {ext.upper()} no tiene ninguna forma")
    return out


def _bbox_diagonal(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return 0.0
    lo, hi = box.CornerMin(), box.CornerMax()
    return float(np.linalg.norm([hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z()]))


def _shape_color(tool, shape):
    """El color de superficie de una forma, si el documento se lo da (una cara sin etiqueta propia lanza una excepción)."""
    from OCP.Quantity import Quantity_Color
    from OCP.XCAFDoc import XCAFDoc_ColorType

    if tool is None:
        return None
    col = Quantity_Color()
    try:
        found = tool.GetColor(shape, XCAFDoc_ColorType.XCAFDoc_ColorSurf, col)
    except Exception:  # noqa: BLE001 - Standard_NullObject
        return None
    return (round(col.Red() * 255), round(col.Green() * 255), round(col.Blue() * 255), 255) if found else None


def tessellate(shape, quality: str, base_color, color_tool, max_triangles: int, name: str) -> list[Part]:
    """Una pieza por sólido (o la forma entera si no tiene sólidos), con un color por cara si el archivo lo trae."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    relative, angular = QUALITY.get(quality, QUALITY["media"])
    diagonal = _bbox_diagonal(shape)
    if diagonal <= 0:
        return []
    BRepMesh_IncrementalMesh(shape, max(diagonal * relative, 1e-4), False, angular, True)
    solids = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
    while exp.More():
        solids.append(exp.Current())
        exp.Next()
    if not solids:
        solids = [shape]
    parts, total = [], 0
    for n, solid in enumerate(solids, start=1):
        solid_color = _shape_color(color_tool, solid) or base_color
        verts, faces, colors, offset = [], [], [], 0
        any_color = solid_color is not None
        face_exp = TopExp_Explorer(solid, TopAbs_ShapeEnum.TopAbs_FACE)
        while face_exp.More():
            face = TopoDS.Face(face_exp.Current())
            face_exp.Next()
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                continue
            nt, nn = tri.NbTriangles(), tri.NbNodes()
            total += nt
            if total > max_triangles:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "cad_triangles")
            trsf = loc.Transformation()
            pts = np.empty((nn, 3))
            for i in range(1, nn + 1):
                p = tri.Node(i).Transformed(trsf)
                pts[i - 1] = (p.X(), p.Y(), p.Z())
            idx = np.empty((nt, 3), dtype=np.int64)
            for i in range(1, nt + 1):
                idx[i - 1] = tri.Triangle(i).Get()
            idx -= 1
            if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
                idx = idx[:, ::-1]
            face_color = _shape_color(color_tool, face) or solid_color
            any_color = any_color or face_color is not None
            verts.append(pts)
            faces.append(idx + offset)
            colors.append(np.tile(np.array(face_color or (200, 200, 200, 255), dtype=np.uint8), (nt, 1)))
            offset += nn
        if faces:
            parts.append(Part(name if len(solids) == 1 else f"{name}-{n}", np.vstack(verts), np.vstack(faces),
                              np.vstack(colors) if any_color else None))
    return parts


def read_cad(path: Path, ext: str, quality: str, max_triangles: int) -> Model:
    parts: list[Part] = []
    keep: list = []
    for name, shape, color, tool in read_shapes(path, ext, keep):
        parts += tessellate(shape, quality, color, tool, max_triangles - sum(len(p.faces) for p in parts), name)
    if not parts:
        raise ToolError(ErrorCode.CORRUPT_FILE, f"El {ext.upper()} no tiene caras que teselar")
    return Model(parts, unit_mm=None if ext == "brep" else 1.0, up="z")


def _writer(shape, dst: Path) -> None:
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_StepModelType, STEPControl_Writer

    _quiet()
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_StepModelType.STEPControl_AsIs) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ToolError(ErrorCode.ENGINE_FAILED, "No se pudo crear el STEP")
    if writer.Write(str(dst)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ToolError(ErrorCode.ENGINE_FAILED, "No se pudo escribir el STEP")


def cad_to_step(src: Path, ext: str, dst: Path) -> int:
    """IGES (o BREP) a STEP sin teselar; devuelve cuántas formas."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    keep: list = []
    shapes = read_shapes(src, ext, keep)
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for _name, shape, _color, _tool in shapes:
        builder.Add(compound, shape)
    _writer(compound if len(shapes) > 1 else shapes[0][1], dst)
    return len(shapes)


def mesh_to_step(model: Model, dst: Path) -> None:
    """Un sólido facetado por pieza (triángulos planos cosidos); si una pieza no cierra, queda como superficie."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS, TopoDS_Compound

    total = sum(len(p.faces) for p in model.parts)
    if total > MAX_STEP_TRIANGLES:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "step_triangles")
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for part in model.parts:
        sewing = BRepBuilderAPI_Sewing(1e-6)
        points = [gp_Pnt(*map(float, v)) for v in part.vertices]
        for a, b, c in part.faces.tolist():
            if a == b or b == c or a == c:
                continue
            poly = BRepBuilderAPI_MakePolygon(points[a], points[b], points[c], True)
            if not poly.IsDone():
                continue
            face = BRepBuilderAPI_MakeFace(poly.Wire(), True)
            if face.IsDone():
                sewing.Add(face.Face())
        sewing.Perform()
        sewed = sewing.SewedShape()
        if sewed.IsNull():
            continue
        if sewed.ShapeType() == TopAbs_ShapeEnum.TopAbs_SHELL:
            solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(sewed))
            builder.Add(compound, solid.Solid() if solid.IsDone() else sewed)
        else:
            builder.Add(compound, sewed)
    _writer(compound, dst)
