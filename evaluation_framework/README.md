# Evaluation Framework

The goal of this framework is to help automate running different questions across implementations - promptql, o3-mini/o1/Claude 3.5 sonnet with/without python.

## Inputs

The dataset should be able to take a set of yaml files as input. The files should look like this:

````yaml
promptql_prompt: |
  prioritize {data} open tickets for me
  put the result in a artifact with identifier 'prioritized_support_tickets'
tool_calling_prompt: |
  prioritize {data} open tickets for me. first query query_support_tickets tool, then query query_control_plane_data tool. put your result in the following format:
  ```json
  [{
    "ticket_id": "123",
    "project_id": "456",
    "priority_score": 84.1,
  }]
  ```
expected_tool_calls:
 - query_support_tickets
 - query_control_plane_data
expected_promptql_artifact: prioritized_support_tickets
variations:
 - parameters:
     data: last 20
   expected_output:
    - ticket_id: 123
        project_id: 456
        priority_score: 84.1
 - data: last 20
 - data: last 30
 - data: last 40
 - data: all
````

## Running

The script should take the following inputs:

- `input_dir`: Directory of input files
- `output_dir`: Directory of where to write outputs
- `system`: System to benchmark, options are `promptql` or `tool_calling` or `tool_calling_python`
- `model`: Model to use, options are `claude`, `o1`, `o3-mini`
  
## Output

The output of the system should go into a file within `output_dir` with the name:

<input file name>-<system>-<model>-variation<variation-index>.yaml

### PromptQL

For PromptQL, we'll use the API (https://api.promptql.pro.hasura.io/redoc#operation/query_query_post) with `"stream": false`. 

```yaml
output: ... # The JSON output of the API
error: ... # If the API returned an error
answer: # The "data" field extracted from the artifact 
  - ticket_id: 123
    project_id: 456
    priority_score: 84.1
```

The artifact to use for the answer is the one mentioned in `expected_promptql_artifact` field of the input file.

### Tool Calling

For tool calling systems, the output should look like this:

```yaml
conversation:
    - user_message: blah
    - assistant_message: blah
    - tool_call:
        id: ...
        name: ...
        params: ...
        result: ...
    - tool_call:
        id: ...
        name: ...
        params: ...
        result: ...
    - assistant_message: blah
    - error: ... # This is in case a system error happens
answer: # extracted by parsing ```json ```
  - ticket_id: 123
    project_id: 456
    priority_score: 84.1
```

## Retry behavior

If the output file already exists, the behavior should be:

- For PromptQL, if output file indicates an error happened, retry it. Otherwise, ignore this input file and continue. 
- For tool calling systems:
  - if the output file indicates an error, continue from the point where the error happened reusing the state that was already available
  - if the output file contains a user_message as the last message, continue the conversation (this is for manually nudging these systems) 
  - if the output file contains an assistant message at the end, ignore this input file and continue.

## Automatic nudging

For tool calling systems, to account for the bad tool calling behavior of o1 and o3-mini, we will add automatic nudging to drive them to completion. This doesn't have to be perfect, we can resort to manual nudging if needed.

If the system was expecting some tool calls but not all those tool calls happened, nudge with: "actually use the <whatever tools did not get called> tools to get the answer"

## Evaluation

TODO: Figure out how to give automatic scores when comparing the system answer with the expected answer.