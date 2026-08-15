"""
One-time cleanup script: strips leftover Markdown (**, ##, etc.)
from summaries and MCQs that were saved to Supabase BEFORE
clean_markdown() was added to utils.py.

Run once with: python cleanup_markdown.py
"""

from config import supabase
from utils import clean_markdown


def cleanup_documents():
    print("Fetching documents...")
    docs = supabase.table("documents").select("id, summary").execute().data

    updated = 0
    for doc in docs:
        summary = doc.get("summary")
        if not summary:
            continue  # skip docs with no summary yet

        cleaned = clean_markdown(summary)
        if cleaned != summary:
            supabase.table("documents").update({"summary": cleaned}).eq("id", doc["id"]).execute()
            updated += 1
            print(f"  Cleaned summary for document {doc['id']}")

    print(f"Documents updated: {updated}\n")


def cleanup_questions():
    print("Fetching questions...")
    questions = supabase.table("questions").select(
        "id, question_text, option_a, option_b, option_c, option_d"
    ).execute().data

    updated = 0
    for q in questions:
        changes = {}
        for field in ("question_text", "option_a", "option_b", "option_c", "option_d"):
            value = q.get(field)
            if value:
                cleaned = clean_markdown(value)
                if cleaned != value:
                    changes[field] = cleaned

        if changes:
            supabase.table("questions").update(changes).eq("id", q["id"]).execute()
            updated += 1
            print(f"  Cleaned question {q['id']}")

    print(f"Questions updated: {updated}\n")


if __name__ == "__main__":
    print("Starting Markdown cleanup...\n")
    cleanup_documents()
    cleanup_questions()
    print("Done.")