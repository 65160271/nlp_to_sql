#!/usr/bin/env python3
"""
RAG SQL Service - Dynamic RAG Schema Linking for Text-to-SQL
=============================================================

This service class implements a robust Dynamic RAG (Retrieval-Augmented Generation)
pipeline for converting natural language questions to SQL queries.

Architecture:
1. **Check Cache**: Verify if schema embeddings exist for the given db_url
2. **Indexing**: Extract schema, generate embeddings, cache results
3. **Retrieval**: Find top-k relevant tables using cosine similarity
4. **Generation**: Send filtered schema + question to LLM (Ollama)

Author: Senior Backend & AI Engineer
Optimized for: MacBook Air M4 (Local LLM & Embedding)
Date: 2025-12-10
"""

import re
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np
import ollama
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError


class RAGSQLService:
    """
    RAG-based SQL generation service with intelligent schema linking.
    
    Features:
    - In-memory caching of schema embeddings
    - Multilingual support (Thai/English)
    - Dynamic schema extraction from any database
    - Cosine similarity-based table retrieval
    - Integration with Ollama LLM
    
    Example:
        >>> service = RAGSQLService()
        >>> sql = service.get_sql_response(
        ...     question="Show all products",
        ...     db_url="sqlite:///path/to/db.sqlite"
        ... )
        >>> print(sql)
    """
    
    def __init__(
        self,
        embedding_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        ollama_model: str = "gemma:7b",
        ollama_base_url: str = "http://localhost:11434",
        cache_maxsize: int = 10,
        enable_value_injection: bool = True,
        max_sample_values: int = 5,
        max_sample_columns: int = 3,
        verbose: bool = False
    ):
        """
        Initialize the RAG SQL Service.
        
        Args:
            embedding_model_name: Sentence transformer model for embeddings
            ollama_model: Ollama model name for SQL generation
            ollama_base_url: Ollama API base URL
            cache_maxsize: Maximum number of databases to cache
            enable_value_injection: Enable dynamic value injection to prevent hallucination
            max_sample_values: Maximum values to sample per column
            max_sample_columns: Maximum columns to sample per table
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.cache_maxsize = cache_maxsize
        self.enable_value_injection = enable_value_injection
        self.max_sample_values = max_sample_values
        self.max_sample_columns = max_sample_columns
        
        # In-memory cache: {db_url: (embeddings, table_descriptions, table_names)}
        self.schema_cache: Dict[str, Tuple[np.ndarray, List[str], List[str]]] = {}
        
        # Load embedding model once (expensive operation)
        if self.verbose:
            print(f"🔧 Loading embedding model: {embedding_model_name}...")
            start = time.time()
        
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
        if self.verbose:
            print(f"✅ Model loaded in {time.time() - start:.2f}s")
    
    def _log(self, message: str):
        """Internal logging helper."""
        if self.verbose:
            print(message)
    
    def _extract_schema_from_db(self, db_url: str) -> Tuple[List[str], List[str]]:
        """
        Extract table names and column information from database.
        
        Args:
            db_url: Database connection string
            
        Returns:
            Tuple of (table_names, table_descriptions)
            
        Raises:
            SQLAlchemyError: If database connection fails
        """
        self._log(f"📊 Extracting schema from: {db_url}")
        
        try:
            engine = create_engine(db_url)
            inspector = inspect(engine)
            
            table_names = inspector.get_table_names()
            table_descriptions = []
            
            for table_name in table_names:
                # Get columns for this table
                columns = inspector.get_columns(table_name)
                column_info = []
                
                for col in columns:
                    col_type = str(col['type'])
                    col_name = col['name']
                    nullable = "" if col.get('nullable', True) else " NOT NULL"
                    column_info.append(f"{col_name} {col_type}{nullable}")
                
                # Create a description string for embedding
                description = f"Table: {table_name}\nColumns: {', '.join(column_info)}"
                table_descriptions.append(description)
            
            engine.dispose()
            
            self._log(f"✅ Extracted {len(table_names)} tables")
            return table_names, table_descriptions
            
        except SQLAlchemyError as e:
            raise SQLAlchemyError(f"Failed to connect to database: {str(e)}")
    
    def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text descriptions to embed
            
        Returns:
            NumPy array of embeddings (shape: [n_texts, embedding_dim])
        """
        self._log(f"🔢 Generating embeddings for {len(texts)} tables...")
        start = time.time()
        
        embeddings = self.embedding_model.encode(texts, convert_to_numpy=True)
        
        self._log(f"✅ Embeddings generated in {time.time() - start:.2f}s")
        return embeddings
    
    def _should_sample_column(self, column_name: str, column_type: str) -> bool:
        """
        Determine if a column should have value sampling.
        
        Args:
            column_name: Name of the column
            column_type: SQL type of the column
            
        Returns:
            True if column should be sampled
        """
        column_lower = column_name.lower()
        type_upper = str(column_type).upper()
        
        # Skip these columns (high cardinality or not useful)
        skip_patterns = [
            'uuid', 'guid',
            'created_at', 'updated_at', 'modified_at', 'deleted_at',
            'timestamp',
            'description', 'note', 'comment', 'detail', 'remark',
            'email', 'phone', 'address', 'url',
            'password', 'token', 'hash', 'salt'
        ]
        for pattern in skip_patterns:
            if pattern in column_lower:
                return False
        
        # IMPORTANT: Sample these columns (likely to have useful values)
        sample_patterns = [
            'status', 'state', 'type', 'category', 'class',
            'name', 'title', 'code', 'label', 'tag',
            'role', 'level', 'priority', 'grade',
            'lot', 'batch', 'serial',  # Include lot/batch numbers!
            'number'  # Include various number fields (except IDs)
        ]
        
        # Skip if it's an ID column
        if column_lower.endswith('id') or column_lower.startswith('id'):
            return False
        
        for pattern in sample_patterns:
            if pattern in column_lower:
                return True
        
        # Sample VARCHAR/TEXT columns (likely categorical)
        if any(t in type_upper for t in ['VARCHAR', 'CHAR', 'TEXT', 'STRING']):
            return True
        
        # Sample ENUM columns
        if 'ENUM' in type_upper:
            return True
        
        return False
    
    def _sample_column_values(
        self,
        db_url: str,
        table_name: str,
        column_name: str,
        limit: int = 5
    ) -> List[str]:
        """
        Sample distinct values from a column.
        
        Args:
            db_url: Database connection string
            table_name: Name of the table
            column_name: Name of the column
            limit: Maximum number of values to sample
            
        Returns:
            List of sample values (as strings)
        """
        try:
            from sqlalchemy import text
            engine = create_engine(db_url)
            
            # Build safe query with proper quoting
            query = text(f'SELECT DISTINCT "{column_name}" FROM "{table_name}" WHERE "{column_name}" IS NOT NULL LIMIT :limit')
            
            with engine.connect() as conn:
                result = conn.execute(query, {"limit": limit})
                values = [str(row[0]) for row in result if row[0] is not None]
            
            engine.dispose()
            return values[:limit]
            
        except Exception as e:
            self._log(f"   ⚠️  Error sampling {table_name}.{column_name}: {str(e)}")
            return []
    
    def _build_value_context(
        self,
        db_url: str,
        selected_tables: List[str]
    ) -> str:
        """
        Build a context string with sample values from selected tables.
        
        Args:
            db_url: Database connection string
            selected_tables: List of table names to sample from
            
        Returns:
            Formatted string with sample values
        """
        if not self.enable_value_injection:
            return ""
        
        self._log(f"📊 Sampling values from {len(selected_tables)} tables...")
        
        try:
            engine = create_engine(db_url)
            inspector = inspect(engine)
            
            value_lines = []
            
            for table_name in selected_tables:
                columns = inspector.get_columns(table_name)
                sampled_count = 0
                
                for col in columns:
                    if sampled_count >= self.max_sample_columns:
                        break
                    
                    col_name = col['name']
                    col_type = str(col['type'])
                    
                    # Check if we should sample this column
                    if not self._should_sample_column(col_name, col_type):
                        continue
                    
                    # Sample values
                    values = self._sample_column_values(
                        db_url, table_name, col_name, self.max_sample_values
                    )
                    
                    if values:
        # Format values based on type
                        if any(t in col_type.upper() for t in ['INT', 'DECIMAL', 'FLOAT', 'NUMERIC']):
                            formatted_values = ", ".join(values)
                        else:
                            # Quote string values and escape quotes
                            escaped_values = [v.replace("'", "''") for v in values]
                            formatted_values = ", ".join([f"'{v}'" for v in escaped_values])
                        
                        value_lines.append(f"  - {table_name}.{col_name}: {formatted_values}")
                        sampled_count += 1
            
            engine.dispose()
            
            if value_lines:
                context = "\n### Sample Values (Use these actual values from the database)\n" + "\n".join(value_lines)
                self._log(f"✅ Sampled {len(value_lines)} columns")
                return context
            else:
                return ""
                
        except Exception as e:
            self._log(f"⚠️  Error building value context: {str(e)}")
            return ""
    
    def _get_or_create_index(
        self, 
        db_url: str
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """
        Get cached index or create new one for the given database.
        
        This method implements the caching logic:
        1. Check if db_url exists in cache
        2. If yes, return cached embeddings and metadata
        3. If no, extract schema, generate embeddings, cache, and return
        
        Args:
            db_url: Database connection string
            
        Returns:
            Tuple of (embeddings, table_descriptions, table_names)
        """
        # Check cache first
        if db_url in self.schema_cache:
            self._log(f"✅ Using cached index for: {db_url}")
            return self.schema_cache[db_url]
        
        # Cache miss - create new index
        self._log(f"⚠️  Cache miss - creating new index for: {db_url}")
        
        # Step 1: Extract schema
        table_names, table_descriptions = self._extract_schema_from_db(db_url)
        
        # Step 2: Generate embeddings
        embeddings = self._generate_embeddings(table_descriptions)
        
        # Step 3: Cache the results
        self.schema_cache[db_url] = (embeddings, table_descriptions, table_names)
        
        # Step 4: Implement LRU eviction if cache is too large
        if len(self.schema_cache) > self.cache_maxsize:
            # Remove oldest entry (simple FIFO for now)
            oldest_key = next(iter(self.schema_cache))
            del self.schema_cache[oldest_key]
            self._log(f"🗑️  Evicted oldest cache entry: {oldest_key}")
        
        return embeddings, table_descriptions, table_names
    
    def _retrieve_relevant_tables(
        self,
        question: str,
        embeddings: np.ndarray,
        table_descriptions: List[str],
        table_names: List[str],
        top_k: int = 3
    ) -> Tuple[List[str], List[str], List[float]]:
        """
        Retrieve top-k most relevant tables for the question.
        
        Args:
            question: User's natural language question
            embeddings: Pre-computed table embeddings
            table_descriptions: Table description strings
            table_names: Table names
            top_k: Number of tables to retrieve
            
        Returns:
            Tuple of (selected_table_names, selected_descriptions, similarity_scores)
        """
        self._log(f"🔍 Retrieving top-{top_k} relevant tables...")
        
        # Embed the question
        question_embedding = self.embedding_model.encode([question], convert_to_numpy=True)[0]
        
        # Compute cosine similarity
        # Normalize vectors
        question_norm = question_embedding / np.linalg.norm(question_embedding)
        embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # Compute similarities
        similarities = np.dot(embeddings_norm, question_norm)
        
        # Get top-k indices
        top_k_indices = np.argsort(similarities)[::-1][:top_k]
        
        # Extract results
        selected_tables = [table_names[i] for i in top_k_indices]
        selected_descriptions = [table_descriptions[i] for i in top_k_indices]
        selected_scores = [float(similarities[i]) for i in top_k_indices]
        
        if self.verbose:
            self._log("📋 Selected tables:")
            for table, score in zip(selected_tables, selected_scores):
                self._log(f"   • {table} (similarity: {score:.3f})")
        
        return selected_tables, selected_descriptions, selected_scores
    
    def _build_filtered_schema(
        self,
        db_url: str,
        selected_tables: List[str]
    ) -> str:
        """
        Build a filtered schema DDL for selected tables.
        
        Args:
            db_url: Database connection string
            selected_tables: List of table names to include
            
        Returns:
            Schema DDL string
        """
        try:
            engine = create_engine(db_url)
            inspector = inspect(engine)
            
            schema_parts = []
            
            for table_name in selected_tables:
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
            
            engine.dispose()
            return "\n\n".join(schema_parts)
            
        except Exception as e:
            self._log(f"⚠️  Error building schema: {str(e)}")
            # Fallback to simple schema
            return "\n\n".join([f"-- Table: {table}" for table in selected_tables])
    
    def _generate_sql_with_llm(
        self,
        question: str,
        filtered_schema: str,
        value_context: str = "",
        dialect: str = "SQLite"
    ) -> str:
        """
        Generate SQL using Ollama LLM.
        
        Args:
            question: User's natural language question
            filtered_schema: Filtered database schema DDL
            value_context: Sample values from database (for value injection)
            dialect: SQL dialect
            
        Returns:
            Generated SQL query
        """
        self._log(f"🤖 Generating SQL with {self.ollama_model}...")
        
        # Build enhanced prompt with value injection
        prompt = f"""### Task
Generate a SIMPLE and FOCUSED SQL query to answer the following question.

### Database Schema
The query will run on a {dialect} database with the following schema:
{filtered_schema}
{value_context}

### Critical Instructions
1. **KEEP IT SIMPLE**: Only SELECT the columns the user explicitly asked for
2. **AVOID UNNECESSARY JOINS**: Only join tables if absolutely required to answer the question
3. **EXACT COLUMN NAMES**: Use ONLY column names that exist in the schema above
4. **NO HALLUCINATION**: Do NOT invent column names, table names, or placeholder values
5. **USE SAMPLE VALUES**: If sample values are provided above, use them as reference for filtering
6. **TEXT SEARCH**: For text searches, prefer LIKE '%keyword%' over exact matches
7. **VALID SYNTAX**: Generate a valid {dialect} query
8. **NO DUMMY DATA**: Do NOT use placeholder values like 'John Doe', 'example@email.com', 'LOT-123', etc.

### Question
{question}

### Answer
Given the database schema, here is the SQL query that answers the question:
[SQL]
"""
        
        try:
            # Call Ollama API
            start = time.time()
            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 500,
                    "stop": ["[/SQL]", "###", "\n\n\n"]
                }
            )
            
            sql = response['response'].strip()
            
            self._log(f"✅ SQL generated in {time.time() - start:.2f}s")
            
            # Clean the response
            sql = self._clean_sql_response(sql)
            
            return sql
            
        except Exception as e:
            raise Exception(f"Ollama API error: {str(e)}")
    
    def _clean_sql_response(self, response: str) -> str:
        """
        Clean the SQL response from LLM.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Cleaned SQL query
        """
        # Remove special tokens
        response = re.sub(r'</?s>', '', response)
        response = re.sub(r'<\|im_start\|>', '', response)
        response = re.sub(r'<\|im_end\|>', '', response)
        response = re.sub(r'<\|.*?\|>', '', response)
        
        # Remove SQL tags
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
        
        # Ensure it ends with semicolon
        if response and not response.endswith(";"):
            response += ";"
        
        return response
    
    def get_sql_response(
        self,
        question: str,
        db_url: str,
        top_k: int = 3,
        dialect: Optional[str] = None
    ) -> str:
        """
        Main public method: Generate SQL from natural language question.
        
        This is the primary interface for the service. It orchestrates:
        1. Cache check / schema extraction
        2. Embedding generation (if needed)
        3. Retrieval of relevant tables
        4. SQL generation via LLM
        
        Args:
            question: Natural language question (Thai or English)
            db_url: Database connection string
            top_k: Number of tables to consider (default: 3)
            dialect: SQL dialect (auto-detected if None)
            
        Returns:
            Generated SQL query string
            
        Example:
            >>> service = RAGSQLService()
            >>> sql = service.get_sql_response(
            ...     "Show all products with Paracetamol",
            ...     "sqlite:///database.sqlite"
            ... )
        """
        total_start = time.time()
        
        self._log(f"\n{'='*70}")
        self._log(f"🚀 RAG SQL Service - Processing Query")
        self._log(f"{'='*70}")
        self._log(f"Question: {question}")
        self._log(f"Database: {db_url}")
        self._log(f"Top-K: {top_k}\n")
        
        try:
            # Step 1: Get or create index (with caching)
            embeddings, table_descriptions, table_names = self._get_or_create_index(db_url)
            
            # Step 2: Retrieve relevant tables
            selected_tables, selected_descriptions, scores = self._retrieve_relevant_tables(
                question=question,
                embeddings=embeddings,
                table_descriptions=table_descriptions,
                table_names=table_names,
                top_k=top_k
            )
            
            # Step 3: Build filtered schema
            filtered_schema = self._build_filtered_schema(db_url, selected_tables)
            
            # Step 4: Build value context (NEW - Value Injection)
            value_context = self._build_value_context(db_url, selected_tables)
            
            # Step 5: Detect dialect if not provided
            if dialect is None:
                if db_url.startswith("sqlite"):
                    dialect = "SQLite"
                elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
                    dialect = "PostgreSQL"
                elif db_url.startswith("mysql"):
                    dialect = "MySQL"
                else:
                    dialect = "SQL"
            
            # Step 6: Generate SQL with LLM (with value injection)
            sql = self._generate_sql_with_llm(
                question=question,
                filtered_schema=filtered_schema,
                value_context=value_context,  # Pass sampled values
                dialect=dialect
            )
            
            total_time = time.time() - total_start
            self._log(f"\n{'='*70}")
            self._log(f"✅ Total processing time: {total_time:.2f}s")
            self._log(f"{'='*70}\n")
            
            return sql
            
        except Exception as e:
            self._log(f"\n❌ Error: {str(e)}\n")
            raise
    
    def get_cache_info(self) -> Dict:
        """
        Get information about the current cache state.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_databases": list(self.schema_cache.keys()),
            "cache_size": len(self.schema_cache),
            "cache_maxsize": self.cache_maxsize,
            "embedding_model": self.embedding_model.get_sentence_embedding_dimension()
        }
    
    def clear_cache(self, db_url: Optional[str] = None):
        """
        Clear the schema cache.
        
        Args:
            db_url: If provided, clear only this database. Otherwise clear all.
        """
        if db_url:
            if db_url in self.schema_cache:
                del self.schema_cache[db_url]
                self._log(f"🗑️  Cleared cache for: {db_url}")
            else:
                self._log(f"⚠️  No cache entry found for: {db_url}")
        else:
            self.schema_cache.clear()
            self._log("🗑️  Cleared all cache entries")


# Convenience function for quick usage
def generate_sql(question: str, db_url: str, top_k: int = 3, verbose: bool = True) -> str:
    """
    Convenience function to generate SQL without managing service instance.
    
    Note: This creates a new service instance each time. For better performance,
    create a RAGSQLService instance and reuse it.
    
    Args:
        question: Natural language question
        db_url: Database connection string
        top_k: Number of tables to consider
        verbose: Enable verbose logging
        
    Returns:
        Generated SQL query
    """
    service = RAGSQLService(verbose=verbose)
    return service.get_sql_response(question, db_url, top_k)
