from pycparser import c_parser, c_ast

class VariableDefinitionChecker(c_ast.NodeVisitor):
    def __init__(self):
        self.errors = []
        self.in_global = True
        self.in_param = False # whether an argument for functions
        self.decl_lines = {}  # line -> list of variable names

    # visit the declaration for variables
    def visit_Decl(self, node):
        if node.name is None:
            return

        if not self.in_param and node.coord:
            line = node.coord.line
            # save for later Rule XII.A
            self.decl_lines.setdefault(line, []).append(node.name)

        # Rule I.A: Variable names must be all lowercase.
        if node.name != node.name.lower():
            self.errors.append(f"Line {node.coord.line}: Variable '{node.name}' should be all lowercase.")

        # Rule I.D: Global variables (i.e. at global scope and not function arguments) must start with "g_"
        if self.in_global and not self.in_param:
            if not node.name.startswith("g_"):
                self.errors.append(f"Line {node.coord.line}: Global variable '{node.name}' should start with 'g_'.")

        # Rule XII.B: All variables (non-arguments) must be initialized.
        if not self.in_param and node.init is None:
            self.errors.append(f"Line {node.coord.line}: Variable '{node.name}' must be initialized at the time it is defined.")

        # Rule XII.D: Variable length arrays are prohibited.
        if self._is_vla(node.type):
            self.errors.append(f"Line {node.coord.line}: Variable length arrays are prohibited.")

        # Recursion check for children on AST
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

def main():
    code = r'''
int g_temperature = 0;
int roomTemp = 10, invalidCamelCase = 5;
int g_pressure = 1013;
int g_altitude;

int g_arr[5] = {1,2,3,4,5};
int g_vla[n] = {0};

int function(int *a[3], char s[6]){
    return 666;
}

int main() {
    int localVar = 100;
    int a, b = 0;
    return 0;
}
    '''
    parser = c_parser.CParser()
    try:
        ast = parser.parse(code)
    except Exception as e:
        print("Parsing error:", e)
        return

    checker = VariableDefinitionChecker()
    checker.visit(ast)
    checker.finalize()

    if checker.errors:
        print("Variable Definition Errors Found:")
        for err in checker.errors:
            print(err)
    else:
        print("No variable definition errors found.")

if __name__ == "__main__":
    main()
