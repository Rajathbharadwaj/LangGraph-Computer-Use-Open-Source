#!/usr/bin/env python3
"""
Generate X posts/comments using user's writing style with LangChain structured output
"""
import asyncio
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool
from x_writing_style_learner import XWritingStyleManager
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

# Load environment variables
load_dotenv()

# Database connection
DB_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/xgrowth")


class XPost(BaseModel):
    """A generated X post in the user's writing style"""
    content: str = Field(description="The post content (max 280 chars)")
    hashtags: list[str] = Field(description="Relevant hashtags to include", default_factory=list)


class XComment(BaseModel):
    """A generated X comment/reply in the user's writing style"""
    content: str = Field(description="The comment content")
    mentions: list[str] = Field(description="Users to mention (without @)", default_factory=list)


async def generate_styled_content(
    user_id: str,
    context: str,
    content_type: str = "post"
) -> XPost | XComment:
    """
    Generate a post or comment in the user's writing style
    
    Args:
        user_id: User's extension ID
        context: What to write about (for posts) or what to reply to (for comments)
        content_type: "post" or "comment"
    
    Returns:
        XPost or XComment with generated content
    """
    # Initialize store
    conn_pool = ConnectionPool(
        conninfo=DB_URI,
        min_size=1,
        max_size=10
    )
    store = PostgresStore(conn=conn_pool)
    
    # Initialize style manager
    style_manager = XWritingStyleManager(store, user_id)
    
    # Generate few-shot prompt with user's examples
    few_shot_prompt = style_manager.generate_few_shot_prompt(
        context=context,
        content_type=content_type,
        num_examples=3
    )
    
    print(f"📝 Generating {content_type} with few-shot prompt...")
    print(f"📊 Context: {context[:100]}...\n")
    
    # Create agent with structured output
    schema = XPost if content_type == "post" else XComment
    
    agent = create_agent(
        model="claude-sonnet-4-5-20250929",
        tools=[],
        response_format=ToolStrategy(schema)
    )
    
    # Generate content
    result = agent.invoke({
        "messages": [{"role": "user", "content": few_shot_prompt}]
    })
    
    # Close pool
    conn_pool.close()
    
    return result["structured_response"]


async def main():
    """Test the styled content generation"""
    user_id = "user_6l78nk"  # Rajath's extension user ID
    
    print("=" * 70)
    print("TEST 1: Generate a comment on a tech post")
    print("=" * 70)
    
    tech_post = """
    Just released our new AI model with 10x faster inference!
    Built with PyTorch and optimized for edge devices.
    Check it out: https://github.com/example/model
    """
    
    comment = await generate_styled_content(
        user_id=user_id,
        context=tech_post,
        content_type="comment"
    )
    
    print(f"💬 Generated Comment:")
    print(f"   {comment.content}")
    if comment.mentions:
        print(f"   Mentions: {', '.join('@' + m for m in comment.mentions)}")
    print()
    
    print("=" * 70)
    print("TEST 2: Generate a post about building side projects")
    print("=" * 70)
    
    post_context = """
    Share your thoughts on the best way to build and ship a side project quickly.
    Give practical advice on tech stack, deployment, and getting first users.
    """
    
    post = await generate_styled_content(
        user_id=user_id,
        context=post_context,
        content_type="post"
    )
    
    print(f"📝 Generated Post:")
    print(f"   {post.content}")
    if post.hashtags:
        print(f"   Hashtags: {' '.join('#' + h for h in post.hashtags)}")
    print()
    
    print("=" * 70)
    print("✅ Styled content generation complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

