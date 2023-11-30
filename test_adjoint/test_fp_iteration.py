from firedrake import *
from goalie_adjoint import *
from setup_adjoint_tests import *
import abc
from parameterized import parameterized
import unittest


def get_qoi(mesh_seq, solutions, index):
    R = FunctionSpace(mesh_seq[index], "R", 0)

    def qoi():
        return Function(R).assign(1 if mesh_seq.fp_iteration % 2 == 0 else 2) * dx

    return qoi


class MeshSeqBaseClass:
    """
    Base class for :meth:`fixed_point_iteration` unit tests.
    """

    @abc.abstractmethod
    def setUp(self):
        pass

    @abc.abstractmethod
    def mesh_seq(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def set_values(self, mesh_seq, value):
        pass

    @abc.abstractmethod
    def check_convergence(self, mesh_seq):
        pass

    def test_convergence_noop(self):
        miniter = self.parameters.miniter
        mesh_seq = self.mesh_seq()
        mesh_seq.fixed_point_iteration(empty_adaptor)
        self.assertEqual(len(mesh_seq.element_counts), miniter + 1)
        self.assertTrue(np.allclose(mesh_seq.converged, True))
        self.assertTrue(np.allclose(mesh_seq.check_convergence, True))

    def test_noconvergence(self):
        mesh1 = UnitSquareMesh(1, 1)
        mesh2 = UnitTriangleMesh()

        def adaptor(mesh_seq, *args):
            mesh_seq[0] = mesh1 if mesh_seq.fp_iteration % 2 == 0 else mesh2
            return [False]

        maxiter = self.parameters.maxiter
        mesh_seq = self.mesh_seq(mesh=mesh2)
        mesh_seq.fixed_point_iteration(adaptor)
        self.assertEqual(len(mesh_seq.element_counts), maxiter + 1)
        self.assertTrue(np.allclose(mesh_seq.converged, False))
        self.assertTrue(np.allclose(mesh_seq.check_convergence, True))

    def test_no_late_convergence(self):
        mesh1 = UnitSquareMesh(1, 1)
        mesh2 = UnitTriangleMesh()
        time_partition = TimePartition(1.0, 2, [0.5, 0.5], [])
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq(
            time_partition=time_partition, mesh=mesh2, qoi_type="end_time"
        )

        def adaptor(mesh_seq, *args):
            mesh_seq[0] = mesh1 if mesh_seq.fp_iteration % 2 == 0 else mesh2
            return [False, False]

        mesh_seq.fixed_point_iteration(adaptor)
        expected = [[1, 1], [2, 1], [1, 1], [2, 1], [1, 1], [2, 1]]
        self.assertEqual(mesh_seq.element_counts, expected)
        self.assertTrue(np.allclose(mesh_seq.converged, [False, False]))
        self.assertTrue(np.allclose(mesh_seq.check_convergence, [True, True]))

    @parameterized.expand([[True], [False]])
    def test_dropout(self, drop_out_converged):
        mesh1 = UnitSquareMesh(1, 1)
        mesh2 = UnitTriangleMesh()
        time_partition = TimePartition(1.0, 2, [0.5, 0.5], [])
        self.parameters.drop_out_converged = drop_out_converged
        mesh_seq = self.mesh_seq(
            time_partition=time_partition, mesh=mesh2, qoi_type="end_time"
        )

        def adaptor(mesh_seq, *args):
            mesh_seq[1] = mesh1 if mesh_seq.fp_iteration % 2 == 0 else mesh2
            return [False, False]

        mesh_seq.fixed_point_iteration(adaptor)
        expected = [[1, 1], [1, 2], [1, 1], [1, 2], [1, 1], [1, 2]]
        self.assertEqual(mesh_seq.element_counts, expected)
        self.assertTrue(np.allclose(mesh_seq.converged, [True, False]))
        self.assertTrue(
            np.allclose(mesh_seq.check_convergence, [not drop_out_converged, True])
        )

    def test_update_params(self):
        def update_params(params, fp_iteration):
            params.element_rtol = fp_iteration

        self.parameters.miniter = self.parameters.maxiter
        self.parameters.element_rtol = 0.5
        mesh_seq = self.mesh_seq()
        mesh_seq.fixed_point_iteration(empty_adaptor, update_params=update_params)
        self.assertEqual(self.parameters.element_rtol + 1, 5)


class TestMeshSeq(unittest.TestCase, MeshSeqBaseClass):
    """
    Unit tests for :meth:`MeshSeq.fixed_point_iteration`.
    """

    def setUp(self):
        self.parameters = AdaptParameters(
            {
                "miniter": 3,
                "maxiter": 5,
            }
        )

    def mesh_seq(self, time_partition=None, mesh=None, parameters=None, **kwargs):
        return MeshSeq(
            time_partition or TimeInstant([]),
            mesh or UnitTriangleMesh(),
            get_function_spaces=empty_get_function_spaces,
            get_form=empty_get_form,
            get_bcs=empty_get_bcs,
            get_solver=empty_get_solver,
            parameters=parameters or self.parameters,
        )
    
    def set_values(self, mesh_seq, value):
        mesh_seq.element_counts = value

    def check_convergence(self, mesh_seq):
        return mesh_seq.check_element_count_convergence()

    def test_element_convergence_lt_miniter(self):
        mesh_seq = self.mesh_seq()
        self.assertFalse(self.check_convergence(mesh_seq))
        self.assertFalse(mesh_seq.converged)

    def test_element_convergence_true(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        self.set_values(mesh_seq, np.ones((mesh_seq.params.miniter + 1, 1)))
        self.assertTrue(self.check_convergence(mesh_seq))
        self.assertTrue(mesh_seq.converged)

    def test_element_convergence_false(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        values = np.ones((self.parameters.miniter + 1, 1))
        values[-1] = 2
        self.set_values(mesh_seq, values)
        self.assertFalse(self.check_convergence(mesh_seq))
        self.assertFalse(mesh_seq.converged)


class TestAdjointMeshSeq(unittest.TestCase, MeshSeqBaseClass):
    """
    Unit tests for :meth:`AdjointMeshSeq.fixed_point_iteration`.
    """

    def setUp(self):
        self.parameters = GoalOrientedParameters(
            {
                "miniter": 3,
                "maxiter": 5,
            }
        )

    def mesh_seq(
        self, time_partition=None, mesh=None, parameters=None, qoi_type="steady"
    ):
        return AdjointMeshSeq(
            time_partition or TimeInstant([]),
            mesh or UnitTriangleMesh(),
            get_function_spaces=empty_get_function_spaces,
            get_form=empty_get_form,
            get_bcs=empty_get_bcs,
            get_solver=empty_get_solver,
            get_qoi=get_qoi,
            parameters=parameters or self.parameters,
            qoi_type=qoi_type,
        )
    
    def set_values(self, mesh_seq, value):
        mesh_seq.qoi_values = value

    def check_convergence(self, mesh_seq):
        return mesh_seq.check_qoi_convergence()

    def test_qoi_convergence_lt_miniter(self):
        mesh_seq = self.mesh_seq()
        self.assertFalse(self.check_convergence(mesh_seq))
        self.assertFalse(mesh_seq.converged)

    def test_qoi_convergence_true(self):
        mesh_seq = self.mesh_seq()
        self.set_values(mesh_seq, np.ones((mesh_seq.params.miniter + 1, 1)))
        self.assertTrue(self.check_convergence(mesh_seq))

    def test_qoi_convergence_false(self):
        mesh_seq = self.mesh_seq()
        values = np.ones((self.parameters.miniter + 1, 1))
        values[-1] = 2
        self.set_values(mesh_seq, values)
        self.assertFalse(self.check_convergence(mesh_seq))

    def test_qoi_convergence_check_false(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        self.set_values(mesh_seq, np.ones((mesh_seq.params.miniter + 1, 1)))
        mesh_seq.check_convergence[:] = True
        mesh_seq.check_convergence[-1] = False
        self.assertFalse(self.check_convergence(mesh_seq))


class TestGoalOrientedMeshSeq(unittest.TestCase, MeshSeqBaseClass):
    """
    Unit tests for :meth:`GoalOrientedMeshSeq.fixed_point_iteration`.
    """

    def setUp(self):
        self.parameters = GoalOrientedParameters(
            {
                "miniter": 3,
                "maxiter": 5,
            }
        )

    def mesh_seq(
        self, time_partition=None, mesh=None, parameters=None, qoi_type="steady"
    ):
        return GoalOrientedMeshSeq(
            time_partition or TimeInstant([]),
            mesh or UnitTriangleMesh(),
            get_function_spaces=empty_get_function_spaces,
            get_form=empty_get_form,
            get_bcs=empty_get_bcs,
            get_solver=empty_get_solver,
            get_qoi=get_qoi,
            parameters=parameters or self.parameters,
            qoi_type=qoi_type,
        )
    
    def set_values(self, mesh_seq, value):
        mesh_seq.estimator_values = value

    def check_convergence(self, mesh_seq):
        return mesh_seq.check_estimator_convergence()

    def test_estimator_convergence_lt_miniter(self):
        mesh_seq = self.mesh_seq()
        self.assertFalse(self.check_convergence(mesh_seq))
        self.assertFalse(mesh_seq.converged)

    def test_estimator_convergence_true(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        self.set_values(mesh_seq, np.ones((mesh_seq.params.miniter + 1, 1)))
        self.assertTrue(self.check_convergence(mesh_seq))

    def test_estimator_convergence_false(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        values = np.ones((self.parameters.miniter + 1, 1))
        values[-1] = 2
        self.set_values(mesh_seq, values)
        self.assertFalse(self.check_convergence(mesh_seq))

    def test_estimator_convergence_check_false(self):
        self.parameters.drop_out_converged = True
        mesh_seq = self.mesh_seq()
        self.set_values(mesh_seq, np.ones((mesh_seq.params.miniter + 1, 1)))
        mesh_seq.check_convergence[:] = True
        mesh_seq.check_convergence[-1] = False
        self.assertFalse(self.check_convergence(mesh_seq))

    def test_convergence_criteria_all(self):
        mesh = UnitSquareMesh(1, 1)
        time_partition = TimePartition(1.0, 1, 0.5, [])
        self.parameters.convergence_criteria = "all"
        mesh_seq = self.mesh_seq(
            time_partition=time_partition, mesh=mesh, qoi_type="end_time"
        )
        mesh_seq.fixed_point_iteration(empty_adaptor)
        self.assertTrue(np.allclose(mesh_seq.element_counts, 2))
        self.assertTrue(np.allclose(mesh_seq.converged, False))
        self.assertTrue(np.allclose(mesh_seq.check_convergence, True))
