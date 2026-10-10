from __future__ import annotations

"""
python3 -m evaluation.dev_test_empty_normalization
"""

import pandas as pd

from evaluation.tools.comparators import AggComparator, MultiValueComparator, NumericComparator, StringLLMComparator
from evaluation.tools.config import EvalSettings
from evaluation.tools.utils import normalize_empty_cells


def _column_accuracy(df_pred: pd.DataFrame, df_gold: pd.DataFrame, column: str, comparator) -> float:
    correct = 0.0
    for pred_cell, gold_cell in zip(df_pred[column], df_gold[column]):
        score = comparator.compare(pred_cell, gold_cell)
        correct += 1.0 if score.f1 == 1.0 else 0.0
    return correct / len(df_gold) if len(df_gold) else 0.0


def main() -> None:
    settings = EvalSettings(llm_provider="none")
    numeric = NumericComparator(settings)
    string = StringLLMComparator(settings)
    multi = MultiValueComparator(settings)
    agg = AggComparator()

    gold_aligned = pd.DataFrame(
        {
            "id": ["1", None, "3", "4"],
            "num": [1.0, None, float("nan"), "null"],
            "text": ["Alice", "None", "", None],
            "multi": ["a||b", None, "n/a", ""],
            "agg_val": [10, None, "NaN", ""],
        }
    )
    pred_aligned = pd.DataFrame(
        {
            "id": ["1", "2", "3", "4"],
            "num": ["1", "None", "NaN", ""],
            "text": ["alice", "", "null", "  "],
            "multi": ["a||b", "None", "", "x"],
            "agg_val": ["10.0", "None", None, "null"],
        }
    )

    numeric_columns = ["num", "agg_val"]
    empty_tokens = ["none", "nan", "null", "n/a"]
    gold_clean = normalize_empty_cells(gold_aligned, numeric_columns=numeric_columns, empty_tokens=empty_tokens)
    pred_clean = normalize_empty_cells(pred_aligned, numeric_columns=numeric_columns, empty_tokens=empty_tokens)

    assert pd.isna(gold_clean.loc[1, "num"])
    assert pd.isna(pred_clean.loc[1, "num"])
    assert gold_clean.loc[1, "text"] == ""
    assert pred_clean.loc[2, "text"] == ""

    num_acc = _column_accuracy(pred_clean, gold_clean, "num", numeric)
    text_acc = _column_accuracy(pred_clean, gold_clean, "text", string)
    multi_acc = _column_accuracy(pred_clean, gold_clean, "multi", multi)
    agg_acc = _column_accuracy(pred_clean, gold_clean, "agg_val", agg)

    assert num_acc == 1.0
    assert text_acc == 1.0
    assert multi_acc == 0.75
    assert agg_acc == 1.0

    print("PASS: empty normalization + comparators behave as expected.")
    print(f"num_acc={num_acc:.2f} text_acc={text_acc:.2f} multi_acc={multi_acc:.2f} agg_acc={agg_acc:.2f}")


if __name__ == "__main__":
    main()

