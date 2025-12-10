"""
FastAPI Backend for Natural Language to SQL Converter
======================================================
This backend receives user questions along with database schema and dialect,
then uses SQLCoder (open-source text-to-SQL model) to generate SQL queries.
Supports automatic schema extraction from SQLite, PostgreSQL, and MySQL databases.
"""

import os
import re
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from thefuzz import fuzz

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
SQLCODER_MODEL = os.getenv("SQLCODER_MODEL", "sqlcoder")

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
    table_description: Optional[str] = Field(
        default="", description="Optional description of the tables and their relationships"
    )
    message: str = Field(
        ..., min_length=1, description="The user's natural language question"
    )
    history: Optional[List[ChatMessage]] = Field(
        default=[], description="Previous chat messages for context"
    )
    enable_value_injection: bool = Field(
        default=True, description="Enable dynamic value injection to prevent hallucinations"
    )
    searchable_columns: Optional[List[str]] = Field(
        default=None, description="List of table.column pairs to search (e.g., ['employees.first_name', 'departments.name']). If None, searches common text columns."
    )
    connection_string: Optional[str] = Field(
        default=None, description="Database connection string for value injection. Required if enable_value_injection is True."
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
# Dynamic Value Injection Functions
# ---------------------------------------------------------

# Common stop words to filter out from user queries
STOP_WORDS = {
    'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'should', 'could', 'may', 'might', 'must', 'can', 'shall',
    'a', 'an', 'and', 'or', 'but', 'if', 'then', 'else', 'when',
    'at', 'by', 'for', 'with', 'about', 'against', 'between',
    'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off',
    'over', 'under', 'again', 'further', 'then', 'once',
    'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
    'show', 'get', 'find', 'list', 'give', 'tell', 'me', 'all', 'any',
    'select', 'from', 'where', 'order', 'group', 'having', 'limit',
    'of', 'that', 'this', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
    'we', 'they', 'them', 'their', 'my', 'your', 'his', 'her', 'its', 'our'
}


def extract_keywords(user_query: str) -> List[str]:
    """
    Extract meaningful keywords from user query by removing stop words.
    
    Args:
        user_query: The user's natural language question
        
    Returns:
        List of keywords to search for in the database
    """
    # Convert to lowercase and split into words
    words = re.findall(r'\b\w+\b', user_query.lower())
    
    # Filter out stop words and very short words
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    
    return keywords


def search_column_values(
    connection_string: str,
    table_name: str,
    column_name: str,
    keywords: List[str],
    similarity_threshold: int = 70,
    max_results: int = 5
) -> List[Tuple[str, int]]:
    """
    Search a specific column for values matching keywords using fuzzy matching.
    
    Args:
        connection_string: Database connection string
        table_name: Name of the table to search
        column_name: Name of the column to search
        keywords: List of keywords to search for
        similarity_threshold: Minimum fuzzy match score (0-100)
        max_results: Maximum number of results to return
        
    Returns:
        List of (value, confidence_score) tuples
    """
    try:
        engine = create_engine(connection_string)
        
        # Build LIKE conditions for initial filtering
        like_conditions = " OR ".join([f"{column_name} LIKE :keyword{i}" for i in range(len(keywords))])
        
        if not like_conditions:
            return []
        
        # Query to get distinct values from the column
        query = text(f"""
            SELECT DISTINCT {column_name}
            FROM {table_name}
            WHERE {column_name} IS NOT NULL
            AND ({like_conditions})
            LIMIT 100
        """)
        
        # Create keyword parameters with wildcards
        params = {f"keyword{i}": f"%{kw}%" for i, kw in enumerate(keywords)}
        
        with engine.connect() as conn:
            result = conn.execute(query, params)
            db_values = [row[0] for row in result if row[0]]
        
        # Apply fuzzy matching to filter and score results
        scored_values = []
        for db_value in db_values:
            # Calculate best match score across all keywords
            max_score = 0
            for keyword in keywords:
                score = fuzz.partial_ratio(keyword.lower(), str(db_value).lower())
                max_score = max(max_score, score)
            
            if max_score >= similarity_threshold:
                scored_values.append((str(db_value), max_score))
        
        # Sort by confidence score (descending) and return top N
        scored_values.sort(key=lambda x: x[1], reverse=True)
        
        engine.dispose()
        return scored_values[:max_results]
        
    except Exception as e:
        print(f"Error searching {table_name}.{column_name}: {str(e)}")
        return []


def find_relevant_values(
    user_query: str,
    connection_string: str,
    searchable_columns: Optional[List[str]] = None,
    similarity_threshold: int = 70
) -> Dict[str, List[Tuple[str, int]]]:
    """
    Find relevant values from the database that match keywords in the user query.
    
    Args:
        user_query: The user's natural language question
        connection_string: Database connection string
        searchable_columns: List of 'table.column' pairs to search. If None, searches common text columns.
        similarity_threshold: Minimum fuzzy match score (0-100)
        
    Returns:
        Dictionary mapping 'table.column' to list of (value, confidence_score) tuples
    """
    # Extract keywords from user query
    keywords = extract_keywords(user_query)
    
    if not keywords:
        return {}
    
    # If no searchable columns specified, try to detect text columns
    if not searchable_columns:
        try:
            engine = create_engine(connection_string)
            inspector = inspect(engine)
            searchable_columns = []
            
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                for col in columns:
                    # Search text/varchar columns, skip IDs and dates
                    col_type_str = str(col['type']).upper()
                    col_name_lower = col['name'].lower()
                    
                    if ('VARCHAR' in col_type_str or 'TEXT' in col_type_str or 'CHAR' in col_type_str) and \
                       not col_name_lower.endswith('_id') and \
                       'date' not in col_name_lower and \
                       'time' not in col_name_lower:
                        searchable_columns.append(f"{table_name}.{col['name']}")
            
            engine.dispose()
        except Exception as e:
            print(f"Error detecting searchable columns: {str(e)}")
            return {}
    
    # Search each column for matching values
    matched_values = {}
    
    for column_spec in searchable_columns:
        if '.' not in column_spec:
            continue
            
        table_name, column_name = column_spec.split('.', 1)
        
        values = search_column_values(
            connection_string=connection_string,
            table_name=table_name,
            column_name=column_name,
            keywords=keywords,
            similarity_threshold=similarity_threshold
        )
        
        if values:
            matched_values[column_spec] = values
    
    return matched_values


# ---------------------------------------------------------
# SQLCoder Prompt Template
# ---------------------------------------------------------

SQLCODER_PROMPT_TEMPLATE = """### Task
Generate a SQL query to answer [QUESTION]{question}[/QUESTION]

### Instructions
1. Use ONLY the column names that exist in the schema below
2. Do NOT invent or assume column names
3. Follow the exact table and column names from the schema
4. Use proper JOIN conditions based on foreign key relationships shown in the schema
5. If a column doesn't exist in the schema, you cannot use it
6. Do NOT include example data, sample values, or WHERE clauses with hardcoded temporary data
7. Generate queries that retrieve actual data from the database, not example results
8. Do NOT include example data, sample values, or WHERE clauses with hardcoded temporary data
### Database Schema
The query will run on a database with the following schema:
{schema}
{table_description}
### Answer
Given the database schema, here is the SQL query that answers [QUESTION]{question}[/QUESTION]
[SQL]
"""


def build_sqlcoder_prompt(
    schema_text: str, 
    question: str, 
    dialect: str, 
    table_description: str = "",
    matched_values: Optional[Dict[str, List[Tuple[str, int]]]] = None
) -> str:
    """
    Build the prompt for SQLCoder model.
    
    Args:
        schema_text: Database schema DDL
        question: User's natural language question
        dialect: SQL dialect
        table_description: Optional table context
        matched_values: Optional dict mapping column names to (value, confidence_score) tuples
    """
    # Add dialect hint to the schema
    schema_with_dialect = f"-- Database dialect: {dialect}\n{schema_text}"
    
    # Add table description if provided
    description_section = ""
    if table_description and table_description.strip():
        description_section = f"\n### Table Context\n{table_description.strip()}\n"
    
    # Add matched values section if provided
    matched_values_section = ""
    if matched_values and any(matched_values.values()):
        matched_values_section = "\n### Context / Matched Values\n"
        matched_values_section += "The following actual values from the database match keywords in the user's question.\n"
        matched_values_section += "USE THESE EXACT VALUES in your query instead of inventing or guessing values:\n\n"
        
        for column, values in matched_values.items():
            if values:
                matched_values_section += f"**{column}**:\n"
                for value, confidence in values[:5]:  # Top 5 matches
                    matched_values_section += f"  - '{value}' (confidence: {confidence}%)\n"
                matched_values_section += "\n"
    
    return SQLCODER_PROMPT_TEMPLATE.format(
        question=question,
        schema=schema_with_dialect,
        table_description=description_section + matched_values_section
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
    Clean the SQL response from SQLCoder.
    """
    # Remove special tokens like <s>, </s>, <|im_start|>, <|im_end|>, etc.
    response = re.sub(r'</?s>', '', response)
    response = re.sub(r'<\|im_start\|>', '', response)
    response = re.sub(r'<\|im_end\|>', '', response)
    response = re.sub(r'<\|.*?\|>', '', response)
    
    # Remove SQL tags if present
    response = re.sub(r'\[/?SQL\]', '', response)
    
    # Remove markdown code fences
    if response.startswith("```"):
        lines = response.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        response = "\n".join(lines)
    
    # Clean up whitespace
    response = response.strip()
    
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
        
        # Dynamic Value Injection: Find relevant values from database
        matched_values = None
        if request.enable_value_injection and request.connection_string:
            try:
                matched_values = find_relevant_values(
                    user_query=request.message,
                    connection_string=request.connection_string,
                    searchable_columns=request.searchable_columns,
                    similarity_threshold=70
                )
                print(f"Value injection found {len(matched_values)} matching columns")
            except Exception as e:
                # Don't fail the request if value injection fails
                print(f"Value injection error (continuing without it): {str(e)}")
                matched_values = None
        
        prompt = build_sqlcoder_prompt(
            schema_text=request.schema_text,
            question=question,
            dialect=request.dialect,
            table_description=request.table_description or "",
            matched_values=matched_values
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
