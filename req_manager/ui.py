from __future__ import annotations

from pathlib import Path

import streamlit as st


STREAMLIT_COMPAT_CSS = """
/* Streamlit compatibility layer for score.css (LAD) */
.stApp, .stApp * {
  font-family: var(--lad-font, "Oracle Sans", "Helvetica Neue", Arial, sans-serif) !important;
}

.stApp {
  background: var(--lad-bg, #ffffff) !important;
  color: var(--lad-text, #111111) !important;
}

.stApp .block-container {
  max-width: min(1960px, 98vw);
  padding-top: 1.2rem;
  padding-bottom: 2rem;
}

.stApp h1, .stApp h2, .stApp h3 {
  color: var(--lad-text, #111111) !important;
  letter-spacing: -0.01em;
  font-weight: 800;
}

.stApp [data-testid="stMetric"] {
  background: #ffffff !important;
  border: 1px solid var(--lad-border-soft, #d9d9d9) !important;
  border-radius: 3px !important;
  padding: 10px 12px;
}

.stApp .kpi-card,
.stApp .section-box,
.stApp .info-box {
  background: #ffffff !important;
  border: 1px solid var(--lad-border-soft, #d9d9d9) !important;
  border-radius: 3px !important;
  box-shadow: var(--lad-shadow-card, 0 1px 3px rgba(0, 0, 0, .28));
}

.stApp .kpi-card { padding: 12px 14px; }
.stApp .kpi-label { color: var(--lad-muted, #5d6368) !important; font-size: .85rem; }
.stApp .kpi-value { color: var(--lad-text, #111111) !important; font-weight: 800; font-size: 1.4rem; }
.stApp .section-box { padding: 14px; }
.stApp .info-box { padding: 10px 12px; }

.stApp [data-testid="stDataFrame"] {
  border: 1px solid var(--lad-border-table, #d4d4d4) !important;
  border-radius: 3px !important;
  overflow: hidden;
  background: #fff !important;
}

.stApp [data-testid="stDataFrame"] thead tr th {
  background: var(--lad-teal-header, #155f67) !important;
  color: #fff !important;
  border-color: #ffffff !important;
}

.stApp [data-testid="stDataFrame"] tbody tr:nth-child(even) td {
  background: #fbfbfb !important;
}

.stApp .stButton > button,
.stApp .stFormSubmitButton > button {
  min-height: 2.2rem;
  border-radius: 3px !important;
  border: 1px solid var(--lad-control-border, #a8a8a8) !important;
  background: var(--lad-teal, #1f6671) !important;
  color: #fff !important;
  font-weight: 700;
}

.stApp .stButton > button:hover,
.stApp .stFormSubmitButton > button:hover {
  background: var(--lad-teal-dark, #15555f) !important;
  border-color: var(--lad-teal-dark, #15555f) !important;
}

.stApp [data-baseweb="input"] > div,
.stApp [data-baseweb="select"] > div,
.stApp textarea {
  border-radius: 3px !important;
  border-color: var(--lad-control-border, #a8a8a8) !important;
}

.stApp [data-testid="stSidebar"] {
  background: #fff !important;
  border-right: 1px solid var(--lad-border-soft, #d9d9d9) !important;
}

.stApp .stTabs [role="tab"][aria-selected="true"] {
  color: var(--lad-teal, #1f6671) !important;
  border-bottom-color: var(--lad-teal, #1f6671) !important;
}
"""


def apply_dashboard_css() -> None:
    css_path = Path(__file__).resolve().parent.parent / "assets" / "dashboard.css"
    if not css_path.exists():
        return

    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}\n{STREAMLIT_COMPAT_CSS}</style>", unsafe_allow_html=True)
