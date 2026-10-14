"""Controles condicionais para skills de arquitetura e Carrier."""
from __future__ import annotations

import re

from specialized_controls import _finding


def analyze_hld(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".pdf", ".docx", ".txt", ".md"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:hld|high\s+level\s+design|arquitetura\s+(?:de\s+)?alto\s+n[ií]vel)\b", doc["name"] + "\n" + text, re.I)
        if not trigger:
            continue
        has_visual = any(d.get("ext") in (".png", ".jpg", ".jpeg", ".svg", ".drawio", ".bmp") for d in documents)
        checks = [
            ("HLD-ESCOPO", r"\b(?:objetivo|escopo)\b", "Objetivo ou escopo da arquitetura não identificado", "O HLD não apresenta referência explícita a objetivo ou escopo.", "Não é possível delimitar a responsabilidade do desenho arquitetural."),
            ("HLD-TOPOLOGIA", r"\b(?:topologia|diagrama|arquitetura|componente)\b", "Topologia ou componentes da arquitetura não identificados", "O HLD não descreve topologia, diagrama ou componentes de forma recuperável.", "A composição e os fluxos da solução não podem ser rastreados."),
            ("HLD-RNF", r"\b(?:disponibilidade|desempenho|escalab|seguran[cç]a|requisito\s+n[aã]o\s+funcional)\b", "Requisitos não funcionais não identificados", "O HLD não contém requisito não funcional recuperável de disponibilidade, desempenho, escalabilidade ou segurança.", "A validação da arquitetura contra atributos de qualidade fica incompleta."),
            ("HLD-DEPENDENCIA", r"\b(?:premissa|depend[eê]ncia|restri[cç][aã]o)\b", "Premissas, dependências ou restrições não identificadas", "O HLD não explicita premissas, dependências externas ou restrições conhecidas.", "Riscos de integração e limites de escopo podem permanecer ocultos."),
        ]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="HLD / Arquitetura", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta" if rule == "HLD-RNF" else "Média", prio="P1" if rule == "HLD-RNF" else "P2"))
        if not has_visual and not re.search(r"\b(?:figura|diagrama)\b", text, re.I):
            findings.append(_finding("HLD-DIAGRAMA", "Diagrama de alto nível não localizado no lote", doc, trigger, category="HLD / Arquitetura", finding_type="Lacuna", fact="Não foi localizado arquivo visual nem referência textual a diagrama no HLD.", impact="A topologia de alto nível não pode ser conferida visualmente.", crit="Média", prio="P2"))
    return findings


def analyze_carrier(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        text = doc.get("text", "")
        if not re.search(r"\b(?:dw?dm|dark\s+fiber|fibra\s+apagada|mpls|l[23]vpn|peering|ixp|pni|bgp|sd-?wan|dcn|route\s+reflector)\b", text, re.I):
            continue
        checks = [
            (r"\b(?:dw?dm|dark\s+fiber|fibra\s+apagada)\b", "CAR-FIBRA", r"\b(?:otdr|atenua[cç][aã]o|dB/km|osnr|span\s+budget)\b", "Parâmetros de fibra ou óptica não identificados", "O escopo óptico não explicita parâmetro de atenuação, ensaio OTDR, OSNR ou orçamento de enlace.", "A validação de viabilidade e aceite do enlace óptico fica incompleta."),
            (r"\b(?:bgp|peering|ixp|pni|route\s+reflector)\b", "CAR-BGP", r"\b(?:rpki|max-?prefix|bogon|flowspec|rtbh)\b", "Controles de segurança de roteamento BGP não identificados", "O escopo BGP/peering não referencia RPKI, max-prefix, filtragem de bogons, Flowspec ou RTBH.", "A política de proteção do roteamento não pode ser verificada."),
            (r"\b(?:l2vpn|l3vpn|p2p|mpls)\b", "CAR-SERVICO", r"\b(?:mtu|jumbo|qos|h-?qos|vlan|vrf)\b", "Parâmetros de serviço de transporte não identificados", "O escopo de transporte não explicita MTU, QoS, VLAN ou VRF.", "O comportamento e a segmentação do serviço podem ficar ambíguos."),
            (r"\b(?:sd-?wan)\b", "CAR-SDWAN", r"\b(?:ipsec|dtls|criptograf|controller|controladora|failover)\b", "Controles de SD-WAN não identificados", "O escopo SD-WAN não explicita criptografia, controladora ou failover.", "A segurança e a continuidade do overlay não podem ser confirmadas."),
            (r"\b(?:dcn|out-?of-?band|oob|ger[eê]ncia)\b", "CAR-DCN", r"\b(?:snmpv3|gnmi|telemetr|oob|out-?of-?band)\b", "Gerência e observabilidade DCN não identificadas", "O escopo DCN/gerência não referencia telemetria, SNMPv3 ou rede OOB.", "A segregação e a observabilidade operacional não podem ser verificadas."),
        ]
        for pattern, rule, required, title, fact, impact in checks:
            trigger = re.search(pattern, text, re.I)
            if trigger and not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="Carrier Telecom & DCN", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta", prio="P1"))
    return findings


def analyze_integrations(documents: list[dict]) -> list[dict]:
    """Verificações documentais para interfaces que o próprio lote declara."""
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".pdf", ".docx", ".txt", ".md"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:api|rest|soap|webhook|esb|barramento|kafka|integra[cç][aã]o)\b", text, re.I)
        if not trigger:
            continue
        checks = [
            ("INT-CONTRATO", r"\b(?:endpoint|uri|url|opera[cç][aã]o|m[eé]todo\s+(?:get|post|put|delete)|wsdl)\b", "Contrato de interface não identificado", "O escopo de integração não explicita endpoint, operação, método HTTP ou WSDL.", "A implementação e o teste da interface não possuem contrato técnico recuperável."),
            ("INT-SEGURANCA", r"\b(?:oauth|token|autentica[cç][aã]o|autoriza[cç][aã]o|mtls|certificado|api[ -]?key)\b", "Autenticação ou autorização da integração não identificada", "O escopo de integração não explicita mecanismo de autenticação ou autorização.", "O controle de acesso da troca de dados não pode ser verificado."),
            ("INT-ERRO", r"\b(?:erro|falha|retry|retentativa|timeout|idempot[eê]ncia|c[oó]digo\s+(?:http|de\s+retorno))\b", "Tratamento de falhas da integração não identificado", "O escopo de integração não documenta tratamento de erro, timeout, retentativa ou idempotência.", "Falhas de comunicação podem produzir comportamento divergente ou perda de rastreabilidade."),
            ("INT-DADOS", r"\b(?:payload|campo|mapeamento|schema|json|xml|atributo|dado)\b", "Modelo ou mapeamento de dados não identificado", "O escopo de integração não explicita payload, schema ou mapeamento de campos.", "A semântica e a transformação dos dados trocados permanecem ambíguas."),
        ]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="Integrações / APIs", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta", prio="P1"))
    return findings


def analyze_lgpd(documents: list[dict]) -> list[dict]:
    """Lacunas documentais de privacidade, sem emitir interpretação jurídica."""
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".pdf", ".docx", ".txt", ".md"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:lgpd|dados\s+pessoais|cpf|rg|biom[eé]tric|dados\s+de\s+sa[uú]de|anpd|dpo|privacidade|titular(?:es)?)\b", text, re.I)
        if not trigger:
            continue
        checks = [
            ("LGPD-FINALIDADE", r"\b(?:finalidade|prop[oó]sito)\b", "Finalidade do tratamento não identificada", "Há referência a dados pessoais, mas a finalidade do tratamento não foi localizada.", "A aderência do tratamento ao escopo documentado não pode ser avaliada."),
            ("LGPD-BASE", r"\b(?:base\s+legal|art(?:igo)?\.?\s*(?:7|11)|consentimento|leg[ií]timo\s+interesse|obriga[cç][aã]o\s+legal)\b", "Base legal do tratamento não identificada", "Há referência a dados pessoais, mas não foi localizada base legal ou referência aos arts. 7º/11 da LGPD.", "O ponto deve ser encaminhado ao DPO/Jurídico para avaliação competente."),
            ("LGPD-DIREITOS", r"\b(?:direito(?:s)?\s+do(?:s)?\s+titular|acesso|corre[cç][aã]o|exclus[aã]o|canal\s+de\s+atendimento)\b", "Atendimento aos direitos dos titulares não identificado", "Não foi localizado mecanismo de acesso, correção, exclusão ou canal para o titular.", "A resposta a solicitações de titulares não pode ser rastreada."),
            ("LGPD-INCIDENTE", r"\b(?:incidente|viola[cç][aã]o|notifica[cç][aã]o\s+(?:à|a)\s+anpd|comunica[cç][aã]o\s+de\s+incidente)\b", "Notificação de incidente de privacidade não identificada", "Não foi localizado procedimento de tratamento ou notificação de incidente de privacidade.", "A reação a incidentes envolvendo dados pessoais pode permanecer indefinida."),
            ("LGPD-RETENCAO", r"\b(?:reten[cç][aã]o|prazo\s+de\s+guarda|elimina[cç][aã]o|descarte)\b", "Prazo de retenção ou descarte não identificado", "Não foi localizado prazo de retenção, eliminação ou descarte de dados pessoais.", "O ciclo de vida dos dados não pode ser conferido."),
        ]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="LGPD / Privacidade", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta", prio="P1"))
    return findings


def analyze_cloud(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".pdf", ".docx", ".txt", ".md"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:cloud|nuvem|aws|azure|gcp|openstack|kubernetes|container|serverless|iaas|paas|saas)\b", text, re.I)
        if not trigger:
            continue
        checks = [
            ("CLD-IAM", r"\b(?:iam|identidade|acesso|menor\s+privil[eé]gio|rbac|mfa|autentica[cç][aã]o)\b", "Gestão de identidades e acessos Cloud não identificada", "O escopo Cloud não explicita IAM, RBAC, MFA ou princípio de menor privilégio.", "O controle de acesso aos recursos de nuvem não pode ser verificado."),
            ("CLD-RESILIENCIA", r"\b(?:backup|disaster\s+recovery|dr\b|rto|rpo|multi-?az|zona\s+de\s+disponibilidade|resili[eê]ncia)\b", "Resiliência ou recuperação Cloud não identificada", "O escopo Cloud não documenta backup, DR, RTO/RPO ou distribuição por zonas.", "A continuidade dos serviços em nuvem não pode ser confirmada."),
            ("CLD-OBS", r"\b(?:monitoramento|observabilidade|log(?:s)?|m[eé]trica|alerta|telemetria)\b", "Observabilidade Cloud não identificada", "O escopo Cloud não explicita logs, métricas, monitoramento ou alertas.", "A detecção e o diagnóstico de falhas ficam sem critério documentado."),
            ("CLD-REDE", r"\b(?:vpc|vnet|sub-?rede|segmenta[cç][aã]o|security\s+group|firewall|network)\b", "Segmentação de rede Cloud não identificada", "O escopo Cloud não documenta VPC/VNet, sub-redes, segmentação ou controles de rede.", "O isolamento de workloads e fluxos de rede não pode ser conferido."),
        ]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="Cloud / Arquitetura", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta", prio="P1"))
    return findings


def analyze_datacenter(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".pdf", ".docx", ".txt", ".md"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:data\s*center|datacenter|tier\s*(?:iii|iv|3|4)|ups|nobreak|pdu|gerador|rack|climatiza[cç][aã]o)\b", text, re.I)
        if not trigger:
            continue
        checks = [
            ("DC-REDUNDANCIA", r"\b(?:n\+1|2n|redund[aâ]ncia|tier\s*(?:iii|iv|3|4))\b", "Modelo de redundância do Datacenter não identificado", "O escopo de Datacenter não explicita N+1, 2N, Tier ou outro modelo de redundância.", "A disponibilidade da infraestrutura física não pode ser verificada."),
            ("DC-ENERGIA", r"\b(?:ups|nobreak|gerador|pdu|energia)\b", "Componentes de energia do Datacenter não identificados", "O escopo de Datacenter não documenta UPS/nobreak, gerador, PDU ou cadeia de energia.", "A continuidade elétrica não possui evidência documental recuperável."),
            ("DC-CLIMA", r"\b(?:climatiza[cç][aã]o|temperatura|umidade|hvac|crac)\b", "Climatização ambiental do Datacenter não identificada", "O escopo de Datacenter não documenta climatização, temperatura, umidade ou HVAC/CRAC.", "As condições ambientais dos equipamentos não podem ser avaliadas."),
            ("DC-MONITORAMENTO", r"\b(?:monitoramento|dcim|sensor|alerta|telemetria)\b", "Monitoramento de infraestrutura do Datacenter não identificado", "O escopo de Datacenter não explicita monitoramento, sensores, DCIM ou alertas.", "A supervisão da infraestrutura física não pode ser conferida."),
        ]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="Datacenter / Infraestrutura", finding_type="Lacuna", fact=fact, impact=impact, crit="Alta", prio="P1"))
    return findings


def run(documents: list[dict], skills: list[str]) -> list[dict]:
    result = []
    if "analisar-hld" in skills:
        result.extend(analyze_hld(documents))
    if "analisar-carrier" in skills:
        result.extend(analyze_carrier(documents))
    if "analisar-integracoes" in skills:
        result.extend(analyze_integrations(documents))
    if "analisar-lgpd" in skills:
        result.extend(analyze_lgpd(documents))
    if "analisar-cloud" in skills:
        result.extend(analyze_cloud(documents))
    if "analisar-datacenter" in skills:
        result.extend(analyze_datacenter(documents))
    return result


IMPLEMENTED_SKILLS = {"analisar-hld", "analisar-carrier", "analisar-integracoes", "analisar-lgpd", "analisar-cloud", "analisar-datacenter"}
