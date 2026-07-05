"""
generate_skills.py -- Docs-to-Skill converter (capstone project)

Reads messy internal docs from input_docs/ and distills each into a
reusable Agent Skill (SKILL.md + references/) following the Agent Skill
specification (https://agentskills.io/specification) -- the same format
ADK's SkillToolset loads via google.adk.skills.load_skill_from_dir, and
the format Antigravity itself uses for its own skills.

Usage:
    python generate_skills.py                # uses Gemini if GEMINI_API_KEY is set
    python generate_skills.py --mock         # force offline heuristic mode (no key/network needed)
"""
import argparse
import json
import os
import pathlib
import re
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()

INPUT_DIR = pathlib.Path("input_docs")
SKILLS_DIR = pathlib.Path("skills")

PROMPT_TEMPLATE = """You are converting messy internal documentation into a
reusable Agent Skill for an AI agent, following the Agent Skill specification
(https://agentskills.io/specification).

Given the raw document below, produce a JSON object with exactly these keys:
- "name": a short kebab-case identifier (letters, digits, hyphens only)
- "description": ONE sentence describing what the skill helps with and WHEN
  an agent should trigger it (used for skill discovery -- be specific about
  triggering conditions, not just a summary)
- "instructions": clear, numbered, step-by-step markdown instructions an
  agent should follow when this skill is invoked. Keep only actionable
  content; drop filler, apologies, or meta-commentary found in the source.

Return ONLY the JSON object, no markdown fences, no commentary.

RAW DOCUMENT (filename: {filename}):
---
{content}
---
"""


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return re.sub(r"-+", "-", text).strip("-") or "untitled-skill"


def call_gemini(filename: str, content: str) -> dict:
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(filename=filename, content=content)
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt,
    )
    text = response.text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def mock_distill(filename: str, content: str) -> dict:
    """Offline heuristic fallback -- no API key / no network required.
    Lets you demo the full pipeline instantly; switch to the real Gemini
    path (unset --mock, set GEMINI_API_KEY) before recording your video."""
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    title = lines[0] if lines else filename
    name = slugify(pathlib.Path(filename).stem)
    body_lines = lines[1:] if len(lines) > 1 else lines
    steps = []
    for l in body_lines:
        l = re.sub(r"^[-*\d\.\)\s]+", "", l).strip()
        if len(l) > 3:
            steps.append(l)
    instructions = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) or "1. Refer to the source document."
    description = f"Use this skill when the user asks about {title.lower()}. Distilled from {filename}."
    return {"name": name, "description": description[:300], "instructions": instructions}


def write_skill(skill: dict, source_filename: str, source_content: str) -> pathlib.Path:
    name = slugify(skill["name"])
    skill_dir = SKILLS_DIR / name
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = {"name": name, "description": skill["description"]}
    skill_md = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False).strip() + "\n---\n\n"
    skill_md += f"# {name.replace('-', ' ').title()}\n\n"
    skill_md += skill["instructions"].strip() + "\n"

    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (refs_dir / "source.md").write_text(
        f"<!-- original source: {source_filename} -->\n\n{source_content}", encoding="utf-8"
    )
    return skill_dir


def main():
    parser = argparse.ArgumentParser(description="Convert messy docs into Agent Skills")
    parser.add_argument("--mock", action="store_true", help="force offline heuristic mode")
    parser.add_argument("--input", default=str(INPUT_DIR), help="input docs directory")
    args = parser.parse_args()

    input_dir = pathlib.Path(args.input)
    if not input_dir.exists():
        sys.exit(f"Input directory not found: {input_dir}")

    use_mock = args.mock or not os.environ.get("GEMINI_API_KEY")
    if use_mock:
        print("[generate_skills] No GEMINI_API_KEY found (or --mock passed) -- running in MOCK mode.")
        print("                  Set GEMINI_API_KEY and re-run without --mock for the real submission.\n")

    docs = sorted([p for p in input_dir.iterdir() if p.suffix.lower() in (".txt", ".md")])
    if not docs:
        sys.exit(f"No .txt/.md files found in {input_dir}")

    SKILLS_DIR.mkdir(exist_ok=True)
    created = []
    for doc in docs:
        content = doc.read_text(encoding="utf-8")
        try:
            skill = mock_distill(doc.name, content) if use_mock else call_gemini(doc.name, content)
        except Exception as e:
            print(f"  ! Gemini call failed for {doc.name} ({e}); falling back to mock for this file.")
            skill = mock_distill(doc.name, content)
        skill_dir = write_skill(skill, doc.name, content)
        created.append(skill_dir)
        print(f"  -> {doc.name}  =>  {skill_dir}/SKILL.md")

    print(f"\nDone. {len(created)} skill(s) written to {SKILLS_DIR}/")


if __name__ == "__main__":
    main()
