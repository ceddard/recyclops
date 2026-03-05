#!/usr/bin/env python3
import sys
import os
import asyncio

# Add services path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'recyclops'))

from models import InvokeRequest
from llm import CersIA

async def test_service():
    # Test simple HTML
    html = '''<html>
<head>
    <title>Test Page</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>Test Page - Accessibility Check</h1>
    <p>This is a test paragraph without alt text for images.</p>
    <img src="test.jpg">
    <button>Click me</button>
    <a href="#">Link</a>
</body>
</html>'''

    request = InvokeRequest(html_content=html, pr_metadata={'filename': 'test.html'})

    # Check if API key is available
    api_key = os.getenv("OPENAI_API_KEY")
    print(f'OPENAI_API_KEY set: {bool(api_key)}')
    if api_key:
        print(f'API KEY first 10 chars: {api_key[:10]}...')
        if api_key.startswith("your-"):
            print("⚠️  WARNING: API KEY appears to be a placeholder, not a real key!")
    else:
        print("⚠️  NO API KEY FOUND! Service will not work without OPENAI_API_KEY environment variable.")
        return

    print("\n📋 Starting test...")
    print("-" * 60)

    try:
        print("⏳ Invoking CersIA with test HTML...")
        result = await CersIA.invoke(request)
        
        print(f'\n✅ SUCCESS!')
        print(f'   Score: {result.score}/100')
        print(f'   Issues found: {len(result.issues)}')
        print(f'   Suggestions: {len(result.suggestions)}')
        print(f'\n📝 Summary:\n   {result.summary}')
        
        if result.issues:
            print(f'\n⚠️  Top issues:')
            for issue in result.issues[:3]:
                print(f'   - [{issue.severity.upper()}] {issue.message}')
    except Exception as e:
        print(f'\n❌ ERROR: {type(e).__name__}')
        print(f'   {e}')
        import traceback
        print("\n📍 Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_service())
