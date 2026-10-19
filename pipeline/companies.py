"""Company families: a payment from any member counts as declared if the statement names any member."""
import re

FAMILIES = {
    "Abbott": ["abbott", "st\\.? ?jude", "alere", "cardiovascular systems", "csi "],
    "AbbVie": ["abbvie", "allergan", "pharmacyclics", "cerevel", "immunogen"],
    "Johnson & Johnson": ["johnson ?& ?johnson", "j ?& ?j", "janssen", "biosense", "medical device business services", "ethicon",
                          "depuy", "synthes", "actelion", "abiomed", "shockwave", "auris", "cerenovus", "mentor worldwide"],
    "Bristol Myers Squibb": ["bristol", "bms", "squibb", "celgene", "juno", "myokardia", "turning point", "karuna", "mirati", "receptos"],
    "Sanofi": ["sanofi", "genzyme", "regeneron.*sanofi", "bioverativ", "provention"],
    "Merck": ["merck", "msd", "acceleron", "prometheus", "verona"],
    "Roche": ["roche", "genentech", "foundation medicine", "chugai", "spark therapeutics"],
    "Novartis": ["novartis", "sandoz", "hexal", "advanced accelerator", "avexis", "endocyte"],
    "Pfizer": ["pfizer", "seagen", "seattle genetics", "arena", "global blood", "biohaven", "array biopharma", "hospira", "wyeth"],
    "AstraZeneca": ["astra ?zeneca", "astrazenca", "alexion", "medimmune", "acerta"],
    "Eli Lilly": ["lilly", "loxo", "dermira", "prevail"],
    "Amgen": ["amgen", "horizon", "chemocentryx", "teneobio"],
    "Gilead": ["gilead", "kite", "immunomedics", "forty seven"],
    "GSK": ["gsk", "glaxo", "tesaro", "sierra oncology", "viiv"],
    "Takeda": ["takeda", "shire", "baxalta", "millennium"],
    "Boehringer Ingelheim": ["boehringer"],
    "Bayer": ["bayer"],
    "Novo Nordisk": ["novo ?nordisk", "novo"],
    "Medtronic": ["medtronic", "covidien", "intersect ent"],
    "Boston Scientific": ["boston scientific", "bsci", "farapulse", "baylis"],
    "Stryker": ["stryker", "wright medical", "vocera"],
    "BeiGene": ["beigene", "beone"],
    "CSL": ["csl", "vifor"],
    "Daiichi Sankyo": ["daiichi"],
    "Otsuka": ["otsuka", "avanir", "astex"],
    "Astellas": ["astellas", "iveric", "audentes"],
    "Biogen": ["biogen"],
    "UCB": ["ucb", "zogenix", "ra pharma"],
    "Teva": ["teva"],
    "Jazz": ["jazz", "gw pharma"],
    "Edwards Lifesciences": ["edwards"],
    "Siemens": ["siemens"],
    "GE HealthCare": ["ge health", "general electric", "ge medical"],
    "Philips": ["philips"],
    "Intuitive": ["intuitive"],
    "Zimmer Biomet": ["zimmer", "biomet"],
    "Smith & Nephew": ["smith ?& ?nephew"],
    "Olympus": ["olympus"],
    "Incyte": ["incyte"],
    "Exact Sciences": ["exact sciences"],
    "Vertex": ["vertex"],
    "Alnylam": ["alnylam"],
    "Ipsen": ["ipsen"],
    "Servier": ["servier"],
    "Eisai": ["eisai"],
    "Sumitomo": ["sumitomo", "sunovion", "myovant", "urovant"],
    "Kyowa Kirin": ["kyowa"],
    "Galderma": ["galderma"],
    "LEO Pharma": ["leo pharma"],
    "Sun Pharma": ["sun pharma"],
    "Ferring": ["ferring"],
    "Chiesi": ["chiesi"],
    "Insulet": ["insulet"],
    "Dexcom": ["dexcom"],
    "Zoll": ["zoll"],
    "iRhythm": ["irhythm"],
    "Inspire Medical": ["inspire"],
    "Penumbra": ["penumbra"],
    "Integra": ["integra"],
    "Cochlear": ["cochlear"],
    "Natera": ["natera"],
    "Guardant": ["guardant"],
    "Illumina": ["illumina", "grail"],
}
_COMPILED = {fam: re.compile(r"\b(" + "|".join(pats) + r")", re.I) for fam, pats in FAMILIES.items()}


def family(company):
    for fam, rx in _COMPILED.items():
        if rx.search(company or ""):
            return fam
    # fall back to the first meaningful word of the payer name
    words = [w for w in re.findall(r"[A-Za-z]+", company or "") if len(w) > 2 and w.upper() not in {"THE", "INC", "LLC", "CORP"}]
    return words[0].title() if words else company


def named_in(statement, company):
    """True if the statement mentions any name in the company's family."""
    fam = family(company)
    rx = _COMPILED.get(fam)
    if rx:
        return bool(rx.search(statement))
    return bool(re.search(r"\b" + re.escape(fam) + r"\b", statement, re.I))


def author_refs(given, surname):
    """Ways a statement may refer to the author: full surname, or initials such as 'R.R.', 'RR', 'R. R.'."""
    parts = [p for p in re.split(r"[\s\-]+", given.strip()) if p] + [surname.strip()]
    ini = [p[0].upper() for p in parts if p[0].isalpha()]
    first_last = [ini[0], ini[-1]] if len(ini) >= 2 else ini
    pats = {r"(?i:\b" + re.escape(surname.strip()) + r"\b)"}
    for seq in {tuple(ini), tuple(first_last)}:
        if len(seq) >= 2:  # initials stay case-sensitive so 'RR' does not match words
            pats.add(r"\b" + r"\.?\s?".join(seq) + r"\.?(?=[\s,;:)]|$)")
    return re.compile("|".join(pats))
