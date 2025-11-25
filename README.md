# NL2SQL - Natural Language to SQL Converter

A web application that converts natural language questions into SQL queries. Built with Vue 3 + TypeScript (frontend) and FastAPI (backend).

![NL2SQL Screenshot](https://via.placeholder.com/800x500?text=NL2SQL+Chat+Interface)

## Features

- 📝 **Schema Input**: Upload `.sql` or `.txt` files, or paste your schema directly
- 💬 **Chat Interface**: ChatGPT-like conversational UI
- 🔄 **Multiple Dialects**: Support for PostgreSQL, MySQL, SQLite, and SQL Server
- 🔒 **Read-Only**: Only generates SELECT queries (no data modification)
- 🌍 **Multi-language**: Understands questions in English, Thai, and other languages

## Project Structure

```
data_frontend/
├── backend/
│   ├── main.py              # FastAPI server with /api/chat endpoint
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.vue          # Main Vue component
│   │   ├── main.ts          # App entry point
│   │   └── style.css        # Global styles
│   ├── package.json         # Node dependencies
│   └── vite.config.ts       # Vite configuration
└── README.md
```

## Prerequisites

- **Python 3.9+**
- **Node.js 18+**
- **OpenAI API Key** (or compatible API)

## Setup Instructions

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"
# On Windows: set OPENAI_API_KEY=your-api-key-here

# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`.

### 2. Frontend Setup

```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at `http://localhost:5173`.

## Usage

1. **Open the app** at `http://localhost:5173`

2. **Provide your database schema** (left sidebar):
   - Upload a `.sql` or `.txt` file containing `CREATE TABLE` statements
   - Or paste the schema directly into the textarea

3. **Select your SQL dialect**:
   - PostgreSQL
   - MySQL
   - SQLite
   - SQL Server

4. **Ask questions in natural language** (chat area):
   - "Show me all users who registered this month"
   - "What's the total sales per product category?"
   - "List the top 10 customers by order count"

5. **Get SQL queries** as responses without executing them

## Example Schema

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    total_amount DECIMAL(10,2),
    order_date DATE,
    status VARCHAR(20)
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200),
    price DECIMAL(10,2),
    category VARCHAR(100)
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER,
    unit_price DECIMAL(10,2)
);
```

## Example Questions

- "Show total revenue per month for 2024"
- "Who are the top 5 customers by total spending?"
- "What products have never been ordered?"
- "Count orders by status for each user"
- "Average order value by day of week"

## API Reference

### POST /api/chat

Generate SQL from natural language.

**Request Body:**
```json
{
  "dialect": "PostgreSQL",
  "schema_text": "CREATE TABLE users (...)",
  "message": "Show all users who registered today",
  "history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous SQL"}
  ]
}
```

**Response:**
```json
{
  "sql": "SELECT * FROM users WHERE DATE(created_at) = CURRENT_DATE;"
}
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | Your OpenAI API key | Yes |

### Using Alternative LLM Providers

You can use any OpenAI-compatible API by modifying `backend/main.py`:

```python
# For Azure OpenAI
from openai import AzureOpenAI
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-02-01",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# For other compatible providers (e.g., Ollama, LocalAI)
client = OpenAI(
    base_url="http://localhost:11434/v1",  # Ollama example
    api_key="ollama"
)
```

## Development

### Backend Development
```bash
cd backend
uvicorn main:app --reload
```

### Frontend Development
```bash
cd frontend
npm run dev
```

### Build for Production

**Frontend:**
```bash
cd frontend
npm run build
```

**Backend:**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Tech Stack

- **Frontend**: Vue 3, TypeScript, Vite, Axios
- **Backend**: FastAPI, Pydantic, OpenAI SDK
- **Styling**: Custom CSS with CSS Variables

## License

MIT License - feel free to use this project for any purpose.

