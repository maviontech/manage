"""
Test script to verify the date-based progress calculation
"""
from datetime import date, timedelta

def calculate_date_based_progress(start_date, end_date, current_date=None):
    """
    Calculate project progress percentage based on time elapsed between start and end dates.
    """
    if not start_date or not end_date:
        return 0.0
    
    if current_date is None:
        current_date = date.today()
    
    # If project hasn't started yet
    if current_date < start_date:
        return 0.0
    
    # If project is past due date
    if current_date >= end_date:
        return 100.0
    
    # Calculate progress based on days elapsed
    total_days = (end_date - start_date).days
    if total_days <= 0:
        return 100.0
    
    days_elapsed = (current_date - start_date).days
    progress = (days_elapsed / total_days) * 100
    
    return round(progress, 1)

# Test Case from the screenshot
print("=" * 60)
print("TEST CASE: Customer Support Chat Integration")
print("=" * 60)
start_date = date(2026, 1, 20)
due_date = date(2026, 1, 31)
today = date(2026, 1, 21)

total_days = (due_date - start_date).days
days_elapsed = (today - start_date).days
progress = calculate_date_based_progress(start_date, due_date, today)

print(f"Start Date:     {start_date.strftime('%b %d, %Y')}")
print(f"Due Date:       {due_date.strftime('%b %d, %Y')}")
print(f"Current Date:   {today.strftime('%b %d, %Y')}")
print(f"Total Days:     {total_days} days")
print(f"Days Elapsed:   {days_elapsed} day(s)")
print(f"Progress:       {progress}%")
print()

# Additional Test Cases
print("=" * 60)
print("ADDITIONAL TEST CASES")
print("=" * 60)

# Test Case 2: Multiple days passed
test_date_2 = date(2026, 1, 22)
progress_2 = calculate_date_based_progress(start_date, due_date, test_date_2)
days_elapsed_2 = (test_date_2 - start_date).days
print(f"\nDay 2 (Jan 22): {days_elapsed_2} days elapsed → {progress_2}%")

# Test Case 3: Multiple days passed
test_date_3 = date(2026, 1, 23)
progress_3 = calculate_date_based_progress(start_date, due_date, test_date_3)
days_elapsed_3 = (test_date_3 - start_date).days
print(f"Day 3 (Jan 23): {days_elapsed_3} days elapsed → {progress_3}%")

# Test Case 4: Halfway through
test_date_4 = date(2026, 1, 25)
progress_4 = calculate_date_based_progress(start_date, due_date, test_date_4)
days_elapsed_4 = (test_date_4 - start_date).days
print(f"Day 5 (Jan 25): {days_elapsed_4} days elapsed → {progress_4}%")

# Test Case 5: Project completion date
test_date_5 = due_date
progress_5 = calculate_date_based_progress(start_date, due_date, test_date_5)
print(f"Due Date (Jan 31): Project complete → {progress_5}%")

# Test Case 6: Before start date
test_date_6 = date(2026, 1, 19)
progress_6 = calculate_date_based_progress(start_date, due_date, test_date_6)
print(f"Before Start (Jan 19): Not started → {progress_6}%")

print("\n" + "=" * 60)
print("FORMULA: Progress = (Days Elapsed / Total Days) × 100")
print("=" * 60)
