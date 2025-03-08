import io
from pycparser import c_parser, c_ast
from pcpp import Preprocessor

undefined_type = {
    'bool',
    'FILE',
    # 'void',
}

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
        self.decl_lines = {}  # line -> list of variable names
        self.grader = grader
        self.header_len = header_len
        self.var_name_dict_list = [] # act like a stack, and the top is the current compound's var_name_dict

    # visit the compound
    def visit_Compound(self, node):
        # we are going to a new region, deeper
        self.var_name_dict_list.append({})
        self.generic_visit(node)
        # At the end of this Compound, we check for all un-used ones 
        # (in this level, since if they are used in a deeper compound that will not count)
        current_dict = self.var_name_dict_list[-1]
        for var_name in current_dict:
            item = current_dict[var_name]
            if item[1] == False:
                self.errors.append(f"Line {item[0]}: Variable '{var_name}' should be defined to the localest potision")
                self.grader.update_item("XII.C")
        self.var_name_dict_list.pop()

    # visit the ID
    def visit_ID(self, node):
        if len(self.var_name_dict_list):
            current_dict = self.var_name_dict_list[-1]
            # visit a variable
            if node.name and node.name in current_dict:
                current_dict[node.name][1] = True
        self.generic_visit(node)

    # visit the declaration for variables
    def visit_Decl(self, node):
        if node.name is None:
            return

        # only consider things in .c file
        if node.coord.line > self.header_len:
            # save for Rule XII.C
            if not self.in_global and not self.in_param:
                self.var_name_dict_list[-1].setdefault(node.name, [node.coord.line - self.header_len, False])

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
            if not self.in_param and node.init is None:
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

def whole_check(src_address: str, grader):
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

    if checker.errors:
        print("Variable Definition Errors Found:")
        for err in checker.errors:
            print(err)
    elif pass_test:
        print("Pass the variable name and initialization check")

    # normal return value
    return 0
