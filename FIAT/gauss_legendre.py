# Copyright (C) 2015 Imperial College London and others.
#
# This file is part of FIAT (https://www.fenicsproject.org)
#
# SPDX-License-Identifier:    LGPL-3.0-or-later
#
# Written by David A. Ham (david.ham@imperial.ac.uk), 2015
#
# Modified by Pablo D. Brubeck (brubeck@protonmail.com), 2021

from FIAT import finite_element, polynomial_set, dual_set, functional
from FIAT.reference_element import POINT, LINE, TRIANGLE, TETRAHEDRON
from FIAT.orientation_utils import make_entity_permutations_simplex
from FIAT.barycentric_interpolation import LagrangePolynomialSet
from FIAT.recursive_points import make_node_family, recursive_points


class GaussLegendreDualSet(dual_set.DualSet):
    """The dual basis for 1D discontinuous elements with nodes at the
    Gauss-Legendre points."""
    node_family = make_node_family("gl")

    def __init__(self, ref_el, degree):
        entity_ids = {}
        nodes = []
        entity_permutations = {}

        # make nodes by getting points
        # need to do this dimension-by-dimension, facet-by-facet
        top = ref_el.get_topology()

        for dim in sorted(top):
            entity_ids[dim] = {}
            entity_permutations[dim] = {}
            perms = make_entity_permutations_simplex(dim, degree + 1 if dim == len(top) - 1 else -1)
            for entity in sorted(top[dim]):
                entity_ids[dim][entity] = []
                entity_permutations[dim][entity] = perms

        pts = recursive_points(self.node_family, ref_el.vertices, degree)
        nodes = [functional.PointEvaluation(ref_el, x) for x in pts]
        entity_ids[dim][0] = list(range(len(nodes)))

        super(GaussLegendreDualSet, self).__init__(nodes, ref_el, entity_ids, entity_permutations)


class GaussLegendre(finite_element.CiarletElement):
    """Simplicial discontinuous element with nodes at the (recursive) Gauss-Legendre points."""
    def __init__(self, ref_el, degree):
        if ref_el.shape not in {POINT, LINE, TRIANGLE, TETRAHEDRON}:
            raise ValueError("Gauss-Legendre elements are only defined on simplices.")
        dual = GaussLegendreDualSet(ref_el, degree)
        if ref_el.shape == LINE:
            poly_set = LagrangePolynomialSet(ref_el, dual.node_family[degree])
        else:
            poly_set = polynomial_set.ONPolynomialSet(ref_el, degree)
        formdegree = ref_el.get_spatial_dimension()  # n-form
        super(GaussLegendre, self).__init__(poly_set, dual, degree, formdegree)
