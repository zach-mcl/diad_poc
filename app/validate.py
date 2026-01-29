from __future__ import annotations
import re


DISALLOWED = [
    r"\binsert\b", r"\bupdate\b", r"\bdelete\b", r"\bdrop\b", r"\bcreate\b", r"\balter\b",
    r"\battach\b", r"\bcopy\b", r"\bpragma\b", r"\bcall\b", r"\bload\b", r"\binstall\b",
]


def strip_code_fences(text: str) -> str:
    t = text.strip()

    # ```sql ... ```
    m = re.search(r"```sql\s*(.*?)\s*```", t, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()

    # generic ``` ... ```
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
        t = t.strip()

    # remove <think>...</think> blocks if any model emits them
    t = re.sub(r"(?is)<think>.*?</think>", "", t).strip()

    # if the model included extra text, keep from first SELECT/WITH onward
    m2 = re.search(r"(?is)\b(with|select)\b.*", t)
    if m2:
        return m2.group(0).strip()

    return t


def sanitize_sql(sql: str) -> str:
    s = sql.strip()

    # Normalize whitespace
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def is_select_only(sql: str) -> tuple[bool, str]:
    s = sql.strip()
    if not s:
        return False, "Empty SQL."

    # Count semicolons outside quotes
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

    return True, "OK"
