"""Streamlit UI: streamlit run app.py"""

import streamlit as st
from dotenv import load_dotenv

from mtg_assistant import RulesAgent

load_dotenv()
st.set_page_config(page_title="MTG Rules Assistant", page_icon="🃏")
st.title("MTG Rules Assistant")
st.caption("Claude on AWS Bedrock + Scryfall. Answers are grounded in official Oracle text and rulings.")


@st.cache_resource
def get_agent() -> RulesAgent:
    return RulesAgent()


if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    st.chat_message(role).markdown(text)

if question := st.chat_input("e.g. Does deathtouch work with trample?"):
    st.chat_message("user").markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Looking up cards..."):
            result = get_agent().ask(question)
        st.markdown(result.answer)
        with st.expander("Tool calls"):
            st.json({"tool_calls": result.tool_calls, "usage": result.usage})
    st.session_state.history += [("user", question), ("assistant", result.answer)]
