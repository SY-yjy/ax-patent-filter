"""launch — 실제 배포 버전. experiment와 같은 엔진·같은 화면 셸.

실행:  streamlit run launch/app.py
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "engine"))

import streamlit as st
import ui_app

st.set_page_config(page_title="특허 판정 v4", page_icon="🚀", layout="wide")
ui_app.render_app("launch")
