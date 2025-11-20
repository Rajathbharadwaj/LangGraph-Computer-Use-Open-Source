#!/usr/bin/env python3
"""Patch X Native discovery results - simple version using psycopg2"""
import psycopg2
import json

conn = psycopg2.connect('postgresql://postgres:password@localhost:5433/xgrowth')
cur = conn.cursor()

# Get current graph data
cur.execute("""
    SELECT value
    FROM store
    WHERE prefix = 'user_34wsv56iMdmN9jPXo6Pg6HeroFK.social_graph'
    AND key = 'latest'
""")

row = cur.fetchone()
if not row:
    print("No graph data found")
    exit(1)

graph_data = row[0]  # Already parsed as dict by psycopg2

if graph_data.get('method') != 'x_native_common_followers':
    print(f"Not X Native data (method: {graph_data.get('method')})")
    exit(1)

print(f"Found X Native discovery data")
total_followers = 198  # From discovery log

# Update all competitors
updated_comps = []
for comp in graph_data.get('all_competitors_raw', []):
    mutual = comp.get('mutual_connections', 0)
    overlap_percentage = round((mutual / max(total_followers, 1)) * 100, 1)

    comp['overlap_count'] = mutual
    comp['overlap_percentage'] = overlap_percentage
    updated_comps.append(comp)

    print(f"  @{comp['username']:20s} {mutual:3d} mutual = {overlap_percentage:5.1f}%")

# Update graph data
graph_data['all_competitors_raw'] = updated_comps
graph_data['top_competitors'] = sorted(updated_comps, key=lambda x: x.get('mutual_connections', 0), reverse=True)[:20]

# Save back to database
cur.execute("""
    UPDATE store
    SET value = %s::jsonb
    WHERE prefix = 'user_34wsv56iMdmN9jPXo6Pg6HeroFK.social_graph'
    AND key = 'latest'
""", (json.dumps(graph_data),))

conn.commit()
print(f"\n✅ Updated {len(updated_comps)} competitors")

cur.close()
conn.close()
