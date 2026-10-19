"""Step 1 — fetch open-access papers with US authors and pull out authors, affiliations and the conflict-of-interest statement."""
import re
import xml.etree.ElementTree as ET

from common import DATA, cfg, get, log, pool, write_jsonl

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
          "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
          "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
          "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
          "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
          "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
          "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
          "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
          "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
          "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC"}
ABBR = set(STATES.values())
COI_TITLE = re.compile(r"conflict|competing|disclos|declaration of interest|coi", re.I)


def state_of(aff):
    for name, ab in STATES.items():
        if re.search(rf"\b{name}\b", aff):
            return ab
    m = re.search(r",\s*([A-Z]{2})\s*\d{0,5}(-\d{4})?\s*,?\s*(USA|United States)", aff)
    return m.group(1) if m and m.group(1) in ABBR else None


def text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def search(c):
    p = c["papers"]
    out = []
    for i, (journal, field) in enumerate(p["journals"].items(), 1):
        q = f'JOURNAL:"{journal}" AND FIRST_PDATE:[{p["from_date"]} TO {p["to_date"]}] AND AFF:"{p["country_filter"]}"'
        if p["open_access_only"]:
            q += " AND OPEN_ACCESS:y"
        cursor, n = "*", 0
        while True:
            r = get(f"{EPMC}/search", {"query": q, "format": "json", "pageSize": 1000, "resultType": "lite", "cursorMark": cursor})
            res = r["resultList"]["result"]
            for x in res:
                if x.get("pmcid"):
                    x["journal"], x["field"] = journal, field
                    out.append(x)
            n += len(res)
            nxt = r.get("nextCursorMark")
            if not res or not nxt or nxt == cursor:
                break
            cursor = nxt
        log(f"search: {journal} -> {n} papers", i, len(p["journals"]))
    return list({x["pmcid"]: x for x in out}.values())


def parse(hit):
    xml = get(f"{EPMC}/{hit['pmcid']}/fullTextXML", as_json=False)
    root = ET.fromstring(xml)
    affs = {a.get("id"): text(a) for a in root.iter("aff")}
    authors = []
    for c in root.iter("contrib"):
        if c.get("contrib-type") != "author":
            continue
        sn, gn = c.find(".//surname"), c.find(".//given-names")
        if sn is None or gn is None:
            continue
        aff = " | ".join(affs.get(x.get("rid"), "") for x in c.iter("xref") if x.get("ref-type") == "aff")
        aff = aff or text(c.find(".//aff"))
        if "USA" in aff or "United States" in aff:
            authors.append({"given": text(gn), "surname": text(sn), "aff": aff[:400], "state": state_of(aff)})
    coi = []
    for tag in ("sec", "fn", "notes"):
        for el in root.iter(tag):
            head = " ".join(filter(None, [text(el.find("title")), el.get("fn-type"), el.get("sec-type"), el.get("notes-type")]))
            if COI_TITLE.search(head):
                coi.append(text(el))
    return {"pmcid": hit["pmcid"], "doi": hit.get("doi"), "title": hit.get("title"), "journal": hit["journal"],
            "field": hit["field"], "date": hit["firstPublicationDate"], "year": int(hit["firstPublicationDate"][:4]),
            "authors": authors, "coi": " ".join(dict.fromkeys(coi))[:4000]}


def main():
    c = cfg()
    hits = search(c)
    log(f"fetching full text for {len(hits)} papers")
    papers = pool(hits, parse, 8, "full text")
    papers = [p for p in papers if p["authors"]]
    write_jsonl(DATA / "papers.jsonl", papers)
    log(f"saved {len(papers)} papers with US authors, {sum(len(p['authors']) for p in papers)} US author slots")


if __name__ == "__main__":
    main()
