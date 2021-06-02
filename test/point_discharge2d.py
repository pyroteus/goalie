"""
Problem specification for a simple
advection-diffusion test case with a
point source, from [Riadh et al. 2014].

This test case is notable for Pyroteus
because it has an analytical solution,
meaning the effectivity index can be
computed.

[Riadh et al. 2014] A. Riadh, G.
    Cedric, M. Jean, "TELEMAC modeling
    system: 2D hydrodynamics TELEMAC-2D
    software release 7.0 user manual."
    Paris: R&D, Electricite de France,
    p. 134 (2014).
"""
from firedrake import *
import pyadjoint


# Problem setup
n = 0
mesh = RectangleMesh(100*2**n, 20*2**n, 50, 10)
fields = ['tracer_2d']
function_space = {'tracer_2d': FunctionSpace(mesh, "CG", 1)}
solves_per_dt = [1]
end_time = 18.0
dt = 20.0
dt_per_export = 1
src_x, src_y, src_r = 2.0, 5.0, 0.05606388
rec_x, rec_y, rec_r = 20.0, 7.50, 0.5


def source(mesh):
    """
    Gaussian approximation to a point source
    at (2, 5) with discharge rate 100 on a
    given mesh.
    """
    x, y = SpatialCoordinate(mesh)
    return 100.0*exp(-((x - src_x)**2 + (y - src_y)**2)/src_r**2)


def solver(ic, t_start, t_end, dt, J=0, qoi=None):
    """
    Solve an advection-diffusion equation
    with a point source. Note that none of
    the arguments are used, except ``ic``,
    which solely used to provide the
    :class:`FunctionSpace`.
    """
    if qoi is not None:
        raise ValueError("Time integrated QoIs don't make sense for steady-state problems")
    fs = ic['tracer_2d'].function_space()
    D = Constant(0.1)
    u = Constant(as_vector([1.0, 0.0]))
    n = FacetNormal(fs.mesh())
    h = CellSize(fs.mesh())
    S = source(fs.mesh())

    # Stabilisation parameter
    unorm = sqrt(dot(u, u))
    tau = 0.5*h/unorm
    tau = min_value(tau, unorm*h/(6*D))

    # Setup variational problem
    psi = TestFunction(fs)
    psi = psi + tau*dot(u, grad(psi))
    c = TrialFunction(fs)
    a = dot(u, grad(c))*psi*dx \
        + inner(D*grad(c), grad(psi))*dx \
        - dot(grad(c), n)*psi*ds(2)
    L = S*psi*dx
    bc = DirichletBC(fs, 0, 1)

    # Solve
    sp = {
        'mat_type': 'aij',
        'ksp_type': 'preonly',
        'pc_type': 'lu',
        'pc_factor_mat_solver_type': 'mumps',
    }
    ch = Function(fs)
    solve(a == L, ch, bcs=bc, solver_parameters=sp)
    return {'tracer_2d': ch}, J


@pyadjoint.no_annotations
def initial_condition(fs):
    """
    Dummy initial condition function which
    acts merely to pass over the
    :class:`FunctionSpace`.
    """
    return {'tracer_2d': Function(fs['tracer_2d'])}


def end_time_qoi(sol):
    """
    Quantity of interest which integrates
    the tracer concentration over an offset
    receiver region.
    """
    c = sol['tracer_2d']
    x, y = SpatialCoordinate(c.function_space().mesh())
    kernel = conditional((x - rec_x)**2 + (y - rec_y)**2 < rec_r**2, 1, 0)
    area = assemble(kernel*dx)
    area_analytical = pi*rec_r**2
    scaling = 1.0 if np.allclose(area, 0.0) else area_analytical/area
    return scaling*kernel*c*dx


def bessi0(x):
    """
    Modified Bessel function of the first kind. Code taken from [3].
    """
    ax = abs(x)
    y1 = x/3.75
    y1 *= y1
    expr1 = 1.0 + y1*(3.5156229 + y1*(3.0899424 + y1*(1.2067492 + y1*(
        0.2659732 + y1*(0.360768e-1 + y1*0.45813e-2)))))
    y2 = 3.75/ax
    expr2 = exp(ax)/sqrt(ax)*(0.39894228 + y2*(0.1328592e-1 + y2*(
        0.225319e-2 + y2*(-0.157565e-2 + y2*(0.916281e-2 + y2*(
            -0.2057706e-1 + y2*(0.2635537e-1 + y2*(-0.1647633e-1 + y2*0.392377e-2))))))))
    return conditional(le(ax, 3.75), expr1, expr2)


def bessk0(x):
    """
    Modified Bessel function of the second kind. Code taken from [3].
    """
    y1 = x*x/4.0
    expr1 = -ln(x/2.0)*bessi0(x) + (-0.57721566 + y1*(0.42278420 + y1*(
        0.23069756 + y1*(0.3488590e-1 + y1*(0.262698e-2 + y1*(0.10750e-3 + y1*0.74e-5))))))
    y2 = 2.0/x
    expr2 = exp(-x)/sqrt(x)*(1.25331414 + y2*(-0.7832358e-1 + y2*(0.2189568e-1 + y2*(
        -0.1062446e-1 + y2*(0.587872e-2 + y2*(-0.251540e-2 + y2*0.53208e-3))))))
    return conditional(ge(x, 2), expr2, expr1)


def analytical_solution(mesh):
    """
    Analytical solution as represented on
    a given mesh. See [Riadh et al. 2014].
    """
    x, y = SpatialCoordinate(mesh)
    u = Constant(1.0)
    D = Constant(0.1)
    Pe = 0.5*u/D
    r = max_value(sqrt((x - src_x)**2 + (y - src_y)**2), src_r)
    return 0.5/(pi*D)*exp(Pe*(x - src_x))*bessk0(Pe*r)


if __name__ == "__main__":
    n = 4
    mesh = RectangleMesh(100*2**n, 20*2**n, 50, 10)
    function_space = {'tracer_2d': FunctionSpace(mesh, "CG", 1)}
    c = interpolate(analytical_solution(mesh), function_space['tracer_2d'])
    File("outputs/point_discharge2d/analytical.pvd").write(c)
    sols, J = solver(initial_condition(function_space), 0, end_time, dt)
    File("outputs/point_discharge2d/finite_element.pvd").write(sols['tracer_2d'])
