"""
Writing a real Excel workbook, with nothing installed.

An .xlsx file is a zip archive holding a handful of XML parts. Everything
needed to build one, zipfile and the XML itself, is in the Python that ships
with the machine, so this costs nothing and never breaks because a package
moved on.

Why a workbook and not a comma separated file. Money in Nepal is written
1,23,456.78, and a comma separated file cannot hold that: either the commas are
stripped and it stops reading like money, or they are kept and every amount
splits across three columns. In a workbook the number goes in as a number and
carries its own format, so it adds up in Excel, sorts properly, and still reads
the Nepali way on the screen.
"""

import datetime
import zipfile

# Cell formats. The first four are built into every spreadsheet program; the
# ones from 164 up are ours, and Excel numbers custom formats from there.
MONEY = "#,##,##0.00;[Red]-#,##,##0.00"
QUANTITY = "#,##,##0.###"
DATE = "yyyy-mm-dd"

STYLE_PLAIN = 0
STYLE_HEADING = 1
STYLE_MONEY = 2
STYLE_QUANTITY = 3
STYLE_DATE = 4
STYLE_TOTAL = 5
STYLE_TITLE = 6

_ESCAPES = ((u"&", u"&amp;"), (u"<", u"&lt;"), (u">", u"&gt;"),
            (u'"', u"&quot;"), (u"'", u"&apos;"))


def _text(value):
    out = u"" if value is None else unicode_str(value)
    for bad, good in _ESCAPES:
        out = out.replace(bad, good)
    # Control characters are not allowed in the XML a spreadsheet will open.
    return u"".join(ch for ch in out if ch >= u" " or ch in u"\t\n")


def unicode_str(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return u"%s" % (value,)


class Sheet(object):
    """One tab of the workbook."""

    def __init__(self, name, columns=None):
        # Excel refuses these characters in a tab name, and refuses one over 31
        # characters, so the name is made safe rather than the file rejected.
        safe = u"".join(u" " if ch in u"[]:*?/\\" else ch for ch in unicode_str(name))
        self.name = (safe.strip() or u"Sheet")[:31]
        self.rows = []
        self.columns = columns or []

    def add(self, cells):
        """Add a row. Each cell is a value, or a (value, style) pair."""
        self.rows.append([c if isinstance(c, tuple) else (c, None) for c in cells])
        return self

    def blank(self):
        return self.add([])


def _column_letter(index):
    letters = u""
    while index >= 0:
        letters = chr(ord("A") + index % 26) + letters
        index = index // 26 - 1
    return letters


def _guess_style(value, given):
    if given is not None:
        return given
    if isinstance(value, bool):
        return STYLE_PLAIN
    if isinstance(value, (int, float)):
        return STYLE_MONEY
    if isinstance(value, (datetime.date, datetime.datetime)):
        return STYLE_DATE
    return STYLE_PLAIN


def _cell_xml(reference, value, style):
    style = _guess_style(value, style)
    attributes = u' r="%s"' % reference
    if style:
        attributes += u' s="%d"' % style
    if value is None or value == u"":
        return u"<c%s/>" % attributes
    if isinstance(value, bool):
        return u"<c%s t=\"str\"><v>%s</v></c>" % (attributes, u"Yes" if value else u"No")
    if isinstance(value, (datetime.date, datetime.datetime)):
        # Spreadsheets count days from the last day of 1899, with the famous
        # phantom 29 February 1900 built in, so the offset is 25569 from 1970.
        day = value.date() if isinstance(value, datetime.datetime) else value
        serial = (day - datetime.date(1899, 12, 30)).days
        return u"<c%s><v>%d</v></c>" % (attributes, serial)
    if isinstance(value, (int, float)):
        return u"<c%s><v>%s</v></c>" % (attributes, repr(value) if isinstance(value, float)
                                        else u"%d" % value)
    return u"<c%s t=\"inlineStr\"><is><t xml:space=\"preserve\">%s</t></is></c>" % (
        attributes, _text(value))


def _sheet_xml(sheet):
    parts = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             u'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if sheet.columns:
        parts.append(u"<cols>")
        for index, width in enumerate(sheet.columns, start=1):
            parts.append(u'<col min="%d" max="%d" width="%s" customWidth="1"/>'
                         % (index, index, width))
        parts.append(u"</cols>")
    parts.append(u"<sheetData>")
    for row_number, row in enumerate(sheet.rows, start=1):
        if not row:
            continue
        parts.append(u'<row r="%d">' % row_number)
        for column, (value, style) in enumerate(row):
            parts.append(_cell_xml(u"%s%d" % (_column_letter(column), row_number),
                                   value, style))
        parts.append(u"</row>")
    parts.append(u"</sheetData></worksheet>")
    return u"".join(parts)


_CONTENT_TYPES = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
%s</Types>'''

_ROOT_RELS = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

_STYLES = u'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3">
<numFmt numFmtId="164" formatCode="%s"/>
<numFmt numFmtId="165" formatCode="%s"/>
<numFmt numFmtId="166" formatCode="%s"/>
</numFmts>
<fonts count="3">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="12"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEFEFEF"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top/><bottom style="thin"><color rgb="FF999999"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
</styleSheet>''' % (MONEY, QUANTITY, DATE)


def build(sheets):
    """Turn a list of Sheet objects into the bytes of an .xlsx file."""
    import io as _io
    sheets = [s for s in sheets if s is not None] or [Sheet(u"Sheet1")]

    overrides = u"".join(
        u'<Override PartName="/xl/worksheets/sheet%d.xml" '
        u'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        % (i + 1) for i in range(len(sheets)))

    workbook = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                u'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                u' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
                u"<sheets>"]
    relationships = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                     u'relationships">',
                     u'<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/'
                     u'officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    for index, sheet in enumerate(sheets, start=1):
        workbook.append(u'<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                        % (_text(sheet.name), index, index))
        relationships.append(
            u'<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/'
            u'2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (index, index))
    workbook.append(u"</sheets></workbook>")
    relationships.append(u"</Relationships>")

    buffer = _io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", (_CONTENT_TYPES % overrides).encode("utf-8"))
        archive.writestr("_rels/.rels", _ROOT_RELS.encode("utf-8"))
        archive.writestr("xl/workbook.xml", u"".join(workbook).encode("utf-8"))
        archive.writestr("xl/_rels/workbook.xml.rels", u"".join(relationships).encode("utf-8"))
        archive.writestr("xl/styles.xml", _STYLES.encode("utf-8"))
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr("xl/worksheets/sheet%d.xml" % index,
                             _sheet_xml(sheet).encode("utf-8"))
    return buffer.getvalue()
