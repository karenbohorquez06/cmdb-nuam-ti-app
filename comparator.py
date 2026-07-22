from dataclasses import dataclass
import pandas as pd
from typing import List

@dataclass
class ComparisonResult:
    added: pd.DataFrame
    removed: pd.DataFrame
    changed: pd.DataFrame
    unchanged: pd.DataFrame

def compare_dataframes(old_df, new_df, keys: List[str], cols: List[str]) -> ComparisonResult:
    old_df = old_df.set_index(keys, drop=False)
    new_df = new_df.set_index(keys, drop=False)

    added_idx = new_df.index.difference(old_df.index)
    removed_idx = old_df.index.difference(new_df.index)
    common_idx = old_df.index.intersection(new_df.index)

    added = new_df.loc[added_idx].reset_index(drop=True)
    removed = old_df.loc[removed_idx].reset_index(drop=True)

    changed_rows = []
    unchanged_rows = []

    for idx in common_idx:
        old_row = old_df.loc[idx]
        new_row = new_df.loc[idx]

        if isinstance(old_row, pd.DataFrame):
            old_row = old_row.iloc[0]
        if isinstance(new_row, pd.DataFrame):
            new_row = new_row.iloc[0]

        diff = {}
        for col in cols:
            if old_row[col] != new_row[col]:
                diff[col] = {"old": old_row[col], "new": new_row[col]}

        base = {k: new_row[k] for k in keys}

        if diff:
            changed_rows.append({**base, "cambios": diff})
        else:
            unchanged_rows.append(base)

    return ComparisonResult(
        pd.DataFrame(added),
        pd.DataFrame(removed),
        pd.DataFrame(changed_rows),
        pd.DataFrame(unchanged_rows),
    )