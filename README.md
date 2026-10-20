# Travel Database SQL RAG Assistant

A natural-language to SQL assistant built for querying a MySQL travel database (bookings, flights, hotels, customers, and cities).

## Features

- **City Normalization & Spell Checking**: Cleans and normalizes old/informal city names (e.g. Bombay -> Mumbai, Bangalore -> Bengaluru, New Delhi -> Delhi) and short codes (e.g. Blr, Goi) while preserving query syntax and punctuation.
- **SQL Schema & Relationship Inspection**: Extracts database schemas and foreign keys (both explicit and logical relationships) to provide accurate context to the model.
- **Resilient Execution & Error Handling**: Gracefully handles database query errors, Windows character encodings, and LLM API quota errors without crashing.
- **CLI Query Support**: Pass any question directly as command-line arguments to test different scenarios.

## Setup

1. **Activate the Virtual Environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables** in `.env`:
   ```env
   # API Keys (Hugging Face or OpenAI)
   HF_TOKEN=your_huggingface_token
   OPENAI_API_KEY=your_openai_api_key

   # Database Connection
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=RAG
   DB_USER=loco
   DB_PASSWORD=erRor100@23
   ```

## Usage

Run with the default question:
```powershell
python main.py
```

Or ask custom questions directly:
```powershell
python main.py "How many bookings were cancelled, and what percentage of all bookings does that represent?"
python main.py "Which customer has spent the most money on bookings, and how much?"
python main.py "Show me all flights from Mumbai to Delhi that are under 2 hours in Business class."
python main.py "What's the total amount I'd pay for a 3-night stay at the cheapest hotel in Goa?"
python main.py "Which hotels in Jaipur have a pool and free wifi?"
```
