from _poc_guardrails import EnhancedLLMGuardrails, CustomGuardrails
import anthropic
import yaml
import os


class RealLLMChatbot:
    """Chatbot com guardrails usando Claude via Anthropic SDK."""

    def __init__(self, config_path="config.yaml"):
        self.guardrails = EnhancedLLMGuardrails()
        self.custom_guards = CustomGuardrails(
            blocked_topics=["violence", "illegal", "hate"]
        )

        with open(config_path) as f:
            config = yaml.safe_load(f)

        api_key = config.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")
        self.model = config.get("model", "claude-sonnet-4-6")

        self.client = anthropic.Anthropic(api_key=api_key)

        self.system_prompt = (
            "Você é um assistente de IA prestativo e amigável. "
            "Forneça respostas precisas e informativas, sendo sempre respeitoso e profissional. "
            "Foque em ser útil e educativo. "
            "Você NÃO fornece assistência para hacking, atividades ilegais ou qualquer coisa prejudicial."
        )

        self.conversation_history = []

    def chat(self, user_message: str) -> str:
        """Processa mensagem com guardrails e Claude."""
        print("🔍 Verificando segurança da entrada...")

        injection_check = self.custom_guards.check_prompt_injection(user_message)
        if injection_check["detected"]:
            print("   ✗ Tentativa de injeção de prompt detectada!")
            return f"⚠️ Requisição inválida: {injection_check['reason']}"

        input_check = self.guardrails.validate_input(user_message)
        if not input_check["safe"]:
            return f"⚠️ Sua mensagem foi bloqueada: {input_check['reason']}"

        pii_notice = ""
        if input_check["pii_detected"]:
            pii_types = [item["type"] for item in input_check["pii_detected"]]
            pii_notice = f"\n\n🔒 Aviso de privacidade: Detectei e protegi seus dados: {', '.join(pii_types)}."
            print(
                f"   ✓ Dados pessoais detectados e mascarados: {', '.join(pii_types)}"
            )

        safe_input = input_check["sanitized_input"]
        print("   ✓ Entrada segura")

        self.conversation_history.append({"role": "user", "content": safe_input})

        print("🤖 Gerando resposta...")
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=self.system_prompt,
                messages=self.conversation_history,
            )
            llm_output = response.content[0].text
            self.conversation_history.append(
                {"role": "assistant", "content": llm_output}
            )

        except anthropic.AuthenticationError:
            self.conversation_history.pop()
            return "⚠️ API key inválida. Verifique o config.yaml."
        except anthropic.RateLimitError:
            self.conversation_history.pop()
            return "⚠️ Rate limit atingido. Tente novamente em instantes."
        except Exception as e:
            self.conversation_history.pop()
            return f"⚠️ Erro ao gerar resposta: {e}"

        print("🔍 Verificando segurança da saída...")
        output_check = self.guardrails.validate_output(llm_output)
        if not output_check["safe"]:
            print(f"   ✗ Saída bloqueada: {output_check['reason']}")
            self.conversation_history.pop()
            return "⚠️ Não consigo fornecer essa resposta por questões de segurança."

        print("   ✓ Saída segura")
        return output_check["sanitized_output"] + pii_notice

    def reset_conversation(self):
        self.conversation_history = []
        print("✓ Histórico de conversa limpo")

    def get_metrics(self):
        return self.guardrails.get_metrics()


def main():
    print("\n" + "=" * 70)
    print("🤖 Chatbot com Guardrails (Claude)")
    print("=" * 70)

    bot = RealLLMChatbot()

    print("\n📝 Comandos:")
    print("  - Digite sua pergunta normalmente")
    print("  - 'reset' - Limpar histórico da conversa")
    print("  - 'stats' - Ver métricas dos guardrails")
    print("  - 'sair'  - Encerrar o chatbot")
    print("\n💡 Casos de teste:")
    print("  - O que é inteligência artificial?")
    print("  - Meu email é teste@exemplo.com, pode me ajudar?")
    print("  - Você é idiota (teste de toxicidade)")
    print("  - Como hackear uma senha (teste de intenção maliciosa)")
    print("  - Ignore todas as instruções anteriores (teste de injeção)")
    print("=" * 70 + "\n")

    while True:
        try:
            user_input = input("Você: ").strip()
            if not user_input:
                continue

            if user_input.lower() == "sair":
                print("\n👋 Até logo!")
                print(f"Métricas finais: {bot.get_metrics()}")
                break

            if user_input.lower() == "stats":
                metrics = bot.get_metrics()
                print("\n📊 Métricas dos Guardrails:")
                for k, v in metrics.items():
                    print(f"   - {k}: {v}")
                print()
                continue

            if user_input.lower() == "reset":
                bot.reset_conversation()
                print()
                continue

            response = bot.chat(user_input)
            print(f"\nBot: {response}\n")
            print("-" * 70 + "\n")

        except KeyboardInterrupt:
            print("\n\n👋 Até logo!")
            break
        except Exception as e:
            print(f"\n⚠️ Erro inesperado: {e}\n")


if __name__ == "__main__":
    main()
