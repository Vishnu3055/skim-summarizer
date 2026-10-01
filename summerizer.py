import json
import os

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from utils import logger, retry_with_backoff

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# MAX_CHARS = 100_000  # temporary limit; Phase 5 will replace this with chunking
CHUNK_SIZE = 12_000     # characters per chunk
MAX_CHARS = 300_000     # hard limit so one request can't use up the free quota

LENGTH_INSTRUCTIONS = {
    "short": "in 2 to 3 sentences",
    "medium": "in one paragraph of about 5 to 6 sentences",
    "detailed": "in 2 to 3 paragraphs, covering all the main points",
}


class SummarizerError(Exception):
    """An error whose message is safe to show directly to the user."""


def friendly_message(code: int) -> str:
    """Translate an HTTP status code into something a user can understand."""
    if code == 429:
        return "Rate limit reached. Please wait a minute and try again."
    if code in (400, 401, 403):
        return "The API key is invalid or not allowed. Check GEMINI_API_KEY in .env."
    if code == 404:
        return "Model not found. Check GEMINI_MODEL in .env."
    if code >= 500:
        return "The AI service had a problem. Please try again shortly."
    return f"Unexpected API error (code {code})."


def parse_response(raw: str) -> dict:
    """Turn the model's JSON string into a dict and validate it."""
    if not raw:
        raise ValueError("Empty response from model")

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()

    data = json.loads(cleaned)

    if "summary" not in data or "key_takeaways" not in data:
        raise ValueError("Response is missing 'summary' or 'key_takeaways'")
    return data


@retry_with_backoff(max_retries=4, base_delay=1.0)
def call_llm(prompt: str, config: types.GenerateContentConfig) -> str:
    """The only function that talks to the API. Retries are handled by the decorator."""
    response = client.models.generate_content(
        model=MODEL, contents=prompt, config=config
    )
    return response.text
def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks of at most chunk_size characters, breaking on line boundaries."""
    chunks, current = [], ""
    for line in text.split("\n"):
        # A single line longer than chunk_size has to be cut manually
        while len(line) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:chunk_size])
            line = line[chunk_size:]

        if current and len(current) + len(line) + 1 > chunk_size:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current.strip():
        chunks.append(current)
    return chunks


def condense_long_text(text: str) -> str:
    """Summarize each chunk, then join the partial summaries into one shorter text."""
    chunks = split_into_chunks(text)
    logger.info("Long text: split into %d chunks", len(chunks))

    partials = []
    for i, chunk in enumerate(chunks, start=1):
        prompt = (
            "Summarize this part of a longer document in one dense paragraph. "
            "Keep key facts, names and numbers. Do not add anything not in the text.\n\n"
            f"Part {i} of {len(chunks)}:\n{chunk}"
        )
        partial = call_llm(prompt, types.GenerateContentConfig())
        partials.append(partial or "")
        logger.info("Summarized chunk %d/%d", i, len(chunks))

    return "\n\n".join(partials)

def summarize(text: str, length: str = "medium", num_takeaways: int = 3) -> dict:
    """Return {'summary': str, 'key_takeaways': [str, ...]}."""
    if not text or not text.strip():
        raise SummarizerError("Please provide some text to summarize.")
    if len(text) > MAX_CHARS:
        raise SummarizerError(
            f"Text is too long ({len(text):,} characters). Limit is {MAX_CHARS:,}."
        )

    try:
        if len(text) > CHUNK_SIZE:
            text = condense_long_text(text)  # map step
        return summarize_final(text, length, num_takeaways)  # reduce step
    except errors.APIError as e:
        raise SummarizerError(friendly_message(e.code)) from e
    except httpx.TransportError as e:
        raise SummarizerError(
            "Could not reach the AI service. Check your internet connection."
        ) from e


def summarize_final(text: str, length: str, num_takeaways: int) -> dict:
    """Build the JSON prompt, call the model, and parse the result."""
    instruction = LENGTH_INSTRUCTIONS.get(length, LENGTH_INSTRUCTIONS["medium"])
    prompt = (
        f"Summarize the following text {instruction}, "
        f"and list exactly {num_takeaways} key takeaways.\n"
        "Use simple language and do not add information that is not in the text.\n"
        "Respond ONLY with valid JSON in exactly this format:\n"
        '{"summary": "...", "key_takeaways": ["...", "..."]}\n\n'
        f"Text:\n{text}"
    )
    config = types.GenerateContentConfig(response_mime_type="application/json")

    last_error = None
    for attempt in range(2):  # retry once if the JSON is malformed
        try:
            return parse_response(call_llm(prompt, config))
        except ValueError as e:  # includes json.JSONDecodeError
            last_error = e
            logger.warning("Bad JSON on attempt %d: %s", attempt + 1, e)

    logger.error("Model returned invalid JSON twice: %s", last_error)
    raise SummarizerError("The AI returned an unreadable response. Please try again.")

if __name__ == "__main__":
    sample = """
    Python is a high-level programming language created by Guido van Rossum
    and first released in 1991. It is known for its readable syntax, which
    makes it popular with beginners. Python is used in web development, data
    science, automation, and artificial intelligence.
    """
    try:
        result = summarize(sample, "short", 3)
        print("SUMMARY:", result["summary"])
        for point in result["key_takeaways"]:
            print(" -", point)
    except SummarizerError as e:
        print("Error:", e)