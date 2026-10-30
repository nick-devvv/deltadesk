"""walk_forward.py - chronological evaluation with no peeking.

Splits are by SESSION (calendar day), shared by every symbol, so one market day is never training data for one ticker
and test data for another. Each outer fold trains only on sessions before it, chooses its parameters there (with an
optional inner chronological validation), freezes them, then evaluates the next block once. Outcomes are intraday and
flat by 15:25, so no label crosses a session boundary; `embargo` sessions can still be skipped between train and test
when a study uses multi-session horizons. Re-running a fold with new choices is a new experiment, logged as such.
"""


def folds(sessions, test_size, min_train, embargo=0, step=None):
    """Expanding-window folds: [(train_sessions, test_sessions), ...] in time order."""
    s = sorted(set(sessions))
    step = step or test_size
    out = []
    start = min_train
    while start + embargo + test_size <= len(s):
        train = s[:start]
        test = s[start + embargo:start + embargo + test_size]
        out.append((train, test))
        start += step
    return out


def inner_split(train_sessions, frac=0.7):
    """Inner chronological validation inside a training window (earlier part fits, later part validates)."""
    s = sorted(train_sessions)
    k = max(1, int(len(s) * frac))
    return s[:k], s[k:]


def run(rows, select, evaluate, test_size=5, min_train=10, embargo=0):
    """rows: [{session, ...}]. select(train_rows) -> frozen params (sees ONLY training rows). evaluate(test_rows, params)
    -> result. Returns per-fold records with the params that were frozen before the test block was seen."""
    sess = sorted({r["session"] for r in rows})
    out = []
    for i, (tr, te) in enumerate(folds(sess, test_size, min_train, embargo)):
        trs, tes = set(tr), set(te)
        params = select([r for r in rows if r["session"] in trs])
        res = evaluate([r for r in rows if r["session"] in tes], params)
        out.append({"fold": i, "train": [tr[0], tr[-1]], "test": [te[0], te[-1]], "params": params, "result": res})
    return out
