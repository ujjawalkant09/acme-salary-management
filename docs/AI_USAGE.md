# How AI was used

A running log of how AI tools were used to build this, kept to show the process honestly. The standing instructions given to the AI agent (code style, tests, always run the code, git rules) are in [../.claude/CLAUDE.md](../.claude/CLAUDE.md).

| Phase | What AI did | What I decided / verified myself |
|------|-------------|----------------------------------|
| 1. Requirements | Read the brief, asked clarifying questions (stack, deploy, git, ownership), drafted REQUIREMENTS.md and ARCHITECTURE.md | _fill in: what you changed or pushed back on_ |
| 1b. Design | Used the repo skills (frontend-design, python-patterns, senior-backend) to draft the design pack and a clickable prototype; screenshot-tested the prototype and fixed the bugs found | _fill in: which decisions you changed_ |
| 1c. Decisions | Turned the HR/tech answers into DECISIONS.md, redesigned the prototype in shadcn style (simpler), added the deployment and secrets design (Render demo + AWS App Runner/RDS/Secrets Manager) | Chose shadcn only, App Runner (later replaced by one EC2 server), Docker, demo login; rejected the first prototype look |
| 1d. UI research | Researched filter UX, dashboard overload and SaaS navigation; wrote 07-UI-RESEARCH.md; rebuilt the prototype (v3) and screenshot-tested it on desktop and phone | Asked for left filters, a calmer home page and visible user info; rejected v2 |
| 1e. Decisions | Sent clarifying questions to the hiring team; built an interactive decision book (42 questions with recommendations); read back the answers and updated every design doc; researched hosting regions | Answered all 42 questions; chose two roles, photos and documents, live rates, gender stored only, a separate employee page |
| 1f. Review | Cross-checked every doc against the brief and the decision book; fixed contradictions (stale ARCHITECTURE.md, page size, levels, money precision, "left" status, region, backups, worker container) | Asked for the review and approved the fixes |
