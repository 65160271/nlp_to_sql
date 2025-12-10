#!/usr/bin/env python3
"""
Dynamic Value Injection Demonstration Script
=============================================
This script demonstrates how the Dynamic Value Injection system prevents
LLM hallucinations by searching the database for actual values and injecting
them into the prompt.

Author: Senior Python AI Engineer
Date: 2025-12-09
"""

import os
import sys
from typing import Dict, List, Tuple

# Add parent directory to path to import from main.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    extract_keywords,
    find_relevant_values,
    search_column_values,
    build_sqlcoder_prompt
)

# ANSI color codes for pretty output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'



def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_subsection(title: str):
    """Print a formatted subsection header."""
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}{title}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}{'-'*len(title)}{Colors.ENDC}")


def demo_keyword_extraction():
    """Demonstrate keyword extraction from user queries."""
    print_section("STEP 1: Keyword Extraction")
    
    test_queries = [
        "Show me sales for Mr. Somchai",
        "Find employees in the Engineering department",
        "What is the salary of John Smith?",
        "List all products in the Electronics category"
    ]
    
    for query in test_queries:
        keywords = extract_keywords(query)
        print(f"{Colors.OKCYAN}Query:{Colors.ENDC} {query}")
        print(f"{Colors.OKGREEN}Keywords:{Colors.ENDC} {keywords}\n")


def demo_value_search():
    """Demonstrate searching for values in the database."""
    print_section("STEP 2: Database Value Search")
    
    # Use the existing employee database (one level up from backend/)
    connection_string = "sqlite:///../cdg_employee.db"
    
    print(f"{Colors.OKCYAN}Database:{Colors.ENDC} {connection_string}\n")
    
    # Test searching for employee names
    print_subsection("Searching employees.first_name for 'somchai'")
    
    results = search_column_values(
        connection_string=connection_string,
        table_name="employees",
        column_name="first_name",
        keywords=["somchai"],
        similarity_threshold=70,
        max_results=5
    )
    
    if results:
        print(f"{Colors.OKGREEN}Found {len(results)} matches:{Colors.ENDC}")
        for value, confidence in results:
            print(f"  • {value} (confidence: {confidence}%)")
    else:
        print(f"{Colors.WARNING}No matches found{Colors.ENDC}")
    
    # Test searching for department names
    print_subsection("Searching departments.name for 'engineering'")
    
    results = search_column_values(
        connection_string=connection_string,
        table_name="departments",
        column_name="name",
        keywords=["engineering", "eng"],
        similarity_threshold=60,
        max_results=5
    )
    
    if results:
        print(f"{Colors.OKGREEN}Found {len(results)} matches:{Colors.ENDC}")
        for value, confidence in results:
            print(f"  • {value} (confidence: {confidence}%)")
    else:
        print(f"{Colors.WARNING}No matches found{Colors.ENDC}")


def demo_full_value_injection():
    """Demonstrate the complete value injection process."""
    print_section("STEP 3: Complete Value Injection")
    
    connection_string = "sqlite:///../cdg_employee.db"
    
    test_cases = [
        {
            "query": "Show me employees named Somchai",
            "searchable_columns": ["employees.first_name", "employees.last_name"]
        },
        {
            "query": "Find all people in the Engineering department",
            "searchable_columns": ["departments.name", "employees.first_name"]
        },
        {
            "query": "List managers and senior positions",
            "searchable_columns": ["positions.title", "positions.grade"]
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print_subsection(f"Test Case {i}: {test_case['query']}")
        
        matched_values = find_relevant_values(
            user_query=test_case["query"],
            connection_string=connection_string,
            searchable_columns=test_case["searchable_columns"],
            similarity_threshold=70
        )
        
        if matched_values:
            print(f"{Colors.OKGREEN}Matched values found in {len(matched_values)} columns:{Colors.ENDC}\n")
            for column, values in matched_values.items():
                print(f"{Colors.BOLD}{column}:{Colors.ENDC}")
                for value, confidence in values[:3]:  # Show top 3
                    print(f"  • '{value}' (confidence: {confidence}%)")
                print()
        else:
            print(f"{Colors.WARNING}No matched values found{Colors.ENDC}\n")


def demo_prompt_enhancement():
    """Demonstrate how matched values enhance the prompt."""
    print_section("STEP 4: Prompt Enhancement")
    
    connection_string = "sqlite:///../cdg_employee.db"
    user_query = "Show me employees named Somchai"
    
    # Get schema (simplified for demo)
    schema = """CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    department_id INTEGER,
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);"""
    
    print_subsection("WITHOUT Value Injection")
    prompt_without = build_sqlcoder_prompt(
        schema_text=schema,
        question=user_query,
        dialect="SQLite"
    )
    print(f"{Colors.OKCYAN}{prompt_without[:500]}...{Colors.ENDC}\n")
    
    print_subsection("WITH Value Injection")
    
    # Find matched values
    matched_values = find_relevant_values(
        user_query=user_query,
        connection_string=connection_string,
        searchable_columns=["employees.first_name", "employees.last_name"],
        similarity_threshold=70
    )
    
    prompt_with = build_sqlcoder_prompt(
        schema_text=schema,
        question=user_query,
        dialect="SQLite",
        matched_values=matched_values
    )
    
    print(f"{Colors.OKGREEN}{prompt_with[:800]}...{Colors.ENDC}\n")
    
    if matched_values:
        print(f"{Colors.BOLD}Notice:{Colors.ENDC} The enhanced prompt includes actual database values!")
        print(f"This prevents the LLM from hallucinating names like 'Somchai ABC'")


def demo_comparison():
    """Show before/after comparison."""
    print_section("STEP 5: Before/After Comparison")
    
    print(f"{Colors.FAIL}{Colors.BOLD}❌ WITHOUT Value Injection:{Colors.ENDC}")
    print("User asks: 'Show employees named Somchai'")
    print("LLM might generate: SELECT * FROM employees WHERE first_name = 'Somchai ABC'")
    print(f"{Colors.FAIL}Result: No rows found (hallucinated name){Colors.ENDC}\n")
    
    print(f"{Colors.OKGREEN}{Colors.BOLD}✅ WITH Value Injection:{Colors.ENDC}")
    print("User asks: 'Show employees named Somchai'")
    print("System finds: 'Somchai Khemglad', 'Somchai Prasert' in database")
    print("LLM generates: SELECT * FROM employees WHERE first_name LIKE '%Somchai%'")
    print(f"{Colors.OKGREEN}Result: Returns actual employees named Somchai{Colors.ENDC}\n")


def main():
    """Run all demonstrations."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║     Dynamic Value Injection - Demonstration Script               ║")
    print("║     Preventing LLM Hallucinations in Text-to-SQL                 ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")
    
    try:
        demo_keyword_extraction()
        demo_value_search()
        demo_full_value_injection()
        demo_prompt_enhancement()
        demo_comparison()
        
        print_section("✅ DEMONSTRATION COMPLETE")
        print(f"{Colors.OKGREEN}All demonstrations completed successfully!{Colors.ENDC}")
        print(f"\n{Colors.BOLD}Key Takeaways:{Colors.ENDC}")
        print("1. Keywords are extracted from user queries")
        print("2. Database is searched for matching values using fuzzy matching")
        print("3. Matched values are injected into the LLM prompt")
        print("4. LLM uses actual values instead of hallucinating")
        print("5. This significantly improves SQL generation accuracy\n")
        
    except Exception as e:
        print(f"\n{Colors.FAIL}{Colors.BOLD}Error during demonstration:{Colors.ENDC}")
        print(f"{Colors.FAIL}{str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
