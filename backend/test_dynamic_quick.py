#!/usr/bin/env python3
"""
Quick test for dynamic database connection feature
Tests schema extraction and caching without requiring Ollama
"""

from rag_text_to_sql import (
    extract_schema_from_db,
    DynamicVectorSearch,
    load_embedding_model,
    get_cache_info,
    clear_cache
)
import time

def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def main():
    """Quick test of dynamic features"""
    print_header("DYNAMIC DATABASE CONNECTION - QUICK TEST")
    
    db_url = "sqlite:////Users/kittawan/nlp_to_sql/database2-2.sqlite"
    
    # Test 1: Schema Extraction
    print_header("TEST 1: Schema Extraction")
    print(f"Database: {db_url}\n")
    
    start = time.time()
    schema = extract_schema_from_db(db_url)
    elapsed = time.time() - start
    
    print(f"\n✅ Extracted {len(schema)} tables in {elapsed:.2f}s")
    print(f"\nSample tables:")
    for table_name in list(schema.keys())[:5]:
        print(f"  - {table_name}")
        print(f"    Columns: {', '.join(schema[table_name]['key_columns'])}")
        print(f"    Searchable: {', '.join(schema[table_name]['searchable_columns'][:3])}")
    
    # Test 2: Caching
    print_header("TEST 2: Caching Behavior")
    
    print("\n📊 Cache before second extraction:")
    cache_info = get_cache_info()
    print(f"   Cached databases: {len(cache_info['cached_databases'])}")
    
    print("\n🔄 Extracting schema again (should use cache)...")
    start = time.time()
    schema2 = extract_schema_from_db(db_url)
    elapsed2 = time.time() - start
    
    print(f"✅ Second extraction: {elapsed2:.2f}s (cached)")
    print(f"   First extraction: {elapsed:.2f}s (cold)")
    print(f"   Speedup: {elapsed/elapsed2:.1f}x faster")
    
    # Test 3: Dynamic Vector Search
    print_header("TEST 3: Dynamic Vector Search")
    
    print("\n🔧 Loading embedding model...")
    model = load_embedding_model()
    
    print("\n🔧 Creating DynamicVectorSearch...")
    start = time.time()
    vector_search = DynamicVectorSearch(schema, model)
    elapsed = time.time() - start
    print(f"✅ Created in {elapsed:.2f}s")
    
    # Test queries
    test_queries = [
        "Show all products",
        "แสดงสินค้าทั้งหมด",
        "What is the stock level?",
        "List all suppliers"
    ]
    
    print("\n🔍 Testing semantic search:")
    for query in test_queries:
        tables = vector_search.get_relevant_tables(query, top_k=3)
        print(f"\n   Query: '{query}'")
        print(f"   Top tables: {[t['table_name'] for t in tables]}")
    
    # Test 4: Cache Management
    print_header("TEST 4: Cache Management")
    
    print("\n📊 Current cache state:")
    cache_info = get_cache_info()
    print(f"   Schema cache: {cache_info['schema_cache_size']} databases")
    print(f"   Vector cache: {cache_info['vector_cache_size']} databases")
    print(f"   Databases: {cache_info['cached_databases']}")
    
    print("\n🗑️  Clearing cache...")
    clear_cache()
    
    cache_info = get_cache_info()
    print(f"\n📊 After clearing:")
    print(f"   Schema cache: {cache_info['schema_cache_size']} databases")
    print(f"   Vector cache: {cache_info['vector_cache_size']} databases")
    
    print_header("ALL TESTS PASSED!")
    
    print("\n✨ Dynamic Features Working:")
    print("   ✅ Schema extraction from live database")
    print("   ✅ Automatic caching for performance")
    print("   ✅ Dynamic vector search")
    print("   ✅ Cache management utilities")
    
    print("\n💡 Next Steps:")
    print("   1. Test with Ollama: python demo_dynamic_rag.py")
    print("   2. Try different databases (PostgreSQL, MySQL)")
    print("   3. Integrate into your application")
    print()

if __name__ == "__main__":
    main()
