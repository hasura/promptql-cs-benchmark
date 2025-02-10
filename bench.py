import json
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import yaml
from datetime import datetime, timedelta
from o1_eval import AIAssistant as OpenAIAssistant
from claude35_eval import AIAssistant as ClaudeAssistant


class InputVariations(BaseModel):
    name: str
    parameters: Dict[str, Any]

class InputConfig(BaseModel):
    promptql_prompt: str
    llm_prompt: str
    result_artifact_name: str
    variations: Optional[List[InputVariations]] = None
    repeat: Optional[int] = None
    
class QueryProcessor:
    def __init__(self, ai_assistant, output_dir):
        self.assistant = ai_assistant
        self.output_dir = output_dir
        
    def read_input(self, filepath: str) -> InputConfig:
        """Read and validate query from YAML file"""
        try:
            with open(filepath) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                return InputConfig.model_validate(data)
        except Exception as e:
            raise Exception(f"Failed to read query file: {e}")
            
    def save_results(self, variation_name: str, run_index: int, results: dict, elapsed_time: timedelta):
        """Save query results to output directory"""
        base_filename = f"{self.output_dir}/{variation_name}_run_{run_index}"
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Save main output
        with open(f"{base_filename}.result", 'w') as f:
            output = self.process_response(results)
            f.write(output)
            #json.dump(output,f, indent=2, default=str)
            
        # Save conversation history
        with open(f"{base_filename}.history", 'w') as f:
            json.dump(results['history'], f, indent=2, default=str)
            
        # Save API responses
        with open(f"{base_filename}.api", 'w') as f:
            json.dump(self.assistant.api_responses, f, indent=2, default=str)

        with open(f"{base_filename}.time", 'w') as f:
            f.write(f"{elapsed_time}")
    
    def should_skip(self, variation_name: str, run_index: int) -> bool:
        """Check if output already exists"""
        output_file = Path(self.output_dir) / f"{variation_name}_run_{run_index}.result"
        return output_file.exists()
    
    async def process_query(self, query: str) -> dict:
        """Process a single query with given parameters"""
        self.assistant.clear_history()
        # query = query_template.format(k=run_info['topk'], n=run_info['lastn'])
        response = await self.assistant.process_query(query)
        
        return {
            'query': query,
            'response': response,
            'history': self.assistant.messages
        }

    #TODO: Process the response to parse out the json output        
    def process_response(self, results: dict):
        return results['response']
        
    async def run(self, input_filepath: str, system: str):
        """Main processing loop"""
        try:
            input_config = self.read_input(input_filepath)
            # Determine query template based on system
            query_template = input_config.promptql_prompt if system == "promptql" else input_config.llm_prompt
            # Handle variations or default case
            variations = input_config.variations or [InputVariations(name="default", parameters={})]
        
            for variation in variations:
                # Format query with parameters (empty dict for default case)
                query = query_template
                for param_name, param_value in variation.parameters.items():
                    # We should do a direct replace. To the user it changes nothing
                    # Python template string formatting will break if the prompt includes any brackets {}
                    query = query.replace('{' + f'{param_name}' + '}', str(param_value))
                # Determine number of runs
                num_runs = input_config.repeat if input_config.repeat else 1
            
                for run_index in range(1, num_runs + 1):
                    # Log processing status
                    param_info = f" with params: {variation.parameters}" if variation.parameters else ""
                    print(f"Processing {input_filepath} run {run_index}{param_info}")
                
                    # Skip if output exists
                    if self.should_skip(variation.name, run_index):
                        print(f"Skipping existing output for run {run_index}{param_info}")
                        continue
                
                    # Process query and measure time
                    start_time = datetime.now()
                    results = await self.process_query(query=query)
                    elapsed_time = datetime.now() - start_time
                
                    print(f"TOTAL PROCESSING TIME: {elapsed_time} seconds")

                    final_answer = None
                    print(results["response"])
                    try:
                        final_answer = json.loads(results["response"])
                        results["response"] = final_answer
                    except json.decoder.JSONDecodeError:
                        print("TRYING AGAIN")
                        try:
                            final_answer = json.loads(results["response"].lstrip("```json").lstrip('```').rstrip('```'))
                            results["response"] = final_answer
                        except json.decoder.JSONDecodeError:
                            print("TRYING AGAIN - Ask LLM to fix")
                            fix_prompt = """Your previous response was not valid JSON. Please provide your complete response in valid JSON format.
                            Previous response: {previous_response}
                            
                            Format your response as a raw JSON object, without any markdown code blocks or additional text.""".format(
                                previous_response=results["response"]
                            )
                            
                            new_results = await self.process_query(fix_prompt)
                            try:
                                final_answer = json.loads(new_results["response"])
                                results["response"] = final_answer
                            except json.decoder.JSONDecodeError:
                                try:
                                    final_answer = json.loads(results["response"].lstrip("```json").lstrip('```').rstrip('```'))
                                    results["response"] = final_answer
                                except json.decoder.JSONDecodeError:
                                    print("Cannot process response")
                                    pass
                    finally:
                        if final_answer is None:
                            # MARK: TODO
                            # If final_answer is still None then we didn't get valid JSON
                            # So we should tell the assistant that it needs to fix it's output to be valid JSON.
                            # OR we can try other common validation patterns we see.
                            pass
                    self.save_results(variation.name, run_index, results, elapsed_time)
                
        except Exception as e:
            print(f"Error during processing: {e}\nError Type: {type(e)}")
        finally:
            self.assistant.close()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Process queries using AI Assistant')
    parser.add_argument('--input_filepath', help='Input query file path', required=True)
    parser.add_argument('--output_dir', help='Output directory path', required=True)
    parser.add_argument('--model', help='LLM to use', required=True)
    parser.add_argument('--system', help='System to evaluate', required=True)
    args = parser.parse_args()
    
    if args.system == "promptql":
        #TODO: Add promptql executor class which uses NL API
        processor = QueryProcessor(PromptQLAssistant(args.model), output_dir=f"{args.output_dir}/{args.system}")
    elif args.system == "llm":
        if args.model == "o1":
            processor = QueryProcessor(OpenAIAssistant("o1"), output_dir=f"{args.output_dir}/{args.system}/{args.model}")
        elif args.model == "o3-mini":
            processor = QueryProcessor(OpenAIAssistant("o3-mini"), output_dir=f"{args.output_dir}/{args.system}/{args.model}")
        elif args.model == "anthropic":
            processor = QueryProcessor(ClaudeAssistant(), output_dir=f"{args.output_dir}/{args.system}/{args.model}")
        else:
            print("unknown model")
            exit(1)
    else:
        print("uknown system")
        exit(1)
    
    await processor.run(args.input_filepath, args.system) # type: ignore

if __name__ == "__main__":
    asyncio.run(main())