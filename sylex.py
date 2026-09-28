#!/usr/bin/env python3
"""
SYLEX v3.0 — Deep Adaptive Syllabus Extraction Engine
Evidence-first, fully offline, any college format.

Task 1:  python sylex.py --pdf syllabus.pdf
Task 2:  python sylex.py --pdf syllabus.pdf --course CS23301
Hints:   python sylex.py --pdf syllabus.pdf --hints hints.json
Debug:   python sylex.py --pdf syllabus.pdf --debug
"""

import argparse, json, re, sys, os, hashlib, unicodedata, warnings, urllib, urllib.request
os.environ["PYMUPDF_SUGGEST_LAYOUT_ANALYZER"] = "0"
warnings.filterwarnings("ignore")

from pathlib  import Path
from typing   import Optional, List, Dict, Tuple, Any
from collections import defaultdict, Counter

# ── PDF libraries ──────────────────────────────────────────────────────
try:
    import pdfplumber; HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pymupdf as fitz
    fitz._recommend_layout = False
    HAS_FITZ = True
except ImportError:
    try:
        import fitz
        fitz._recommend_layout = False
        HAS_FITZ = True
    except ImportError:
        HAS_FITZ = False

if not HAS_PDFPLUMBER and not HAS_FITZ:
    print("ERROR: pip install pdfplumber PyMuPDF", file=sys.stderr)
    sys.exit(4)

# ══════════════════════════════════════════════════════════════════════
#  SIGNAL PATTERNS  (generic — zero college specifics)
# ══════════════════════════════════════════════════════════════════════

RE_CODE = re.compile(
    r'\b(?=[A-Z0-9\-]{3,15}\b)(?=[A-Z0-9\-]*[A-Z])(?=[A-Z0-9\-]*\d)[A-Z0-9]+(?:[\-][A-Z0-9]+)?\b'
)
RE_CODE_SPACED = re.compile(r'\b[A-Z]{2,5}\s+\d{2,4}[A-Z]?\b')
RE_CODE_DOT    = re.compile(r'\b\d{1,2}\.\d{2,4}[A-Z]?\b')  # MIT/Caltech style e.g. 6.0001, 18.06
RE_LABEL_CODE  = re.compile(
    r'(?i)\b(?:course|subject|paper|module)\s*(?:code|no\.?|number|id)?\s*[:\-]\s*'
    r'([A-Z0-9\.\-]{2,15})\b'
)
RE_LABEL_TITLE = re.compile(
    r'(?i)(?:course|subject|paper|module)\s+(?:title|name)\s*[:\-]\s*(.+)'
)

STOP_WORDS = {
    'ISBN', 'ISBN-10', 'ISBN-13', 'TOTAL', 'HOURS', 'SEMESTER', 'SECTION', 
    'CHAPTER', 'MODULE', 'UNIT', 'PREAMBLE', 'SYLLABUS', 'COURSE', 'OBJECTIVES',
    'OUTCOMES', 'REFERENCES', 'DEPARTMENT', 'REGULATION', 'TABLE', 'MARKS',
    'CONVERSION', 'INJECTING', 'DISCOURSE', 'SEGMENTATION', 'FABRIC', 'BASIC',
    'THEORY', 'PRACTICALS', 'CREDIT', 'CREDITS', 'CATEGORY', 'PREREQUISITE',
    'ELECTIVE', 'FOUNDATION', 'MANDATORY', 'CORE', 'CURRICULUM', 'APPENDIX',
    'ANNEXURE', 'PROGRAMME', 'PROGRAM', 'BACHELOR', 'MASTER', 'DOCTOR',
    'FACULTY', 'COLLEGE', 'UNIVERSITY', 'INSTITUTE', 'CAMPUS', 'INDEX',
    'EXAMINATION', 'EVALUATION', 'SESSION', 'PERIOD', 'ACADEMIC', 'YEAR',
    'MINIMUM', 'MAXIMUM', 'INTERNAL', 'EXTERNAL', 'CONTINUOUS', 'ASSESSMENT',
    'MITTAL', 'GHOSAL', 'NAGRATH', 'SAHA', 'HEATH', 'MERZOUKI', 'TANENBAUM',
    'PRESSMAN', 'SILBERSCHATZ', 'FOROUZAN', 'STALLINGS', 'KORTH', 'SUDARSHAN',
    'RITCHIE', 'KERNIGHAN', 'DEITEL', 'SCHILDT', 'SEDGEWICK', 'CORMEN',
    'EDITION', 'PUBLISHER', 'PUBLICATION', 'PUBLICATIONS', 'AUTHOR', 'AUTHORS',
    'VOLUME', 'VOL', 'PAGES', 'PAGE', 'PRESS', 'DESIGNER', 'DESIGNERS', 'PROFESSOR'
}

def is_valid_course_code(code: str) -> bool:
    c = code.upper().strip()
    if c in STOP_WORDS:
        return False
    if any(w in c.split() for w in STOP_WORDS):
        return False
    if c in {'POP3', 'IPV4', 'IPV6', 'HTML5', 'CSS3', 'MP3', 'MP4', 'SHA1', 'SHA2', 'WIN32', 'X86', 'UTF8', 'UTF16', 'HTTP', 'HTTPS'}:
        return False
    # Reject numbered list items (e.g. "2 MITTAL", "1 GHOSAL", "1. INTRODUCTION", "3 STEVE")
    if re.match(r'^\d+[\s\.\)\:\-]+[A-Za-z]+', c):
        return False
    # Exclude legal section numbers (e.g. 304B, 376A: 2-3 digits + 1 letter)
    if re.fullmatch(r'\d{2,3}[A-Z]', c):
        return False
    if re.match(r'^(?:UNIT|MODULE|CHAPTER|PART|SECTION|BLOCK|WEEK|CO|PO|PSO|PEO|PLO|ILO|CLO|LO|GA|BT|BL|K|ACT|RULE|ANNEXURE)[\-\s_]?\d+', c):
        return False
    # Exclude year ranges like 2021-22 or 2021/2022
    if re.fullmatch(r'\d{4}[-\/]\d{2,4}', c):
        return False
    # Reject pure numbers < 5 digits (e.g. page numbers 224, serial numbers 1, 2)
    if re.fullmatch(r'\d{1,4}', c) or re.fullmatch(r'\d{13,}', c):
        return False
    # Allow 5-10 digit university numeric subject codes (e.g. 34421002, 1910401)
    if re.fullmatch(r'\d{5,10}', c):
        return True
    # Support dot-notation (MIT style) e.g. 6.0001, 18.06
    if re.fullmatch(r'\d{1,2}\.\d{2,4}[A-Z]?', c):
        return True
    # If contains space, prefix must be 2-6 letters followed by digits (e.g. "CS 101")
    if ' ' in c:
        if not (re.fullmatch(r'[A-Z]{2,6}\s+[A-Z0-9\-]{1,8}', c) or re.fullmatch(r'[A-Z0-9\-]{1,8}\s+[A-Z]{2,6}', c)):
            return False
    has_alpha = bool(re.search(r'[A-Z]', c))
    has_digit = bool(re.search(r'\d', c))
    if not (has_alpha and has_digit):
        return False
    if not (3 <= len(c.replace(' ', '')) <= 15):
        return False
    return True

def norm_title(t: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(t or '').upper())

def codes_match(c1: str, c2: str) -> bool:
    if not c1 or not c2: return False
    n1 = normalize_id(c1)
    n2 = normalize_id(c2)
    if n1 == n2: return True
    # 0 <-> O equivalence for university open electives
    if n1.replace('O', '0') == n2.replace('O', '0'):
        return True
    return False

def clean_title(title_lines: List[str]) -> str:
    raw = ' '.join(title_lines)
    raw = re.sub(r'^\s*\(?\d+\)?[\.\)]\s*', '', raw)
    raw = re.sub(r'\s+\d\s+\d\s+\d\s+\d.*$', '', raw)
    raw = re.sub(r'(?i)\s+\d+(?:\.\d+)?\s*credits?\b.*$', '', raw)
    raw = re.sub(r'(?i)\s+(?:NIL|None|N\.?A\.?)\s*$', '', raw)
    raw = re.sub(r'\s+(?:CC|PC|PE|OE|FC-[A-Z0-9]+|EC-[A-Z0-9]+|OE-[A-Z0-9]+|HSMC|ESC|PCC|OEC|PROJ)\b.*$', '', raw)
    raw = re.sub(r'(?i)\s+(?:CSE|MECH|CIVIL|ECE|EEE|ENG|MATH|MANAG|CHEM|PHY|PHED|LAW|GEN|PE|INFOSYS|AERO|AUTO|BT|BME|E&I|M&E)\b.*$', '', raw)
    raw = re.sub(r'\s{2,}[A-Z]{2,6}\s*$', '', raw)
    raw = re.sub(r'\s*[\(\[]\s*\d+\s*[-/:\s]\s*\d+\s*[-/:\s]\s*\d+.*$', '', raw)
    raw = re.sub(r'\s+', ' ', raw)
    return raw.strip(' :-|.,;')
RE_UNIT = re.compile(
    r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))'
    r'(UNIT|MODULE|PART|CHAPTER|SECTION|WEEK|SESSION)\s*'
    r'[-–—:.\s]*\s*([IVXLCDM]+|\d+)\b'
)
RE_ROMAN_UNIT = re.compile(
    r'(?im)^[\s\u00a0\t]*([IVXLCDM]+)[\.\)]\s+([A-Z][A-Z0-9\s,\-–\(\)]+)'
)
RE_CO   = re.compile(r'\b(?:(CO|CLO|LO)\s*[-.]?\s*0*(\d{1,2})|C\d{3,4}\.(\d{1,2}))\b', re.I)
RE_PO   = re.compile(r'\b(PO|PLO|PEO|GA)\s*[-.]?\s*0*(\d{1,2})\b', re.I)
RE_PSO  = re.compile(r'\b(PSO|PSO-)\s*[-.]?\s*0*(\d{1,2})\b', re.I)
RE_LTPC = re.compile(r'(?i)\bL\s*[-/:\s]\s*T\s*[-/:\s]\s*P\b')
RE_LTPC_VALS = re.compile(r'(\d+)\s*[-/:\s]\s*(\d+)\s*[-/:\s]\s*(\d+)(?:\s*[-/:\s]\s*(\d+))?')
RE_CREDITS   = re.compile(r'(?i)credits?\s*[:\-]?\s*(\d+(?:\.\d+)?)')
RE_HOURS     = re.compile(r'(?i)\b(\d{1,3})\s*(?:hr?s?\.?|hours?|periods?)\b')
RE_YEAR      = re.compile(r'\b(19|20)\d{2}\b')
RE_EDITION   = re.compile(r'(\d+(?:st|nd|rd|th)?)\s+(?:ed(?:ition)?\.?)', re.I)
RE_BOOK_NUM  = re.compile(r'^\s*(?:(\d+|[ivxlc]+)[\.\)]?(\s+|$)|(?:Book|Ref|TB|RB)\s*\d+[\.\:\-]?\s*)', re.I)
RE_MATRIX_HDR= re.compile(r'(?i)\b(co\s*[-/]?\s*po|mapping|articulation|correlation)\b')

RE_TEXTBOOK  = re.compile(
    r'(?im)^\s*(text\s*books?(?:\s*\(s\))?|prescribed\s*(?:books?|texts?)|core\s*books?|required\s*(?:texts?|books?)|course\s*(?:texts?|books?)|text\s*books?\s*/\s*references?)\s*[:\-]?\s*$'
)
RE_REFBOOK   = re.compile(
    r'(?im)^\s*(reference\s*books?(?:\s*\(s\))?|references?|suggested\s*readings?|'
    r'additional\s*readings?|supplementary\s*(?:readings?|texts?)|recommended\s*(?:books?|texts?|readings?)|reading\s*list|bibliography|online\s*resources?)\s*[:\-]?\s*$'
)

# Bloom markers
RE_K_LEVEL  = re.compile(r'\(?K([1-6])\)?')
RE_BT_LEVEL = re.compile(r'\b(?:BT|BL|L)([1-6])\b')
BLOOM_WORDS = ["remember","understand","apply","analyse","analyze","evaluate","create"]

ROMAN_MAP = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}

def roman_to_int(s: str) -> Optional[int]:
    s = s.upper().strip()
    if re.fullmatch(r'\d+', s): return int(s)
    try:
        result, prev = 0, 0
        for ch in reversed(s):
            v = ROMAN_MAP.get(ch)
            if v is None: return None
            result = result + v if v >= prev else result - v
            prev = v
        return result if result > 0 else None
    except Exception: return None

def normalize_id(s: str) -> str:
    cleaned = re.sub(r'\s+', '', s).upper()
    m_nba = re.match(r'^C\d{3,4}\.(\d{1,2})$', cleaned)
    if m_nba:
        return f"CO{int(m_nba.group(1))}"
    return cleaned

# ── Bloom verb lexicon ─────────────────────────────────────────────────
BLOOM_VERBS: Dict[str, List[str]] = {
    "remember":   ["define","list","state","name","recall","identify","label","recognize",
                   "reproduce","enumerate","mention","write","record","repeat","memorize",
                   "arrange","match","select","choose","find","omit","show"],
    "understand": ["explain","describe","summarize","classify","interpret","discuss",
                   "illustrate","outline","paraphrase","relate","translate","distinguish",
                   "contrast","predict","express","review","tell","show","generalize",
                   "estimate","infer","locate","recognize","report","restate"],
    "apply":      ["apply","use","solve","implement","demonstrate","compute","calculate",
                   "construct","execute","practice","operate","perform","produce","complete",
                   "examine","modify","prepare","change","experiment","discover","employ",
                   "schedule","sketch","write","determine","develop"],
    "analyse":    ["analyse","analyze","differentiate","compare","contrast","examine",
                   "categorize","infer","relate","decompose","break","separate","discriminate",
                   "test","inspect","investigate","question","detect","diagram","distinguish",
                   "prioritize","point out","attribute","deduce","survey"],
    "evaluate":   ["evaluate","justify","critique","appraise","judge","assess","argue",
                   "defend","select","recommend","rank","prioritize","support","decide",
                   "estimate","measure","validate","rate","value","verify","conclude",
                   "interpret","predict","score","summarize"],
    "create":     ["design","create","develop","formulate","compose","plan","propose",
                   "devise","generate","build","invent","compile","produce","assemble",
                   "synthesize","construct","write","formulate","arrange","combine",
                   "set up","organize","manage","prepare","hypothesize"],
}

VERB_MAP: Dict[str, str] = {}
for _lvl, _verbs in BLOOM_VERBS.items():
    for _v in _verbs: VERB_MAP[_v] = _lvl

def infer_bloom(text: str) -> str:
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    # Check first few words (learning verb usually at start)
    for w in words[:8]:
        if w in VERB_MAP: return VERB_MAP[w]
    # Check all words
    for w in words:
        if w in VERB_MAP: return VERB_MAP[w]
    return "understand"

def detect_printed_bloom(text: str) -> Optional[Tuple[str, str]]:
    """Return (level, 'printed') if a Bloom level is explicitly stated."""
    # K1-K6
    m = RE_K_LEVEL.search(text)
    if m:
        k = {1:"remember",2:"understand",3:"apply",4:"analyse",5:"evaluate",6:"create"}
        lvl = k.get(int(m.group(1)))
        if lvl: return lvl, "printed"
    # BT/BL/L levels
    m = RE_BT_LEVEL.search(text)
    if m:
        k = {1:"remember",2:"understand",3:"apply",4:"analyse",5:"evaluate",6:"create"}
        lvl = k.get(int(m.group(1)))
        if lvl: return lvl, "printed"
    # Bracketed single/double letter code: (R), (U), (Ap), (An), (Ev), (Cr), (E), (C)
    m_code = re.search(r'[\(\[]\s*(R|U|Ap|An|Ev|Cr|E|C)\s*[\)\]]', text, re.I)
    if m_code:
        code_map = {'R':"remember",'U':"understand",'AP':"apply",'AN':"analyse",'EV':"evaluate",'E':"evaluate",'CR':"create",'C':"create"}
        lvl = code_map.get(m_code.group(1).upper())
        if lvl: return lvl, "printed"
    # Explicit words
    for word in BLOOM_WORDS:
        if re.search(r'\b' + word + r'\b', text, re.I):
            lvl = "analyse" if word == "analyze" else word.lower()
            return lvl, "printed"
    return None

# ══════════════════════════════════════════════════════════════════════
#  PAGE MODEL
# ══════════════════════════════════════════════════════════════════════

class PageInfo:
    __slots__ = ('number','text','tables','words','is_scanned')
    def __init__(self, number, text, tables, words, is_scanned=False):
        self.number    = number
        self.text      = text
        self.tables    = tables   # List[List[List[str]]]
        self.words     = words    # List[{text,x0,y0,x1,y1}]
        self.is_scanned= is_scanned

    def line_at(self, char_pos: int) -> int:
        """Return line index (0-based) for a character position."""
        return self.text[:char_pos].count('\n')

# ══════════════════════════════════════════════════════════════════════
#  PDF READER
# ══════════════════════════════════════════════════════════════════════

class PDFReader:
    def __init__(self, path: str):
        self.path  = path
        self.pages: List[PageInfo] = []
        self._sha  = ""
        self._load()

    def _load(self):
        if not os.path.isfile(self.path):
            print(f"ERROR: File not found: {self.path}", file=sys.stderr)
            sys.exit(2)
        # SHA-256
        h = hashlib.sha256()
        with open(self.path,'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''): h.update(chunk)
        self._sha = h.hexdigest()

        if HAS_FITZ:
            self._load_fitz()
        elif HAS_PDFPLUMBER:
            self._load_pdfplumber()

    def _load_pdfplumber(self):
        try:
            with pdfplumber.open(self.path) as pdf:
                for i, pg in enumerate(pdf.pages, 1):
                    text = pg.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    tables = []
                    for tbl in (pg.extract_tables() or []):
                        clean = [[str(c or "").strip() for c in row] for row in (tbl or [])]
                        tables.append(clean)
                    words = []
                    try:
                        for w in (pg.extract_words(x_tolerance=3) or []):
                            words.append({"text":w.get("text",""),
                                          "x0":w.get("x0",0),"y0":w.get("top",0),
                                          "x1":w.get("x1",0),"y1":w.get("bottom",0)})
                    except Exception: pass
                    is_scanned = len(text.strip()) < 50 and len(words) < 10
                    self.pages.append(PageInfo(i, text, tables, words, is_scanned))
        except Exception as e:
            print(f"ERROR reading PDF: {e}", file=sys.stderr)
            sys.exit(2)

    def _load_fitz(self):
        try:
            doc = fitz.open(self.path)
            for i, pg in enumerate(doc, 1):
                text  = pg.get_text("text") or ""
                words = [{"text":w[4],"x0":w[0],"y0":w[1],"x1":w[2],"y1":w[3]}
                         for w in pg.get_text("words")]
                is_scanned = len(text.strip()) < 50
                self.pages.append(PageInfo(i, text, [], words, is_scanned))
            doc.close()
        except Exception as e:
            print(f"ERROR reading PDF: {e}", file=sys.stderr)
            sys.exit(2)

    @property
    def page_count(self): return len(self.pages)

    def full_text(self) -> str:
        return "\n\f\n".join(p.text for p in self.pages)

    def range_text(self, start: int, end: int) -> str:
        return "\n\f\n".join(p.text for p in self.pages
                             if start <= p.number <= end)

    def _extract_tables_for_page(self, page_num: int) -> List[List[List[str]]]:
        fitz_tables = []
        if HAS_FITZ:
            try:
                if not hasattr(self, '_fitz_doc') or self._fitz_doc is None or getattr(self._fitz_doc, 'is_closed', True):
                    self._fitz_doc = fitz.open(self.path)
                pg = self._fitz_doc[page_num - 1]
                tabs = pg.find_tables()
                for t in tabs:
                    data = t.extract()
                    clean = [[str(c or "").strip() for c in row] for row in (data or [])]
                    if clean and any(any(c for c in row) for row in clean):
                        fitz_tables.append(clean)
            except Exception:
                pass

        if fitz_tables:
            return fitz_tables

        plumber_tables = []
        if HAS_PDFPLUMBER:
            try:
                if not hasattr(self, '_plumber_doc') or self._plumber_doc is None:
                    self._plumber_doc = pdfplumber.open(self.path)
                pg = self._plumber_doc.pages[page_num - 1]
                for tbl in (pg.extract_tables() or []):
                    clean = [[str(c or "").strip() for c in row] for row in (tbl or [])]
                    if clean and any(any(c for c in row) for row in clean):
                        plumber_tables.append(clean)
            except Exception:
                pass

        return plumber_tables

    def range_tables(self, start: int, end: int) -> List[Tuple[int, List]]:
        result = []
        for p in self.pages:
            if start <= p.number <= end:
                if not p.tables:
                    p.tables = self._extract_tables_for_page(p.number)
                for tbl in p.tables:
                    result.append((p.number, tbl))
        return result

    def scanned_pages(self, start: int, end: int) -> List[int]:
        return [p.number for p in self.pages
                if start <= p.number <= end and p.is_scanned]

# ══════════════════════════════════════════════════════════════════════
#  DOCUMENT GRAMMAR  (runtime induction)
# ══════════════════════════════════════════════════════════════════════

class DocumentGrammar:
    def __init__(self, reader: PDFReader):
        self.reader = reader
        self.unit_keyword   = "UNIT"        # learned
        self.co_prefix      = "CO"          # learned
        self.po_prefix      = "PO"          # learned
        self.dominant_separator = "-"       # learned
        self.matrix_symbols: set = set()    # learned
        self.has_toc        = False
        self.toc_page       = -1
        self._induce()

    def _induce(self):
        sample = self.reader.full_text()[:60000]

        # Learn unit keyword
        counts = Counter()
        for kw in ["UNIT","MODULE","PART","CHAPTER","SECTION"]:
            counts[kw] = len(re.findall(r'(?i)\b' + kw + r'\s+(?:[IVXLCDM]+|\d+)\b', sample))
        self.unit_keyword = counts.most_common(1)[0][0] if counts else "UNIT"

        # Learn separator
        dashes  = len(re.findall(r'\s-\s', sample))
        semis   = len(re.findall(r';', sample))
        bullets = len(re.findall(r'[\u2022\u2023\u25e6\u2219]', sample))
        self.dominant_separator = (
            ";" if semis > dashes * 2 else
            "bullet" if bullets > dashes else "-"
        )

        # Detect TOC
        for pg in self.reader.pages[:10]:
            if len(re.findall(r'\b\d+\b', pg.text)) > 15 and \
               len(re.findall(r'\.{3,}', pg.text)) > 3:
                self.has_toc = True
                self.toc_page = pg.number
                break

        # Matrix symbols
        # Look for tables that might be CO-PO matrices
        full = self.reader.full_text()
        m = RE_MATRIX_HDR.search(full)
        if m:
            region = full[m.start():m.start()+2000]
            for sym in re.findall(r'\b([SMLHsmlh]|[123456])\b', region):
                self.matrix_symbols.add(sym.upper())
        if not self.matrix_symbols:
            self.matrix_symbols = {'S','M','L','1','2','3','H'}

# ══════════════════════════════════════════════════════════════════════
#  COURSE DETECTOR
# ══════════════════════════════════════════════════════════════════════

class CourseCandidate:
    __slots__ = ('code','title','page','score','signals','aliases')
    def __init__(self, code, title, page, score=0.5, signals=None, aliases=None):
        self.code    = code
        self.title   = title
        self.page    = page
        self.score   = score
        self.signals = signals or []
        self.aliases = aliases or []

class CourseDetector:
    def __init__(self, reader: PDFReader, grammar: DocumentGrammar,
                 hints: Dict = None):
        self.reader  = reader
        self.grammar = grammar
        self.hints   = hints or {}

    def detect(self) -> List[CourseCandidate]:
        syllabus_candidates: Dict[str, CourseCandidate] = {}
        curriculum_candidates: Dict[str, CourseCandidate] = {}

        for pg in self.reader.pages:
            text = pg.text
            if not text.strip(): continue
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines: continue

            # Count distinct codes on this page
            page_codes = set(re.findall(RE_CODE, text)) - STOP_WORDS
            page_codes = {c for c in page_codes if not re.match(r'^(CO|PO|PSO|BT|K)\d+$', c)}
            is_multi_course_page = len(page_codes) >= 3 or bool(re.search(r'(?i)(CURRICULUM|SEMESTER\s*[I|1-8]|COURSE\s*STRUCTURE|SCHEME\s*OF\s*INSTRUCTION)', text))
            has_syllabus_signals = bool(re.search(r'(?i)(PREAMBLE|COURSE\s*OBJECTIVES?|COURSE\s*OUTCOMES?|SYLLABUS|TEXT\s*BOOKS?|REFERENCES?|PREREQUISITE)', text))

            # 1. Single / Detailed Course Syllabus Page
            if not is_multi_course_page or has_syllabus_signals:
                limit = len(lines) if has_syllabus_signals else min(10, len(lines))
                for i in range(limit):
                    line = lines[i]
                    if re.fullmatch(r'\d{1,4}', line): continue

                    # For mid-page lines (i >= 8), require strong syllabus signals immediately below
                    if i >= 8:
                        below_chunk = ' '.join(lines[i:min(i+8, len(lines))])
                        if not re.search(r'(?i)(Category\s+L\s+T\s+P|PREAMBLE|PREREQUISITE|COURSE\s*OBJECTIVES?|COURSE\s*OUTCOMES?|SYLLABUS)', below_chunk):
                            continue

                    words = line.split()
                    code_cand = None
                    inline_title = None

                    # A. Check if line starts with code and title on same line (e.g. "CS8391 DATA STRUCTURES", "CS101: Introduction to...")
                    m_sep = re.match(r'^([A-Z0-9\.\-]{2,15})\s*[:\-–]\s*(.+)$', line)
                    if m_sep:
                        c_try = m_sep.group(1).strip().upper()
                        t_try = m_sep.group(2).strip()
                        if is_valid_course_code(c_try) and len(t_try) > 3 and sum(c.isalpha() for c in t_try) > len(t_try) * 0.35:
                            code_cand = c_try
                            inline_title = t_try

                    # A2. Check reverse: "<TITLE> - <CODE>" (e.g. "YOGA AND MEDITATION - 34121Z81")
                    if not code_cand:
                        m_rev = re.match(r'^(.+?)\s*[:\-–]\s*([A-Z0-9\.\-]{3,15})$', line)
                        if m_rev:
                            t_try = m_rev.group(1).strip()
                            c_try = m_rev.group(2).strip().upper()
                            if is_valid_course_code(c_try) and len(t_try) > 3 and sum(c.isalpha() for c in t_try) > len(t_try) * 0.35:
                                code_cand = c_try
                                inline_title = t_try

                    # B. Check first word or first two words as code
                    if not code_cand and len(words) >= 2:
                        if is_valid_course_code(words[0]):
                            rem = ' '.join(words[1:])
                            if len(rem) > 3 and sum(c.isalpha() for c in rem) > len(rem) * 0.35:
                                code_cand = words[0].upper()
                                inline_title = rem
                        elif len(words) >= 3 and is_valid_course_code(' '.join(words[:2])):
                            rem = ' '.join(words[2:])
                            if len(rem) > 3 and sum(c.isalpha() for c in rem) > len(rem) * 0.35:
                                code_cand = ' '.join(words[:2]).upper()
                                inline_title = rem

                    # C. Standalone code line
                    if not code_cand:
                        if len(words) == 1 and (RE_CODE.fullmatch(words[0]) or RE_CODE_DOT.fullmatch(words[0])):
                            code_cand = words[0].upper()
                        elif len(words) == 2 and RE_CODE_SPACED.fullmatch(line):
                            code_cand = line.upper()
                        elif ':' in line or '-' in line:
                            m = RE_LABEL_CODE.search(line)
                            if m: code_cand = m.group(1).upper()

                    if code_cand and is_valid_course_code(code_cand):
                        title_lines = [inline_title] if inline_title else []
                        if not inline_title:
                            j = i + 1
                            while j < min(i + 6, len(lines)):
                                nxt = lines[j]
                                if re.search(r'(?i)^(category|preamble|prerequisite|course\s*objectives?|course\s*outcomes?|l\b|credit|credits|syllabus)', nxt):
                                    break
                                if sum(c.isalpha() for c in nxt) > len(nxt) * 0.4 and len(nxt) > 2:
                                    title_lines.append(nxt)
                                j += 1
                        if title_lines:
                            t = clean_title(title_lines)
                            if t and len(t) > 3:
                                norm = normalize_id(code_cand)
                                cand_key = f"{norm}:{norm_title(t)}:{pg.number}"
                                if cand_key not in syllabus_candidates:
                                    syllabus_candidates[cand_key] = CourseCandidate(code_cand, t, pg.number, 0.98, ["syllabus-page"])
                                # Only break if top of page; mid-page may have another course or continue
                                if i < 8:
                                    break

            # 2. Multi-course Curriculum / Overview Table (from text lines)
            if is_multi_course_page:
                for i, line in enumerate(lines):
                    m = RE_CODE.search(line) or RE_CODE_DOT.search(line) or RE_CODE_SPACED.search(line)
                    if m:
                        code_cand = m.group(0).upper()
                        if not is_valid_course_code(code_cand): continue
                        title_lines = []
                        for k in range(i + 1, min(i + 4, len(lines))):
                            nxt = lines[k]
                            if RE_CODE.search(nxt) or RE_CODE_DOT.search(nxt) or RE_CODE_SPACED.search(nxt) or re.match(r'^\d+$', nxt): break
                            if sum(c.isalpha() for c in nxt) > len(nxt) * 0.4:
                                title_lines.append(nxt)
                                if len(title_lines) >= 2: break
                        if title_lines:
                            t = clean_title(title_lines)
                            if t and len(t) > 3:
                                norm = normalize_id(code_cand)
                                cand_key = f"{norm}:{norm_title(t)}"
                                if cand_key not in curriculum_candidates:
                                    curriculum_candidates[cand_key] = CourseCandidate(code_cand, t, pg.number, 0.85, ["curriculum-table"])

            # 3. Curriculum Scheme from structured tables
            if is_multi_course_page or pg.number <= 25:
                pg_tabs = self.reader._extract_tables_for_page(pg.number)
                for tbl in pg_tabs:
                    if not tbl or len(tbl) < 2: continue
                    hdr = [str(c or "").strip().lower() for c in tbl[0]]
                    code_col = next((ci for ci, h in enumerate(hdr) if any(k in h for k in ['course code', 'sub code', 'subject code', 'paper code', 'course no', 'sub. code', 'code'])), None)
                    title_col = next((ci for ci, h in enumerate(hdr) if any(k in h for k in ['course title', 'course name', 'subject title', 'subject name', 'title', 'name of the course', 'paper title', 'course'])), None)
                    if code_col is not None and title_col is not None and code_col != title_col:
                        for row in tbl[1:]:
                            if code_col < len(row) and title_col < len(row):
                                raw_code = str(row[code_col] or "").strip().upper()
                                raw_title = str(row[title_col] or "").strip()
                                if is_valid_course_code(raw_code) and len(raw_title) > 3:
                                    cleaned_t = clean_title([raw_title])
                                    if cleaned_t and len(cleaned_t) > 3:
                                        norm = normalize_id(raw_code)
                                        cand_key = f"{norm}:{norm_title(cleaned_t)}"
                                        if cand_key not in curriculum_candidates:
                                            curriculum_candidates[cand_key] = CourseCandidate(raw_code, cleaned_t, pg.number, 0.90, ["table-row"])

            # 4. Explicit label fallback: Course Code: CS23301
            for m in RE_LABEL_CODE.finditer(text):
                code_cand = m.group(1).upper()
                if is_valid_course_code(code_cand):
                    norm = normalize_id(code_cand)
                    t = self._extract_title(text, m.start())
                    if t:
                        cand_key = f"{norm}:{norm_title(t)}:{pg.number}"
                        if cand_key not in syllabus_candidates:
                            syllabus_candidates[cand_key] = CourseCandidate(code_cand, t, pg.number, 0.95, ["explicit-label"])

        # Merge: syllabus_candidates wins over curriculum_candidates
        from collections import OrderedDict
        merged = OrderedDict()
        for k, cand in syllabus_candidates.items():
            merged[k] = cand

        for k, cand in curriculum_candidates.items():
            # Check if this curriculum candidate already exists in syllabus_candidates
            matching_syl = None
            c_title_norm = norm_title(cand.title)
            for s_k, s_cand in syllabus_candidates.items():
                s_title_norm = norm_title(s_cand.title)
                if codes_match(cand.code, s_cand.code):
                    matching_syl = s_cand; break
                if len(c_title_norm) > 4 and (c_title_norm == s_title_norm or c_title_norm in s_title_norm or s_title_norm in c_title_norm):
                    matching_syl = s_cand; break

            if matching_syl:
                # Syllabus candidate on actual syllabus page wins!
                if cand.code not in matching_syl.aliases:
                    matching_syl.aliases.append(cand.code)
                if matching_syl.code not in matching_syl.aliases:
                    matching_syl.aliases.append(matching_syl.code)
                if not matching_syl.code or (cand.code and len(cand.code) < len(matching_syl.code)):
                    matching_syl.code = cand.code
                continue

            if k not in merged:
                merged[k] = cand

        result = sorted(merged.values(), key=lambda x: (x.page, -x.score))

        # Apply hints: manual course overrides
        if "courses" in self.hints:
            for hc in self.hints["courses"]:
                code  = hc.get("code","")
                title = hc.get("title","")
                page  = hc.get("page", 1)
                norm  = normalize_id(code)
                found = next((c for c in result if codes_match(c.code, code)), None)
                if found:
                    found.title = title or found.title
                    found.page  = page or found.page
                else:
                    result.append(CourseCandidate(code, title, page, 0.99, ["hint"]))
            result.sort(key=lambda x: x.page)

        return result

    def _extract_title(self, text: str, pos: int) -> Optional[str]:
        # 1. Label-based title
        m = RE_LABEL_TITLE.search(text[max(0,pos-400):pos+600])
        if m:
            t = m.group(1).strip().rstrip('.,:;')
            if 3 < len(t) < 150: return t

        # 2. Surrounding lines
        lines = text.split('\n')
        char, code_line = 0, 0
        for i, l in enumerate(lines):
            if char + len(l) >= pos:
                code_line = i; break
            char += len(l) + 1

        best = None
        for delta in [0,1,-1,2,-2,3,-3]:
            idx = code_line + delta
            if not (0 <= idx < len(lines)): continue
            line = lines[idx].strip()
            if (5 < len(line) < 120
                    and not RE_UNIT.match(line)
                    and not re.match(r'(?i)^(CO|PO|PSO)\s*\d', line)
                    and not re.match(r'^\d+$', line)
                    and sum(c.isalpha() for c in line) > len(line)*0.45):
                cleaned = RE_CODE.sub('', line).strip(' :-|')
                candidate = cleaned if len(cleaned) > 4 else line
                if best is None or len(candidate) > len(best):
                    best = candidate

        return best

    def find_boundary(self, candidates: List[CourseCandidate],
                      code: str, title: str,
                      target_obj: Optional[CourseCandidate] = None) -> Tuple[int, int]:
        norm_code  = normalize_id(code)
        target_t   = norm_title(title) if title else ""

        idx = None
        if target_obj is not None and target_obj in candidates:
            idx = candidates.index(target_obj)

        if idx is None:
            def matches_cand(c):
                if target_t and norm_title(c.title) and (target_t == norm_title(c.title) or target_t in norm_title(c.title) or norm_title(c.title) in target_t):
                    return True
                if codes_match(c.code, code): return True
                if any(codes_match(a, code) for a in getattr(c, 'aliases', [])): return True
                return False

            idx = next((i for i, c in enumerate(candidates) if matches_cand(c)), None)

        if idx is None and norm_code:
            idx = next((i for i, c in enumerate(candidates)
                        if norm_code in normalize_id(c.code) or normalize_id(c.code) in norm_code), None)

        if idx is None:
            # Document-wide fallback search for syllabus page
            for pg in self.reader.pages:
                if codes_match(code, pg.text) or (title and title.upper() in pg.text.upper()):
                    if any(k in pg.text.upper() for k in ["PREAMBLE", "COURSE OUTCOMES", "SYLLABUS", "COURSE OBJECTIVES"]):
                        start = pg.number
                        for nxt_pg in self.reader.pages[pg.number:]:
                            if any(k in nxt_pg.text.upper() for k in ["PREAMBLE", "CATEGORY", "COURSE OUTCOMES"]) and nxt_pg.number > start:
                                return start, nxt_pg.number
                        return start, min(start + 4, self.reader.page_count)
            return 1, self.reader.page_count

        target_cand = candidates[idx]

        # If target candidate is merely from a curriculum overview table, search downstream for the actual detailed syllabus page!
        if "curriculum-table" in target_cand.signals or "table-row" in target_cand.signals or target_cand.page <= 25:
            t_norm = norm_title(target_cand.title)
            syl_cand = next((c for c in candidates if c.page > target_cand.page and (codes_match(c.code, target_cand.code) or (t_norm and (t_norm == norm_title(c.title) or t_norm in norm_title(c.title) or norm_title(c.title) in t_norm)))), None)
            if syl_cand:
                idx = candidates.index(syl_cand)
                target_cand = syl_cand
            else:
                # Document-wide downstream search for the true syllabus page
                for pg in self.reader.pages[target_cand.page:]:
                    p_text = pg.text or ""
                    matches_title = bool(t_norm and len(t_norm) > 4 and t_norm in norm_title(p_text[:800]))
                    matches_code = codes_match(target_cand.code, p_text[:400])
                    has_syl_markers = any(k in p_text.upper() for k in ["PREAMBLE", "COURSE OUTCOMES", "COURSE OBJECTIVES", "SYLLABUS", "UNIT", "MODULE"])
                    if (matches_title or matches_code) and has_syl_markers:
                        target_cand = CourseCandidate(target_cand.code, target_cand.title, pg.number, 0.98, ["syllabus-page-found"])
                        break

        start = target_cand.page
        next_cand = next((c for c in candidates[idx+1:] if c.page > start and (c.page - start) <= 6), None)
        if next_cand:
            end = next_cand.page
        else:
            end = None
            max_scan = min(start + 5, self.reader.page_count)
            for pg in self.reader.pages[start:max_scan]:
                p_text = pg.text or ""
                if any(k in p_text.upper() for k in ["COURSE OUTCOMES", "SYLLABUS", "COURSE OBJECTIVES", "PREAMBLE", "PREREQUISITES"]):
                    m_c = RE_CODE.search(p_text[:400])
                    if m_c and not codes_match(target_cand.code, m_c.group(0)):
                        end = pg.number
                        break
            if end is None or end <= start:
                end = min(start + 3, self.reader.page_count)

        return start, max(start, end)

# ══════════════════════════════════════════════════════════════════════
#  DEEP EXTRACTOR
# ══════════════════════════════════════════════════════════════════════

class DeepExtractor:
    def __init__(self, reader: PDFReader, grammar: DocumentGrammar,
                 start: int, end: int, hints: Dict = None):
        self.reader  = reader
        self.grammar = grammar
        self.sp, self.ep = start, end
        self.hints   = hints or {}
        self.course_code = self.hints.get("course_code", "")
        self.text    = reader.range_text(start, end)
        self.tables  = reader.range_tables(start, end)
        self.scanned = reader.scanned_pages(start, end)
        self.not_extracted: List[str] = []

        # Prevent cross-course leakage: if multi-page range, truncate text at start of next course on end page
        self._end_page_dropped = False
        if end > start and end <= len(reader.pages):
            parts = self.text.split("\n\f\n")
            if len(parts) > 1 and parts[-1].strip():
                last_txt = parts[-1]
                m_next = re.search(r'(?m)^[\s\u00a0]*([A-Z0-9\.\-]{3,15})\s*\n+[\s\u00a0]*([A-Z][A-Z0-9\s,\-–\(\)]{4,80})\s*\n+Category', last_txt)
                if not m_next:
                    m_next = re.search(r'(?i)\b(?:course|subject)\s*code\s*[:\-]\s*([A-Z0-9\.\-]{3,15})', last_txt)
                if not m_next:
                    m_next = re.search(r'(?m)^[\s\u00a0]*([A-Z]{2,5}\d{2,5}[A-Z]?)\b[^\n]*\b([A-Z][A-Z\s]{4,80})\b', last_txt)
                if m_next:
                    cand_code = m_next.group(1).strip()
                    if not codes_match(cand_code, self.course_code):
                        if m_next.start() < 120:
                            self._end_page_dropped = True
                            parts = parts[:-1]
                        else:
                            parts[-1] = last_txt[:m_next.start()].strip()
                        self.text = "\n\f\n".join(parts).strip()

        if self.scanned:
            self.not_extracted.append(
                f"pages {self.scanned} appear scanned — text extraction may be incomplete; "
                f"install pytesseract for OCR support"
            )

    # ── Front matter ────────────────────────────────────────────────
    def extract_front_matter(self, code: str, title: str) -> Dict:
        text   = self.text[:3000]   # front of course
        pages_list = list(range(self.sp, self.ep)) if self._end_page_dropped else list(range(self.sp, self.ep + 1))
        result = {
            "code":      code,
            "title":     title,
            "category":  self._category(self.text[:2000]),
            "lecture":   None,
            "tutorial":  None,
            "practical": None,
            "credits":   None,
            "pages":     pages_list,
        }
        ltpc = self._ltpc(self.text[:4000])
        if ltpc:
            keys = ["lecture","tutorial","practical","credits"]
            for k, v in zip(keys, ltpc):
                result[k] = v
        elif not any(result[k] is not None for k in ["lecture","tutorial","practical"]):
            m = RE_CREDITS.search(text)
            if m:
                try: result["credits"] = int(float(m.group(1)))
                except: pass
        return result

    def _category(self, text: str) -> str:
        for cat in ["HSMC","AECC","FC-HS","FC-BS","FC-ES","EC-PS","EC-IE","OE-EA","AC","SE","PC","PE","OE","BS","ES","HS","MC","LC","FC","GE","SEC","CC"]:
            if re.search(r'\b' + re.escape(cat) + r'\b', text[:1500]): return cat
        m = re.search(r'(?i)\b(?:category|type)\s*[:\-]?\s*([A-Z0-9\-]{2,8})\b', text[:1500])
        if m and m.group(1).upper() not in ("L", "T", "P", "C", "CREDIT", "CREDITS", "COURSE"):
            return m.group(1).upper()
        m_hdr = re.search(r'(?i)\bcategory\b[^\n]*\n\s*([A-Z0-9\-]{2,10})\b', text[:1500])
        if m_hdr and m_hdr.group(1).upper() not in ("L", "T", "P", "C", "CREDIT", "CREDITS"):
            return m_hdr.group(1).upper()
        return ""

    def _ltpc(self, text: str) -> Optional[List]:
        # Table: L T P C header row
        for _, tbl in self.tables:
            for i, row in enumerate(tbl):
                cells = [str(c or "").strip().upper() for c in row]
                if 'L' in cells and 'T' in cells and 'P' in cells:
                    if i + 1 < len(tbl):
                        vals = []
                        for c in tbl[i+1]:
                            try: vals.append(int(str(c).strip()))
                            except: pass
                        if len(vals) >= 3: return vals[:4]

        # Text: L T P C or L T P Credit followed by numbers
        m = re.search(r'(?i)\bL\s*[\n\t\s/:-]*T\s*[\n\t\s/:-]*P(?:\s*[\n\t\s/:-]*C(?:redits?)?)?\b', text)
        if m:
            after = text[m.end():m.end()+150]
            m_tuple = re.search(r'\b(\d{1,2})\s*[-/:\s]\s*(\d{1,2})\s*[-/:\s]\s*(\d{1,2})(?:\s*[-/:\s]\s*(\d{1,2}))?\b', after)
            if m_tuple:
                vals = [int(m_tuple.group(i)) for i in range(1, 5) if m_tuple.group(i) is not None]
                if len(vals) >= 3:
                    return vals[:4]
            nums = re.findall(r'\b\d+\b', after)
            if len(nums) >= 3:
                return [int(x) for x in nums[:4]]

        # Inline L: 3, T: 0, P: 0
        l_m = re.search(r'(?i)\bL(?:ecture)?\s*[:\-]?\s*(\d+)', text)
        t_m = re.search(r'(?i)\bT(?:utorial)?\s*[:\-]?\s*(\d+)', text)
        p_m = re.search(r'(?i)\bP(?:ractical)?\s*[:\-]?\s*(\d+)', text)
        c_m = re.search(r'(?i)\bC(?:redits?)?\s*[:\-]?\s*(\d+)', text)
        if l_m and t_m and p_m:
            return [int(l_m.group(1)), int(t_m.group(1)), int(p_m.group(1)), int(c_m.group(1)) if c_m else None]

        # Tuple like "3 0 0 3"
        mv = RE_LTPC_VALS.search(text[:2000])
        if mv:
            vals = [int(mv.group(i)) for i in range(1,5) if mv.group(i)]
            if len(vals) >= 3: return vals
        return None

    # ── Units ────────────────────────────────────────────────────────
    def extract_units(self) -> List[Dict]:
        text   = self.text
        units  = []
        matches = list(RE_UNIT.finditer(text))

        if not matches:
            # Fallback A: Units from structured syllabus table
            tbl_units = self._units_from_table()
            if tbl_units: return tbl_units

            # Fallback B: Roman numeral headings e.g. I. LINEAR STRUCTURES
            roman_matches = list(RE_ROMAN_UNIT.finditer(text))
            if len(roman_matches) >= 2:
                for idx, rm in enumerate(roman_matches):
                    num = roman_to_int(rm.group(1)) or (idx + 1)
                    title = rm.group(2).strip()
                    body_start = rm.end()
                    body_end = roman_matches[idx+1].start() if idx+1 < len(roman_matches) else len(text)
                    body = self._trim_unit_body(text[body_start:body_end].strip())
                    hours = self._hours(rm.group(0) + '\n' + body[:300])
                    topics = self._split_topics(body, num)
                    units.append({
                        "number": num,
                        "title":  title,
                        "hours":  hours,
                        "text":   body,
                        "topics": topics,
                    })
                return units

            # Fallback C: Implicit units under SYLLABUS / COURSE CONTENT
            m_syl = re.search(r'(?im)^[\s]*(?:SYLLABUS|COURSE\s*CONTENTS?|COURSE\s*OUTLINE|TOPICS?)\b', text)
            if m_syl:
                syl_text = text[m_syl.end():]
                m_end = re.search(r'(?im)^[\s]*(?:TEXT\s*BOOKS?|REFERENCES?|COURSE\s*DESIGNERS|COURSE\s*OUTCOMES?|CO\s*[-/]?\s*PO)\b', syl_text)
                if m_end:
                    syl_text = syl_text[:m_end.start()]
                lines = [l.strip() for l in syl_text.splitlines() if l.strip()]
                headings = []
                for i, l in enumerate(lines):
                    alpha = [c for c in l if c.isalpha()]
                    if not alpha or len(l) > 85 or len(l) < 3: continue
                    upper_ratio = sum(c.isupper() for c in alpha) / len(alpha)
                    is_head = (upper_ratio >= 0.70 or l.istitle()) and not l.endswith(('.', ';', ',')) and not re.search(r'[-–—]\s+[A-Za-z]', l)
                    if is_head and not re.match(r'^(?:TOTAL|HOURS|PERIODS|CREDITS|PREAMBLE|OBJECTIVES?|CO\d|PO\d|PREREQUISITE)\b', l, re.I):
                        headings.append((i, l))
                if headings:
                    for idx, (line_idx, h_title) in enumerate(headings):
                        start_line = line_idx + 1
                        end_line = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
                        body_lines = lines[start_line:end_line]
                        body = ' '.join(body_lines)
                        topics = self._split_topics(body, idx + 1)
                        units.append({
                            "number": idx + 1,
                            "title":  h_title,
                            "hours":  self._hours(h_title + '\n' + body[:300]),
                            "text":   body,
                            "topics": topics,
                        })
                    return units

            # Fallback D: Hints
            if "units" in self.hints:
                return self.hints["units"]

            # Fallback E: Treat entire course text as Unit 1 if body has content
            trimmed = self._trim_unit_body(text)
            if len(trimmed) > 50:
                topics = self._split_topics(trimmed, 1)
                units.append({
                    "number": 1,
                    "title":  "",
                    "hours":  self._hours(trimmed[:300]),
                    "text":   trimmed,
                    "topics": topics,
                })
                return units

            self.not_extracted.append(
                "units — no unit/module/part headings found; document may use non-standard heading style"
            )
            return []

        for i, m in enumerate(matches):
            num_str = m.group(2).strip()
            num     = roman_to_int(num_str) or (i + 1)

            body_start = m.end()
            body_end   = matches[i+1].start() if i+1 < len(matches) else len(text)
            raw_seg    = text[body_start:body_end]

            title, hours, body = self._parse_unit_segment(raw_seg)

            body    = self._trim_unit_body(body)
            if hours is None:
                hours = self._hours(body[:200])
            topics  = self._split_topics(body, num)

            units.append({
                "number": num,
                "title":  title,
                "hours":  hours,
                "text":   body,
                "topics": topics,
            })

        return units

    def _parse_unit_segment(self, raw_seg: str) -> Tuple[str, Optional[int], str]:
        text = raw_seg.strip()
        title = ""
        hours = None
        body = text

        text = re.sub(r'^[\s\-–—:.]+', '', text).strip()

        # Pattern 1: Inline ALL-CAPS title followed by hours and sentence/topics
        m_inline = re.match(
            r'^\s*([A-Z0-9\s,\-–—/&]{3,80}?)\s+'
            r'(?:[\(\[]\s*(\d{1,3})\s*(?:hr?s?\.?|hours?|periods?)?[\)\]]|[-–—:]\s*(\d{1,3})\s*(?:hr?s?\.?|hours?|periods?)?|\b(\d{1,2})\b)\s+'
            r'(?=[A-Z][a-z])',
            text
        )
        if m_inline:
            title = m_inline.group(1).strip(' -–—:.')
            h_str = m_inline.group(2) or m_inline.group(3) or m_inline.group(4)
            if h_str: hours = int(h_str)
            body = text[m_inline.end():].strip()
            body = re.sub(r'^(?:(?:periods?|hours?|hrs?\.?)\b[\s\-–—:]*)+', '', body, flags=re.I).strip()
            return title, hours, body

        # Pattern 2: Inline ALL-CAPS title directly transitioning to mixed-case without hours in between
        m_inline_nohours = re.match(
            r'^\s*([A-Z0-9\s,\-–—/&]{3,80}?)\s*[-–—:]?\s+(?=[A-Z][a-z])',
            text
        )
        if m_inline_nohours:
            cand_title = m_inline_nohours.group(1).strip(' -–—:.')
            if len(cand_title.split()) >= 1 and cand_title.isupper():
                title = cand_title
                body = text[m_inline_nohours.end():].strip()
                body = re.sub(r'^(?:(?:periods?|hours?|hrs?\.?)\b[\s\-–—:]*)+', '', body, flags=re.I).strip()
                return title, hours, body

        # Pattern 3: Multiline
        first_nl = text.find('\n')
        first_line = (text[:first_nl] if first_nl != -1 else text).strip()
        if 2 < len(first_line) < 85 and not first_line.endswith(('.', ';', ',')):
            h_m = re.search(r'[\(\[]\s*(\d{1,3})\s*(?:hr?s?\.?|hours?|periods?)?[\)\]]|(?:[-–—:]|\b)\s*(\d{1,2})\s*(?:hr?s?\.?|hours?|periods?)\s*$', first_line, re.I)
            if h_m:
                hours = int(h_m.group(1) or h_m.group(2))
                cand = re.sub(r'[\(\[]\s*\d{1,3}\s*(?:hr?s?\.?|hours?|periods?)?[\)\]]|(?:[-–—:]|\b)\s*\d{1,2}\s*(?:hr?s?\.?|hours?|periods?)\s*$', '', first_line, flags=re.I).strip(' -–—:.')
            else:
                cand = first_line.strip(' -–—:.')
            if cand and not re.match(r'(?i)^(?:TOTAL|HOURS|PERIODS|CREDITS|PREAMBLE|OBJECTIVES?|CO\d|PO\d)\b', cand):
                alpha = [c for c in cand if c.isalpha()]
                if alpha and (sum(c.isupper() for c in alpha) / len(alpha) > 0.4 or cand.istitle()):
                    title = cand
                    body = (text[first_nl+1:] if first_nl != -1 else '').strip()
                    body = re.sub(r'^(?:(?:periods?|hours?|hrs?\.?)\b[\s\-–—:]*)+', '', body, flags=re.I).strip()
                    return title, hours, body

        return title, hours, body

    def _units_from_table(self) -> List[Dict]:
        for _, tbl in self.tables:
            if not tbl or len(tbl) < 2: continue
            hdr = [str(c or "").strip().lower() for c in tbl[0]]
            if any(k in ' '.join(hdr) for k in ['faculty', 'designation', 'designer', 'mail id']): continue
            unit_col = next((i for i, h in enumerate(hdr) if any(k in h for k in ['unit', 'module', 'chapter', 'part', 's.no', 'no.'])), None)
            content_col = next((i for i, h in enumerate(hdr) if any(k in h for k in ['content', 'contents', 'syllabus', 'topics', 'description', 'course content', 'details'])), None)
            hours_col = next((i for i, h in enumerate(hdr) if any(k in h for k in ['hours', 'hrs', 'periods', 'contact hours'])), None)
            title_col = next((i for i, h in enumerate(hdr) if any(k in h for k in ['title', 'unit title', 'module title', 'name'])), None)
            if unit_col is not None and content_col is not None and unit_col != content_col:
                res = []
                for row_idx, row in enumerate(tbl[1:], 1):
                    if unit_col < len(row) and content_col < len(row):
                        u_raw = str(row[unit_col] or "").strip()
                        num = roman_to_int(u_raw) or row_idx
                        u_title = str(row[title_col] or "").strip() if title_col is not None and title_col < len(row) else ""
                        body = str(row[content_col] or "").strip()
                        if len(body) > 10:
                            u_hrs = None
                            if hours_col is not None and hours_col < len(row):
                                u_hrs = self._hours(str(row[hours_col] or ""))
                            if not u_hrs:
                                u_hrs = self._hours(body)
                            res.append({
                                "number": num,
                                "title": u_title,
                                "hours": u_hrs,
                                "text": body,
                                "topics": self._split_topics(body, num)
                            })
                if len(res) >= 2:
                    return res
        return []

    def _trim_unit_body(self, text: str) -> str:
        """Cut off CO/PO/books/matrix that leaks into unit body."""
        text = re.sub(r'(?i)\bTotal\s*[:\-]?\s*\d+\s*(?:hr?s?|hours?|periods?)[^\n.]*', '', text).strip()
        stops = [
            r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))(?:Course\s+Outcomes?|CO\s*[:\-])',
            r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))(?:Programme\s+Outcomes?|Program\s+Outcomes?)',
            r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))(?:Text\s*Books?|Reference\s*Books?|References?)\s*[:\-]?',
            r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))(?:CO\s*[-/]?\s*PO|Mapping|Articulation|Correlation)',
            r'(?i)(?:^|[\n\r]|(?<=[.;:\s]))(?:UNIT|MODULE|PART|CHAPTER|SECTION|WEEK|SESSION)\s*[-–—:.\s]*\s*(?:[IVXLCDM]+|\d+)\b',
        ]
        cut = len(text)
        for pat in stops:
            m = re.search(pat, text)
            if m and m.start() < cut:
                cut = m.start()
        return text[:cut].strip()

    def _hours(self, text: str) -> Optional[int]:
        if not text: return None
        # 1. Explicit hours / periods (e.g. "9 hrs", "9 hours", "9 periods")
        m = RE_HOURS.search(text)
        if m: return int(m.group(1))

        # 2. Keyed pattern (e.g. "Hours: 9", "Periods: 8", "Contact Hours : 9")
        m_key = re.search(r'(?i)\b(?:hours?|periods?|contact\s*hours?|no\.?\s*of\s*(?:hours?|periods?))\s*[:\-]?\s*(\d{1,3})\b', text)
        if m_key: return int(m_key.group(1))

        # 3. Bracketed or parenthesized number at end of line (e.g. "[9]", "(8)", "(9 Periods)")
        m_bracket = re.search(r'[\(\[]\s*(\d{1,2})\s*(?:hr?s?\.?|periods?|hours?)?\s*[\)\]]', text)
        if m_bracket: return int(m_bracket.group(1))

        # 4. Heading line dash/colon annotation e.g. "- 9" or ": 9"
        m_dash = re.search(r'(?m)[-–—:]\s*(\d{1,2})\s*$', text[:200])
        if m_dash: return int(m_dash.group(1))

        return None

    # ── Topic splitter (7 strategies + reconstruction check) ─────────
    def _split_topics(self, body: str, unit_num: int) -> List[Dict]:
        if not body.strip(): return []
        topics = []

        # Remove trailing hours line (e.g. "Total: 45 hrs")
        body = re.sub(r'(?i)\n?total\s*[:\-]?\s*\d+\s*(?:hr?s?|hours?)[^\n]*', '', body).strip()

        # Strategy order: text-based first (faithful), then table fallback
        # semicolons > bullets > numbered > dashes > commas > newlines
        for strategy in [self._by_semicolon, self._by_bullet,
                         self._by_numbered, self._by_dash,
                         self._by_comma, self._by_newline]:
            parts = strategy(body)
            if len(parts) > 1:
                topics = self._make_topic_list(parts, unit_num)
                if topics: break

        # Fallback: structured table with topic/bloom columns (only if text splitting failed)
        if not topics:
            table_topics = self._try_table_topics(unit_num)
            if table_topics: return table_topics

        if not topics:
            # Whole unit as one topic
            pb = detect_printed_bloom(body[:200])
            if pb and pb[0]:
                bloom_val, bloom_src = pb
            else:
                bloom_val, bloom_src = infer_bloom(body), "inferred"
            topics.append({
                "id": f"u{unit_num}t1",
                "text": body.strip(),
                "bloom": bloom_val,
                "bloom_source": bloom_src,
            })

        return topics

    def _try_table_topics(self, unit_num: int) -> List[Dict]:
        """If a unit is presented as a table with Bloom column, parse it."""
        for _, tbl in self.tables:
            if not tbl or len(tbl) < 3: continue
            header = [str(c or "").strip().lower() for c in tbl[0]]
            # Reject if table header is faculty/designers or administrative table
            hdr_text = ' '.join(header)
            if any(k in hdr_text for k in ['faculty', 'designation', 'designer', 'mail id', 'department', 's. no']):
                continue
            if any(len(c) > 80 for c in header):
                continue

            topic_col = next((i for i, h in enumerate(header)
                              if h in ['topic', 'topics', 'subtopic', 'subtopics', 'topic name', 'content', 'contents']
                              or ('topic' in h and 'topic no' not in h)), None)
            bloom_col = next((i for i, h in enumerate(header)
                              if any(k in h for k in ['bloom', 'bt', 'level', 'k-level', 'taxonomy'])), None)
            if topic_col is None: continue

            topics = []
            for r_idx, row in enumerate(tbl[1:], 1):
                if topic_col >= len(row): continue
                text_val = str(row[topic_col] or "").strip()
                if not text_val or text_val == '-' or len(text_val) < 2: continue
                bloom_val = "understand"
                bloom_src = "inferred"
                if bloom_col is not None and bloom_col < len(row):
                    cell = str(row[bloom_col] or "").strip()
                    pb = detect_printed_bloom(cell)
                    if pb: bloom_val, bloom_src = pb
                    else: bloom_val = infer_bloom(text_val)
                else:
                    pb = detect_printed_bloom(text_val)
                    if pb:
                        bloom_val, bloom_src = pb
                        text_val = re.sub(r'\(?K[1-6]\)?|\b(?:BT|BL|L)[1-6]\b', '', text_val).strip()
                    else:
                        bloom_val = infer_bloom(text_val)
                topics.append({
                    "id":           f"u{unit_num}t{len(topics)+1}",
                    "text":         text_val,
                    "bloom":        bloom_val,
                    "bloom_source": bloom_src,
                })
            if topics: return topics
        return []

    def _split_guarded(self, text: str, sep_chars: str = ';') -> List[str]:
        """Split text by separator characters, but NEVER split inside parentheses or brackets."""
        parts = []
        cur = []
        depth = 0
        for ch in text:
            if ch in '([{':
                depth += 1
                cur.append(ch)
            elif ch in ')]}':
                if depth > 0: depth -= 1
                cur.append(ch)
            elif depth == 0 and ch in sep_chars:
                token = ''.join(cur).strip()
                if token: parts.append(token)
                cur = []
            else:
                cur.append(ch)
        if cur:
            token = ''.join(cur).strip()
            if token: parts.append(token)
        return [p for p in parts if len(p) > 1]

    def _by_semicolon(self, text: str) -> List[str]:
        return self._split_guarded(text, ';')

    def _by_bullet(self, text: str) -> List[str]:
        lines = text.split('\n')
        bullets = [re.sub(r'^[\u2022\u2023\u25e6\u2219\-\*\>]\s*','',l).strip()
                   for l in lines if re.match(r'^\s*[\u2022\u2023\u25e6\u2219\-\*\>]\s+', l)]
        return [b for b in bullets if len(b) > 1]

    def _by_numbered(self, text: str) -> List[str]:
        parts = re.split(r'\n\s*\d+[\.\)]\s+', text)
        return [p.strip() for p in parts if len(p.strip()) > 1]

    def _by_dash(self, text: str) -> List[str]:
        """Split by standalone dashes/hyphens outside brackets/parentheses."""
        parts = []
        cur = []
        depth = 0
        n = len(text)
        dash_chars = {'-', '–', '—'}
        i = 0
        while i < n:
            ch = text[i]
            if ch in '([{':
                depth += 1
                cur.append(ch)
            elif ch in ')]}':
                if depth > 0: depth -= 1
                cur.append(ch)
            elif depth == 0 and ch in dash_chars and (i > 0 and text[i-1].isspace()) and (i + 1 < n and text[i+1].isspace()):
                token = ''.join(cur).strip()
                if token: parts.append(token)
                cur = []
            else:
                cur.append(ch)
            i += 1
        if cur:
            token = ''.join(cur).strip()
            if token: parts.append(token)
        return [p for p in parts if len(p) > 1]

    def _by_comma(self, text: str) -> List[str]:
        """Split by commas outside brackets/parentheses to preserve subtopic clauses."""
        parts = []
        cur = []
        depth = 0
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch in '([{':
                depth += 1
                cur.append(ch)
            elif ch in ')]}':
                if depth > 0: depth -= 1
                cur.append(ch)
            elif depth == 0 and ch == ',':
                token = ''.join(cur).strip()
                if token: parts.append(token)
                cur = []
            elif depth == 0 and ch == '.' and (i + 1 < n and text[i+1].isspace() and i + 2 < n and text[i+2].isupper()):
                token = ''.join(cur).strip()
                if token: parts.append(token)
                cur = []
            else:
                cur.append(ch)
            i += 1
        if cur:
            token = ''.join(cur).strip()
            if token: parts.append(token)
        return [p.strip(' .') for p in parts if len(p.strip()) > 2]

    def _by_newline(self, text: str) -> List[str]:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if all(5 < len(l) < 100 for l in lines) and len(lines) > 1:
            return lines
        return []

    def _make_topic_list(self, parts: List[str], unit_num: int) -> List[Dict]:
        topics = []
        expanded = []
        for p in parts:
            p = p.strip()
            if len(p) > 50 and (',' in p or '. ' in p or ': ' in p):
                sub = [s.strip().strip(',.:;') for s in re.split(r'[,.]\s+(?=[A-Za-z])|:\s+(?=[A-Za-z])', p) if len(s.strip()) > 3]
                if len(sub) > 1:
                    expanded.extend(sub)
                else:
                    expanded.append(p)
            else:
                expanded.append(p)

        for part in expanded:
            part = part.strip().strip('.,;:')
            # Clean leading bullet markers
            part = re.sub(r'^[\u2022\u2023\u25e6\u2219\-\*\>\u27a2\u27a4\u25b6\u25ba\u25cf\u25aa\u25ab\uf0a7\uf0d8\u2794\u279c\u27a1\u27a7\u27a8\u27a9\u27aa\u27ab\u27ac\u27ad\u27ae\u27af\u27b1\u27b2\u27b3\u27b4\u27b5\u27b6\u27b7\u27b8\u27b9\u27ba\u27bb\u27bc\u27bd\u27be\u27bf\s]+', '', part).strip()
            if len(part) < 2: continue
            # Reject junk tokens
            if re.match(r'^(?:total\s*[:\-]?\s*\d+|\d+\s*(?:hrs?|hours?|periods?)|total\b|\d+$)', part, re.I):
                continue
            if re.match(r'^(?:unit|module|part|chapter|section)\s*[-–—:.\s]*\s*(?:[ivxlcdm]+|\d+)?$', part, re.I):
                continue
            if re.match(r'^(?:course\s*outcomes?|co\s*[-/]?\s*po|text\s*books?|reference\s*books?|references?|syllabus)\b', part, re.I):
                continue

            pb = detect_printed_bloom(part)
            if pb and pb[0]:
                bloom, src = pb
                # Strip only explicit annotation markers; preserve topic text word-for-word (Rule 2)
                part = re.sub(r'\(?K[1-6]\)?|\b(?:BT|BL|L)[1-6]\b', '', part).strip()
                part = re.sub(r'[\(\[]\s*(?:R|U|Ap|An|Ev|Cr|E|C)\s*[\)\]]', '', part, flags=re.I).strip()
            else:
                bloom, src = infer_bloom(part), "inferred"
            if len(part) < 2: continue
            topics.append({
                "id":           f"u{unit_num}t{len(topics)+1}",
                "text":         part,
                "bloom":        bloom,
                "bloom_source": src,
            })
        return topics

    # ── Course Outcomes ──────────────────────────────────────────────
    def extract_course_outcomes(self) -> List[Dict]:
        section = self._co_section(self.text)
        if not section:
            self.not_extracted.append("course_outcomes — CO section not detected")
            return []

        outcomes = []
        pat = re.compile(
            r'((?:CO|CLO|LO)\s*[-.]?\s*0*\d{1,2}|C\d{3,4}\.\d{1,2})\s*[:\-.]?\s*(.+?)(?=(?:CO|CLO|LO)\s*[-.]?\s*0*\d{1,2}|C\d{3,4}\.\d{1,2}|$)',
            re.I | re.DOTALL
        )
        for m in pat.finditer(section):
            co_id   = normalize_id(m.group(1))
            raw_text = m.group(2).strip()
            item = self._clean_outcome_item(co_id, raw_text)
            if item: outcomes.append(item)

        if not outcomes:
            # Fallback: Numbered list 1. ... 2. ... under Course Outcomes
            num_pat = re.compile(r'(?:^|\n)\s*(\d+)[\.\)]\s+([^\n]+(?:\n(?!\s*\d+[\.\)]\s+)[^\n]+)*)')
            for m in num_pat.finditer(section):
                num_idx = int(m.group(1))
                co_id = f"CO{num_idx}"
                raw_text = m.group(2).strip()
                item = self._clean_outcome_item(co_id, raw_text)
                if item: outcomes.append(item)

        if not outcomes:
            self.not_extracted.append("course_outcomes — CO items could not be parsed from section")
        return outcomes

    def _clean_outcome_item(self, co_id: str, raw_text: str) -> Optional[Dict]:
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        # Filter standalone numbers (page numbers/furniture like 223)
        lines = [l for l in lines if not re.fullmatch(r'\d{1,4}', l)]
        if not lines: return None

        bloom = None
        src = "inferred"
        last_line = lines[-1].strip(' .')
        for bw in ["remember","understand","apply","analyse","analyze","evaluate","create"]:
            if last_line.lower() == bw:
                bloom = "analyse" if bw == "analyze" else bw
                src = "printed"
                lines = lines[:-1]
                break
        if not bloom and lines:
            last_line = lines[-1].strip(' .')
            m_bt = re.search(r'\(?(K[1-6]|BT[1-6]|L[1-6])\)?', last_line, re.I)
            if m_bt:
                k_map = {'1':"remember",'2':"understand",'3':"apply",'4':"analyse",'5':"evaluate",'6':"create"}
                digit = re.search(r'\d', m_bt.group(0)).group(0)
                bloom = k_map.get(digit, "understand")
                src = "printed"
                lines = lines[:-1]

        co_text = ' '.join(lines)
        co_text = re.sub(r'\s+', ' ', co_text).strip().rstrip('.,;')
        if len(co_text) < 5: return None

        if not bloom:
            pb = detect_printed_bloom(co_text)
            if pb:
                bloom, src = pb
            else:
                bloom, src = infer_bloom(co_text), "inferred"

        return {
            "id":           co_id,
            "text":         co_text,
            "bloom":        bloom,
            "bloom_source": src
        }

    def _co_section(self, text: str) -> str:
        patterns = [
            r'(?i)(?:Course\s+(?:Learning\s+)?Outcomes?|Expected\s+Outcomes?)[^\n]*\n(.*?)'
            r'(?=\n\s*(?:Programme|Program|CO\s*[-/]?\s*PO|MAPPING|SYLLABUS|UNIT|Text\s*Books?|Reference|\Z))',
            r'(?i)(?:COs?\s*[:\-][^\n]*)\n(.*?)(?=\n\s*(?:Programme|Program|CO\s*[-/]?\s*PO|MAPPING|SYLLABUS|UNIT|Text|Reference|\Z))',
            # Fallback: look for "Learning Outcomes" or "Objectives" sections
            r'(?i)(?:Learning\s+Outcomes?|Course\s+Objectives?)[^\n]*\n(.*?)'
            r'(?=\n\s*(?:Programme|Program|CO\s*[-/]?\s*PO|MAPPING|SYLLABUS|UNIT|Text|Reference|\Z))',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL)
            if m: return m.group(1)
        # Fallback hits: only take CO occurrences BEFORE any matrix, mapping, or syllabus header
        m_map = re.search(r'(?i)\b(?:MAPPING|CO\s*[-/]?\s*PO|SYLLABUS)\b', text)
        search_region = text[:m_map.start()] if m_map else text
        hits = list(RE_CO.finditer(search_region))
        if len(hits) >= 2:
            s = max(0, hits[0].start() - 60)
            e = min(len(search_region), hits[-1].end() + 400)
            return search_region[s:e]
        return ""

    # ── Programme Outcomes ───────────────────────────────────────────
    def extract_programme_outcomes(self) -> List[Dict]:
        outcomes = self._extract_po_from_text(self.text)
        if not outcomes:
            full = self.reader.full_text()
            outcomes = self._extract_po_from_text(full)

        # Also extract PSOs (Programme Specific Outcomes) if present
        psos = self._extract_pso_from_text(self.text)
        if not psos:
            psos = self._extract_pso_from_text(self.reader.full_text())

        if not outcomes and not psos:
            self.not_extracted.append(
                "programme_outcomes — PO section not found in document"
            )
            return []

        return outcomes + psos

    def _extract_po_from_text(self, text: str) -> List[Dict]:
        section = self._po_section(text)
        if not section: return []

        outcomes = []
        pat = re.compile(
            r'((?:PO|PLO|PEO)\s*[-.]?\s*0*\d{1,2})\s*[:\-]?\s*(.+?)(?=(?:PO|PLO|PEO)\s*[-.]?\s*0*\d{1,2}|PSO|$)',
            re.I | re.DOTALL
        )
        for m in pat.finditer(section):
            po_id   = normalize_id(m.group(1))
            po_text = m.group(2).strip()
            lines   = [l.strip() for l in po_text.split('\n') if l.strip()]
            clean   = ' '.join(lines[:3])
            clean   = re.sub(r'\s+', ' ', clean).strip().rstrip('.,;')
            if len(clean) > 20 and sum(c.isalpha() for c in clean) > 15:
                outcomes.append({"id": po_id, "text": clean})

        if not outcomes:
            num_pat = re.compile(r'(?:^|\n)\s*(\d+)[\.\)]\s+([^\n]+(?:\n(?!\s*\d+[\.\)]\s+)[^\n]+)*)')
            for m in num_pat.finditer(section):
                po_id = f"PO{m.group(1)}"
                po_text = m.group(2).strip()
                lines = [l.strip() for l in po_text.split('\n') if l.strip()]
                clean = ' '.join(lines[:3])
                clean = re.sub(r'\s+', ' ', clean).strip().rstrip('.,;')
                if len(clean) > 20 and sum(c.isalpha() for c in clean) > 15:
                    outcomes.append({"id": po_id, "text": clean})

        return outcomes

    def _po_section(self, text: str) -> str:
        patterns = [
            r'(?i)(?:Programme|Program)\s+Outcomes?(?:\s*\([A-Z\s]+\))?\s*[:\-]?\s*\n(.*?)'
            r'(?=\n\s*(?:CO\s*[-/]?\s*PO|Text\s*Books?|Reference|Course\s*Outcomes?|PSO|\Z))',
            r'(?i)Graduate\s+Attributes\s*[:\-]?\s*\n(.*?)'
            r'(?=\n\s*(?:CO\s*[-/]?\s*PO|Text\s*Books?|Reference|\Z))',
            r'(?i)POs?\s*[:\-]\s*\n(.*?)(?=\n\s*(?:[A-Z]{2}|\Z))',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL)
            if m: return m.group(1)
        hits = list(RE_PO.finditer(text))
        if len(hits) >= 3:
            s = max(0, hits[0].start() - 80)
            e = min(len(text), hits[-1].end() + 500)
            return text[s:e]
        return ""

    def _extract_pso_from_text(self, text: str) -> List[Dict]:
        """Extract Programme Specific Outcomes (PSOs) if present."""
        section = ""
        m = re.search(
            r'(?i)(?:Programme|Program)\s+Specific\s+Outcomes?\s*[:\-]?\s*\n(.*?)'
            r'(?=\n\s*(?:CO\s*[-/]?\s*PO|Text\s*Books?|Reference|Programme\s+Outcomes?|\Z))',
            text, re.DOTALL
        )
        if m:
            section = m.group(1)
        else:
            hits = list(RE_PSO.finditer(text))
            if len(hits) >= 2:
                s = max(0, hits[0].start() - 80)
                e = min(len(text), hits[-1].end() + 400)
                section = text[s:e]
        if not section:
            return []

        outcomes = []
        pat = re.compile(
            r'(PSO\s*[-.]?\s*0*\d{1,2})\s*[:\-]?\s*(.+?)(?=PSO\s*[-.]?\s*0*\d{1,2}|$)',
            re.I | re.DOTALL
        )
        for m in pat.finditer(section):
            pso_id = normalize_id(m.group(1))
            pso_text = m.group(2).strip()
            lines = [l.strip() for l in pso_text.split('\n') if l.strip()]
            clean = ' '.join(lines[:3])
            clean = re.sub(r'\s+', ' ', clean).strip().rstrip('.,;')
            if len(clean) > 15 and sum(c.isalpha() for c in clean) > 10:
                outcomes.append({"id": pso_id, "text": clean})
        return outcomes

    # ── CO-PO Matrix ─────────────────────────────────────────────────
    def extract_matrix(self) -> Dict[str, Dict[str, str]]:
        # Try table first (most reliable)
        for pnum, tbl in self.tables:
            result = self._matrix_from_table(tbl)
            if result: return result

        # Multi-page matrix stitch
        multi = self._stitch_matrix_tables()
        if multi: return multi

        # Text-based
        txt = self._matrix_from_text()
        if txt: return txt

        self.not_extracted.append(
            "co_po_matrix — no matrix table found; if present, it may be in an image or scanned page"
        )
        return {}

    def _matrix_from_table(self, tbl: List[List[str]]) -> Dict:
        if not tbl or len(tbl) < 2: return {}

        # Form 1: Header row has PO identifiers, column 0 has CO identifiers
        header_idx = -1
        for i, row in enumerate(tbl):
            po_count = sum(1 for c in row if RE_PO.match(str(c).strip()) or RE_PSO.match(str(c).strip()))
            if po_count >= 2:
                header_idx = i; break
        if header_idx >= 0:
            po_cols: List[Tuple[int, Optional[str]]] = []
            for j, cell in enumerate(tbl[header_idx]):
                cell_s = str(cell).strip()
                pm = RE_PO.match(cell_s) or RE_PSO.match(cell_s)
                if pm:
                    po_cols.append((j, normalize_id(cell_s)))
                else:
                    po_cols.append((j, None))

            matrix = {}
            for row in tbl[header_idx+1:]:
                if not row: continue
                co_key = None
                for c_idx in range(min(3, len(row))):
                    cell_val = str(row[c_idx]).strip()
                    m_co = RE_CO.search(cell_val)
                    if m_co:
                        co_key = normalize_id(m_co.group(0))
                        break
                if not co_key: continue
                matrix[co_key] = {}
                for j, po_key in po_cols:
                    if po_key is None: continue
                    if j < len(row):
                        val = str(row[j]).strip()
                        if val and val not in ('', '-', '–', '—', '0', 'nil', 'Nil', 'N/A', 'n/a'):
                            matrix[co_key][po_key] = val
            matrix = {co: r for co, r in matrix.items() if r}
            if matrix: return matrix

        # Form 2: Inverted table: Header row has CO identifiers, column 0 has PO identifiers
        co_header_idx = -1
        for i, row in enumerate(tbl):
            co_count = sum(1 for c in row if RE_CO.search(str(c).strip()))
            if co_count >= 2:
                co_header_idx = i; break
        if co_header_idx >= 0:
            co_cols: List[Tuple[int, Optional[str]]] = []
            for j, cell in enumerate(tbl[co_header_idx]):
                cell_s = str(cell).strip()
                cm = RE_CO.search(cell_s)
                if cm:
                    co_cols.append((j, normalize_id(cm.group(0))))
                else:
                    co_cols.append((j, None))

            matrix = defaultdict(dict)
            for row in tbl[co_header_idx+1:]:
                if not row: continue
                po_key = None
                for c_idx in range(min(3, len(row))):
                    cell_val = str(row[c_idx]).strip()
                    m_po = RE_PO.search(cell_val) or RE_PSO.search(cell_val)
                    if m_po:
                        po_key = normalize_id(m_po.group(0))
                        break
                if not po_key: continue
                for j, co_key in co_cols:
                    if co_key is None: continue
                    if j < len(row):
                        val = str(row[j]).strip()
                        if val and val not in ('', '-', '–', '—', '0', 'nil', 'Nil', 'N/A', 'n/a'):
                            matrix[co_key][po_key] = val
            cleaned = {co: dict(r) for co, r in matrix.items() if r}
            if cleaned: return cleaned

        return {}

    def _stitch_matrix_tables(self) -> Dict:
        """Stitch multi-page matrix by aligning CO row keys."""
        all_pages = [(pn, tbl) for pn, tbl in self.tables]
        if len(all_pages) < 2: return {}
        combined: Dict[str, Dict[str, str]] = {}
        for _, tbl in all_pages:
            part = self._matrix_from_table(tbl)
            for co, row in part.items():
                if co not in combined: combined[co] = {}
                combined[co].update(row)
        combined = {co: r for co, r in combined.items() if r}
        return combined if len(combined) > 0 else {}

    def _matrix_from_text(self) -> Dict:
        matrix = {}
        # "CO1 : PO1-S PO2-M PO3-L" style
        for m in re.finditer(r'(CO\s*\d{1,2})\s*[:\-]\s*([^\n]+)', self.text, re.I):
            co_key = normalize_id(m.group(1))
            rest   = m.group(2)
            pairs  = re.findall(r'(PO\s*\d{1,2})\s*[-:]\s*([SMLHsmlh1-6])', rest, re.I)
            if pairs:
                matrix[co_key] = {}
                for po, s in pairs:
                    matrix[co_key][normalize_id(po)] = s.upper()
        return matrix

    # ── Books ────────────────────────────────────────────────────────
    def extract_books(self) -> List[Dict]:
        text   = self.text
        books  = []
        tb_m   = RE_TEXTBOOK.search(text)
        rb_m   = RE_REFBOOK.search(text)

        sections = []
        if tb_m:
            end = rb_m.start() if rb_m and rb_m.start() > tb_m.end() else len(text)
            sections.append(("text", text[tb_m.end():end]))
        if rb_m:
            # Bound reference section: stop at next course/section markers
            rb_text = text[rb_m.end():]
            rb_end = re.search(
                r'(?im)^\s*(?:UNIT|MODULE|CHAPTER|PART|SECTION|CO\s*[-/]?\s*PO|'
                r'Mapping|Articulation|Programme|Course\s*Designers?|Faculty|'
                r'(?:Course|Subject)\s*Code\s*[:\-]|[A-Z0-9\.\-]{3,15}\s*\n\s*[A-Z][A-Z\s]{4,}\s*\nCategory)',
                rb_text
            )
            if rb_end:
                rb_text = rb_text[:rb_end.start()]
            sections.append(("reference", rb_text))

        if not sections:
            m = re.search(r'(?im)^(?:books?|bibliography|readings?)\s*[:\-]?\s*$', text)
            if m: sections.append(("text", text[m.end():]))

        for kind, sec in sections:
            books.extend(self._parse_book_section(sec, kind))

        if not books:
            self.not_extracted.append(
                "books — text books / reference books section not found"
            )
        return books

    def _parse_book_section(self, text: str, kind: str) -> List[Dict]:
        books, current = [], []
        for line in text.split('\n'):
            line = line.strip()
            if not line: continue
            if re.fullmatch(r'\d{3,4}', line): continue
            # Stop at non-book sections
            if re.match(r'(?i)^(?:UNIT|MODULE|CHAPTER|PART|SECTION|CO\s*[-/]?\s*PO|CO\d|PO\d|Mapping|Articulation|Programme|Course\s*Designers?|Faculty|Email|S\.?\s*No|Prepared\s+by|Verified\s+by|Approved)', line):
                break
            # Stop at next course header pattern
            if re.match(r'^[A-Z0-9\.\-]{3,15}\s*$', line) and re.search(r'[A-Z]', line) and re.search(r'\d', line):
                from sylex import is_valid_course_code
                if is_valid_course_code(line.strip()):
                    break
            is_num_start = bool(re.match(r'^\d{1,2}[\.\)]?$', line) or (RE_BOOK_NUM.match(line) and re.match(r'^\d{1,2}[\.\)]?\s+[A-Z]', line)))
            if is_num_start and current:
                if any(len(re.sub(r'^\s*(\d+|[ivxlc]+)[\.\)]?\s*', '', l).strip()) > 3 for l in current):
                    b = self._parse_book_entry('\n'.join(current), kind)
                    if b: books.append(b)
                current = [line]
            else:
                current.append(line)
        if current:
            b = self._parse_book_entry('\n'.join(current), kind)
            if b: books.append(b)
        return books

    def _parse_book_entry(self, text: str, kind: str) -> Optional[Dict]:
        lines = [l.strip() for l in text.splitlines() if l.strip() and not re.fullmatch(r'\d{1,4}', l.strip())]
        text = ' '.join(lines)
        text = re.sub(r'^\s*(?:(\d+|[ivxlc]+)[\.\)]?\s*)+', '', text).strip()
        if len(text) < 5: return None

        year_m = RE_YEAR.search(text)
        year   = int(year_m.group(0)) if year_m else None

        ed_m    = RE_EDITION.search(text)
        edition = ed_m.group(1).strip() if ed_m else None

        title, author, publisher = self._bib_slots(text)

        return {
            "kind":      kind,
            "title":     title or "",
            "author":    author or "",
            "publisher": publisher if publisher else None,
            "edition":   edition,
            "year":      year,
        }

    def _bib_slots(self, text: str) -> Tuple[str, str, Optional[str]]:
        clean = RE_YEAR.sub('', text)
        clean = RE_EDITION.sub('', clean)
        # Strip ISBN strings so they don't pollute publisher or title
        clean = re.sub(r'(?i)\bISBN(?:-1[03])?\s*[:\-]?\s*[\d\-X]{9,17}\b', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip().strip(',.')

        known_pubs = [
            'McGraw-Hill', 'McGraw Hill', 'Tata McGraw-Hill', 'Pearson', 'Pearson Education',
            'Cengage', 'Wiley', 'John Wiley', 'Prentice Hall', 'Prentice', 'Oxford University Press',
            'Oxford', 'Cambridge University Press', 'Cambridge', 'Springer', 'O\'Reilly',
            'MIT Press', 'PHI', 'Elsevier', 'Morgan Kaufmann', 'CRC Press', 'Academic Press',
            'Addison-Wesley', 'S. Chand', 'Laxmi Publications', 'Laxmi', 'Charotar', 'Cognitive Class',
            'Sage', 'Vikas', 'Dhanpat Rai', 'Khanna', 'Orient BlackSwan', 'Bpb'
        ]

        # 1. Quoted title check: "Title" or “Title” or ”Title”
        q_m = re.search(r'[\u201c\u201d\"\'`‘]([^\u201c\u201d\"\'`’]{4,140})[\u201c\u201d\"\'`’]', clean)
        if q_m:
            title = q_m.group(1).strip(' ,-–;:\u201c\u201d"\'')
            author = clean[:q_m.start()].strip(' ,-–;:\u201c\u201d"\'')
            rest = clean[q_m.end():].strip(' ,-–;:\u201c\u201d"\'')
            pub = None
            for kp in known_pubs:
                if re.search(r'\b' + re.escape(kp), rest, re.I):
                    pub = kp
                    break
            if not pub and rest:
                rest_clean = re.sub(r'[\(\)\[\]]', '', rest).strip(' ,-–;:')
                parts = [p.strip() for p in rest_clean.split(';') if p.strip()]
                if parts:
                    cand = parts[0].split(',')[0].strip()
                    if 2 < len(cand) < 40 and not re.search(r'(?i)\bedition\b', cand):
                        pub = cand
            return title, author, pub

        # 2. Check for known publisher in text
        for kp in known_pubs:
            m_kp = re.search(r'\b' + re.escape(kp) + r'\b', clean, re.I)
            if m_kp:
                pub = kp
                before_pub = clean[:m_kp.start()].strip(' ,-–;:')
                by_s = re.split(r'\s+[Bb]y\s+', before_pub, maxsplit=1)
                if len(by_s) == 2:
                    return by_s[0].strip('"\''), by_s[1].strip(' ,-–;:'), pub
                chunks = [c.strip() for c in re.split(r'[,.]\s+', before_pub) if c.strip()]
                if len(chunks) >= 2:
                    return chunks[-1].strip('"\''), ', '.join(chunks[:-1]), pub
                elif len(chunks) == 1:
                    return chunks[0].strip('"\''), "", pub

        # 3. Split by " by "
        by_s = re.split(r'\s+[Bb]y\s+', clean, maxsplit=1)
        if len(by_s) == 2:
            return by_s[0].strip('"\''), by_s[1].strip(' ,-–;:'), None

        # 4. Comma split: author, title, publisher
        parts = [p.strip() for p in clean.split(',') if p.strip()]
        if len(parts) >= 3:
            return parts[1].strip('"\''), parts[0], parts[-1]
        if len(parts) == 2:
            return parts[1].strip('"\''), parts[0], None

        # 5. Period split fallback: author. title. publisher.
        period_parts = [p.strip() for p in re.split(r'\.\s+', clean) if p.strip()]
        if len(period_parts) >= 3:
            return period_parts[1].strip('"\''), period_parts[0], period_parts[2]
        if len(period_parts) == 2:
            return period_parts[1].strip('"\''), period_parts[0], None

        return clean[:120], "", None

# ══════════════════════════════════════════════════════════════════════
#  TASK RUNNERS
# ══════════════════════════════════════════════════════════════════════

def _load_hints(path: Optional[str]) -> Dict:
    if not path: return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Could not load hints: {e}", file=sys.stderr)
        return {}

_GLOBAL_COURSE_DETECTOR_CACHE: Dict[str, List['CourseCandidate']] = {}

def _get_doc_cache_key(reader: 'PDFReader', pdf_path: str = "") -> str:
    n_pages = reader.page_count
    first_text = reader.pages[0].text[:300] if n_pages > 0 else ""
    return f"{n_pages}_{hash(first_text)}_{Path(pdf_path).name}"

def run_task1(pdf_path: str, hints: Dict = None) -> Dict:
    hints    = hints or {}
    reader   = PDFReader(pdf_path)
    grammar  = DocumentGrammar(reader)
    doc_key  = _get_doc_cache_key(reader, pdf_path)
    if doc_key in _GLOBAL_COURSE_DETECTOR_CACHE:
        cands = _GLOBAL_COURSE_DETECTOR_CACHE[doc_key]
    else:
        detector = CourseDetector(reader, grammar, hints)
        cands    = detector.detect()
        _GLOBAL_COURSE_DETECTOR_CACHE[doc_key] = cands

    courses = [{"code": c.code, "title": c.title, "page": c.page}
               for c in cands]

    return {
        "document":     Path(pdf_path).name,
        "course_count": len(courses),
        "courses":      courses,
    }

def run_task2(pdf_path: str, course_id: str, hints: Dict = None,
              debug: bool = False) -> Dict:
    hints    = hints or {}
    reader   = PDFReader(pdf_path)
    grammar  = DocumentGrammar(reader)
    doc_key  = _get_doc_cache_key(reader, pdf_path)

    # Ultra-Fast Path 1: If hints contains catalog courses with page numbers, construct candidates directly!
    cands = []
    if hints and "courses" in hints and isinstance(hints["courses"], list) and len(hints["courses"]) > 0:
        for c in hints["courses"]:
            if isinstance(c, dict):
                c_code = c.get("code") or ""
                c_title = c.get("title") or ""
                try:
                    c_page = int(c.get("page") or 1)
                except Exception:
                    c_page = 1
                cands.append(CourseCandidate(c_code, c_title, c_page, 0.99, ["catalog-hint"]))
        cands.sort(key=lambda x: x.page)
    elif doc_key in _GLOBAL_COURSE_DETECTOR_CACHE:
        cands = _GLOBAL_COURSE_DETECTOR_CACHE[doc_key]

    detector = CourseDetector(reader, grammar, hints)

    # Find target using codes_match and title
    t_target = norm_title(course_id)
    def matches_target(c):
        if codes_match(c.code, course_id): return True
        if any(codes_match(a, course_id) for a in getattr(c, 'aliases', [])): return True
        if t_target and (t_target == norm_title(c.title) or t_target in norm_title(c.title) or norm_title(c.title) in t_target):
            return True
        if course_id.upper() in c.title.upper(): return True
        return False

    target = next((c for c in cands if matches_target(c)), None) if cands else None

    # Ultra-Fast Path 2: Check target candidate in hints dictionary directly
    if target is None and isinstance(hints.get("target"), dict):
        h_t = hints["target"]
        t_page = h_t.get("page")
        if t_page:
            try:
                target = CourseCandidate(h_t.get("code") or course_id, h_t.get("title") or "", int(t_page), 0.98, ["hint-target"])
            except: pass

    # Fallback to document detection or cache if target still not found
    if target is None:
        if doc_key in _GLOBAL_COURSE_DETECTOR_CACHE:
            cands = _GLOBAL_COURSE_DETECTOR_CACHE[doc_key]
        else:
            cands = detector.detect()
            _GLOBAL_COURSE_DETECTOR_CACHE[doc_key] = cands
        target = next((c for c in cands if matches_target(c)), None)
    if target is None:
        return {
            "course": None,
            "units": [], "course_outcomes": [],
            "programme_outcomes": [], "co_po_matrix": {},
            "books": [],
            "not_extracted": [f"requested course '{course_id}' not found in document"],
        }

    sp, ep = detector.find_boundary(cands, target.code, target.title, target_obj=target)
    hints_with_code = dict(hints or {})
    hints_with_code["course_code"] = target.code
    ext    = DeepExtractor(reader, grammar, sp, ep, hints_with_code)

    meta   = ext.extract_front_matter(target.code, target.title)
    units  = ext.extract_units()
    cos    = ext.extract_course_outcomes()
    pos    = ext.extract_programme_outcomes()
    matrix = ext.extract_matrix()
    books  = ext.extract_books()

    result = {
        "course":             meta,
        "units":              units,
        "course_outcomes":    cos,
        "programme_outcomes": pos,
        "co_po_matrix":       matrix,
        "books":              books,
        "not_extracted":      sorted(set(ext.not_extracted)),
    }

    if debug:
        result["_debug"] = {
            "sha256":       reader._sha,
            "page_range":   [sp, ep],
            "scanned_pages":ext.scanned,
            "grammar": {
                "unit_keyword":        grammar.unit_keyword,
                "dominant_separator":  grammar.dominant_separator,
                "has_toc":             grammar.has_toc,
                "matrix_symbols":      list(grammar.matrix_symbols),
            },
            "course_signals": target.signals,
        }

    return result

# ══════════════════════════════════════════════════════════════════════
#  CURRICULUM AUDIT & NBA ACCREDITATION ANALYTICS ENGINE
# ══════════════════════════════════════════════════════════════════════

def calculate_curriculum_audit(d2: Dict) -> Dict:
    """Compute comprehensive NBA/OBE accreditation audit, Bloom HOTS/LOTS ratios, and credit integrity."""
    if not isinstance(d2, dict) or not d2.get("course"):
        return {
            "status": "no_data",
            "message": "No course data available for audit."
        }

    c = d2.get("course") or {}
    units = d2.get("units") or []
    cos = d2.get("course_outcomes") or []
    pos = d2.get("programme_outcomes") or []
    matrix = d2.get("co_po_matrix") or {}
    books = d2.get("books") or []

    # 1. Contact Hour & Credit Integrity
    total_unit_hours = sum((u.get("hours") or 0) for u in units)
    lec = c.get("lecture")
    tut = c.get("tutorial") or 0
    prac = c.get("practical") or 0
    credits = c.get("credits")
    expected_contact_hours = (lec * 15) if (lec is not None and lec > 0) else None

    if total_unit_hours > 0 and expected_contact_hours:
        if abs(total_unit_hours - expected_contact_hours) <= 5:
            hour_status = "VERIFIED_ACCURATE"
            hour_msg = f"Unit contact hours ({total_unit_hours} hrs) perfectly align with {credits} credits ({lec}L x 15 weeks)."
        else:
            hour_status = "DISCREPANCY_FLAGGED"
            hour_msg = f"Unit contact hours ({total_unit_hours} hrs) differ from expected {expected_contact_hours} hrs ({lec}L x 15 weeks)."
    elif total_unit_hours > 0:
        hour_status = "DOCUMENTED"
        hour_msg = f"Total contact hours allocated: {total_unit_hours} hrs across {len(units)} units."
    else:
        hour_status = "UNSPECIFIED"
        hour_msg = "Unit hours not explicitly printed in syllabus."

    # 2. Bloom Cognitive Progression & HOTS Analysis
    all_blooms = []
    for u in units:
        for t in u.get("topics", []):
            all_blooms.append(str(t.get("bloom") or "understand").lower())
    for co in cos:
        all_blooms.append(str(co.get("bloom") or "understand").lower())

    bloom_counts = Counter(all_blooms)
    total_blooms = len(all_blooms) or 1
    k1 = bloom_counts.get("remember", 0)
    k2 = bloom_counts.get("understand", 0)
    k3 = bloom_counts.get("apply", 0)
    k4 = bloom_counts.get("analyse", 0)
    k5 = bloom_counts.get("evaluate", 0)
    k6 = bloom_counts.get("create", 0)

    lots = k1 + k2
    hots = k3 + k4 + k5 + k6
    hots_pct = round((hots / total_blooms) * 100, 1)

    # Washington Accord / NBA threshold for engineering degree courses: >= 50% HOTS
    if hots_pct >= 50.0:
        nba_bloom_status = "COMPLIANT_HIGH_RIGOR"
        nba_bloom_msg = f"Higher-Order Cognitive Rigor is {hots_pct}% (>=50% Washington Accord / NBA Benchmark)."
    else:
        nba_bloom_status = "LOTS_HEAVY_REVIEW_NEEDED"
        nba_bloom_msg = f"Lower-Order Thinking ({lots} items) dominates. Elevate {max(0.0, 50.0 - hots_pct):.1f}% more topics to Apply/Analyse."

    # 3. CO-PO Matrix Attainment & Coverage
    all_po_ids = [po.get("id") for po in pos if po.get("id")]
    if not all_po_ids:
        all_po_ids = [f"PO{i}" for i in range(1, 13)]

    mapped_pos = set()
    mapped_cell_count = 0
    strong_count = 0
    medium_count = 0
    weak_count = 0

    for co_id, row in matrix.items():
        if isinstance(row, dict):
            for po_id, val in row.items():
                s_val = str(val).strip().upper()
                if s_val:
                    mapped_pos.add(po_id)
                    mapped_cell_count += 1
                    if s_val in ("3", "S", "H", "HIGH", "STRONG"):
                        strong_count += 1
                    elif s_val in ("2", "M", "MED", "MEDIUM"):
                        medium_count += 1
                    elif s_val in ("1", "L", "LOW", "WEAK"):
                        weak_count += 1

    total_possible_cells = max(1, len(cos) * len(all_po_ids))
    density_pct = round((mapped_cell_count / total_possible_cells) * 100, 1)
    unmapped_pos = sorted(list(set(all_po_ids) - mapped_pos))

    # 4. Overall Curriculum Health Score (0 - 100)
    score = 100
    if not units: score -= 30
    if not cos: score -= 20
    if not matrix: score -= 20
    if not books: score -= 15
    if hots_pct < 40: score -= 10
    score = max(0, min(100, score))

    return {
        "status": "ok",
        "curriculum_score": score,
        "course_identity": f"{c.get('code', 'N/A')} - {c.get('title', 'Course')}",
        "hour_integrity": {
            "status": hour_status,
            "message": hour_msg,
            "total_unit_hours": total_unit_hours,
            "expected_contact_hours": expected_contact_hours,
            "credits": credits,
            "l_t_p": f"{lec or 0}-{tut or 0}-{prac or 0}"
        },
        "bloom_analytics": {
            "distribution": {
                "remember": k1, "understand": k2, "apply": k3,
                "analyse": k4, "evaluate": k5, "create": k6
            },
            "lots_count": lots,
            "hots_count": hots,
            "hots_percentage": hots_pct,
            "nba_status": nba_bloom_status,
            "nba_message": nba_bloom_msg
        },
        "co_po_coverage": {
            "total_mapped_cells": mapped_cell_count,
            "matrix_density_pct": density_pct,
            "mapped_pos": sorted(list(mapped_pos)),
            "unmapped_pos": unmapped_pos,
            "strength_distribution": {
                "strong": strong_count,
                "medium": medium_count,
                "weak": weak_count
            }
        },
        "structure_summary": {
            "unit_count": len(units),
            "topic_count": sum(len(u.get("topics", [])) for u in units),
            "co_count": len(cos),
            "po_count": len(pos),
            "book_count": len(books)
        }
    }

# ══════════════════════════════════════════════════════════════════════
#  CLI OUTPUT NORMALIZATION
# ══════════════════════════════════════════════════════════════════════

def _normalize_cli_output(result: Dict) -> Dict:
    """Ensure CLI output strictly conforms to the problem statement schema.
    Guarantees: bloom ∈ {remember,understand,apply,analyse,evaluate,create},
    bloom_source ∈ {printed,inferred}, no None values in bloom fields."""
    valid_blooms = {"remember", "understand", "apply", "analyse", "evaluate", "create"}

    def _fix(obj):
        if isinstance(obj, dict):
            if "bloom" in obj:
                b = str(obj["bloom"] or "understand").lower().strip()
                if b == "analyze": b = "analyse"
                if b not in valid_blooms: b = "understand"
                obj["bloom"] = b
            if "bloom_source" in obj:
                s = str(obj["bloom_source"] or "inferred").lower().strip()
                if s != "printed": s = "inferred"
                obj["bloom_source"] = s
            for v in obj.values():
                _fix(v)
        elif isinstance(obj, list):
            for item in obj:
                _fix(item)

    _fix(result)
    return result

# ══════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="SYLEX v3.0 — Syllabus Extraction Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sylex.py --pdf syllabus.pdf
  python sylex.py --pdf syllabus.pdf --course CS23301
  python sylex.py --pdf syllabus.pdf --hints hints.json
  python sylex.py --pdf syllabus.pdf --out task1.json --debug

Exit codes:  0=ok  2=pdf missing  3=course not found  4=error
"""
    )
    parser.add_argument('--pdf',    required=True)
    parser.add_argument('--course', default=None)
    parser.add_argument('--out',    default=None)
    parser.add_argument('--hints',  default=None,
                        help='JSON hints file to override extraction')
    parser.add_argument('--debug',  action='store_true')
    args = parser.parse_args()

    hints = _load_hints(args.hints)

    try:
        if args.course:
            result    = run_task2(args.pdf, args.course, hints, args.debug)
            exit_code = 3 if result.get("course") is None else 0
        else:
            result    = run_task1(args.pdf, hints)
            exit_code = 0

        # Normalize output for strict schema compliance (bloom values, spelling)
        result = _normalize_cli_output(result)

        output = json.dumps(result, ensure_ascii=False, indent=2, default=str)

        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f: f.write(output)
        else:
            print(output)

        sys.exit(exit_code)

    except SystemExit: raise
    except Exception as e:
        if args.debug:
            import traceback; traceback.print_exc(file=sys.stderr)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)

if __name__ == '__main__':
    main()
