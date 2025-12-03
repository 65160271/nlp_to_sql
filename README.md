# NL2SQL - Natural Language to SQL Converter

A web application that converts natural language questions into SQL queries using **SQLCoder** (open-source text-to-SQL model). Built with Vue 3 + TypeScript (frontend) and FastAPI (backend).

## Features

- 🤖 **SQLCoder Model**: Uses open-source SQLCoder via Ollama (no API keys needed!)
- 🔌 **Direct Database Connection**: Connect to SQLite, PostgreSQL, or MySQL and auto-fetch schema
- 📝 **Schema Input**: Upload `.sql` or `.txt` files, or paste your schema directly
- 💬 **Chat Interface**: ChatGPT-like conversational UI
- 🔄 **Multiple Dialects**: Support for PostgreSQL, MySQL, SQLite, and SQL Server
- 🔒 **Read-Only**: Only generates SELECT queries (no data modification)
- 🌍 **Multi-language**: Understands questions in English, Thai, and other languages

## Project Structure

```
nlp_to_sql/
├── backend/
│   ├── main.py              # FastAPI server with SQLCoder integration
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
- **Ollama** (for running SQLCoder locally)

## Setup Instructions

### 1. Install Ollama and SQLCoder Model

```bash
# Install Ollama (macOS)
brew install ollama

# Or download from https://ollama.ai/download

# Start Ollama service
ollama serve

# Pull the SQLCoder model (in a new terminal)
ollama pull sqlcoder
```

> **Note**: SQLCoder model is ~4GB. Alternatively, you can use `ollama pull sqlcoder:7b-q4_0` for a smaller quantized version.

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`.

**Environment Variables (optional):**
```bash
export OLLAMA_BASE_URL="http://localhost:11434"  # Default Ollama URL
export SQLCODER_MODEL="sqlcoder"                  # Default model name
```

### 3. Frontend Setup

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

### Method 1: Connect to Your Database (Recommended)

1. **Open the app** at `http://localhost:5173`

2. **Enter your database connection string** in the "Database Connection" card:
   - **SQLite**: `sqlite:///path/to/database.db`
   - **PostgreSQL**: `postgresql://user:password@localhost:5432/dbname`
   - **MySQL**: `mysql://user:password@localhost:3306/dbname`

3. **Click "Test"** to verify the connection

4. **Click "Connect & Fetch Schema"** to auto-load the schema

5. **Ask questions** in natural language!

### Method 2: Manual Schema Input

1. **Provide your database schema** (left sidebar):
   - Upload a `.sql` or `.txt` file containing `CREATE TABLE` statements
   - Or paste the schema directly into the textarea

2. **Select your SQL dialect**

3. **Ask questions** in natural language

## Example Connection Strings

```
# SQLite (local file)
sqlite:///./mydata.db
sqlite:////absolute/path/to/database.db

# PostgreSQL
postgresql://postgres:password@localhost:5432/mydb
postgresql://user:pass@host.docker.internal:5432/database

# MySQL
mysql://root:password@localhost:3306/mydb
mysql://user:pass@192.168.1.100:3306/database
```

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
- "แสดงรายชื่อลูกค้าที่สั่งซื้อมากกว่า 10 ครั้ง" (Thai)

## API Reference

### GET /api/health

Check Ollama and SQLCoder availability.

**Response:**
```json
{
  "ollama_available": true,
  "sqlcoder_available": true,
  "available_models": ["sqlcoder", "llama3"],
  "configured_model": "sqlcoder"
}
```

### POST /api/chat

Generate SQL from natural language.

**Request Body:**
```json
{
  "dialect": "PostgreSQL",
  "schema_text": "CREATE TABLE users (...)",
  "message": "Show all users who registered today",
  "history": []
}
```

**Response:**
```json
{
  "sql": "SELECT * FROM users WHERE DATE(created_at) = CURRENT_DATE;"
}
```

### POST /api/connect

Connect to a database and extract its schema.

**Request Body:**
```json
{
  "connection_string": "postgresql://user:pass@localhost:5432/mydb"
}
```

**Response:**
```json
{
  "success": true,
  "dialect": "PostgreSQL",
  "schema_text": "CREATE TABLE users (...)",
  "tables": ["users", "orders", "products"],
  "message": "Successfully connected..."
}
```

### POST /api/test-connection

Test database connection without fetching schema.

**Request Body:**
```json
{
  "connection_string": "sqlite:///./test.db"
}
```

**Response:**
```json
{
  "success": true,
  "dialect": "SQLite",
  "tables_count": 5,
  "message": "Successfully connected..."
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `SQLCODER_MODEL` | Model name to use | `sqlcoder` |

### Using Different SQLCoder Versions

```bash
# Standard SQLCoder
ollama pull sqlcoder

# SQLCoder 7B (smaller, faster)
ollama pull sqlcoder:7b

# SQLCoder with quantization (smallest)
ollama pull sqlcoder:7b-q4_0
```

Update the environment variable to use a different model:
```bash
export SQLCODER_MODEL="sqlcoder:7b-q4_0"
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
- **Backend**: FastAPI, Pydantic, SQLAlchemy, httpx
- **AI Model**: SQLCoder (via Ollama)
- **Database Support**: SQLite, PostgreSQL, MySQL
- **Styling**: Custom CSS with CSS Variables

## Troubleshooting

### "Cannot connect to Ollama"
1. Make sure Ollama is running: `ollama serve`
2. Verify the URL: `curl http://localhost:11434/api/tags`
3. Check if SQLCoder is installed: `ollama list`

### "Model not found"
```bash
# Pull the model again
ollama pull sqlcoder
```

### Database Connection Issues
- **SQLite**: Use absolute paths or `./` prefix for relative paths
- **PostgreSQL**: Install `libpq-dev` on Linux: `apt install libpq-dev`
- **MySQL**: Make sure the MySQL server allows remote connections

## License

MIT License - feel free to use this project for any purpose.
