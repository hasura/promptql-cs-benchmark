import json
import textwrap
from typing import List, Dict
from colorama import init, Fore, Style
import argparse

# Initialize colorama for cross-platform colored output
init()

class ChatRenderer:
    def __init__(self, terminal_width: int = 80):
        self.terminal_width = terminal_width
        self.indent = "    "
        
    def wrap_text(self, text: str, initial_indent: str = "", subsequent_indent: str = "") -> str:
        """Wrap text to terminal width with proper indentation."""
        width = self.terminal_width - len(initial_indent)
        wrapped = textwrap.fill(
            text,
            width=width,
            initial_indent=initial_indent,
            subsequent_indent=subsequent_indent or initial_indent
        )
        return wrapped

    def render_code_block(self, code: str) -> str:
        """Render a code block with proper indentation and syntax."""
        if not code:
            return ""
        
        lines = code.split('\n')
        indented_code = '\n'.join(f"{self.indent}{line}" for line in lines)
        return f"{Fore.CYAN}{indented_code}{Style.RESET_ALL}"

    def render_message(self, role: str, content: str) -> str:
        """Render a message with proper formatting based on role."""
        role_color = Fore.GREEN if role == "User" else Fore.YELLOW
        header = f"{role_color}{role}:{Style.RESET_ALL}"
        
        if not content:  # Handle empty content
            return header
            
        content_lines = content.split('\n')
        wrapped_lines = [self.wrap_text(line, self.indent) for line in content_lines]
        return f"{header}\n{'\n'.join(wrapped_lines)}"

    def render_action(self, action: Dict) -> str:
        """Render an assistant action with all its components."""
        sections = []
        
        # Render message
        if action.get("message"):
            sections.append(self.wrap_text(action["message"], self.indent))

        # Render plan if present
        if action.get("plan"):
            sections.append(f"\n{Fore.BLUE}Plan:{Style.RESET_ALL}")
            plan_lines = action["plan"].split('\n')
            wrapped_plan = [self.wrap_text(line, self.indent) for line in plan_lines]
            sections.append('\n'.join(wrapped_plan))

        # Render code if present
        if action.get("code"):
            sections.append(f"\n{Fore.BLUE}Code:{Style.RESET_ALL}")
            sections.append(self.render_code_block(action["code"]))

        # Render code output if present
        if action.get("code_output"):
            sections.append(f"\n{Fore.BLUE}Code Output:{Style.RESET_ALL}")
            output_lines = action["code_output"].split('\n')
            wrapped_output = [self.wrap_text(line, self.indent) for line in output_lines]
            sections.append('\n'.join(wrapped_output))

        # Render code error if present
        if action.get("code_error"):
            sections.append(f"\n{Fore.RED}Code Error:{Style.RESET_ALL}")
            sections.append(self.wrap_text(str(action["code_error"]), self.indent))

        return "\n".join(sections)

    def render_conversation(self, data: List[Dict]) -> str:
        """Render the entire conversation."""
        output = []
        
        for item in data:
            # Render user message
            if "user_message" in item:
                output.append(self.render_message("User", item["user_message"]["text"]))
                output.append("")  # Add spacing

            # Render assistant actions
            if "assistant_actions" in item:
                for action in item["assistant_actions"]:
                    output.append(self.render_message("Assistant", ""))
                    output.append(self.render_action(action))
                output.append("")  # Add spacing

        return "\n".join(output)

def main():
    parser = argparse.ArgumentParser(description="Render chat JSON in terminal")
    parser.add_argument("file", help="JSON file to render")
    parser.add_argument("--width", type=int, default=80, help="Terminal width (default: 80)")
    args = parser.parse_args()

    try:
        with open(args.file, 'r') as f:
            data = json.load(f)
        
        renderer = ChatRenderer(args.width)
        print(renderer.render_conversation(data))
        
    except FileNotFoundError:
        print(f"{Fore.RED}Error: File {args.file} not found{Style.RESET_ALL}")
    except json.JSONDecodeError:
        print(f"{Fore.RED}Error: Invalid JSON file{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()