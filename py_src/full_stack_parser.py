import io
from pycparser import c_parser, c_ast
from pcpp import Preprocessor

undefined_type = {
    'bool',
    'FILE',
    # 'void',
}

# function transferring a list of objects to the list of the ids
def obj2id(li: list):
    return [id(x) for x in li]

# function to return a common prefix of 2 id list, corresponding to the LCA on a tree (each list is a path from root)
def LCA_common_prefix(li1: list, li2: list):
    if li1 == None: # for the first time, it's used
        return li2
    pos, len1, len2 = 0, len(li1), len(li2)
    while pos < len1 and pos < len2 and li1[pos] == li2[pos]:
        pos += 1
    return li1[: pos]

# function to compare 2 id lists
def is_equal(li1: list, li2: list):
    if li1 == None: # for a var which is never used after the definition
        return False
    return li1 == li2

# class for original source code, only to check for the constants
class MyPreprocessor(Preprocessor):
    # We override this function, to handle undefined var type (since we do not look into other headers)
    def expand_macros(self, tokens, expanding_from = []):
        for i in range(len(tokens)):
            if tokens[i].value in undefined_type:
                tokens[i].value = "int" # default type
        return super().expand_macros(tokens, expanding_from)

    # We override this function, to return None for all not found cases
    def on_include_not_found(self, is_system_include, curdir, includepath, io, directive = None):
        # print(f"Warning: Skipping missing include file '{includepath}'")
        return None  # Returning None tells pcpp to ignore it

# class for preprocessed source code
class VariableDefinitionChecker(c_ast.NodeVisitor):
    def __init__(self, header_len, grader):
        self.errors = []
        self.in_global = True
        self.in_param = False # whether an argument for functions
        self.type_def = False # whether in a type define
        self.decl_lines = {}  # line -> list of variable names
        self.grader = grader
        self.header_len = header_len
        self.var_name_dict_list = [{}] # act like a stack, and the top is the current compound's var_name_dict
                                       # ensure it's not empty at any point
        self.all_var_name_dict_list = [] # to save all the Compound's var dict, for the ref count not decrease to 0
        self.name_list = []          # store all the variables defined in user's code

    # visit the type_def
    def visit_Typedef(self, node):
        old_status = self.type_def
        self.type_def = True
        self.generic_visit(node)
        self.type_def = old_status

    # visit the compound
    def visit_Compound(self, node):
        # we are going to a new region, deeper
        self.var_name_dict_list.append({})
        self.all_var_name_dict_list.append(self.var_name_dict_list[-1]) # to increase the ref count
        self.generic_visit(node)
        
        # At the end of this Compound, we check for all un-used ones 
        # (in this level, since if they are used in a deeper compound that will not count)
        current_dict = self.var_name_dict_list[-1]
        for var_name in current_dict: # check all the defined vars in the currect region
            item = current_dict[var_name]
            # Rule XII.C: Variables should be placed in as local a scope as possible, as close to the first use as possible.
            if not is_equal(item[1], obj2id(self.var_name_dict_list)): # the LCA of all used cases not equal to where it's defined...
                self.errors.append(f"Line {item[0]}: Variable '{var_name}' should be defined to the localest potision")
                self.grader.update_item("XII.C")
            # print(f"Line {item[0]}: Variable '{var_name}'")
            # print(f"LCA = {item[1]}, while the current position on tree is {obj2id(self.var_name_dict_list)}")
        self.var_name_dict_list.pop()

    # visit the ID
    def visit_ID(self, node):
        if node.name:
            for current_dict in self.var_name_dict_list[-1::-1]:
                # visit a variable, for Rule XII.C
                if node.name in current_dict: # here if a variable used before defined, we will ignore it, but in fact it will cause a compile error in practice
                    # print(f"Find {node.name}, with current stack = {obj2id(self.var_name_dict_list)}")
                    # find where this variable is defined, and then update the LCA of this item
                    current_dict[node.name][1] = LCA_common_prefix(current_dict[node.name][1], obj2id(self.var_name_dict_list))
                    break
        self.generic_visit(node)

    # visit the declaration for variables
    def visit_Decl(self, node):
        if node.name is None:
            return

        # only consider things in .c file
        if node.coord.line > self.header_len:
            # save for Rule I.B
            if self.in_global:
                if node.name.startswith("g_"):
                    self.name_list.append(node.name[2: ])
            else:
                self.name_list.append(node.name)

            # save for Rule XII.C
            if not self.in_global and not self.in_param and not self.type_def: 
                # we don't check the latest usage for global vars, arguments and vars in a type_def
                # and a var define should be in the latest Compound region
                self.var_name_dict_list[-1].setdefault(node.name, [node.coord.line - self.header_len, None])

            # save for later Rule XII.A
            if not self.in_param:
                self.decl_lines.setdefault(node.coord.line - self.header_len, []).append(node.name)

            # Rule I.A: Variable names must be all lowercase.
            if not node.name.islower():
                self.errors.append(f"Line {node.coord.line - self.header_len}: Variable '{node.name}' should be all lowercase.")
                self.grader.update_item("I.A")

            # Rule I.D: Global variables (i.e. at global scope and not function arguments) must start with "g_"
            if self.in_global and not self.in_param:
                if not node.name.startswith("g_"):
                    self.errors.append(f"Line {node.coord.line - self.header_len}: Global variable '{node.name}' should start with 'g_'.")
                    self.grader.update_item("I.D")

            # Rule XII.B: All variables (non-arguments) must be initialized.
            if not self.in_param and not self.type_def and node.init is None:
                # we don't check for arguments and vars in a type_def, for initialization
                self.errors.append(f"Line {node.coord.line - self.header_len}: Variable '{node.name}' must be initialized at the time it is defined.")
                self.grader.update_item("XII.B")

            # Rule XII.D: Variable length arrays are prohibited.
            if self._is_vla(node.type):
                self.errors.append(f"Line {node.coord.line - self.header_len}: Variable length arrays are prohibited.")
                self.grader.update_item("XII.D")

        # Dive into the definition detail of this variable
        self.generic_visit(node)

    def _is_vla(self, type_node):
        # need recursion check here, since we might have multiple dimensional arrays
        if isinstance(type_node, c_ast.ArrayDecl):
            if type_node.dim is None: # e.g. char s[] = "Purdue";
                return True
            if not isinstance(type_node.dim, c_ast.Constant): # e.g. int a[n] = ... where n is a variable
                return True
            # Recursion check for other dimensions
            return self._is_vla(type_node.type)
        return False

    def visit_FuncDef(self, node):
        # print(node) # Can observe the structure of AST (subtree) of this function

        # next we will not be in the Global Scope
        old_global = self.in_global
        self.in_global = False

        # Process function arguments (not sure whether it's neccessary)
        if node.decl and isinstance(node.decl.type, c_ast.FuncDecl) and node.decl.type.args:
            old_in_param = self.in_param
            self.in_param = True
            self.visit(node.decl.type.args)
            self.in_param = old_in_param

        # Visit the function body (e.g. the real content in a function)
        self.visit(node.body)

        # Recover the global scope flag
        self.in_global = old_global

    def finalize(self):
        # Rule XII.A: No more than one variable may be defined on a single line.
        for line, names in self.decl_lines.items():
            if len(names) > 1:
                for name in names:
                    self.errors.append(f"Line {line}: More than one variable defined on a single line (variable '{name}').")
                    self.grader.update_item("XII.A")

def whole_check(src_address: str, grader, check_for_I_B = False):
    pass_test = True

    # read in the original source code
    header_file = open(src_address + '.h', "r")
    code_original = header_file.read()
    header_lines_number = len(code_original.split('\n'))
    code_original += '\n'
    header_file.close()
    src_file = open(src_address + '.c', "r")
    code_original += src_file.read()
    src_file.close()

    # Step 1: preprocessing
    pp = MyPreprocessor()
    pp.parse(code_original)

    # Use a StringIO to capture the preprocessed output.
    output = io.StringIO()
    pp.write(output)
    processed_code = output.getvalue()
    # Rule I.C: All constants must be all uppercase, and contain at least two characters.
    for name, macro in pp.macros.items():
        if name not in {'__PCPP__', '__DATE__', '__TIME__', '__FILE__'} and not name.isupper():
            print(f"Error: Found invalid constant name = {name}")
            grader.update_item("I.C")
            pass_test = False
    # # Whether to print the preprocessed code
    # print(processed_code)

    # Step 2: source code body check
    parser = c_parser.CParser()
    try:
        ast = parser.parse(processed_code)
    except Exception as e:
        print("Parsing error:", e)
        # mark a Parsing error
        return 1

    checker = VariableDefinitionChecker(header_lines_number, grader)
    checker.visit(ast)
    checker.finalize()

    if check_for_I_B:
        # now it's still under developing...
        # and we need llama3.2 for this part
        from ollama import chat
        from ollama import ChatResponse
        response: ChatResponse = chat(model='llama3.2', messages=[
                                        {
                                            'role': 'user',
                                            'content': '''
                                            Assuming you are a code standard checker for C programming language source code,
                                            and I'm going to give you a list of all the variable names, you should answer whether or not all the 
                                            variable names are descriptive and meaningful, or not.
                                            And you are expected to be more tolerant since some variables might be simplified.
                                            Example: Variable such as "room_temperature" is 
                                            descriptive and meaningful, but "i" is not.  An exception can
                                            be made if "i" is used for loop counting, array indexing, etc.
                                            An exception can also be made if the variable name is something
                                            commonly used in a mathematical equation, and the code is
                                            implementing that equation. For example "z" as a complex number.\n 
                                            Next is the variable name list:\n
                                            ''' + str(checker.name_list) + '''
                                            \n\nNow it's your answer, yes or no (and give your explanation):
                                            ''',
                                        },
                                        ]
                                    )
        print(response.message.content)

    if checker.errors:
        print("Variable Definition Errors Found:")
        for err in checker.errors:
            print(err)
    elif pass_test:
        print("Pass the variable name and initialization check")

    # normal return value
    return 0
