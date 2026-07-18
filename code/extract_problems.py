"""
Extract odd-numbered problems using ToC structure to identify chapters.
"""
import pymupdf, re, json, os

base = r"TEXTBOOK_PATH"

volumes = [
    ("Vol1", "University Physics Volume 1 (Chapters 1-20) (1).pdf", range(1, 21)),
    ("Vol2", "University Physics Volume 2 (Chapters 21-37).pdf", range(21, 38)),
    ("Vol3", "University Physics with Modern Physics Volume 3.pdf", range(38, 45)),
]

all_clean = []
all_manual = []

for vol_name, fname, valid_chapters in volumes:
    path = os.path.join(base, fname)
    doc = pymupdf.open(path)
    toc = doc.get_toc()
    
    # Build chapter -> problem page mapping from ToC
    # L2 entries are chapters like "4 Newton's Laws of Motion"
    # L3 entries include "Questions/Exercises/Problems"
    chapter_pages = {}  # chapter_number -> (chapter_page, problems_page)
    
    current_chapter = None
    current_chapter_page = None
    
    for entry in toc:
        level, title, page = entry
        
        if level == 2:
            # Chapter entry: "4 Newton's Laws of Motion"
            m = re.match(r'^(\d+)\s', title)
            if m:
                current_chapter = int(m.group(1))
                current_chapter_page = page
        
        elif level == 3 and current_chapter is not None:
            if 'Questions/Exercises/Problems' in title:
                chapter_pages[current_chapter] = (current_chapter_page, page)
    
    print(f"{vol_name}: found {len(chapter_pages)} chapter problem sections")
    
    for ch_num, (ch_page, prob_page) in sorted(chapter_pages.items()):
        if ch_num not in valid_chapters:
            continue
        
        # Scan forward from QEP page, collecting until we hit another chapter
        # Start a few pages before in case ToC is offset (e.g., Ch.41)
        start_page = max(0, prob_page - 4)
        text = ""
        for p in range(start_page, doc.page_count):
            page_text = doc[p].get_text()
            # Stop if we encounter another valid chapter's problem numbers
            if p > prob_page:
                other_ch = re.search(r'^(\d+)\.\d+\s', page_text, re.MULTILINE)
                if other_ch:
                    oc = int(other_ch.group(1))
                    if oc in valid_chapters and oc != ch_num:
                        break
            text += page_text + "\n"
        
        # Extract all problems for this chapter
        prob_pattern = re.compile(rf'^{ch_num}\.(\d+)\s+(.+)', re.MULTILINE)
        matches = list(prob_pattern.finditer(text))
        
        for i, pm in enumerate(matches):
            prob_num = int(pm.group(1))
            if prob_num % 2 == 0:
                continue
            
            answer_start = pm.start(2)
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = min(pm.end() + 600, len(text))
            
            raw = text[answer_start:end].strip()
            raw = re.sub(r'\s+', ' ', raw)
            
            # Cut at figure label bleed
            fig_cut = re.search(r'Figure\s+\w+\.\d+\s', raw)
            if fig_cut and fig_cut.start() > 10:
                raw = raw[:fig_cut.start()]
            
            if len(raw) < 15:
                continue
            
            problem_key = f"{ch_num}.{prob_num}"
            
            has_figure = bool(re.search(r'\(Fig\.|Figure\s+\w', raw))
            has_vector = bool(re.search(r'[A-Z]\s+S\b', raw))
            
            if has_figure or has_vector:
                reasons = []
                if has_figure: reasons.append("figure")
                if has_vector: reasons.append("vector-garbling")
                all_manual.append({
                    "volume": vol_name, "chapter": ch_num,
                    "problem": problem_key,
                    "reason": ", ".join(reasons),
                    "text_preview": raw[:200]
                })
            else:
                all_clean.append({
                    "volume": vol_name, "chapter": ch_num,
                    "problem": problem_key,
                    "problem_text": raw
                })
    
    doc.close()
    cc = sum(1 for p in all_clean if p['volume'] == vol_name)
    cm = sum(1 for p in all_manual if p['volume'] == vol_name)
    print(f"  -> {cc} CLEAN + {cm} MANUAL = {cc+cm} total")

# Cross-check
with open(os.path.expanduser("~/benchmarks/university_physics_problems.json"), "r", encoding="utf-8") as f:
    answers = json.load(f)
answer_keys = set(p['problem'] for p in answers)

clean_keys = set(p['problem'] for p in all_clean)
manual_keys = set(p['problem'] for p in all_manual)
extracted = clean_keys | manual_keys

missing = answer_keys - extracted

print(f"\n{'='*50}")
print(f"CLEAN:    {len(all_clean)}")
print(f"MANUAL:   {len(all_manual)}")
print(f"TOTAL:    {len(all_clean) + len(all_manual)}")
print(f"Answers:  {len(answers)}")
print(f"Matched:  {len(extracted & answer_keys)}")
print(f"Missing:  {len(missing)}")

if missing:
    # Show which chapters are missing
    from collections import Counter
    by_ch = Counter()
    for p in missing:
        ch = int(p.split('.')[0])
        by_ch[ch] += 1
    print("Missing by chapter:")
    for ch in sorted(by_ch):
        print(f"  Ch.{ch}: {by_ch[ch]} missing")

out = os.path.expanduser("~/benchmarks")
with open(f"{out}/problems_clean.json", "w", encoding="utf-8") as f:
    json.dump(all_clean, f, indent=2, ensure_ascii=False)
with open(f"{out}/problems_manual.json", "w", encoding="utf-8") as f:
    json.dump(all_manual, f, indent=2, ensure_ascii=False)
print(f"\nSaved.")
