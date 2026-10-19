"""Step 2 — find each US author in Open Payments (name + state + city) and pull what companies paid them, by company and payment type."""
import re
from collections import defaultdict

from common import DATA, cfg, get, log, pool, read_jsonl, write_jsonl

OP = "https://openpaymentsdata.cms.gov/api/1"
# Nature-of-payment codes in the grouped datasets, mapped by matching against the detailed 2025 records.
NATURE = {"1": "Consulting Fee", "2": "Compensation for services other than consulting (speaker/faculty)", "3": "Honoraria",
          "6": "Food and Beverage", "7": "Travel and Lodging", "8": "Education", "14": "Grant", "19": "Acquisitions"}


def datasets():
    items = get(f"{OP}/metastore/schemas/dataset/items", {"show-reference-ids": "false"})
    by_title = {i["title"]: i["identifier"] for i in items}
    physician = by_title["Payments grouped by physician (distinct) for all years"]
    yearly = {}
    for t, i in by_title.items():
        m = re.fullmatch(r"(\d{4}) payments grouped by reporting entities, covered recipient, and nature of payments", t)
        if m:
            yearly[int(m.group(1))] = i
    return physician, yearly


def query(ds, conditions, props, offset=0):
    params = {"limit": 500, "offset": offset}
    for i, (prop, op, val) in enumerate(conditions):
        params[f"conditions[{i}][property]"], params[f"conditions[{i}][operator]"] = prop, op
        if isinstance(val, (list, tuple)):
            params[f"conditions[{i}][value][]"] = list(val)
        else:
            params[f"conditions[{i}][value]"] = val
    if props:
        params["properties[]"] = props
    return get(f"{OP}/datastore/query/{ds}/0", params)


def norm_first(given):
    return re.split(r"[\s.\-]+", given.strip())[0].upper()


def main():
    c = cfg()
    m, pay = c["matching"], c["payments"]
    papers = read_jsonl(DATA / "papers.jsonl")
    physician_ds, yearly_ds = datasets()
    log(f"Open Payments years available: {sorted(yearly_ds)}")

    # unique people: (FIRST, LAST, STATE) -> affiliations seen
    people = defaultdict(set)
    for p in papers:
        for a in p["authors"]:
            f = norm_first(a["given"])
            if a["state"] and len(f) > 1:
                people[(f, a["surname"].strip().upper(), a["state"])].add(a["aff"])
    keys = sorted(people)
    years = [str(y) for y in sorted(yearly_ds)]
    log(f"{len(keys)} unique US authors to look up")

    props = ["covered_recipient_profile_id", "covered_recipient_profile_first_name", "covered_recipient_profile_last_name",
             "covered_recipient_profile_city", "covered_recipient_profile_state", "covered_recipient_profile_primary_specialty",
             "program_year", "general_total_payment"]

    def lookup(batch):
        lasts, firsts = sorted({k[1] for k in batch}), sorted({k[0] for k in batch})
        want, rows, off = set(batch), [], 0
        cond = [("covered_recipient_profile_last_name", "in", lasts), ("covered_recipient_profile_first_name", "in", firsts),
                ("program_year", "in", years)]
        while True:
            r = query(physician_ds, cond, props, off)
            res = r.get("results", [])
            rows += [x for x in res if (x["covered_recipient_profile_first_name"], x["covered_recipient_profile_last_name"],
                                        x["covered_recipient_profile_state"]) in want]
            off += 500
            if off >= int(r.get("count", 0)) or not res:
                return rows

    B = m["name_batch_size"]
    batches = [keys[i:i + B] for i in range(0, len(keys), B)]
    rows = [x for b in pool(batches, lookup, m["workers"], "name lookups") for x in b]

    profiles = defaultdict(dict)  # person key -> profile id -> info
    for x in rows:
        k = (x["covered_recipient_profile_first_name"], x["covered_recipient_profile_last_name"], x["covered_recipient_profile_state"])
        info = profiles[k].setdefault(x["covered_recipient_profile_id"], {
            "city": x["covered_recipient_profile_city"], "specialty": (x["covered_recipient_profile_primary_specialty"] or "").split("|")[-1],
            "by_year": {}})
        info["by_year"][int(x["program_year"])] = float(x["general_total_payment"] or 0)

    matched = {}
    for k, profs in profiles.items():
        affs = " ".join(people[k]).upper()
        ok = {pid: v for pid, v in profs.items() if not m["require_city_in_affiliation"] or v["city"].upper() in affs}
        status = "matched" if len(ok) == 1 else ("ambiguous" if len(ok) > 1 else "city_mismatch")
        matched[k] = {"status": status, "profiles": profs, "pid": next(iter(ok)) if len(ok) == 1 else None}
    log(f"matched {sum(v['status'] == 'matched' for v in matched.values())} of {len(keys)} authors to one payee profile")

    # payment breakdown (company x type) only for matched people with money in the relevant years
    need = {}
    for k, v in matched.items():
        if v["pid"]:
            yrs = [y for y, amt in v["profiles"][v["pid"]]["by_year"].items() if amt > 0]
            if yrs:
                need[v["pid"]] = yrs
    jobs = [(pid, y) for pid, yrs in need.items() for y in yrs if y in yearly_ds]

    def breakdown(job):
        pid, y = job
        r = query(yearly_ds[y], [("recipient_id", "=", pid)], None)
        return pid, y, r.get("results", [])

    detail = defaultdict(list)
    for pid, y, res in pool(jobs, breakdown, m["workers"] * 2, "payment breakdowns"):
        for x in res:
            code = str(x.get("nature_of_payment_type_code"))
            detail[pid].append({"year": y, "company": x.get("amgpo_name"), "type": NATURE.get(code, f"Other (code {code})"),
                                "amount": round(float(x.get("total_amount") or 0), 2)})

    out = []
    for k, v in matched.items():
        rec = {"first": k[0], "last": k[1], "state": k[2], "status": v["status"], "pid": v["pid"]}
        if v["pid"]:
            prof = v["profiles"][v["pid"]]
            rec.update(city=prof["city"], specialty=prof["specialty"], payments=detail.get(v["pid"], []))
        out.append(rec)
    write_jsonl(DATA / "payments.jsonl", out)
    log(f"saved payment records for {len(out)} authors")


if __name__ == "__main__":
    main()
