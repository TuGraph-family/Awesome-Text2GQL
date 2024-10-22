class Expr:
    def __init__(self,value):
        self.value = value
        self.left = None
        self.right = None

    def depth_first_search(self,node):
        if node is None:
            return
        print(node.value, end=' ')
        self.depth_first_search(node.left)
        self.depth_first_search(node.right)

class ExprLeaf:
    def __init__(self,left_expr,symbol,right_expr):
        self.left_expr=left_expr
        self.symbol=symbol
        self.right_expr=right_expr
    
    def pre_gen_leaf(self):
        if self.left_expr[1]==0:
            return True
        else:
            # symbol  ( '=' SP? oC_AddOrSubtractExpression )
        #                            | ( '<>' SP? oC_AddOrSubtractExpression )
        #                            | ( '<' SP? oC_AddOrSubtractExpression )
        #                            | ( '>' SP? oC_AddOrSubtractExpression )
        #                            | ( '<=' SP? oC_AddOrSubtractExpression )
        #                            | ( '>=' SP? oC_AddOrSubtractExpression )
            if self.left_expr[1] == self.right_expr[1] and self.left_expr[1]!=0:
                # n.title == m.tile
                return False # require changing the size of query_lists

    def gen_leaf(self, matched_label_lists, query_lists):
        idxs_2_rm=[]
        # find those to been removed
        return query_lists

if __name__ == "__main__":
    root = Expr('A')
    root.left = Expr('B')
    root.right = Expr('C')
    root.left.left = Expr('D')
    root.left.right = Expr('E')