"""Step 3 — compare each author's declaration with what companies reported paying them, and sort into channels."""
import csv
import hashlib
import json
import re
from collections import defaultdict

import requests

from common import CACHE, DATA, RESULTS, cfg, env_token, log, pool, read_jsonl, write_jsonl
from companies import author_refs, family, named_in
from dates import anchor, program_years
from s2_payments import nature_name, norm_first

RELEVANT = re.compile(r"relevant (conflicts?|competing|financial|disclosures?)|relevant to (the|this) (content|paper|work|study|article|manuscript|research)|not relevant|unrelated to (this|the)|outside (the )?submitted work"
                      r"|(no|any|not have)( known| potential| financial)? (conflicts?|competing (financial )?interests?)( of interest)?( to declare| to disclose)?( directly)? (related to|in|for|with respect to|regarding|relevant to) (this|the) (present |current |submitted )?(work|study|paper|article|manuscript|research|report|publication)", re.I)

BLANKET = re.compile(r"(declare|report|have|has|disclose)[sd]?\s+(that\s+)?(there\s+(are|is)\s+)?(no|nothing)\b"
                     r"|no (known |potential |relevant )?(conflicts?|competing|financial)|none declared|nothing to (declare|disclose|report)", re.I)
# statements that send the reader to a list kept elsewhere (supplement, website) cannot be checked from the text
ELSEWHERE = re.compile(r"(disclosures?|conflicts?( of interest)?|interests?) (forms? )?(are|is|can be) (available|found|provided|listed)"
                       r"|see (the )?(supporting|supplementa)|available (in|at) (the )?(supporting|supplementa|online|https?:)|https?://|www\.", re.I)
MENTIONS = re.compile(r"consult|advis|speaker|honorar|grant|fees?\b|stock|employ|royalt|board|received|support(ed)? by|funding from|paid", re.I)


def blanket_none(coi):
    return bool(coi) and bool(BLANKET.search(coi)) and not MENTIONS.search(coi) and len(coi) < 400


def significant(payments, pay):
    """Company -> {total, types} for companies whose payments are worth declaring."""
    by = defaultdict(lambda: {"total": 0.0, "types": defaultdict(float)})
    for x in payments:
        if x["type"] in pay.get("exclude_types", []):
            continue
        by[x["company"]]["total"] += x["amount"]
        by[x["company"]]["types"][x["type"]] += x["amount"]
    out = {}
    for co, v in by.items():
        flagged_type = any(t and any(t.startswith(k) for k in pay["flag_any_amount_for"]) for t in v["types"])
        if flagged_type or v["total"] >= pay["min_total_usd"]:
            out[co] = {"total": round(v["total"]), "types": {t: round(a) for t, a in v["types"].items()}}
    return out


def llm_undeclared(c, coi, author, initials, companies):
    """Ask the LLM which paying companies the statement does NOT cover for this author. Cached.

    The model first quotes the part of the statement about this author. A company whose group is named in that
    quote is then always treated as declared, so a model slip can only clear a flag, never create one."""
    key = hashlib.sha1(json.dumps([coi, author, initials, sorted(companies), c["llm"]["model"], "v3"]).encode()).hexdigest()
    path = CACHE / "llm" / f"{key}.json"
    if path.exists():
        ans = json.loads(path.read_text(encoding="utf-8"))
    else:
        token = env_token(c["llm"]["token_env"])
        fams = {co: family(co) for co in companies}
        prompt = (f"Conflict-of-interest statement from a medical paper:\n\"\"\"{coi}\"\"\"\n\n"
                  f"Author: {author} (the statement may refer to them by full name, surname or initials such as {initials}).\n"
                  f"Companies that reported paying this author, with their corporate group: {json.dumps(fams)}\n\n"
                  "Step 1: copy, word for word, every part of the statement that describes THIS author's own relationships "
                  "(for example the sentence or list that starts with their name or initials). Do not include parts about "
                  "other authors. If the statement says all authors have no conflicts, copy that sentence. If nothing refers "
                  "to this author, return an empty string.\n"
                  "Step 2: for each paying company, decide whether that part discloses ANY relationship with that company or "
                  "any company in the same corporate group (parent, subsidiary, acquired brand, abbreviation such as BMS for "
                  "E.R. Squibb, MSD for Merck Sharp & Dohme, EMD Serono or plain 'Merck' for Merck KGaA). Being an employee, "
                  "consultant, speaker, advisor, grantee or stockholder all count as disclosed. If you cannot tell whom a "
                  "relationship belongs to, treat it as disclosed.\n"
                  'Reply with JSON only: {"author_segment": "...", "undeclared": [paying companies not disclosed for this author], '
                  '"author_referenced": true/false}')
        r = requests.post(f"{c['llm']['base_url']}/chat/completions", timeout=180,
                          headers={"Authorization": f"Bearer {token}"},
                          json={"model": c["llm"]["model"], "temperature": 0, "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        ans = json.loads(r.json()["choices"][0]["message"]["content"])
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(ans), encoding="utf-8")
    seg = ans.get("author_segment") or ""
    canon = {co.strip().lower(): co for co in companies}  # the model may change the capitalisation of names
    picked = [canon.get(str(x).strip().lower()) for x in ans.get("undeclared", [])]
    ans["undeclared"] = [x for x in dict.fromkeys(picked) if x and not (seg and named_in(seg, x))]
    return ans


def main():
    c = cfg()
    pay = c["payments"]
    papers = read_jsonl(DATA / "papers.jsonl")
    people = {(r["first"], r["last"], r["state"]): r for r in read_jsonl(DATA / "payments.jsonl")}
    for r in people.values():
        for x in r.get("payments", []):
            x["type"] = nature_name(x["type"])

    # Disclosure window: the months before the anchor date (manuscript received, else publication).
    # Step 2 pulls Open Payments totals by program (calendar) year, not dated payments, so every program
    # year is counted by pay["year_rule"]: "inside" (only years wholly inside the window) or "overlap".
    mode = pay.get("window_anchor", "received")
    months = pay.get("lookback_months") or 12 * pay.get("lookback_years", 3)
    rule = pay.get("year_rule", "inside")
    rows, llm_jobs, basis_n = [], [], defaultdict(int)
    for p in papers:
        anchor_date, basis = anchor(p, mode)
        basis_n[basis] += 1
        window = program_years(anchor_date, months, rule)
        for a in p["authors"]:
            k = (norm_first(a["given"]), a["surname"].strip().upper(), a["state"])
            r = people.get(k)
            row = {"pmcid": p["pmcid"], "doi": p["doi"], "title": p["title"], "journal": p["journal"], "field": p["field"],
                   "date": p["date"], "author": f"{a['given']} {a['surname']}", "state": a["state"], "aff": a["aff"], "orcid": a.get("orcid", ""),
                   "coi": p["coi"], "window": f"{min(window)}-{max(window)}",
                   "window_anchor": anchor_date.isoformat(), "window_basis": basis}
            if not a["state"]:
                row["channel"] = "not_checkable"
            elif not p["coi"]:
                row["channel"] = "no_statement"
            elif r is None:
                row["channel"] = "green"; row["reason"] = "no payments on record"
            elif r["status"] != "matched":
                row["channel"] = "unclear"; row["reason"] = r["status"]
            else:
                sig = significant([x for x in r["payments"] if x["year"] in window], pay)
                row.update(specialty=r["specialty"], city=r["city"], pid=r["pid"], paid=sig)
                refs = author_refs(a["given"], a["surname"])
                parts = [x for x in re.split(r"[\s\-]+", a["given"].strip()) if x] + [a["surname"].strip()]
                row["initials"] = ".".join(x[0].upper() for x in parts) + "."
                if not sig:
                    row["channel"] = "green"; row["reason"] = "nothing significant on record"
                elif blanket_none(p["coi"]):
                    row["undeclared"] = list(sig)
                    if RELEVANT.search(p["coi"]):
                        row["channel"] = "amber"; row["reason"] = "declares no RELEVANT conflicts"
                    else:
                        row["channel"] = "red"; row["reason"] = "statement declares no conflicts"
                else:
                    # payers whose company group is never named anywhere in the statement are clearly undeclared
                    sponsor = bool(re.search(r"sponsor", p["coi"], re.I)) and bool(refs.search(p["coi"]))
                    unnamed = [] if sponsor else [co for co in sig if not named_in(p["coi"], co)]
                    named = [co for co in sig if co not in unnamed]
                    row["undeclared"] = unnamed
                    if sponsor:
                        named = list(sig)
                    if named and refs.search(p["coi"]) and c["llm"]["enabled"]:
                        row["channel"] = "pending_llm"; row["llm_companies"] = named; llm_jobs.append(row)
                    elif named and refs.search(p["coi"]):
                        row["channel"] = "unclear"; row["reason"] = "partial disclosure, LLM step off"
                    else:
                        row["channel"] = "red" if unnamed else "green"
                        row["reason"] = "payer not named anywhere in a partial disclosure" if unnamed else "payers named in statement"
                    if row["channel"] == "red" and RELEVANT.search(p["coi"]):
                        row["channel"] = "amber"; row["reason"] += " (statement limits to relevant conflicts)"
            rows.append(row)
    log(f"look-back {months} months from the {mode} date; papers using received date: {basis_n['received']}, "
        f"publication date: {basis_n['published']}", basis_n["received"], len(papers))

    if llm_jobs:
        log(f"LLM check for {len(llm_jobs)} authors with partial disclosures")

        def run(row):
            ini = row["initials"]
            ans = llm_undeclared(c, row["coi"], row["author"], ini, row["llm_companies"])
            row["undeclared"] = row["undeclared"] + [x for x in ans["undeclared"] if x not in row["undeclared"]]
            row["channel"] = "red" if row["undeclared"] else "green"
            row["reason"] = "partial disclosure misses some companies" if row["undeclared"] else "disclosure covers the payers"
            if row["channel"] == "red" and RELEVANT.search(row["coi"]):
                row["channel"] = "amber"; row["reason"] += " (statement limits to relevant conflicts)"
        pool(llm_jobs, run, 6, "LLM checks")
        for row in llm_jobs:
            if row["channel"] == "pending_llm":
                row["channel"] = "unclear"; row["reason"] = "LLM check failed"

    # royalties: authors often disclose "royalties" or a patent without naming the licensee company
    for row in rows:
        if row["channel"] != "red" or not row.get("undeclared"):
            continue
        roy_only = [co for co in row["undeclared"] if all(t.startswith("Royalty") for t in row["paid"][co]["types"])]
        refs = author_refs(*row["author"].rsplit(" ", 1))
        if roy_only and refs.search(row["coi"]) and re.search(r"royalt|patent|inventor|licens", row["coi"], re.I):
            row["undeclared"] = [co for co in row["undeclared"] if co not in roy_only]
            if not row["undeclared"]:
                row["undeclared"] = roy_only
                row["channel"] = "amber"; row["reason"] += " (royalties or patents disclosed without naming the company)"
    for row in rows:
        if row["channel"] == "red" and ELSEWHERE.search(row["coi"]):
            row["channel"] = "amber"; row["reason"] += " (statement points to disclosures kept elsewhere)"
    write_jsonl(RESULTS / "authors.jsonl", rows)
    red = [r for r in rows if r["channel"] == "red"]
    with open(RESULTS / "red_flags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "journal", "doi", "title", "author", "specialty", "city", "state", "undeclared_companies",
                    "undeclared_total_usd", "reason", "statement"])
        for r in sorted(red, key=lambda r: r["date"], reverse=True):
            tot = sum(r["paid"][co]["total"] for co in r["undeclared"])
            w.writerow([r["date"], r["journal"], r["doi"], r["title"], r["author"], r["specialty"], r["city"], r["state"],
                        "; ".join(r["undeclared"]), tot, r["reason"], r["coi"][:500]])
    counts = defaultdict(int)
    for r in rows:
        counts[r["channel"]] += 1
    log(f"channels: {dict(counts)}; red flags in {len({r['pmcid'] for r in red})} papers")


if __name__ == "__main__":
    main()
