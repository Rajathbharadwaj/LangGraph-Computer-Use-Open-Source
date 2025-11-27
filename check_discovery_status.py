#!/usr/bin/env python3
"""Check discovery status and results"""
import psycopg2
import json

conn = psycopg2.connect('postgresql://postgres:password@localhost:5433/xgrowth')
cur = conn.cursor()

# Check store schema
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'store'
    ORDER BY ordinal_position
""")
print("Store columns:")
for col in cur.fetchall():
    print(f"  {col[0]}: {col[1]}")

print("\n" + "="*80)

# Try to find any social_graph related data
cur.execute("""
    SELECT prefix, key, value
    FROM store
    WHERE prefix LIKE '%social_graph%'
    ORDER BY updated_at DESC
    LIMIT 5
""")

rows = cur.fetchall()
print(f"\nFound {len(rows)} social_graph entries\n")

for prefix, key, value in rows:
    print(f"Prefix: {prefix}")
    print(f"Key: {key}")
    if isinstance(value, dict):
        print(f"Created: {value.get('created_at', 'unknown')}")
        print(f"Total candidates: {len(value.get('all_competitors_raw', []))}")
        print(f"High quality: {value.get('high_quality_competitors', 0)}")

        # Show top matches
        comps = value.get('all_competitors_raw', [])
        if comps:
            sorted_comps = sorted(comps, key=lambda x: x.get('overlap_percentage', 0), reverse=True)
            print(f"\nTop 10 by overlap:")
            for i, c in enumerate(sorted_comps[:10], 1):
                print(f"  {i}. @{c.get('username')}: {c.get('overlap_percentage')}% ({c.get('follower_overlap', 0)} shared)")
    print("\n" + "-"*80 + "\n")

conn.close()
