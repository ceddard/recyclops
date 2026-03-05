#!/usr/bin/env python3
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'recyclops'))

from models import InvokeRequest
from llm import CersIA

async def test_real_html():
    # HTML do usuário
    with open('mecontrataaipfvr/index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    request = InvokeRequest(html_content=html, pr_metadata={'filename': 'index.html'})

    api_key = os.getenv("OPENAI_API_KEY")
    print(f'✓ OPENAI_API_KEY: {api_key[:15]}...' if api_key else '✗ NO API KEY')
    print(f'📄 Arquivo: mecontrataaipfvr/index.html')
    print(f'📊 Tamanho: {len(html)} caracteres')
    print("\n" + "="*70)

    try:
        print("⏳ Analisando HTML com CersIA...")
        result = await CersIA.invoke(request)
        
        print(f"\n✅ ANÁLISE COMPLETA!\n")
        print(f"📈 Score: {result.score}/100")
        print(f"⚠️  Issues: {len(result.issues)}")
        print(f"💡 Sugestões: {len(result.suggestions)}")
        print(f"\n📝 Resumo:\n{result.summary}")
        
        if result.issues:
            print(f"\n🔴 ISSUES DETECTADAS:")
            for i, issue in enumerate(result.issues, 1):
                print(f"\n{i}. [{issue.severity.upper()}] {issue.message}")
                print(f"   Elemento: {issue.element}")
                if issue.wcag_criterion:
                    print(f"   WCAG: {issue.wcag_criterion}")
        
        if result.suggestions:
            print(f"\n✏️  SUGESTÕES DE CORREÇÃO:")
            for i, sug in enumerate(result.suggestions, 1):
                print(f"\n{i}. {sug.description}")
                print(f"   ❌ Original:\n{sug.original_code}")
                print(f"   ✅ Corrigido:\n{sug.fixed_code}")
    except Exception as e:
        print(f'\n❌ ERRO: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_real_html())
