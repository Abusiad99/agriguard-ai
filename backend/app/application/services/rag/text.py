"""
Text utilities for the retrieval pipeline: extraction from source files, cleaning,
sentence-aware chunking with overlap, and a bilingual (English/Arabic) tokenizer.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
class _HTMLText(HTMLParser):
    _SKIP = {"script", "style", "nav", "footer", "header", "noscript", "form", "aside"}
    _BLOCK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in ("h1", "h2", "h3", "h4") and not self._skip_depth:
            self.parts.append("\n\n# ")
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        parser = _HTMLText()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return html.unescape("".join(parser.parts))
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # optional dependency
            raise RuntimeError("PDF ingestion requires the optional 'pypdf' package.") from exc
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    raise ValueError(f"Unsupported source file type: {suffix}")


_CONTROL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]")


def clean_text(text: str) -> str:
    """Normalize Unicode, drop control/bidi-override characters (which can hide text
    from reviewers), and collapse whitespace while keeping paragraph breaks."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    index: int
    text: str
    section: Optional[str]


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟。])\s+|\n{2,}")


def chunk_text(text: str, target_chars: int = 900, overlap_chars: int = 150) -> List[Chunk]:
    """Split on paragraph/sentence boundaries into ~target_chars chunks, carrying the
    last ~overlap_chars of the previous chunk forward so a fact that straddles a
    boundary is retrievable from either side. Markdown-style '# ' headings become the
    `section` metadata of the chunks that follow them. No text is ever dropped: any
    content not yet emitted is flushed before a heading and at the end."""
    chunks: List[Chunk] = []
    section: Optional[str] = None
    buf: List[str] = []
    buf_len = 0
    fresh = False  # buffer holds text that has not been emitted in any chunk yet

    def flush(carry_overlap: bool = True):
        nonlocal buf, buf_len, fresh
        body = " ".join(buf).strip()
        if body and fresh:
            chunks.append(Chunk(index=len(chunks), text=body, section=section))
        buf, buf_len, fresh = [], 0, False
        if carry_overlap and body and overlap_chars:
            tail = body[-overlap_chars:]
            if " " in tail:
                tail = tail[tail.index(" ") + 1:]
            if tail:
                buf, buf_len = [tail], len(tail)

    def add(piece: str):
        nonlocal buf_len, fresh
        buf.append(piece)
        buf_len += len(piece) + 1
        fresh = True

    for block in text.split("\n"):
        line = block.strip()
        if not line:
            continue
        if line.startswith("#"):
            flush(carry_overlap=False)  # overlap never crosses a section boundary
            section = line.lstrip("#").strip()[:300] or section
            continue
        for sentence in _SENTENCE_SPLIT.split(line):
            sentence = sentence.strip()
            while len(sentence) > target_chars * 1.5:  # very long run-on text
                head, sentence = sentence[:target_chars], sentence[target_chars:]
                add(head)
                flush()
            if not sentence:
                continue
            if fresh and buf_len + len(sentence) > target_chars:
                flush()
            add(sentence)
    flush(carry_overlap=False)
    return chunks


# ---------------------------------------------------------------------------
# Tokenization (English + Arabic)
# ---------------------------------------------------------------------------
_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

_STOP_EN = set("""a an the and or of to in on for with by from at as is are was were be been being this that these
those it its into than then there their they them can could should would may might will do does did not no
yes if but so such what which who whom how when where why about over under more most less very also any all
each other some your you we our us i my me he she his her""".split())
_STOP_AR = {"في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "هو", "هي",
            "ما", "ماذا", "كيف", "هل", "لا", "او", "أو", "ثم", "كان", "يكون", "لم", "لن", "قد", "كل", "بعض",
            "عند", "بين", "اذا", "إذا", "انا", "نحن", "انت", "به", "بها", "له", "لها"}


def normalize_arabic(text: str) -> str:
    text = _AR_DIACRITICS.sub("", text)
    return (text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي"))


def tokenize(text: str) -> List[str]:
    text = normalize_arabic(text.lower())
    tokens = []
    for tok in _TOKEN.findall(text):
        if tok in _STOP_EN or tok in _STOP_AR or len(tok) < 2:
            continue
        if tok.startswith("ال") and len(tok) > 4:  # Arabic definite article
            tok = tok[2:]
        elif tok.isascii() and len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]  # light English plural stemming
        tokens.append(tok)
    return tokens


def contains_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


# Arabic agricultural terms -> English search terms, used to expand Arabic questions so
# they can match English-language sources lexically.
AR_EN_TERMS = {
    "طماطم": "tomato", "بندوره": "tomato", "بطاطس": "potato", "بطاطا": "potato", "ذره": "corn", "قمح": "wheat",
    "ارز": "rice", "خيار": "cucumber", "فلفل": "pepper", "خس": "lettuce", "عنب": "grape", "تفاح": "apple",
    "حمضيات": "citrus", "برتقال": "orange citrus", "ليمون": "lemon citrus", "موز": "banana", "ريحان": "basil",
    "فاصوليا": "bean", "فول": "bean", "صويا": "soybean", "فراوله": "strawberry", "بروكلي": "broccoli",
    "ملفوف": "cabbage", "كرنب": "cabbage", "قرنبيط": "cauliflower", "زهره": "cauliflower", "جزر": "carrot",
    "كرفس": "celery", "كرز": "cherry", "قهوه": "coffee", "بن": "coffee", "باذنجان": "eggplant", "ثوم": "garlic",
    "زنجبيل": "ginger", "خوخ": "peach", "دراق": "peach", "برقوق": "plum", "قرع": "squash", "كوسه": "zucchini",
    "تبغ": "tobacco", "نخيل": "palm", "نخله": "palm", "زيتون": "olive", "توت": "berry",
    "لفحه": "blight", "مبكره": "early", "متاخره": "late", "بياض": "mildew", "دقيقي": "powdery",
    "زغبي": "downy", "صدا": "rust", "تبقع": "spot", "بقع": "spot", "بقعه": "spot", "عفن": "rot mold",
    "فيروس": "virus", "تبرقش": "mosaic", "موزاييك": "mosaic", "ذبول": "wilt", "تجعد": "curl", "اصفرار": "yellowing",
    "بكتيري": "bacterial", "فطري": "fungal", "فطر": "fungus", "علاج": "treatment management", "وقايه": "prevention",
    "اعراض": "symptoms", "مبيد": "fungicide pesticide", "سماد": "fertilizer nutrient", "نقص": "deficiency",
    "حشرات": "insects pests", "افه": "pest", "ري": "irrigation water", "جفاف": "drought", "ورقه": "leaf",
    "اوراق": "leaves", "ثمار": "fruit", "ساق": "stem", "جذور": "root",
}


def expand_arabic_query(text: str) -> str:
    extra = []
    for tok in _TOKEN.findall(normalize_arabic(text.lower())):
        base = tok[2:] if tok.startswith("ال") and len(tok) > 4 else tok
        if base in AR_EN_TERMS:
            extra.append(AR_EN_TERMS[base])
    return " ".join(extra)
