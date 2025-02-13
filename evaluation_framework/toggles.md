# Stack toggles needed for evaluation script

**Per Model (claude 3.5 sonnet):**

There are 6 stack variations to run for every question. So given a question, golden truth etc. we need to capture results on these 6 different stacks.

1. Data upfront without tools (oracle prompt)
    1. With python
    2. Without python
2. With tools
    1. With python
    2. Without python
3. PromptQL
    1. With initial artifact (equivalent of oracle prompt)
    2. With tools (aka SQL engine)

**Automatic evaluation**

1. We need a way to configure an automatic evaluator for a question
2. Automatic evaluator will take output from a particular run, compare to golden truth and return a number between 0 and 1.
3. Automatic evaluation options:
  1. Exact answer evaluator: Exact match, 0 or 1. (for numbers, strings, JSON values etc)
  2. Numeric close answer evaluator with a zero cutoff: Score of 1 for exact and 0 for any answer further than cutoff. Scales between 1 and 0 exponentially.
  3. Exact prefix list evaluator: What percentage of the prefix of the list is correct
  4. Similar list evaluator: Penalize for how off the element is from its correct position. With a zero cutoff if the element is more than cutoff positions away from the right place.
