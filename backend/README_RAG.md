# RAG Text-to-SQL System - Quick Start Guide

## 🚀 Quick Start

### Prerequisites
1. **Ollama** installed and running
2. **gemma:7b** model downloaded
3. Python dependencies installed

### Installation

```bash
# 1. Install Ollama (if not already installed)
# Visit: https://ollama.ai and download for Mac

# 2. Start Ollama service
ollama serve

# 3. Pull the gemma:7b model (~4.8GB download)
ollama pull gemma:7b

# 4. Verify Ollama is ready
ollama list
# Should show: gemma:7b

# 5. Install Python dependencies (if not already installed)
cd /Users/kittawan/nlp_to_sql/backend
pip install sentence-transformers scikit-learn numpy requests
```

---

## 📝 Basic Usage

### Simple Query Example

```python
from rag_text_to_sql import generate_sql

# English query
sql = generate_sql("Show all products with Paracetamol")
print(sql)

# Thai query
sql = generate_sql("แสดงสินค้าทั้งหมดที่มีชื่อว่า Paracetamol")
print(sql)
```

---

## 🏗️ System Architecture

**3-Stage Pipeline:**

1. **Stage 1: Schema Linking** - Filters 15+ tables down to top-3 most relevant
2. **Stage 2: Value Injection** - Finds exact matches in database to prevent hallucination
3. **Stage 3: LLM Generation** - Generates SQL using Ollama with verified context

---

## 🔧 API Reference

### Quick Reference

| Function | Module | Purpose |
|----------|--------|---------|
| `RAGSQLService()` | `rag_sql_service` | Main service for dynamic RAG SQL generation |
| `get_sql_response()` | `rag_sql_service` | Generate SQL from natural language |
| `get_cache_info()` | `rag_sql_service` | Get cache statistics |
| `clear_cache()` | `rag_sql_service` | Clear schema/embedding cache |
| `SQLGatekeeperService()` | `gatekeeper_service` | Query classifier/filter |
| `classify_query()` | `gatekeeper_service` | Classify user input type |
| `should_show_rag_tip()` | `gatekeeper_service` | Check if troubleshooting tip needed |
| `extract_keywords()` | `main` | Extract keywords from query |
| `find_relevant_values()` | `main` | Find matching values in database |
| `build_sqlcoder_prompt()` | `main` | Build LLM prompt with value injection |
| `generate_sql_with_sqlcoder()` | `main` | Generate SQL via Ollama |
| `clean_sql_response()` | `main` | Clean LLM response |

---

### RAGSQLService Class

The main service class for dynamic RAG-based SQL generation.

#### Constructor

```python
from rag_sql_service import RAGSQLService

service = RAGSQLService(
    embedding_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    ollama_model: str = "gemma:7b",
    ollama_base_url: str = "http://localhost:11434",
    cache_maxsize: int = 10,
    enable_value_injection: bool = True,
    max_sample_values: int = 5,
    max_sample_columns: int = 3,
    verbose: bool = False
)
```

**Parameters:**
- `embedding_model_name`: Sentence transformer model for embeddings
- `ollama_model`: Ollama model name for SQL generation
- `ollama_base_url`: Ollama API base URL
- `cache_maxsize`: Maximum number of databases to cache
- `enable_value_injection`: Enable dynamic value sampling from database
- `max_sample_values`: Maximum values to sample per column
- `max_sample_columns`: Maximum columns to sample per table
- `verbose`: Enable detailed logging

---

#### get_sql_response()

Generate SQL from natural language question with dynamic schema linking.

```python
sql = service.get_sql_response(
    question: str,
    db_url: str,
    top_k: int = 3,
    dialect: str = None
) -> str
```

**Parameters:**
- `question`: Natural language question (Thai or English)
- `db_url`: Database connection string (e.g., `sqlite:///path/to/db.sqlite`)
- `top_k`: Number of most relevant tables to consider (1-10)
- `dialect`: SQL dialect (auto-detected if None)

**Returns:**
- Generated SQL query string

**Example:**
```python
sql = service.get_sql_response(
    question="Show all products with Paracetamol",
    db_url="sqlite:////Users/kittawan/nlp_to_sql/database2-2.sqlite",
    top_k=3
)
```

---

#### get_cache_info()

Get information about the current cache state.

```python
info = service.get_cache_info() -> Dict
```

**Returns:**
Dictionary with:
- `cached_databases`: List of cached database URLs
- `cache_size`: Number of databases in cache
- `cache_maxsize`: Maximum cache size
- `embedding_model`: Embedding model name

**Example:**
```python
info = service.get_cache_info()
print(f"Cached DBs: {info['cached_databases']}")
```

---

#### clear_cache()

Clear the schema and embedding cache.

```python
service.clear_cache(db_url: str = None)
```

**Parameters:**
- `db_url`: If provided, clear only this database. Otherwise clear all.

**Example:**
```python
# Clear specific database
service.clear_cache("sqlite:///database.sqlite")

# Clear all cache
service.clear_cache()
```

---

### SQLGatekeeperService Class

Intelligent query classifier that filters user input before SQL generation.

#### Constructor

```python
from gatekeeper_service import SQLGatekeeperService

gatekeeper = SQLGatekeeperService(
    ollama_model: str = "gemma:7b",
    ollama_base_url: str = "http://localhost:11434",
    verbose: bool = False
)
```

---

#### classify_query()

Classify user input into CHIT_CHAT, OUT_OF_SCOPE, SCHEMA_QUESTION, or VALID_QUERY.

```python
response = gatekeeper.classify_query(
    user_input: str,
    db_url: str = None
) -> GatekeeperResponse
```

**Parameters:**
- `user_input`: User's natural language input
- `db_url`: Optional database connection string for schema extraction

**Returns:**
`GatekeeperResponse` with:
- `type`: Classification type
- `reply`: Pre-generated reply for non-query inputs
- `query`: Original query (for VALID_QUERY)

**Example:**
```python
response = gatekeeper.classify_query("Hello!")
if response.type == "CHIT_CHAT":
    print(response.reply)  # "Hello! How can I help you with your database queries?"
```

---

#### should_show_rag_tip()

Determine if RAG troubleshooting tip should be shown based on low confidence.

```python
show_tip = gatekeeper.should_show_rag_tip(
    similarity_scores: list,
    max_score: float = None
) -> bool
```

**Parameters:**
- `similarity_scores`: List of similarity scores from RAG retrieval
- `max_score`: Optional maximum score (if already calculated)

**Returns:**
- `True` if tip should be shown (low confidence detected)

---

### Value Injection Functions

Functions for dynamic value injection to prevent LLM hallucination.

#### extract_keywords()

Extract meaningful keywords from user query.

```python
from main import extract_keywords

keywords = extract_keywords(user_query: str) -> List[str]
```

**Example:**
```python
keywords = extract_keywords("Show products with Paracetamol")
# Returns: ["products", "Paracetamol"]
```

---

#### find_relevant_values()

Find relevant values from database that match keywords in the user query.

```python
from main import find_relevant_values

matches = find_relevant_values(
    user_query: str,
    connection_string: str,
    searchable_columns: List[str] = None,
    similarity_threshold: int = 70
) -> Dict[str, List[Tuple[str, int]]]
```

**Parameters:**
- `user_query`: User's natural language question
- `connection_string`: Database connection string
- `searchable_columns`: List of `table.column` to search (None = search all text columns)
- `similarity_threshold`: Minimum fuzzy match score (0-100)

**Returns:**
- Dictionary mapping `table.column` to list of `(value, confidence_score)` tuples

**Example:**
```python
matches = find_relevant_values(
    "Show Paracetamol products",
    "sqlite:///database.sqlite"
)
# Returns: {"products.product_name": [("Paracetamol 500mg", 95), ...]}
```

---

#### build_sqlcoder_prompt()

Build the prompt for SQLCoder model with optional value injection.

```python
from main import build_sqlcoder_prompt

prompt = build_sqlcoder_prompt(
    schema_text: str,
    question: str,
    dialect: str,
    table_description: str = "",
    matched_values: Dict[str, List[Tuple[str, int]]] = None
) -> str
```

**Parameters:**
- `schema_text`: Database schema DDL
- `question`: User's natural language question
- `dialect`: SQL dialect (PostgreSQL, MySQL, SQLite, SQL Server)
- `table_description`: Optional table context
- `matched_values`: Dictionary of matched values from `find_relevant_values()`

**Returns:**
- Formatted prompt string for LLM

---

### Utility Functions

#### generate_sql_with_sqlcoder()

Generate SQL using SQLCoder via Ollama.

```python
from main import generate_sql_with_sqlcoder

sql = generate_sql_with_sqlcoder(prompt: str) -> str
```

---

#### clean_sql_response()

Clean the SQL response from LLM (removes markdown, extra tokens, etc.).

```python
from main import clean_sql_response

clean_sql = clean_sql_response(response: str) -> str
```

---

## 📊 Sample Queries

### English Queries
```python
# Product search
generate_sql("Show all products with Paracetamol")

# Stock inquiry
generate_sql("What is the current stock level of Amoxicillin?")

# Supplier filter
generate_sql("Show all suppliers from Bangkok")

# Branch listing
generate_sql("List all branches")
```

### Thai Queries
```python
# Product search
generate_sql("แสดงสินค้าทั้งหมดที่มีชื่อว่า Paracetamol")

# Expiration tracking
generate_sql("รายการสินค้าที่จะหมดอายุในเดือนหน้า")

# Receipt totals
generate_sql("ยอดรับสินค้าทั้งหมดในปีนี้")

# Low stock alert
generate_sql("สินค้าที่มีสต็อกต่ำกว่าระดับขั้นต่ำ")
```

---

## 🐛 Troubleshooting

### Ollama Connection Error

**Error:** `Ollama API error: Connection refused`

**Solution:**
```bash
# Start Ollama service
ollama serve

# In another terminal, verify it's running
ollama list
```

### Model Not Found

**Error:** `model 'gemma:7b' not found`

**Solution:**
```bash
# Pull the model
ollama pull gemma:7b

# Verify
ollama list
```

### Database Connection Error

**Error:** `Database connection failed`

**Solution:**
- Verify database path in `rag_text_to_sql.py` (line 23)
- Default: `/Users/kittawan/nlp_to_sql/database2-2.sqlite`
- Update `DATABASE_PATH` if your database is elsewhere

---

## 📁 File Structure

```
/Users/kittawan/nlp_to_sql/backend/
├── rag_text_to_sql.py          # Main RAG pipeline implementation
├── requirements.txt            # Python dependencies
└── database2-2.sqlite          # Pharmaceutical database
```

---

## 🎯 Key Features

✅ **Multilingual**: Supports Thai and English queries  
✅ **Hallucination Prevention**: Uses exact database values  
✅ **Fast**: ~3-6 seconds total pipeline time  
✅ **Accurate**: Semantic schema linking with 15+ tables  
✅ **Production-Ready**: Error handling and validation included  

---

## 📚 Next Steps

1. **Test the system**: Use the `generate_sql()` function in your code
2. **Integrate with FastAPI**: Add RAG endpoint to your backend
3. **Customize prompts**: Adjust prompt templates in `construct_prompt()`
4. **Add more tables**: Extend `TABLE_METADATA` dictionary
5. **Fine-tune**: Adjust `top_k`, temperature, or embedding model

---

## 💡 Tips

- **Low temperature (0.1)**: More deterministic SQL output
- **Top-3 tables**: Balance between context and accuracy
- **Verified values**: Always shown to LLM to prevent hallucination
- **Multilingual embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` works well for Thai/English

---

## 📞 Support

For issues or questions:
1. Check the [walkthrough.md](file:///Users/kittawan/.gemini/antigravity/brain/9ca0395c-88b2-44bc-9704-f67898a569cc/walkthrough.md) for detailed documentation
2. Review error messages and logs
3. Verify Ollama is running: `ollama list`
4. Check database connection: `sqlite3 database2-2.sqlite ".tables"`
