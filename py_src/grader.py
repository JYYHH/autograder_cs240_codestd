import pandas as pd
import sys
from full_stack_parser import whole_check

grade_items = {
    "I.A",
    "I.C",
    "I.D",
    "XII.A",
    "XII.B",
    "XII.D",
}
def get_init_grade():
    return {item: True for item in grade_items}

class Grade():
    def __init__(self, username):
        self.data = get_init_grade()
        self.subtract = 0
        self.username = username
    def update_item(self, item_key):
        if item_key in self.data:
            self.data[item_key] = False
        else:
            print("Error: such rule not found!")
    def update_score(self):
        self.subtract = 0
        for item_key in self.data:
            if not self.data[item_key]:
                self.subtract -= 2

if __name__ == "__main__":
    # TODO(JHY): modify to handling students' submissions later
    src_ = sys.argv[1]
    grader = Grade("jin511")
    whole_check(src_, grader)
    print(grader.data)