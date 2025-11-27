#!/usr/bin/env python3
"""Clear all scraped posts to force re-scraping with engagement metrics"""
import psycopg2
import json

conn = psycopg2.connect('postgresql://postgres:password@localhost:5433/xgrowth')
cur = conn.cursor()

# Get graph data
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

graph_data = row[0]

# Clear posts from all competitors
for comp in graph_data.get('all_competitors_raw', []):
    comp['posts'] = []
    comp['post_count'] = 0

# Update graph in database
cur.execute("""
    UPDATE store
    SET value = %s::jsonb
    WHERE prefix = 'user_34wsv56iMdmN9jPXo6Pg6HeroFK.social_graph'
    AND key = 'latest'
""", (json.dumps(graph_data),))

conn.commit()
print(f"✅ Cleared posts from {len(graph_data.get('all_competitors_raw', []))} competitors")
print("   Ready to re-scrape with engagement metrics!")

cur.close()
conn.close()
