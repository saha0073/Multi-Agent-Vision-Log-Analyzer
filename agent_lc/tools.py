from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from typing import Annotated, Dict, List
import json
from pathlib import Path
import logging
import base64
from PIL import Image
from io import BytesIO
import re
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class Tools:
    @staticmethod
    def setup_tool_log_analyzer():
        return [Tools.extract_steps_from_log]

    @staticmethod
    def setup_tool_video_analyzer():
        return [Tools.analyze_screenshot]

    @staticmethod
    def setup_tool_cross_check():
        tavily_tool = TavilySearchResults(max_results=5)
        tools = [tavily_tool]
        return tools# For cross-check, we don't need any tools as we'll use direct LLM calls


    @tool
    def extract_steps_from_log(
        log_path: Annotated[str, "Path to the log file to analyze"],
    ) -> str:
        """Extract steps from a log file. The log file should be a JSON file containing the test execution steps.
        This tool will parse the log file and return a structured list of steps with their descriptions."""
        try:
            # Read the log file
            with open(log_path, 'r') as f:
                log_content = f.read()
            
            # Parse the log content
            try:
                log_data = json.loads(log_content)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON format in log file: {log_path}"
            
            # Extract steps
            steps = []
            if isinstance(log_data, dict) and "user_proxy_agent" in log_data:
                messages = log_data["user_proxy_agent"]
                
                # Find the first planner_agent message with a plan
                for msg in messages:
                    if msg.get("name") == "planner_agent" and isinstance(msg.get("content"), dict):
                        content = msg["content"]
                        if "plan" in content:
                            # Extract steps from the plan
                            plan_lines = content["plan"].split("\n")
                            for line in plan_lines:
                                if line.strip() and line[0].isdigit():
                                    # Extract step number and description
                                    parts = line.split(".", 1)
                                    if len(parts) == 2:
                                        step_num = parts[0].strip()
                                        description = parts[1].strip()
                                        steps.append({
                                            "step_number": int(step_num),
                                            "description": description
                                        })
                            break  # We only need the first plan
            
            if not steps:
                return "No steps found in the log file."
            
            # Format the output
            output = []
            output.append(f"Found {len(steps)} steps:")
            for step in steps:
                output.append(f"{step['step_number']}. {step['description']}")
            
            return "\n".join(output)
            
        except Exception as e:
            logger.error(f"Error extracting steps from log: {str(e)}")
            return f"Error extracting steps from log: {str(e)}"

    @tool
    def analyze_screenshot(
        screenshot_path: Annotated[str, "Path to the screenshot file to analyze"],
    ) -> str:
        """Analyze a screenshot and verify if it matches the expected action based on the filename.
        This tool takes a screenshot path, reads the image, and verifies if the image content matches
        the action described in the filename."""
        try:
            # Parse the filename to extract action type and phase
            # Example: click_start_1749284255204444500.png
            filename = Path(screenshot_path).name
            match = re.match(r"(\w+)_(start|end)_(\d+)\.png", filename)
            if not match:
                return f"Error: Invalid screenshot filename format: {filename}"
            
            action_type, phase, timestamp = match.groups()
            
            # Read and process the image
            try:
                with Image.open(screenshot_path) as img:
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    # Resize image to reduce size
                    img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                    
                    # Convert to base64
                    img_byte_arr = BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=85)
                    img_byte_arr = img_byte_arr.getvalue()
                    base64_image = base64.b64encode(img_byte_arr).decode()
            except Exception as e:
                return f"Error processing image: {str(e)}"
            
            # Initialize GPT-4 Vision model
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return "Error: OPENAI_API_KEY environment variable is not set"
                
            vision_model = ChatOpenAI(
                model_name="gpt-4o",
                temperature=0.7,
                api_key=api_key
            )
            
            # Create the prompt for image analysis
            prompt = f"""Analyze this screenshot and provide a detailed description of what you see.
            The filename suggests this might be related to a {action_type} action, but focus on describing the actual content.
            
            Please provide:
            1. A clear description of the current state and UI elements
            2. Any visible user interactions or system responses
            3. The overall context and layout of the interface
            4. Any notable changes or transitions visible
            5. A summary of what's happening in this moment
            
            Focus on describing what you actually see, using the filename only as general context."""
            
            # Make the API call
            try:
                response = vision_model.invoke([
                    {"role": "system", "content": "You are a screenshot analyzer that verifies if images match expected actions."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ])
                
                return response.content
                
            except Exception as e:
                return f"Error calling GPT-4 Vision API: {str(e)}"
            
        except Exception as e:
            logger.error(f"Error analyzing screenshot: {str(e)}")
            return f"Error analyzing screenshot: {str(e)}"
