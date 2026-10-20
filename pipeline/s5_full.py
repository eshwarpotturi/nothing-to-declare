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
    pub_cases = json.loads((ROOT / "docs" / "data" / "cases.json").read_text(encoding="utf-8"))
    summary = json.loads((ROOT / "docs" / "data" / "summary.json").read_text(encoding="utf-8"))
    pub_papers = json.loads((ROOT / "docs" / "data" / "papers.json").read_text(encoding="utf-8"))

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

    # hand-checked cases (from handcheck.py) and the audit of all hand checks, if present
    hc_path, audit_path = RESULTS / "handcheck.json", RESULTS / "audit.json"
    hand = json.loads(hc_path.read_text(encoding="utf-8")) if hc_path.exists() else []
    orcid = {(r["pmcid"], r["author"]): r.get("orcid", "") for r in rows}
    for h in hand:
        pm = h["key"].split("|")[0]
        h["orcid"] = orcid.get((pm, h["name"]), "")
        h["scholar"] = "https://scholar.google.com/scholar?q=" + quote_plus(f'author:"{h["name"]}"')
        h["case"] = cid_of.get((pm, h["name"]))
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {"rounds": []}

    tpl = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    data = json.dumps({"S": summary, "C": cases, "P": papers, "H": hand, "A": audit}, separators=(",", ":")).replace("</", "<\\/")
    html = patch(tpl, data)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    log(f"internal full version: {OUT} ({len(html) / 1e6:.1f} MB, {len(cases)} cases, {len(papers)} papers)")


def patch(s, data):
    rep = [
        ('<title>Nothing to Declare</title>', '<title>Nothing to Declare (internal)</title>'),
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
         '.hgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:12px}\n'
         '.hcard{all:unset;cursor:pointer;display:grid;gap:4px;background:var(--paper);border:1px solid var(--rule);border-left:6px solid var(--bad);border-radius:10px;padding:12px 16px}\n'
         '.hcard:hover{background:var(--hover)}.hname{font:800 24px var(--serif);color:var(--ink)}.hsub{font-size:17px;color:var(--muted)}\n'
         '.hline{font-size:18px;font-style:italic;color:var(--ink2)}.hamt{font:700 26px var(--mono);color:var(--bad)}.hamt small{font:400 16px var(--sans);color:var(--muted)}\n'
         '.hok{font:600 14px var(--mono);color:var(--good);text-transform:uppercase;letter-spacing:.06em}\n'
         '.ptab{width:100%;border-collapse:collapse;font-size:17px;margin-top:10px}.ptab th{text-align:left;font:600 14px var(--mono);text-transform:uppercase;color:var(--muted);border-bottom:2px solid var(--rule);padding:6px}\n'
         '.ptab td:first-child{white-space:nowrap}.ptab td{border-bottom:1px solid var(--rule);padding:6px;vertical-align:top;color:var(--ink2)}.audit td{font-size:17px}\n'
         '.tag{font:600 13px var(--mono);text-transform:uppercase;letter-spacing:.06em;border-radius:99px;padding:3px 8px;text-align:center;color:#fff}\n'
         '/* modal */'),
    ]
    for a, b in rep:
        assert a in s, a[:50]
        s = s.replace(a, b)
    s = s.replace('Authors are anonymised to specialty and US region; amounts are rounded to $1,000, and amounts over $100,000 appear only as bands.',
                  'This internal version shows real names, exact amounts and a link to each public payment record.')
    s = s.replace('<p class="kicker">One real case, anonymised</p>', '<p class="kicker">One real case</p>')
    s = s.replace('<section>\n    <p class="kicker">Explore</p>', HAND_HTML + '\n  <section>\n    <p class="kicker">Explore</p>', 1)
    s = s.replace('<span>${esc(c.specialty)} · US ${esc(c.region)}<small>${esc(c.field)} paper, ${c.year} · ${famTxt(c,3)}',
                  '<span>${esc(c.name)} · ${esc(c.specialty)}, ${esc(c.city)}<small>${esc(c.journal)}, ${c.year} · ${famTxt(c,3)}')
    # data inline instead of fetch
    s = s.replace('Promise.all(["summary","cases","papers"].map(n=>fetch(`data/${n}.json`).then(r=>r.json())))',
                  'Promise.resolve((d=>[d.S,d.C,d.P])(JSON.parse(document.getElementById("ntd-data").textContent)))')
    s = s.replace('<div id="modalRoot"></div>', '<div id="modalRoot"></div>\n<script type="application/json" id="ntd-data">' + data + '</script>')
    # extra JS: named views (override functions defined earlier)
    s = s.replace('/* ---------- hover cards ---------- */', FULL_JS + '\n/* ---------- hover cards ---------- */')
    return s


HAND_HTML = '''<section>
    <p class="kicker">Checked by hand</p>
    <h2>Ten cases, checked line by line against the government record.</h2>
    <p class="read"><b>How to read:</b> each card is one author. The quote is what the paper says about them; the amount is what companies reported paying them in the 36 months before the journal received the paper. Click a card for every dated payment record. <b>For a publisher</b>, this is the evidence an editor would see before sending a query.</p>
    <div class="hgrid" id="handGrid"></div>
    <h3 style="margin-top:26px;font-size:30px">How we tested the checker</h3>
    <p class="read">We also checked 43 random red cases by hand, in three rounds. Each error we found was traced to its cause and fixed in the code before the next round.</p>
    <table class="ptab audit"><thead><tr><th>Round</th><th>Checked</th><th>Held up</th><th>Errors found</th><th>Fix</th></tr></thead><tbody id="auditBody"></tbody></table>
  </section>'''


FULL_JS = r'''
/* ---------- internal: named views ---------- */
let HD=[],AU={rounds:[]};
try{const d=JSON.parse(document.getElementById("ntd-data").textContent);HD=d.H||[];AU=d.A||{rounds:[]}}catch(e){}
const usd=x=>"$"+Math.round(x).toLocaleString();
function handView(h){
  const rows=h.payments.map(p=>`<tr><td>${p.date}</td><td>${esc(p.company)}</td><td>${esc(p.type)}</td><td style="text-align:right;font-family:var(--mono)">${usd(p.usd)}</td><td style="font-family:var(--mono);color:var(--muted)">${esc(p.record)}</td></tr>`).join("");
  return `<h3>${esc(h.name)}</h3><p class="sub">${esc(h.specialty||"")}, ${esc(h.city)}, ${esc(h.state)} · <i>${esc(h.title)}</i> (${esc(h.journal)}, ${h.date.slice(0,4)})</p>
   <div class="links"><a class="proof" href="${h.proof}" target="_blank" rel="noopener">Proof: government payment record ↗</a><a href="https://doi.org/${h.doi}" target="_blank" rel="noopener">Read the paper ↗</a><a href="${h.scholar}" target="_blank" rel="noopener">Google Scholar ↗</a>${h.orcid?`<a href="https://orcid.org/${h.orcid}" target="_blank" rel="noopener">ORCID ↗</a>`:""}</div>
   <div class="quote">“${esc(h.line)}”<br><small style="font-style:normal">What the paper's statement says about this author. Received by the journal ${h.received}; payments counted from ${h.window.replace("-"," to ")}.</small></div>
   <p class="read"><b>${h.payments.length} payment records, ${usd(h.total)} in total</b>, of which ${usd(h.fees)} were fees (consulting, speaking, honoraria). Every row below is one record in the US government's Open Payments database.</p>
   <div style="max-height:420px;overflow:auto;margin-top:8px"><table class="ptab"><thead><tr><th>Date</th><th>Company</th><th>Type</th><th>Amount</th><th>Record</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function drawHand(){
  const el=document.getElementById("handGrid");if(!el)return;
  el.innerHTML=HD.map((h,i)=>`<button class="hcard" data-i="${i}"><span class="hname">${esc(h.name)}</span><span class="hsub">${esc(h.specialty||"")}, ${esc(h.city)} · ${esc(h.journal)}, ${h.date.slice(0,4)}</span>
     <span class="hline">“${esc(h.line)}”</span><span class="hamt">${usd(h.total)} <small>from ${esc(h.by_company.slice(0,2).map(x=>nice(x[0])).join(", "))}${h.by_company.length>2?" and others":""}</small></span><span class="hok">✓ Checked by hand</span></button>`).join("");
  el.querySelectorAll(".hcard").forEach(b=>b.onclick=()=>openModal(handView(HD[+b.dataset.i])));
  const au=document.getElementById("auditBody");
  if(au)au.innerHTML=AU.rounds.map(r=>`<tr><td>${esc(r.name)}</td><td style="text-align:center">${r.checked}</td><td style="text-align:center" class="grn"><b>${r.held}</b></td><td>${r.errors.map(esc).join("<br>")}</td><td>${esc(r.fix)}</td></tr>`).join("");
}
setTimeout(drawHand,0);
const TAGC={red:"--bad",amber:"--warn",green:"--good",unclear:"--none",not_checkable:"--none",outside:"--none",no_statement:"--none"};
const TAGT={red:"Undeclared",amber:"Limited",green:"Clean",unclear:"Unclear match",not_checkable:"Not checkable",outside:"Non-US",no_statement:"No statement"};
const plink=x=>x.doi?`https://doi.org/${x.doi}`:"";
function linksFor(c){return `<div class="links"><a class="proof" href="${c.proof}" target="_blank" rel="noopener">Proof: government payment record ↗</a><a href="${c.scholar}" target="_blank" rel="noopener">Google Scholar ↗</a>${c.orcid?`<a href="https://orcid.org/${c.orcid}" target="_blank" rel="noopener">ORCID ↗</a>`:""}<a href="${plink(c)}" target="_blank" rel="noopener">Read the paper ↗</a></div>`}
caseView=function(c,back){
  const amb=c.ch==="amber",cos=[...new Set(c.items.map(i=>esc(nice(i.company))))].join(" and ");
  return `${back?`<button class="back" id="mback">← Back</button>`:""}<h3>${esc(c.name)}</h3>
   <p class="sub">${esc(c.specialty)}, ${esc(c.city)}, ${esc(c.state)} · <i>${esc(c.title)}</i> (${esc(c.journal)}, ${c.year})</p>
   ${linksFor(c)}
   ${caseBlock({...c,specialty:c.name,region:c.city+", "+c.state},true)}
   <div class="quote">“${esc(c.statement)}”<br><small style="font-style:normal">The paper's conflict-of-interest statement, as published.</small></div>
   <div class="letter"><b>Draft query the editor could send:</b> Dear Dr ${esc(c.name.split(" ").slice(-1)[0])}, as part of a routine disclosure check we noticed that public US records list payments to you from ${cos} in the 36 months before you submitted your article, which do not appear in its conflict-of-interest statement. Could you confirm whether these should be added? We are happy to publish an updated statement.</div>`;
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
