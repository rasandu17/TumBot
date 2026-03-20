import os, json
from dotenv import load_dotenv
load_dotenv()
import pytumblr

client = pytumblr.TumblrRestClient(
    os.getenv('TUMBLR_CONSUMER_KEY'),
    os.getenv('TUMBLR_CONSUMER_SECRET'),
    os.getenv('TUMBLR_OAUTH_TOKEN'),
    os.getenv('TUMBLR_OAUTH_SECRET'),
)
blog = os.getenv('TUMBLR_BLOG_NAME')

print("=== PUBLISHED POSTS ===")
result = client.posts(blog, limit=5)
posts = result.get('posts', [])
print(f"Count: {len(posts)}")
for p in posts:
    print(f"  id={p.get('id')} type={p.get('type')} state={p.get('state')} url={p.get('post_url')}")

print("\n=== DRAFTS ===")
drafts = client.drafts(blog)
draft_posts = drafts.get('posts', [])
print(f"Count: {len(draft_posts)}")
for p in draft_posts:
    print(f"  id={p.get('id')} type={p.get('type')} state={p.get('state')}")

print("\n=== QUEUE ===")
queue = client.queue(blog)
queue_posts = queue.get('posts', [])
print(f"Count: {len(queue_posts)}")
for p in queue_posts:
    print(f"  id={p.get('id')} type={p.get('type')} state={p.get('state')}")

print("\n=== blog_info ===")
info = client.blog_info(blog)
b = info.get('blog', {})
print(f"  name: {b.get('name')}")
print(f"  title: {b.get('title')}")
print(f"  total_posts: {b.get('total_posts')}")
print(f"  url: {b.get('url')}")
