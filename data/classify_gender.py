#!/usr/bin/env python3
"""Backfill prompts.subject_gender by scanning title+prompt_text for gendered language.

Classification is deliberately simple (word-boundary keyword counting) since it
only needs to steer prompt selection away from obvious mismatches (e.g. a
prompt describing "a man in a suit" being applied to a photo of a woman), not
perform nuanced NLP.
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "prompts.db"

MALE_WORDS = {
    "man", "men", "male", "boy", "boys", "guy", "guys", "he", "him", "his",
    "gentleman", "masculine", "father", "dad", "husband", "groom", "king",
    "prince", "brother", "son", "boyfriend", "businessman", "gentlemen",
}
FEMALE_WORDS = {
    "woman", "women", "female", "girl", "girls", "lady", "ladies", "she",
    "her", "hers", "feminine", "mother", "mom", "wife", "bride", "queen",
    "princess", "sister", "daughter", "girlfriend", "businesswoman",
}


def classify(title, prompt_text):
    text = f"{title or ''} {prompt_text or ''}".lower()
    male_count = sum(len(re.findall(rf"\b{w}\b", text)) for w in MALE_WORDS)
    female_count = sum(len(re.findall(rf"\b{w}\b", text)) for w in FEMALE_WORDS)
    if male_count == 0 and female_count == 0:
        return "neutral"
    if male_count > female_count:
        return "male"
    if female_count > male_count:
        return "female"
    return "neutral"  # mixed/ambiguous (e.g. "couple" prompts mentioning both)


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, title, prompt_text FROM prompts").fetchall()
    counts = {"male": 0, "female": 0, "neutral": 0}
    for prompt_id, title, prompt_text in rows:
        gender = classify(title, prompt_text)
        counts[gender] += 1
        conn.execute("UPDATE prompts SET subject_gender = ? WHERE id = ?", (gender, prompt_id))
    conn.commit()
    conn.close()
    print(f"Classified {len(rows)} prompts: {counts}")


if __name__ == "__main__":
    main()
