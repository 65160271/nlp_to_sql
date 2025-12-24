"""
Integration Example: Adding RAG SQL Service to Existing main.py
================================================================

This snippet shows how to integrate the RAGSQLService into your existing
FastAPI backend (main.py) with minimal changes.

OPTION 1: Add as a new endpoint (recommended for testing)
OPTION 2: Replace existing /api/chat logic (for production)
"""

# ============================================================================
# OPTION 1: Add RAG as a New Endpoint
# ============================================================================

# Step 1: Add import at the top of main.py
from rag_sql_service import RAGSQLService

# Step 2: Add global service instance (after app initialization)
rag_service: Optional[RAGSQLService] = None

# Step 3: Initialize service on startup
@app.on_event("startup")
async def startup_rag_service():
    """Initialize RAG service on startup."""
    global rag_service
    print("🚀 Initializing RAG SQL Service...")
    rag_service = RAGSQLService(
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
        ollama_model="gemma:7b",
        ollama_base_url="http://localhost:11434",
        cache_maxsize=10,
        verbose=False  # Set to True for debugging
    )
    print("✅ RAG SQL Service ready!")

# Step 4: Add new request/response models
class RAGChatRequest(BaseModel):
    """Request for RAG-based SQL generation."""
    message: str = Field(..., min_length=1, description="Natural language question")
    connection_string: str = Field(..., description="Database connection string")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of tables to consider")

class RAGChatResponse(BaseModel):
    """Response for RAG-based SQL generation."""
    sql: str
    cached: bool
    relevant_tables: List[str]
    processing_time: float

# Step 5: Add new endpoint
@app.post("/api/rag-chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest) -> RAGChatResponse:
    """
    Generate SQL using RAG schema linking.
    
    This endpoint uses Dynamic RAG to:
    1. Extract and cache database schema
    2. Retrieve only relevant tables using semantic search
    3. Generate SQL with filtered context
    """
    if rag_service is None:
        raise HTTPException(503, "RAG service not initialized")
    
    try:
        import time
        start = time.time()
        
        # Check if cached
        was_cached = request.connection_string in rag_service.schema_cache
        
        # Generate SQL
        sql = rag_service.get_sql_response(
            question=request.message,
            db_url=request.connection_string,
            top_k=request.top_k
        )
        
        # Get relevant tables from cache
        if request.connection_string in rag_service.schema_cache:
            _, _, table_names = rag_service.schema_cache[request.connection_string]
            relevant_tables = table_names[:request.top_k]
        else:
            relevant_tables = []
        
        processing_time = time.time() - start
        
        return RAGChatResponse(
            sql=sql,
            cached=was_cached,
            relevant_tables=relevant_tables,
            processing_time=round(processing_time, 2)
        )
        
    except Exception as e:
        raise HTTPException(500, f"Failed to generate SQL: {str(e)}")


# ============================================================================
# OPTION 2: Replace Existing /api/chat Logic
# ============================================================================

# Modify the existing /api/chat endpoint to use RAG when connection_string is provided

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Generate SQL from a natural language question.
    
    If connection_string is provided, uses RAG schema linking.
    Otherwise, uses the traditional approach with full schema.
    """
    # Validate inputs
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    try:
        # NEW: Use RAG if connection_string is provided
        if request.connection_string and rag_service:
            sql = rag_service.get_sql_response(
                question=request.message,
                db_url=request.connection_string,
                top_k=3  # Use top 3 tables
            )
            
            # Clean and validate
            sql_upper = sql.upper().strip()
            write_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "MERGE"]
            
            if any(sql_upper.startswith(kw) for kw in write_keywords):
                return ChatResponse(
                    sql="-- ERROR: Write operations are not allowed. Only SELECT queries permitted."
                )
            
            return ChatResponse(sql=sql)
        
        # EXISTING: Traditional approach (full schema from frontend)
        else:
            if not request.schema_text.strip():
                raise HTTPException(status_code=400, detail="Schema text cannot be empty")
            
            # ... rest of existing logic ...
            # (keep all existing code for backward compatibility)
    
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"-- ERROR: Failed to generate SQL. {str(e)}"
        return ChatResponse(sql=error_message)


# ============================================================================
# USAGE FROM FRONTEND
# ============================================================================

"""
// Vue.js Frontend Example

// Option 1: Use new RAG endpoint
async function generateSQLWithRAG(question, dbUrl) {
  const response = await fetch('http://localhost:8000/api/rag-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: question,
      connection_string: dbUrl,
      top_k: 3
    })
  });
  
  const data = await response.json();
  console.log('SQL:', data.sql);
  console.log('Cached:', data.cached);
  console.log('Tables used:', data.relevant_tables);
  console.log('Time:', data.processing_time);
}

// Option 2: Use existing endpoint with connection_string
async function generateSQL(question, dbUrl) {
  const response = await fetch('http://localhost:8000/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dialect: 'SQLite',
      schema_text: '',  // Empty - will use RAG
      message: question,
      connection_string: dbUrl  // Triggers RAG mode
    })
  });
  
  const data = await response.json();
  console.log('SQL:', data.sql);
}
"""


# ============================================================================
# TESTING
# ============================================================================

"""
# Test the new endpoint
curl -X POST http://localhost:8000/api/rag-chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show all products with Paracetamol",
    "connection_string": "sqlite:////Users/kittawan/nlp_to_sql/database2-2.sqlite",
    "top_k": 3
  }'

# Expected response:
{
  "sql": "SELECT * FROM product WHERE name LIKE '%Paracetamol%';",
  "cached": false,
  "relevant_tables": ["product", "product_price", "product_unit"],
  "processing_time": 21.6
}

# Second request (cached):
{
  "sql": "SELECT * FROM supplier;",
  "cached": true,
  "relevant_tables": ["supplier", "supplier_type", "product_price"],
  "processing_time": 2.8
}
"""
