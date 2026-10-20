"""Hand-check helper: for chosen flagged authors, pull every dated payment record from Open Payments inside the
disclosure window, so a person can compare it with the paper's statement. Output stays in private/.

Usage: python handcheck.py "PMCID|Author Name" ["PMCID|Author Name" ...]"""
import json
import sys
from collections import defaultdict

from common import RESULTS, get, log, read_jsonl
from companies import family
from s2_payments import OP, query

FEES = ("Consulting", "Compensation", "Honoraria", "Royalty", "Grant")


def detail_datasets():
    items = get(f"{OP}/metastore/schemas/dataset/items", {"show-reference-ids": "false"})
    out = {}
    for i in items:
        t = i["title"]
        if t.endswith(" General Payment Data") and t[:4].isdigit():
            out[int(t[:4])] = i["identifier"]
    return out


def records(ds, pid):
    rows, off = [], 0
    while True:
        r = query(ds, [("covered_recipient_profile_id", "=", pid)], None, off)
        batch = r.get("results", [])
        rows += batch
        if len(batch) < 500:
            return rows
        off += 500


def main(keys):
    rows = {f'{r["pmcid"]}|{r["author"]}': r for r in read_jsonl(RESULTS / "authors.jsonl")}
    ds = detail_datasets()
    out = []
    for n, k in enumerate(keys, 1):
        r = rows[k]
        lo, hi = map(int, r["window"].split("-"))
        und_fams = {family(c) for c in r["undeclared"]}
        pays = []
        for y in range(lo, hi + 1):
            for x in records(ds[y], r["pid"]):
                co = x.get("applicable_manufacturer_or_applicable_gpo_making_payment_name", "")
                if family(co) not in und_fams:
                    continue
                m, d, yy = x["date_of_payment"].split("/")
                pays.append({"date": f"{yy}-{m}-{d}", "company": co, "usd": float(x["total_amount_of_payment_usdollars"]),
                             "type": x.get("nature_of_payment_or_transfer_of_value", ""), "record": x.get("record_id", "")})
        pays.sort(key=lambda p: p["date"])
        by = defaultdict(float)
        for p in pays:
            by[p["company"]] += p["usd"]
        out.append({"key": k, "name": r["author"], "specialty": r.get("specialty"), "city": (r.get("city") or "").title(),
                    "state": r["state"], "aff": r["aff"], "title": r["title"], "journal": r["journal"], "date": r["date"],
                    "received": r.get("window_anchor"), "window": r["window"], "doi": r["doi"], "statement": r["coi"],
                    "reason": r["reason"], "proof": f"https://openpaymentsdata.cms.gov/physician/{r['pid']}",
                    "total": round(sum(by.values())), "by_company": sorted(by.items(), key=lambda kv: -kv[1]),
                    "fees": round(sum(p["usd"] for p in pays if p["type"].startswith(FEES))), "payments": pays})
        log(f"hand-check records for {r['author']}: {len(pays)} payments", n, len(keys))
    (RESULTS / "handcheck.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(out)} cases to private/results/handcheck.json")


if __name__ == "__main__":
    main(sys.argv[1:])
