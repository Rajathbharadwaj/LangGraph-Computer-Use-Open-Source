#!/usr/bin/env python3
"""Patch X Native discovery results to add frontend-compatible fields"""
import asyncio
from langgraph.store.postgres import PostgresStore

async def patch_results():
    async with PostgresStore.from_conn_string('postgresql://postgres:password@localhost:5433/xgrowth') as store:
        namespace = ('user_34wsv56iMdmN9jPXo6Pg6HeroFK', 'social_graph')

        # Get current graph data
        items = list(store.search(namespace, limit=1))
        if not items:
            print("No graph data found")
            return

        graph_data = items[0].value

        if graph_data.get('method') != 'x_native_common_followers':
            print(f"Not X Native data (method: {graph_data.get('method')})")
            return

        print(f"Found X Native discovery data")
        print(f"Analyzed followers: {graph_data.get('analyzed_followers')}")

        # Update all competitors with overlap fields
        total_followers = 198  # From the discovery log
        updated_comps = []

        for comp in graph_data.get('all_competitors_raw', []):
            mutual = comp.get('mutual_connections', 0)

            # Calculate overlap percentage
            overlap_percentage = round((mutual / max(total_followers, 1)) * 100, 1)

            # Add frontend-compatible fields
            comp['overlap_count'] = mutual
            comp['overlap_percentage'] = overlap_percentage

            updated_comps.append(comp)
            print(f"  @{comp['username']}: {mutual} mutual = {overlap_percentage}%")

        # Update graph data
        graph_data['all_competitors_raw'] = updated_comps
        graph_data['top_competitors'] = sorted(updated_comps, key=lambda x: x.get('mutual_connections', 0), reverse=True)[:20]

        # Save back to store
        await store.aput(namespace, 'latest', graph_data)

        print(f"\n✅ Updated {len(updated_comps)} competitors with overlap fields")

asyncio.run(patch_results())
