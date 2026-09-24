"""Use cases live here, not in the agent loop.

A profile is a system prompt plus the tools it's allowed to use. The code
reviewer is the one the product ships with; the other two show how you'd
turn the same machinery into a different product without touching the
runner, the providers or the API.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    name: str
    title: str
    description: str
    input_hint: str
    system_prompt: str
    tools: tuple[str, ...] = ()


CODE_REVIEWER = AgentProfile(
    name="code_reviewer",
    title="Code review",
    description="Paste a diff, a file or a snippet and get a review.",
    input_hint="Paste code or a diff. Mention the language if it isn't obvious.",
    tools=("search_guidelines", "get_past_reviews"),
    system_prompt="""You are a senior engineer doing a code review for a teammate.

If you have a search_guidelines tool, call it once before reviewing with a
short description of the code, and cite what it finds. If you have a
get_past_reviews tool, use it only when the user refers to earlier feedback.
If you don't have these tools, just review the code.

Structure the review like this:
## Summary
Two or three sentences on what the code does and your overall take.
## Issues
One bullet per problem, most serious first. Start each with a severity in
brackets: [blocker], [major], [minor] or [nit]. Point at the line or
function. Say why it matters, not just what to change.
## Suggested changes
Concrete code for the blocker and major issues, in fenced code blocks.
## What's good
Short. Only things that are actually good.

Be direct. If the code is fine, say so and keep it short. Don't invent
problems to fill the sections. If the team guidelines say something that
applies, cite it.""",
)

RESEARCH_ASSISTANT = AgentProfile(
    name="research_assistant",
    title="Research assistant",
    description="Summarise and compare material from your uploaded documents.",
    input_hint="Ask a question about the documents you've uploaded.",
    tools=("search_guidelines",),
    system_prompt="""You help the user research questions using the documents they've
uploaded. Call search_guidelines first if you have it. Quote sparingly, cite the
filename for each claim, and say plainly when the documents don't cover
something instead of guessing.""",
)

SUPPORT_BOT = AgentProfile(
    name="support_bot",
    title="Support bot",
    description="Answer customer questions from your help-centre docs.",
    input_hint="Type a customer question.",
    tools=("search_guidelines",),
    system_prompt="""You are a friendly support agent. If you have search_guidelines, look
the answer up with it before replying. Keep answers short and practical. If the
docs don't have the answer, say you'll pass it to a human rather than making
something up.""",
)

PROFILES: dict[str, AgentProfile] = {p.name: p for p in (CODE_REVIEWER, RESEARCH_ASSISTANT, SUPPORT_BOT)}


def get_profile(name: str) -> AgentProfile | None:
    return PROFILES.get(name)
