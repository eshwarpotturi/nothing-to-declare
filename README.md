# Nothing to Declare?

**Live dashboard:** https://eshwarpotturi.github.io/nothing-to-declare/

Medical papers end with a conflict-of-interest statement, often just *"The authors declare no conflicts of interest."* Journals rarely check it. This project checks it automatically against the US government's public record of what drug and device companies paid each doctor ([CMS Open Payments](https://openpaymentsdata.cms.gov/)).

The dashboard uses a customs-checkpoint metaphor. Each paper is a traveller with a declaration form, the payments record is the X-ray, and a mismatch sends the paper to the **red channel** for an editor's question.

## What the scan found (Oct 2023 – Oct 2026)

| | |
|---|---|
| Open-access papers with US authors, 40 clinical journals | 2,878 |
| US authors matched and checked | 16,541 |
| Authors with undeclared industry payments (red) | 1,814 |
| Papers with at least one red author | 967 |
| Hand check of 20 random red cases | about 9 in 10 correct |

A red channel is a question, not a finding of misconduct. Journal policies differ on what must be declared, some disclosures may reach the editor without being printed, and only US clinicians appear in the payment record.

## Why it matters

- **Publishers:** a disclosure check that runs on every submission and gives editors the evidence plus a draft query, instead of trusting the form.
- **Readers and reviewers:** context on industry relationships behind a paper.
- **What it shows about AI:** rules handle the clear cases; an AI model reads partial disclosures ("declared Pfizer, but not Bayer?") and understands corporate groups and author initials.

## How it works

```
python run.py            # all four steps
python run.py --from 3   # re-flag only, e.g. after changing rules in config.yaml
```

| Step | File | What it does |
|---|---|---|
| 1 Papers | `pipeline/s1_papers.py` | Fetches open-access full text from Europe PMC; extracts US authors, affiliations and the conflict-of-interest statement |
| 2 Payments | `pipeline/s2_payments.py` | Matches each author to one Open Payments profile (name + state + city in the affiliation) and pulls payments by company and type |
| 3 Flag | `pipeline/s3_flag.py` | Compares declared vs paid in the 3 calendar years before publication. Rules for "no conflicts" statements, corporate-group matching (`companies.py`), and an LLM for partial disclosures |
| 4 Publish | `pipeline/s4_publish.py` | Writes anonymised `docs/data/*.json` for the dashboard and a private verification sample |

All settings (dates, look-back, thresholds, matching, model) live in `config.yaml`. Every web response is cached locally, so re-runs are fast and cost nothing extra. Logs show a timestamp and done/total progress.

## Privacy

The public data contains no names, papers or journals. Authors are shown by specialty and US region, with amounts rounded to the nearest $1,000. The un-anonymised results, the journal list, caches and API keys stay in `private/`, which is not committed.

## Requirements

Python 3.10+, `requests`, `pyyaml`. The LLM step uses an OpenAI-compatible endpoint; set `LLMFOUNDRY_TOKEN` in `private/.env` or turn it off in `config.yaml`.
