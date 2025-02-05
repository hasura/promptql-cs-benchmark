import json

with open("answer_correct.json", "r") as f:
    correct = json.load(f)

with open("answer_test.json", "r") as f:
    check_me = json.load(f)

def print_json_differences(obj1, obj2, path=""):
    if isinstance(obj1, dict):
        for key in obj1:
            new_path = f"{path}.{key}" if path else key
            
            if key not in obj2:
                print(f"Missing in test: {new_path}")
                continue
                
            if type(obj1[key]) != type(obj2[key]):
                print(f"Type mismatch at {new_path}: {type(obj1[key])} vs {type(obj2[key])}")
                continue
                
            if isinstance(obj1[key], (dict, list)):
                print_json_differences(obj1[key], obj2[key], new_path)
            elif obj1[key] != obj2[key]:
                print(f"Value mismatch at {new_path}: {obj1[key]} vs {obj2[key]}")
        
        for key in obj2:
            if key not in obj1:
                new_path = f"{path}.{key}" if path else key
                print(f"Extra in test: {new_path}")
    
    elif isinstance(obj1, list):
        if len(obj1) != len(obj2):
            print(f"Length mismatch at {path}: {len(obj1)} vs {len(obj2)}")
        
        for i, (item1, item2) in enumerate(zip(obj1, obj2)):
            new_path = f"{path}[{i}]"
            if isinstance(item1, (dict, list)):
                print_json_differences(item1, item2, new_path)
            elif item1 != item2:
                print(f"Value mismatch at {new_path}: {item1} vs {item2}")

print(correct == check_me)
print_json_differences(correct, check_me)