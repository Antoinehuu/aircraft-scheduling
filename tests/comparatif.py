from gurobipy import *

def canonical_constraint(model, constr, tol=1e-9):
    row = model.getRow(constr)

    terms = []

    for i in range(row.size()):
        var = row.getVar(i)
        coeff = row.getCoeff(i)

        if abs(coeff) > tol:
            terms.append((var.VarName, round(coeff, 9)))

    # IMPORTANT : tri pour ignorer l'ordre
    terms.sort()

    return (
        tuple(terms),
        constr.Sense,
        round(constr.RHS, 9),
    )


def model_to_set(model):
    s = set()

    for c in model.getConstrs():
        s.add(canonical_constraint(model, c))

    return s


def compare_models(m1, m2):
    s1 = model_to_set(m1)
    s2 = model_to_set(m2)

    only_1 = s1 - s2
    only_2 = s2 - s1

    print("=== Only in model 1 ===")
    for c in only_1:
        print(c)

    # print("\n=== Only in model 2 ===")
    # for c in only_2:
    #     print(c)
        
m1 = read("model.lp")
m2 = read("model_feasible.lp")

compare_models(m1, m2)