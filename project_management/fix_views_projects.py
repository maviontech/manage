#!/usr/bin/env python
"""Fix views_projects.py by removing leftover code"""

with open('core/views_projects.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where the bad code starts (after PAGE_SIZE = 10)
fixed_lines = []
skip_mode = False

for i, line in enumerate(lines):
    if i < 12:  # Keep first 12 lines (imports + PAGE_SIZE)
        fixed_lines.append(line)
    elif line.strip().startswith('def '):  # Start of a function
        skip_mode = False
        fixed_lines.append(line)
    elif not skip_mode:
        # Check if this is the bad leftover code
        if 'member_id = request.session.get' in line and i < 50:
            skip_mode = True  # Start skipping
            continue
        fixed_lines.append(line)

# Write back
with open('core/views_projects.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("✓ Fixed views_projects.py")
