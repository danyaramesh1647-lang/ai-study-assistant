import PyPDF2
import json
import re


def extract_text_from_pdf(file_path):
    """Extract raw text from a PDF file on disk."""
    text = ""
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def clean_markdown(text):
    """Strip common Markdown symbols so plain HTML pages don't show raw ** ## etc."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)   # **bold**
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)  # ## headings
    text = re.sub(r"^[-*]\s+", "\u2022 ", text, flags=re.MULTILINE)  # - or * bullet -> •
    return text.strip()


def generate_summary(gemini_model, text):
    prompt = (
        "Summarize the following study notes as a clean bullet-point list of key "
        "concepts a student should remember. "
        "Output ONLY the bullet points — do NOT include any introductory sentence "
        "like 'Here is a summary'. "
        "Put EACH bullet point on its own new line. "
        "Do NOT use Markdown formatting (no **, no #, no _). "
        "Start each line with a dash (-) character.\n\n"
        f"NOTES:\n{text[:15000]}"  # cap input size for safety
    )
    response = gemini_model.generate_content(prompt)
    return clean_markdown(response.text.strip())

def generate_mcqs(gemini_model, text, num_questions=5):
    prompt = (
        f"Based on the following study notes, generate exactly {num_questions} "
        "multiple choice questions to test understanding. "
        "Return ONLY valid JSON (no markdown, no explanation) as a list of objects "
        "with keys: question, option_a, option_b, option_c, option_d, correct_option "
        "(correct_option must be exactly 'A', 'B', 'C', or 'D'). "
        "Do not use ** or any Markdown formatting inside the text values.\n\n"
        f"NOTES:\n{text[:15000]}"
    )
    response = gemini_model.generate_content(prompt)
    raw = response.text.strip()
    raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
    mcqs = json.loads(raw)
    for q in mcqs:
        for key in ("question", "option_a", "option_b", "option_c", "option_d"):
            q[key] = clean_markdown(q[key])
    return mcqs


def answer_question(gemini_model, text, question):
    prompt = (
        "Answer the student's question using ONLY the information in the notes below. "
        "If the answer isn't in the notes, say so clearly. "
        "Do NOT use Markdown formatting (no **, no #, no _) — plain text only.\n\n"
        f"NOTES:\n{text[:15000]}\n\n"
        f"QUESTION: {question}"
    )
    response = gemini_model.generate_content(prompt)
    return clean_markdown(response.text.strip())