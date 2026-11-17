#!/usr/bin/env python3
"""
scripts/check_sensitive_data.py — Verificador de Segurança Pré-Commit / Pré-Push (FCA-ENG-001)

Verifica se há dados sensíveis de produção, arquivos de análise ou credenciais
sendo incluídos no Git antes de commit ou envio público.

Modos de uso:
    python3 scripts/check_sensitive_data.py --staged      # Verifica arquivos no stage (pre-commit)
    python3 scripts/check_sensitive_data.py --unpushed    # Verifica commits não enviados (pre-push)
    python3 scripts/check_sensitive_data.py --all         # Verifica todos os arquivos rastreados
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Extensões e caminhos estritamente proibidos de serem versionados no Git
PROHIBITED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
    ".vsdx", ".vsd", ".drawio", ".pcap", ".pcapng",
    ".zip", ".7z", ".tar.gz", ".rar",
    ".key", ".pem", ".p12", ".pfx", ".crt", ".cert", ".der",
    ".jks", ".keystore", ".kdbx",
}

PROHIBITED_FILENAMES = {
    "dados_analise.json",
    "decisoes.yaml",
    "credentials.json",
    "credentials.yml",
    "credentials.yaml",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
}

PROHIBITED_PREFIXES = [
    "entrada/",
    "analise/",
    "scratch/",
    "publicacao-candidata/",
]

ALLOWED_EXCEPTIONS = {
    "entrada/.gitkeep",
    "entrada/README.md",
    "analise/.gitkeep",
    "analise/README.md",
}

# Expressões regulares para detecção de dados sensíveis de produção
SENSITIVE_PATTERNS = [
    # Chaves privadas
    (re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"), "Chave privada criptográfica detectada"),
    # Tokens ou segredos com atribuição direta
    (re.compile(r"""(?i)(?:api_key|access_token|secret_key|auth_token|bearer\s+[a-z0-9_\-\.]{20,})\s*[:=]\s*['"][a-z0-9_\-\.]{16,}['"]"""), "Possível token ou segredo de API hardcodeado"),
    # Endereços IPv4 privados de infraestrutura real (exceto loops e documentação RFC 5737 / RFC 3330)
    (re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"), "Endereço IPv4 privado de produção detectado"),
    # Nomes reais de projetos ou clientes que devem ser anonimizados no repositório aberto
    (re.compile(r"(?i)\b(?:eaf\s+sdwan\s+seguro|hld\s+eaf\s+gerencia|eaf_sdwan)\b"), "Referência direta a documento ou projeto real de cliente"),
    # Caminhos absolutos de estações locais de trabalho
    (re.compile(r"/(?:home|Users)/[a-zA-Z0-9_\-\.]+/(?:projetos|desktop|downloads)"), "Caminho absoluto local de estação de trabalho"),
]

# Arquivos ou linhas isentas de checagem de IP ou padrões (ex: documentação técnica que cita RFCs)
WHITELIST_IPS = {
    "127.0.0.1", "0.0.0.0", "192.0.2.", "198.51.100.", "203.0.113."
}


def run_git(cmd: list[str]) -> str:
    """Executa um comando Git e retorna a saída."""
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        return ""
    return res.stdout.strip()


def get_target_files(mode: str) -> list[str]:
    """Obtém a lista de arquivos a serem inspecionados conforme o modo."""
    if mode == "staged":
        # Arquivos adicionados ou modificados no staging
        out = run_git(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
        return [f.strip() for f in out.splitlines() if f.strip()]
    elif mode == "unpushed":
        # Arquivos modificados entre origin/main e HEAD
        upstream = run_git(["git", "rev-parse", "--abbrev-ref", "@{upstream}"]) or "origin/main"
        out = run_git(["git", "diff", f"{upstream}..HEAD", "--name-only", "--diff-filter=ACMR"])
        if not out:
            # Fallback para staged se upstream não estiver disponível ou sem diff
            out = run_git(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
        return [f.strip() for f in out.splitlines() if f.strip()]
    else:  # mode == "all"
        out = run_git(["git", "ls-files"])
        return [f.strip() for f in out.splitlines() if f.strip()]


def check_file_path(file_path: str) -> list[str]:
    """Verifica se o caminho do arquivo viola as diretrizes de publicação."""
    errors = []
    norm_path = file_path.replace("\\", "/").lstrip("./")

    if norm_path in ALLOWED_EXCEPTIONS:
        return []

    # Checa diretórios proibidos
    for prefix in PROHIBITED_PREFIXES:
        if norm_path.startswith(prefix):
            errors.append(f"Arquivo localizado em diretório proibido para versionamento: '{norm_path}'")

    # Checa extensões proibidas
    ext = os.path.splitext(norm_path)[1].lower()
    if ext in PROHIBITED_EXTENSIONS:
        errors.append(f"Arquivo com extensão proibida para versionamento ('{ext}'): '{norm_path}'")

    # Checa nomes de arquivos proibidos
    fname = os.path.basename(norm_path).lower()
    if fname in PROHIBITED_FILENAMES:
        errors.append(f"Arquivo restrito de dados ou credenciais: '{norm_path}'")

    if norm_path.startswith(".env") and not norm_path.startswith(".env.example"):
        errors.append(f"Arquivo de variáveis de ambiente sensível: '{norm_path}'")

    return errors


def check_file_content(file_path: str, staged_only: bool = False) -> list[str]:
    """Verifica se o conteúdo do arquivo contém padrões sensíveis."""
    errors = []
    norm_path = file_path.replace("\\", "/").lstrip("./")

    # Se este for o próprio script de verificação, ignora os padrões literais para evitar auto-detecção
    if norm_path == "scripts/check_sensitive_data.py":
        return []

    lines_to_check: list[tuple[int, str]] = []

    if staged_only:
        # Pega apenas as linhas adicionadas (+) no diff do stage
        diff_out = run_git(["git", "diff", "--cached", "-U0", "--", file_path])
        line_num = 0
        for diff_line in diff_out.splitlines():
            if diff_line.startswith("@@"):
                m = re.search(r"\+(\d+)", diff_line)
                if m:
                    line_num = int(m.group(1))
            elif diff_line.startswith("+") and not diff_line.startswith("+++"):
                lines_to_check.append((line_num, diff_line[1:]))
                line_num += 1
    else:
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for idx, line in enumerate(f, start=1):
                    lines_to_check.append((idx, line))
        except Exception:
            return []

    for line_idx, line in lines_to_check:
        for pattern, desc in SENSITIVE_PATTERNS:
            match = pattern.search(line)
            if match:
                matched_str = match.group(0)
                # Verifica exceções de IP
                if any(white in matched_str for white in WHITELIST_IPS):
                    continue
                # Se for IPv4, checar se não é uma máscara de sub-rede como 255.255.255.0
                if "IPv4" in desc and (matched_str.startswith("255.") or matched_str.endswith(".255") or matched_str.endswith(".0")):
                    continue

                snippet = line.strip()[:100]
                errors.append(
                    f"{norm_path}:{line_idx} — {desc} -> '{matched_str}' | Linha: {snippet}"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificador de Segurança Pré-Commit / Pré-Push (FCA-ENG-001)")
    parser.add_argument("--staged", action="store_true", help="Verifica alterações no staging (pre-commit)")
    parser.add_argument("--unpushed", action="store_true", help="Verifica commits locais pendentes de envio (pre-push)")
    parser.add_argument("--all", action="store_true", help="Verifica todos os arquivos rastreados no Git")
    args = parser.parse_args()

    mode = "staged" if args.staged else ("unpushed" if args.unpushed else ("all" if args.all else "staged"))

    files = get_target_files(mode)
    if not files:
        print(f"🛡️  [FCA-ENG-001 Security Check] Nenhum arquivo para validar ({mode}).")
        return 0

    print(f"🛡️  [FCA-ENG-001 Security Check] Inspecionando {len(files)} arquivo(s) no modo '{mode}'...")

    all_errors = []

    for fpath in files:
        # Checa caminho/nome/extensão
        path_errs = check_file_path(fpath)
        all_errors.extend(path_errs)

        # Checa conteúdo de texto
        content_errs = check_file_content(fpath, staged_only=(mode == "staged"))
        all_errors.extend(content_errs)

    if all_errors:
        print("\n❌ [FCA-ENG-001 BLOQUEIO DE SEGURANÇA] Violação de segurança detectada!")
        print("Os seguintes arquivos ou conteúdos violam as regras de anonimização e integridade:\n")
        for err in all_errors:
            print(f"  • {err}")
        print("\nOperação do Git abortada para evitar vazamento de dados de produção.")
        print("Corrija ou remova os dados sensíveis antes de tentar novamente.\n")
        return 1

    print("✅ [FCA-ENG-001 Security Check] Nenhum dado sensível de produção detectado. Validação concluída com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
