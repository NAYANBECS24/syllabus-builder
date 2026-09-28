// SYLEX-ΩX v2.2 — Demo Data matching exact JSON schemas

const DEMO_TASK1 = {
  document: "SampleCollege-R2023-CSE.pdf",
  course_count: 12,
  courses: [
    { code: "CS23301", title: "DATA STRUCTURES AND ALGORITHMS", page: 12 },
    { code: "CS23302", title: "OBJECT ORIENTED PROGRAMMING", page: 24 },
    { code: "MA23101", title: "ENGINEERING MATHEMATICS I", page: 36 },
    { code: "CS23303", title: "COMPUTER ORGANIZATION AND ARCHITECTURE", page: 48 },
    { code: "CS23304", title: "OPERATING SYSTEMS", page: 60 },
    { code: "CS23305", title: "DATABASE MANAGEMENT SYSTEMS", page: 72 },
    { code: "EC23201", title: "DIGITAL ELECTRONICS", page: 84 },
    { code: "CS23401", title: "COMPUTER NETWORKS", page: 96 },
    { code: "CS23402", title: "COMPILER DESIGN", page: 108 },
    { code: "CS23403", title: "MACHINE LEARNING", page: 120 },
    { code: "CS23404", title: "INFORMATION SECURITY", page: 132 },
    { code: "",         title: "PROFESSIONAL ETHICS AND HUMAN VALUES", page: 144 }
  ]
};

const DEMO_TASK2 = {
  course: {
    code: "CS23301",
    title: "DATA STRUCTURES AND ALGORITHMS",
    category: "PC",
    lecture: 3,
    tutorial: 1,
    practical: 0,
    credits: 4,
    pages: [12, 13, 14, 15]
  },
  units: [
    {
      number: 1,
      title: "LINEAR DATA STRUCTURES",
      hours: 9,
      text: "Arrays - linked lists - singly, doubly and circular linked lists - stacks - queues - dequeues - priority queues - applications.",
      topics: [
        { id: "u1t1", text: "Arrays", bloom: "remember", bloom_source: "inferred" },
        { id: "u1t2", text: "linked lists", bloom: "understand", bloom_source: "inferred" },
        { id: "u1t3", text: "singly, doubly and circular linked lists", bloom: "understand", bloom_source: "inferred" },
        { id: "u1t4", text: "stacks", bloom: "apply", bloom_source: "inferred" },
        { id: "u1t5", text: "queues", bloom: "apply", bloom_source: "inferred" },
        { id: "u1t6", text: "dequeues", bloom: "apply", bloom_source: "inferred" },
        { id: "u1t7", text: "priority queues", bloom: "apply", bloom_source: "inferred" },
        { id: "u1t8", text: "applications", bloom: "apply", bloom_source: "inferred" }
      ]
    },
    {
      number: 2,
      title: "TREES",
      hours: 9,
      text: "Trees - binary trees - binary search trees - AVL trees - B-trees - red-black trees - heap - applications.",
      topics: [
        { id: "u2t1", text: "Trees", bloom: "understand", bloom_source: "inferred" },
        { id: "u2t2", text: "binary trees", bloom: "understand", bloom_source: "inferred" },
        { id: "u2t3", text: "binary search trees", bloom: "apply", bloom_source: "inferred" },
        { id: "u2t4", text: "AVL trees", bloom: "analyse", bloom_source: "inferred" },
        { id: "u2t5", text: "B-trees", bloom: "analyse", bloom_source: "inferred" },
        { id: "u2t6", text: "red-black trees", bloom: "analyse", bloom_source: "inferred" },
        { id: "u2t7", text: "heap", bloom: "apply", bloom_source: "inferred" },
        { id: "u2t8", text: "applications", bloom: "apply", bloom_source: "inferred" }
      ]
    },
    {
      number: 3,
      title: "GRAPHS",
      hours: 9,
      text: "Graph representation - BFS - DFS - spanning trees - Prim's algorithm - Kruskal's algorithm - shortest paths - Dijkstra's algorithm - Floyd-Warshall algorithm.",
      topics: [
        { id: "u3t1", text: "Graph representation", bloom: "understand", bloom_source: "inferred" },
        { id: "u3t2", text: "BFS", bloom: "apply", bloom_source: "inferred" },
        { id: "u3t3", text: "DFS", bloom: "apply", bloom_source: "inferred" },
        { id: "u3t4", text: "spanning trees", bloom: "understand", bloom_source: "inferred" },
        { id: "u3t5", text: "Prim's algorithm", bloom: "apply", bloom_source: "printed" },
        { id: "u3t6", text: "Kruskal's algorithm", bloom: "apply", bloom_source: "printed" },
        { id: "u3t7", text: "shortest paths", bloom: "analyse", bloom_source: "inferred" },
        { id: "u3t8", text: "Dijkstra's algorithm", bloom: "apply", bloom_source: "printed" },
        { id: "u3t9", text: "Floyd-Warshall algorithm", bloom: "analyse", bloom_source: "printed" }
      ]
    },
    {
      number: 4,
      title: "SORTING AND SEARCHING",
      hours: 9,
      text: "Insertion sort - selection sort - bubble sort - merge sort - quick sort - heap sort - radix sort - hashing techniques - collision resolution.",
      topics: [
        { id: "u4t1", text: "Insertion sort", bloom: "remember", bloom_source: "inferred" },
        { id: "u4t2", text: "selection sort", bloom: "remember", bloom_source: "inferred" },
        { id: "u4t3", text: "bubble sort", bloom: "remember", bloom_source: "inferred" },
        { id: "u4t4", text: "merge sort", bloom: "apply", bloom_source: "inferred" },
        { id: "u4t5", text: "quick sort", bloom: "apply", bloom_source: "inferred" },
        { id: "u4t6", text: "heap sort", bloom: "apply", bloom_source: "inferred" },
        { id: "u4t7", text: "radix sort", bloom: "apply", bloom_source: "inferred" },
        { id: "u4t8", text: "hashing techniques", bloom: "understand", bloom_source: "inferred" },
        { id: "u4t9", text: "collision resolution", bloom: "analyse", bloom_source: "inferred" }
      ]
    },
    {
      number: 5,
      title: "ALGORITHM DESIGN AND ANALYSIS",
      hours: 9,
      text: "Algorithm design paradigms - divide and conquer - dynamic programming - greedy algorithms - backtracking - branch and bound - complexity analysis - NP-completeness.",
      topics: [
        { id: "u5t1", text: "Algorithm design paradigms", bloom: "understand", bloom_source: "inferred" },
        { id: "u5t2", text: "divide and conquer", bloom: "apply", bloom_source: "inferred" },
        { id: "u5t3", text: "dynamic programming", bloom: "apply", bloom_source: "inferred" },
        { id: "u5t4", text: "greedy algorithms", bloom: "apply", bloom_source: "inferred" },
        { id: "u5t5", text: "backtracking", bloom: "apply", bloom_source: "inferred" },
        { id: "u5t6", text: "branch and bound", bloom: "analyse", bloom_source: "inferred" },
        { id: "u5t7", text: "complexity analysis", bloom: "evaluate", bloom_source: "inferred" },
        { id: "u5t8", text: "NP-completeness", bloom: "evaluate", bloom_source: "inferred" }
      ]
    }
  ],
  course_outcomes: [
    { id: "CO1", text: "Apply linear data structures to solve computational problems.", bloom: "apply", bloom_source: "printed" },
    { id: "CO2", text: "Analyse tree-based data structures and their time complexity.", bloom: "analyse", bloom_source: "printed" },
    { id: "CO3", text: "Design graph algorithms for real-world network problems.", bloom: "create", bloom_source: "printed" },
    { id: "CO4", text: "Evaluate and compare sorting and searching algorithms.", bloom: "evaluate", bloom_source: "printed" },
    { id: "CO5", text: "Formulate solutions using advanced algorithm design techniques.", bloom: "create", bloom_source: "printed" }
  ],
  programme_outcomes: [
    { id: "PO1", text: "Engineering knowledge: Apply the knowledge of mathematics, science, engineering fundamentals, and an engineering specialization to the solution of complex engineering problems." },
    { id: "PO2", text: "Problem analysis: Identify, formulate, review research literature, and analyse complex engineering problems reaching substantiated conclusions using first principles of mathematics, natural sciences, and engineering sciences." },
    { id: "PO3", text: "Design/development of solutions: Design solutions for complex engineering problems and design system components or processes that meet the specified needs with appropriate consideration for the public health and safety." },
    { id: "PO4", text: "Conduct investigations of complex problems: Use research-based knowledge and research methods including design of experiments, analysis and interpretation of data, and synthesis of the information to provide valid conclusions." },
    { id: "PO5", text: "Modern tool usage: Create, select, and apply appropriate techniques, resources, and modern engineering and IT tools including prediction and modelling to complex engineering activities." },
    { id: "PO6", text: "The engineer and society: Apply reasoning informed by the contextual knowledge to assess societal, health, safety, legal and cultural issues and the consequent responsibilities relevant to the professional engineering practice." }
  ],
  co_po_matrix: {
    CO1: { PO1: "S", PO2: "M", PO3: "L", PO4: "M", PO5: "S" },
    CO2: { PO1: "S", PO2: "S", PO3: "M", PO4: "S", PO5: "M" },
    CO3: { PO1: "M", PO2: "S", PO3: "S", PO4: "M", PO5: "S", PO6: "L" },
    CO4: { PO1: "S", PO2: "S", PO3: "M", PO4: "S" },
    CO5: { PO1: "M", PO2: "M", PO3: "S", PO4: "M", PO5: "S", PO6: "M" }
  },
  books: [
    {
      kind: "text",
      title: "Data Structures and Algorithm Analysis in C",
      author: "Mark Allen Weiss",
      publisher: "Pearson Education",
      edition: "2nd",
      year: 2002
    },
    {
      kind: "text",
      title: "Introduction to Algorithms",
      author: "Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein",
      publisher: "MIT Press",
      edition: "3rd",
      year: 2009
    },
    {
      kind: "reference",
      title: "The Art of Computer Programming, Volume 1: Fundamental Algorithms",
      author: "Donald E. Knuth",
      publisher: "Addison-Wesley",
      edition: "3rd",
      year: 1997
    },
    {
      kind: "reference",
      title: "Algorithm Design",
      author: "Jon Kleinberg, Eva Tardos",
      publisher: "Pearson",
      edition: "1st",
      year: 2005
    },
    {
      kind: "reference",
      title: "Fundamentals of Data Structures in C",
      author: "Ellis Horowitz, Sartaj Sahni, Susan Anderson-Freed",
      publisher: "Universities Press",
      edition: "2nd",
      year: 2008
    }
  ],
  not_extracted: [
    "programme_outcomes — sourced from document-wide PO section (pages 5-6), not course-local"
  ]
};

const PIPELINE_STEPS = [
  { id: "triage",     label: "Document Triage",        icon: "🔍", desc: "Detecting native/scan/mixed modality, validating PDF integrity, computing SHA-256 fingerprint." },
  { id: "cdm",        label: "Canonical Document Model", icon: "📄", desc: "Building geometry-aware word, page, and block representations with font, bbox, and char offsets." },
  { id: "layout",     label: "Layout + Reading Order", icon: "📐", desc: "XY-Cut geometry analysis, furniture detection (headers/footers), multi-column layout resolution." },
  { id: "normindex",  label: "NormIndex Construction", icon: "🔗", desc: "Building bidirectional normalized→raw index for source-grounded string matching." },
  { id: "grammar",    label: "Grammar Induction",      icon: "🧠", desc: "Learning document-wide conventions: code patterns, label variants, unit headings, separator styles." },
  { id: "pageroles",  label: "Page Role Classification", icon: "🏷️", desc: "Classifying each page: cover, toc, course_front, unit_body, matrix, books, etc." },
  { id: "toc",        label: "TOC + Page Map Engine",  icon: "🗺️", desc: "Solving printed vs physical page offsets. Monotonic sequence alignment for irregular pagination." },
  { id: "courses",    label: "Course Hypothesis Discovery", icon: "🎯", desc: "Multi-signal course boundary detection: typography, code pattern, labels, TOC, L-T-P-C tuples." },
  { id: "extract",    label: "Deep Field Extraction",  icon: "⛏️", desc: "Extracting units, topics, Bloom levels, COs, POs, CO-PO matrix, and bibliographic entries." },
  { id: "consensus",  label: "Multi-Engine Consensus", icon: "⚖️", desc: "Reconciling native PDF, table parser, OCR, and LLM proposals at span/cell level." },
  { id: "evidence",   label: "Evidence Graph Build",   icon: "🕸️", desc: "Linking every field to source spans, page geometry, extraction method, and confidence tier." },
  { id: "verify",     label: "Source Span Verification", icon: "✅", desc: "SpanAligner confirms every emitted text is a verified raw source slice." },
  { id: "constraints","label": "Constraint Solver",    icon: "🔒", desc: "Hard constraints reject impossible candidates. Soft constraints downgrade uncertainty." },
  { id: "redteam",    label: "Adversarial Red Team",   icon: "🔴", desc: "Critic tests: boundary flip, topic merge/split, coverage holes, Bloom mismatch, cross-course leakage." },
  { id: "abstention", label: "Calibrated Abstention",  icon: "🎚️", desc: "Applying isotonic-regression calibrated confidence bands. Uncertain fields → not_extracted ledger." },
  { id: "serialize",  label: "Deterministic Serialization", icon: "📤", desc: "Stable canonical JSON output. Byte-identical across 3 runs. Schema validated." }
];

const EVIDENCE_GRAPH_DATA = {
  nodes: [
    { id: "f_title",   label: "course.title",       type: "field",    tier: 5, x: 400, y: 80 },
    { id: "f_code",    label: "course.code",        type: "field",    tier: 5, x: 200, y: 80 },
    { id: "f_units",   label: "units[0].text",      type: "field",    tier: 4, x: 600, y: 80 },
    { id: "f_bloom",   label: "topics.bloom",       type: "field",    tier: 3, x: 800, y: 80 },
    { id: "c_title1",  label: "H1: label-following",type: "candidate",tier: 5, x: 300, y: 200 },
    { id: "c_title2",  label: "H2: font-largest",   type: "candidate",tier: 4, x: 450, y: 200 },
    { id: "c_title3",  label: "H3: TOC entry",      type: "candidate",tier: 4, x: 600, y: 200 },
    { id: "c_code1",   label: "regex match",        type: "candidate",tier: 5, x: 150, y: 200 },
    { id: "c_unit1",   label: "span[p12,r1]",       type: "candidate",tier: 5, x: 750, y: 200 },
    { id: "s_span1",   label: "page 12, line 3",    type: "span",     tier: 5, x: 350, y: 320 },
    { id: "s_span2",   label: "page 12, line 1",    type: "span",     tier: 4, x: 500, y: 320 },
    { id: "s_span3",   label: "TOC page 3",         type: "span",     tier: 4, x: 650, y: 320 },
    { id: "s_code",    label: "page 12, label-row", type: "span",     tier: 5, x: 150, y: 320 },
    { id: "s_unit",    label: "page 12-13 body",    type: "span",     tier: 5, x: 800, y: 320 },
    { id: "m_native",  label: "native PDF (T5)",    type: "method",   tier: 5, x: 250, y: 440 },
    { id: "m_toc",     label: "TOC engine (T4)",    type: "method",   tier: 4, x: 450, y: 440 },
    { id: "m_ocr",     label: "OCR agree (T3)",     type: "method",   tier: 3, x: 650, y: 440 },
    { id: "m_lexicon", label: "verb lexicon",       type: "method",   tier: 3, x: 850, y: 440 }
  ],
  edges: [
    { from: "f_title",  to: "c_title1" }, { from: "f_title",  to: "c_title2" }, { from: "f_title",  to: "c_title3" },
    { from: "f_code",   to: "c_code1" },
    { from: "f_units",  to: "c_unit1" },
    { from: "f_bloom",  to: "m_lexicon" },
    { from: "c_title1", to: "s_span1" }, { from: "c_title2", to: "s_span2" }, { from: "c_title3", to: "s_span3" },
    { from: "c_code1",  to: "s_code" },
    { from: "c_unit1",  to: "s_unit" },
    { from: "s_span1",  to: "m_native" }, { from: "s_span2",  to: "m_native" }, { from: "s_span3",  to: "m_toc" },
    { from: "s_code",   to: "m_native" },
    { from: "s_unit",   to: "m_native" }, { from: "s_unit",   to: "m_ocr" }
  ]
};

const DEBUG_ARTIFACTS = {
  grammar: {
    code_pattern: "\\b[A-Z]{2,5}[- ]?\\d{2,4}[A-Z]?\\b",
    unit_heading: "^\\s*(UNIT|Module|Part|Chapter)\\s*[-:.]?\\s*([IVXLC]+|\\d+)\\b",
    co_pattern: "\\bCO\\s*[- ]?\\d{1,2}\\b",
    po_pattern: "\\bPO\\s*[- ]?\\d{1,2}\\b",
    ltp_pattern: "\\bL\\s*[-/:]\\s*T\\s*[-/:]\\s*P\\b",
    label_code: "(?i)\\b(course|subject|paper)\\s*(code|no\\.?)\\b",
    separator_dominant: "hyphen",
    consistency_score: 0.94,
    pages_analyzed: 15
  },
  segmentation: {
    hypotheses: [
      { page: 12, score: 0.97, signals: ["S0","S1","S2","S3","S4","S8"], code: "CS23301", title: "DATA STRUCTURES AND ALGORITHMS" },
      { page: 24, score: 0.94, signals: ["S0","S1","S2","S3","S4","S8"], code: "CS23302", title: "OBJECT ORIENTED PROGRAMMING" },
      { page: 36, score: 0.91, signals: ["S0","S1","S2","S3","S8"],       code: "MA23101", title: "ENGINEERING MATHEMATICS I" }
    ],
    rejected: [
      { page: 13, score: 0.22, reason: "continuation penalty — same typography as page 12" }
    ]
  },
  consensus: {
    fields_unanimous: 47,
    fields_strong_majority: 8,
    fields_simple_majority: 3,
    fields_split: 1,
    fields_single_source: 2,
    fields_unresolved: 0,
    split_detail: { field: "books[2].publisher", candidates: ["Addison-Wesley", "Addison Wesley Professional"], resolution: "exact native source span wins" }
  },
  critique: {
    tests_run: 13,
    tests_passed: 12,
    concern_raised: 1,
    concern: { test: "Topic merge", field: "units[0].topics[2]", action: "re-examined separator — hyphen confirmed as boundary; original split preserved" }
  }
};
