import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from utils import logger


class ExtractionError(Exception):
    """Raised when text can't be extracted. The message is safe to show users."""


def extract_from_url(url: str) -> str:
    """Download a web page and return its readable text."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ExtractionError("Please enter a full URL starting with http:// or https://")

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (AI Summarizer project)"},
        )
        response.raise_for_status()  # turns 404, 500 etc. into exceptions
    except requests.exceptions.Timeout as e:
        logger.error("URL timeout: %s", url)
        raise ExtractionError("The website took too long to respond.") from e
    except requests.exceptions.RequestException as e:
        logger.error("URL fetch failed: %s (%s)", url, e)
        raise ExtractionError("Could not load that page. Check the URL and try again.") from e

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove page parts that are not the main content
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Prefer the main article area if the page has one
    main = soup.find("article") or soup.find("main") or soup.body or soup

    lines = [line.strip() for line in main.get_text(separator="\n").splitlines()]
    text = "\n".join(line for line in lines if line)

    if len(text) < 200:
        raise ExtractionError(
            "Not enough readable text found. The page may need JavaScript or a login."
        )
    logger.info("Extracted %d characters from %s", len(text), url)
    return text


def extract_from_pdf(file) -> str:
    """Return the text of every page in a PDF (file-like object)."""
    try:
        reader = PdfReader(file)
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        logger.error("PDF read failed: %s", e)
        raise ExtractionError("Could not read this PDF. It may be corrupted or encrypted.") from e

    text = "\n".join(pages).strip()
    if not text:
        raise ExtractionError("No text found. This PDF may be a scanned image.")
    return text


def extract_from_txt(file) -> str:
    """Read a plain text file."""
    text = file.read().decode("utf-8", errors="ignore").strip()
    if not text:
        raise ExtractionError("The file is empty.")
    return text