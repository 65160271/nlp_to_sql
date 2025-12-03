"""
FastAPI Backend for Natural Language to SQL Converter
======================================================
This backend receives user questions along with database schema and dialect,
then uses SQLCoder (open-source text-to-SQL model) to generate SQL queries.
Supports automatic schema extraction from SQLite, PostgreSQL, and MySQL databases.
"""

import os
import re
from typing import List, Literal, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="NL2SQL API",
    description="Convert natural language questions to SQL queries using SQLCoder",
    version="2.0.0",
)

# Configure CORS for Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLCoder configuration via Ollama
# Default to localhost:11434 (Ollama default port)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
SQLCODER_MODEL = os.getenv("SQLCODER_MODEL", "gemma:7b")

print(f"Using Ollama at: {OLLAMA_BASE_URL}")
print(f"SQLCoder model: {SQLCODER_MODEL}")

# ---------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------

class ChatMessage(BaseModel):
    """Represents a single chat message in the conversation history."""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Request body for the /api/chat endpoint."""
    dialect: Literal["PostgreSQL", "MySQL", "SQLite", "SQL Server"] = Field(
        ..., description="The SQL dialect to generate queries for"
    )
    schema_text: str = Field(
        ..., min_length=1, description="The database schema (CREATE TABLE DDL or description)"
    )
    message: str = Field(
        ..., min_length=1, description="The user's natural language question"
    )
    history: Optional[List[ChatMessage]] = Field(
        default=[], description="Previous chat messages for context"
    )


class ChatResponse(BaseModel):
    """Response body for the /api/chat endpoint."""
    sql: str = Field(..., description="The generated SQL query or error message")


class DatabaseConnectionRequest(BaseModel):
    """Request body for database connection."""
    connection_string: str = Field(
        ..., description="Database connection string (e.g., sqlite:///path/to/db.sqlite, postgresql://user:pass@host:port/dbname, mysql://user:pass@host:port/dbname)"
    )


class DatabaseConnectionResponse(BaseModel):
    """Response body for database connection."""
    success: bool
    dialect: str
    schema_text: str
    tables: List[str]
    message: str


class TestConnectionRequest(BaseModel):
    """Request body for testing database connection."""
    connection_string: str


class TestConnectionResponse(BaseModel):
    """Response body for testing database connection."""
    success: bool
    dialect: str
    tables_count: int
    message: str


# ---------------------------------------------------------
# SQLCoder Prompt Template
# ---------------------------------------------------------

SQLCODER_PROMPT_TEMPLATE = """You are an expert SQL query generator used inside a chat-style web application.

Your single and only responsibility:
- Convert the user's natural-language question into EXACTLY ONE SQL query string.
- The output must be a valid SQL SELECT query for the given database dialect ({dialect}), based strictly on the provided schema.

Rules:
1. Dialect: {dialect}. Use syntax specific to this dialect.
2. Schema: Use ONLY the provided schema below. Do not invent tables.
3. Output: Return ONLY the SQL query. NO explanations. NO markdown.
4. Read-only: No INSERT/UPDATE/DELETE.

### Schema
{schema}

### Question
{question}

### SQL Query
"""


# แก้ไขฟังก์ชัน build_sqlcoder_prompt (ประมาณบรรทัด 142)
def build_sqlcoder_prompt(schema_text: str, question: str, dialect: str) -> str:
    """
    Build the prompt for DeepSeek model.
    """
    # ไม่ต้องเอา dialect ไปรวมกับ schema แล้ว เพราะใน Template เราแยกที่วางไว้ให้แล้ว
    return SQLCODER_PROMPT_TEMPLATE.format(
        question=question,
        schema=schema_text,
        dialect=dialect  # ส่ง dialect เข้าไปตรงๆ
    )


async def generate_sql_with_sqlcoder(prompt: str) -> str:
    """
    Generate SQL using SQLCoder via Ollama.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": SQLCODER_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 500,
                        "stop": ["[/SQL]", "###", "\n\n\n"]
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Make sure Ollama is running with SQLCoder model."
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama error: {str(e)}"
            )


def clean_sql_response(response: str) -> str:
    """
    Clean the SQL response from DeepSeek-R1.
    """
    # [สำคัญ] 1. ลบส่วนที่โมเดลกำลัง "คิด" (<think>...</think>) ออกไปให้หมด
    # flags=re.DOTALL จำเป็นมาก เพื่อให้ครอบคลุมข้อความหลายบรรทัด
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

    # 2. ลบ SQL tags (โค้ดเดิม)
    response = re.sub(r'\[/?SQL\]', '', response)
    
    # 3. ลบ Markdown code blocks (โค้ดเดิม)
    if "```" in response:
        # ใช้ Pattern นี้จะแม่นยำกว่าการ split
        match = re.search(r'```(?:sql)?\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if match:
            response = match.group(1)
        else:
            # Fallback วิธีเดิมถ้าหา pattern ไม่เจอ
            if response.startswith("```"):
                lines = response.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines)

    return response.strip()
    # Remove any trailing explanations (everything after the first semicolon followed by text)
    if ";" in response:
        parts = response.split(";")
        # Keep only the SQL part
        sql_parts = []
        for i, part in enumerate(parts):
            sql_parts.append(part)
            # Check if this looks like end of SQL
            if i < len(parts) - 1:
                next_part = parts[i + 1].strip()
                # If next part starts with a lowercase word (explanation), stop
                if next_part and next_part[0].islower() and not any(kw in next_part.upper()[:20] for kw in ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE']):
                    break
        response = ";".join(sql_parts)
        if not response.endswith(";"):
            response += ";"
    
    return response


# ---------------------------------------------------------
# Database Schema Extraction
# ---------------------------------------------------------

def detect_dialect_from_connection_string(connection_string: str) -> str:
    """
    Detect SQL dialect from connection string.
    """
    conn_lower = connection_string.lower()
    if conn_lower.startswith("sqlite"):
        return "SQLite"
    elif conn_lower.startswith("postgresql") or conn_lower.startswith("postgres"):
        return "PostgreSQL"
    elif conn_lower.startswith("mysql"):
        return "MySQL"
    elif conn_lower.startswith("mssql") or "sql server" in conn_lower:
        return "SQL Server"
    else:
        return "Unknown"


def extract_schema_from_database(connection_string: str) -> tuple[str, List[str], str]:
    """
    Extract schema from a database using SQLAlchemy.
    Returns (schema_ddl, table_names, dialect).
    """
    try:
        engine = create_engine(connection_string)
        inspector = inspect(engine)
        
        # Detect dialect
        dialect_name = engine.dialect.name
        if dialect_name == "sqlite":
            dialect = "SQLite"
        elif dialect_name == "postgresql":
            dialect = "PostgreSQL"
        elif dialect_name == "mysql":
            dialect = "MySQL"
        elif dialect_name == "mssql":
            dialect = "SQL Server"
        else:
            dialect = dialect_name.title()
        
        schema_parts = []
        table_names = inspector.get_table_names()
        
        for table_name in table_names:
            # Get columns
            columns = inspector.get_columns(table_name)
            pk_constraint = inspector.get_pk_constraint(table_name)
            pk_columns = pk_constraint.get("constrained_columns", []) if pk_constraint else []
            foreign_keys = inspector.get_foreign_keys(table_name)
            
            # Build CREATE TABLE statement
            column_defs = []
            for col in columns:
                col_def = f"  {col['name']} {col['type']}"
                if not col.get("nullable", True):
                    col_def += " NOT NULL"
                if col.get("default") is not None:
                    col_def += f" DEFAULT {col['default']}"
                if col["name"] in pk_columns and len(pk_columns) == 1:
                    col_def += " PRIMARY KEY"
                column_defs.append(col_def)
            
            # Add composite primary key if exists
            if len(pk_columns) > 1:
                column_defs.append(f"  PRIMARY KEY ({', '.join(pk_columns)})")
            
            # Add foreign keys
            for fk in foreign_keys:
                fk_cols = ", ".join(fk["constrained_columns"])
                ref_table = fk["referred_table"]
                ref_cols = ", ".join(fk["referred_columns"])
                column_defs.append(f"  FOREIGN KEY ({fk_cols}) REFERENCES {ref_table}({ref_cols})")
            
            create_stmt = f"CREATE TABLE {table_name} (\n" + ",\n".join(column_defs) + "\n);"
            schema_parts.append(create_stmt)
        
        schema_ddl = "\n\n".join(schema_parts)
        
        engine.dispose()
        return schema_ddl, table_names, dialect
        
    except SQLAlchemyError as e:
        raise HTTPException(status_code=400, detail=f"Database connection error: {str(e)}")


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "NL2SQL API is running",
        "model": "SQLCoder (via Ollama)",
        "ollama_url": OLLAMA_BASE_URL
    }


@app.get("/api/health")
async def health_check():
    """Check if Ollama and SQLCoder are available."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            
            sqlcoder_available = any(SQLCODER_MODEL in name for name in model_names)
            
            return {
                "ollama_available": True,
                "sqlcoder_available": sqlcoder_available,
                "available_models": model_names,
                "configured_model": SQLCODER_MODEL
            }
    except Exception as e:
        return {
            "ollama_available": False,
            "sqlcoder_available": False,
            "error": str(e),
            "configured_model": SQLCODER_MODEL
        }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Generate SQL from a natural language question using SQLCoder.
    
    This endpoint receives:
    - dialect: The SQL dialect (PostgreSQL, MySQL, SQLite, SQL Server)
    - schema_text: The database schema as DDL or description
    - message: The user's natural language question
    - history: Optional previous chat messages for context
    
    Returns:
    - sql: The generated SQL query or an error message
    """
    # Validate inputs
    if not request.schema_text.strip():
        raise HTTPException(status_code=400, detail="Schema text cannot be empty")
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        # Build the SQLCoder prompt
        # Include context from history if available
        context = ""
        if request.history:
            for msg in request.history[-4:]:  # Last 4 messages for context
                if msg.role == "user":
                    context += f"Previous question: {msg.content}\n"
                else:
                    context += f"Previous SQL: {msg.content}\n"
        
        question = request.message
        if context:
            question = f"{context}\nCurrent question: {request.message}"
        
        prompt = build_sqlcoder_prompt(
            schema_text=request.schema_text,
            question=question,
            dialect=request.dialect
        )
        
        # Generate SQL using SQLCoder
        raw_response = await generate_sql_with_sqlcoder(prompt)
        
        # Clean the response
        sql_response = clean_sql_response(raw_response)
        
        # Validate it's a SELECT query (read-only)
        sql_upper = sql_response.upper().strip()
        write_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "MERGE"]
        
        if any(sql_upper.startswith(kw) for kw in write_keywords):
            return ChatResponse(
                sql="-- ERROR: Write operations (INSERT/UPDATE/DELETE/DDL) are not allowed. Only SELECT queries are permitted."
            )
        
        if not sql_response or sql_response.isspace():
            return ChatResponse(
                sql="-- ERROR: Could not generate SQL for this question. Please try rephrasing."
            )
        
        return ChatResponse(sql=sql_response)
    
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"-- ERROR: Failed to generate SQL. {str(e)}"
        return ChatResponse(sql=error_message)


@app.post("/api/connect", response_model=DatabaseConnectionResponse)
async def connect_database(request: DatabaseConnectionRequest) -> DatabaseConnectionResponse:
    """
    Connect to a database and extract its schema.
    
    Supports:
    - SQLite: sqlite:///path/to/database.db
    - PostgreSQL: postgresql://user:password@host:port/dbname
    - MySQL: mysql://user:password@host:port/dbname
    """
    try:
        schema_ddl, table_names, dialect = extract_schema_from_database(request.connection_string)
        
        if not table_names:
            return DatabaseConnectionResponse(
                success=True,
                dialect=dialect,
                schema_text="",
                tables=[],
                message="Connected successfully, but no tables found in the database."
            )
        
        return DatabaseConnectionResponse(
            success=True,
            dialect=dialect,
            schema_text=schema_ddl,
            tables=table_names,
            message=f"Successfully connected to {dialect} database. Found {len(table_names)} table(s)."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        return DatabaseConnectionResponse(
            success=False,
            dialect="Unknown",
            schema_text="",
            tables=[],
            message=f"Failed to connect: {str(e)}"
        )


@app.post("/api/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest) -> TestConnectionResponse:
    """
    Test database connection without extracting full schema.
    """
    try:
        engine = create_engine(request.connection_string)
        
        # Try to connect
        with engine.connect() as conn:
            # Simple query to test connection
            if engine.dialect.name == "sqlite":
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            elif engine.dialect.name == "postgresql":
                result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            elif engine.dialect.name == "mysql":
                result = conn.execute(text("SHOW TABLES"))
            else:
                result = conn.execute(text("SELECT 1"))
            
            tables = list(result)
        
        dialect_name = engine.dialect.name
        if dialect_name == "sqlite":
            dialect = "SQLite"
        elif dialect_name == "postgresql":
            dialect = "PostgreSQL"
        elif dialect_name == "mysql":
            dialect = "MySQL"
        else:
            dialect = dialect_name.title()
        
        engine.dispose()
        
        return TestConnectionResponse(
            success=True,
            dialect=dialect,
            tables_count=len(tables),
            message=f"Successfully connected to {dialect} database with {len(tables)} table(s)."
        )
    
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            dialect="Unknown",
            tables_count=0,
            message=f"Connection failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
