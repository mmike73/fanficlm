# Project: fanficlm
## An Agentic LLM for Interactive Fanfiction Exploration

*Team: 5Gang*

*Members:*
* Chiș Bogdan Mihai - IA
* Mera Maria Mădălina - IR
* Moldovan Ovidiu Mihai - IR
* Muntean Larisa Maria - IR
* Toda Puiuleț Emanuela Coralia - IR

## Project Description

This project aims to develop an agentic Large Language Model (LLM) designed to enhance how users explore and interact with fanfiction content, particularly from platforms such as Wattpad.

The system acts as a creative assistant that helps users:
- discover fanfiction stories based on their interests,
- generate new story ideas,
- extend existing narratives through prompt-based interaction.

By combining retrieval and generation, the application enables a more immersive and personalized storytelling experience, especially for younger audiences.

---

## Architecture Overview

The system is based on a Retrieval-Augmented Generation (RAG) pipeline enhanced with agentic behavior and memory.

### Data Ingestion
- Supports continuous ingestion of fanfiction datasets.
- When content for a specific theme is missing, the system can retrieve external data via web search or scraping pipelines.
- Newly acquired data is processed and stored for future use.

### Text Processing and Chunking
To preserve narrative structure and improve retrieval:
- Semantic chunking splits text into coherent units such as paragraphs or sentences.
- Recursive chunking divides large texts into hierarchical sections (chapters, scenes, paragraphs).

### Embeddings and Vector Storage
- Text chunks are converted into embeddings.
- Stored in a vector database using Approximate Nearest Neighbor (ANN) search.
- Candidate technologies include:
  - FAISS (clustering-based search)
  - HNSW (graph-based similarity search)

### Retrieval-Augmented Generation (RAG)
- Retrieves relevant fanfiction excerpts and integrates them into generation.
- Improves coherence and thematic consistency.
- Reduces hallucinations by grounding responses in retrieved data.

### Agentic Layer
- A Smaller Language Model (SLM) decides when retrieval is necessary.
- Can trigger external tools such as search or scraping pipelines.
- Coordinates the interaction between system components.

### Memory Component
- Stores user preferences and interaction history.
- Enables personalized recommendations and context-aware story generation.

### Fine-Tuned Smaller Language Models (SLMs)
- Fine-tuned for:
  - question answering,
  - story continuation,
  - prompt-based generation.
- Improves performance on fanfiction-specific tasks.

### Safety and Content Filtering
- Filters harmful or inappropriate content.
- Ensures outputs are suitable for a young audience.

### Feedback Loop (RLHF)
- Collects and uses user feedback to improve system performance.
- Helps refine story quality, coherence, and safety.
- Can flag low-quality or problematic data.

---

## Evaluation

The system is evaluated using:
- Relevance
- Coherence
- Creativity
- Safety

Both automated metrics and human evaluation are considered.

---

## Tech Stack (Planned)
- Python / JavaScript
- Vector database: FAISS or HNSW-based solution
- Backend: Node.js or Python
- Models: Fine-tuned Smaller Language Models
- Data processing: scraping and ingestion pipelines



# FanficLM

A local LLM chat platform built with FastAPI and React, powered by a fine-tuned model served via LM Studio.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- [LM Studio](https://lmstudio.ai) installed on your machine

---

## 1. Set up LM Studio

1. Download and install [LM Studio](https://lmstudio.ai).
2. Open LM Studio and search for your model (e.g. `google/gemma-4-e4b`).
3. Download the model.
4. Go to the **Local Server** tab (the `↔` icon on the left sidebar).
5. Select your model from the dropdown and click **Start Server**.
6. The server runs on `http://127.0.0.1:1234` by default.

---

## 2. Configure the backend

Copy the example env file and fill in your values:

```bash
cd backend
cp .env.example .env
```

Edit `.env`:

```
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=google/gemma-4-e4b
TEMPERATURE=0.7
TIMEOUT=120
```

Make sure `LM_STUDIO_MODEL` matches exactly the model identifier shown in LM Studio's local server tab.

---

## 3. Run the backend

From the `backend/` directory:

```bash
# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
Swagger UI at `http://127.0.0.1:8000/docs`.

---

## 4. Run the frontend

From the `frontend/` directory:

```bash
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## System prompt

The default system prompt is located at:

```
backend/prompts/system_default.txt
```

Edit it freely to change the assistant's behaviour. Restart the backend after any changes.

---

## Project structure

```
fanficlm/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # route handlers
│   │   ├── core/               # config, logging
│   │   ├── schemas/            # Pydantic models
│   │   └── services/           # LM Studio client, future services
│   ├── prompts/                # system prompt .txt files
│   ├── data/                   # raw, processed datasets
│   ├── vector_store/           # ChromaDB persistent store
│   ├── feedback_store/         # RLHF feedback records
│   ├── reports/                # evaluation outputs
│   ├── .env
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.jsx
        ├── main.jsx
        └── index.css
```