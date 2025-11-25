"""
FastAPI Backend for Natural Language to SQL Converter
======================================================
This backend receives user questions along with database schema and dialect,
then uses an LLM to generate SQL queries without executing them.
"""

import os
from typing import List, Literal, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="NL2SQL API",
    description="Convert natural language questions to SQL queries",
    version="1.0.0",
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

# Initialize Gemini client
# Set your API key via environment variable: GEMINI_API_KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable is not set!")
    print("Get your API key from: https://aistudio.google.com/apikey")
else:
    print(f"Gemini API key loaded (starts with: {GEMINI_API_KEY[:10]}...)")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

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


# ---------------------------------------------------------
# System Prompt for the LLM
# ---------------------------------------------------------

SYSTEM_PROMPT = """You are an expert SQL query generator used inside a chat-style web application.

The application works like this:
- On the frontend (similar to a ChatGPT interface), the user uploads or pastes their database schema (as SQL DDL or a textual description of tables and columns) and then asks questions in natural language.
- On the backend, a server (FastAPI in Python) sends you:
  1) The database dialect being used (for example: PostgreSQL, MySQL, SQLite, SQL Server).
  2) The full database schema, as provided by the user.
  3) The user's latest question in natural language (which may be in English, Thai, or another language).
  4) Optionally, some previous chat messages.

Your single and only responsibility:
- Convert the user's natural-language question into EXACTLY ONE SQL query string.
- The output must be a valid SQL SELECT query for the given database dialect, based strictly on the provided schema.

You must follow these rules carefully:

1. Dialect awareness
   - You will receive the database dialect in plain text, such as:
     - "PostgreSQL"
     - "MySQL"
     - "SQLite"
     - "SQL Server"
   - You MUST generate SQL that is valid for that specific dialect.
   - Use appropriate syntax and functions for that dialect, especially for:
     - Date/time operations
     - String manipulation
     - Pagination and limiting results

2. Use ONLY the provided schema
   - You will be given the schema inside a <SCHEMA> ... </SCHEMA> block.
   - The schema may be:
     - Raw CREATE TABLE statements (SQL DDL), or
     - A structured description of tables, columns, data types, and relationships.
   - You MUST NOT:
     - Invent new tables.
     - Invent new columns.
     - Assume the existence of fields that are not present in the schema.
   - If the user's question refers to data that is not available in the schema, you may not fabricate structure.

3. Output format
   - Return ONLY the SQL query text.
   - Do NOT include any explanations.
   - Do NOT include natural-language comments.
   - Do NOT wrap the query in backticks or markdown code fences.
   - A trailing semicolon at the end is allowed but not required.
   - There must be exactly one query (no multiple statements).

4. Read-only restriction
   - Only read-only analytical queries are allowed.
   - You MUST NOT generate queries that modify or delete data:
     - No INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, TRUNCATE, CREATE, or any DDL/DML that changes the database.
   - If the user explicitly asks for write operations or schema changes, you must NOT generate such a query.
   - Instead, return a single line:
     -- ERROR: Write operations (INSERT/UPDATE/DELETE/DDL) are not allowed. Only SELECT queries are permitted.

5. Handling impossible or incompatible requests
   - If the question absolutely cannot be answered using the provided schema (e.g. the referenced table or column does not exist in <SCHEMA>), then:
     - Return a single-line SQL comment starting with:
       -- ERROR:
     - For example:
       -- ERROR: The question refers to tables or columns that do not exist in the provided schema.

6. Joins and relationships
   - If the schema indicates foreign keys or common naming conventions (e.g. user_id, customer_id), use sensible JOINs.
   - Use explicit JOIN syntax (e.g. INNER JOIN, LEFT JOIN) with ON clauses.
   - Use clear table aliases when helpful.

7. Aggregations and grouping
   - If the user asks for totals, counts, averages, minimum, maximum, or similar aggregations:
     - Use the appropriate aggregate functions (COUNT, SUM, AVG, MIN, MAX, etc.).
     - Include a proper GROUP BY clause when needed.

8. Time ranges and natural language
   - When the user mentions "today", "yesterday", "last week", "last month", "this year", etc., convert those into date filters using:
     - The correct "current time" function and date manipulation functions for the specified dialect.
   - You may interpret:
     - "last month" as the full previous calendar month.
     - "last week" as the previous 7 days or previous calendar week, using a reasonable convention as long as it is consistent.

9. Language of the question
   - The user's question may be in English, Thai, or other languages.
   - You ONLY need to understand it well enough to generate the correct SQL.
   - Your output must always be SQL-only, never a natural language explanation.

Summary:
- Your response must be EXACTLY ONE of the following:
  1) A single valid SQL SELECT query, OR
  2) A single-line SQL comment starting with `-- ERROR:` describing why the query cannot be generated.

Follow these instructions strictly."""


def build_user_prompt(dialect: str, schema_text: str, message: str) -> str:
    """
    Build the user prompt that includes dialect, schema, and the question.
    """
    return f"""Database dialect: {dialect}

<SCHEMA>
{schema_text}
</SCHEMA>

User question:
"{message}"
"""


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "NL2SQL API is running"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Generate SQL from a natural language question.
    
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
        # Build the full prompt with system instructions and history
        full_prompt = SYSTEM_PROMPT + "\n\n"
        
        # Add chat history if provided (limit to last 10 messages for context)
        if request.history:
            for msg in request.history[-10:]:
                role_label = "User" if msg.role == "user" else "Assistant"
                full_prompt += f"{role_label}: {msg.content}\n\n"
        
        # Add the current user prompt
        user_prompt = build_user_prompt(
            dialect=request.dialect,
            schema_text=request.schema_text,
            message=request.message
        )
        full_prompt += f"User: {user_prompt}"
        
        # Call Gemini with low temperature for deterministic output
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2000,
        )
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
        )
        
        # Extract and clean the response
        sql_response = response.text.strip()
        
        # Remove any markdown code fences if the model added them despite instructions
        if sql_response.startswith("```"):
            lines = sql_response.split("\n")
            # Remove first line (```sql or ```)
            lines = lines[1:]
            # Remove last line if it's closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            sql_response = "\n".join(lines).strip()
        
        return ChatResponse(sql=sql_response)
    
    except Exception as e:
        # Return a user-friendly error message
        error_message = f"-- ERROR: Failed to generate SQL. {str(e)}"
        return ChatResponse(sql=error_message)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

