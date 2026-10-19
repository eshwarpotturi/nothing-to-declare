"""Step 4 — anonymise results for the public dashboard and draw a private verification sample."""
import csv
import json
import random
from collections import Counter, defaultdict

from common import PUBLIC, RESULTS, cfg, log, read_jsonl

REGION = {**{s: "Northeast" for s in "CT ME MA NH RI VT NJ NY PA".split()},
          **{s: "Midwest" for s in "IL IN MI OH WI IA KS MN MO NE ND SD".split()},
          **{s: "South" for s in "DE FL GA MD NC SC VA DC WV AL KY MS TN AR LA OK TX".split()},
          **{s: "West" for s in "AZ CO ID MT NV NM UT WY AK CA HI OR WA".split()}}


def rnd(x, step):
    return max(step, int(round(x / step)) * step)


def band(x):
    """Large amounts are shown as bands so individual doctors are harder to trace."""
    if x >= 1_000_000:
        return 1_000_000, "$1M+"
    if x >= 100_000:
        return 100_000, "$100k+"
    return None, None


def main():
    c = cfg()
    step = c["publish"]["round_usd_to"]
    rows = read_jsonl(RESULTS / "authors.jsonl")
    red = [r for r in rows if r["channel"] == "red"]

    cases = []
    for i, r in enumerate(sorted(red, key=lambda r: (r["date"], r["pmcid"])), 1):
        items = []
        for co in r["undeclared"]:
            v = r["paid"][co]
            floor, label = band(v["total"])
            item = {"company": co, "usd": floor or rnd(v["total"], step),
                    "types": sorted(v["types"], key=lambda t: -v["types"][t])}
            if label:
                item["band"] = label
            items.append(item)
        fee_types = ("Consulting", "Compensation", "Honoraria", "Grant", "Royalty")
        fees = any(t.startswith(fee_types) for x in items for t in x["types"])
        cases.append({"id": f"C{i:04d}", "field": r["field"], "year": int(r["date"][:4]), "fees": fees,
                      "specialty": r.get("specialty") or "Clinician", "region": REGION.get(r["state"], "US"),
                      "reason": r["reason"], "items": items, "usd": sum(x["usd"] for x in items),
                      "banded": any("band" in x for x in items)})

    counts = Counter(r["channel"] for r in rows)
    by_field = defaultdict(lambda: Counter())
    for r in rows:
        by_field[r["field"]][r["channel"]] += 1
    company_counts = Counter(co for r in red for co in r["undeclared"])
    summary = {
        "papers": len({r["pmcid"] for r in rows}), "authors": len(rows), "channels": dict(counts),
        "red_papers": len({r["pmcid"] for r in red}),
        "period": f'{c["papers"]["from_date"][:7]} to {c["papers"]["to_date"][:7]}',
        "by_field": {f: dict(v) for f, v in sorted(by_field.items())},
        "by_year": dict(sorted(Counter(int(r["date"][:4]) for r in red).items())),
        "top_companies": company_counts.most_common(12),
        "undeclared_usd_total": int(sum(sum(r["paid"][co]["total"] for co in r["undeclared"]) for r in red)),
        "usd_to_inr": c["publish"]["usd_to_inr"],
    }
    (PUBLIC / "cases.json").write_text(json.dumps(cases, indent=1))
    (PUBLIC / "summary.json").write_text(json.dumps(summary, indent=1))
    log(f"public: {len(cases)} anonymised red cases, summary {dict(counts)}")

    random.seed(7)
    sample = random.sample(red, min(20, len(red)))
    with open(RESULTS / "verify_sample.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doi", "author", "aff", "payee_city", "payee_specialty", "undeclared", "statement", "match_ok(y/n)", "flag_ok(y/n)"])
        for r in sample:
            w.writerow([r["doi"], r["author"], r["aff"][:200], r.get("city"), r.get("specialty"), "; ".join(r["undeclared"]), r["coi"][:400], "", ""])
    log(f"private verification sample: {len(sample)} rows -> private/results/verify_sample.csv")


if __name__ == "__main__":
    main()
