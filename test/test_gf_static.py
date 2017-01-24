import unittest
import numpy as num
import cProfile
import math
import logging

from tempfile import mkdtemp
from common import Benchmark
from pyrocko import gf, util, cake
from pyrocko.fomosto import qseis

random = num.random
logger = logging.getLogger('test_gf_static.py')
benchmark = Benchmark()

r2d = 180. / math.pi
d2r = 1.0 / r2d
km = 1000.


class GFStaticTest(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        self.tempdirs = []
        self._dummy_store = None
        self.qseis_store_dir = None
        unittest.TestCase.__init__(self, *args, **kwargs)

    def __del__(self):
        import shutil

        for d in self.tempdirs:
            shutil.rmtree(d)

    def setUp(self):
        self.cprofile = cProfile.Profile()
        self.cprofile.enable()
        self.addCleanup(
            lambda: self.cprofile.dump_stats('/tmp/make_sum_params.cprof'))

    def get_qseis_store_dir(self):
        return '/tmp/gfstoreOiW0kP'
        if self.qseis_store_dir is None:
            self.qseis_store_dir = self._create_qseis_store()

        return self.qseis_store_dir

    def _create_qseis_store(self):
        mod = cake.LayeredModel.from_scanlines(cake.read_nd_model_str('''
 0. 5.8 3.46 2.6 1264. 600.
 20. 5.8 3.46 2.6 1264. 600.
 20. 6.5 3.85 2.9 1283. 600.
 35. 6.5 3.85 2.9 1283. 600.
mantle
 35. 8.04 4.48 3.58 1449. 600.
 77.5 8.045 4.49 3.5 1445. 600.
 77.5 8.045 4.49 3.5 180.6 75.
 120. 8.05 4.5 3.427 180. 75.
 120. 8.05 4.5 3.427 182.6 76.06
 165. 8.175 4.509 3.371 188.7 76.55
 210. 8.301 4.518 3.324 201. 79.4
 210. 8.3 4.52 3.321 336.9 133.3
 410. 9.03 4.871 3.504 376.5 146.1
 410. 9.36 5.08 3.929 414.1 162.7
 660. 10.2 5.611 3.918 428.5 172.9
 660. 10.79 5.965 4.229 1349. 549.6'''.lstrip()))
        store_dir = mkdtemp(prefix='gfstore')
        # self.tempdirs.append(store_dir)

        qsconf = qseis.QSeisConfig()
        qsconf.qseis_version = '2006a'

        qsconf.time_region = (
            gf.meta.Timing('0'),
            gf.meta.Timing('end+100'))

        qsconf.cut = (
            gf.meta.Timing('0'),
            gf.meta.Timing('end+100'))

        qsconf.wavelet_duration_samples = 0.001
        qsconf.sw_flat_earth_transform = 0

        config = gf.meta.ConfigTypeA(
            id='qseis_test',
            ncomponents=10,
            sample_rate=0.25,
            receiver_depth=0.*km,
            source_depth_min=10*km,
            source_depth_max=20*km,
            source_depth_delta=1*km,
            distance_min=0*km,
            distance_max=20*km,
            distance_delta=2.5*km,
            modelling_code_id='qseis.2006a',
            earthmodel_1d=mod,
            tabulated_phases=[
                gf.meta.TPDef(
                    id='begin',
                    definition='p,P,p\\,P\\'),
                gf.meta.TPDef(
                    id='end',
                    definition='2.5'),
            ])

        config.validate()
        gf.store.Store.create_editables(
            store_dir, config=config, extra={'qseis': qsconf})

        store = gf.store.Store(store_dir, 'r')
        store.make_ttt()
        store.close()

        qseis.build(store_dir, nworkers=1)
        print store_dir
        return store_dir

    def test_sum_static(self):
        from pyrocko.gf import store_ext
        benchmark.show_factor = True

        store = gf.Store(self.get_qseis_store_dir())
        store.open()
        dim = 1*km
        ntargets = 1
        interp = ['nearest_neighbor', 'multilinear']
        interpolation = interp[0]

        source = gf.RectangularSource(
            lat=0., lon=0.,
            depth=15*km, north_shift=0., east_shift=0.,
            width=dim, length=dim)

        r1 = random.rand()*5*km
        r2 = random.rand()*5*km
        targets = [gf.Target(
            lat=0.0, lon=0.0,
            north_shift=5*km+r1,
            east_shift=0*km+r2)
                for x in xrange(ntargets)]

        dsource = source.discretize_basesource(store, targets[0])
        source_coords_arr = dsource.coords5()
        mts_arr = dsource.m6s

        receiver_coords_arr = num.empty((len(targets), 5))
        for itarget, target in enumerate(targets):
            receiver = target.receiver(store)
            receiver_coords_arr[itarget, :] = \
                [receiver.lat, receiver.lon, receiver.north_shift,
                 receiver.east_shift, receiver.depth]

        @benchmark.labeled('timeseries')
        def sum_timeseries(cstore, irecords, delays, weights, pos):
            nsummands = weights.size / ntargets
            res = num.zeros(ntargets)
            for t in xrange(ntargets):
                sl = slice(t*nsummands, (t+1) * nsummands)
                r = store_ext.store_sum(
                    cstore, irecords[sl], delays[sl], weights[sl], pos, 1)
                res[t] = r[0]
            return res

        @benchmark.labeled('static')
        def sum_static(cstore, irecords, delays, weights, pos, nthreads):
            return store_ext.store_sum_static(
                cstore, irecords, delays, weights, pos, ntargets, nthreads)

        for i, (component, args, delays, weights) in \
            enumerate(store.config.make_sum_params(
                      dsource, targets[0].receiver(store))):
            continue

        args = (store.cstore, source_coords_arr, mts_arr, receiver_coords_arr,
                'elastic10', interpolation, 0)

        for (weights, irecords) in store_ext.make_sum_params(*args):
            delays = num.zeros_like(weights)
            pos = 6
            t = sum_timeseries(store.cstore, irecords, delays, weights, pos)
            s = sum_static(store.cstore, irecords, delays, weights, pos, 1)
            print benchmark.__str__(header=False)
            benchmark.clear()
            num.testing.assert_equal(t, s)


if __name__ == '__main__':
    util.setup_logging('test_gf', 'warning')
    unittest.main(defaultTest='GFStaticTest.test_sum_static')
