from guardrails.compliance.rubric import BENIGN_FEW_SHOTS, FEW_SHOTS, RULES


def build_system_prompt() -> str:
    lines: list[str] = []

    lines.append("Você é um auditor de compliance bancário BACEN/CVM. Avalie o output do chatbot contra as regras abaixo.")
    lines.append("")

    lines.append("REGRAS (R1-R5):")
    for i, (rule_id, description) in enumerate(RULES.items(), start=1):
        lines.append(f"{i}. {rule_id}: {description}")
    lines.append("")

    lines.append("EXEMPLOS:")
    for rule_id, shots in FEW_SHOTS.items():
        for shot in shots:
            lines.append(f'Output: "{shot["output"]}" → verdict={shot["verdict"]}, rule_violated={shot["rule_violated"]}, reasoning="{shot["reasoning"]}"')
    for shot in BENIGN_FEW_SHOTS:
        lines.append(f'Output: "{shot["output"]}" → verdict={shot["verdict"]}, rule_violated={shot["rule_violated"]}, reasoning="{shot["reasoning"]}"')
    lines.append("")

    lines.append("Use a tool `emit_verdict` para responder. NÃO emita texto livre. `reasoning` em PT-BR, máximo 2 frases.")

    return "\n".join(lines)
