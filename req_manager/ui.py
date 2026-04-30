from __future__ import annotations

from pathlib import Path

import streamlit as st


STREAMLIT_COMPAT_CSS = """
/* Streamlit compatibility layer for enterprise theme */
.stApp {
  background: var(--oracle-page-bg, #f7f7f6);
  color: var(--oracle-text, #161513);
}

.stApp .block-container {
  max-width: 1320px;
  padding-top: 1.2rem;
  padding-bottom: 2rem;
}

.stApp h1, .stApp h2, .stApp h3 {
  color: var(--oracle-black, #312d2a);
  letter-spacing: -0.01em;
}

.stApp [data-testid="stMetric"] {
  background: var(--oracle-card-bg, #fff);
  border: 1px solid var(--oracle-border, #d6d2cd);
  border-radius: 10px;
  padding: 10px 12px;
}

.stApp .kpi-card,
.stApp .section-box,
.stApp .info-box {
  background: var(--oracle-card-bg, #fff);
  border: 1px solid var(--oracle-border, #d6d2cd);
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.08);
}

.stApp .kpi-card {
  padding: 12px 14px;
}

.stApp .kpi-label {
  color: var(--oracle-muted, #6f6a64);
  font-size: 0.85rem;
}

.stApp .kpi-value {
  color: var(--oracle-black, #312d2a);
  font-weight: 700;
  font-size: 1.4rem;
}

.stApp .section-box {
  padding: 14px;
}

.stApp .info-box {
  padding: 10px 12px;
}

.stApp [data-testid="stDataFrame"] {
  border: 1px solid var(--oracle-border, #d6d2cd);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}

.stApp [data-testid="stDataFrame"] * {
  font-family: var(--oracle-font, "Oracle Sans", Arial, sans-serif);
}

.stApp .stButton > button,
.stApp .stFormSubmitButton > button {
  border-radius: 8px;
  border: 1px solid var(--oracle-border-dark, #b9b3ad);
  background: var(--oracle-purple, #3b263f);
  color: #fff;
  font-weight: 600;
}

.stApp .stButton > button:hover,
.stApp .stFormSubmitButton > button:hover {
  background: var(--oracle-purple-dark, #2f1e33);
  border-color: var(--oracle-purple-dark, #2f1e33);
}

.stApp [data-testid="stSidebar"] {
  background: var(--oracle-card-bg, #fff);
  border-right: 1px solid var(--oracle-border, #d6d2cd);
}

.stApp input, .stApp textarea, .stApp select {
  border-radius: 8px !important;
}
"""


def apply_dashboard_css() -> None:
    css_path = Path(__file__).resolve().parent.parent / "assets" / "dashboard.css"
    if not css_path.exists():
        return

    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}\n{STREAMLIT_COMPAT_CSS}</style>", unsafe_allow_html=True)
