# Research Scout

A small, dependency-light research agent that searches the web, reads pages, and
writes a sourced brief. No agent framework — just `requests`, `beautifulsoup4`,
and `ddgs` driving a chat-completions model in an explicit tool-use loop.

## Features

- **Tool-using loop**: the model chooses `SEARCH`, `READ`, or `FINISH` one step at
  a time, up to a step limit (`MAX_STEPS`, default 8).
- **Honest sourcing**: every finding must end with the URL it came from in square
  brackets, or `[no source]` if it came from prior knowledge or a search snippet.
- **Real state checks** (via `--eval`): verifies the run actually searched, read
  more than one source, finished within the step limit, contains a recommendation,
  and lists at least three sources.
- **Hard FINISH gate**: a `FINISH` is refused unless the agent has read at least
  three different pages and produced a non-empty report. Duplicate reads are
  refused.
- **Two source lists** in the brief:
  - **Pages read** — URLs opened and from which text was returned.
  - **Also found** — URLs from search results that were never opened.
  - Pages that failed to load appear under neither heading.

## Requirements

- Python 3.10+
- A model API compatible with the OpenAI chat-completions endpoint.

Install dependencies:

```bash
pip install -r requirements.txt
```

## Setup

Create a `.env` file in the project root with your API settings:

```ini
API_BASE_URL=https://your-api-endpoint.example.com/v1
API_KEY=your_api_key
MODEL=your_model_name
```

The `.env` file is git-ignored and must not be committed.

## Usage

Run interactively (you will be prompted for a research question):

```bash
python research_agent.py
```

### Evaluation mode

Run a research pass and then score it against five checks, printing `PASS`/`FAIL`
and a total score:

```bash
python research_agent.py --eval
```

You can also pass the question directly:

```bash
python research_agent.py --eval "What is the latest price of Mapletree Logistics Trust?"
```

### Standalone tools

```bash
python research_agent.py search_web "your query"
python research_agent.py read_webpage "https://example.com/page"
```

## How it works

1. The model is given the goal and the step budget, then asked to return a single
   JSON action on each step.
2. `SEARCH` queries the web via `ddgs` and returns up to 5 results.
3. `READ` fetches a page, strips the HTML to visible text (capped at 5000
   characters), and returns it.
4. `FINISH` is only accepted once at least three distinct pages have been read
   successfully and the report is non-empty.

The evaluation mode inspects the run's actual `state` and output, not the model's
self-assessment.

## Project layout

- `research_agent.py` — the entire agent (loop, tools, brief printing, eval).
- `requirements.txt` — Python dependencies.
- `.env` — local API settings (not committed).
