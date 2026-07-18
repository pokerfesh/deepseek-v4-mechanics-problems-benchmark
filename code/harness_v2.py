"""
Incremental benchmark harness — writes every result to CSV immediately.
Safe to kill and resume mid-run.
"""
import os, sys, json, csv, time, argparse
from datetime import datetime
from openai import OpenAI

SYSTEM_UNGROUNDED = (
    "You are solving a university-level physics problem. "
    "Provide only your final numerical answer, in exactly this format:\n"
    "FINAL ANSWER: [value with unit]\n\n"
    "Do not show your reasoning or work. "
    "Do not provide multiple possible answers - commit to one final numerical answer."
)

SYSTEM_GROUNDED = (
    "You are solving a university-level physics problem. "
    "You are given the relevant textbook chapter for reference. Use it as needed.\n\n"
    "Provide only your final numerical answer, in exactly this format:\n"
    "FINAL ANSWER: [value with unit]\n\n"
    "Do not show your reasoning or work. "
    "Do not provide multiple possible answers - commit to one final numerical answer."
)

BASE_URL = "https://api.deepseek.com"
MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]
TEMPERATURE = 0.0
MAX_TOKENS = 4000
RETRY_DELAY = 2

# Track which condition combos have been done (saved to .checkpoint file)
checkpoint = set()
writer_handle = None


def load_checkpoint(output_path):
    """Load completed test keys from existing CSV."""
    done = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # header
            for row in reader:
                if len(row) >= 4:
                    done.add(f"{row[2]}_{row[3]}")
    return done


def write_header(output_path):
    """Write CSV header if file doesn't exist."""
    if not os.path.exists(output_path):
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["volume", "chapter", "problem", "condition", "model",
                         "use_context", "success", "answer", "error", "timestamp"])


def write_result(output_path, result):
    """Append a single result row to the CSV immediately."""
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([result["volume"], result["chapter"], result["problem"],
                     result["condition"], result["model"], result["use_context"],
                     result["success"], result["answer"], result["error"],
                     result["timestamp"]])


def call_deepseek(api_key, model, system_prompt, user_prompt):
    """Single-turn, STATELESS call."""
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    result = {
        "success": False, "answer": "", "error": "",
        "model": model, "timestamp": datetime.now().isoformat()
    }

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages,
                temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
            )
            result["success"] = True
            result["answer"] = response.choices[0].message.content or ""
            return result
        except Exception as e:
            err = str(e)
            if "rate" in err.lower() or "429" in err:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            result["error"] = err
            return result

    result["error"] = "Max retries (rate limit)"
    return result


def run_benchmark(api_key, problems, chapter_contexts, output_path, mode):
    write_header(output_path)
    done = load_checkpoint(output_path)

    if mode == "ungrounded":
        conditions = [("Pro-Ungrounded", "deepseek-v4-pro", False),
                      ("Flash-Ungrounded", "deepseek-v4-flash", False)]
    elif mode == "grounded":
        conditions = [("Pro-Grounded", "deepseek-v4-pro", True),
                      ("Flash-Grounded", "deepseek-v4-flash", True)]
    else:
        conditions = [("Pro-Ungrounded", "deepseek-v4-pro", False),
                      ("Flash-Ungrounded", "deepseek-v4-flash", False),
                      ("Pro-Grounded", "deepseek-v4-pro", True),
                      ("Flash-Grounded", "deepseek-v4-flash", True)]

    total = len(problems) * len(conditions)
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {len(problems)} problems x {len(conditions)} = {total} tests")
    print(f"Already done: {len(done)}  Remaining: {total - len(done)}")
    print(f"Mode: {mode}  Temp: {TEMPERATURE}")
    print(f"Incremental save to: {output_path}")
    print(f"{'='*60}\n")

    t0 = time.time()

    for i, prob in enumerate(problems):
        ch = prob.get("chapter", 0)
        pid = prob.get("problem", "?")
        ptext = prob.get("problem_text", "")
        chtext = chapter_contexts.get(str(ch), "")

        if not ptext:
            print(f"  [{i+1}/{len(problems)}] {pid}: SKIP")
            continue

        for cname, model, use_ctx in conditions:
            key = f"{pid}_{cname}"
            if key in done:
                print(f"  [{i+1}/{len(problems)}] {pid} {cname}: SKIP (already done)")
                continue

            if use_ctx:
                sp = SYSTEM_GROUNDED
                if chtext:
                    sp += f"\n\nReference (University Physics Ch.{ch}):\n\n{chtext[:8000]}"
            else:
                sp = SYSTEM_UNGROUNDED

            r = call_deepseek(api_key, model, sp, ptext)
            r.update({
                "problem": pid, "chapter": ch,
                "volume": prob.get("volume", ""),
                "condition": cname, "use_context": use_ctx,
            })
            
            # Write immediately — safe to kill after this line
            write_result(output_path, r)
            done.add(key)

            ok = "OK" if r["success"] else "FAIL"
            prev = r["answer"][:80].replace("\n", " ") if r["answer"] else "(empty)"
            print(f"  [{i+1}/{len(problems)}] {pid} {cname}: {ok} | {prev}")
            time.sleep(0.3)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE in {elapsed:.0f}s")
    print(f"  Output: {output_path}")


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--problems")
    p.add_argument("--contexts")
    p.add_argument("--mode", default="ungrounded",
                   choices=["ungrounded", "grounded", "all"])
    p.add_argument("--output", default="benchmark_results.csv")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    api_key = get_api_key()
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found")
        sys.exit(1)

    if not args.problems:
        print("ERROR: --problems required")
        sys.exit(1)

    with open(args.problems, "r", encoding="utf-8") as f:
        problems = json.load(f)

    contexts = {}
    if args.contexts:
        with open(args.contexts, "r", encoding="utf-8") as f:
            contexts = json.load(f)

    if args.limit > 0:
        problems = problems[:args.limit]

    run_benchmark(api_key, problems, contexts, args.output, args.mode)
