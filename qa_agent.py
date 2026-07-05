"""
qa_agent.py -- Q&A agent that answers questions using the generated Agent
Skills (skills/*/SKILL.md), and reports which skill it used (citation).

Real path: builds a google-adk Agent with a SkillToolset loaded from
skills/, backed by Gemini, run via ADK's InMemoryRunner. This is the same
mechanism taught in the course's Day 3 "persistent Agent Skills" material.

Fallback (--mock, or no GEMINI_API_KEY / google-adk not installed):
keyword-matches the question against skill descriptions/instructions so
you can demo the citation behavior offline, with zero setup.

Usage:
    python qa_agent.py "How do I set up VPN access?"
    python qa_agent.py --mock "How do I get reimbursed for travel?"
"""
import argparse
import asyncio
import os
import pathlib
import re

import yaml
from dotenv import load_dotenv

load_dotenv()

SKILLS_DIR = pathlib.Path("skills")


def load_skills_raw():
    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        md_path = skill_dir / "SKILL.md"
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        if not m:
            continue
        frontmatter = yaml.safe_load(m.group(1)) or {}
        body = m.group(2).strip()
        skills.append({
            "dir": skill_dir,
            "name": frontmatter.get("name", skill_dir.name),
            "description": frontmatter.get("description", ""),
            "body": body,
        })
    return skills


STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "for", "on", "in", "at", "to", "of", "and", "or",
    "how", "what", "when", "where", "why", "who", "which", "with", "up",
    "my", "your", "i", "you", "it", "this", "that", "there", "get", "set",
    "can", "should", "would", "will", "new", "like", "just", "about",
}


def _keywords(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1}


def mock_answer(question: str, skills: list) -> str:
    """Offline retrieval -- no API key required. Mirrors real skill discovery:
    the description (L1 metadata) is what an agent matches against first, so
    it's weighted higher than the instruction body."""
    q_words = _keywords(question)
    best, best_score = None, -1
    for s in skills:
        desc_words = _keywords(s["description"])
        body_words = _keywords(s["body"])
        score = 3 * len(q_words & desc_words) + len(q_words & body_words)
        if score > best_score:
            best, best_score = s, score
    if not best or best_score < 2:
        return "I couldn't find a skill covering that. Try rephrasing, or add more source docs."
    return (
        f"[MOCK MODE -- no GEMINI_API_KEY set]\n\n"
        f"Based on skill '{best['name']}':\n\n{best['body']}\n\n"
        f"-- Cited skill: {best['name']} ({best['dir']}/SKILL.md)"
    )


async def real_answer(question: str, skills: list) -> str:
    from google.adk import Agent
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools import skill_toolset
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    loaded = [load_skill_from_dir(s["dir"]) for s in skills]
    toolset = skill_toolset.SkillToolset(skills=loaded)

    agent = Agent(
        model="gemini-flash-latest",
        name="wiki_qa_agent",
        description="Answers internal questions using distilled wiki Agent Skills.",
        instruction=(
            "You answer questions using the available skills only. "
            "Always end your answer with a line: 'Cited skill: <skill-name>' "
            "naming the skill you relied on. If no skill applies, say so."
        ),
        tools=[toolset],
    )

    runner = InMemoryRunner(agent=agent, app_name="docs_to_skill_qa")
    session = await runner.session_service.create_session(app_name="docs_to_skill_qa", user_id="user")

    final_text = ""
    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text
    return final_text


def main():
    parser = argparse.ArgumentParser(description="Ask a question against the generated skills")
    parser.add_argument("question")
    parser.add_argument("--mock", action="store_true", help="force offline retrieval mode")
    args = parser.parse_args()

    if not SKILLS_DIR.exists() or not any(SKILLS_DIR.iterdir()):
        raise SystemExit("No skills found -- run generate_skills.py first.")

    skills = load_skills_raw()
    use_mock = args.mock or not os.environ.get("GEMINI_API_KEY")

    if use_mock:
        print(mock_answer(args.question, skills))
    else:
        try:
            answer = asyncio.run(real_answer(args.question, skills))
            print(answer)
        except Exception as e:
            print(f"[ADK/Gemini call failed: {e}] Falling back to mock mode.\n")
            print(mock_answer(args.question, skills))


if __name__ == "__main__":
    main()
