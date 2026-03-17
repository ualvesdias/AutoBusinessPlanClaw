from __future__ import annotations

REQUIRED_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("problem", "What specific problem am I solving?"),
    ("icp", "Who exactly is my target customer (ICP)?"),
    ("current_solution", "How are they solving this problem today?"),
    ("why_now", "Why are current solutions not good enough?"),
    ("advantage", "What is my unique advantage or insight?"),
    ("mvp", "What is the simplest version of my solution (MVP)?"),
    ("payment_reason", "Why would someone pay for this?"),
    ("first_10_customers", "How will I get my first 10 customers?"),
    ("early_success", "What does success look like in the first 30–60 days?"),
    ("killer_risks", "What are the biggest risks that could kill this idea?"),
)


def required_question_map() -> dict[str, str]:
    return dict(REQUIRED_QUESTIONS)
