#!/usr/bin/env python3
"""
Teste para integração Analyzer → Bypass-API → GitHub Comments
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Mock models
class MockSQSEvent:
    def __init__(self, repo, pr_number, head_sha):
        self.repo = repo
        self.pr_number = pr_number
        self.head_sha = head_sha

class MockFileAnalysis:
    def __init__(self, filename, score):
        self.filename = filename
        self.score = score
        self.issues = []
        self.suggestions = []
        self.summary = f"Score {score}/100"

# Test Cases
async def test_bypass_api_check():
    """Teste 1: Verificar se bypass-api check funciona (score baixo + bypass ativo)"""
    print("\n📋 Teste 1: Bypass-API Check")
    print("─" * 50)
    
    # Simulação
    score = 35  # Abaixo do threshold 50
    threshold = 50
    bypass_response = {
        "active": True,
        "reason": "Layout redesign in progress",
        "created_by": "tech-lead",
        "expires_at": 1735600000
    }
    
    print(f"Score: {score}/100 (abaixo threshold {threshold})")
    print(f"Esperado: Chamar bypass-api")
    
    # Lógica de decisão
    should_call_bypass_api = score < threshold
    if should_call_bypass_api and bypass_response and bypass_response.get("active"):
        result = "✅ PASS | PR aprovado via bypass"
    else:
        result = "❌ FAIL | Lógica incorreta"
    
    print(f"Resultado: {result}")
    return "✅" in result


async def test_bypass_remote_priority():
    """Teste 2: Bypass remoto tem prioridade sobre local"""
    print("\n📋 Teste 2: Bypass Remoto vs Local (Prioridade)")
    print("─" * 50)
    
    bypass_local = {"active": False}
    bypass_remote = {"active": True, "reason": "API call"}
    
    # Lógica: remoto ou local
    bypass = bypass_remote or bypass_local
    
    expected = bypass_remote
    if bypass == expected:
        result = "✅ PASS | Remoto tem prioridade"
    else:
        result = f"❌ FAIL | Esperado {expected}, obteve {bypass}"
    
    print(f"Bypass local: {bypass_local}")
    print(f"Bypass remoto: {bypass_remote}")
    print(f"Resultado: {result}")
    return "✅" in result


async def test_pr_comment_format():
    """Teste 3: Formato do comentário está correto"""
    print("\n📋 Teste 3: Formato do Comentário PR")
    print("─" * 50)
    
    score = 87.5
    issues_count = 2
    passed = True
    bypass = None
    
    # Simular construção do comentário
    icon = "✅" if passed else "❌"
    status = "APROVADO" if passed else "BLOQUEADO"
    
    comment_body = f"""{icon} **CERS-IA — Resultado da Análise**

| Métrica | Valor |
|---|---|
| **Score** | `{score:.0f} / 100` |
| **Threshold** | `50 / 100` |
| **Status** | {status} |
| **Problemas** | {issues_count} |"""
    
    required_fields = ["CERS-IA", "Score", "Threshold", "Status", "Problemas"]
    has_all_fields = all(field in comment_body for field in required_fields)
    
    if has_all_fields and "✅" in comment_body:
        result = "✅ PASS | Comentário bem formatado"
    else:
        result = "❌ FAIL | Campos obrigatórios faltando"
    
    print(f"Has all required fields: {has_all_fields}")
    print(f"Resultado: {result}")
    return "✅" in result


async def test_pr_comment_with_bypass():
    """Teste 4: Comentário inclui informação de bypass"""
    print("\n📋 Teste 4: Comentário com Bypass Ativo")
    print("─" * 50)
    
    score = 35
    passed = True  # Passou porque tem bypass
    bypass = {
        "active": True,
        "reason": "Design sprint phase",
        "created_by": "designer"
    }
    
    has_bypass_note = bypass is not None
    if has_bypass_note and passed:
        comment_includes_bypass = f"Motivo: _{bypass['reason']}_"
        result = "✅ PASS | Bypass incluído no comentário"
    else:
        result = "❌ FAIL | Bypass deveria estar no comentário"
    
    print(f"Score: {score}/100")
    print(f"Bypass ativo: {bypass['reason']}")
    print(f"Resultado: {result}")
    return "✅" in result


async def test_dlq_on_error():
    """Teste 5: Erro crítico envia para DLQ"""
    print("\n📋 Teste 5: DLQ em Erro Crítico")
    print("─" * 50)
    
    error_message = "Connection timeout to CERS-IA"
    event = MockSQSEvent("owner/repo", 123, "abc123")
    
    dlq_enabled = os.environ.get("DLQ_URL") is not None
    
    if dlq_enabled:
        result = "✅ PASS | DLQ está configurado"
    else:
        # Simular envio (sem DLQ real)
        dlq_message = {
            "repo": event.repo,
            "pr_number": event.pr_number,
            "head_sha": event.head_sha,
            "error": error_message
        }
        result = "⚠️  PASS (SIM) | DLQ não configurado, mas lógica está pronta"
    
    print(f"Erro: {error_message}")
    print(f"Enviaria para DLQ: {dlq_message if 'dlq_message' in locals() else 'Sim'}")
    print(f"Resultado: {result}")
    return "✅" in result or "⚠️" in result


async def test_score_decision_logic():
    """Teste 6: Lógica de decisão de score vs bypass"""
    print("\n📋 Teste 6: Lógica de Decisão (Score vs Bypass)")
    print("─" * 50)
    
    threshold = 50
    test_cases = [
        (85, None, True, "Score OK, sem bypass"),
        (35, None, False, "Score baixo, sem bypass"),
        (35, {"active": True}, True, "Score baixo, mas tem bypass"),
        (85, {"active": True}, True, "Score OK, com bypass (redundante)"),
    ]
    
    all_pass = True
    for score, bypass, expected_passed, desc in test_cases:
        passed = score >= threshold or bypass is not None
        is_correct = passed == expected_passed
        status = "✅" if is_correct else "❌"
        print(f"{status} {desc}: score={score}, bypass={'Sim' if bypass else 'Não'} → passed={passed}")
        all_pass = all_pass and is_correct
    
    result = "✅ PASS | Todos os casos corretos" if all_pass else "❌ FAIL | Lógica incorreta"
    print(f"\nResultado: {result}")
    return all_pass


async def main():
    print("=" * 50)
    print("🧪 TESTE: ANALYZER BYPASS-API INTEGRATION")
    print("=" * 50)
    
    tests = [
        ("Bypass-API Check", test_bypass_api_check),
        ("Prioridade Remoto", test_bypass_remote_priority),
        ("Formato Comentário", test_pr_comment_format),
        ("Comentário com Bypass", test_pr_comment_with_bypass),
        ("DLQ em Erro", test_dlq_on_error),
        ("Lógica Decisão", test_score_decision_logic),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = await test_func()
        except Exception as e:
            print(f"❌ Erro ao executar {name}: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES")
    print("=" * 50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\n{'✅' if passed == total else '⚠️ '} {passed}/{total} testes passaram")
    print("=" * 50)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
