from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.runnables.history import RunnableWithMessageHistory
from .tools import Tools  
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

class Agent:
    def __init__(self, prompt_text, agent_type):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_text),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        self.llm = ChatOpenAI(
            model_name="gpt-4o",  # Using the correct vision model
            temperature=0.7, 
            streaming=False,
            api_key=api_key
        )
        
        if agent_type == "log_analyzer":
            self.tools = Tools.setup_tool_log_analyzer() 
        elif agent_type == "video_analyzer":
            self.tools = Tools.setup_tool_video_analyzer() 
            # Update prompt template for video analyzer
        elif agent_type == "cross_check":
            self.tools = Tools.setup_tool_cross_check()
            
        print(agent_type, " : ", self.tools)

        self.agent = create_openai_tools_agent(
            self.llm.with_config({"tags": ["agent_llm"]}), self.tools, self.prompt
        )

    def get_agent_executor(self):
        return AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)

    