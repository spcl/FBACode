#!/usr/bin/env python

import clang.cindex
from sys import argv
from clang.cindex import CursorKind



def find_typerefs(node, typename):
    # find all typerefs with name typename
    results = []
    # print("called find_typedefs with cursor {} at {}".format(
    #         node.displayname, node.location))
    if node.kind.is_reference():
        # print("is reference!")
        # ref_node = clang.cindex.Cursor(node)
        if node.displayname == typename:
            print("Found {} at {}".format(typename, node.location))
            results.append(node)
    # recursively traverse the tree
    for c in node.get_children():
        results.extend(find_typerefs(c, typename))
    return results

def find_callexp(node, fname):
    results = []
    # print("{} at {}, TYPE: {}".format(node.displayname, node.location, node.kind))
    # kind = CursorKind()
    if node.kind == CursorKind.CALL_EXPR and node.displayname == fname:
        # print("IS CALLEXP")
        results.append(node)
    for c in node.get_children():
        results.extend(find_callexp(c, fname))
    return results

def traverse_tree(node, indent):
    print("{}{} at {}, TYPE: {}".format(" " * indent, node.displayname, node.location, node.kind))
    for c in node.get_children():
        traverse_tree(c, indent + 1)

def main():
    # idx = clang.cindex.Index.create()

    # tu = idx.parse("../tmp.cpp")

    # TODO: look into TranslationUnit.from_ast_file
    #   open the previously generated ast file instead of source files
    # print("Translation unit:", tu.spelling)
    idx = clang.cindex.Index.create()
    tu = idx.parse(argv[1])
    traverse_tree(tu.cursor, 0)
    # results = callexp_in_file("../tmp1.ast", "add")
    # print(results)


def typeref_in_file(filename, typename, ast=False):
    idx = clang.cindex.Index.create()
    if ast:
        tu = idx.read(filename)
    else:
        tu = idx.parse(filename)
    results = find_typerefs(tu.cursor, typename)
    return results

def callexp_in_file(filename, fname, ast=False):
    idx = clang.cindex.Index.create()
    if ast:
        tu = idx.read(filename)
    else:
        tu = idx.parse(filename)
    results = find_callexp(tu.cursor, fname)
    return results

if __name__ == "__main__":
    main()
