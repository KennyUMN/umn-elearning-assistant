"""Academic Styler — Formatter dokumen resmi berstandar akademik Universitas Multimedia Nusantara (UMN).

Standar Format Akademik UMN:
- Kertas: A4 (21.0 x 29.7 cm)
- Margin: Kiri 4.0 cm, Atas 4.0 cm, Kanan 3.0 cm, Bawah 3.0 cm (standar 4-4-3-3)
- Font Utama: Times New Roman 12 pt
- Spasi Baris: 1.5 spasi, Rata Kiri-Kanan (Justified)
- Indent Paragraf: 1.0 cm untuk paragraf bodi
- Heading:
  * BAB / Judul Bagian: Times New Roman 13-14 pt, Bold
  * Sub-bagian: Times New Roman 12 pt, Bold
- Kotak Kode Program: Font Consolas 9.5 pt, background abu-abu #F3F4F6, aksen border UMN Blue #004C97
- Cover Resmi UMN: Header institusi, judul tugas, nama matkul, identitas penyusun (Nama/NIM), Tangerang & Tahun.
- Header & Footer: Cover bersih (Different First Page), halaman 2+ memuat nomor halaman dan header ringkas.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor


# Warna Identitas UMN
COLOR_UMN_BLUE = RGBColor(0, 76, 151)       # #004C97
COLOR_DARK_GRAY = RGBColor(55, 65, 81)      # #374151
HEX_BG_CODE = "F3F4F6"
HEX_BORDER_LIGHT = "E5E7EB"
HEX_BORDER_UMN_BLUE = "004C97"


def setup_umn_document(doc: Document, header_text: str = "") -> Document:
    """Terapkan orientasi A4, margin 4-4-3-3 cm, dan header/footer halaman kedua dst."""
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(4.0)
    section.bottom_margin = Cm(3.0)
    section.left_margin = Cm(4.0)
    section.right_margin = Cm(3.0)

    # First page (Cover) tidak memiliki nomor halaman / header
    section.different_first_page_header_footer = True

    # Header halaman 2+
    if header_text:
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hr = hp.add_run(header_text)
        hr.font.name = "Times New Roman"
        hr.font.size = Pt(8.5)
        hr.font.italic = True
        hr.font.color.rgb = RGBColor(120, 120, 120)

    # Footer halaman 2+ (Nomor Halaman)
    footer = section.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = fp.add_run()
    fr.font.name = "Times New Roman"
    fr.font.size = Pt(10)
    fr.font.color.rgb = RGBColor(100, 100, 100)
    fld = parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls('w'))
    fp._p.append(fld)

    return doc


def infer_umn_faculty_dept(course_name: str) -> Tuple[str, str]:
    """Deteksi Fakultas dan Program Studi berdasarkan kode mata kuliah UMN."""
    upper = course_name.upper()
    if any(k in upper for k in ["IF", "INFORMATIKA", "CYBER", "CS", "DATA"]):
        return "FAKULTAS TEKNIK DAN INFORMATIKA", "PROGRAM STUDI INFORMATIKA"
    elif any(k in upper for k in ["SI", "SISTEM INFORMASI", "IS"]):
        return "FAKULTAS TEKNIK DAN INFORMATIKA", "PROGRAM STUDI SISTEM INFORMASI"
    elif any(k in upper for k in ["TE", "ELEKTRO", "FT"]):
        return "FAKULTAS TEKNIK DAN INFORMATIKA", "PROGRAM STUDI TEKNIK ELEKTRO"
    elif any(k in upper for k in ["DKV", "DESAIN", "ANIMASI", "FILM"]):
        return "FAKULTAS SENI DAN DESAIN", "PROGRAM STUDI DESAIN KOMUNIKASI VISUAL"
    elif any(k in upper for k in ["MN", "MANAJEMEN", "AK", "AKUNTANSI"]):
        return "FAKULTAS BISNIS", "PROGRAM STUDI MANAJEMEN"
    elif any(k in upper for k in ["ILKOM", "KOMUNIKASI", "JURNALISME", "PR"]):
        return "FAKULTAS ILMU KOMUNIKASI", "PROGRAM STUDI ILMU KOMUNIKASI"
    return "FAKULTAS TEKNIK DAN INFORMATIKA", "PROGRAM STUDI INFORMATIKA"


def add_umn_cover_page(
    doc: Document,
    title: str,
    course_name: str,
    student_name: str,
    student_nim: str,
    doc_type: str = "TUGAS KULIAH"
) -> None:
    """Buat halaman cover formal sesuai pedoman akademik Universitas Multimedia Nusantara."""
    faculty, dept = infer_umn_faculty_dept(course_name)

    # 1. Header Institusi
    p_inst = doc.add_paragraph()
    p_inst.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_inst.paragraph_format.space_before = Pt(0)
    p_inst.paragraph_format.space_after = Pt(48)

    r_inst1 = p_inst.add_run("UNIVERSITAS MULTIMEDIA NUSANTARA\n")
    r_inst1.bold = True
    r_inst1.font.name = "Times New Roman"
    r_inst1.font.size = Pt(13)
    r_inst1.font.color.rgb = COLOR_UMN_BLUE

    r_inst2 = p_inst.add_run(f"{faculty}\n{dept}")
    r_inst2.bold = True
    r_inst2.font.name = "Times New Roman"
    r_inst2.font.size = Pt(11)
    r_inst2.font.color.rgb = COLOR_DARK_GRAY

    # 2. Judul Tugas (Huruf Kapital, Bold, Ukuran Proporsional)
    clean_title = re.sub(r"^(tugas|assignment|laporan|paper)[:\s-]+", "", title, flags=re.IGNORECASE).strip()
    full_title = f"{doc_type.upper()}\n{clean_title.upper()}"

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(36)
    p_title.paragraph_format.space_after = Pt(18)

    r_title = p_title.add_run(full_title)
    r_title.bold = True
    r_title.font.name = "Times New Roman"
    r_title.font.size = Pt(14)
    r_title.font.color.rgb = RGBColor(0, 0, 0)

    # 3. Keterangan Mata Kuliah
    p_course = doc.add_paragraph()
    p_course.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_course.paragraph_format.space_after = Pt(96)

    r_course = p_course.add_run(f"Diajukan untuk Memenuhi Persyaratan Tugas Mata Kuliah\n{course_name}")
    r_course.font.name = "Times New Roman"
    r_course.font.size = Pt(11)
    r_course.font.italic = True
    r_course.font.color.rgb = COLOR_DARK_GRAY

    # 4. Identitas Penyusun
    p_author = doc.add_paragraph()
    p_author.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_author.paragraph_format.space_after = Pt(108)

    r_author1 = p_author.add_run("Disusun Oleh:\n\n")
    r_author1.font.name = "Times New Roman"
    r_author1.font.size = Pt(11)

    r_name = p_author.add_run(f"{student_name}\n")
    r_name.bold = True
    r_name.font.name = "Times New Roman"
    r_name.font.size = Pt(12)

    r_nim = p_author.add_run(f"NIM: {student_nim}")
    r_nim.bold = True
    r_nim.font.name = "Times New Roman"
    r_nim.font.size = Pt(12)

    # 5. Kota & Tahun
    current_year = datetime.now().year
    p_foot = doc.add_paragraph()
    p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_foot.paragraph_format.space_after = Pt(0)

    r_foot = p_foot.add_run(f"TANGERANG\n{current_year}")
    r_foot.bold = True
    r_foot.font.name = "Times New Roman"
    r_foot.font.size = Pt(12)

    # Pisahkan cover dari halaman isi
    doc.add_page_break()


def add_code_block(doc: Document, code_text: str) -> None:
    """Tambahkan blok kode program rapi dengan background abu-abu dan aksen garis biru UMN."""
    if not code_text.strip():
        return

    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    cell = table.cell(0, 0)
    tcPr = cell._tc.get_or_add_tcPr()

    # Background warna soft gray
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{HEX_BG_CODE}"/>')
    tcPr.append(shd)

    # Border kiri tebal UMN Blue, sisi lain tipis abu-abu
    borders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER_LIGHT}"/>
            <w:left w:val="single" w:sz="24" w:space="0" w:color="{HEX_BORDER_UMN_BLUE}"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER_LIGHT}"/>
            <w:right w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER_LIGHT}"/>
        </w:tcBorders>
    ''')
    tcPr.append(borders)

    # Padding sel
    padding = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="140" w:type="dxa"/>
            <w:left w:w="180" w:type="dxa"/>
            <w:bottom w:w="140" w:type="dxa"/>
            <w:right w:w="180" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(padding)

    # Isi teks kode
    lines = code_text.splitlines()
    for idx, line in enumerate(lines):
        p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = Pt(13)
        run = p.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(30, 41, 59)

    # Spasi setelah tabel
    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(6)


def render_umn_academic_document(
    spec: Dict[str, Any],
    assignment: Dict[str, Any],
    student_name: str,
    student_nim: str,
    out_path: Path
) -> Path:
    """Render dokumen Word berstandar akademik UMN lengkap dari spesifikasi tugas."""
    doc = Document()

    title = spec.get("filename", assignment.get("title", "Tugas Kuliah")).replace(".docx", "")
    course_name = assignment.get("course_name", "")

    # 1. Setup layout halaman A4, margin 4-4-3-3 cm, header/footer
    header_title = course_name.split("-")[0].strip() if "-" in course_name else course_name[:30]
    setup_umn_document(doc, header_text=f"{header_title} — {title[:40]}")

    # 2. Halaman Cover Resmi UMN
    doc_type = "LAPORAN TUGAS"
    title_lower = title.lower()
    if "cobit" in title_lower or "audit" in title_lower:
        doc_type = "LAPORAN AUDIT TATA KELOLA TI"
    elif "praktikum" in title_lower or "lab" in title_lower:
        doc_type = "LAPORAN PRAKTIKUM"
    elif "research" in title_lower or "penelitian" in title_lower or "riset" in title_lower:
        doc_type = "LAPORAN RISET & PENELITIAN"

    add_umn_cover_page(
        doc=doc,
        title=title,
        course_name=course_name,
        student_name=student_name,
        student_nim=student_nim,
        doc_type=doc_type
    )

    # 3. Konten Dokumen
    sections = spec.get("sections", [])
    for sec_idx, section in enumerate(sections):
        heading = (section.get("heading") or "").strip()
        if heading:
            # Format Bab / Heading
            hp = doc.add_paragraph()
            hp.paragraph_format.space_before = Pt(14 if sec_idx > 0 else 0)
            hp.paragraph_format.space_after = Pt(6)
            hp.paragraph_format.keep_with_next = True

            hrun = hp.add_run(heading)
            hrun.bold = True
            hrun.font.name = "Times New Roman"

            if heading.upper().startswith("BAB ") or "PENDAHULUAN" in heading.upper() or "KESIMPULAN" in heading.upper():
                hrun.font.size = Pt(13)
                hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                hrun.font.size = Pt(12)
                hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # Paragraf Isi
        for para in section.get("paragraphs", []) or []:
            text = str(para).strip()
            if not text:
                continue
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.first_line_indent = Cm(1.0)  # Indent standar 1 cm

            run = p.add_run(text)
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor(0, 0, 0)

        # Bullet List
        for bullet in section.get("bullets", []) or []:
            b_text = str(bullet).strip()
            if not b_text:
                continue
            bp = doc.add_paragraph(style="List Bullet")
            bp.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            bp.paragraph_format.line_spacing = 1.25
            bp.paragraph_format.space_before = Pt(0)
            bp.paragraph_format.space_after = Pt(3)

            brun = bp.add_run(b_text)
            brun.font.name = "Times New Roman"
            brun.font.size = Pt(12)

        # Blok Kode Program
        code = (section.get("code") or "").strip()
        if code:
            add_code_block(doc, code)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
