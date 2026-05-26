"""Legacy PoC kept for reference; superseded by guardrails/ package."""

from detoxify import Detoxify
import re
from typing import Dict, List


class EnhancedLLMGuardrails:
    """Guardrails aprimorados para LLMs com detecção de intenção maliciosa."""

    def __init__(self):
        print("Inicializando guardrails...")
        self.detoxify = Detoxify("original")
        print("✓ Detector de toxicidade carregado")

        self.pii_patterns = {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "telefone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
            "cartao_credito": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        }

        self.harmful_keywords = {
            "hacking": ["hack", "crack", "breach", "exploit", "break into", "invadir"],
            "senhas": ["password", "passwd", "login", "credential", "senha"],
            "ilegal": [
                "bomb",
                "explosive",
                "weapon",
                "kill",
                "murder",
                "bomba",
                "arma",
                "matar",
            ],
            "fraude": ["steal", "fraud", "scam", "phishing", "roubar", "golpe"],
        }

        self.metrics = {
            "entradas_toxicas": 0,
            "saidas_toxicas": 0,
            "pii_detectado": 0,
            "intencao_maliciosa_bloqueada": 0,
            "total_verificacoes": 0,
        }

    def verificar_intencao_maliciosa(self, texto: str) -> Dict:
        """Verifica intenção maliciosa usando correspondência de palavras-chave."""
        texto_lower = texto.lower()

        tem_hack = any(word in texto_lower for word in self.harmful_keywords["hacking"])
        tem_senha = any(word in texto_lower for word in self.harmful_keywords["senhas"])

        if tem_hack and tem_senha:
            return {
                "detected": True,
                "category": "hacking",
                "reason": "Intenção maliciosa detectada: tentativa de hackear senhas/contas",
            }

        frases_solicitacao = [
            "how to",
            "help me",
            "guide me",
            "teach me",
            "show me",
            "como",
            "me ajuda",
            "me ensina",
            "me mostra",
        ]
        if tem_hack and any(frase in texto_lower for frase in frases_solicitacao):
            return {
                "detected": True,
                "category": "hacking",
                "reason": "Intenção maliciosa detectada: solicitação de orientação para hacking",
            }

        frases_criacao = [
            "how to",
            "make",
            "create",
            "build",
            "como",
            "fazer",
            "criar",
            "construir",
        ]
        if any(word in texto_lower for word in self.harmful_keywords["ilegal"]):
            if any(frase in texto_lower for frase in frases_criacao):
                return {
                    "detected": True,
                    "category": "atividades_ilegais",
                    "reason": "Intenção maliciosa detectada: atividades ilegais",
                }

        frases_fraude = [
            "how to",
            "help me",
            "guide me",
            "como",
            "me ajuda",
            "me ensina",
        ]
        if any(word in texto_lower for word in self.harmful_keywords["fraude"]):
            if any(frase in texto_lower for frase in frases_fraude):
                return {
                    "detected": True,
                    "category": "fraude",
                    "reason": "Intenção maliciosa detectada: atividades fraudulentas",
                }

        return {"detected": False}

    def verificar_toxicidade(self, texto: str, threshold: float = 0.7) -> tuple:
        """Verifica se o texto contém conteúdo tóxico."""
        resultados = self.detoxify.predict(texto)

        scores_toxicos = {
            "toxicidade": resultados["toxicity"],
            "toxicidade_severa": resultados["severe_toxicity"],
            "obscenidade": resultados["obscene"],
            "ameaca": resultados["threat"],
            "insulto": resultados["insult"],
        }

        for categoria, score in scores_toxicos.items():
            if score > threshold:
                return True, categoria, score

        return False, None, 0.0

    def detectar_pii(self, texto: str) -> tuple:
        """Detecta e mascara dados pessoais (PII) no texto."""
        pii_detectado = []
        texto_mascarado = texto

        for tipo_pii, pattern in self.pii_patterns.items():
            matches = re.finditer(pattern, texto)
            for match in matches:
                pii_detectado.append(
                    {"type": tipo_pii, "value": match.group(), "position": match.span()}
                )
                texto_mascarado = texto_mascarado.replace(
                    match.group(), f"[{tipo_pii.upper()}_REDACTED]"
                )

        return texto_mascarado, pii_detectado

    def validate_input(self, entrada: str) -> Dict:
        """Valida a entrada do usuário antes de enviar ao LLM."""
        self.metrics["total_verificacoes"] += 1

        # Verificação 1: intenção maliciosa (primeiro!)
        check_intencao = self.verificar_intencao_maliciosa(entrada)
        if check_intencao["detected"]:
            self.metrics["intencao_maliciosa_bloqueada"] += 1
            return {
                "safe": False,
                "reason": f"{check_intencao['reason']} - Esta solicitação pode causar danos",
                "sanitized_input": None,
            }

        # Verificação 2: toxicidade
        toxico, categoria, score = self.verificar_toxicidade(entrada)
        if toxico:
            self.metrics["entradas_toxicas"] += 1
            return {
                "safe": False,
                "reason": f"Conteúdo tóxico detectado: {categoria} (score: {score:.2f})",
                "sanitized_input": None,
            }

        # Verificação 3: detectar e mascarar dados pessoais
        entrada_sanitizada, pii_encontrado = self.detectar_pii(entrada)
        if pii_encontrado:
            self.metrics["pii_detectado"] += len(pii_encontrado)

        return {
            "safe": True,
            "sanitized_input": entrada_sanitizada,
            "pii_detected": pii_encontrado,
        }

    def validate_output(self, saida_llm: str) -> Dict:
        """Valida a saída do LLM antes de exibir ao usuário."""
        check_intencao = self.verificar_intencao_maliciosa(saida_llm)
        if check_intencao["detected"]:
            return {
                "safe": False,
                "reason": f"Saída contém conteúdo prejudicial: {check_intencao['category']}",
                "sanitized_output": None,
            }

        toxico, categoria, score = self.verificar_toxicidade(saida_llm)
        if toxico:
            self.metrics["saidas_toxicas"] += 1
            return {
                "safe": False,
                "reason": f"LLM gerou conteúdo tóxico: {categoria}",
                "sanitized_output": None,
            }

        return {"safe": True, "sanitized_output": saida_llm}

    def get_metrics(self) -> Dict:
        """Retorna as métricas dos guardrails."""
        return self.metrics


class CustomGuardrails:
    """Regras de validação personalizadas adicionais."""

    def __init__(self, blocked_topics: List[str] = None):
        self.blocked_topics = [t.lower() for t in (blocked_topics or [])]

        self.injection_keywords = [
            # inglês
            "ignore all previous",
            "ignore previous",
            "disregard all",
            "disregard previous",
            "forget your instructions",
            "forget previous",
            "you are now",
            "new instructions",
            "system prompt",
            "reveal your prompt",
            "show your prompt",
            "bypass",
            # português
            "ignore todas as anteriores",
            "ignore as instruções anteriores",
            "desconsidere tudo",
            "desconsidere as instruções",
            "esqueça suas instruções",
            "esqueça as instruções",
            "esqueça o anterior",
            "você agora é",
            "você é agora",
            "novas instruções",
            "prompt do sistema",
            "revele seu prompt",
            "mostre seu prompt",
            "mostre suas instruções",
            "contornar",
        ]

    def check_prompt_injection(self, texto: str) -> Dict:
        """Detecta tentativas de injeção de prompt por palavras-chave."""
        texto_lower = texto.lower()

        for keyword in self.injection_keywords:
            if keyword in texto_lower:
                return {
                    "detected": True,
                    "keyword": keyword,
                    "reason": "Possível injeção de prompt detectada",
                }

        injection_patterns = [
            r"ignore.{0,20}(previous|all|above|anterior|todas)",
            r"disregard.{0,20}(previous|all|above)",
            r"forget.{0,20}instructions",
            r"esqueça.{0,20}(instruções|regras)",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, texto_lower):
                return {
                    "detected": True,
                    "pattern": pattern,
                    "reason": "Possível injeção de prompt detectada",
                }

        return {"detected": False}


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Testando Guardrails com Correspondência de Palavras-chave")
    print("=" * 60)

    guardrails = EnhancedLLMGuardrails()

    entradas_teste = [
        "O que é machine learning?",
        "Meu email é joao@exemplo.com",
        "Você é idiota",
        "Quero hackear a senha do meu amigo, me ajuda",
        "Como hackear uma senha",
        "Como crackear senhas",
        "Me ajuda a invadir uma conta",
        "Me ensina programação Python",
    ]

    for entrada in entradas_teste:
        print(f"\n{'=' * 60}")
        print(f"Entrada: {entrada}")
        resultado = guardrails.validate_input(entrada)

        if resultado["safe"]:
            print(f"✓ SEGURO - Sanitizado: {resultado['sanitized_input']}")
        else:
            print("✗ BLOQUEADO")
            print(f"  Motivo: {resultado['reason']}")

    print(f"\n{'=' * 60}")
    print(f"Métricas: {guardrails.get_metrics()}")
    print("=" * 60)
