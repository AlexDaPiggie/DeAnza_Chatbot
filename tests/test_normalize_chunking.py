from core.chunking import chunk_course
from core.course_codes import resolve_code
import pytest

def test_resolve_code_user_inputs():
    assert resolve_code("what is cis22a")=="CIS 22A"
    assert resolve_code("repreq for math-1a") == "MATH 1A"
    assert resolve_code("take PhYs4a next quarter") == "PHYS 4A"
    assert resolve_code("is chem 1a hard?") == "CHEM 1A"
    assert resolve_code("how much is tuition") is None

def test_chunk_course_keys():
    raw_elumen_course = {
        "Course ID (CB01A and CB01B)": "CIS D022A",
        "Course Title (CB02)": "Beginning Programming Methodologies in C++",
        "Minimum Credits Units": "4.5",
        "Advisory(ies)": "MATH 114 or equivalent",
        "Couse Description": "Introductory course in C++ programming",
        "FSA": "Computer Information Systems",
    }
    chunk = chunk_course(raw_elumen_course)
    assert "CIS 22A" in chunk.metadata.code
    assert chunk.metadata.title == "Beginning Programming Methodologies in C++"
