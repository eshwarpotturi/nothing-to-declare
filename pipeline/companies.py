"""Company families: a payment from any member counts as declared if the statement names any member."""
import re

FAMILIES = {
    "Abbott": ["abbott", "st\\.? ?jude", "alere", "cardiovascular systems", "csi "],
    "AbbVie": ["abbvie", "allergan", "pharmacyclics", "cerevel", "immunogen"],
    "Johnson & Johnson": ["johnson ?& ?johnson", "j ?& ?j", "janssen", "biosense", "medical device business services", "ethicon",
                          "depuy", "synthes", "actelion", "abiomed", "shockwave", "auris", "cerenovus", "mentor worldwide"],
    "Bristol Myers Squibb": ["bristol", "bms", "squibb", "celgene", "juno", "myokardia", "turning point", "karuna", "mirati", "receptos"],
    "Sanofi": ["sanofi", "genzyme", "regeneron.*sanofi", "bioverativ", "provention"],
    # Merck KGaA (EMD Serono in the US) is a different company from Merck & Co (MSD): keep them apart
    "Merck KGaA (EMD Serono)": ["emd serono", "emd", "merck kgaa", "merck serono", "merck healthcare kgaa"],
    "Merck": ["merck(?![\\s-]*(kgaa|serono|healthcare kgaa))", "msd", "acceleron", "prometheus", "verona"],
    "Roche": ["roche", "genentech", "foundation medicine", "chugai", "spark therapeutics"],
    "Novartis": ["novartis", "sandoz", "hexal", "advanced accelerator", "avexis", "endocyte"],
    "Pfizer": ["pfizer", "seagen", "seattle genetics", "arena pharma", "global blood", "biohaven", "array biopharma", "hospira", "wyeth"],
    "AstraZeneca": ["astra ?zeneca", "astrazenca", "alexion", "medimmune", "acerta"],
    "Eli Lilly": ["lilly", "loxo", "dermira", "prevail"],
    "Amgen": ["amgen", "horizon (therapeutics|pharma)", "chemocentryx", "teneobio"],
    "Gilead": ["gilead", "kite", "immunomedics", "forty seven"],
    "GSK": ["gsk", "glaxo", "tesaro", "sierra oncology", "viiv"],
    "Takeda": ["takeda", "shire", "baxalta", "millennium pharma"],
    "Boehringer Ingelheim": ["boehringer"],
    "Bayer": ["bayer"],
    "Novo Nordisk": ["novo ?nordisk"],
    "Medtronic": ["medtronic", "covidien", "intersect ent"],
    "Boston Scientific": ["boston scientific", "bsci", "farapulse", "baylis"],
    "Stryker": ["stryker", "wright medical", "vocera"],
    "BeiGene": ["beigene", "beone"],
    "CSL": ["csl", "vifor"],
    "Daiichi Sankyo": ["daiichi", "daichii", "daiichii", "dai-ichi"],
    "Otsuka": ["otsuka", "avanir", "astex"],
    "Astellas": ["astellas", "iveric", "audentes"],
    "Biogen": ["biogen"],
    "UCB": ["ucb", "zogenix", "ra pharma"],
    "Teva": ["teva"],
    "Jazz": ["jazz", "gw pharma"],
    "Edwards Lifesciences": ["edwards life"],
    "Siemens": ["siemens"],
    "GE HealthCare": ["ge health", "general electric", "ge medical"],
    "Philips": ["philips"],
    "Intuitive": ["intuitive surgical"],
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
    "Inspire Medical": ["inspire medical"],
    "Penumbra": ["penumbra"],
    "Integra": ["integra"],
    "Cochlear": ["cochlear"],
    "Natera": ["natera"],
    "Guardant": ["guardant"],
    "Illumina": ["illumina", "grail"],
    "Dr. Reddy's": ["dr\\.? ?reddy", "reddy'?s"],
    "Regeneron": ["regeneron"],
}
_COMPILED = {fam: re.compile(r"\b(" + "|".join(pats) + r")", re.I) for fam, pats in FAMILIES.items()}
# Statements often write plain "Merck" for Merck KGaA / EMD Serono, so for that group a bare "Merck" counts as named.
# (For Merck & Co the reverse is not allowed: "Merck KGaA" does not declare MSD.)
ALSO_NAMED = {"Merck KGaA (EMD Serono)": re.compile(r"\bmerck\b", re.I)}


def family(company):
    for fam, rx in _COMPILED.items():
        if rx.search(company or ""):
            return fam
    # fall back to the payer's own name. Short leading words ("G1", "TG", "CTI") are kept with the next word,
    # so "G1 Therapeutics" and "TG Therapeutics" stay apart and a generic word like "Therapeutics" is never the key.
    words = [w for w in re.findall(r"[A-Za-z0-9]+", company or "") if w.upper() not in {"THE", "INC", "LLC", "CORP", "CO", "LTD", "LP", "USA", "US"}]
    if not words:
        return company
    if len(words[0]) <= 3 and len(words) > 1:
        return f"{words[0].upper()} {words[1].title()}"
    return words[0].title()


def named_in(statement, company):
    """True if the statement mentions any name in the company's family."""
    fam = family(company)
    rx = _COMPILED.get(fam)
    if rx:
        return bool(rx.search(statement)) or bool(ALSO_NAMED.get(fam) and ALSO_NAMED[fam].search(statement))
    if re.search(r"\b" + re.escape(fam).replace(r"\ ", r"[\s-]?") + r"\b", statement, re.I):
        return True
    # short brand written alone, e.g. "TG" for TG Therapeutics (capitals only, so ordinary words don't match)
    short = fam.split()[0]
    return " " in fam and len(short) >= 2 and short.isupper() and bool(re.search(r"\b" + re.escape(short) + r"\b", statement))


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
