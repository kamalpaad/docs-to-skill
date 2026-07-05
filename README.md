Every team has a wiki, README, or set of onboarding docs that's messy, outdated,
and duplicated across three places. New agents (and new hires) can't use that
knowledge reliably because it isn't structured for retrieval.

## What this does

1. **`generate_skills.py`** reads raw, messy docs (`input_docs/*.txt`) and
   distills each one into a reusable **Agent Skill** — a `SKILL.md` file with
   YAML frontmatter (`name`, `description`) plus step-by-step instructions in
   the body. The original doc is preserved under
   `skills/<name>/references/source.md` for traceability.
2. **`qa_agent.py`** loads all generated skills and answers user questions,
   **citing which skill it used** — proving the skills are actually being
   discovered and applied, not just generated and ignored.
