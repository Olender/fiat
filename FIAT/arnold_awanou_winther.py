# -*- coding: utf-8 -*-
"""Implementation of the Arnold-Awanou-Winther finite elements."""

# Copyright (C) 2016-2018 Lizao Li <lzlarryli@gmail.com>
#
# This file is part of FIAT.
#
# FIAT is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FIAT is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with FIAT. If not, see <http://www.gnu.org/licenses/>.

from FIAT.finite_element import CiarletElement
from FIAT.dual_set import DualSet
from FIAT.polynomial_set import ONSymTensorPolynomialSet
from FIAT.functional import PointwiseInnerProductEvaluation as InnerProduct, IntegralMoment
from FIAT.quadrature import GaussLegendreQuadratureLineRule, QuadratureRule
from FIAT.reference_element import UFCInterval as interval
import numpy


class IntegralNormalNormalLegendreMoment(IntegralMoment):
    """Enforce that dot(n, dot(tau, n)) is of degree n - 1 on entity."""
    def __init__(self, cell, entity, degree):
        sd = cell.get_spatial_dimension()
        shp = (sd, sd)

        n = cell.compute_scaled_normal(entity)
        nnT = numpy.outer(n, n)
        quadpoints = degree + 1
        Q = GaussLegendreQuadratureLineRule(interval(), quadpoints)
        legendre = numpy.polynomial.legendre.legval(2*Q.get_points()-1, [0]*degree + [1])

        # Missing a constant factor for transformation of domain, but it doesn't matter
        # for the kernel of the functional
        f_at_qpts = [nnT*legendre[i] for i in range(quadpoints)]

        # Map the quadrature points
        fmap = cell.get_entity_transform(sd-1, entity)
        mappedqpts = [fmap(pt) for pt in Q.get_points()]
        mappedQ = QuadratureRule(cell, mappedqpts, Q.get_weights())

        IntegralMoment.__init__(self, cell, mappedQ, f_at_qpts, shp=shp)


    def to_riesz(self, poly_set):
        es = poly_set.get_expansion_set()
        ed = poly_set.get_embedded_degree()
        pts = list(self.pt_dict.keys())
        bfs = es.tabulate(ed, pts)
        wts = numpy.array([foo[0][0] for foo in list(self.pt_dict.values())])
        result = numpy.zeros(poly_set.coeffs.shape[1:], "d")

        for i in range(result.shape[0]):
            for j in range(result.shape[1]):
                result[i, j, :] = numpy.dot(bfs, wts[:, i, j])

        return result


class ArnoldAwanouWintherDual(DualSet):
    """Degrees of freedom for Arnold-Awanou-Winther elements."""
    def __init__(self, cell, degree):
        dim = cell.get_spatial_dimension()
        if not dim == 2:
            raise ValueError("Arnold-Awanou-Winther elements are only"
                             "defined in dimension 2, for now! The theory"
                             "is there in 3D, I just haven't implemented it.")

        if not degree == 2:
            raise ValueError("Arnold-Awanou-Winther elements are only defined"
                             "for degree 2.")

        # construct the degrees of freedoms
        dofs = []               # list of functionals
        # dof_ids[i][j] contains the indices of dofs that are associated with
        # entity j in dim i
        dof_ids = {}

        # no vertex dof
        dof_ids[0] = {i: [] for i in range(dim + 1)}

        # edge dofs
        (_dofs, _dof_ids) = self._generate_edge_dofs(cell, degree)
        dofs.extend(_dofs)
        dof_ids[1] = _dof_ids

        # cell dofs
        (_dofs, _dof_ids) = self._generate_trig_dofs(cell, degree, len(dofs))
        dofs.extend(_dofs)
        dof_ids[dim] = _dof_ids

        # extra dofs for enforcing linearity of dot(n, dot(sigma, n)) on edges
        (_dofs, _dof_ids) = self._generate_constraint_dofs(cell, degree, len(dofs))
        dofs.extend(_dofs)

        for entity_id in range(3):
            dof_ids[1][entity_id] = dof_ids[1][entity_id] + _dof_ids[entity_id]

        super(ArnoldAwanouWintherDual, self).__init__(dofs, cell, dof_ids)


    @staticmethod
    def _generate_edge_dofs(cell, degree):
        """generate dofs on edges.
        On each edge, let n be its normal. The components of dot(u, n)
        are evaluated at two different points.
        """
        dofs = []
        dof_ids = {}
        offset = 0

        for entity_id in range(3):                  # a triangle has 3 edges
            pts = cell.make_points(1, entity_id, degree + 1)  # edges are 1D
            normal = cell.compute_scaled_normal(entity_id)
            tangent = cell.compute_normalized_tangents(1, entity_id)[0]
            dofs += [InnerProduct(cell, normal, dir, pt) for pt in pts for dir in [normal, tangent]]
            num_new_dofs = 2*len(pts)               # 2 dof per point on edge
            dof_ids[entity_id] = list(range(offset, offset + num_new_dofs))
            offset += num_new_dofs
        return (dofs, dof_ids)


    @staticmethod
    def _generate_constraint_dofs(cell, degree, offset):
        """
        Generate constraint dofs on edges.
        dot(n, dot(sigma, n)) must be linear on each edge.
        So we introduce functionals whose kernel describes this property,
        as described in the FIAT paper.
        """
        dofs = []
        dof_ids = {}

        for entity_id in range(3):
            dof = IntegralNormalNormalLegendreMoment(cell, entity_id, degree)
            dofs += [dof]
            dof_ids[entity_id] = [offset]
            offset += 1

        return (dofs, dof_ids)


    @staticmethod
    def _generate_trig_dofs(cell, degree, offset):
        """generate dofs on edges.
        On each triangle, for degree=r, the three components
              u11, u12, u22
        are evaluated at a single point.
        """
        dofs = []
        dof_ids = {}
        pts = cell.make_points(2, 0, 3)           # 2D trig #0
        e1 = numpy.array([1.0, 0.0])              # euclidean basis 1
        e2 = numpy.array([0.0, 1.0])              # euclidean basis 2
        basis = [(e1, e1), (e1, e2), (e2, e2)]    # basis for symmetric matrix
        for (v1, v2) in basis:
            dofs += [InnerProduct(cell, v1, v2, pt) for pt in pts]
        num_dofs = 3 * len(pts)                   # 3 dofs per trig
        dof_ids[0] = list(range(offset, offset + num_dofs))
        return (dofs, dof_ids)


class ArnoldAwanouWinther(CiarletElement):
    """The definition of the Arnold-Awanou-Winther element.
    """
    def __init__(self, cell, degree):
        assert degree == 2, "Only defined for degree 2"
        # polynomial space
        Ps = ONSymTensorPolynomialSet(cell, degree)
        # degrees of freedom
        Ls = ArnoldAwanouWintherDual(cell, degree)
        # mapping under affine transformation
        mapping = "double contravariant piola"

        super(ArnoldAwanouWinther, self).__init__(Ps, Ls, degree,
                                                  mapping=mapping)
