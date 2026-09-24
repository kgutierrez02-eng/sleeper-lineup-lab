"""Display-only formatting; model calculations retain full precision."""

import re

import streamlit as st


SCORE_COLUMNS = {"Model score", "Week actual", "Mean points", "Latest points", "Weighted points",
                 "Std deviation", "Shrunk baseline", "Points for", "Points against", "Actual points",
                 "League median", "Your model / slot", "Peer median / slot", "Gap / slot",
                 "Model gap", "Model score lost"}


def score_columns(frame):
    return {name: st.column_config.NumberColumn(name, format="%.2f") for name in frame.columns
            if name in SCORE_COLUMNS or re.fullmatch(r"W\d+ actual", str(name))}


def score_table(frame, **kwargs):
    return st.dataframe(frame, hide_index=True, width="stretch", column_config=score_columns(frame), **kwargs)