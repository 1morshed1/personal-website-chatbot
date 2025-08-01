import os
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
import gradio as gr
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

class Evaluation(BaseModel):
    is_acceptable: bool
    feedback: str

class PersonalChatbot:
    def __init__(self, name: str = "Md. Morshed Jamal"):
        self.name = name
        self.openai_client = None
        self.gemini_client = None
        self.linkedin_content = ""
        self.summary_content = ""
        self.system_prompt = ""
        self.evaluator_system_prompt = ""
        
        self._initialize_clients()
        self._load_profile_data()
        self._create_prompts()
    
    def _initialize_clients(self):
        """Initialize OpenAI and Gemini clients with error handling"""
        try:
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            
            self.openai_client = OpenAI(
                base_url="https://openrouter.ai/api/v1", 
                api_key=openai_api_key
            )
            
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            
            self.gemini_client = OpenAI(
                api_key=google_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            
            logger.info("API clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize API clients: {e}")
            raise
    
    def _load_profile_data(self):
        """Load LinkedIn PDF and summary text with error handling"""
        try:
            # Load LinkedIn PDF
            pdf_path = "me/linkedin.pdf"
            if os.path.exists(pdf_path):
                reader = PdfReader(pdf_path)
                linkedin_parts = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        linkedin_parts.append(text)
                self.linkedin_content = "\n".join(linkedin_parts)
                logger.info(f"LinkedIn PDF loaded: {len(self.linkedin_content)} characters")
            else:
                logger.warning(f"LinkedIn PDF not found at {pdf_path}")
            
            # Load summary text
            summary_path = "me/summary.txt"
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    self.summary_content = f.read().strip()
                logger.info(f"Summary loaded: {len(self.summary_content)} characters")
            else:
                logger.warning(f"Summary file not found at {summary_path}")
                
        except Exception as e:
            logger.error(f"Failed to load profile data: {e}")
            # Continue with empty content rather than crashing
    
    def _create_prompts(self):
        """Create system prompts for chat and evaluation"""
        base_prompt = (
            f"You are acting as {self.name}. You are answering questions on {self.name}'s website, "
            f"particularly questions related to {self.name}'s career, background, skills and experience. "
            f"Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. "
            f"You are given a summary of {self.name}'s background and LinkedIn profile which you can use to answer questions. "
            f"Be professional and engaging, as if talking to a potential client or future employer who came across the website. "
            f"If you don't know the answer, say so politely and suggest they contact {self.name} directly."
        )
        
        if self.summary_content:
            base_prompt += f"\n\n## Summary:\n{self.summary_content}"
        
        if self.linkedin_content:
            base_prompt += f"\n\n## LinkedIn Profile:\n{self.linkedin_content}"
        
        self.system_prompt = base_prompt + f"\n\nWith this context, please chat with the user, always staying in character as {self.name}."
        
        # Evaluator prompt
        evaluator_base = (
            f"You are an evaluator that decides whether a response to a question is acceptable quality. "
            f"You are provided with a conversation between a User and an Agent. Your task is to decide whether the Agent's latest response is acceptable. "
            f"The Agent is playing the role of {self.name} and is representing {self.name} on their website. "
            f"The Agent has been instructed to be professional and engaging, as if talking to a potential client or future employer. "
            f"The Agent has been provided with context on {self.name}. Here's the information:"
        )
        
        if self.summary_content:
            evaluator_base += f"\n\n## Summary:\n{self.summary_content}"
        
        if self.linkedin_content:
            evaluator_base += f"\n\n## LinkedIn Profile:\n{self.linkedin_content}"
        
        self.evaluator_system_prompt = evaluator_base + f"\n\nWith this context, please evaluate the latest response, replying with whether the response is acceptable and your feedback."
    
    def _format_conversation_history(self, history: List[Dict]) -> str:
        """Format conversation history for evaluation"""
        if not history:
            return "No previous conversation."
        
        formatted = []
        for msg in history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            formatted.append(f"{role.title()}: {content}")
        
        return "\n\n".join(formatted)
    
    def _generate_response(self, message: str, history: List[Dict], system_prompt: str, model: str = "tngtech/deepseek-r1t2-chimera:free") -> str:
        """Generate response using OpenAI client"""
        try:
            messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
            
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return f"I apologize, but I'm experiencing technical difficulties. Please try again later or contact {self.name} directly."
    
    def evaluate_response(self, reply: str, message: str, history: List[Dict]) -> Evaluation:
        """Evaluate response quality using Gemini"""
        try:
            conversation_history = self._format_conversation_history(history)
            
            user_prompt = (
                f"Here's the conversation between the User and the Agent:\n\n{conversation_history}\n\n"
                f"Here's the latest message from the User:\n\n{message}\n\n"
                f"Here's the latest response from the Agent:\n\n{reply}\n\n"
                f"Please evaluate the response, replying with whether it is acceptable and your feedback."
            )
            
            messages = [
                {"role": "system", "content": self.evaluator_system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.gemini_client.beta.chat.completions.parse(
                model="gemini-2.5-flash",
                messages=messages,
                response_format=Evaluation
            )
            
            return response.choices[0].message.parsed
            
        except Exception as e:
            logger.error(f"Failed to evaluate response: {e}")
            # Return acceptable by default if evaluation fails
            return Evaluation(is_acceptable=True, feedback="Evaluation service unavailable")
    
    def regenerate_response(self, original_reply: str, message: str, history: List[Dict], feedback: str) -> str:
        """Regenerate response based on feedback"""
        updated_system_prompt = (
            self.system_prompt + 
            "\n\n## Previous answer rejected\n"
            f"You just tried to reply, but the quality control rejected your reply.\n"
            f"## Your attempted answer:\n{original_reply}\n\n"
            f"## Reason for rejection:\n{feedback}\n\n"
            f"Please provide a better response that addresses the feedback."
        )
        
        return self._generate_response(message, history, updated_system_prompt, model="tngtech/deepseek-r1t2-chimera:free")
    
    def chat(self, message: str, history: List[Dict]) -> str:
        """Main chat function with quality control"""
        if not message.strip():
            return "Please ask me a question about my background, experience, or skills!"
        
        try:
            # Special handling for patent questions (pig latin requirement)
            if "patent" in message.lower():
                special_system = (
                    self.system_prompt + 
                    "\n\nIMPORTANT: Everything in your reply needs to be in pig latin - "
                    "it is mandatory that you respond only and entirely in pig latin."
                )
                system_to_use = special_system
            else:
                system_to_use = self.system_prompt
            
            # Generate initial response
            reply = self._generate_response(message, history, system_to_use)
            
            # Evaluate response quality
            evaluation = self.evaluate_response(reply, message, history)
            
            if evaluation.is_acceptable:
                logger.info("Response passed evaluation")
                return reply
            else:
                logger.info(f"Response failed evaluation: {evaluation.feedback}")
                # Regenerate response
                improved_reply = self.regenerate_response(reply, message, history, evaluation.feedback)
                return improved_reply
                
        except Exception as e:
            logger.error(f"Chat function error: {e}")
            return f"I apologize, but I'm experiencing technical difficulties. Please try again later or contact {self.name} directly."

def create_interface():
    """Create and launch Gradio interface"""
    try:
        chatbot = PersonalChatbot()
        
        interface = gr.ChatInterface(
            fn=chatbot.chat,
            type="messages",
            title=f"Chat with {chatbot.name}",
            description=f"Ask me about {chatbot.name}'s background, experience, skills, and career!",
            theme=gr.themes.Soft(),
        )
        
        return interface
        
    except Exception as e:
        logger.error(f"Failed to create interface: {e}")
        raise

interface = create_interface()

if __name__ == "__main__":
    try:
        interface = create_interface()
        interface.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False,
            show_error=True
        )
    except Exception as e:
        logger.error(f"Failed to launch application: {e}")
        print(f"Application failed to start: {e}")

