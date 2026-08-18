import re
from typing import List
from core.schemas import Chunk, ChunkMetaData

FIELD_ALIASES = {
    "code": ["code", "course_code", "course id", "course id (cb01a and cb01b)"],
    "title": ["title", "course title", "course title (cb02)", "name"],
    "units": ["units", "minimum credit units", "credit units"],
    "desc": ["description", "course description", "catalog description"],
    "prereqs": ["prerequisites", "prerequisite(s)", "advisory(ies)", "entrance skills", "prereq_text"],
    "dept": ["department", "fsa", "faculty requirements"],
}

def _extract_field(data: dict, field_name: str, used_keys: set) -> str:
    """Finds first matching alias in dictionary and marks key as used."""
    aliases = FIELD_ALIASES.get(field_name, [])
    for k, v in data.items():
        if k.strip().lower() in aliases and v is not None and str(v).strip():
            used_keys.add(k)
            return str(v).strip()
    return ""

def chunk_course(c: dict) -> Chunk:
    """
    Takes raw course dictionary from scrapers or catalog JSON, maps aliases,
    normalizes course codes, captures extra metadata, and returns a typed Chunk.
    """
    used_keys = set()

    # 1/ Extract primary fields using alias mapping
    code = _extract_field(c, "code", used_keys)
    # Normalize eLumen codes like "CIS D022A" -> "CIS 22A"
    code = re.sub(r'([A-Za-z]+)\s*D0*(\d+[A-Za-z]*)', r'\1 \2', code)

    title = _extract_field(c, "title", used_keys)
    units_raw = _extract_field(c, "units", used_keys)
    desc = _extract_field(c, "desc", used_keys)
    prereqs = _extract_field(c, "prereqs", used_keys) or "None"
    dept = _extract_field(c, "dept", used_keys)
    import urllib.parse
    clean_code = code.strip()
    encoded_code = urllib.parse.quote(clean_code)
    url = c.get("url") or f"https://deanza.elumenapp.com/catalog/course/{encoded_code}"

    # 2/ Catch-All: Collect all remaining unmapped attributes (Transferability, Hours, etc.)
    extra_details = {}
    extra_lines = []
    ignored = {"na", "course family", "full_text", "html"}
    for k, v in c.items():
        if k not in used_keys and k.strip().lower() not in ignored and v:
            clean_val = str(v).strip()
            if clean_val:
                extra_details[k] = clean_val
                extra_lines.append(f"{k}: {clean_val}")

    extra_details["department"] = dept

    # 3/ Build structured text for dense & sparse search
    text_parts = [
        f"Course Code: {code}",
        f"Title: {title}",
        f"Department: {dept}",
        f"Units: {units_raw}",
        f"Prerequisites: {prereqs}",
        f"Description: {desc}",
    ]
    if extra_lines:
        text_parts.append("Additional Details:\n" + "\n".join(extra_lines))

    chunk_text = "\n".join(text_parts)

    # 4/ Parse numeric units if valid
    unit_num = None
    units_digits = re.findall(r"\d+\.?\d*", units_raw)
    if units_digits:
        try:
            unit_num = float(units_digits[0])
        except ValueError:
            pass

    meta = ChunkMetaData(
        source_type="course",
        code=code,
        title=title,
        units=unit_num,
        prereqs=prereqs,
        extra=extra_details
    )

    return Chunk(
        source_type="course",
        source_url=url,
        doc_id=code.lower().replace(" ", "-"),
        title=f"{code} - {title}",
        chunk_text=chunk_text,
        metadata=meta
    )

def chunk_page(
    p: dict,
    max_chars: int = 1500,
    overlap_chars: int = 200,
):
    """The purpose of this function is to splits long text pages (policies, rules,..) into smaller, searchable pieces (~1500 characters each)"""
    url = p.get("url") or ""
    title = p.get("title") or "De Anza Policy"
    content = p.get("content") or p.get("text") or ""

    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    paragraphs = content.split("\n\n")

    chunks: List[Chunk] = []
    current_text = ""
    chunk_idx = 0

    for para in paragraphs:
        while len(para) > max_chars:
            slice_text = para[:max_chars]
            para = para[max_chars - overlap_chars:]
            chunks.append(Chunk(
                source_type="page",
                source_url=url,
                doc_id=f"{url}#part-{chunk_idx}",
                title=f"{title} (Part {chunk_idx + 1})",
                chunk_text=slice_text,
                metadata=ChunkMetaData(source_type="page", title=title)
            ))
            chunk_idx += 1
        
        if len(current_text) + len(para) <= max_chars:
            current_text += ("\n\n" if current_text else "") + para

        else: 
            if current_text:
                chunks.append(Chunk(
                    source_type="page",
                    source_url=url,
                    doc_id=f"{url}#part-{chunk_idx}",
                    title=f"{title} (Part {chunk_idx + 1})",
                    chunk_text=current_text,
                    metadata=ChunkMetaData(
                        source_type="page",
                        title=title
                    )
                ))
                chunk_idx += 1
                current_text = current_text[-overlap_chars:] + "\n\n" + para
            else:
                current_text = para

    if current_text.strip():
        chunks.append(Chunk(
            source_type="page",
            source_url=url,
            doc_id=f"{url}#part-{chunk_idx}",
            title=f"{title} (Part {chunk_idx + 1})" if chunk_idx > 0 else title,
            chunk_text=current_text.strip(),
            metadata=ChunkMetaData(
                source_type="page",
                title=title,
            )
        ))

    return chunks

def chunk_section(s: dict) -> Chunk:
    """Format class schedule section into a typed Chunk."""
    crn = str(s.get("crn") or "").strip()
    course = str(s.get("course") or "").strip()
    # Normalize course code (e.g. "CIS D022A" -> "CIS 22A")
    course_norm = re.sub(r'([A-Za-z]+)\s*D0*(\d+[A-Za-z]*)', r'\1 \2', course)
    sec = str(s.get("sec") or s.get("section") or "").strip()
    title = str(s.get("title") or "").strip()
    days = str(s.get("days") or "").strip()
    times = str(s.get("times") or "").strip()
    instructor = str(s.get("instructor") or "").strip()
    loc = str(s.get("loc") or s.get("location") or "").strip()
    seats = str(s.get("seats") or "").strip()
    url = s.get("source_url") or "https://mobile.deanza.edu/schedule"

    text = (
        f"Schedule Section: {course_norm} - {title}\n"
        f"CRN: {crn}\n"
        f"Section: {sec}\n"
        f"Seats/Status: {seats}\n"
        f"Days: {days}\n"
        f"Times: {times}\n"
        f"Instructor: {instructor}\n"
        f"Location: {loc}"
    )

    meta = ChunkMetaData(
        source_type="section",
        code=course_norm,
        title=title,
        crn=crn,
        extra={
            "section": sec,
            "days": days,
            "times": times,
            "instructor": instructor,
            "location": loc
        }
    )

    doc_id = f"sec-{crn}" if crn else f"sec-{course_norm}-{sec}".lower().replace(" ", "-")

    return Chunk(
        source_type="section",
        source_url=url,
        doc_id=doc_id,
        title=f"{course_norm} (CRN {crn})",
        chunk_text=text,
        metadata=meta
    )