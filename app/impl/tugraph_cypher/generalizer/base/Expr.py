# this file is reserved for parsing and generate the expr in where clause
class ExprLeaf:
    def __init__(self, left_expr, symbol, right_expr):
        self.symbol = symbol
        self.left_expr = left_expr
        self.right_expr = right_expr

    def pre_gen_leaf(self):
        if self.left_expr[1] == 0:
            return True
        else:
            # '=' ,'<>', '<','>' ,'<=','>=', find constraints
            if self.left_expr[1] == self.right_expr[1] and self.left_expr[1] != 0:
                # n.title == m.tile
                return False  # require changing the size of query_lists

    def gen_leaf(self, matched_label_lists, query_lists):
        # find those to been removed
        return query_lists


class ExprTree:
    def __init__(self, value=None):
        self.value = value
        self.left = None
        self.right = None

    def add_leaf(self, expr: ExprLeaf):
        if self.left_expr is None:
            self.left_expr = expr
        else:
            self.right_expr = expr

    def pre_gen_where(self, matched_label_lists):
        pass  # dfs,ExprLeaf.pre_gen_where

    def depth_first_search(self, node):
        if node is None:
            return
        print(node.value, end=" ")
        self.depth_first_search(node.left)
        self.depth_first_search(node.right)

    def gen_tree():
        pass


if __name__ == "__main__":
    root = ExprTree("A")
    root.left = ExprTree("B")
    root.right = ExprTree("C")
    root.left.left = ExprTree("D")
    root.left.right = ExprTree("E")
