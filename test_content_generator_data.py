"""
Quick validation script to check if user has required data for content generation
"""

from langgraph.store.postgres import PostgresStore

# Initialize store
conn_string = 'postgresql://postgres:password@localhost:5433/xgrowth'

with PostgresStore.from_conn_string(conn_string) as store:
    user_id = 'user_34wsv56iMdmN9jPXo6Pg6HeroFK'

    # Check writing samples
    print("=" * 60)
    print("📝 Checking Writing Samples...")
    posts_namespace = (user_id, "writing_samples")
    writing_samples = list(store.search(posts_namespace))
    print(f"✅ Found {len(writing_samples)} writing samples")

    if writing_samples:
        sample = writing_samples[0]
        print(f"   Sample post: {sample.value.get('text', '')[:100]}...")

    # Check competitors
    print("\n" + "=" * 60)
    print("🎯 Checking Competitor Data...")

    high_quality = []
    try:
        # Try different namespace patterns
        graph_namespace = (user_id, "social_graph")

        # Search all keys in the social_graph namespace
        all_graph_items = list(store.search(graph_namespace))
        print(f"   Found {len(all_graph_items)} items in social_graph namespace")

        for item in all_graph_items:
            print(f"   - Key: {item.key}, Type: {type(item.value)}")

        # Get graph data (try both keys)
        graph_data = store.get(graph_namespace, "graph_data") or store.get(graph_namespace, "latest")
        if graph_data:
            # Try different possible keys for competitors list
            competitors = (graph_data.value.get("top_competitors") or
                          graph_data.value.get("all_competitors_raw") or
                          graph_data.value.get("competitors", []))
            print(f"✅ Found {len(competitors)} competitors")

            # Count competitors with posts
            with_posts = [c for c in competitors if c.get("posts")]
            print(f"✅ {len(with_posts)} competitors have posts")

            # Count high-quality competitors
            high_quality = [c for c in competitors if c.get("quality_score", 0) >= 60 and c.get("posts")]
            print(f"✅ {len(high_quality)} high-quality competitors (60%+) with posts")

            if high_quality:
                sample_comp = high_quality[0]
                print(f"   Sample: @{sample_comp.get('username')} - Quality: {sample_comp.get('quality_score'):.1f}% - {len(sample_comp.get('posts', []))} posts")
        else:
            print("❌ No 'full_graph' key found in social_graph namespace")
    except Exception as e:
        print(f"❌ Error loading competitors: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Writing Samples: {len(writing_samples)} (need at least 10)")
    print(f"   High-Quality Competitors: {len(high_quality) if 'high_quality' in locals() else 0} (need at least 1)")

    if len(writing_samples) >= 10 and len(high_quality) >= 1:
        print("\n✅ User has sufficient data for content generation!")
    else:
        print("\n⚠️  User may not have sufficient data for optimal content generation")

    print("=" * 60)
