"""Targeted re-run harness — supports single-model runs."""
import os, sys, json, csv, time, argparse
from datetime import datetime
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are solving a university-level physics problem.\n\n"
    "If the problem has multiple parts (a, b, c, etc.) or is multiple choice, "
    "answer ALL parts. If a single problem contains a single or multiple parts "
    "but a part requires more than 1 answer (553 N, 30 degrees), "
    "you must state all answers.\n\n"
    "Format (and examples):\n"
    "- Single part: FINAL ANSWER: 553 N\n"
    "- Single part with more than one answer: FINAL ANSWER: 553 N, 30 degrees\n"
    "- Multiple choice: FINAL ANSWER: (c)\n"
    "- Multi-part with choices: FINAL ANSWER: (a) 5.0 m/s  (b) (d)  (c) 120 N\n"
    "- Multi-part numerical: FINAL ANSWER: (a) 1480 m  (b) 1.85 cm\n"
    "- Multi-part with a part having more than one answer: "
    "FINAL ANSWER: (a) 1480 m, 45 degrees east  (b) 1.85 cm\n\n"
    "Do not show your reasoning or work. Commit to ONE answer per part. "
    "No extra text."
)

BASE_URL = "https://api.deepseek.com"
TEMPERATURE = 0.0
MAX_TK = 4000
RETRY_SEC = 2


def write_header(output_path):
    if not os.path.exists(output_path):
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["volume","chapter","problem","condition","model",
                         "use_context","success","answer","error","timestamp"])


def write_result(output_path, result):
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([result["volume"],result["chapter"],result["problem"],
                     result["condition"],result["model"],result["use_context"],
                     result["success"],result["answer"],result["error"],
                     result["timestamp"]])


def call_model(api_key, model, user_prompt):
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    result = {"success": False, "answer": "", "error": "",
              "model": model, "timestamp": datetime.now().isoformat()}
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages,
                temperature=TEMPERATURE, max_tokens=MAX_TK)
            result["success"] = True
            result["answer"] = response.choices[0].message.content or ""
            return result
        except Exception as e:
            err = str(e)
            if "rate" in err.lower() or "429" in err:
                time.sleep(RETRY_SEC * (attempt + 1))
                continue
            result["error"] = err
            return result
    result["error"] = "Max retries (rate limit)"
    return result


def run(api_key, problems, output_path, model_name, condition_name):
    write_header(output_path)
    done = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 4:
                    done.add(f"{row[2]}_{row[3]}")
    total = len(problems)
    print(f"\n{model_name}: {total} problems")
    print(f"Already done: {len(done)}  Remaining: {total - len(done)}\n")
    t0 = time.time()
    for i, prob in enumerate(problems):
        pid = prob["problem"]
        ptext = prob["problem_text"]
        key = f"{pid}_{condition_name}"
        if key in done:
            print(f"  [{i+1}/{total}] {pid}: SKIP")
            continue
        r = call_model(api_key, model_name, ptext)
        r.update({"problem": pid, "chapter": prob.get("chapter", 0),
                   "volume": prob.get("volume", ""),
                   "condition": condition_name, "use_context": False})
        write_result(output_path, r)
        done.add(key)
        ok = "OK" if r["success"] else "FAIL"
        prev = r["answer"][:100].replace("\n", " ") if r["answer"] else "(empty)"
        print(f"  [{i+1}/{total}] {pid}: {ok} | {prev}")
        time.sleep(0.3)
    elapsed = time.time() - t0
    print(f"\nDONE in {elapsed:.0f}s")


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import subprocess
        r = subprocess.run(["grep", "DEEPSEEK_API_KEY",
                           os.path.expanduser("~/.hermes/.env")],
                          capture_output=True, text=True)
        if r.stdout:
            parts = r.stdout.strip().split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"').strip("'")
    except:
        pass
    return None


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--problems", required=True)
    p.add_argument("--output", default="targeted_rerun.csv")
    p.add_argument("--model", required=True,
                   choices=["deepseek-v4-pro", "deepseek-v4-flash"])
    p.add_argument("--condition", default="Targeted")
    args = p.parse_args()
    api_key = get_api_key()
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found")
        sys.exit(1)
    with open(args.problems) as f:
        problems = json.load(f)
    run(api_key, problems, args.output, args.model, args.condition)
