import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

ENV_FILE = ".env"

MAX_STEPS = 8

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
    "(capped at 5000 characters) and return it; use this to read the contents of "
    "a specific URL."
)

FINISH_DESCRIPTION = (
    "finish(report): Write the report. Only choose this after you have read at "
    "least three different web pages. Base the report on the text of those pages. "
    "Search result titles and snippets are not enough on their own. Price tickers, "
    "shop pages and product listings give you a number but no explanation, so "
    "prefer news articles, analysis and official sources when you choose what to "
    "read."
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


def call_model(settings, messages):
    """Call the model with a message list and return the reply text, with retries."""
    url = settings["API_BASE_URL"] + "/chat/completions"
    body = json.dumps({
        "model": settings["MODEL"],
        "messages": messages,
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
    """Fetch a web page, strip the HTML to visible text capped at 5000 chars."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
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
    return text[:5000]


def _parse_action(text):
    """Strip markdown fences if present and parse the model's JSON action."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        obj = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
            except Exception:
                return None
        else:
            return None
    if not isinstance(obj, dict):
        return None
    return obj


def _format_state(state, question, step):
    """Build the prompt body: the goal, the step budget, and full history."""
    lines = []
    lines.append("Goal: " + question)
    lines.append(
        "You are on step " + str(step) + " of " + str(MAX_STEPS) +
        " allowed steps. Choose your next action."
    )
    lines.append("")
    lines.append("What has happened so far:")
    if not state:
        lines.append("(nothing yet -- this is your first step)")
    else:
        for entry in state:
            lines.append(
                "Step " + str(entry["step"]) + " [" + entry["action"] + "]: " +
                entry.get("reason", "")
            )
            if entry["action"] == "SEARCH":
                lines.append("  query: " + entry.get("query", ""))
            elif entry["action"] == "READ":
                lines.append("  url: " + entry.get("url", ""))
            lines.append("  observation: " + entry.get("observation", ""))
    lines.append("")
    lines.append("Reply now with only the JSON action object, nothing else.")
    return "\n".join(lines)


def _split_sources(state):
    """Return (pages_read, also_found) with no repeats.

    pages_read  : URLs the agent opened and got text back from.
    also_found  : URLs from search results that were never opened (read).
    A page that failed to load is neither read nor opened, so it is listed
    under neither heading.
    """
    pages_read = []
    opened = set()
    for entry in state:
        if entry["action"] == "READ" and entry.get("url"):
            url = entry["url"]
            opened.add(url)
            if entry.get("loaded") and url not in pages_read:
                pages_read.append(url)

    also_found = []
    for entry in state:
        if entry["action"] == "SEARCH":
            for result in entry.get("results", []):
                url = result.get("url")
                if url and url not in opened and url not in also_found:
                    also_found.append(url)
    return pages_read, also_found


def _collect_sources(state):
    """Return the combined honest source set: pages read plus also-found URLs."""
    pages_read, also_found = _split_sources(state)
    sources = list(pages_read)
    for url in also_found:
        if url not in sources:
            sources.append(url)
    return sources


def _split_report(report):
    """Split the FINISH report into Findings/Comparison/Recommendation."""
    result = {"Findings": "", "Comparison": "", "Recommendation": ""}
    current = None
    for line in report.splitlines():
        match = re.match(
            r"^\s*(findings|comparison|recommendation)\s*[:\-]\s*(.*)$",
            line, re.IGNORECASE,
        )
        if match:
            current = match.group(1).capitalize()
            result[current] = (match.group(2).strip() + "\n")
        elif current is not None:
            result[current] += line + "\n"
    if not any(result.values()):
        result["Findings"] = report
    return result


def _print_brief(question, state, report):
    """Print the final research brief with the required sections."""
    sections = _split_report(report)
    pages_read, also_found = _split_sources(state)
    print("")
    print("=" * 60)
    print("RESEARCH BRIEF")
    print("=" * 60)
    print("\nQuestion:\n" + question)
    print("\nFindings:\n" + sections["Findings"].strip())
    print("\nComparison:\n" + sections["Comparison"].strip())
    print("\nRecommendation:\n" + sections["Recommendation"].strip())
    print("\nPages read:")
    if pages_read:
        for index, url in enumerate(pages_read, 1):
            print("  " + str(index) + ". " + url)
    else:
        print("  (none)")
    print("\nAlso found:")
    if also_found:
        for index, url in enumerate(also_found, 1):
            print("  " + str(index) + ". " + url)
    else:
        print("  (none)")
    print("=" * 60)


def research(settings, question):
    """Run the explicit tool-using research loop and print a brief."""
    system = (
        "You are a research agent working toward this goal:\n" + question + "\n\n"
        "You have three tools:\n"
        "- SEARCH: " + SEARCH_WEB_DESCRIPTION + " Use it to find pages.\n"
        "- READ: " + READ_WEBPAGE_DESCRIPTION +
        " Page text often contains navigation and menus, so read it critically.\n"
        "- FINISH: " + FINISH_DESCRIPTION + "\n\n"
        "On every step reply with ONLY a single JSON object, no prose, in one of:\n"
        '{"reason": "one short sentence", "action": "SEARCH", "query": "..."}\n'
        '{"reason": "one short sentence", "action": "READ", "url": "..."}\n'
        '{"reason": "one short sentence", "action": "FINISH", "report": "..."}\n\n'
        "You may take at most " + str(MAX_STEPS) + " steps total. "
        "When you have enough information, choose FINISH. "
        "When FINISH, write the report as plain text with three labeled "
        "sections, each starting on its own line:\n"
        "Findings: <what you learned>\n"
        "Comparison: <how the sources compare>\n"
        "Recommendation: <what you recommend>\n\n"
        "Every finding you list must end with the URL it came from, in square "
        "brackets, for example: \"The merger was announced in March. "
        "[https://example.com/news/merger]\". Only put a URL in brackets if that "
        "exact page is one you READ (it will appear in the Pages read list); a "
        "fact taken from a search snippet or result title must end with "
        "[no source], not with the search result's URL. If a finding comes from "
        "what you already knew rather than from a page you read, end it with "
        "[no source].\n\n"
        "A failed search or a page that will not load is normal. Record what "
        "happened and choose a different approach on the next step."
    )

    state = []
    read_urls = []       # URLs the agent opened and got text back from
    seen_urls = set()    # every URL the agent has tried to READ
    for step in range(1, MAX_STEPS + 1):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _format_state(state, question, step)},
        ]
        reply = call_model(settings, messages)
        if reply is None:
            print("Model call failed; stopping the agent.")
            return None, state

        action_obj = _parse_action(reply)
        if action_obj is None:
            print("Could not parse the model's reply as JSON. Raw reply:")
            print(reply)
            print("Stopping the agent.")
            return None, state

        reason = action_obj.get("reason", "")
        action = action_obj.get("action")
        print("Step " + str(step) + ": " + str(action) + " -- " + reason)

        if action == "SEARCH":
            query = action_obj.get("query", "")
            results = search_web(query)
            observation = (
                "Search returned " + str(len(results)) + " result(s): " +
                json.dumps(results, ensure_ascii=False)
            )
            state.append({
                "step": step, "reason": reason, "action": "SEARCH",
                "query": query, "results": results, "observation": observation,
            })
            summary = (
                str(len(results)) + " result(s)" +
                ("; first: " + results[0]["title"] if results else "; no results")
            )
        elif action == "READ":
            url = action_obj.get("url", "")
            if url in seen_urls:
                observation = (
                    "Refused: URL already read (" + url +
                    "); read a different page instead."
                )
                summary = "duplicate read refused"
                state.append({
                    "step": step, "reason": reason, "action": "READ",
                    "url": url, "loaded": False, "observation": observation,
                })
            else:
                seen_urls.add(url)
                text = read_webpage(url)
                if text:
                    observation = "Page text: " + text
                    summary = "loaded " + str(len(text)) + " chars"
                    read_urls.append(url)
                else:
                    observation = "Page could not be loaded or returned no text."
                    summary = "load failed"
                state.append({
                    "step": step, "reason": reason, "action": "READ",
                    "url": url, "loaded": bool(text), "observation": observation,
                })
        elif action == "FINISH":
            report = action_obj.get("report", "")
            if not report or not report.strip():
                note = (
                    "FINISH refused: the report is empty. Read at least three "
                    "different pages, then write a non-empty report."
                )
                state.append({
                    "step": step, "reason": reason, "action": "FINISH",
                    "refused": True, "observation": note,
                })
                print("  Observation: " + note)
            elif len(read_urls) < 3:
                note = (
                    "FINISH refused: only " + str(len(read_urls)) +
                    " page(s) read successfully; 3 are required before FINISH; "
                    "choose READ next."
                )
                state.append({
                    "step": step, "reason": reason, "action": "FINISH",
                    "refused": True, "observation": note,
                })
                print("  Observation: " + note)
            else:
                state.append({
                    "step": step, "reason": reason, "action": "FINISH",
                    "refused": False, "observation": "Agent finished.",
                })
                print("  Observation: agent chose to finish.")
                _print_brief(question, state, report)
                return report, state
            continue
        else:
            observation = "Unknown action: " + str(action)
            summary = "unknown action"
            state.append({
                "step": step, "reason": reason, "action": str(action),
                "observation": observation,
            })

        print("  Observation: " + summary)

    print(
        "Step limit of " + str(MAX_STEPS) +
        " reached without FINISH. Stopping without a final brief."
    )
    return None, state


def evaluate_run(state, report):
    """Check a completed run's actual state and output. Returns (results, score)."""
    results = []

    search_used = any(entry["action"] == "SEARCH" for entry in state)
    results.append(("search tool used at least once", search_used))

    sources = _collect_sources(state)
    results.append(("more than one distinct source consulted", len(sources) > 1))

    finished = any(
        entry["action"] == "FINISH" and not entry.get("refused")
        for entry in state
    )
    results.append(("run stayed within step limit", finished))

    sections = _split_report(report) if report else {"Recommendation": ""}
    has_recommendation = bool(sections.get("Recommendation", "").strip())
    results.append(("brief contains a recommendation", has_recommendation))

    results.append(("brief lists at least three sources", len(sources) >= 3))

    return results, sum(1 for _, ok in results if ok)


def run_eval(settings, question):
    """Run research then evaluate the completed run from its real state and output."""
    report, state = research(settings, question)
    results, score = evaluate_run(state, report)
    print("")
    print("=" * 60)
    print("EVALUATION")
    print("=" * 60)
    for name, ok in results:
        print(("PASS" if ok else "FAIL") + " -- " + name)
    print("-" * 60)
    print("SCORE: " + str(score) + "/" + str(len(results)))
    print("=" * 60)
    return score


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "--eval":
            question = " ".join(sys.argv[2:]).strip() if len(sys.argv) > 2 else ""
            if not question:
                question = input("Enter your research question: ")
            print("Your research question: " + question)

            settings, missing = read_settings()
            if missing:
                for name in missing:
                    print("Missing setting: " + name)
                print("Please set the missing value(s) in your .env file and try again.")
                return

            run_eval(settings, question)
            return
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

    research(settings, question)


if __name__ == "__main__":
    main()
