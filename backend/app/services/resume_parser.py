from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile
from xml.etree import ElementTree
from uuid import uuid4

from backend.app.schemas.domain import CandidateProfile


KNOWN_SKILLS = {
    "python",
    "sql",
    "javascript",
    "typescript",
    "react",
    "fastapi",
    "django",
    "node",
    "aws",
    "docker",
    "kubernetes",
    "airflow",
    "pandas",
    "machine learning",
    "llms",
    "rag",
    "langchain",
    "langgraph",
    "postgres",
    "git",
}


class ResumeParsingError(ValueError):
    pass


class UnsupportedResumeFormatError(ResumeParsingError):
    pass


def decode_resume(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def extract_resume_text(filename: str | None, content: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {"", ".txt", ".md"}:
        text = decode_resume(content)
    elif suffix == ".docx":
        text = _extract_docx_text(content)
    elif suffix == ".pdf":
        text = _extract_pdf_text(content)
    else:
        raise UnsupportedResumeFormatError(
            f"Unsupported resume format '{suffix or 'unknown'}'. Use txt, md, docx, or pdf."
        )

    cleaned = text.strip()
    if not cleaned:
        raise ResumeParsingError("The uploaded resume did not contain readable text.")
    return cleaned


def infer_skills(resume_text: str) -> list[str]:
    lowered = resume_text.lower()
    return sorted(skill for skill in KNOWN_SKILLS if skill in lowered)


def infer_achievements(resume_text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in resume_text.splitlines()]
    likely_bullets = [line for line in lines if len(line) > 25]
    quantified = [line for line in likely_bullets if any(char.isdigit() for char in line)]
    return quantified[:8] or likely_bullets[:8]


def build_profile(
    resume_text: str,
    target_roles: list[str],
    preferred_locations: list[str],
    name: str | None = None,
) -> CandidateProfile:
    return CandidateProfile(
        profile_id=str(uuid4()),
        name=name,
        resume_text=resume_text,
        target_roles=target_roles,
        preferred_locations=preferred_locations,
        skills=infer_skills(resume_text),
        achievements=infer_achievements(resume_text),
    )


def _extract_docx_text(content: bytes) -> str:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(BytesIO(content)) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as error:
            raise ResumeParsingError("The DOCX file is missing its main document content.") from error

    root = ElementTree.fromstring(document_xml)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        line = "".join(fragments).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise UnsupportedResumeFormatError(
            "PDF parsing requires the optional dependency 'pypdf'. Install project dependencies first."
        ) from error

    reader = PdfReader(BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text
