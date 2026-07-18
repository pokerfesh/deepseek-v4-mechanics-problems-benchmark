import csv, os, re

out = os.path.expanduser("~/benchmarks")

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
            if ans and ((prob, model) not in new or len(ans) > len(new[(prob, model)])):
                new[(prob, model)] = ans

lines = []
lines.append("=" * 80)
lines.append("TARGETED RE-RUN — Full Results Dump")
lines.append("All NEW values for every problem re-run.")
lines.append("=" * 80)
lines.append("")

def safe_key(k):
    try:
        parts = k[0].split(".")
        return (int(parts[0]), int(parts[1]), k[1])
    except:
        return (999, 0, "")

count = 0
for key in sorted(new, key=safe_key):
    prob, model = key
    clean = re.sub(r'^FINAL ANSWER:\s*', '', new[key]).strip()
    lines.append(f"#{prob} {model}: {clean}")
    count += 1

lines.append("")
lines.append(f"Total: {count} entries")

with open(os.path.join(out, "targeted_rerun_full.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Saved: targeted_rerun_full.txt ({count} entries)")
