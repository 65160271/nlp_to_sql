#!/usr/bin/env python3
"""
Demo script for RAG-based Text-to-SQL system
Tests the complete 3-stage pipeline with example queries
"""

from rag_text_to_sql import (
    generate_sql,
    validate_sql,
    execute_sql,
    initialize_table_embeddings
)

def print_separator():
    print("\n" + "=" * 80 + "\n")

def test_query(query: str, description: str):
    """Test a single query through the pipeline"""
    print_separator()
    print(f"TEST: {description}")
    print(f"Query: {query}")
    print_separator()
    
    try:
        # Generate SQL
        sql = generate_sql(query, verbose=False)
        
        print(f"\n📝 Generated SQL:")
        print(f"   {sql}")
        
        # Validate SQL
        is_valid, error = validate_sql(sql)
        if is_valid:
            print(f"\n✅ SQL is valid and executable")
            
            # Try to execute
            try:
                results = execute_sql(sql, limit=5)
                print(f"\n📊 Sample Results ({len(results)} rows):")
                for i, row in enumerate(results[:3], 1):
                    print(f"   Row {i}: {row}")
            except Exception as e:
                print(f"\n⚠️  Execution note: {e}")
        else:
            print(f"\n❌ SQL validation failed: {error}")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print_separator()
    input("Press Enter to continue...")

def main():
    """Run demo tests"""
    print("\n" + "=" * 80)
    print("RAG-BASED TEXT-TO-SQL SYSTEM - DEMO")
    print("=" * 80)
    
    # Initialize system
    print("\n🔧 Initializing system...")
    initialize_table_embeddings()
    print("✅ System ready!\n")
    
    # Test cases
    test_cases = [
        {
            "query": "Show all products with Paracetamol",
            "description": "English query - Product search"
        },
        {
            "query": "แสดงสินค้าทั้งหมดที่มีชื่อว่า Paracetamol",
            "description": "Thai query - Product search with exact name"
        },
        {
            "query": "What is the current stock level of Amoxicillin?",
            "description": "English query - Stock inquiry"
        },
        {
            "query": "รายการสินค้าที่จะหมดอายุในเดือนหน้า",
            "description": "Thai query - Expiring products"
        },
        {
            "query": "Show all suppliers from Bangkok",
            "description": "English query - Supplier location filter"
        },
        {
            "query": "ยอดรับสินค้าทั้งหมดในปีนี้",
            "description": "Thai query - Goods receipt totals"
        },
        {
            "query": "List all branches",
            "description": "English query - Simple branch listing"
        },
        {
            "query": "สินค้าที่มีสต็อกต่ำกว่าระดับขั้นต่ำ",
            "description": "Thai query - Low stock alert"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n\n{'#' * 80}")
        print(f"# TEST CASE {i}/{len(test_cases)}")
        print(f"{'#' * 80}")
        test_query(test_case["query"], test_case["description"])
    
    print("\n" + "=" * 80)
    print("DEMO COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    main()
