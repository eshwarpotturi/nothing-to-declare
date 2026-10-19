"""Step 5 — build the INTERNAL full version: one self-contained HTML file with real names, paper links and proof links.
Written to private/ only (gitignored). Never publish it."""
import json
import re
from collections import defaultdict
from urllib.parse import quote_plus

from common import DATA, PRIVATE, RESULTS, ROOT, log, read_jsonl
from s4_publish import REGION
from companies import family

OUT = PRIVATE / "full" / "nothing-to-declare-full.html"


def main():
    rows = read_jsonl(RESULTS / "authors.jsonl")
    meta = {p["pmcid"]: p for p in read_jsonl(DATA / "papers.jsonl")}
    pub_cases = json.loads((ROOT / "docs" / "data" / "cases.json").read_text())
    summary = json.loads((ROOT / "docs" / "data" / "summary.json").read_text())
    pub_papers = json.loads((ROOT / "docs" / "data" / "papers.json").read_text())

    # rebuild case ids exactly as step 4 does, then attach real details
    flagged = sorted([r for r in rows if r["channel"] in ("red", "amber")], key=lambda r: (r["date"], r["pmcid"]))
    full = {}
    for i, r in enumerate(flagged, 1):
        cid = f"C{i:04d}"
        items = [{"company": co, "fam": family(co), "usd": int(round(r["paid"][co]["total"])),
                  "types": sorted(r["paid"][co]["types"], key=lambda t: -r["paid"][co]["types"][t])} for co in r["undeclared"]]
        full[cid] = {"name": r["author"], "city": (r.get("city") or "").title(), "state": r["state"], "orcid": r.get("orcid", ""),
                     "proof": f"https://openpaymentsdata.cms.gov/physician/{r['pid']}",
                     "scholar": "https://scholar.google.com/scholar?q=" + quote_plus(f'author:"{r["author"]}"'),
                     "doi": r["doi"], "title": r["title"], "journal": r["journal"], "statement": r["coi"][:1500],
                     "items": items, "usd": sum(x["usd"] for x in items), "pmcid": r["pmcid"]}
    cases = []
    for c in pub_cases:
        f = full[c["id"]]
        c = {**c, **f, "banded": False}
        cases.append(c)

    # papers: same order as the public grid, plus title, journal, link and every author
    by_author = {(r["pmcid"], r["author"]): r for r in rows}
    cid_of = {(full[k]["pmcid"], full[k]["name"]): k for k in full}
    pmcids_in_order = []
    groups = defaultdict(set)
    for r in rows:
        groups[r["pmcid"]].add(r["channel"])
    import hashlib
    for pm in sorted(groups, key=lambda k: hashlib.md5(k.encode()).hexdigest()):
        pmcids_in_order.append(pm)
    papers = []
    for pub, pm in zip(pub_papers, pmcids_in_order):
        m = meta[pm]
        auth = []
        for a in m.get("everyone", []):
            r = by_author.get((pm, a["name"]))
            st = r["channel"] if r else ("outside" if not a["us"] else "not_checkable")
            auth.append({"name": a["name"], "st": st, "case": cid_of.get((pm, a["name"])), "orcid": a.get("orcid", "")})
        papers.append({**pub, "t": m["title"], "j": m["journal"], "doi": m["doi"], "a": auth})

    tpl = (ROOT / "docs" / "index.html").read_text()
    data = json.dumps({"S": summary, "C": cases, "P": papers}, separators=(",", ":")).replace("</", "<\\/")
    html = patch(tpl, data)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    log(f"internal full version: {OUT} ({len(html) / 1e6:.1f} MB, {len(cases)} cases, {len(papers)} papers)")


def patch(s, data):
    rep = [
        ('<title>Nothing to Declare</title>', '<title>Nothing to Declare (internal)</title>'),
        # title and subtitle (Anand's feedback: two lines, UK-government plain style)
        ('<h1>One in three medical papers has an author who didn\'t declare <span class="red">drug-company money</span>.</h1>',
         '<h1>1 in 3 papers hides <span class="red">drug-company money</span>.</h1>'),
        # internal banner
        ('<div class="col">\n  <div class="topbar">',
         '<div class="internal">Internal. Contains real names. Not for public sharing.</div>\n<div class="col">\n  <div class="topbar">'),
        ('/* modal */', '.internal{background:var(--bad);color:#fff;text-align:center;font-weight:700;padding:6px;font-size:18px}\n'
         '.links{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px}.links a{font-size:17px;border:1px solid var(--rule);background:var(--paper);border-radius:99px;padding:4px 12px;color:var(--ink);text-decoration:none}\n'
         '.links a:hover{background:var(--hover)}.links a.proof{border-color:var(--bad);color:var(--bad);font-weight:600}\n'
         '.quote{margin-top:12px;background:var(--paper);border-left:4px solid var(--muted);padding:10px 16px;font-size:18px;color:var(--ink2);font-style:italic}\n'
         '.authors{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:6px}\n'
         '.authors li{display:grid;grid-template-columns:110px 1fr auto;gap:12px;align-items:center;background:var(--paper);border:1px solid var(--rule);border-radius:8px;padding:8px 12px;font-size:19px}\n'
         '.authors li.clk{cursor:pointer}.authors li.clk:hover{background:var(--hover)}\n'
         '.tag{font:600 13px var(--mono);text-transform:uppercase;letter-spacing:.06em;border-radius:99px;padding:3px 8px;text-align:center;color:#fff}\n'
         '/* modal */'),
    ]
    for a, b in rep:
        assert a in s, a[:50]
        s = s.replace(a, b)
    s = re.sub(r'<p class="lede">.*?</p>',
               '<p class="lede">Medical papers ask authors to declare money from drug and device companies. '
               'We checked 2,878 papers against the US government\'s public payment record. Half pass. A third do not.</p>', s, count=1, flags=re.S)
    s = s.replace('<span>${esc(c.specialty)} · US ${esc(c.region)}<small>${esc(c.field)} paper, ${c.year} · ${famTxt(c,3)}',
                  '<span>${esc(c.name)} · ${esc(c.specialty)}, ${esc(c.city)}<small>${esc(c.journal)}, ${c.year} · ${famTxt(c,3)}')
    # data inline instead of fetch
    s = s.replace('Promise.all(["summary","cases","papers"].map(n=>fetch(`data/${n}.json`).then(r=>r.json())))',
                  'Promise.resolve((d=>[d.S,d.C,d.P])(JSON.parse(document.getElementById("ntd-data").textContent)))')
    s = s.replace('<div id="modalRoot"></div>', '<div id="modalRoot"></div>\n<script type="application/json" id="ntd-data">' + data + '</script>')
    # extra JS: named views (override functions defined earlier)
    s = s.replace('/* ---------- hover cards ---------- */', FULL_JS + '\n/* ---------- hover cards ---------- */')
    return s


FULL_JS = r'''
/* ---------- internal: named views ---------- */
const TAGC={red:"--bad",amber:"--warn",green:"--good",unclear:"--none",not_checkable:"--none",outside:"--none",no_statement:"--none"};
const TAGT={red:"Undeclared",amber:"No relevant",green:"Clean",unclear:"Unclear match",not_checkable:"Not checkable",outside:"Non-US",no_statement:"No statement"};
const plink=x=>x.doi?`https://doi.org/${x.doi}`:"";
function linksFor(c){return `<div class="links"><a class="proof" href="${c.proof}" target="_blank" rel="noopener">Proof: government payment record ↗</a><a href="${c.scholar}" target="_blank" rel="noopener">Google Scholar ↗</a>${c.orcid?`<a href="https://orcid.org/${c.orcid}" target="_blank" rel="noopener">ORCID ↗</a>`:""}<a href="${plink(c)}" target="_blank" rel="noopener">Read the paper ↗</a></div>`}
caseView=function(c,back){
  const amb=c.ch==="amber",cos=[...new Set(c.items.map(i=>esc(nice(i.company))))].join(" and ");
  return `${back?`<button class="back" id="mback">← Back</button>`:""}<h3>${esc(c.name)}</h3>
   <p class="sub">${esc(c.specialty)}, ${esc(c.city)}, ${esc(c.state)} · <i>${esc(c.title)}</i> (${esc(c.journal)}, ${c.year})</p>
   ${linksFor(c)}
   ${caseBlock({...c,specialty:c.name,region:c.city+", "+c.state},true)}
   <div class="quote">“${esc(c.statement)}”<br><small style="font-style:normal">The paper's conflict-of-interest statement, as published.</small></div>
   <div class="letter"><b>Draft query the editor could send:</b> Dear Dr ${esc(c.name.split(" ").slice(-1)[0])}, as part of a routine disclosure check we noticed that public US records list payments to you from ${cos} in the three years before your article, which do not appear in its conflict-of-interest statement. Could you confirm whether these should be added? We are happy to publish an updated statement.</div>`;
};
paperView=function(p){
  const rows=p.a.map(a=>{const c=a.case?byId[a.case]:null;return `<li class="${c?"clk":""}" ${c?`data-id="${c.id}"`:""}><span class="tag" style="background:var(${TAGC[a.st]||"--none"})">${TAGT[a.st]||a.st}</span><span>${esc(a.name)}${a.orcid?` <a href="https://orcid.org/${a.orcid}" target="_blank" rel="noopener" style="font-size:15px">ORCID</a>`:""}</span><span class="amt" style="font-family:var(--mono)">${c?k(c.usd)+" undeclared":""}</span></li>`}).join("");
  const nf=p.a.filter(a=>a.case).length;
  const html=()=>`<h3 style="font-size:28px">${esc(p.t)}</h3><p class="sub">${esc(p.j)}, ${p.y}. ${p.a.length} authors; ${p.n} US authors checked${nf?`; <b class="red">${nf} with undeclared payments</b>`:""}.</p>
    <div class="links"><a href="https://doi.org/${p.doi}" target="_blank" rel="noopener">Read the paper ↗</a></div>
    <ul class="authors">${rows}</ul>${nf?'<p class="hint">Click a flagged author for the evidence.</p>':""}`;
  const wire=()=>$("mbody").querySelectorAll("li[data-id]").forEach(li=>li.onclick=e=>{if(e.target.tagName==="A")return;setModal(caseView(byId[li.dataset.id],true));$("mback").onclick=()=>{setModal(html());wire()}});
  openModal(html());wire();
};
listView=function(title,sub,cases,stats){
  const rows=cases.slice().sort((a,b)=>b.usd-a.usd).slice(0,200);
  const html=()=>`<h3>${esc(title)}</h3><p class="sub">${sub}</p>${stats||""}
   <ul class="mlist">${rows.map(c=>`<li><button data-id="${c.id}"><i style="background:var(${c.ch==="amber"?"--warn":"--bad"})"></i><span>${esc(c.name)} · ${esc(c.specialty)}, ${esc(c.city)}<small>${esc(c.journal)}, ${c.year} · ${famTxt(c,3)}</small></span><span class="amt">${k(c.usd)}</span></button></li>`).join("")}</ul>
   ${cases.length>200?`<p class="hint">Showing the 200 largest of ${cases.length.toLocaleString()}.</p>`:""}`;
  const wire=()=>$("mbody").querySelectorAll("[data-id]").forEach(b=>b.onclick=()=>{setModal(caseView(byId[b.dataset.id],true));$("mback").onclick=()=>{setModal(html());wire()}});
  openModal(html());wire();
};
'''


if __name__ == "__main__":
    main()
