import csv, os, re

out = os.path.expanduser("~/benchmarks")

all_runs = [f"ch{i}_ungrounded.csv" for i in range(1, 15)]
all_runs += ["supplement_ch1.csv", "supplement_ch4.csv", "supplement_ch5.csv",
             "rerun_empty_responses.csv", "rerun_persistent.csv",
             "rerun_all_empties.csv", "rerun_final_v2.csv",
             "rerun_multipart_1-3.csv", "rerun_multipart_4-6.csv",
             "rerun_multipart_7-11.csv", "rerun_multipart_12-14.csv",
             "rerun_salvage_empties.csv", "rerun_multi_value_single.csv"]

old = {}
for fname in all_runs:
    path = os.path.join(out, fname)
    if not os.path.exists(path): continue
    with open(path) as f:
        next(f)
        for line in f:
            parts = line.split(",")
            if len(parts) < 8: continue
            prob = parts[2]; ans = parts[7].strip().strip('"')
            model = "Pro" if "pro" in parts[4].lower() else "Flash"
            if ans and ((prob, model) not in old or len(ans) > len(old[(prob, model)])):
                old[(prob, model)] = ans

new = {}
for fname in ["rerun_targeted_pro.csv", "rerun_targeted_flash.csv"]:
    path = os.path.join(out, fname)
    if not os.path.exists(path): continue
    with open(path) as f:
        next(f)
        for line in f:
            parts = line.split(",")
            if len(parts) < 8: continue
            prob = parts[2]; ans = parts[7].strip().strip('"')
            model = "Pro" if "pro" in parts[4].lower() else "Flash"
            if ans:
                new[(prob, model)] = ans

lines = []
lines.append("=" * 80)
lines.append("TARGETED RE-RUN — Updated Answers (Old vs New)")
lines.append("Copy NEW values into your Google Sheets cells.")
lines.append("=" * 80)
lines.append("")

changed = 0
def safe_key(k):
    """Robust sort key that handles garbled data."""
    try:
        parts = k[0].split(".")
        return (int(parts[0]), int(parts[1]), k[1])
    except (ValueError, IndexError):
        return (999, 0, "")

for key in sorted(new, key=safe_key):
    prob, model = key
    new_ans = new[key]
    new_clean = re.sub(r'^FINAL ANSWER:\s*', '', new_ans).strip()
    old_ans = old.get(key, "")
    old_clean = re.sub(r'^FINAL ANSWER:\s*', '', old_ans).strip() if old_ans else "(was empty)"
    if new_clean == old_clean: continue
    changed += 1
    lines.append(f"#{prob}  {model}:")
    lines.append(f"  OLD: {old_clean[:120]}")
    lines.append(f"  NEW: {new_clean[:120]}")
    lines.append("")

lines.append(f"Total updated: {changed} entries")

with open(os.path.join(out, "targeted_rerun_fixes.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Saved ({changed} entries changed)")
