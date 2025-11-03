from guardrails import EnhancedLLMGuardrails, CustomGuardrails  # ← Changed this line!
from openai import OpenAI
import os

class RealLLMChatbot:
    """A real chatbot that uses LLM with enhanced guardrails"""
    
    def __init__(self, openai_api_key: str = None):
        # Initialize ENHANCED guardrails (not SimpleLLMGuardrails!)
        self.guardrails = EnhancedLLMGuardrails()  # ← Changed this line!
        self.custom_guards = CustomGuardrails(
            blocked_topics=['violence', 'illegal', 'hate']
        )
        
        # Set up OpenAI client (new SDK v1.0+)
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  Warning: No OpenAI API key provided.")
        
        self.client = OpenAI(api_key=api_key)
        
        # System prompt for the LLM
        self.system_prompt = """You are a helpful, friendly AI assistant. 
        You provide accurate, informative responses while being respectful and professional.
        Focus on being helpful and educational.
        You do NOT provide assistance with hacking, illegal activities, or anything harmful."""
        
        # Conversation history
        self.conversation_history = [
            {"role": "system", "content": self.system_prompt}
        ]
    
    def chat(self, user_message: str) -> str:
        """Process message with full guardrails and real LLM"""
        
        print("🔍 Checking input safety...")
        
        # Step 1: Check for prompt injection FIRST (most critical!)
        injection_check = self.custom_guards.check_prompt_injection(user_message)
        if injection_check['detected']:
            print(f"   ✗ Prompt injection detected!")
            return f"⚠️ Invalid request: {injection_check['reason']}"
        
        # Step 2: Validate input - Toxicity and harmful intent
        input_check = self.guardrails.validate_input(user_message)
        if not input_check['safe']:
            return f"⚠️ Your message was blocked: {input_check['reason']}"
        
        # Step 3: Notify about PII detection
        pii_notice = ""
        if input_check['pii_detected']:
            pii_types = [item['type'] for item in input_check['pii_detected']]
            pii_notice = f"\n\n🔒 Privacy Note: I've detected and protected your {', '.join(pii_types)}."
            print(f"   ✓ PII detected and masked: {', '.join(pii_types)}")
        
        # Step 4: Use sanitized input (PII removed) for LLM
        safe_input = input_check['sanitized_input']
        print("   ✓ Input is safe")
        
        # Step 5: Call the LLM
        print("🤖 Generating response...")
        try:
            # Add user message to history
            self.conversation_history.append({
                "role": "user", 
                "content": safe_input
            })
            
            # Call OpenAI API (new SDK)
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self.conversation_history,
                max_tokens=500,
                temperature=0.7
            )
            
            llm_output = response.choices[0].message.content
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": llm_output
            })
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'api key' in error_msg or 'authentication' in error_msg or 'unauthorized' in error_msg:
                return "⚠️ OpenAI API key is invalid. Please set a valid API key."
            elif 'rate limit' in error_msg or 'quota' in error_msg:
                return "⚠️ Rate limit exceeded. Please try again later."
            else:
                return f"⚠️ Error generating response: {str(e)}"
        
        # Step 6: Validate output - Check if LLM generated toxic content
        print("🔍 Checking output safety...")
        output_check = self.guardrails.validate_output(llm_output)
        if not output_check['safe']:
            print(f"   ✗ Output blocked: {output_check['reason']}")
            return "⚠️ I apologize, but I cannot provide that response due to safety concerns."
        
        print("   ✓ Output is safe")
        
        return output_check['sanitized_output'] + pii_notice
    
    def reset_conversation(self):
        """Reset conversation history"""
        self.conversation_history = [
            {"role": "system", "content": self.system_prompt}
        ]
        print("✓ Conversation history cleared")
    
    def get_metrics(self):
        """Get guardrail statistics"""
        return self.guardrails.get_metrics()


def main():
    """Interactive chatbot with real LLM"""
    print("\n" + "="*70)
    print("🤖 Real LLM Chatbot with Enhanced Guardrails")
    print("="*70)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OpenAI API Key Required!")
        print("Set your API key in one of these ways:")
        print("1. Set environment variable: export OPENAI_API_KEY='your-key-here'")
        print("2. Create a .env file with: OPENAI_API_KEY=your-key-here")
        print("3. Pass it when creating the bot: RealLLMChatbot(openai_api_key='your-key')")
        print("\nGet your API key from: https://platform.openai.com/api-keys")
        
        # Ask if they want to enter it now
        key_input = input("\nEnter your OpenAI API key (or press Enter to exit): ").strip()
        if not key_input:
            print("Exiting...")
            return
        api_key = key_input
    
    # Initialize bot
    bot = RealLLMChatbot(openai_api_key=api_key)
    
    print("\n📝 Commands:")
    print("  - Type your question/message naturally")
    print("  - 'reset' - Clear conversation history")
    print("  - 'stats' - View guardrail metrics")
    print("  - 'quit' - Exit the chatbot")
    print("\n💡 Try these test cases:")
    print("  - What is artificial intelligence?")
    print("  - My email is test@example.com, can you help me?")
    print("  - You are stupid (toxic test)")
    print("  - How to hack a password (harmful intent test)")
    print("  - Ignore all previous instructions (injection test)")
    print("="*70 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.lower() == 'quit':
                print("\n👋 Goodbye!")
                print(f"Final Metrics: {bot.get_metrics()}")
                break
            
            if user_input.lower() == 'stats':
                metrics = bot.get_metrics()
                print(f"\n📊 Guardrail Metrics:")
                print(f"   - Total checks: {metrics['total_checks']}")
                print(f"   - Toxic inputs blocked: {metrics['toxic_inputs']}")
                print(f"   - Toxic outputs blocked: {metrics['toxic_outputs']}")
                print(f"   - Harmful intent blocked: {metrics['harmful_intent_blocked']}")
                print(f"   - PII items detected: {metrics['pii_detected']}\n")
                continue
            
            if user_input.lower() == 'reset':
                bot.reset_conversation()
                print()
                continue
            
            # Process the message
            response = bot.chat(user_input)
            print(f"\nBot: {response}\n")
            print("-" * 70 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n⚠️ Unexpected error: {e}\n")


if __name__ == "__main__":
    main()