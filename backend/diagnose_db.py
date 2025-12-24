#!/usr/bin/env python3
"""
Diagnostic: Check what's in the database and what values are being sampled
"""

from sqlalchemy import create_engine, inspect, text

db_url = "sqlite:////Users/kittawan/nlp_to_sql/database2-2.sqlite"

print("\n" + "="*70)
print("  Database Diagnostic")
print("="*70)

engine = create_engine(db_url)
inspector = inspect(engine)

# Find tables with 'lot' in the name or columns
print("\n📊 Tables with 'lot' or 'batch' references:")
print("="*70)

for table_name in inspector.get_table_names():
    columns = inspector.get_columns(table_name)
    
    # Check if table name contains lot/batch
    if 'lot' in table_name.lower() or 'batch' in table_name.lower():
        print(f"\n✅ Table: {table_name}")
        for col in columns:
            print(f"   - {col['name']} ({col['type']})")
    
    # Check if any column contains lot/batch
    lot_columns = [col for col in columns if 'lot' in col['name'].lower() or 'batch' in col['name'].lower()]
    if lot_columns:
        print(f"\n✅ Table: {table_name} (has lot/batch columns)")
        for col in lot_columns:
            print(f"   - {col['name']} ({col['type']})")
            
            # Sample some values
            try:
                query = text(f'SELECT DISTINCT "{col["name"]}" FROM "{table_name}" WHERE "{col["name"]}" IS NOT NULL LIMIT 5')
                with engine.connect() as conn:
                    result = conn.execute(query)
                    values = [str(row[0]) for row in result]
                    if values:
                        print(f"     Sample values: {', '.join(values[:3])}")
            except Exception as e:
                print(f"     Error sampling: {e}")

# Check stock_transfer_slip_details specifically
print("\n" + "="*70)
print("📦 Checking stock_transfer_slip_details:")
print("="*70)

try:
    columns = inspector.get_columns('stock_transfer_slip_details')
    print("\nColumns:")
    for col in columns:
        print(f"  - {col['name']} ({col['type']})")
    
    # Sample lot_number values
    query = text('SELECT DISTINCT lot_number FROM stock_transfer_slip_details WHERE lot_number IS NOT NULL LIMIT 10')
    with engine.connect() as conn:
        result = conn.execute(query)
        lot_numbers = [str(row[0]) for row in result]
        print(f"\n✅ Actual lot_number values in database:")
        for lot in lot_numbers:
            print(f"   • {lot}")
except Exception as e:
    print(f"❌ Error: {e}")

engine.dispose()

print("\n" + "="*70)
print("  Diagnostic Complete")
print("="*70 + "\n")
