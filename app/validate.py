from __future__ import annotations
import re


DISALLOWED = [
    r"\binsert\b", r"\bupdate\b", r"\bdelete\b", r"\bdrop\b", r"\bcreate\b", r"\balter\b",
    r"\battach\b", r"\bcopy\b", r"\bpragma\b", r"\bcall\b", r"\bload\b", r"\binstall\b",
]

DISALLOWED_SET_OPS = [
    r"\bexcept\b",
    r"\bintersect\b",
    r"\bunion\b",
]


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def strip_ansi_and_control_chars(text: str) -> str:
    t = ANSI_ESCAPE_RE.sub("", text)
    t = CONTROL_CHARS_RE.sub("", t)
    return t


def strip_code_fences(text: str) -> str:
    t = text.strip()
    t = strip_ansi_and_control_chars(t)

    m = re.search(r"```sql\s*(.*?)\s*```", t, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return strip_ansi_and_control_chars(m.group(1).strip())

    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
        t = t.strip()

    t = re.sub(r"(?is)<think>.*?</think>", "", t).strip()

    m2 = re.search(r"(?is)\b(with|select)\b.*", t)
    if m2:
        return strip_ansi_and_control_chars(m2.group(0).strip())

    return strip_ansi_and_control_chars(t)


def sanitize_sql(sql: str) -> str:
    s = strip_ansi_and_control_chars(sql).strip()
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\r\n?", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def is_select_only(sql: str) -> tuple[bool, str]:
    s = strip_ansi_and_control_chars(sql).strip()
    if not s:
        return False, "Empty SQL."

    semicolons = re.sub(r"'[^']*'|\"[^\"]*\"", "", s).count(";")
    if semicolons > 1:
        return False, "Multiple statements detected."

    s_no_trailing = re.sub(r";\s*$", "", s).strip()

    if not re.match(r"^(select|with)\b", s_no_trailing, flags=re.IGNORECASE):
        return False, "SQL must start with SELECT or WITH."

    lower = s_no_trailing.lower()

    for pat in DISALLOWED:
        if re.search(pat, lower):
            return False, f"Disallowed keyword detected: {pat}"

    for pat in DISALLOWED_SET_OPS:
        if re.search(pat, lower):
            return False, f"Set operator not allowed for generated SQL: {pat}"

    return True, "OK"