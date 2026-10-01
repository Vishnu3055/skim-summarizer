import streamlit as st

from extractor import (
    ExtractionError,
    extract_from_pdf,
    extract_from_txt,
    extract_from_url,
)
from summerizer import SummarizerError, summarize
from utils import logger

st.set_page_config(page_title="Skim", layout="centered")

# A little CSS: narrower column, hide the default menu and footer
st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {max-width: 720px; padding-top: 3.5rem;}
    h1 {font-size: 2.4rem; margin-bottom: 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Skim")
st.write("Paste an article, drop in a link, or upload a PDF. Get the short version.")
st.write("")

source = st.radio(
    "Source",
    ["Paste text", "Link", "File"],
    horizontal=True,
    label_visibility="collapsed",
)

pasted = url = uploaded = None
if source == "Paste text":
    pasted = st.text_area(
        "Text",
        height=220,
        placeholder="Paste the article or notes you don't have time to read...",
        label_visibility="collapsed",
    )
elif source == "Link":
    url = st.text_input(
        "Link",
        placeholder="https://en.wikipedia.org/wiki/...",
        label_visibility="collapsed",
    )
else:
    uploaded = st.file_uploader(
        "File", type=["pdf", "txt"], label_visibility="collapsed"
    )

# Options sit right above the button instead of in a sidebar
LENGTHS = {"Brief": "short", "Standard": "medium", "Thorough": "detailed"}
col1, col2 = st.columns(2)
length_label = col1.selectbox("How long?", list(LENGTHS), index=1)
num_points = col2.number_input("Key points", min_value=3, max_value=7, value=3)

if st.button("Summarize", type="primary"):
    try:
        with st.spinner("Reading..."):
            if source == "Paste text":
                text = pasted
            elif source == "Link":
                text = extract_from_url(url or "")
            else:
                if uploaded is None:
                    raise SummarizerError("Please upload a file first.")
                if uploaded.name.lower().endswith(".pdf"):
                    text = extract_from_pdf(uploaded)
                else:
                    text = extract_from_txt(uploaded)

            result = summarize(text, LENGTHS[length_label], int(num_points))

        words_in = len(text.split())
        words_out = len(result["summary"].split())

        with st.container(border=True):
            st.markdown("**The short version**")
            st.write(result["summary"])
            st.markdown("**Worth remembering**")
            for point in result["key_takeaways"]:
                st.markdown(f"- {point}")

        st.caption(f"{words_in:,} words in, {words_out:,} words out")

    except (ExtractionError, SummarizerError) as e:
        st.error(str(e))
    except Exception:
        logger.exception("Unexpected error")
        st.error("Something went wrong on our end. Please try again.")