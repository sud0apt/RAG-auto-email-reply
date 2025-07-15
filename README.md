<h3 align="center">

<a name="readme-top"></a>

<strong>RAG-Auto-Email-Reply</strong>

</h3>

<div align="center">

<img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/RAG-Powered-green?logo=openai&logoColor=white" alt="RAG">
<img src="https://img.shields.io/badge/LLM-Automation-orange" alt="Automation">
<img src="https://img.shields.io/badge/Email-Responder-blueviolet" alt="Email">

</div>

<div align="center">

<p>
Empower your email workflows with intelligent, context-aware reply automation using RAG and Outlook integration.
</p>

</div>

---

## 🎯 Project Overview

**RAG‑auto‑email‑reply** streamlines email communication by automatically fetching incoming Outlook emails, gathering relevant context, and generating intelligent, human-like replies—powered by a Retrieval‑Augmented Generation (RAG) model. It includes a dedicated flow for NDA facilitation, reducing manual effort for routine exchanges.

---

## ✅ Features

- **Automated Outlook Integration**  
  Fetches and processes inbound emails automatically.

- **Smart Context Gathering**  
  Uses past threads, attachments, transcripts, and external data to inform reply generation.

- **RAG‑Powered Responses**  
  Generates replies that feel natural, relevant, and on‑point.

- **NDA Flow**  
  Streamlined handling of NDA requests, including detection, generation, and sending.

---

## 🔁 End-to-End Flow (How It Works)

1. **Webhook Triggered by Fireflies**  
   A POST webhook is received once transcription is completed on Fireflies.

2. **Transcript & Context Processing**  
   - Transcripts, notes, meeting metadata, and optional investor reports are fetched.
   - All information is chunked, embedded via SentenceTransformers, and indexed into a Qdrant vector DB.

3. **Keyword Contextual Search**  
   Queries for "NDA", "Data Room", and "Pre-NDA" are made in Qdrant to retrieve relevant context snippets.

4. **LLM-Powered Decision Logic**  
   Retrieved content is passed to GPT-4o, which decides:
   - If any flow is triggered (NDA, Data Room, Pre-NDA)
   - If not, no reply is sent.

5. **Role Identification**  
   Extracts speaker roles to determine the appropriate sender name for email personalization.

6. **Dynamic Email Generation**  
   GPT-4o crafts a reply using:
   - The detected scenario (e.g. NDA, Pre-NDA)
   - Extracted roles
   - A friendly, human-like tone
   - Ensures attachments are referenced clearly

7. **Outlook Integration**  
   The reply is sent via Microsoft Outlook using its API and the correct access token.

8. **Logging & Response**  
   The webhook logs decision outcomes, GPT analysis, and final status for audit/debugging.

---

## 🏗️ System Architecture

Modular Python design:

- `outlook.py` → Handles Outlook interaction (fetching & sending emails)  
- `context_gathering.py` → Assembles relevant conversational and document history  
- `RAG.py` → Core pipeline: fetch → gather → generate → reply  
- `phase2.py` → Manages NDA-specific logic flows  
- `database_utils.py`, `transcript_utils.py` → Support modules for history and transcript handling  

---

