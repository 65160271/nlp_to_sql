"""
RAG-based Text-to-SQL System
A complete 3-stage pipeline for converting natural language queries to SQL:
1. Stage 1: Semantic Schema Linking (Vector Search)
2. Stage 2: Dynamic Value Injection (Hallucination Prevention)
3. Stage 3: LLM SQL Generation (Ollama)

Supports Thai and English queries.
Author: Senior AI Engineer
"""

import os
import re
import sqlite3
from typing import List, Dict, Tuple, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import requests
import json
import functools
from sqlalchemy import create_engine, inspect, MetaData, Table
from sqlalchemy.exc import SQLAlchemyError

# ============================================================================
# CONFIGURATION
# ============================================================================

DATABASE_PATH = "/Users/kittawan/nlp_to_sql/database2-2.sqlite"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma:7b"
TOP_K_TABLES = 3

# ============================================================================
# DATABASE METADATA - Comprehensive Schema Descriptions (Thai + English)
# ============================================================================

TABLE_METADATA = {
    "product": {
        "description_en": "Product master data including medicines, medical supplies, and pharmaceutical products with pricing, storage, and regulatory information",
        "description_th": "ข้อมูลหลักของสินค้า รวมถึงยา เวชภัณฑ์ และผลิตภัณฑ์ทางเภสัชกรรม พร้อมข้อมูลราคา การจัดเก็บ และข้อมูลกำกับดูแล",
        "key_columns": ["product_code", "product_name", "generic_name", "standard_cost", "barcode"],
        "searchable_columns": ["product_name", "generic_name", "product_code"],
        "schema": """
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    product_code TEXT UNIQUE NOT NULL,
    product_name TEXT NOT NULL,
    generic_name TEXT,
    standard_cost NUMERIC NOT NULL,
    storage_location TEXT,
    stock_min INTEGER,
    stock_max INTEGER,
    packing_size TEXT,
    reg_no TEXT,
    indications TEXT,
    warnings TEXT,
    barcode TEXT,
    isactive BOOLEAN DEFAULT 1,
    manufacturerId INTEGER,
    distributorId INTEGER,
    productGroupId INTEGER,
    base_unit TEXT
)"""
    },
    
    "stock": {
        "description_en": "Current inventory levels and stock information by product, branch, and lot number with expiration tracking",
        "description_th": "ระดับสินค้าคงคลังปัจจุบันและข้อมูลสต็อกตามสินค้า สาขา และหมายเลขล็อต พร้อมการติดตามวันหมดอายุ",
        "key_columns": ["productId", "branchId", "remaining", "lot_number", "exp_date"],
        "searchable_columns": ["lot_number"],
        "schema": """
CREATE TABLE stock (
    id INTEGER PRIMARY KEY,
    productId INTEGER NOT NULL,
    product_unit_id INTEGER,
    branchId INTEGER NOT NULL,
    quantity_initial INTEGER DEFAULT 0,
    remaining FLOAT NOT NULL,
    status TEXT,
    lot_number TEXT,
    cost_unit FLOAT,
    exp_date DATE,
    mfg_date DATE,
    received_date DATETIME,
    is_active BOOLEAN DEFAULT 1,
    grDetailId INTEGER,
    FOREIGN KEY (productId) REFERENCES product(id),
    FOREIGN KEY (branchId) REFERENCES branch(id)
)"""
    },
    
    "goods_receipt": {
        "description_en": "Goods receipt documents for incoming inventory from suppliers including tax, discount, and payment terms",
        "description_th": "เอกสารรับสินค้าจากซัพพลายเออร์ รวมถึงภาษี ส่วนลด และเงื่อนไขการชำระเงิน",
        "key_columns": ["code", "receive_date", "gr_total", "status", "distributorId", "branchId"],
        "searchable_columns": ["code", "tax_invoice_number"],
        "schema": """
CREATE TABLE goods_receipt (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    po_date DATETIME,
    po_code TEXT,
    date_document DATETIME NOT NULL,
    receive_date DATETIME,
    po_total FLOAT,
    tax FLOAT NOT NULL,
    tax_total FLOAT NOT NULL,
    gr_total FLOAT NOT NULL,
    status TEXT NOT NULL,
    tax_invoice_number TEXT,
    credit_days INTEGER DEFAULT 30,
    vat_percent NUMERIC DEFAULT 7,
    note TEXT,
    poId INTEGER,
    distributorId INTEGER,
    branchId INTEGER,
    userId INTEGER,
    FOREIGN KEY (distributorId) REFERENCES supplier(id),
    FOREIGN KEY (branchId) REFERENCES branch(id)
)"""
    },
    
    "goods_receipt_details": {
        "description_en": "Line items of goods receipt showing product quantities, prices, discounts, and lot information",
        "description_th": "รายการสินค้าในเอกสารรับสินค้า แสดงจำนวน ราคา ส่วนลด และข้อมูลล็อต",
        "key_columns": ["grId", "productId", "receive_quantity", "receive_price_before_tax", "lot_number_before"],
        "searchable_columns": ["lot_number_before", "production_number"],
        "schema": """
CREATE TABLE goods_receipt_details (
    id INTEGER PRIMARY KEY,
    product_unit_id INTEGER,
    lot_number_before TEXT NOT NULL,
    receive_quantity NUMERIC NOT NULL,
    receive_unit TEXT NOT NULL,
    receive_price_before_tax FLOAT NOT NULL,
    receive_price_after_discount FLOAT NOT NULL,
    production_number TEXT,
    mfg_date DATE,
    exp_date DATE,
    total_receive_quantity NUMERIC NOT NULL,
    cost_unit FLOAT NOT NULL,
    total_price_product FLOAT NOT NULL,
    gr_total FLOAT NOT NULL,
    grId INTEGER,
    productId INTEGER,
    FOREIGN KEY (grId) REFERENCES goods_receipt(id),
    FOREIGN KEY (productId) REFERENCES product(id)
)"""
    },
    
    "purchase_order": {
        "description_en": "Purchase orders to suppliers with order totals, tax calculations, and delivery tracking",
        "description_th": "ใบสั่งซื้อสินค้าจากซัพพลายเออร์ พร้อมยอดรวม การคำนวณภาษี และการติดตามการจัดส่ง",
        "key_columns": ["code", "order_date", "po_total", "status", "supplierId", "branchId"],
        "searchable_columns": ["code", "contact"],
        "schema": """
CREATE TABLE purchase_order (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    contact TEXT NOT NULL,
    address TEXT NOT NULL,
    date DATE NOT NULL,
    po_total REAL DEFAULT 0,
    tax FLOAT DEFAULT 0,
    tax_total FLOAT DEFAULT 0,
    status TEXT NOT NULL,
    order_date DATETIME NOT NULL,
    order_discount FLOAT DEFAULT 0,
    note TEXT,
    order_total FLOAT DEFAULT 0,
    receive_total FLOAT DEFAULT 0,
    receive_status TEXT NOT NULL,
    supplierId INTEGER,
    userId INTEGER,
    branchId INTEGER,
    vat_percent FLOAT DEFAULT 7,
    FOREIGN KEY (supplierId) REFERENCES supplier(id),
    FOREIGN KEY (branchId) REFERENCES branch(id)
)"""
    },
    
    "purchase_order_item": {
        "description_en": "Line items in purchase orders detailing products, quantities, and prices ordered",
        "description_th": "รายการสินค้าในใบสั่งซื้อ ระบุสินค้า จำนวน และราคาที่สั่ง",
        "key_columns": ["poId", "productId", "order_quantity", "order_price", "total_price"],
        "searchable_columns": [],
        "schema": """
CREATE TABLE purchase_order_item (
    id INTEGER PRIMARY KEY,
    order_quantity NUMERIC NOT NULL,
    order_unit TEXT NOT NULL,
    order_price FLOAT NOT NULL,
    total_price FLOAT NOT NULL,
    receive_quantity NUMERIC DEFAULT 0,
    poId INTEGER,
    productId INTEGER,
    productUnitId INTEGER,
    FOREIGN KEY (poId) REFERENCES purchase_order(id),
    FOREIGN KEY (productId) REFERENCES product(id)
)"""
    },
    
    "supplier": {
        "description_en": "Supplier and distributor master data including contact information, tax ID, and payment terms",
        "description_th": "ข้อมูลหลักของซัพพลายเออร์และผู้จัดจำหน่าย รวมถึงข้อมูลติดต่อ เลขประจำตัวผู้เสียภาษี และเงื่อนไขการชำระเงิน",
        "key_columns": ["code", "name", "address", "phone", "tax_id", "contact_person"],
        "searchable_columns": ["name", "contact_person", "code"],
        "schema": """
CREATE TABLE supplier (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    tax_id TEXT,
    contact_person TEXT,
    contact_phone TEXT,
    email TEXT,
    isactive BOOLEAN DEFAULT 1,
    supplierTypeId INTEGER,
    credit_days INTEGER DEFAULT 30,
    FOREIGN KEY (supplierTypeId) REFERENCES supplier_type(id)
)"""
    },
    
    "branch": {
        "description_en": "Branch locations and warehouse information for inventory management",
        "description_th": "ข้อมูลสาขาและคลังสินค้าสำหรับการจัดการสินค้าคงคลัง",
        "key_columns": ["id", "name", "code"],
        "searchable_columns": ["name"],
        "schema": """
CREATE TABLE branch (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    code INTEGER NOT NULL,
    address TEXT
)"""
    },
    
    "product_group": {
        "description_en": "Product categorization and grouping for classification and reporting",
        "description_th": "การจัดหมวดหมู่และจัดกลุ่มสินค้าสำหรับการจำแนกและการรายงาน",
        "key_columns": ["id", "name", "code"],
        "searchable_columns": ["name"],
        "schema": """
CREATE TABLE product_group (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT NOT NULL,
    isactive BOOLEAN DEFAULT 1
)"""
    },
    
    "stock_transfer_slip": {
        "description_en": "Stock transfer documents between branches for inventory movement tracking",
        "description_th": "เอกสารโอนสต็อกระหว่างสาขาสำหรับติดตามการเคลื่อนย้ายสินค้าคงคลัง",
        "key_columns": ["code", "transfer_date", "status", "from_branchId", "to_branchId"],
        "searchable_columns": ["code"],
        "schema": """
CREATE TABLE stock_transfer_slip (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    transfer_date DATETIME NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    from_branchId INTEGER,
    to_branchId INTEGER,
    userId INTEGER,
    FOREIGN KEY (from_branchId) REFERENCES branch(id),
    FOREIGN KEY (to_branchId) REFERENCES branch(id)
)"""
    },
    
    "stock_transfer_slip_details": {
        "description_en": "Line items in stock transfer slips showing products and quantities transferred",
        "description_th": "รายการสินค้าในเอกสารโอนสต็อก แสดงสินค้าและจำนวนที่โอน",
        "key_columns": ["stsId", "productId", "quantity_ordered", "quantity_sent"],
        "searchable_columns": [],
        "schema": """
CREATE TABLE stock_transfer_slip_details (
    id INTEGER PRIMARY KEY,
    quantity_ordered NUMERIC NOT NULL,
    quantity_sent NUMERIC DEFAULT 0,
    status TEXT,
    stsId INTEGER,
    productId INTEGER,
    FOREIGN KEY (stsId) REFERENCES stock_transfer_slip(id),
    FOREIGN KEY (productId) REFERENCES product(id)
)"""
    },
    
    "user": {
        "description_en": "System users and employees with roles and authentication information",
        "description_th": "ผู้ใช้ระบบและพนักงาน พร้อมบทบาทและข้อมูลการยืนยันตัวตน",
        "key_columns": ["id", "username", "firstname", "lastname", "role"],
        "searchable_columns": ["username", "firstname", "lastname"],
        "schema": """
CREATE TABLE user (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    firstname TEXT,
    lastname TEXT,
    email TEXT,
    phone TEXT,
    role TEXT,
    isactive BOOLEAN DEFAULT 1
)"""
    },
    
    "payment_goods_receipt": {
        "description_en": "Payment records for goods receipts tracking supplier payments and due dates",
        "description_th": "บันทึกการชำระเงินสำหรับการรับสินค้า ติดตามการชำระเงินซัพพลายเออร์และวันครบกำหนด",
        "key_columns": ["payment_date", "payment_amount", "grId"],
        "searchable_columns": [],
        "schema": """
CREATE TABLE payment_goods_receipt (
    id INTEGER PRIMARY KEY,
    payment_date DATETIME NOT NULL,
    payment_amount FLOAT NOT NULL,
    payment_method TEXT,
    note TEXT,
    grId INTEGER,
    FOREIGN KEY (grId) REFERENCES goods_receipt(id)
)"""
    },
    
    "stock_history": {
        "description_en": "Historical stock movement records for audit trail and inventory analysis",
        "description_th": "บันทึกประวัติการเคลื่อนไหวสต็อกสำหรับการตรวจสอบและวิเคราะห์สินค้าคงคลัง",
        "key_columns": ["product_id", "branch_id", "remaining", "status", "timestamp"],
        "searchable_columns": ["lot_number"],
        "schema": """
CREATE TABLE stock_history (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    product_unit_id INTEGER,
    branch_id INTEGER NOT NULL,
    remaining DECIMAL(10,2) DEFAULT 0,
    status VARCHAR(50) NOT NULL,
    lot_number VARCHAR(100),
    timestamp TEXT NOT NULL,
    season VARCHAR(20),
    FOREIGN KEY (product_id) REFERENCES product(id),
    FOREIGN KEY (branch_id) REFERENCES branch(id)
)"""
    },
    
    "product_unit": {
        "description_en": "Product unit conversions and packaging information for different selling units",
        "description_th": "การแปลงหน่วยสินค้าและข้อมูลบรรจุภัณฑ์สำหรับหน่วยขายที่แตกต่างกัน",
        "key_columns": ["id", "unit_name", "conversion_rate", "productId"],
        "searchable_columns": ["unit_name"],
        "schema": """
CREATE TABLE product_unit (
    id INTEGER PRIMARY KEY,
    unit_name TEXT NOT NULL,
    conversion_rate FLOAT NOT NULL,
    is_base_unit BOOLEAN DEFAULT 0,
    productId INTEGER,
    FOREIGN KEY (productId) REFERENCES product(id)
)"""
    }
}

# ============================================================================
# GLOBAL VARIABLES
# ============================================================================

_embedding_model = None
_table_embeddings = None
_table_names = None

# Caching for dynamic database connections
_schema_cache = {}  # db_url -> schema_metadata
_vector_cache = {}  # db_url -> DynamicVectorSearch instance

# ============================================================================
# STAGE 0: INITIALIZATION & DATABASE CONNECTION
# ============================================================================

def get_db_connection():
    """
    Establish connection to SQLite database.
    
    Returns:
        sqlite3.Connection: Database connection object
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    except sqlite3.Error as e:
        raise Exception(f"Database connection failed: {e}")


def load_embedding_model():
    """
    Load the multilingual sentence transformer model.
    This model supports both Thai and English.
    
    Returns:
        SentenceTransformer: Loaded embedding model
    """
    global _embedding_model
    
    if _embedding_model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("✓ Embedding model loaded successfully")
    
    return _embedding_model


# ============================================================================
# DYNAMIC SCHEMA EXTRACTION
# ============================================================================

def extract_schema_from_db(db_url: str) -> Dict[str, Dict]:
    """
    Dynamically extract schema metadata from any SQLAlchemy-compatible database.
    
    This function connects to the database, inspects all tables, and generates
    metadata in the same format as the static TABLE_METADATA.
    
    Args:
        db_url: SQLAlchemy connection string (e.g., 'sqlite:///path/to/db.sqlite')
    
    Returns:
        Dictionary mapping table names to metadata dictionaries
    
    Example:
        >>> schema = extract_schema_from_db('sqlite:///database.db')
        >>> print(schema['users']['description_en'])
        'Table containing columns: id, username, email, created_at'
    """
    # Check cache first
    if db_url in _schema_cache:
        print(f"✓ Using cached schema for {db_url}")
        return _schema_cache[db_url]
    
    print(f"\n[Dynamic Schema Extraction]")
    print(f"Connecting to: {db_url}")
    
    try:
        # Create engine and inspector
        engine = create_engine(db_url)
        inspector = inspect(engine)
        
        # Get all table names
        table_names = inspector.get_table_names()
        print(f"Found {len(table_names)} tables")
        
        schema_metadata = {}
        
        for table_name in table_names:
            # Get column information
            columns = inspector.get_columns(table_name)
            column_names = [col['name'] for col in columns]
            column_types = {col['name']: str(col['type']) for col in columns}
            
            # Get primary keys
            pk_constraint = inspector.get_pk_constraint(table_name)
            primary_keys = pk_constraint.get('constrained_columns', [])
            
            # Get foreign keys
            foreign_keys = inspector.get_foreign_keys(table_name)
            
            # Auto-generate description from column names
            description_en = f"Table containing columns: {', '.join(column_names)}"
            description_th = f"ตารางที่มีคอลัมน์: {', '.join(column_names)}"
            
            # Generate DDL-like schema string
            schema_lines = [f"CREATE TABLE {table_name} ("]
            for col in columns:
                col_name = col['name']
                col_type = str(col['type'])
                nullable = "" if col['nullable'] else " NOT NULL"
                pk = " PRIMARY KEY" if col_name in primary_keys else ""
                default = f" DEFAULT {col['default']}" if col.get('default') else ""
                
                schema_lines.append(f"    {col_name} {col_type}{nullable}{pk}{default},")
            
            # Add foreign key constraints
            for fk in foreign_keys:
                fk_cols = ', '.join(fk['constrained_columns'])
                ref_table = fk['referred_table']
                ref_cols = ', '.join(fk['referred_columns'])
                schema_lines.append(f"    FOREIGN KEY ({fk_cols}) REFERENCES {ref_table}({ref_cols}),")
            
            # Remove trailing comma and close
            if schema_lines[-1].endswith(','):
                schema_lines[-1] = schema_lines[-1][:-1]
            schema_lines.append(")")
            
            schema_ddl = "\n".join(schema_lines)
            
            # Determine searchable columns (text/varchar columns)
            searchable_columns = [
                col['name'] for col in columns
                if 'CHAR' in str(col['type']).upper() or 'TEXT' in str(col['type']).upper()
            ]
            
            # Build metadata dictionary
            schema_metadata[table_name] = {
                "description_en": description_en,
                "description_th": description_th,
                "key_columns": column_names[:5],  # First 5 columns as key columns
                "searchable_columns": searchable_columns,
                "schema": schema_ddl,
                "column_types": column_types
            }
        
        # Cache the result
        _schema_cache[db_url] = schema_metadata
        
        print(f"✓ Extracted schema for {len(schema_metadata)} tables")
        engine.dispose()
        
        return schema_metadata
    
    except SQLAlchemyError as e:
        raise Exception(f"Failed to extract schema from {db_url}: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error during schema extraction: {e}")


# ============================================================================
# DYNAMIC VECTOR SEARCH CLASS
# ============================================================================

class DynamicVectorSearch:
    """
    Ephemeral vector search for dynamically extracted database schemas.
    
    This class creates embeddings on-the-fly for a given schema and stores
    them in memory. It's designed to be lightweight and disposable.
    """
    
    def __init__(self, schema_metadata: Dict[str, Dict], embedding_model: SentenceTransformer):
        """
        Initialize the vector search with schema metadata.
        
        Args:
            schema_metadata: Dictionary of table metadata (from extract_schema_from_db)
            embedding_model: Pre-loaded SentenceTransformer model
        """
        self.schema_metadata = schema_metadata
        self.embedding_model = embedding_model
        self.table_names = list(schema_metadata.keys())
        
        # Generate embeddings immediately
        print(f"Generating embeddings for {len(self.table_names)} tables...")
        self.embeddings = self._generate_embeddings()
        print("✓ Embeddings generated")
    
    def _generate_embeddings(self) -> np.ndarray:
        """
        Generate embeddings for all table descriptions.
        
        Returns:
            Numpy array of embeddings
        """
        descriptions = []
        for table_name in self.table_names:
            metadata = self.schema_metadata[table_name]
            # Combine English and Thai descriptions
            combined_desc = f"{metadata['description_en']} {metadata['description_th']}"
            descriptions.append(combined_desc)
        
        embeddings = self.embedding_model.encode(descriptions, convert_to_numpy=True)
        return embeddings
    
    def get_relevant_tables(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        Find top-k most relevant tables for the given query.
        
        Args:
            query: User's natural language question
            top_k: Number of tables to return
        
        Returns:
            List of dictionaries with table metadata and similarity scores
        """
        # Embed the query
        query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
        
        # Compute cosine similarity
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # Build results
        relevant_tables = []
        for idx in top_indices:
            table_name = self.table_names[idx]
            similarity_score = similarities[idx]
            
            relevant_tables.append({
                "table_name": table_name,
                "similarity_score": float(similarity_score),
                "metadata": self.schema_metadata[table_name]
            })
        
        return relevant_tables


def initialize_table_embeddings():
    """
    Pre-compute embeddings for all table descriptions.
    This is done once at startup for efficiency.
    
    Returns:
        Tuple[np.ndarray, List[str]]: (embeddings matrix, table names list)
    """
    global _table_embeddings, _table_names
    
    if _table_embeddings is not None and _table_names is not None:
        return _table_embeddings, _table_names
    
    model = load_embedding_model()
    
    # Combine Thai and English descriptions for better multilingual matching
    table_descriptions = []
    table_names = []
    
    for table_name, metadata in TABLE_METADATA.items():
        # Combine both language descriptions for richer semantic representation
        combined_desc = f"{metadata['description_en']} {metadata['description_th']}"
        table_descriptions.append(combined_desc)
        table_names.append(table_name)
    
    print(f"Computing embeddings for {len(table_names)} tables...")
    embeddings = model.encode(table_descriptions, convert_to_numpy=True)
    
    _table_embeddings = embeddings
    _table_names = table_names
    
    print("✓ Table embeddings initialized")
    return embeddings, table_names


# ============================================================================
# STAGE 1: SEMANTIC SCHEMA LINKING (Vector Search)
# ============================================================================

def get_relevant_tables(user_query: str, top_k: int = TOP_K_TABLES) -> List[Dict]:
    """
    Filter tables using semantic similarity between user query and table descriptions.
    
    This is the first stage of the RAG pipeline - reducing the search space
    from 15+ tables down to the most relevant top-k tables.
    
    Args:
        user_query: Natural language question in Thai or English
        top_k: Number of most relevant tables to return
    
    Returns:
        List of dictionaries containing table metadata for top-k tables
    """
    model = load_embedding_model()
    table_embeddings, table_names = initialize_table_embeddings()
    
    # Embed the user query
    query_embedding = model.encode([user_query], convert_to_numpy=True)
    
    # Compute cosine similarity between query and all table descriptions
    similarities = cosine_similarity(query_embedding, table_embeddings)[0]
    
    # Get indices of top-k most similar tables
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    # Prepare results with metadata
    relevant_tables = []
    for idx in top_indices:
        table_name = table_names[idx]
        similarity_score = similarities[idx]
        
        relevant_tables.append({
            "table_name": table_name,
            "similarity_score": float(similarity_score),
            "metadata": TABLE_METADATA[table_name]
        })
    
    print(f"\n[Stage 1: Schema Linking]")
    print(f"Query: {user_query}")
    print(f"Top {top_k} relevant tables:")
    for table in relevant_tables:
        print(f"  - {table['table_name']} (similarity: {table['similarity_score']:.3f})")
    
    return relevant_tables


# ============================================================================
# STAGE 2: DYNAMIC VALUE INJECTION (Hallucination Prevention)
# ============================================================================

def extract_keywords(user_query: str) -> List[str]:
    """
    Extract potential entity keywords from user query.
    
    This is a simple keyword extraction. For production, consider:
    - Named Entity Recognition (NER)
    - Thai word segmentation (pythainlp)
    - More sophisticated entity extraction
    
    Args:
        user_query: User's natural language question
    
    Returns:
        List of extracted keywords
    """
    # Remove common Thai/English stop words and extract meaningful tokens
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'should', 'could', 'may', 'might', 'must', 'can',
        'what', 'when', 'where', 'who', 'which', 'how', 'why',
        'ของ', 'ที่', 'และ', 'หรือ', 'แต่', 'ใน', 'บน', 'ที่', 'เพื่อ',
        'จาก', 'ด้วย', 'โดย', 'เป็น', 'คือ', 'มี', 'ได้', 'จะ', 'ควร',
        'อะไร', 'เมื่อไหร่', 'ที่ไหน', 'ใคร', 'อย่างไร', 'ทำไม',
        'แสดง', 'ให้', 'ดู', 'หา', 'ค้นหา', 'show', 'find', 'get', 'list'
    }
    
    # Split by whitespace and common punctuation
    tokens = re.findall(r'\b\w+\b', user_query.lower())
    
    # Filter out stop words and very short tokens
    keywords = [
        token for token in tokens 
        if token not in stop_words and len(token) > 2
    ]
    
    return keywords


def find_valid_values(user_query: str, relevant_tables: List[Dict], db_url: Optional[str] = None) -> Dict[str, List[Tuple[str, str]]]:
    """
    Search for exact or partial matches of query keywords in database.
    
    This is the second stage - preventing hallucination by finding actual
    values from the database that match entities in the user's question.
    
    Args:
        user_query: User's natural language question
        relevant_tables: List of relevant tables from Stage 1
        db_url: Optional SQLAlchemy connection string for dynamic databases
    
    Returns:
        Dictionary mapping table names to list of (column, value) matches
    """
    # Use dynamic connection if db_url provided, otherwise use default
    if db_url:
        try:
            engine = create_engine(db_url)
            conn = engine.connect()
            use_sqlalchemy = True
        except Exception as e:
            raise Exception(f"Failed to connect to database: {e}")
    else:
        conn = get_db_connection()
        use_sqlalchemy = False
    
    keywords = extract_keywords(user_query)
    found_values = {}
    
    print(f"\n[Stage 2: Value Injection]")
    print(f"Extracted keywords: {keywords}")
    
    for table_info in relevant_tables:
        table_name = table_info["table_name"]
        searchable_columns = table_info["metadata"]["searchable_columns"]
        
        if not searchable_columns:
            continue
        
        table_matches = []
        
        for column in searchable_columns:
            for keyword in keywords:
                try:
                    # Perform case-insensitive LIKE search
                    query_text = f"""
                        SELECT DISTINCT {column} 
                        FROM {table_name} 
                        WHERE LOWER({column}) LIKE LOWER(:keyword) 
                        LIMIT 5
                    """
                    
                    if use_sqlalchemy:
                        from sqlalchemy import text
                        result = conn.execute(text(query_text), {"keyword": f'%{keyword}%'})
                        results = result.fetchall()
                    else:
                        cursor = conn.cursor()
                        query_text = query_text.replace(":keyword", "?")
                        cursor.execute(query_text, (f'%{keyword}%',))
                        results = cursor.fetchall()
                    
                    for row in results:
                        value = row[0]
                        if value:  # Skip NULL values
                            table_matches.append((column, str(value)))
                            print(f"  ✓ Found in {table_name}.{column}: '{value}' (matched keyword: '{keyword}')")
                
                except Exception as e:
                    # Skip columns that cause errors (e.g., wrong type)
                    continue
        
        if table_matches:
            found_values[table_name] = table_matches
    
    if use_sqlalchemy:
        conn.close()
        engine.dispose()
    else:
        conn.close()
    
    if not found_values:
        print("  ℹ No exact matches found in database")
    
    return found_values


def format_verified_context(found_values: Dict[str, List[Tuple[str, str]]]) -> str:
    """
    Format found database values into a readable context string for the LLM.
    
    Args:
        found_values: Dictionary of table -> [(column, value)] matches
    
    Returns:
        Formatted string of verified values
    """
    if not found_values:
        return "No specific values found in database. Use general queries."
    
    context_parts = []
    for table_name, matches in found_values.items():
        context_parts.append(f"\nTable: {table_name}")
        for column, value in matches:
            context_parts.append(f"  - {column} = '{value}'")
    
    return "\n".join(context_parts)


# ============================================================================
# STAGE 3: LLM SQL GENERATION (Ollama)
# ============================================================================

def construct_prompt(user_query: str, relevant_tables: List[Dict], verified_context: str) -> str:
    """
    Construct the final prompt for the LLM with filtered schema and verified values.
    
    Args:
        user_query: User's natural language question
        relevant_tables: Relevant tables from Stage 1
        verified_context: Verified database values from Stage 2
    
    Returns:
        Complete prompt string for LLM
    """
    # Build schema section
    schema_section = "=== DATABASE SCHEMA ===\n\n"
    for table_info in relevant_tables:
        table_name = table_info["table_name"]
        metadata = table_info["metadata"]
        
        schema_section += f"Table: {table_name}\n"
        schema_section += f"Description: {metadata['description_en']}\n"
        schema_section += f"Schema:\n{metadata['schema']}\n\n"
    
    # Build verified context section
    context_section = "=== VERIFIED DATABASE VALUES ===\n"
    context_section += verified_context
    context_section += "\n\n"
    
    # Build instruction section
    instruction_section = """=== INSTRUCTIONS ===

Generate a valid SQLite query to answer the user's question.

CRITICAL RULES:
1. Use ONLY the tables and columns shown in the schema above
2. If specific values are listed in "VERIFIED DATABASE VALUES", use those EXACT values
3. Use proper JOIN syntax when combining tables
4. Return ONLY the SQL query, no explanations or markdown
5. Do not include any prefixes like "Here is" or "```sql"
6. The query must be executable SQLite syntax

"""
    
    # Build question section
    question_section = f"=== USER QUESTION ===\n{user_query}\n\n"
    
    # Combine all sections
    full_prompt = (
        schema_section +
        context_section +
        instruction_section +
        question_section +
        "SQL Query:"
    )
    
    return full_prompt


def call_ollama(prompt: str) -> str:
    """
    Send prompt to Ollama API and get SQL query response.
    
    Args:
        prompt: Complete prompt for LLM
    
    Returns:
        Generated SQL query
    """
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for more deterministic output
                "top_p": 0.9,
                "top_k": 40
            }
        }
        
        print(f"\n[Stage 3: LLM Generation]")
        print(f"Calling Ollama API with model: {OLLAMA_MODEL}")
        
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        generated_text = result.get("response", "")
        
        # Clean up the response
        sql_query = clean_sql_output(generated_text)
        
        print(f"✓ SQL Generated:\n{sql_query}")
        
        return sql_query
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"Ollama API error: {e}")


def clean_sql_output(sql_text: str) -> str:
    """
    Clean up LLM output to extract pure SQL query.
    
    Args:
        sql_text: Raw output from LLM
    
    Returns:
        Cleaned SQL query
    """
    # Remove markdown code blocks
    sql_text = re.sub(r'```sql\s*', '', sql_text)
    sql_text = re.sub(r'```\s*', '', sql_text)
    
    # Remove common prefixes
    prefixes = [
        'here is the sql query:',
        'here is the query:',
        'sql query:',
        'query:',
        'here you go:',
        'here is:',
    ]
    
    for prefix in prefixes:
        if sql_text.lower().startswith(prefix):
            sql_text = sql_text[len(prefix):].strip()
    
    # Remove special tokens like <s>, </s>
    sql_text = re.sub(r'</?s>', '', sql_text)
    
    # Remove leading/trailing whitespace
    sql_text = sql_text.strip()
    
    # Remove any trailing explanations (text after semicolon)
    if ';' in sql_text:
        sql_text = sql_text.split(';')[0] + ';'
    
    return sql_text


# ============================================================================
# MAIN ORCHESTRATION FUNCTION
# ============================================================================

def generate_sql(user_query: str, db_url: Optional[str] = None, top_k: int = TOP_K_TABLES, verbose: bool = True) -> str:
    """
    Main function: Convert natural language query to SQL using 3-stage RAG pipeline.
    
    Supports both static metadata (default) and dynamic database connections.
    
    Pipeline:
    1. Semantic Schema Linking: Find top-k relevant tables
    2. Dynamic Value Injection: Extract and verify entity values
    3. LLM SQL Generation: Generate SQL with Ollama
    
    Args:
        user_query: Natural language question in Thai or English
        db_url: Optional SQLAlchemy connection string for dynamic databases
                (e.g., 'sqlite:///path/to/db.sqlite', 'postgresql://user:pass@host/db')
                If None, uses static TABLE_METADATA
        top_k: Number of tables to consider (default: 3)
        verbose: Print detailed logs (default: True)
    
    Returns:
        Generated SQL query string
    
    Examples:
        # Static mode (using hardcoded metadata)
        >>> sql = generate_sql("แสดงสินค้าทั้งหมดที่มี Paracetamol")
        
        # Dynamic mode (runtime database connection)
        >>> sql = generate_sql("Show all users", db_url="sqlite:///users.db")
        >>> sql = generate_sql("List products", db_url="postgresql://user:pass@localhost/shop")
    """
    print("=" * 80)
    print("RAG-BASED TEXT-TO-SQL PIPELINE")
    if db_url:
        print(f"Mode: DYNAMIC (db_url: {db_url})")
    else:
        print("Mode: STATIC (using hardcoded metadata)")
    print("=" * 80)
    
    # Stage 1: Semantic Schema Linking
    if db_url:
        # Dynamic mode: Extract schema and use DynamicVectorSearch
        global _vector_cache
        
        # Check if we have a cached vector search for this db_url
        if db_url in _vector_cache:
            print(f"\n✓ Using cached vector search for {db_url}")
            vector_search = _vector_cache[db_url]
        else:
            # Extract schema and create new vector search
            schema_metadata = extract_schema_from_db(db_url)
            embedding_model = load_embedding_model()
            vector_search = DynamicVectorSearch(schema_metadata, embedding_model)
            
            # Cache it
            _vector_cache[db_url] = vector_search
        
        # Get relevant tables using dynamic vector search
        print(f"\n[Stage 1: Schema Linking - Dynamic Mode]")
        print(f"Query: {user_query}")
        relevant_tables = vector_search.get_relevant_tables(user_query, top_k=top_k)
        print(f"Top {top_k} relevant tables:")
        for table in relevant_tables:
            print(f"  - {table['table_name']} (similarity: {table['similarity_score']:.3f})")
    else:
        # Static mode: Use pre-defined metadata
        relevant_tables = get_relevant_tables(user_query, top_k=top_k)
    
    # Stage 2: Dynamic Value Injection
    found_values = find_valid_values(user_query, relevant_tables, db_url=db_url)
    verified_context = format_verified_context(found_values)
    
    # Stage 3: LLM SQL Generation
    prompt = construct_prompt(user_query, relevant_tables, verified_context)
    
    if verbose:
        print("\n" + "=" * 80)
        print("FINAL PROMPT TO LLM")
        print("=" * 80)
        print(prompt)
        print("=" * 80)
    
    sql_query = call_ollama(prompt)
    
    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    
    return sql_query




# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def clear_cache(db_url: Optional[str] = None):
    """
    Clear cached schemas and vector searches.
    
    Args:
        db_url: If provided, clear cache only for this database.
                If None, clear all caches.
    """
    global _schema_cache, _vector_cache
    
    if db_url:
        if db_url in _schema_cache:
            del _schema_cache[db_url]
            print(f"✓ Cleared schema cache for {db_url}")
        if db_url in _vector_cache:
            del _vector_cache[db_url]
            print(f"✓ Cleared vector cache for {db_url}")
    else:
        _schema_cache.clear()
        _vector_cache.clear()
        print("✓ Cleared all caches")


def get_cache_info() -> Dict:
    """
    Get information about current cache state.
    
    Returns:
        Dictionary with cache statistics
    """
    return {
        "schema_cache_size": len(_schema_cache),
        "vector_cache_size": len(_vector_cache),
        "cached_databases": list(_schema_cache.keys())
    }


def validate_sql(sql_query: str, db_url: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate SQL query by attempting to execute it (with EXPLAIN).
    
    Args:
        sql_query: SQL query to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Use EXPLAIN to validate without executing
        cursor.execute(f"EXPLAIN {sql_query}")
        conn.close()
        
        return True, None
    
    except sqlite3.Error as e:
        return False, str(e)


def execute_sql(sql_query: str, limit: int = 10) -> List[Dict]:
    """
    Execute SQL query and return results.
    
    Args:
        sql_query: SQL query to execute
        limit: Maximum number of rows to return
    
    Returns:
        List of result rows as dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Add LIMIT if not present
        if 'LIMIT' not in sql_query.upper():
            sql_query = sql_query.rstrip(';') + f' LIMIT {limit};'
        
        cursor.execute(sql_query)
        columns = [description[0] for description in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results
    
    except sqlite3.Error as e:
        conn.close()
        raise Exception(f"SQL execution error: {e}")


# ============================================================================
# DEMO / TESTING
# ============================================================================

def main():
    """
    Demo function showing example usage of the RAG Text-to-SQL system.
    """
    print("\n" + "=" * 80)
    print("RAG-BASED TEXT-TO-SQL SYSTEM - DEMO")
    print("=" * 80)
    
    # Initialize models
    initialize_table_embeddings()
    
    # Example queries (Thai and English)
    example_queries = [
        "แสดงสินค้าทั้งหมดที่มีชื่อว่า Paracetamol",
        "What is the total stock of Amoxicillin?",
        "ยอดรับสินค้าทั้งหมดในเดือนนี้",
        "Show all suppliers from Bangkok",
        "สินค้าที่กำลังจะหมดอายุในเดือนหน้า"
    ]
    
    for i, query in enumerate(example_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"EXAMPLE {i}/{len(example_queries)}")
        print(f"{'=' * 80}")
        
        try:
            sql = generate_sql(query, verbose=False)
            
            # Validate the generated SQL
            is_valid, error = validate_sql(sql)
            if is_valid:
                print(f"\n✓ SQL is valid and executable")
            else:
                print(f"\n✗ SQL validation failed: {error}")
        
        except Exception as e:
            print(f"\n✗ Error: {e}")
        
        print("\n" + "=" * 80)
        input("Press Enter to continue to next example...")


if __name__ == "__main__":
    main()
