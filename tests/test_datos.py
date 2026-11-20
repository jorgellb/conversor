"""F6-B (7.12, D-213 y D-214): hojas de cálculo y datos. 16.5: arreglar-codificacion-csv recupera tildes y eñes; 16.4: XXE."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401  (fixture)

CALC = shutil.which("soffice") and any(Path(p).exists() for p in ("/usr/lib/libreoffice/program/libsclo.so",
                                                                   "/opt/libreoffice/program/libsclo.so"))


def _file(tmp_path: Path, name: str, data: bytes | str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _out(result: list[dict], i: int = 0) -> Path:
    return Path(result[i]["path"])


def _xlsx(tmp_path: Path, name: str = "ventas.xlsx", cached: bool = True) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Enero"
    ws.append(["Cliente", "Importe", "Fecha", "Código", "Activo"])
    ws.append(["Peña, S.L.", 1234.5, dt.datetime(2026, 1, 15), "00123", True])
    ws.append(["Ñandú", 10, dt.datetime(2026, 1, 16, 9, 30), "04001", False])
    ws["B4"] = "=SUM(B2:B3)"
    wb.create_sheet("Febrero").append(["solo", "una fila"])
    wb.create_sheet("Vacía")
    path = tmp_path / name
    wb.save(path)
    if cached:
        # openpyxl no calcula: se simula lo que guarda Excel escribiendo el valor en la caché del XML.
        with zipfile.ZipFile(path) as zf:
            members = {n: zf.read(n) for n in zf.namelist()}
        sheet = members["xl/worksheets/sheet1.xml"].decode()
        assert "<f>SUM(B2:B3)</f><v></v>" in sheet
        members["xl/worksheets/sheet1.xml"] = sheet.replace("<f>SUM(B2:B3)</f><v></v>", "<f>SUM(B2:B3)</f><v>1244.5</v>").encode()
        with zipfile.ZipFile(path, "w") as zf:
            for n, data in members.items():
                zf.writestr(n, data)
    return path


# --- xlsx-a-csv ----------------------------------------------------------------------------------------------------


def test_xlsx_to_csv_active_sheet_values_and_formats(make_ctx, tmp_path):
    src = _xlsx(tmp_path)
    out = run("xlsx-a-csv", make_ctx("xlsx-a-csv", [src]))
    assert out[0]["name"] == "ventas.csv"
    rows = list(csv.reader(io.StringIO(_out(out).read_text(encoding="utf-8"))))
    assert rows[0] == ["Cliente", "Importe", "Fecha", "Código", "Activo"]
    assert rows[1] == ["Peña, S.L.", "1234.5", "2026-01-15", "00123", "TRUE"]
    assert rows[2] == ["Ñandú", "10", "2026-01-16 09:30:00", "04001", "FALSE"]
    assert rows[3][1] == "1244.5"
    european = run("xlsx-a-csv", make_ctx("xlsx-a-csv", [src], {"separador": "punto_y_coma", "decimal": "coma",
                                                                "codificacion": "windows-1252"}))
    text = _out(european).read_bytes().decode("cp1252")
    assert "Peña, S.L.;1234,5;2026-01-15;00123;TRUE" in text


def test_xlsx_to_csv_all_sheets_and_formulas_without_cache(make_ctx, tmp_path):
    out = run("xlsx-a-csv", make_ctx("xlsx-a-csv", [_xlsx(tmp_path, cached=False)], {"hojas": "todas", "codificacion": "utf-8-bom"}))
    assert [o["name"] for o in out] == ["ventas-csv.zip"]
    assert "1 fórmula(s) sin valor calculado" in out[0]["note"]
    with zipfile.ZipFile(_out(out)) as zf:
        assert sorted(zf.namelist()) == ["ventas-Enero.csv", "ventas-Febrero.csv", "ventas-Vacia.csv"]  # zip_files: nombres ASCII
        assert zf.read("ventas-Febrero.csv") == b"\xef\xbb\xbfsolo,una fila\r\n"
        assert zf.read("ventas-Vacia.csv") == b"\xef\xbb\xbf"


def test_corrupt_xlsx(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("xlsx-a-csv", make_ctx("xlsx-a-csv", [_file(tmp_path, "roto.xlsx", b"PK\x03\x04roto")]))
    assert err.value.code == "CORRUPT_FILE"


# --- csv-a-xlsx ----------------------------------------------------------------------------------------------------


def test_csv_to_xlsx_types_header_and_no_formula_injection(make_ctx, tmp_path):
    import openpyxl

    text = ("Nombre;Importe;Fecha;CP;Teléfono;Nota\r\n"
            "José Peña;1.234,56;2026-03-01;04001;+34600111222;=HYPERLINK(\"http://x\",\"pulsa\")\r\n"
            "Ana;12,5;2026-03-02 10:15;28080;600111222;@SUM(1)\r\n")
    src = _file(tmp_path, "clientes.csv", text.encode("cp1252"))
    out = run("csv-a-xlsx", make_ctx("csv-a-xlsx", [src]))
    assert out[0]["name"] == "clientes.xlsx" and "Windows-1252" in out[0]["note"] and "«;»" in out[0]["note"]
    wb = openpyxl.load_workbook(_out(out))
    ws = wb.active
    assert ws.title == "clientes" and ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:F3"
    assert ws["A1"].font.bold and ws["A2"].value == "José Peña"
    assert ws["B2"].value == 1234.56 and ws["B3"].value == 12.5
    assert ws["C2"].value == dt.datetime(2026, 3, 1) and ws["C3"].value == dt.datetime(2026, 3, 2, 10, 15)
    assert ws["D2"].value == "04001" and ws["E2"].value == "+34600111222" and ws["E3"].value == 600111222
    assert ws["F2"].data_type == "s" and ws["F2"].value.startswith("=HYPERLINK")
    with zipfile.ZipFile(_out(out)) as zf:
        assert b"<f>" not in zf.read("xl/worksheets/sheet1.xml")


def test_csv_to_xlsx_one_workbook_and_text_only(make_ctx, tmp_path):
    import openpyxl

    a = _file(tmp_path, "uno.csv", "a,b\n1,2\n")
    b = _file(tmp_path, "dos.csv", "x\tz\n3.5\t007\n")
    out = run("csv-a-xlsx", make_ctx("csv-a-xlsx", [a, b], {"libro": "uno"}))
    wb = openpyxl.load_workbook(_out(out))
    assert out[0]["name"] == "hojas.xlsx" and wb.sheetnames == ["uno", "dos"]
    assert wb["dos"]["A2"].value == 3.5 and wb["dos"]["B2"].value == "007"
    plain = run("csv-a-xlsx", make_ctx("csv-a-xlsx", [a], {"tipos": False, "encabezado": False}))
    ws = openpyxl.load_workbook(_out(plain)).active
    assert ws["A2"].value == "1" and ws.freeze_panes is None


def test_number_rules():
    from tools.utils.datos import to_number

    assert to_number("1.234,56", "coma") == 1234.56 and to_number("1,234.56", "punto") == 1234.56
    assert to_number("-7", "punto") == -7 and to_number("0,5", "coma") == 0.5 and to_number("1e3", "punto") is None
    for text in ("00123", "+34600", "1234567890123456", "12/03/2026", "", "nan", "inf", "1.2.3", "12,5"):
        assert to_number(text, "punto") is None, text


# --- excel-a-json ----------------------------------------------------------------------------------------------------


def test_excel_to_json_objects_and_rows(make_ctx, tmp_path):
    src = _xlsx(tmp_path)
    data = json.loads(_out(run("excel-a-json", make_ctx("excel-a-json", [src]))).read_text())
    assert data[0] == {"Cliente": "Peña, S.L.", "Importe": 1234.5, "Fecha": "2026-01-15", "Código": "00123", "Activo": True}
    assert data[1]["Importe"] == 10 and isinstance(data[1]["Importe"], int)
    every = json.loads(_out(run("excel-a-json", make_ctx("excel-a-json", [src], {"hojas": "todas", "forma": "filas"}))).read_text())
    assert list(every) == ["Enero", "Febrero", "Vacía"] and every["Febrero"] == [["solo", "una fila"]] and every["Vacía"] == []


def test_duplicate_and_empty_header_keys():
    from tools.utils.datos import keys_of

    assert keys_of(["id", None, "id", " "]) == ["id", "columna_2", "id_2", "columna_4"]


# --- arreglar-codificacion-csv (16.5) -------------------------------------------------------------------------------------


TEXTO = "Nombre;Ciudad;Nota\r\nMaría Núñez;A Coruña;Año €5 «muy bien»\r\nJosé Ibáñez;Cádiz;¿Qué tal? ¡Genial!\r\n"


@pytest.mark.parametrize("encoding", ["cp1252", "latin_1", "iso8859_15", "cp850", "mac_roman", "utf-16"])
def test_fix_encoding_recovers_accents(make_ctx, tmp_path, encoding):
    text = TEXTO if encoding not in ("latin_1", "cp850") else TEXTO.replace("€", "EUR")
    src = _file(tmp_path, "contactos.csv", text.encode(encoding))
    out = run("arreglar-codificacion-csv", make_ctx("arreglar-codificacion-csv", [src]))
    data = _out(out).read_bytes()
    assert out[0]["name"] == "contactos-utf8.csv" and data.startswith(b"\xef\xbb\xbf")
    assert data[3:].decode("utf-8") == text


def test_fix_encoding_repairs_mojibake_once_or_twice(make_ctx, tmp_path):
    once = TEXTO.encode("utf-8").decode("cp1252", errors="replace")
    twice = once.encode("utf-8").decode("cp1252", errors="replace")
    for broken in (once, twice):
        src = _file(tmp_path, "roto.csv", broken.encode("utf-8"))
        out = run("arreglar-codificacion-csv", make_ctx("arreglar-codificacion-csv", [src], {"salida": "utf-8"}))
        assert _out(out).read_bytes().decode("utf-8") == TEXTO
        assert "corregidas" in out[0]["note"]
    good = _file(tmp_path, "bien.csv", "São Paulo;Ãrea\n".encode("utf-8"))
    out = run("arreglar-codificacion-csv", make_ctx("arreglar-codificacion-csv", [good], {"salida": "utf-8"}))
    assert _out(out).read_text(encoding="utf-8") == "São Paulo;Ãrea\n"


def test_fix_encoding_forced_wrong_codec(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("arreglar-codificacion-csv", make_ctx("arreglar-codificacion-csv", [_file(tmp_path, "y.csv", b"\x81\x82\xff")],
                                                  {"origen": "utf-16"}))
    assert err.value.detail == "csv_wrong_encoding"


# --- csv-a-json y json-a-csv ----------------------------------------------------------------------------------------


def test_csv_to_json_and_back(make_ctx, tmp_path):
    src = _file(tmp_path, "datos.csv", "id,nombre,precio,activo,cp\n1,Peña,9.95,true,04001\n2,\"Uno, dos\",,false,28080\n")
    out = run("csv-a-json", make_ctx("csv-a-json", [src]))
    data = json.loads(_out(out).read_text())
    assert data == [{"id": 1, "nombre": "Peña", "precio": 9.95, "activo": True, "cp": "04001"},
                    {"id": 2, "nombre": "Uno, dos", "precio": None, "activo": False, "cp": 28080}]
    rows = json.loads(_out(run("csv-a-json", make_ctx("csv-a-json", [src], {"forma": "filas", "tipos": False}))).read_text())
    assert rows[0] == ["id", "nombre", "precio", "activo", "cp"] and rows[2][1] == "Uno, dos"
    back = _file(tmp_path, "datos.json", _out(out).read_bytes())
    text = _out(run("json-a-csv", make_ctx("json-a-csv", [back]))).read_bytes().decode()
    assert text == "id,nombre,precio,activo,cp\r\n1,Peña,9.95,true,04001\r\n2,\"Uno, dos\",,false,28080\r\n"


def test_json_to_csv_flattens_merges_keys_and_unwraps(make_ctx, tmp_path):
    src = _file(tmp_path, "api.json", json.dumps({"total": 2, "data": [
        {"id": 1, "user": {"name": "Ana", "geo": {"lat": 1.5}}, "tags": ["a", "b"]},
        {"id": 2, "extra": None, "user": {}}]}))
    out = run("json-a-csv", make_ctx("json-a-csv", [src], {"separador": "punto_y_coma"}))
    rows = list(csv.reader(io.StringIO(_out(out).read_text()), delimiter=";"))
    assert rows[0] == ["id", "user.name", "user.geo.lat", "tags", "extra", "user"]
    assert rows[1] == ["1", "Ana", "1.5", '["a", "b"]', "", ""] and rows[2][0] == "2"
    assert "«data»" in out[0]["note"]
    lines = _file(tmp_path, "eventos.json", '{"a": 1}\n{"a": 2, "b": "x"}\n')
    out = run("json-a-csv", make_ctx("json-a-csv", [lines]))
    assert _out(out).read_bytes() == b"a,b\r\n1,\r\n2,x\r\n" and "JSON Lines" in out[0]["note"]


@pytest.mark.parametrize("payload,code", [("{roto", "CORRUPT_FILE"), ("[" * 5000 + "]" * 5000, "LIMIT_EXCEEDED")])
def test_bad_json(make_ctx, tmp_path, payload, code):
    with pytest.raises(ToolError) as err:
        run("json-a-csv", make_ctx("json-a-csv", [_file(tmp_path, "malo.json", payload)]))
    assert err.value.code == code


# --- XML ------------------------------------------------------------------------------------------------------------


def test_json_to_xml_valid_names_and_lists(make_ctx, tmp_path):
    from defusedxml.ElementTree import fromstring

    src = _file(tmp_path, "pedido.json", json.dumps({"pedido": {"id": 7, "2fecha": "hoy", "líneas": [{"sku": "A"}, {"sku": "B"}],
                                                                  "nota & más": None, "ok": True}}, ensure_ascii=False))
    out = run("json-a-xml", make_ctx("json-a-xml", [src], {"raiz": "datos"}))
    root = fromstring(_out(out).read_bytes())
    assert root.tag == "datos" and root.find("pedido/id").text == "7" and root.find("pedido/_2fecha").get("clave") == "2fecha"
    assert [e.find("sku").text for e in root.findall("pedido/líneas")] == ["A", "B"]
    assert root.find("pedido/nota___más") is not None and root.find("pedido/ok").text == "true"
    top = run("json-a-xml", make_ctx("json-a-xml", [_file(tmp_path, "lista.json", "[1, 2]")]))
    assert [e.text for e in fromstring(_out(top).read_bytes()).findall("item")] == ["1", "2"]


def test_xml_to_json_attributes_text_lists_and_namespaces(make_ctx, tmp_path):
    xml = ('<?xml version="1.0"?><Invoice xmlns="urn:inv" xmlns:cbc="urn:cbc"><cbc:ID schemeID="x">F-1</cbc:ID>'
           '<Line n="1"><cbc:Qty>2</cbc:Qty></Line><Line n="2"><cbc:Qty>3.5</cbc:Qty></Line><Empty/><Note>a<b>c</b></Note></Invoice>')
    src = _file(tmp_path, "factura.xml", xml)
    data = json.loads(_out(run("xml-a-json", make_ctx("xml-a-json", [src]))).read_text())
    inv = data["Invoice"]
    assert inv["cbc:ID"] == {"@schemeID": "x", "#text": "F-1"}
    assert inv["Line"] == [{"@n": "1", "cbc:Qty": "2"}, {"@n": "2", "cbc:Qty": "3.5"}]
    assert inv["Empty"] is None and inv["Note"] == {"b": "c", "#text": "a"}
    typed = json.loads(_out(run("xml-a-json", make_ctx("xml-a-json", [src], {"tipos": True}))).read_text())
    assert typed["Invoice"]["Line"][1]["cbc:Qty"] == 3.5 and typed["Invoice"]["Line"][0]["@n"] == 1


@pytest.mark.parametrize("xml", [
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/hostname">]><r>&x;</r>',
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><r>&b;</r>',
    '<?xml version="1.0"?><!DOCTYPE r SYSTEM "http://127.0.0.1:9/x.dtd"><r/>',
])
def test_xml_xxe_and_entities_rejected(make_ctx, tmp_path, xml):
    """16.4: XXE y la expansión de entidades se rechazan; el DTD externo no se descarga."""
    src = _file(tmp_path, "xxe.xml", xml)
    try:
        out = run("xml-a-json", make_ctx("xml-a-json", [src]))
    except ToolError as err:
        assert err.detail == "xml_entities"
    else:
        assert json.loads(_out(out).read_text()) == {"r": None}  # el DTD externo sin entidades: ignorado, no leído


# --- YAML ------------------------------------------------------------------------------------------------------------


def test_yaml_to_json_and_back(make_ctx, tmp_path):
    src = _file(tmp_path, "config.yaml", "nombre: Peña\nfecha: 2026-11-20\npuertos: [80, 443]\n1: uno\nbase: &b {x: 1}\nderivado: *b\n")
    data = json.loads(_out(run("yaml-a-json", make_ctx("yaml-a-json", [src]))).read_text())
    assert data == {"nombre": "Peña", "fecha": "2026-11-20", "puertos": [80, 443], "1": "uno", "base": {"x": 1}, "derivado": {"x": 1}}
    multi = _file(tmp_path, "multi.yml", "a: 1\n---\nb: 2\n")
    out = run("yaml-a-json", make_ctx("yaml-a-json", [multi]))
    assert json.loads(_out(out).read_text()) == [{"a": 1}, {"b": 2}] and "2 documentos" in out[0]["note"]
    back = _file(tmp_path, "config.json", _out(run("yaml-a-json", make_ctx("yaml-a-json", [src]))).read_bytes())
    text = _out(run("json-a-yaml", make_ctx("json-a-yaml", [back]))).read_text()
    assert text.startswith("nombre: Peña\nfecha: '2026-11-20'\n") and "- 443" in text


def test_yaml_never_runs_python_tags(make_ctx, tmp_path):
    src = _file(tmp_path, "malo.yaml", "x: !!python/object/apply:os.system ['touch /tmp/pwned']\n")
    with pytest.raises(ToolError) as err:
        run("yaml-a-json", make_ctx("yaml-a-json", [src]))
    assert err.value.code == "CORRUPT_FILE"


@pytest.mark.parametrize("doc,detail", [
    ("a: &a [x,x,x,x,x,x,x,x,x,x]\n" + "".join(f"{c}: &{c} [{', '.join(['*' + p] * 10)}]\n"
                                               for p, c in zip("abcdefgh", "bcdefghi")), "data_too_big"),
    ("a: &a [*a]\n", "data_cycle"),
])
def test_yaml_alias_bombs(make_ctx, tmp_path, doc, detail):
    with pytest.raises(ToolError) as err:
        run("yaml-a-json", make_ctx("yaml-a-json", [_file(tmp_path, "bomba.yaml", doc)]))
    assert err.value.detail == detail


def test_batch_zip(make_ctx, tmp_path):
    files = [_file(tmp_path, "a.json", "[1]"), _file(tmp_path, "b.json", "[2]")]
    out = run("json-a-yaml", make_ctx("json-a-yaml", files))
    assert [o["name"] for o in out] == ["a.yaml", "b.yaml", "json-a-yaml.zip"]


# --- ODS con LibreOffice (en la CI) ------------------------------------------------------------------------------------


@pytest.mark.skipif(not CALC, reason="LibreOffice Calc no instalado (la CI lo instala)")
def test_xlsx_to_ods_and_back(make_ctx, tmp_path):
    import openpyxl

    out = run("xlsx-a-ods", make_ctx("xlsx-a-ods", [_xlsx(tmp_path)]))
    ods = tmp_path / out[0]["name"]
    shutil.copyfile(_out(out), ods)
    with zipfile.ZipFile(ods) as zf:
        assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.spreadsheet"
        assert "Peña, S.L." in zf.read("content.xml").decode()
    back = run("ods-a-xlsx", make_ctx("ods-a-xlsx", [ods]))
    wb = openpyxl.load_workbook(_out(back))
    assert wb.sheetnames[:2] == ["Enero", "Febrero"] and wb["Enero"]["A2"].value == "Peña, S.L."
    assert wb["Enero"]["B4"].value == "=SUM(B2:B3)"


# --- Revisión de F6-B (D-218) -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("doc", [
    # !!pairs y !!omap son listas de tuplas: también cuentan expandidas.
    "x: !!pairs\n" + "".join(f" - k{i}: &{c} [{', '.join(['*' + p] * 10) if p else ', '.join(['1'] * 10)}]\n"
                              for i, (p, c) in enumerate(zip(["", "a", "b", "c", "d", "e", "f", "g"], "abcdefgh"))),
    # Un texto largo repetido por alias pesa por su longitud.
    "a: &a '" + "x" * 20000 + "'\nb: &b [" + ", ".join(["*a"] * 100) + "]\nc: [" + ", ".join(["*b"] * 100) + "]\n",
    # Claves de fusión en cadena: crecen de forma cuadrática dentro de PyYAML.
    "a0: &a0 {k0: 1}\n" + "".join(f"a{i}: &a{i} {{<<: *a{i - 1}, k{i}: 1}}\n" for i in range(1, 1500)),
])
def test_yaml_bombs_that_evaded_the_count(make_ctx, tmp_path, doc):
    with pytest.raises(ToolError) as err:
        run("yaml-a-json", make_ctx("yaml-a-json", [_file(tmp_path, "bomba.yaml", doc)]))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_output_amplification_is_capped(make_ctx, tmp_path, monkeypatch):
    from tools.utils import datos

    monkeypatch.setattr(datos, "MAX_OUTPUT_BYTES", 200_000)
    header = ";".join(f"{'k' * 1000}{i}" for i in range(20))
    wide = _file(tmp_path, "ancho.csv", header + "\n" + "1;" * 19 + "1\n" * 1 + ("1;" * 19 + "1\n") * 50)
    with pytest.raises(ToolError) as err:
        run("csv-a-json", make_ctx("csv-a-json", [wide]))
    assert err.value.detail == "data_output_too_big"
    monkeypatch.setattr(datos, "MAX_CELLS", 10_000)
    sparse = _file(tmp_path, "claves.json", json.dumps([{f"c{i}": 1} for i in range(200)]))
    with pytest.raises(ToolError) as err:
        run("json-a-csv", make_ctx("json-a-csv", [sparse]))
    assert err.value.detail == "data_too_big"
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"], wb.active["XFD1"], wb.active["A2000"] = 1, 2, 3
    far = tmp_path / "lejos.xlsx"
    wb.save(far)
    with pytest.raises(ToolError) as err:
        run("xlsx-a-csv", make_ctx("xlsx-a-csv", [far]))
    assert err.value.detail == "data_too_big"


@pytest.mark.parametrize("text", ["« Un café\u00a0»", "CAFÉ\u00a0:", "AQUÍ»", "QUÉ»", "CAFÉ…", "Sí…»", "Ångström — Ærø"])
def test_mojibake_fixer_leaves_legitimate_text(text):
    from tools.utils.datos import fix_mojibake

    assert fix_mojibake(text) == (text, 0)


def test_cp1252_with_smart_quotes_is_not_mac_roman(make_ctx, tmp_path):
    text = "Ana;Atención: “perfecto” – sin problemas…\r\nLuis;Qué tal\r\n"
    out = run("arreglar-codificacion-csv", make_ctx("arreglar-codificacion-csv", [_file(tmp_path, "w.csv", text.encode("cp1252"))],
                                                    {"salida": "utf-8"}))
    assert _out(out).read_bytes().decode() == text and "Windows-1252" in out[0]["note"]


def test_three_decimals_with_semicolon_are_not_thousands(make_ctx, tmp_path):
    import openpyxl

    src = _file(tmp_path, "pesos.csv", "Producto;Peso kg;Precio\nA;1,500;2,250\nB;0,750;1,125\n")
    ws = openpyxl.load_workbook(_out(run("csv-a-xlsx", make_ctx("csv-a-xlsx", [src])))).active
    assert [ws["B2"].value, ws["C2"].value, ws["B3"].value] == [1.5, 2.25, 0.75]
    comma = _file(tmp_path, "ambiguo.csv", "a,b\n\"1,500\",x\n")
    data = json.loads(_out(run("csv-a-json", make_ctx("csv-a-json", [comma]))).read_text())
    assert data == [{"a": "1,500", "b": "x"}]


def test_control_characters_and_long_cells(make_ctx, tmp_path):
    import openpyxl

    src = _file(tmp_path, "erp.csv", "a;b\n1;x\x0by\n" + "2;" + "z" * 40_000 + "\n\x1a")
    out = run("csv-a-xlsx", make_ctx("csv-a-xlsx", [src]))
    ws = openpyxl.load_workbook(_out(out)).active
    assert ws["B2"].value == "xy" and len(ws["B3"].value) == 32_767
    assert "caracteres de control" in out[0]["note"] and "32 767" in out[0]["note"]


def test_json_to_xml_strips_invalid_characters(make_ctx, tmp_path):
    from defusedxml.ElementTree import fromstring

    src = _file(tmp_path, "c.json", json.dumps({"a": "x\u0001y", "b\u0002": 1, "2x": [1, 2]}))
    root = fromstring(_out(run("json-a-xml", make_ctx("json-a-xml", [src]))).read_bytes())
    assert root.find("a").text == "xy" and root.find("b") is not None
    assert [e.get("clave") for e in root.findall("_2x")] == ["2x", "2x"]
    lone = _file(tmp_path, "s.json", '{"a": "\\ud800"}')
    assert _out(run("json-a-csv", make_ctx("json-a-csv", [lone]))).read_bytes() == b"a\r\n?\r\n"


def test_xml_mixed_content_namespaces_and_marker_names(make_ctx, tmp_path):
    xml = ('<r xmlns:a="urn:1"><p>Hola <b>mundo</b> y adiós <i>x</i> fin</p><a:x/><q xmlns:a="urn:2"><a:y/></q>'
           '<t xml:lang="es" lang="x"/><__lists__>v</__lists__><e/><e/><n>1.0e999</n></r>')
    data = json.loads(_out(run("xml-a-json", make_ctx("xml-a-json", [_file(tmp_path, "m.xml", xml)], {"tipos": True}))).read_text())
    r = data["r"]
    assert r["p"] == {"b": "mundo", "i": "x", "#text": "Hola y adiós fin"}
    assert "a:x" in r and "a2:y" in r["q"] and r["t"] == {"@xml:lang": "es", "@lang": "x"}
    assert r["__lists__"] == "v" and r["e"] == [None, None] and r["n"] == "1.0e999"


def test_chart_sheet_and_csv_formula_guard(make_ctx, tmp_path):
    import openpyxl
    from openpyxl.chart import BarChart, Reference

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["nombre", "nota"])
    ws.append(['=HYPERLINK("http://x","pulsa")', -5])
    ws.append(["-texto", 3])
    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    cs = wb.create_chartsheet("Gráfico")
    cs.add_chart(chart)
    wb.active = 1
    path = tmp_path / "grafico.xlsx"
    wb.save(path)
    from openpyxl import load_workbook

    with zipfile.ZipFile(path) as zf:  # openpyxl guarda la fórmula como fórmula: se pasa a texto con su caché
        members = {n: zf.read(n) for n in zf.namelist()}
    sheet = members["xl/worksheets/sheet1.xml"].decode()
    members["xl/worksheets/sheet1.xml"] = sheet.replace('<c r="A2"><f>HYPERLINK("http://x","pulsa")</f><v></v></c>',
                                                        '<c r="A2" t="inlineStr"><is><t>=HYPERLINK("http://x","pulsa")</t></is></c>').encode()
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in members.items():
            zf.writestr(n, data)
    assert load_workbook(path).sheetnames == ["Sheet", "Gráfico"]
    out = run("xlsx-a-csv", make_ctx("xlsx-a-csv", [path]))
    rows = list(csv.reader(io.StringIO(_out(out).read_text())))
    assert rows == [["nombre", "nota"], ['\'=HYPERLINK("http://x","pulsa")', "-5"], ["'-texto", "3"]]
    data = json.loads(_out(run("excel-a-json", make_ctx("excel-a-json", [path], {"hojas": "todas"}))).read_text())
    assert list(data) == ["Sheet"]
    risky = _file(tmp_path, "r.json", json.dumps([{"=a": "@SUM(1)", "n": -2, "t": "-x"}]))
    assert _out(run("json-a-csv", make_ctx("json-a-csv", [risky]))).read_bytes() == b"'=a,n,t\r\n'@SUM(1),-2,'-x\r\n"


def test_yaml_keys_numbers_and_empty(make_ctx, tmp_path):
    data = json.loads(_out(run("yaml-a-json", make_ctx("yaml-a-json", [_file(tmp_path, "k.yaml", "true: a\n2: b\nnull: c\n1.5: d\n")]))).read_text())
    assert data == {"true": "a", "2": "b", "null": "c", "1.5": "d"}
    assert json.loads(_out(run("yaml-a-json", make_ctx("yaml-a-json", [_file(tmp_path, "v.yaml", "# nada\n")]))).read_text()) is None
    big = _file(tmp_path, "big.json", "[" + "9" * 5000 + "]")
    with pytest.raises(ToolError) as err:
        run("json-a-yaml", make_ctx("json-a-yaml", [big]))
    assert err.value.code == "CORRUPT_FILE"
    text = _out(run("json-a-yaml", make_ctx("json-a-yaml", [_file(tmp_path, "n.json", '{"a": "1e3", "b": "0x10", "c": "texto"}')]))).read_text()
    assert text == "a: '1e3'\nb: '0x10'\nc: texto\n"


def test_csv_rows_longer_than_header_and_flatten_collisions(make_ctx, tmp_path):
    data = json.loads(_out(run("csv-a-json", make_ctx("csv-a-json", [_file(tmp_path, "l.csv", "a,b\n1,2,3\n")]))).read_text())
    assert data == [{"a": 1, "b": 2, "columna_3": 3}]
    rows = _out(run("json-a-csv", make_ctx("json-a-csv", [_file(tmp_path, "f.json", '[{"a.b": 1, "a": {"b": 2}}]')]))).read_bytes()
    assert rows == b"a.b,a.b_2\r\n1,2\r\n"


def test_excel_unicode_text_is_accepted(make_ctx, tmp_path):
    from core.filetype import detect, matches

    path = _file(tmp_path, "export.txt", "Nombre\tAño\r\nPeña\t1990\r\n".encode("utf-16"))
    assert matches(detect(path, "txt"), "txt", ("csv", "txt"))
    data = json.loads(_out(run("csv-a-json", make_ctx("csv-a-json", [path]))).read_text())
    assert data == [{"Nombre": "Peña", "Año": 1990}]
