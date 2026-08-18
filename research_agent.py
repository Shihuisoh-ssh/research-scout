import json
import os
import sys
import time
import urllib.error
import urllib.request

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

ENV_FILE = ".env"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


SEARCH_WEB_DESCRIPTION = (
    "search_web(query): Search the web for a query and return up to 5 results, "
    "each with a title, URL and snippet; use this to find web pages or sources "
    "on a topic before reading them."
)

READ_WEBPAGE_DESCRIPTION = (
    "read_webpage(url): Fetch a single web page, strip its HTML to visible text "
    "(capped at 2000 characters) and return it; use this to read the contents of "
    "a specific URL."
)


def load_env(path):
    """Read KEY=VALUE pairs from a .env file into a dict."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


def read_settings():
    """Return the three required settings or a list of missing names."""
    env = load_env(ENV_FILE)
    required = ["API_BASE_URL", "API_KEY", "MODEL"]
    missing = [name for name in required if not env.get(name)]
    if missing:
        return None, missing
    return {
        "API_BASE_URL": env["API_BASE_URL"].rstrip("/"),
        "API_KEY": env["API_KEY"],
        "MODEL": env["MODEL"],
    }, []


def call_model(settings, prompt):
    """Call the model and return the reply text, with retries for 429/5xx."""
    url = settings["API_BASE_URL"] + "/chat/completions"
    body = json.dumps({
        "model": settings["MODEL"],
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + settings["API_KEY"],
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    attempts = 4
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            status = e.code

            if status == 429 and attempt < attempts - 1:
                retry_after = e.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                    reason = (
                        "rate limited (429); the server asked us to wait "
                        + str(wait)
                        + " second(s) via Retry-After"
                    )
                else:
                    wait = 2
                    reason = (
                        "rate limited (429); no Retry-After header, "
                        "waiting 2 seconds"
                    )
                print("Waiting " + str(wait) + " second(s): " + reason)
                time.sleep(wait)
                continue

            if 500 <= status < 600 and attempt < attempts - 1:
                print("Waiting 2 seconds: server error (" + str(status) + "); retrying")
                time.sleep(2)
                continue

            print("Request failed.")
            print("Error type: HTTPError")
            print("Message: HTTP " + str(status))
            if error_body:
                print("Response body:")
                print(error_body)
            return None
        except urllib.error.URLError as e:
            print("Request failed.")
            print("Error type: URLError")
            print("Message: " + str(e.reason))
            return None
        except Exception as e:
            print("Request failed.")
            print("Error type: " + type(e).__name__)
            print("Message: " + str(e))
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print("Could not read the response as JSON.")
            print("Error type: JSONDecodeError")
            print("Message: " + str(e))
            print("Response body:")
            print(raw)
            return None

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            print("The response did not contain choices[0].message.content.")
            print("Full response body:")
            print(raw)
            return None

    print("Giving up after retrying 3 times.")
    return None


def search_web(query):
    """Search the web and return up to 5 results with title, URL and snippet."""
    try:
        results = DDGS().text(query, max_results=5)
    except Exception as e:
        print("Search failed.")
        print("Error type: " + type(e).__name__)
        print("Message: " + str(e))
        return []

    cleaned = []
    for item in results[:5]:
        cleaned.append({
            "title": item.get("title", ""),
            "url": item.get("href", ""),
            "snippet": item.get("body", ""),
        })
    return cleaned


def read_webpage(url):
    """Fetch a web page, strip the HTML to visible text capped at 2000 chars."""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except Exception as e:
        print("Request failed.")
        print("Error type: " + type(e).__name__)
        print("Message: " + str(e))
        return ""

    if response.status_code != 200:
        print("Status code: " + str(response.status_code))
        print("URL: " + url)
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text[:2000]


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "search_web":
            query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            if not query:
                print("Usage: python research_agent.py search_web <query>")
                return
            results = search_web(query)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return
        if command == "read_webpage":
            if len(sys.argv) < 3:
                print("Usage: python research_agent.py read_webpage <url>")
                return
            text = read_webpage(sys.argv[2])
            print(text)
            return
        print("Unknown command: " + command)
        print("Available commands: search_web, read_webpage")
        return

    question = input("Enter your research question: ")
    print("Your research question: " + question)

    settings, missing = read_settings()
    if missing:
        for name in missing:
            print("Missing setting: " + name)
        print("Please set the missing value(s) in your .env file and try again.")
        return

    reply = call_model(settings, question)
    if reply is not None:
        print("Reply from model:")
        print(reply)


if __name__ == "__main__":
    main()
