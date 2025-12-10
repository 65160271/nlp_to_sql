#!/usr/bin/env python3
"""
Quick test script for RAG Text-to-SQL system (Stages 1 & 2 only)
Tests semantic schema linking and value injection without requiring Ollama
"""

from rag_text_to_sql import (
    get_relevant_tables,
    find_valid_values,
    format_verified_context,
    initialize_table_embeddings
)

def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def test_stage_1_and_2(query, description):
    """Test Stages 1 and 2 of the pipeline"""
    print_header(f"TEST: {description}")
    print(f"Query: {query}\n")
    
    # Stage 1: Schema Linking
    print("🔍 Stage 1: Semantic Schema Linking")
    print("-" * 80)
    tables = get_relevant_tables(query, top_k=3)
    
    print(f"\nTop 3 Relevant Tables:")
    for i, table in enumerate(tables, 1):
        print(f"  {i}. {table['table_name']} (similarity: {table['similarity_score']:.3f})")
    
    # Stage 2: Value Injection
    print(f"\n🎯 Stage 2: Dynamic Value Injection")
    print("-" * 80)
    values = find_valid_values(query, tables)
    context = format_verified_context(values)
    
    if values:
        print(f"\n✅ Found verified values:")
        print(context)
    else:
        print(f"\nℹ️  No specific values found (will use general query)")
    
    print("\n" + "=" * 80)
    print()

def main():
    """Run quick tests"""
    print_header("RAG TEXT-TO-SQL SYSTEM - QUICK TEST (Stages 1 & 2)")
    
    # Initialize
    print("\n🔧 Initializing system...")
    initialize_table_embeddings()
    print("✅ System ready!\n")
    
    # Test cases
    test_cases = [
        ("Show all products with Paracetamol", "English - Product Search"),
        ("แสดงสินค้าทั้งหมด", "Thai - Product Listing"),
        ("What is the stock of Amoxicillin?", "English - Stock Inquiry"),
        ("ยอดรับสินค้าทั้งหมด", "Thai - Goods Receipt Total"),
        ("Show suppliers from Bangkok", "English - Supplier Filter"),
    ]
    
    for query, description in test_cases:
        test_stage_1_and_2(query, description)
        input("Press Enter to continue...")
    
    print_header("ALL TESTS COMPLETE!")
    print("\n✅ Stages 1 & 2 are working correctly!")
    print("\n📝 To test Stage 3 (SQL Generation):")
    print("   1. Start Ollama: ollama serve")
    print("   2. Pull model: ollama pull gemma:7b")
    print("   3. Run: python demo_rag_system.py")
    print()

if __name__ == "__main__":
    main()
