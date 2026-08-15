import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from config import supabase, supabase_auth_client, gemini_model, STORAGE_BUCKET
from utils import extract_text_from_pdf, generate_summary, generate_mcqs, answer_question

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------- AUTH ----------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            result = supabase_auth_client.auth.sign_up({"email": email, "password": password})
            flash("Signup successful! Please log in.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"Signup failed: {e}")
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            result = supabase_auth_client.auth.sign_in_with_password({"email": email, "password": password})
            session["user_id"] = result.user.id
            session["access_token"] = result.session.access_token
            return redirect(url_for("dashboard"))
        except Exception as e:
            flash(f"Login failed: {e}")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def login_required(view):
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


# ---------- DASHBOARD / UPLOAD ----------

@app.route("/")
def index():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    docs = supabase.table("documents").select("*").eq("user_id", session["user_id"]).execute().data

    attempts = supabase.table("quiz_attempts").select("*").eq("user_id", session["user_id"]).execute().data

    total_docs = len(docs)
    total_quizzes = len(attempts)

    if attempts:
        total_score = sum(a["score"] for a in attempts)
        total_possible = sum(a["total_questions"] for a in attempts)
        avg_percent = round((total_score / total_possible) * 100) if total_possible > 0 else 0
    else:
        avg_percent = None

    user_email = None
    try:
        user_email = supabase.auth.admin.get_user_by_id(session["user_id"]).user.email
    except Exception:
        pass

    return render_template(
        "dashboard.html",
        documents=docs,
        total_docs=total_docs,
        total_quizzes=total_quizzes,
        avg_percent=avg_percent,
        user_email=user_email,
    )

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files["pdf_file"]
        if not file or not file.filename.endswith(".pdf"):
            flash("Please upload a valid PDF.")
            return redirect(url_for("upload"))

        local_filename = f"{uuid.uuid4()}.pdf"
        local_path = os.path.join(UPLOAD_FOLDER, local_filename)
        file.save(local_path)

        # Upload to Supabase Storage
        storage_path = f"{session['user_id']}/{local_filename}"
        with open(local_path, "rb") as f:
            supabase.storage.from_(STORAGE_BUCKET).upload(storage_path, f)

        # Extract text locally, then store metadata + text in DB
        extracted_text = extract_text_from_pdf(local_path)

        doc = supabase.table("documents").insert({
            "user_id": session["user_id"],
            "filename": file.filename,
            "storage_path": storage_path,
            "extracted_text": extracted_text,
        }).execute()

        os.remove(local_path)  # clean up local temp file

        flash("Uploaded! Generating summary...")
        return redirect(url_for("view_document", doc_id=doc.data[0]["id"]))

    return render_template("upload.html")

@app.route("/document/<doc_id>/delete", methods=["POST"])
@login_required
def delete_document(doc_id):
    doc = supabase.table("documents").select("*").eq("id", doc_id).single().execute().data
    if not doc:
        flash("Document not found.")
        return redirect(url_for("dashboard"))

    # Remove the file from Supabase Storage
    try:
        supabase.storage.from_(STORAGE_BUCKET).remove([doc["storage_path"]])
    except Exception as e:
        print(f"Storage delete warning: {e}")

    # Remove related questions and quiz attempts first
    supabase.table("questions").delete().eq("document_id", doc_id).execute()
    supabase.table("quiz_attempts").delete().eq("document_id", doc_id).execute()

    # Finally remove the document record
    supabase.table("documents").delete().eq("id", doc_id).execute()

    flash("Document deleted.")
    return redirect(url_for("dashboard"))


# ---------- DOCUMENT VIEW: summary, MCQs, Q&A ----------

@app.route("/document/<doc_id>")
@login_required
def view_document(doc_id):
    doc = supabase.table("documents").select("*").eq("id", doc_id).single().execute().data
    return render_template("document.html", document=doc)


@app.route("/document/<doc_id>/summary", methods=["POST"])
@login_required
def generate_doc_summary(doc_id):
    doc = supabase.table("documents").select("*").eq("id", doc_id).single().execute().data
    summary = generate_summary(gemini_model, doc["extracted_text"])
    supabase.table("documents").update({"summary": summary}).eq("id", doc_id).execute()
    return jsonify({"summary": summary})


@app.route("/document/<doc_id>/mcqs", methods=["POST"])
@login_required
def generate_doc_mcqs(doc_id):
    doc = supabase.table("documents").select("*").eq("id", doc_id).single().execute().data

    # Delete any previously generated questions for this document first
    supabase.table("questions").delete().eq("document_id", doc_id).execute()

    mcqs = generate_mcqs(gemini_model, doc["extracted_text"], num_questions=5)

    for q in mcqs:
        supabase.table("questions").insert({
            "document_id": doc_id,
            "question_text": q["question"],
            "option_a": q["option_a"],
            "option_b": q["option_b"],
            "option_c": q["option_c"],
            "option_d": q["option_d"],
            "correct_option": q["correct_option"],
        }).execute()

    return jsonify({"mcqs": mcqs})


@app.route("/document/<doc_id>/ask", methods=["POST"])
@login_required
def ask_question(doc_id):
    doc = supabase.table("documents").select("*").eq("id", doc_id).single().execute().data
    question = request.json.get("question")
    answer = answer_question(gemini_model, doc["extracted_text"], question)
    return jsonify({"answer": answer})


# ---------- QUIZ ----------

@app.route("/document/<doc_id>/quiz")
@login_required
def quiz(doc_id):
    questions = supabase.table("questions").select("*").eq("document_id", doc_id).execute().data
    return render_template("quiz.html", document_id=doc_id, questions=questions)


@app.route("/document/<doc_id>/quiz/submit", methods=["POST"])
@login_required
def submit_quiz(doc_id):
    answers = request.json.get("answers")  # { question_id: "A" }
    questions = supabase.table("questions").select("*").eq("document_id", doc_id).execute().data

    score = 0
    for q in questions:
        if answers.get(q["id"]) == q["correct_option"]:
            score += 1

    supabase.table("quiz_attempts").insert({
        "user_id": session["user_id"],
        "document_id": doc_id,
        "score": score,
        "total_questions": len(questions),
    }).execute()

    return jsonify({"score": score, "total": len(questions)})


if __name__ == "__main__":
    app.run(debug=True, port=5001)