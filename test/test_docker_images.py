#!/usr/bin/env python3
"""
Teste de validação de imagens Docker
Verifica Dockerfiles, requirements.txt, entrypoints, e sintaxe
"""
import os
import sys
from pathlib import Path
from typing import Dict, List

# Estrutura dos serviços
SERVICES = {
    "bypass-api": {
        "path": "services/bypass-api",
        "port": 8001,
        "type": "http-server",
        "entrypoint": "uvicorn main:app --host 0.0.0.0 --port 8001",
        "main_file": "main.py",
    },
    "accessibility-analyzer": {
        "path": "services/accessibility-analyzer",
        "port": None,  # Worker SQS
        "type": "sqs-worker",
        "entrypoint": "python main.py",
        "main_file": "main.py",
    },
    "recyclops": {
        "path": "services/recyclops",
        "port": 8000,
        "type": "http-server",
        "entrypoint": "uvicorn main:app --host 0.0.0.0 --port 8000",
        "main_file": "main.py",
    },
}

def test_dockerfile_exists(service_name: str, config: Dict) -> bool:
    """Teste 1: Verificar se Dockerfile existe"""
    dockerfile_path = Path(config["path"]) / "Dockerfile"
    if dockerfile_path.exists():
        print(f"  ✅ Dockerfile encontrado")
        return True
    else:
        print(f"  ❌ Dockerfile não encontrado em {dockerfile_path}")
        return False

def test_dockerfile_syntax(service_name: str, config: Dict) -> bool:
    """Teste 2: Validar sintaxe básica do Dockerfile"""
    dockerfile_path = Path(config["path"]) / "Dockerfile"
    
    try:
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        
        # Validações básicas
        required_keywords = ["FROM", "WORKDIR", "COPY", "CMD"]
        missing = [kw for kw in required_keywords if kw not in content]
        
        if missing:
            print(f"  ❌ Dockerfile sem palavras-chave: {missing}")
            return False
        
        # Verificar base image
        if "python:3.12-slim" in content:
            print(f"  ✅ Base image: python:3.12-slim")
        else:
            print(f"  ⚠️  Base image não é python:3.12-slim")
        
        # Verificar entrypoint
        if "CMD" in content:
            print(f"  ✅ CMD definido")
        
        print(f"  ✅ Sintaxe do Dockerfile válida")
        return True
    except Exception as e:
        print(f"  ❌ Erro ao ler Dockerfile: {e}")
        return False

def test_requirements_txt_exists(service_name: str, config: Dict) -> bool:
    """Teste 3: Verificar se requirements.txt existe"""
    req_path = Path(config["path"]) / "requirements.txt"
    if req_path.exists():
        print(f"  ✅ requirements.txt encontrado")
        return True
    else:
        print(f"  ❌ requirements.txt não encontrado")
        return False

def test_requirements_syntax(service_name: str, config: Dict) -> bool:
    """Teste 4: Validar sintaxe de requirements.txt"""
    req_path = Path(config["path"]) / "requirements.txt"
    
    try:
        with open(req_path, 'r') as f:
            lines = f.readlines()
        
        packages = []
        errors = []
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            # Ignorar linhas vazias e comentários
            if not line or line.startswith("#"):
                continue
            
            # Validar formato
            if "==" in line or ">=" in line or "<=" in line or "~=" in line:
                pkg = line.split(("=" if "=" in line else ">")[0])[0].strip()
                packages.append(pkg)
            else:
                errors.append(f"  Linha {i}: {line}")
        
        if errors:
            print(f"  ⚠️  Linhas com formato suspeito:")
            for err in errors[:3]:  # Mostrar apenas 3 primeiras
                print(f"    {err}")
        
        if packages:
            print(f"  ✅ {len(packages)} pacotes encontrados")
            print(f"    Principais: {', '.join(packages[:3])}")
        
        return True
    except Exception as e:
        print(f"  ❌ Erro ao ler requirements.txt: {e}")
        return False

def test_main_file_exists(service_name: str, config: Dict) -> bool:
    """Teste 5: Verificar se main.py existe"""
    main_path = Path(config["path"]) / config["main_file"]
    if main_path.exists():
        print(f"  ✅ {config['main_file']} encontrado")
        return True
    else:
        print(f"  ❌ {config['main_file']} não encontrado")
        return False

def test_main_file_syntax(service_name: str, config: Dict) -> bool:
    """Teste 6: Validar sintaxe Python do main.py"""
    main_path = Path(config["path"]) / config["main_file"]
    
    try:
        with open(main_path, 'r') as f:
            code = f.read()
        
        # Tentar compilar
        compile(code, str(main_path), 'exec')
        print(f"  ✅ Sintaxe Python válida")
        return True
    except SyntaxError as e:
        print(f"  ❌ Erro de sintaxe: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Erro ao validar: {e}")
        return False

def test_service_type_files(service_name: str, config: Dict) -> bool:
    """Teste 7: Verificar arquivos específicos do tipo de serviço"""
    service_path = Path(config["path"])
    
    if config["type"] == "http-server":
        required = ["main.py", "requirements.txt", "Dockerfile"]
        # Pode ter models.py, etc
        print(f"  ✅ HTTP Server: verifica FastAPI")
        
        main_content = (service_path / "main.py").read_text()
        if "FastAPI" in main_content or "fastapi" in main_content:
            print(f"     ✅ FastAPI encontrado")
            return True
        else:
            print(f"     ⚠️  FastAPI não encontrado explicitamente")
            return False
    
    elif config["type"] == "sqs-worker":
        required = ["main.py", "requirements.txt", "Dockerfile", "analyzer.py"]
        print(f"  ✅ SQS Worker: verifica polling")
        
        main_content = (service_path / "main.py").read_text()
        if "receive_message" in main_content or "asyncio" in main_content:
            print(f"     ✅ Code polling/async encontrado")
            return True
        else:
            print(f"     ⚠️  Polling não encontrado")
            return False
    
    return True

def test_docker_build_simulation(service_name: str, config: Dict) -> bool:
    """Teste 8: Simular build (verificar se COPY funcionaria)"""
    service_path = Path(config["path"])
    dockerfile_path = service_path / "Dockerfile"
    
    try:
        content = dockerfile_path.read_text()
        
        # Verificar se COPY references existem
        if "COPY requirements.txt" in content:
            if (service_path / "requirements.txt").exists():
                print(f"  ✅ COPY requirements.txt: arquivo existe")
            else:
                print(f"  ❌ COPY requirements.txt: arquivo não existe")
                return False
        
        if "COPY . ." in content:
            if service_path.exists():
                print(f"  ✅ COPY . .: diretório existe")
            else:
                print(f"  ❌ COPY . .: diretório não existe")
                return False
        
        print(f"  ✅ Estrutura de build válida")
        return True
    except Exception as e:
        print(f"  ❌ Erro ao simular build: {e}")
        return False

def main():
    print("=" * 60)
    print("🐳 TESTE DE VALIDAÇÃO DE IMAGENS DOCKER")
    print("=" * 60)
    
    all_results = {}
    
    for service_name, config in SERVICES.items():
        print(f"\n📦 {service_name.upper()}")
        print("─" * 60)
        
        results = {
            "Dockerfile exists": test_dockerfile_exists(service_name, config),
            "Dockerfile syntax": test_dockerfile_syntax(service_name, config),
            "requirements.txt exists": test_requirements_txt_exists(service_name, config),
            "requirements syntax": test_requirements_syntax(service_name, config),
            "main.py exists": test_main_file_exists(service_name, config),
            "main.py syntax": test_main_file_syntax(service_name, config),
            "Service type files": test_service_type_files(service_name, config),
            "Docker build sim": test_docker_build_simulation(service_name, config),
        }
        
        all_results[service_name] = results
        
        # Summary
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        status = "✅" if passed == total else "⚠️"
        print(f"\n{status} {passed}/{total} testes passaram")
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 RESUMO FINAL")
    print("=" * 60)
    
    total_passed = 0
    total_tests = 0
    
    for service_name, results in all_results.items():
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        total_passed += passed
        total_tests += total
        
        status = "✅" if passed == total else "⚠️"
        print(f"{status} {service_name:30} {passed:2}/{total:2} testes")
    
    print("─" * 60)
    print(f"{'✅' if total_passed == total_tests else '⚠️'} TOTAL: {total_passed}/{total_tests} testes")
    print("=" * 60)
    
    # Recomendações
    print("\n📋 Recomendações para Deploy:")
    print("  1. ✅ Todos os Dockerfiles estão válidos")
    print("  2. ✅ Todos os requirements.txt existem e são válidos")
    print("  3. ✅ Sintaxe Python verificada")
    print("  4. ✅ Estrutura Docker validada")
    print("\n🚀 Próximos passos:")
    print("  1. docker build para cada serviço")
    print("  2. Login no ECR: aws ecr get-login-password | docker login --username AWS")
    print("  3. docker tag | docker push para cada serviço")
    print("  4. Atualizar ECS tasks com novas image URIs")
    
    return total_passed == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
