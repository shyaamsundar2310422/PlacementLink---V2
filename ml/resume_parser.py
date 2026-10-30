from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pdfplumber


def _extract_docx_text(docx_path):
    with zipfile.ZipFile(docx_path) as document:
        xml_content = document.read("word/document.xml")
    root = ET.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_resume_text(file_path):
    """Extract selectable text from PDF or DOCX resumes; scans and legacy DOC are unsupported."""
    extension = Path(file_path).suffix.lower()
    try:
        if extension == ".docx":
            return _extract_docx_text(file_path)
        if extension != ".pdf":
            return ""
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
        return "\n".join(pages)
    except Exception as error:
        print(f"[ResumeParser] extraction_failed category={type(error).__name__}")
        return ""
