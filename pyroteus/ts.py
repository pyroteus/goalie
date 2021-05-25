from collections import Iterable
import numpy as np


__all__ = ["TimePartition"]


class TimePartition(object):
    """
    Object describing the partition of the time
    interval of interest into subintervals.

    For now, the subintervals are assumed to be
    uniform in length. However, different values
    may be used of the timestep on each.
    """
    def __init__(self, end_time, num_subintervals, timesteps, **kwargs):
        """
        :arg end_time: end time of the interval of interest
        :arg num_subintervals: number of subintervals in the partition
        :arg timesteps: (list of values for the) timestep used on each subinterval
        :kwarg timesteps_per_export: (list of) timesteps per export (default 1)
        :kwarg start_time: start time of the interval of interest (default 0.0)
        :kwarg solves_per_timestep: number of (non)linear solves per timestep (default 1)
        """
        self.debug = kwargs.get('debug', False)
        timesteps_per_export = kwargs.get('timesteps_per_export', 1)
        start_time = kwargs.get('start_time', 0.0)
        self.num_subintervals = int(np.round(num_subintervals))
        if not np.isclose(num_subintervals, self.num_subintervals):
            raise ValueError(f"Non-integer number of subintervals {num_subintervals}")
        self.print("num_subintervals")
        solves_per_timestep = kwargs.get('solves_per_timestep', 1)
        self.solves_per_timestep = int(np.round(solves_per_timestep))
        if not np.isclose(solves_per_timestep, self.solves_per_timestep):
            raise ValueError(f"Non-integer number of solves per timestep {solves_per_timestep}")
        self.print("solves_per_timestep")
        self.interval = (start_time, end_time)
        self.print("interval")
        self.subinterval_time = (end_time - start_time)/num_subintervals
        self.print("subinterval_time")
        # TODO: Allow non-uniform subintervals by passing a subintervals=None kwarg

        # Get subintervals
        self.subintervals = [
            (start_time + i*self.subinterval_time, start_time + (i+1)*self.subinterval_time)
            for i in range(num_subintervals)
        ]
        self.print("subintervals")

        # Get timestep on each subinterval
        if not isinstance(timesteps, Iterable):
            timesteps = [timesteps for subinterval in self.subintervals]
        self.timesteps = np.array(timesteps)
        self.print("timesteps")
        if len(self.timesteps) != num_subintervals:
            raise ValueError("Number of timesteps and subintervals do not match"
                             + f" ({len(self.timesteps)} vs. {num_subintervals})")

        # Get number of timesteps on each subinterval
        _timesteps_per_subinterval = [
            (t[1] - t[0])/dt
            for t, dt in zip(self.subintervals, self.timesteps)
        ]
        self.timesteps_per_subinterval = [
            int(np.round(tsps))
            for tsps in _timesteps_per_subinterval
        ]
        if not np.allclose(self.timesteps_per_subinterval, _timesteps_per_subinterval):
            raise ValueError("Non-integer timesteps per subinterval"
                             + f" ({_timesteps_per_subinterval})")
        self.print("timesteps_per_subinterval")

        # Get timesteps per export
        if not isinstance(timesteps_per_export, Iterable):
            if not np.isclose(timesteps_per_export, np.round(timesteps_per_export)):
                raise ValueError("Non-integer timesteps per export"
                                 + f" ({timesteps_per_export})")
            timesteps_per_export = [
                int(np.round(timesteps_per_export))
                for subinterval in self.subintervals
            ]
        self.timesteps_per_export = np.array(timesteps_per_export, dtype=np.int32)
        if len(self.timesteps_per_export) != len(self.timesteps_per_subinterval):
            raise ValueError("Number of timesteps per export and subinterval do not match"
                             + f" ({len(self.timesteps_per_export)}"
                             + f" vs. {self.timesteps_per_subinterval})")
        for i, (tspe, tsps) in enumerate(zip(self.timesteps_per_export,
                                             self.timesteps_per_subinterval)):
            if tsps % tspe != 0:
                raise ValueError("Number of timesteps per export does not divide number of"
                                 + f" timesteps per subinterval ({tspe} vs. {tsps}"
                                 + f" on subinteral {i})")
        self.print("timesteps_per_export")

        # Get exports per subinterval
        self.exports_per_subinterval = np.array([
            tsps//tspe + 1
            for tspe, tsps in zip(self.timesteps_per_export, self.timesteps_per_subinterval)
        ], dtype=np.int32)
        self.print("exports_per_subinterval")

    def print(self, msg):
        """
        Print attribute 'msg' for debugging purposes.
        """
        try:
            val = self.__getattribute__(msg)
        except AttributeError:
            raise AttributeError(f"Attribute {msg} cannot be printed because it doesn't exist")
        label = ' '.join(msg.split('_'))
        if self.debug:
            print(f"TimePartition: {label:25s} {val}")

    def __getitem__(self, i):
        """
        :arg i: index
        :return: subinterval bounds and timestep associated with that index
        """
        return *self.subintervals[i], self.timesteps[i]

    def solve_blocks(self, i=0):  # TODO: Account for systems of coupled equations
        """
        Get all blocks of the tape corresponding to
        solve steps of the prognostic equation on
        subinterval i.
        """
        from firedrake.adjoint.blocks import GenericSolveBlock, ProjectBlock
        from pyadjoint import get_working_tape
        stride = self.solves_per_timestep
        return [
            block
            for block in get_working_tape().get_blocks()
            if issubclass(block.__class__, GenericSolveBlock)
            and not issubclass(block.__class__, ProjectBlock)
            and block.adj_sol is not None  # FIXME: Why are they all None for new Firedrake?
        ][-self.timesteps_per_subinterval[i]*stride::stride]
