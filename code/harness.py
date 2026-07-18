"""
University Physics Benchmark Harness
=====================================
Tests DeepSeek V4 Pro and Flash with/without chapter context.
Stateless: fresh messages array per API call, no session reuse.

Usage:
  python harness.py --verify
  python harness.py --problems probs.json --mode ungrounded
  python harness.py --problems probs.json --mode grounded --contexts ch.json
  python harness.py --problems probs.json --mode all --contexts ch.json
"""

import os, sys, json, csv, time, argparse
from datetime import datetime
from openai import OpenAI

# ── System Prompts (verbatim from experiment design) ──────

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

# ── Configuration ──────────────────────────────────────────

BASE_URL = "https://api.deepseek.com"
MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]
TEMPERATURE = 0.0
MAX_TOKENS = 4000
RETRY_DELAY = 2


def call_deepseek(api_key, model, system_prompt, user_prompt):
    """Single-turn, STATELESS call. Fresh client + messages each time."""
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


def verify_statelessness(api_key):
    """Empirical check: Q1 in call 1, then separate call asks what Q1 was."""
    print("=" * 60)
    print("STATELESSNESS VERIFICATION")
    print("=" * 60)

    r1 = call_deepseek(
        api_key, MODELS[0], SYSTEM_UNGROUNDED,
        "What is the acceleration due to gravity on Earth? Give just the number in m/s^2."
    )
    print(f"\nTrial 1: Q='What is gravity on Earth?'")
    print(f"  A: {r1['answer'][:200]}")

    r2 = call_deepseek(
        api_key, MODELS[0], SYSTEM_UNGROUNDED,
        "What was the previous question I asked you? If you don't know, say so."
    )
    print(f"\nTrial 2: Q='What was the previous question?'")
    print(f"  A: {r2['answer'][:200]}")

    leaked = any(w in r2['answer'].lower() for w in ['gravity', '9.8', '9.81', 'earth', 'acceleration'])
    if leaked:
        print("\nFAIL: Model shows state leakage. Harness is NOT stateless.")
        return False
    print("\nPASS: Model has no memory. Harness is stateless.")
    return True


def run_benchmark(api_key, problems, chapter_contexts, output_path, mode):
    """
    mode: 'ungrounded' (Pro + Flash, no context)
          'grounded'   (Pro + Flash, with chapter context)
          'all'        (all 4 conditions)
    """
    if mode == "ungrounded":
        conditions = [
            ("Pro-Ungrounded", "deepseek-v4-pro", False),
            ("Flash-Ungrounded", "deepseek-v4-flash", False),
        ]
    elif mode == "grounded":
        conditions = [
            ("Pro-Grounded", "deepseek-v4-pro", True),
            ("Flash-Grounded", "deepseek-v4-flash", True),
        ]
    else:  # all
        conditions = [
            ("Pro-Ungrounded", "deepseek-v4-pro", False),
            ("Flash-Ungrounded", "deepseek-v4-flash", False),
            ("Pro-Grounded", "deepseek-v4-pro", True),
            ("Flash-Grounded", "deepseek-v4-flash", True),
        ]

    total = len(problems) * len(conditions)
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {len(problems)} problems x {len(conditions)} conditions = {total} tests")
    print(f"Mode: {mode}  Temperature: {TEMPERATURE}  Max tokens: {MAX_TOKENS}")
    print(f"System prompt (ungrounded): {SYSTEM_UNGROUNDED[:80]}...")
    if mode != "ungrounded":
        print(f"System prompt (grounded):   {SYSTEM_GROUNDED[:80]}...")
    print(f"{'='*60}\n")

    results = []
    t0 = time.time()

    for i, prob in enumerate(problems):
        ch = prob.get("chapter", 0)
        pid = prob.get("problem", "?")
        ptext = prob.get("problem_text", "")
        chtext = chapter_contexts.get(str(ch), "")

        if not ptext:
            print(f"  [{i+1}/{len(problems)}] {pid}: SKIP (no problem_text)")
            continue

        for cname, model, use_ctx in conditions:
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
            results.append(r)

            ok = "OK" if r["success"] else "FAIL"
            prev = r["answer"][:80].replace("\n", " ") if r["answer"] else "(empty)"
            print(f"  [{i+1}/{len(problems)}] {pid} {cname}: {ok} | {prev}")
            time.sleep(0.3)

    elapsed = time.time() - t0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["volume", "chapter", "problem", "condition", "model",
                     "use_context", "success", "answer", "error", "timestamp"])
        for r in results:
            w.writerow([r["volume"], r["chapter"], r["problem"], r["condition"],
                        r["model"], r["use_context"], r["success"],
                        r["answer"], r["error"], r["timestamp"]])

    ok_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"DONE: {len(results)} tests in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Success: {ok_count}  Failed: {len(results)-ok_count}")
    print(f"  Output: {output_path}")
    for cname, _, _ in conditions:
        cr = [r for r in results if r["condition"] == cname]
        print(f"  {cname}: {sum(1 for r in cr if r['success'])}/{len(cr)}")


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
    p.add_argument("--verify", action="store_true")
    p.add_argument("--problems")
    p.add_argument("--contexts")
    p.add_argument("--mode", default="ungrounded",
                   choices=["ungrounded", "grounded", "all"])
    p.add_argument("--output", default="benchmark_results.csv")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    api_key = get_api_key()
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found in env or ~/.hermes/.env")
        sys.exit(1)

    if args.verify:
        ok = verify_statelessness(api_key)
        sys.exit(0 if ok else 1)

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
