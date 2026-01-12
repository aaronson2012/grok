import ast
import operator
import math

# Allowed operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed functions
FUNCTIONS = {
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'sqrt': math.sqrt,
    'log': math.log,
    'abs': abs,
    'round': round,
    'ceil': math.ceil,
    'floor': math.floor,
}

# Allowed constants
CONSTANTS = {
    'pi': math.pi,
    'e': math.e,
}

def safe_eval(node):
    """
    recursively evaluate an AST node if it's safe.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        op_type = type(node.op)
        if op_type in OPERATORS:
            try:
                return OPERATORS[op_type](left, right)
            except ZeroDivisionError:
                return float('inf')
        raise ValueError(f"Unsupported operator: {op_type}")
    elif isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FUNCTIONS:
                args = [safe_eval(arg) for arg in node.args]
                return FUNCTIONS[func_name](*args)
            raise ValueError(f"Unsupported function: {func_name}")
        raise ValueError("Function calls must be by name")
    elif isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise ValueError(f"Unknown variable or constant: {node.id}")
    elif isinstance(node, ast.Expression):
        return safe_eval(node.body)
    else:
        raise ValueError(f"Unsupported syntax: {type(node)}")

def calculate(expression: str) -> str:
    """
    Safely evaluates a mathematical expression string.
    """
    # Remove whitespace and ensure safety limits
    expression = expression.strip()
    if len(expression) > 200:
        return "Error: Expression too long (max 200 chars)"
    
    try:
        # Parse the expression into an AST
        node = ast.parse(expression, mode='eval')
        
        # Evaluate safely
        result = safe_eval(node)
        
        # Format the result
        if isinstance(result, float):
             # Avoid trivial decimals like 5.0
            if result.is_integer():
                return str(int(result))
            return f"{result:.6f}".rstrip('0').rstrip('.')
            
        return str(result)
        
    except SyntaxError:
        return "Error: Invalid syntax"
    except Exception as e:
        return f"Error: {str(e)}"
