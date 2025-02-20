import json
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import re

def extract_messages(history_data: List) -> List[Dict]:
    """Extract relevant messages from history data"""
    messages = []

    for entry in history_data:
        # Handle promptql format
        if 'user_message' in entry:
            messages.append({
                'role': 'user',
                'content': entry['user_message'].get('text', '')
            })

        if 'assistant_actions' in entry:
            for action in entry['assistant_actions']:
                content_parts = []

                # Add message if present
                if action.get("message"):
                    content_parts.append(f"Message:\n{action['message']}")

                # Add plan if present
                if action.get("plan"):
                    content_parts.append(f"\nPlan:\n{action['plan']}")

                # Add code if present
                if action.get("code"):
                    content_parts.append(f"\nCode:\n{action['code']}")

                # Add code output if present
                if action.get("code_output"):
                    content_parts.append(f"\nCode Output:\n{action['code_output']}")

                # Add code error if present
                if action.get("code_error"):
                    content_parts.append(f"\nCode Error:\n{action['code_error']}")

                messages.append({
                    'role': 'assistant',
                    'content': '\n'.join(content_parts)
                })

        # Handle tool_calling and tool_calling_python format
        elif 'role' in entry:
            content = entry.get('content', [])
            
            # Case 1: When content is a list with tool results
            if isinstance(content, list) and len(content) > 0:
                # If first item is a dict with type 'tool_result'
                if isinstance(content[0], dict) and content[0].get('type') == 'tool_result':
                    tool_content = content[0].get('content', '')
                    try:
                        # Try to parse and pretty print JSON
                        json_obj = json.loads(tool_content)
                        formatted_json = json.dumps(json_obj, indent=2)
                        formatted_content = (
                            f'<div class="tool-result">'
                            f'<button class="collapsible">Show Tool Result +</button>'
                            f'<div class="content"><pre class="json">{formatted_json}</pre></div>'
                            f'</div>'
                        )
                    except json.JSONDecodeError:
                        # If not valid JSON, just wrap in pre tags
                        formatted_content = f'<div class="code-block"><pre>{tool_content}</pre></div>'
                    
                    messages.append({
                        'role': entry['role'],
                        'content': formatted_content
                    })
                # If items are strings starting with TextBlock or ToolUseBlock
                else:
                    formatted_content = []
                    for item in content:
                        if isinstance(item, str):
                            if "TextBlock" in item:
                                # Extract text content
                                text_match = re.search(r'text="([^"]*)"', item)
                                if text_match:
                                    formatted_content.append(f'<div class="text-block">{text_match.group(1)}</div>')
                            elif "ToolUseBlock" in item:
                                # Extract SQL query
                                sql_match = re.search(r"'sql': \"(.*?)(?<!\\)\"", item, re.DOTALL)
                                if sql_match:
                                    sql_content = sql_match.group(1).replace('\n', '<br>')
                                    formatted_content.append(
                                        f'<div class="sql-block">'
                                        f'<button class="collapsible">Show SQL Query +</button>'
                                        f'<div class="content"><pre>{sql_content}</pre></div>'
                                        f'</div>'
                                    )
                    
                    if formatted_content:
                        messages.append({
                            'role': entry['role'],
                            'content': '\n'.join(formatted_content)
                        })
            
            # Case 2: When content is a simple string
            elif isinstance(content, str):
                messages.append({
                    'role': entry['role'],
                    'content': f'<div class="text-block">{content}</div>'
                })

    return messages

def read_system_data(base_dir: str, model: str, system: str) -> Dict:
    """Read data for a specific system configuration"""
    path = Path(f"{base_dir}/{model}/{system}/retrieval")
    data = {}

    if not path.exists():
        return data

    # Read all files first
    for file in path.glob("last_10_run_*.history"):
        try:
            with open(file, 'r') as f:
                history = json.load(f)
                run_number = int(file.stem.split('_')[-1])  # Convert to int for proper sorting
                
                # Read the corresponding .time file
                time_file = file.with_suffix('.time')
                execution_time = ''
                if time_file.exists():
                    with open(time_file, 'r') as tf:
                        execution_time = tf.read().strip()

                # Read the corresponding .result file
                result_file = file.with_suffix('.result')
                result_content = 'No result file found'
                if result_file.exists():
                    with open(result_file, 'r') as rf:
                        result_content = rf.read().strip()

                if history:  # Only process non-empty history files
                    data[run_number] = {
                        'messages': extract_messages(history),
                        'type': system,
                        'execution_time': execution_time,
                        'result': result_content
                    }
        except json.JSONDecodeError:
            print(f"Error reading file: {file}")
            continue

    # Convert to sorted dictionary
    return dict(sorted(data.items()))

def format_execution_time(time_str: str) -> str:
    """Convert execution time to human readable format with 2 decimal precision"""
    try:
        # Parse the time string (expected format: H:MM:SS.XXXXXX)
        if not time_str or time_str == 'N/A':
            return 'N/A'

        parts = time_str.split(':')
        if len(parts) != 3:
            return time_str

        hours, minutes, seconds = parts
        seconds, microseconds = seconds.split('.') if '.' in seconds else (seconds, '0')

        # Convert all to numbers
        hours = int(hours)
        minutes = int(minutes)
        seconds = int(seconds)
        microseconds = int(microseconds) if microseconds else 0

        # Calculate seconds with 2 decimal places from microseconds
        seconds_decimal = seconds + (microseconds / 1_000_000)

        # Format based on duration
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds_decimal:.2f}s"
    except (ValueError, IndexError):
        return time_str

def generate_html_content(data: Dict[str, Dict[str, Any]], model: str) -> str:
    """Generate HTML content from the data"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Model Comparison</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 20px; 
                background-color: #f5f5f5;
            }
            .container { 
                display: flex; 
                gap: 20px; 
                margin-bottom: 40px;
            }
            .system { 
                flex: 1; 
                border: 1px solid #ccc; 
                padding: 15px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .system-title {
                display: inline;
            }
            .execution-time {
                font-size: 16px;
                margin-left: 5px;
                display: inline;
            }
            .message { 
                margin: 10px 0; 
                padding: 10px; 
                border-radius: 5px; 
            }
            .user { 
                background-color: #f0f0f0; 
                border-left: 4px solid #007bff;
            }
            .assistant { 
                background-color: #e6f3ff; 
                border-left: 4px solid #28a745;
            }
            .section-title {
                font-weight: bold;
                margin-top: 10px;
                margin-bottom: 5px;
            }
            pre { 
                white-space: pre-wrap; 
                word-wrap: break-word; 
                margin: 5px 0;
            }
            h2, h3 { color: #333; }
            .timestamp { 
                color: #666; 
                font-style: italic; 
                margin-bottom: 20px;
            }
            .collapsible {
                background-color: #f8f9fa;
                cursor: pointer;
                padding: 10px;
                width: 100%;
                border: none;
                text-align: left;
                outline: none;
                margin-top: 5px;
                border-radius: 4px;
            }
            .active, .collapsible:hover {
                background-color: #e9ecef;
            }
            .content {
                padding: 0 18px;
                display: none;
                overflow: hidden;
                background-color: #f8f9fa;
                border-radius: 0 0 4px 4px;
            }
            /* Tab styles */
            .tabs {
                margin-top: 20px;
                margin-bottom: 20px;
                border-bottom: 1px solid #ddd;
            }
            .tab-button {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                border-bottom: none;
                padding: 10px 20px;
                cursor: pointer;
                margin-right: 5px;
                border-radius: 4px 4px 0 0;
            }
            .tab-button.active {
                background-color: #fff;
                border-bottom: 1px solid #fff;
                margin-bottom: -1px;
            }
            .tab-content {
                display: none;
            }
            .tab-content.active {
                display: block;
            }
            .result-section {
                margin-top: 20px;
                padding: 15px;
                background-color: #f8f9fa;
                border-left: 4px solid #6c757d;
                border-radius: 5px;
            }
            .result-section .section-title {
                color: #495057;
                font-size: 1.1em;
                margin-bottom: 10px;
            }
            .result-section pre {
                background-color: #fff;
                padding: 12px;
                border-radius: 4px;
                border: 1px solid #dee2e6;
                color: #212529;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            .title-container {
                display: flex;
                align-items: center;
                gap: 30px;
            }
            .back-link {
                text-decoration: none;
                color: #666;
                font-size: 14px;
            }
            .back-link:hover {
                color: #333;
            }
        </style>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                // Collapsible sections
                var coll = document.getElementsByClassName("collapsible");
                for (var i = 0; i < coll.length; i++) {
                    coll[i].addEventListener("click", function() {
                        this.classList.toggle("active");
                        var content = this.nextElementSibling;
                        if (content.style.display === "block") {
                            content.style.display = "none";
                        } else {
                            content.style.display = "block";
                        }
                    });
                }

                // Tab functionality
                var tabButtons = document.getElementsByClassName("tab-button");
                for (var i = 0; i < tabButtons.length; i++) {
                    tabButtons[i].addEventListener("click", function() {
                        var runId = this.getAttribute("data-run");
                        
                        // Deactivate all tabs
                        var allTabs = document.getElementsByClassName("tab-button");
                        for (var j = 0; j < allTabs.length; j++) {
                            allTabs[j].classList.remove("active");
                        }
                        
                        // Deactivate all content
                        var allContent = document.getElementsByClassName("tab-content");
                        for (var j = 0; j < allContent.length; j++) {
                            allContent[j].classList.remove("active");
                        }
                        
                        // Activate selected tab and content
                        this.classList.add("active");
                        document.getElementById("run-" + runId).classList.add("active");
                    });
                }

                // Activate first tab by default
                if (tabButtons.length > 0) {
                    tabButtons[0].click();
                }
            });
        </script>
    </head>
    <body>
    """

    html += f"""<div class="title-container">
        <h1>With {model.upper()}</h1>
        <a href="index.html" class="back-link">&larr;Back</a>
    </div>"""
    html += f"<div class='timestamp'>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>"

    # Add tab buttons
    html += "<div class='tabs'>"
    for run_number in data.keys():
        html += f"<button class='tab-button' data-run='{run_number}'>Run {run_number}</button>"
    html += "</div>"

    # Add tab content
    for run_number, systems in data.items():
        html += f"<div id='run-{run_number}' class='tab-content'>"
        html += "<div class='container'>"

        for system_type in ['promptql', 'tool_calling', 'tool_calling_python']:
            html += f"<div class='system'>"
            if system_type in systems:
                execution_time = systems[system_type].get('execution_time', 'N/A')
                formatted_time = format_execution_time(execution_time)
                html += f"<h3 class='system-title'>{system_type}</h3> <span class='execution-time'>(Execution time: {formatted_time})</span>"
            else:
                html += f"<h3>{system_type}</h3>"

            if system_type in systems:
                system_data = systems[system_type]
                for message in system_data['messages']:
                    html += f"<div class='message {message['role']}'>"
                    html += f"<strong>{message['role'].title()}:</strong>"

                    if message["role"] == "assistant" and isinstance(message["content"], str):
                        if system_type == 'promptql':
                            sections = message["content"].split("\n")
                            current_section = None
                            current_content = []

                            for line in sections:
                                if line.strip() in ["Message:", "Plan:", "Code:", "Code Output:", "Code Error:"]:
                                    # Process previous section
                                    if current_section and current_content:
                                        if current_section in ["Code:", "Code Output:"]:
                                            html += f'<div class="section-title">{current_section}</div>'
                                            html += f'<button class="collapsible">Show {current_section.strip(":")} +</button>'
                                            html += f'<div class="content"><pre>{"".join(current_content)}</pre></div>'
                                        else:
                                            html += f'<div class="section-title">{current_section}</div>'
                                            html += f'<pre>{"".join(current_content)}</pre>'

                                    current_section = line.strip()
                                    current_content = []
                                else:
                                    current_content.append(line + "\n")

                            # Process the last section
                            if current_section and current_content:
                                if current_section in ["Code:", "Code Output:"]:
                                    html += f'<div class="section-title">{current_section}</div>'
                                    html += f'<button class="collapsible">Show {current_section.strip(":")} +</button>'
                                    html += f'<div class="content"><pre>{"".join(current_content)}</pre></div>'
                                else:
                                    html += f'<div class="section-title">{current_section}</div>'
                                    html += f'<pre>{"".join(current_content)}</pre>'
                        else:
                            html += f'<pre>{message["content"]}</pre>'
                    else:
                        html += f'<pre>{message["content"]}</pre>'

                    html += "</div>"

                # Add result section
                html += "<div class='result-section'>"
                html += "<div class='section-title'>Result:</div>"
                if 'result' in system_data and system_data['result']:
                    html += f'<pre>{system_data["result"]}</pre>'
                else:
                    html += "<pre>No result returned</pre>"
                html += "</div>"

            else:
                html += "<p>Run not found</p>"

            html += "</div>"

        html += "</div></div>"

    html += """
    </body>
    </html>
    """

    return html

def generate_index_html(models: List[str]) -> str:
    """Generate an index HTML page with links to all comparison pages"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Model Comparisons Index</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 20px; 
                background-color: #f5f5f5;
            }
            .container { 
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            .promptql {
                # color: #b6fc34;
            }
            .links {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            a {
                padding: 15px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                color: #007bff;
                text-decoration: none;
                transition: all 0.2s ease;
            }
            a:hover {
                background-color: #e9ecef;
                color: #0056b3;
                transform: translateY(-2px);
            }
            .timestamp { 
                color: #666; 
                font-style: italic; 
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Comparing <span class="promptql">PromptQL</span> vs Tool Calling vs Tool Calling with Python</h1>
            <div class="timestamp">Generated on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</div>
            <div class="links">
    """
    
    for model in models:
        html += f'            <a href="{model}_comparison.html">With {model.upper()}</a>\n'
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    return html

def main():
    base_dir = "score_based_prioritization"
    models = ["claude", "o1", "o3-mini"]
    systems = ["promptql", "tool_calling", "tool_calling_python"]
    
    # Create output directory
    os.makedirs('comparison_output', exist_ok=True)
    
    # Generate index page
    index_html = generate_index_html(models)
    with open('comparison_output/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)
    print("Generated index page: comparison_output/index.html")
    
    for model in models:
        try:
            # Create a dictionary to store all data for this model
            model_data = {}
            
            # Read data for each system
            for system in systems:
                system_data = read_system_data(base_dir, model, system)
                
                # Add system data to runs
                for run_number, data in system_data.items():
                    if run_number not in model_data:
                        model_data[run_number] = {}
                    model_data[run_number][system] = data
            
            if model_data:
                # Generate HTML
                html_content = generate_html_content(model_data, model)
                
                # Write HTML file
                output_file = f'comparison_output/{model}_comparison.html'
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                    
                print(f"Generated comparison for {model}: {output_file}")
            else:
                print(f"No data found for {model}")
            
        except Exception as e:
            print(f"Error processing {model}: {str(e)}")

if __name__ == "__main__":
    main()
