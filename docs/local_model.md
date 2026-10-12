# Local model for $0 dev runs (llama.cpp + Gemma)

Live Gemini matrices cost real money (~21–26k tokens/run with thinking on).
For day-to-day harness debugging, run a small local model instead and reserve
Gemini for final numbers. Provider comparisons are NEVER mixed: a ladder table
is either all-local or all-Gemini.

## 1. Install llama.cpp (Windows)

Download a release zip from
`github.com/ggerganov/llama.cpp/releases` (pick the CUDA build if you have an
NVIDIA GPU, else the plain CPU/AVX2 build) and unzip, e.g. to
`C:\tools\llama.cpp`. You need `llama-server.exe` on PATH or referenced below.

## 2. Download a Gemma GGUF (~2.5 GB)

Any OpenAI-compatible GGUF works; the reference pick is Gemma 3 4B quantized:

- HuggingFace `bartowski/google_gemma-3-4b-it-GGUF`, file
  `google_gemma-3-4b-it-Q4_K_M.gguf` → save as e.g.
  `C:\models\gemma-3-4b-q4km.gguf`

(Exact filename is your choice — nothing in the harness depends on it.)

## 3. Start the server

```powershell
C:\tools\llama.cpp\llama-server.exe -m C:\models\gemma-3-4b-q4km.gguf `
  --port 8080 -c 8192
```

Check health: open `http://localhost:8080/health` (should say no-op ok).

## 4. Point Lever at it

```powershell
$env:LEVER_LOCAL_URL = "http://localhost:8080/v1"
$env:LEVER_LOCAL_MODEL = "gemma-3-4b"
```

Or add both to `.env` (never commit `.env`).

## 5. Smoke test ($0)

```powershell
# single task, headless CLI
uv run lever run --repo bug-repo --task "Read add.py." --provider local --max-steps 5

# eval pilot: 2 tasks x 1 seed, local backend+provider (no confirm needed — free)
uv run python evals/runner.py --tasks b01 b02 --seeds 1 --provider local --out evals/results/local_smoke.jsonl
```

## Caveats (read before citing numbers)

- A 4B local model is much weaker than Gemini: expect low pass rates and shaky
  tool use. That is FINE for debugging (crashes, loops, error paths) and USELESS
  for headline claims. ladders stay single-provider for fair comparisons.
- No thinking/signatures server-side: `count_tokens` is chars//4; token and cost
  columns from local runs are estimates, not bills.
- Small models may ignore tool schemas or emit malformed arguments — the
  provider surfaces `_raw` args and clear errors instead of crashing the run.
