import json
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel
import yaml
from datetime import datetime, timedelta

class Query(BaseModel):
    user_message: str

class QueryProcessor:
    def __init__(self, ai_assistant):
        self.assistant = ai_assistant
        
    def read_query(self, filepath: str) -> str:
        """Read and validate query from YAML file"""
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
                return Query.model_validate(data).user_message
        except Exception as e:
            raise Exception(f"Failed to read query file: {e}")
            
    def save_results(self, output_dir: str, run_info: dict, results: dict, elapsed_time: timedelta):
        """Save query results to output directory"""
        base_filename = f"output_top_{run_info['topk']}_last_{run_info['lastn']}_run_{run_info['run_index']}"
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Save main output
        with open(f"{output_dir}/{base_filename}.txt", 'w') as f:
            f.write(f"Query:\n{results['query']}\n\nResponse:\n{results['response']}")
            
        # Save conversation history
        with open(f"{output_dir}/{base_filename}.input", 'w') as f:
            json.dump(results['history'], f, indent=2, default=str)
            
        # Save API responses
        with open(f"{output_dir}/{base_filename}.output", 'w') as f:
            json.dump(self.assistant.api_responses, f, indent=2, default=str)

        with open(f"{output_dir}/{base_filename}.time", 'w') as f:
            f.write(f"{elapsed_time}")
    
    def should_skip(self, output_dir: str, run_info: dict) -> bool:
        """Check if output already exists"""
        output_file = Path(output_dir) / f"output_top_{run_info['topk']}_last_{run_info['lastn']}_run_{run_info['run_index']}.txt"
        return output_file.exists()
    
    async def process_query(self, query_template: str, run_info: dict) -> dict:
        """Process a single query with given parameters"""
        self.assistant.clear_history()
        query = query_template.format(k=run_info['topk'], n=run_info['lastn'])
        response = await self.assistant.process_query(query)
        
        return {
            'query': query,
            'response': response,
            'history': self.assistant.messages
        }
        
    async def run(self, input_filepath: str, output_dir: str):
        """Main processing loop"""
        try:
            query_template = self.read_query(input_filepath)
            
            for lastn in [20, 30]:
                for topk in [15]:
                # for topk in range(30, lastn+1, 5):
                    for run_index in range(1, 6):
                        run_info = {
                            'run_index': run_index,
                            'topk': topk,
                            'lastn': lastn
                        }
                        
                        print(f"Processing {input_filepath} run {run_index}, top {topk}, last {lastn}")
                        if self.should_skip(output_dir, run_info):
                            print(f"Skipping existing output for run {run_index}, top {topk}, last {lastn}")
                            continue
                            
                        start_time = datetime.now()
                        results = await self.process_query(query_template, run_info)
                        end_time =  datetime.now()
                        elapsed_time = end_time - start_time
                        print(f"TOTAL PROCESSING TIME: {elapsed_time} seconds")
                        
                        self.save_results(output_dir, run_info, results, elapsed_time)
                        
        except Exception as e:
            print(f"Error during processing: {e}")
        finally:
            self.assistant.close()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Process queries using AI Assistant')
    parser.add_argument('--input_filepath', help='Input query file path')
    parser.add_argument('--output_dir', help='Output directory path')
    args = parser.parse_args()
    
    from o1_eval import AIAssistant
    processor = QueryProcessor(AIAssistant())
    await processor.run(args.input_filepath, args.output_dir)

if __name__ == "__main__":
    asyncio.run(main())