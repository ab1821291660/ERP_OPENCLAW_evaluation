import ast
import operator
import re
from decimal import Decimal
from langchain_core.tools import tool


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
def _eval_ast(node: ast.AST) -> Decimal:
    """递归执行已白名单的 AST 节点；其他任意 Python 语法一律拒绝。"""

    # 判断是不是 ast.parse(..., mode="eval") 生成的最外层节点。
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body) # 取出外层节点包裹的实际表达式，递归处理。

    # 判断是不是数字常量，例如 225 或 0.5。
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value)) # 先转字符串再构造 Decimal，避免直接从二进制浮点数构造时带入其表示误差。

    # 判断是不是一元负号，例如 -42。
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        # 递归算出负号后面的值，再取负。例如先得到 42，再返回 -42。
        return -_eval_ast(node.operand)
    # 判断是不是二元运算，并确认运算符在加、减、乘、除白名单中。
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        # 分别递归计算左、右操作数。因此可以处理括号和嵌套表达式。
        left, right = _eval_ast(node.left), _eval_ast(node.right)
        # 如果当前是除法，先检查分母是否为零。
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Division by zero")
        # 从白名单中取出相应运算函数，对左右两个 Decimal 执行计算。
        return _BINARY_OPERATORS[type(node.op)](left, right)
    raise ValueError("Only numeric literals and +, -, *, / are allowed")



@tool(parse_docstring=True)
def safe_calculate(expression: str) -> str:
    """用受限算术表达式计算财务数值，返回可直接复核的十进制结果。

    Args:
        expression: 长度不超过 200 个字符的算术表达式，例如
            ``(225 - 180) / 180 * 100``。支持数字、括号、加减乘除、
            逗号千分位、美元符号和紧跟数字的百分号；须先把财务指标名称
            替换为报告中的原始数值，不支持变量、函数或 Python 代码。

    Returns:
        Decimal 计算结果的字符串形式，例如 ``"25"``，不附加单位或百分号。

    Raises:
        ValueError: 表达式含有非法字符、不支持的语法，或发生除零。
        SyntaxError: 字符合法但表达式不完整，无法解析为语法树。

    Notes:
        使用字符白名单和 AST 节点白名单限制输入，不调用 ``eval``。
    """
    # 第一层检查：长度不得超过 200；正则表达式必须匹配整个输入。
    # 允许数字、空白、点、逗号、括号、加减乘除、百分号和美元符号。
    if len(expression) > 200 or not re.fullmatch(r"[\d\s.,()+\-*/%$]+", expression):
        raise ValueError("Expression contains unsupported characters")
    # 删除逗号和美元符号。例如 $1,200 变为 1200。
    normalized = expression.replace(",", "").replace("$", "")
    if "%" in normalized: # 如果表达式中出现百分号，进入百分比转换。
        # 将紧跟数字的百分数改成除以 100 的表达式。例如 25% 变为 (25/100)。
        normalized = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", normalized)
    # 把表达式解析成 AST 语法树；这一步不会执行 Python 代码。
    tree = ast.parse(normalized, mode="eval")
    # 生成的树可以简化为：
    # 乘法
    # ├── 除法
    # │   ├── 减法
    # │   │   ├── 225
    # │   │   └── 180
    # │   └── 180
    # └── 100
    # 把语法树交给上面的函数 执行器，得到 Decimal 结果。
    result = _eval_ast(tree)##===================================
    # 规范化结果，并以普通十进制字符串返回。例如 Decimal("25.000") 返回 "25"；
    return format(result.normalize(), "f")