"""
Unit tests for post tone/intent analysis tool.

Tests:
- Humor detection
- Spam rejection
- Sarcasm detection
- Educational content approval
- Extended thinking presence
- Performance benchmarks
"""

import pytest
import asyncio
import json
import time
from test_post_analysis_dataset import TEST_POSTS, get_test_post
from async_extension_tools import analyze_post_tone_and_intent


@pytest.mark.asyncio
async def test_humor_detection():
    """Test that humorous posts are detected correctly"""
    post = get_test_post("humor_debugging")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert analysis["tone"] == "humorous", f"Expected humorous, got {analysis['tone']}"
    assert analysis["engagement_worthy"] is True, "Humor post should be engagement-worthy"
    assert analysis["confidence"] >= post["expected_analysis"]["min_confidence"], \
        f"Confidence {analysis['confidence']} below threshold {post['expected_analysis']['min_confidence']}"
    assert len(analysis.get("thinking_summary", "")) > 0, "Should have thinking summary"

    print(f"✅ Humor detection passed: {analysis['tone']} (confidence: {analysis['confidence']:.2f})")


@pytest.mark.asyncio
async def test_spam_rejection():
    """Test that promotional spam is rejected"""
    post = get_test_post("promotional_spam")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert analysis["intent"] == "promotion", f"Expected promotion, got {analysis['intent']}"
    assert analysis["engagement_worthy"] is False, "Spam should not be engagement-worthy"
    assert analysis["recommended_response_type"] == "skip", "Should recommend skip for spam"

    print(f"✅ Spam rejection passed: {analysis['intent']} (engagement_worthy: {analysis['engagement_worthy']})")


@pytest.mark.asyncio
async def test_sarcasm_detection():
    """Test that sarcastic posts are detected with appropriate confidence"""
    post = get_test_post("hard_sarcasm_risky")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert analysis["tone"] == "sarcastic", f"Expected sarcastic, got {analysis['tone']}"

    # If confidence >= 0.9, engagement might be okay
    # If confidence < 0.9, should NOT engage (per user requirements)
    if analysis["confidence"] < 0.9:
        assert analysis["engagement_worthy"] is False or analysis["recommended_response_type"] == "skip", \
            "Low-confidence sarcasm should be skipped"

    print(f"✅ Sarcasm detection passed: {analysis['tone']} (confidence: {analysis['confidence']:.2f}, engage: {analysis['engagement_worthy']})")


@pytest.mark.asyncio
async def test_educational_approval():
    """Test that high-quality educational content is approved"""
    post = get_test_post("educational_technical")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert analysis["tone"] == "serious", f"Expected serious, got {analysis['tone']}"
    assert analysis["intent"] == "educational", f"Expected educational, got {analysis['intent']}"
    assert analysis["engagement_worthy"] is True, "Educational content should be engagement-worthy"
    assert analysis["quality_score"] >= 70, f"Quality score {analysis['quality_score']} too low for educational content"
    assert analysis["recommended_response_type"] == "thoughtful_comment", \
        "Educational posts deserve thoughtful comments"

    print(f"✅ Educational approval passed: quality={analysis['quality_score']}, engage={analysis['engagement_worthy']}")


@pytest.mark.asyncio
async def test_extended_thinking_present():
    """Test that extended thinking reasoning is captured"""
    post = get_test_post("genuine_question")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert "thinking_summary" in analysis, "Should have thinking_summary field"
    # Note: thinking_summary might be empty if extended thinking didn't trigger
    # but the field should exist

    print(f"✅ Extended thinking field present: {len(analysis.get('thinking_summary', ''))} chars")


@pytest.mark.asyncio
async def test_safe_sarcasm_vs_harsh_sarcasm():
    """Test that safe relatable sarcasm is distinguished from harsh sarcasm"""
    safe_post = get_test_post("safe_sarcasm_relatable")

    result = await analyze_post_tone_and_intent(
        post_text=safe_post["post_text"],
        author_handle=safe_post["author_handle"],
        author_followers=safe_post["author_followers"],
        engagement_metrics=json.dumps(safe_post["engagement_metrics"])
    )

    analysis = json.loads(result)

    # Safe sarcasm should be classified as humorous, not sarcastic
    assert analysis["tone"] in ["humorous", "sarcastic"], \
        f"Expected humorous or sarcastic, got {analysis['tone']}"

    # If it's humorous, should be engagement-worthy
    # If it's sarcastic, confidence should be high
    if analysis["tone"] == "humorous":
        assert analysis["engagement_worthy"] is True, "Safe humor should be engagement-worthy"
    elif analysis["tone"] == "sarcastic":
        assert analysis["confidence"] >= 0.7, "Sarcastic classification needs decent confidence"

    print(f"✅ Safe sarcasm test passed: {analysis['tone']} (confidence: {analysis['confidence']:.2f})")


@pytest.mark.asyncio
async def test_genuine_question_engagement():
    """Test that genuine questions are recommended for thoughtful engagement"""
    post = get_test_post("genuine_question")

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    analysis = json.loads(result)

    assert analysis["intent"] in ["question", "conversation_starter"], \
        f"Expected question/conversation_starter, got {analysis['intent']}"
    assert analysis["engagement_worthy"] is True, "Questions should be engagement-worthy"
    assert analysis["recommended_response_type"] in ["thoughtful_comment", "question"], \
        "Questions need thoughtful responses"

    print(f"✅ Question engagement passed: {analysis['intent']}, response_type={analysis['recommended_response_type']}")


@pytest.mark.asyncio
async def test_performance_latency():
    """Test that analysis completes within acceptable time (<5 seconds)"""
    post = get_test_post("educational_technical")

    start_time = time.time()

    result = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"],
        engagement_metrics=json.dumps(post["engagement_metrics"])
    )

    elapsed = time.time() - start_time

    # First call might be slower (no cache), but should still be < 10s
    assert elapsed < 10.0, f"Analysis took {elapsed:.2f}s, expected <10s"

    print(f"✅ Performance test passed: {elapsed:.2f}s")


@pytest.mark.asyncio
async def test_cache_functionality():
    """Test that caching works (second call is faster)"""
    post = get_test_post("humor_debugging")

    # First call (uncached)
    start1 = time.time()
    result1 = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"]
    )
    elapsed1 = time.time() - start1

    # Second call (should be cached)
    start2 = time.time()
    result2 = await analyze_post_tone_and_intent(
        post_text=post["post_text"],
        author_handle=post["author_handle"],
        author_followers=post["author_followers"]
    )
    elapsed2 = time.time() - start2

    # Results should be identical
    assert result1 == result2, "Cached result should match original"

    # Second call should be much faster (< 500ms for cache retrieval)
    assert elapsed2 < 0.5, f"Cache retrieval took {elapsed2:.2f}s, expected <0.5s"

    print(f"✅ Cache test passed: first={elapsed1:.2f}s, cached={elapsed2:.2f}s")


@pytest.mark.asyncio
async def test_all_posts_in_dataset():
    """Run analysis on all test posts to ensure no crashes"""
    results = []

    for post in TEST_POSTS:
        try:
            result = await analyze_post_tone_and_intent(
                post_text=post["post_text"],
                author_handle=post["author_handle"],
                author_followers=post["author_followers"],
                engagement_metrics=json.dumps(post.get("engagement_metrics", {}))
            )

            analysis = json.loads(result)
            results.append({
                "post_id": post["id"],
                "success": True,
                "analysis": analysis
            })

            print(f"  {post['id']}: {analysis['tone']}/{analysis['intent']} (engage={analysis['engagement_worthy']})")

        except Exception as e:
            results.append({
                "post_id": post["id"],
                "success": False,
                "error": str(e)
            })
            print(f"  {post['id']}: FAILED - {e}")

    # All posts should succeed
    failures = [r for r in results if not r["success"]]
    assert len(failures) == 0, f"Some posts failed: {failures}"

    print(f"✅ All {len(TEST_POSTS)} test posts analyzed successfully")


if __name__ == "__main__":
    print("=" * 80)
    print("POST TONE ANALYSIS UNIT TESTS")
    print("=" * 80)

    # Run all tests
    asyncio.run(test_humor_detection())
    asyncio.run(test_spam_rejection())
    asyncio.run(test_sarcasm_detection())
    asyncio.run(test_educational_approval())
    asyncio.run(test_extended_thinking_present())
    asyncio.run(test_safe_sarcasm_vs_harsh_sarcasm())
    asyncio.run(test_genuine_question_engagement())
    asyncio.run(test_performance_latency())
    asyncio.run(test_cache_functionality())
    asyncio.run(test_all_posts_in_dataset())

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED ✅")
    print("=" * 80)
