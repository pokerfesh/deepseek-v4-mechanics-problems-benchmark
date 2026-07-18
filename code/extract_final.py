import pymupdf
import re
import json
import os

base = r"TEXTBOOK_PATH"

volumes = [
    ("Vol1", "University Physics Volume 1 (Chapters 1-20) (1).pdf", range(1, 21)),
    ("Vol2", "University Physics Volume 2 (Chapters 21-37).pdf", range(21, 38)),
    ("Vol3", "University Physics with Modern Physics Volume 3.pdf", range(38, 45)),
]

all_problems = []

for vol_name, fname, valid_chapters in volumes:
    path = os.path.join(base, fname)
    print(f"\n{'='*60}")
    print(f"Processing {vol_name}")

    doc = pymupdf.open(path)
    toc = doc.get_toc()
    answers_page = None
    for entry in toc:
        if 'Answer' in entry[1] and 'Odd' in entry[1]:
            answers_page = entry[2] - 1
            break
    
    if answers_page is None:
        doc.close()
        continue

    # Full text — no column splitting
    answers_text = ""
    for p in range(answers_page, doc.page_count):
        answers_text += doc[p].get_text() + "\n"
    doc.close()

    # Match all valid-chapter problem entries
    prob_pattern = re.compile(
        r'^(' + '|'.join(str(c) for c in valid_chapters) + r')\.(\d+)\s+(.+)',
        re.MULTILINE
    )
    raw_matches = list(prob_pattern.finditer(answers_text))
    print(f"  Raw matches: {len(raw_matches)}")

    vol_problems = []
    for i, pm in enumerate(raw_matches):
        chap = int(pm.group(1))
        prob = int(pm.group(2))
        answer_start = pm.start(3)
        
        # Only odd, reasonable range
        if prob % 2 == 0 or prob > 110:
            continue
        
        # Get answer text (up to next match or end)
        if i + 1 < len(raw_matches):
            answer_end = raw_matches[i + 1].start()
        else:
            answer_end = len(answers_text)
        
        full_answer = answers_text[answer_start:answer_end].strip()
        full_answer = re.sub(r'\s+', ' ', full_answer)
        
        # Skip photo credits
        if full_answer.startswith('p. ') or 'Shutterstock' in full_answer or 'Getty' in full_answer:
            continue
        if 'Answers to Odd-Numbered' in full_answer:
            continue
        # Clean trailing bleed and truncate if answer absorbed next chapter
        full_answer = re.sub(r'\s+', ' ', full_answer)
        # If answer absorbed next chapter, truncate at "Chapter N" marker
        ch_marker = re.search(r'\s+Chapter\s+\d+\b', full_answer)
        if ch_marker:
            full_answer = full_answer[:ch_marker.start()]
        full_answer = re.sub(r'\s*Chapter\s+\d+\s*$', '', full_answer).strip()
        full_answer = re.sub(r'\s*Answers to Odd-Numbered.*$', '', full_answer).strip()
        
        # Cap at 500 chars (real physics answers are shorter)
        if len(full_answer) > 500:
            continue
        
        if not full_answer:
            continue
        
        vol_problems.append({
            'volume': vol_name,
            'chapter': chap,
            'problem': f"{chap}.{prob}",
            'answer': full_answer
        })

    # FILTER constants BEFORE dedup (so they don't win on shortness)
    vol_problems = [p for p in vol_problems 
                    if not re.match(r'^\*\s*10\^?\d', p['answer'].strip())
                    and not p['answer'].strip().startswith('A-')
                    and int(p['problem'].split('.')[1]) <= 100]

    # Dedup: keep SHORTEST of remaining (real answers are brief)
    seen = {}
    for p in vol_problems:
        key = p['problem']
        if key not in seen or len(p['answer']) < len(seen[key]['answer']):
            seen[key] = p

    deduped = list(seen.values())
    all_problems.extend(deduped)
    
    from collections import Counter
    by_ch = Counter(p['chapter'] for p in deduped)
    print(f"  {len(deduped)} problems across {len(by_ch)} chapters")
    for ch in sorted(by_ch):
        print(f"    Ch.{ch}: {by_ch[ch]}")

# Final stats
print(f"\n{'='*60}")
print(f"TOTAL: {len(all_problems)}")
for vol in ["Vol1", "Vol2", "Vol3"]:
    count = sum(1 for p in all_problems if p['volume'] == vol)
    print(f"  {vol}: {count} problems")

# Verify previously-missing problems
checks = ['6.5', '6.37', '1.19', '1.43', '3.23', '3.39', '4.31', '5.29']
print(f"\nVerification of previously missing:")
for prob in checks:
    found = [p for p in all_problems if p['problem'] == prob]
    if found:
        print(f"  ✓ {prob}: {found[0]['answer'][:100]}")
    else:
        print(f"  ✗ {prob}: STILL MISSING")

# Spot-check Ch.4 and Ch.6
for ch_num in [4, 6]:
    ch = sorted([p for p in all_problems if p['chapter']==ch_num and p['volume']=='Vol1'],
                key=lambda x: int(x['problem'].split('.')[1]))
    probs = [int(p['problem'].split('.')[1]) for p in ch]
    print(f"\nCh.{ch_num} ({len(ch)}): first={probs[0]}, last={probs[-1]}, gaps={sorted(set(range(1,max(probs)+1,2)) - set(probs))[:10]}")

os.makedirs(os.path.expanduser("~/benchmarks"), exist_ok=True)
outpath = os.path.expanduser("~/benchmarks/university_physics_problems.json")
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(all_problems, f, indent=2, ensure_ascii=False)
print(f"\nSaved to {outpath}")
