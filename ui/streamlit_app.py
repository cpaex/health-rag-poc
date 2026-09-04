"""Streamlit UI, dual-mode (SPEC.md §9).

    AGENT_MODE=local     -> agent.supervisor.answer() in-process
    AGENT_MODE=agentcore -> InvokeAgentRuntime against the deployed runtime

    streamlit run ui/streamlit_app.py

All non-UI logic lives in ui/backend.py (unit-tested). Run with the `ui` extra:
    pip install -e ".[ui]"
"""

from __future__ import annotations

import os

import streamlit as st

from ui.backend import VALID_MODES, render_citations_markdown, resolve_mode, run_query

DEMO_SCOPES = ["patient-001", "patient-002", "patient-003"]
DEMO_QUESTIONS = [
    "Has this patient reacted badly to imaging contrast, and what precautions apply next time?",
    "List this patient's current active medications.",
    "Were there any anticoagulation problems after the diuretic dose was changed?",
]


def main() -> None:
    st.set_page_config(page_title="Clinical Agentic RAG", page_icon="🩺", layout="centered")
    st.title("🩺 Clinical Agentic RAG")
    st.caption("Decision support over **synthetic** clinical notes. Not for clinical use.")

    with st.sidebar:
        st.header("Session")
        default_mode = resolve_mode()
        mode = st.radio(
            "Execution mode",
            options=list(VALID_MODES),
            index=list(VALID_MODES).index(default_mode),
            help="local = in-process Strands supervisor · agentcore = deployed runtime",
        )
        patient_scope = st.selectbox("Authorized patient scope", DEMO_SCOPES)
        token = st.text_input(
            "Mock JWT (optional)",
            type="password",
            help="A base64url/JSON token with a patient_scope claim.",
        )
        if mode == "agentcore" and not os.environ.get("AGENTCORE_RUNTIME_ARN"):
            st.warning("AGENTCORE_RUNTIME_ARN is not set — agentcore mode will error.")

    question = st.text_area("Question", value=DEMO_QUESTIONS[0], height=100)
    with st.expander("Example questions"):
        for q in DEMO_QUESTIONS:
            st.markdown(f"- {q}")

    if st.button("Ask", type="primary"):
        with st.spinner(f"Running ({mode}) …"):
            view = run_query(question, patient_scope, mode=mode, token=token or None)

        if view.error:
            st.error(view.error)
        elif view.blocked:
            st.warning(f"Blocked by a safety / scope policy ({view.blocked_stage}).")
            if view.answer:
                st.markdown(view.answer)
        else:
            st.markdown(view.answer or "_No answer returned._")
            st.markdown(render_citations_markdown(view.citations))

        st.caption(f"mode: `{view.mode}` · scope: `{view.patient_scope or patient_scope}`")
        with st.expander("Raw response"):
            st.json(view.raw or {})


if __name__ == "__main__":
    main()
