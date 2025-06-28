import glob
import os

bash = "#!/bin/bash\nconda activate alpaca;\n"
for file in glob.glob('./skeleton/*.json'):
    print(file)
    # python planner.py --config {file}
    bash += f"python planner.py --config {file};\n"
# write the outputs to a sh script
with open(f"./run.sh", 'w', encoding='utf8') as outfile:
    outfile.write(bash)