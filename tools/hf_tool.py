"""
hf_tool.py — load an open dataset from the Hugging Face Hub into a DataFrame.

This is the "real data connectivity" step: instead of only the FlowDash demo SQLite
or an uploaded CSV, the agent can pull any public dataset by id (imdb, tweet_eval,
openai/gsm8k, …), row-capped and streamed so it never downloads gigabytes, and hand
it straight to the generic profiler / cleaning / analysis tools.

Usage:
    python tools/hf_tool.py imdb                       # first rows of the train split
    python tools/hf_tool.py tweet_eval emotion --limit 2000
    python tools/hf_tool.py openai/gsm8k main --split test

Network note: the Hub must be reachable. This runs anywhere with normal internet;
some locked-down sandboxes block huggingface.co — in that case run it on your machine.
"""
import sys

import pandas as pd

DEFAULT_LIMIT = 5000


def _profiler_safe(df):
    """HF rows often contain list/dict/image cells. The tabular profiler wants
    scalars — stringify anything non-scalar so profiling/cleaning still works,
    and report which columns were flattened."""
    flattened = []
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, (list, dict, tuple, set, bytes))).any():
            df[col] = df[col].map(lambda v: "" if v is None else str(v))
            flattened.append(str(col))
    return df, flattened


def load(dataset_id, config=None, split="train", limit=DEFAULT_LIMIT):
    """Return (df, meta). Streams up to `limit` rows so big datasets stay cheap.
    Raises a clear error if the Hub is unreachable or the id is wrong."""
    from datasets import load_dataset          # imported lazily (optional dep)
    rows = []
    try:
        stream = load_dataset(dataset_id, config, split=split, streaming=True)
        for i, row in enumerate(stream):
            if i >= limit:
                break
            rows.append(row)
        df = pd.DataFrame(rows)
        truncated = len(df) >= limit
    except Exception:
        # some datasets don't support streaming — fall back to a capped slice
        ds = load_dataset(dataset_id, config, split=f"{split}[:{limit}]")
        df = ds.to_pandas()
        truncated = False
    df, flattened = _profiler_safe(df)
    meta = {"dataset": dataset_id, "config": config, "split": split,
            "rows": len(df), "cols": df.shape[1], "truncated": truncated,
            "flattened_columns": flattened}
    return df, meta


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = DEFAULT_LIMIT
    split = "train"
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        if a.startswith("--split"):
            split = a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
    if not args:
        print("usage: hf_tool.py <dataset_id> [config] [--split train] [--limit 5000]")
        sys.exit(1)
    dataset_id = args[0]
    config = args[1] if len(args) > 1 else None
    try:
        df, meta = load(dataset_id, config, split, limit)
    except Exception as e:
        print(f"❌ Could not load {dataset_id}: {e}")
        print("   (If you're in a locked-down sandbox, the Hub may be blocked — run on your machine.)")
        sys.exit(1)
    print(f"Loaded {meta['dataset']} [{meta['split']}] — {meta['rows']} rows × {meta['cols']} cols"
          + (f" (capped at {limit})" if meta["truncated"] else ""))
    if meta["flattened_columns"]:
        print("Flattened non-scalar columns:", ", ".join(meta["flattened_columns"]))
    print(df.head().to_string()[:1200])
