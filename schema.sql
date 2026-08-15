-- Run this in Supabase SQL Editor (Project > SQL Editor > New Query)

-- Documents table: stores metadata about uploaded PDFs
create table documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) not null,
    filename text not null,
    storage_path text not null,       -- path inside Supabase Storage bucket
    extracted_text text,              -- cached extracted text (for naive Q&A / summary)
    summary text,                     -- generated summary
    created_at timestamptz default now()
);

-- Questions table: stores AI-generated MCQs per document
create table questions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid references documents(id) on delete cascade not null,
    question_text text not null,
    option_a text not null,
    option_b text not null,
    option_c text not null,
    option_d text not null,
    correct_option text not null,     -- 'A' | 'B' | 'C' | 'D'
    created_at timestamptz default now()
);

-- Quiz attempts: tracks a user attempting a set of questions for a document
create table quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) not null,
    document_id uuid references documents(id) not null,
    score integer not null,
    total_questions integer not null,
    attempted_at timestamptz default now()
);

-- Row Level Security: users can only see their own data
alter table documents enable row level security;
alter table questions enable row level security;
alter table quiz_attempts enable row level security;

create policy "Users manage own documents" on documents
    for all using (auth.uid() = user_id);

create policy "Users view questions of own documents" on questions
    for all using (
        document_id in (select id from documents where user_id = auth.uid())
    );

create policy "Users manage own quiz attempts" on quiz_attempts
    for all using (auth.uid() = user_id);