import json

with open("answer_correct.json", "r") as f:
    correct = json.load(f)

with open("answer_test.json", "r") as f:
    check_me = json.load(f)

print(correct == check_me)