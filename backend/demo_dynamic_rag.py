#!/usr/bin/env python3
"""
Demo script for Dynamic RAG Text-to-SQL system
Demonstrates runtime database connection with automatic schema extraction
"""

from rag_text_to_sql import (
    generate_sql,
    extract_schema_from_db,
    clear_cache,
    get_cache_info,
    load_embedding_model
)
import time

def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def test_dynamic_query(query, db_url, description):
    """Test a query against a dynamic database"""
    print_header(f"TEST: {description}")
    print(f"Database: {db_url}")
    print(f"Query: {query}\n")
    
    try:
        start_time = time.time()
        sql = generate_sql(query, db_url=db_url, verbose=False)
        elapsed = time.time() - start_time
        
        print(f"\n\u2705 Generated SQL:")
        print(f"   {sql}")
        print(f"\n\u23f1\ufe0f  Time: {elapsed:.2f}s")
        
    except Exception as e:
        print(f"\n\u274c Error: {e}")
    
    print("\n" + "=" * 80)

def main():
    """Run dynamic database demo"""
    print_header("DYNAMIC RAG TEXT-TO-SQL SYSTEM - DEMO")
    
    # Initialize embedding model once
    print("\n\ud83d\udd27 Initializing system...")
    load_embedding_model()
    print("\u2705 System ready!\n")
    
    # Database path
    db_url = "sqlite:////Users/kittawan/nlp_to_sql/database2-2.sqlite"
    
    print_header("SCENARIO 1: First Query (Cold Start)")
    print("This will extract schema and create embeddings")
    input("Press Enter to continue...")
    
    test_dynamic_query(
        "Show all products with Paracetamol",
        db_url,
        "English - Product Search (Cold Start)"
    )
    
    # Show cache info
    cache_info = get_cache_info()
    print(f"\n\ud83d\udcca Cache Info:")
    print(f"   Cached databases: {cache_info['cached_databases']}")
    print(f"   Schema cache size: {cache_info['schema_cache_size']}")
    print(f"   Vector cache size: {cache_info['vector_cache_size']}")
    
    input("\nPress Enter to continue...")
    
    print_header("SCENARIO 2: Second Query (Cached)")
    print("This will use cached schema and embeddings - should be faster!")
    input("Press Enter to continue...")
    
    test_dynamic_query(
        "\u0e41\u0e2a\u0e14\u0e07\u0e2a\u0e34\u0e19\u0e04\u0e49\u0e32\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14",
        db_url,
        "Thai - Product Listing (Cached)"
    )
    
    input("\nPress Enter to continue...")
    
    print_header("SCENARIO 3: Different Query Types")
    
    test_cases = [
        ("What is the current stock of Amoxicillin?", "Stock Inquiry"),
        ("\u0e22\u0e2d\u0e14\u0e23\u0e31\u0e1a\u0e2a\u0e34\u0e19\u0e04\u0e49\u0e32\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14", "Goods Receipt Total"),
        ("Show all suppliers", "Supplier Listing"),
        ("List all branches", "Branch Listing"),
    ]
    
    for query, desc in test_cases:
        input(f"\nPress Enter for next test: {desc}...")
        test_dynamic_query(query, db_url, desc)
    
    print_header("SCENARIO 4: Cache Management")
    
    print("\n\ud83d\udcca Current cache state:")
    cache_info = get_cache_info()
    print(f"   Cached databases: {len(cache_info['cached_databases'])}")
    for db in cache_info['cached_databases']:
        print(f"     - {db}")
    
    input("\nPress Enter to clear cache...")
    clear_cache()
    
    print("\n\ud83d\udcca Cache after clearing:")
    cache_info = get_cache_info()
    print(f"   Cached databases: {len(cache_info['cached_databases'])}")
    
    input("\nPress Enter to test after cache clear...")
    
    test_dynamic_query(
        "Show products",
        db_url,
        "After Cache Clear (Will re-extract schema)"
    )
    
    print_header("DEMO COMPLETE!")
    
    print("\n\u2728 Key Features Demonstrated:")
    print("   \u2705 Dynamic schema extraction from any database")
    print("   \u2705 Automatic embedding generation")
    print("   \u2705 Intelligent caching for performance")
    print("   \u2705 Multi-language support (Thai/English)")
    print("   \u2705 No manual metadata configuration needed")
    
    print("\n\ud83d\udca1 Usage:")
    print("   # Connect to any database dynamically")
    print("   sql = generate_sql('your question', db_url='sqlite:///path/to/db.sqlite')")
    print("   sql = generate_sql('your question', db_url='postgresql://user:pass@host/db')")
    print()

if __name__ == "__main__":
    main()
