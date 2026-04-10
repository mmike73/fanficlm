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
