# Student Grids System

A web-based application that automates the parsing and evaluation of university transcripts and degree audit grids, helping academic advisors efficiently track student degree progress and graduation eligibility.

**Deployed Application:** [studentgrids.site](https://studentgrids.site)  
**Demo Video:** [YouTube](https://youtu.be/GUc-JfhPIP8?si=NlGMVvPJifysRGZK)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running with Docker](#running-with-docker)
- [Running Locally (without Docker)](#running-locally-without-docker)
- [Running Tests](#running-tests)
- [Team](#team)

---

## Overview

University academic advisors and students face significant challenges navigating degree requirements. Advisors rely on manual, error-prone processes to evaluate audit grids against complex programme rules, while students struggle to determine which courses they need to complete their degree. This system addresses both problems by:

- Parsing raw PDF transcripts and degree audit grids
- Evaluating a student's passed courses against degree requirements (core courses, electives, foundation credits, foreign language requirement)
- Presenting results in a clean web dashboard with graduation eligibility status

---

## Features

- **PDF & Text Parsing** — Extracts student data, course codes, grades, and credits from unstructured university PDF documents using pdfplumber and regex heuristics
- **Degree Evaluation Engine** — A standalone, rule-based engine using `Bucket` and `CourseFilter` classes to dynamically assess degree completion without hardcoded logic
- **Course Equivalencies** — Handles equivalent course codes so students aren't penalized for taking renamed or cross-listed courses
- **Foreign Language Requirement (FLR)** — Evaluates FLR eligibility based on admit term, approved course list, and advisor override capability
- **Asynchronous Processing** — PDF parsing runs in the background via Django-Q2, keeping the app responsive during large file uploads
- **Batch Uploads** — Supports multi-student grid files, processing all students in a single upload
- **Batch PDF Report Generation** — Advisors can generate a downloadable PDF report summarizing graduation eligibility across all students
- **Public Transcript Preview** — Non-authenticated users can upload a transcript and receive a session-based preview without data being saved to the database
- **Secure Advisor Dashboard** — Full authentication system with login, registration, password reset, and password change
- **FLR Exemption Toggle** — Advisors can manually toggle a student's FLR exemption status directly from the student detail page

---

## Tech Stack
| Layer            | Technology                              |
| ---------------- | --------------------------------------- |
| Language         | Python                                  |
| Web Framework    | Django                                  |
| Database         | PostgreSQL                              |
| Data Validation  | Pydantic                                |
| PDF Extraction   | pdfplumber                              |
| Report Generation | pdf-lib (Client-side)                   |
| Task Queue       | Django-Q2                               |
| Frontend         | Bootstrap 5, HTML, CSS                  |
| Forms            | django-crispy-forms + crispy-bootstrap5 |
| Email            | django-anymail + Resend                 |
| Static Files     | WhiteNoise                              |
| Containerisation | Docker                                  |
| Deployment       | Heroku                                  |

---

## Architecture

The system is made up of three main components:

**1. Grids Module (Standalone Python Package)**  
A fully decoupled parsing and evaluation engine. Uses only Pydantic (no Django ORM dependency), meaning it can be tested or run independently as a microservice. Contains:
- PDF and text parsers
- Course equivalency lookup
- Rule-based degree evaluator (`Bucket`, `CourseFilter`, `Major`, `Minor`, `Degree` classes)
- Foreign Language Requirement evaluator

**2. Django Web Application**  
Handles routing, authentication, file uploads, and the advisor dashboard. Passes uploaded documents to the grids module and stores results in PostgreSQL via Django ORM models (`StudentProfile`, `AuditRecord`, `BucketResult`).

**3. Background Task Worker (Django-Q2)**  
Offloads heavy PDF parsing to background workers so web requests don't time out on large files.

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL
- Docker & Docker Compose (recommended)
- [uv](https://github.com/astral-sh/uv) (optional, for local package management)

### Clone the Repository

```bash
git clone https://github.com/AesirGroup/StudentGridsSystem.git
cd StudentGridsSystem
```

---

## Environment Variables

> **⚠️ WARNING:** Never commit your `.env` file to version control. It is already listed in `.gitignore`.

Create a `.env` file in the project root. Use the template below.
When `DEBUG=True`, emails are printed to the terminal instead of being sent via the Resend API — no API key is needed for local development.

### Local Development (Docker Compose)

```env
# Django
SECRET_KEY=django-insecure-replace-this-with-a-long-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Database
# For Docker Compose: hostname is "db" (the compose service name).
# For local non-Docker: use "localhost" instead of "db".
POSTGRES_DB=studentgrids
POSTGRES_USER=user
POSTGRES_PASSWORD=password
DATABASE_URL=postgres://user:password@db:5432/studentgrids

# Email (Resend via django-anymail)
# Required ONLY for production (DEBUG=False). Leave blank for local dev.
RESEND_API_KEY=
DEFAULT_FROM_EMAIL=Local Testing <test@localhost>

# Django-Q2 worker count
Q_CLUSTER_WORKERS=2
```

### Production (Heroku)

Set these in **Heroku Settings → Config Vars**. Do not use a `.env` file in production.

```env
# Django
SECRET_KEY=your-long-random-production-secret-key
DEBUG=False
ALLOWED_HOSTS=.herokuapp.com,studentgrids.site,www.studentgrids.site
CSRF_TRUSTED_ORIGINS=https://*.herokuapp.com,https://studentgrids.site,https://www.studentgrids.site

# Database
# DATABASE_URL is automatically injected by the Heroku Postgres add-on.
# Do not set this manually.

# Email
RESEND_API_KEY=re_your_live_production_key
DEFAULT_FROM_EMAIL=StudentGrids <admin@studentgrids.site>

# Django-Q2
Q_CLUSTER_WORKERS=2
```

---

## Running with Docker
The recommended way to run the full stack (web app + database + background worker) locally.

```bash
docker compose up --build
```

This will start:
- A PostgreSQL database
- An automated database migration service
- The Django web server
- A Django-Q2 background worker

Database migrations are applied automatically on startup.

Create a superuser (advisor account):

```bash
docker compose exec web uv run python manage.py createsuperuser
```

Visit [http://localhost:8000](http://localhost:8000).

> **⚠️ Windows users:** After running `docker compose down`, you may get an error when running `uv sync` locally:
> ```
> error: failed to remove file .venv\lib64: Access is denied.
> ```
> This happens because Docker writes a Linux-style `lib64` symlink into your `.venv` through the bind mount, which Windows cannot clean up. Fix it by deleting the venv and re-syncing:
> ```bash
> Remove-Item -Recurse -Force .\.venv
> uv sync
> ```


---

## Running Locally (without Docker)

**1. Install dependencies**

```bash
uv sync
```

**2. Apply migrations**

```bash
uv run python manage.py migrate
```

**3. Start the Django development server**

```bash
uv run python manage.py runserver
```

**4. Start the Django-Q2 worker (in a separate terminal)**

```bash
uv run python manage.py qcluster
```

**5. (Optional) Use Honcho to run everything at once**

Honcho is a cross-platform process manager. If you encounter issues on Windows (e.g., process signals), run the server and worker in separate terminal tabs instead.

```bash
honcho start -f Procfile.honcho
```

---

## Running Tests

```bash
uv run python manage.py test
```

The test suite covers:
- **Unit tests** — Django ORM models, Pydantic models, `CourseFilter`, equivalency lookups, FLR rules
- **Integration tests** — View endpoints, file upload handling, session-based transcript preview, FLR toggle, report API
- **Performance tests** — N+1 query prevention, response time benchmarks

---

## Team

**Group Aesir** — Developed as a final year group project at the University of the West Indies.

| Name |
|---|
| Aaron Maharaj |
| Jonathan Dass |
| Kareem Farrell |
| Vikash Bissoon |

**Supervisors:** Mrs. Shareeda Mohammed, Mr. Nicholas Smith
