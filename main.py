from agent_lc.agent import Agent
from agent_lc.prompts import LOG_ANALYZER_PROMPT, VIDEO_ANALYZER_PROMPT
from pathlib import Path
import logging
import time
import json
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

def get_screenshot_list(screenshots_dir: str) -> list:
    """Get list of screenshot files from directory"""
    try:
        screenshot_files = []
        for file in Path(screenshots_dir).glob("*.png"):
            # Parse filename to extract action type and phase
            # Example: click_start_1749284255204444500.png
            if "_start_" in file.name or "_end_" in file.name:
                screenshot_files.append(str(file))
        return sorted(screenshot_files)
    except Exception as e:
        logger.error(f"Error getting screenshot list: {str(e)}")
        return []

def get_latest_analysis(test_name: str, run_id: str) -> list:
    """Get the latest analysis from the analysis_logs directory"""
    try:
        log_dir = Path("analysis_logs")
        if not log_dir.exists():
            print(f"Analysis logs directory not found: {log_dir}")
            return []
            
        # Find analysis file for this test and run
        analysis_file = log_dir / f"video_analysis_{test_name}_{run_id}.json"
        if not analysis_file.exists():
            print(f"No analysis file found for test: {test_name} and run: {run_id}")
            return []
            
        print(f"\nFound existing analysis file: {analysis_file}")
        print(f"File last modified: {datetime.fromtimestamp(analysis_file.stat().st_mtime)}")
        
        # Read and return the analysis
        with open(analysis_file, 'r') as f:
            analysis_data = json.load(f)
            print(f"Successfully loaded analysis with {len(analysis_data)} screenshots")
            # Print first screenshot path to verify content
            if analysis_data:
                print(f"First screenshot in analysis: {analysis_data[0]['screenshot']}")
            return analysis_data
            
    except Exception as e:
        logger.error(f"Error getting latest analysis: {str(e)}")
        print(f"Error loading existing analysis: {str(e)}")
        return []

def save_analysis_to_log(analysis_data: list, test_name: str, run_id: str):
    """Save video analysis results to a log file in the analysis_logs folder"""
    try:
        # Create logs directory
        log_dir = Path("analysis_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename with test_id and run_id
        log_file = log_dir / f"video_analysis_{test_name}_{run_id}.json"
        
        # Save the analysis
        with open(log_file, 'w') as f:
            json.dump(analysis_data, f, indent=2)
            
        print(f"\nAnalysis saved to: {log_file}")
    except Exception as e:
        logger.error(f"Error saving analysis to log: {str(e)}")

def get_latest_log_file(test_name: str, run_id: str) -> str:
    """Get the most recent log file for a test run"""
    try:
        log_dir = Path("opt/log_files") / test_name / run_id
        if not log_dir.exists():
            raise FileNotFoundError(f"Log directory not found: {log_dir}")
            
        # Find all log files
        log_files = list(log_dir.glob("log_between_sender-user-rec-chat_manager_*.json"))
        if not log_files:
            raise FileNotFoundError(f"No log files found in {log_dir}")
            
        # Get the latest file
        latest_file = max(log_files, key=lambda x: x.stat().st_mtime)
        return str(latest_file)
            
    except Exception as e:
        logger.error(f"Error getting latest log file: {str(e)}")
        raise

def main(use_existing_analysis: bool = True):
    # Initialize the log analysis agent
    log_analysis_agent = Agent(prompt_text=LOG_ANALYZER_PROMPT, agent_type="log_analyzer")
    log_analysis_agent_executor = log_analysis_agent.get_agent_executor()
    
    # Initialize Groq client for cross-checking
    client = Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
    )
    
    # Test paths for search for a product, add to cart, and verify cart contents
    test_name = "Search_for_a_product,_add_to_cart,_and_verify_cart_contents"
    run_id = "run_20250607_134626"
    
    # Get the most recent log file
    try:
        log_path = get_latest_log_file(test_name, run_id)
        print(f"\nUsing log file: {log_path}")
    except Exception as e:
        print(f"\nError: {str(e)}")
        return
        
    screenshots_dir = f'opt/proofs/{test_name}/{run_id}/screenshots'
    
    # First, analyze the log file
    log_prompt = f"Analyze the log file at '{log_path}'"
    log_response = log_analysis_agent_executor.invoke({"input": log_prompt})
    print("\nLog Analysis Results:")
    print(log_response["output"])
    
    # Get screenshot analysis either from existing file or run new analysis
    if use_existing_analysis:
        print("\nAttempting to use existing screenshot analysis...")
        print(f"Looking for analysis file: video_analysis_{test_name}_{run_id}.json")
        screenshot_analysis = get_latest_analysis(test_name, run_id)
        if not screenshot_analysis:
            print("No existing analysis found. Running new analysis...")
            use_existing_analysis = False
        else:
            print(f"Successfully loaded existing analysis with {len(screenshot_analysis)} screenshots")
            # Verify the analysis data
            if screenshot_analysis:
                print("\nVerifying analysis data:")
                print(f"First screenshot path: {screenshot_analysis[0]['screenshot']}")
                print(f"First screenshot analysis length: {len(screenshot_analysis[0]['analysis'])} characters")
    
    if not use_existing_analysis:
        print("\nRunning new screenshot analysis...")
        # Initialize the video analysis agent
        video_analysis_agent = Agent(prompt_text=VIDEO_ANALYZER_PROMPT, agent_type="video_analyzer")
        video_analysis_agent_executor = video_analysis_agent.get_agent_executor()
        
        # Analyze each screenshot
        screenshot_files = get_screenshot_list(screenshots_dir)
        screenshot_analysis = []
        
        print("\nAnalyzing screenshots...")
        for screenshot_path in screenshot_files:
            try:
                # Create prompt for this screenshot
                screenshot_prompt = f"Analyze this screenshot: {screenshot_path}"
                
                # Run the video analysis agent with rate limiting
                max_retries = 3
                retry_delay = 60  # seconds
                
                for attempt in range(max_retries):
                    try:
                        response = video_analysis_agent_executor.invoke({
                            "input": screenshot_prompt
                        })
                        
                        # Store the analysis
                        screenshot_analysis.append({
                            "screenshot": screenshot_path,
                            "analysis": response["output"]
                        })
                        
                        print(f"Analyzed: {screenshot_path}")
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        if "rate_limit_exceeded" in str(e) and attempt < max_retries - 1:
                            print(f"Rate limit hit, waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            raise  # Re-raise if not rate limit or out of retries
                
            except Exception as e:
                logger.error(f"Error analyzing screenshot {screenshot_path}: {str(e)}")
                continue
        
        # Save new analysis to log file
        save_analysis_to_log(screenshot_analysis, test_name, run_id)
    
    # Print all screenshot analyses
    print("\nScreenshot Analysis Results:")
    for analysis in screenshot_analysis:
        print(f"\nScreenshot: {analysis['screenshot']}")
        print(analysis['analysis'])
        print("-" * 80)
    
    # Run cross-check analysis using Groq with DeepSeek model
    print("\nRunning cross-check analysis...")
    
    # Create a more detailed summary of the analyses
    log_summary = log_response['output']  # Use full log analysis
    
    # Extract key information from screenshot analyses
    screenshot_summary = []
    for analysis in screenshot_analysis:
        # Extract the key points from the structured analysis
        lines = analysis['analysis'].split('\n')
        current_state = next((line for line in lines if "Current State Description" in line), "")
        ui_elements = next((line for line in lines if "UI Elements and Their States" in line), "")
        interactions = next((line for line in lines if "Notable Interactions or Changes" in line), "")
        
        screenshot_summary.append({
            'screenshot': analysis['screenshot'],
            'current_state': current_state,
            'ui_elements': ui_elements,
            'interactions': interactions
        })
    
    print("\nPreparing cross-check data:")
    print(f"Log Analysis Length: {len(log_summary)} characters")
    print(f"Number of screenshots to cross-check: {len(screenshot_summary)}")
    
    cross_check_prompt = f'''Compare these analyses and identify genuine gaps:

    Log Analysis:
    {log_summary}
    
    Screenshot Analysis Summary:
    {json.dumps(screenshot_summary, indent=2)}
    
    Please provide a detailed analysis of:
    1. Genuine Missing Evidence: List only steps that are truly missing from screenshots, after verifying the actual content of each screenshot
    2. Actual Sequence Issues: Note only real sequence mismatches, based on the actual content of screenshots
    3. Real Verification Gaps: List only verification steps that are truly missing, after checking the screenshot analysis for verification evidence
    
    Important:
    - Check the actual content of each screenshot before declaring it missing
    - Don't assume a step is missing just because of the filename
    - Look for evidence in the analysis text
    - Consider implicit verifications in the screenshots
    - Focus on what's genuinely missing, not what might be missing
    
    Example of proper analysis:
    BAD: "No screenshots show login screens" (incorrect because we have screenshots showing username field filled)
    GOOD: "The login process is partially captured with username entry, but missing the password entry step"
    
    BAD: "No screenshots display the cart page" (incorrect because we have screenshots showing cart contents)
    GOOD: "Cart page is captured, but missing the transition from product page to cart page"
    
    Please be this precise in your analysis.'''
    
    try:
        print("\nSending cross-check request to DeepSeek...")
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a test analysis comparison assistant. Focus on identifying only genuine gaps by carefully analyzing the actual content of the screenshot analyses. Be precise and avoid making assumptions."},
                {"role": "user", "content": cross_check_prompt}
            ],
            model="deepseek-r1-distill-llama-70b",
            temperature=0.0
        )
        
        initial_analysis = chat_completion.choices[0].message.content
        print("\nInitial Cross-Check Results:")
        print(initial_analysis)
        
        # Extract only the conclusions after </think>
        conclusions = []
        found_think = False
        for line in initial_analysis.split('\n'):
            line = line.strip()
            if '</think>' in line:
                found_think = True
                continue
            if found_think and line:
                conclusions.append(line)
        
        print("\nConclusions to verify:")
        for conclusion in conclusions:
            print(conclusion)
        
        # Second verification pass
        print("\nPerforming verification of initial analysis...")
        verification_prompt = f'''Please verify these conclusions against the actual screenshot data:

        Conclusions to Verify:
        {chr(10).join(conclusions)}
        
        Screenshot Analysis Summary:
        {json.dumps(screenshot_summary, indent=2)}
        
        For each conclusion, verify if it's correct by checking the actual screenshot data.
        Format your response as:
        
        VERIFICATION RESULTS:
        
        1. Confirmed Conclusions (with evidence):
           - List conclusions that are accurate with screenshot evidence
           - Include the specific screenshot number/ID where the evidence was found
        
        2. Incorrect Conclusions (with actual evidence):
           - List conclusions that were wrong with screenshot evidence
           - Specify which screenshots were checked and what was actually found
           - If a step is missing, identify between which screenshots it should have occurred
        
        3. Final Summary:
           - List each missing step and specify:
             * Between which screenshots it should have occurred
             * What evidence we have before and after the missing step
             * Any partial evidence of the step being attempted
        
        Be extremely precise and only make claims you can verify with the actual data.'''
        
        # Using temperature=0 for deterministic, factual responses
        # This ensures consistent verification results and reduces hallucinations
        verification_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a verification assistant. Your job is to fact-check conclusions against the actual screenshot data. Be extremely precise and only make claims you can verify."},
                {"role": "user", "content": verification_prompt}
            ],
            model="deepseek-r1-distill-llama-70b",
            temperature=0.0
        )
        
        print("\nVerification Results:")
        print(verification_completion.choices[0].message.content)
        
    except Exception as e:
        logger.error(f"Error during cross-check analysis: {str(e)}")
        print(f"\nError during cross-check analysis: {str(e)}")
        print("Please check the logs for details.")

if __name__ == "__main__":
    main(use_existing_analysis=True)  # Default to using existing analysis
