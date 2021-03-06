from pyrocko.snuffling import Param, Snuffling, Switch, Choice
from pyrocko.gui_util import Marker

h = 3600.

scalingmethods = ('[0-1]', '[-1/ratio,1]', '[-1/ratio,1] clipped to [0,1]')
scalingmethod_map = dict([(m, i+1) for (i, m) in enumerate(scalingmethods)])


class DetectorSTALTA(Snuffling):

    '''
    <html>
    <head>
    <style type="text/css">
        body { margin-left:10px };
    </style>
    </head>
    <body>
    <h1 align="center">STA/LTA</h1>
    <p>
    Detect onsets automatically using the Short-Time-Average/Long-Time-Average
    ratio.<br/>
    This snuffling uses the method:
    <a href="http://emolch.github.io/pyrocko/v0.3/trace.html#pyrocko.trace.\
Trace.sta_lta_centered" style="text-decoration:none">
        <pre>pyrocko.trace.Trace.sta_lta_centered</pre>
    </a></p>
    <p>
    <b>Parameters:</b><br />
        <b>&middot; Highpass [Hz]</b>
            - Apply high pass filter before analysing.<br />
        <b>&middot; Lowpass [Hz]</b>
            - Apply low pass filter before analysing.<br />
        <b>&middot; Short Window [s]</b>
            -  Window length of the short window.<br />
        <b>&middot; Ratio</b>
            -  Long window length is the short window length times the
               <b>Ratio</b>.<br />
        <b>&middot; Level</b>
            -  Define a trigger threshold. A marker is added where STA/LTA
               ratios exceed this threshold. <br />
        <b>&middot; Processing Block length</b>
            -  Subdivide dataset in blocks for analysis. <br />
        <b>&middot; Show trigger level traces </b>
            -  Add level traces showing the STA/LTA ration for each
               trace.<br />
        <b>&middot; Apply to full dataset</b>
            -  If marked entire loaded dataset will be analyzed. <br />
        <b>&middot; Scaling/Normalization method</b>
            -  Select how output of the STA/LTA should be scaled.</ br>
    </p>
    <p>
    A helpfull description of how to tune the STA/LTA's parameters can be found
    in the the following ebook chapter by Amadej Trnkoczy: <a
    href="http://ebooks.gfz-potsdam.de/pubman/item/escidoc:4097:3/component/\
escidoc:4098/IS_8.1_rev1.pdf">Understanding
    and parameter setting of STA/LTA trigger algorithm</a>
    </p>
    </body>
    </html>
    '''
    def setup(self):

        self.set_name('STA LTA')
        self.add_parameter(Param(
            'Highpass [Hz]', 'highpass', None, 0.001, 100., low_is_none=True))
        self.add_parameter(Param(
            'Lowpass [Hz]', 'lowpass', None, 0.001, 100., high_is_none=True))
        self.add_parameter(Param(
            'Short Window [s]', 'swin', 30., 0.01, 2*h))
        self.add_parameter(Param(
            'Ratio',  'ratio', 3., 1.1, 20.))
        self.add_parameter(Param(
            'Level', 'level', 0.5, 0., 1.))
        self.add_parameter(Param(
            'Processing Block length (rel. to long window)', 'block_factor',
            10., 2., 100.,))
        self.add_parameter(Switch(
            'Show trigger level traces', 'show_level_traces', False))
        self.add_parameter(Switch(
            'Apply to full dataset', 'apply_to_all', False))
        self.add_parameter(Choice(
            'Variant', 'variant', 'centered', ['centered', 'right']))
        self.add_parameter(Choice(
            'Scaling/Normalization method', 'scalingmethod', '[0-1]',
            scalingmethods))

        self.set_live_update(False)

    def call(self):
        '''Main work routine of the snuffling.'''

        self.cleanup()

        swin, ratio = self.swin, self.ratio
        lwin = swin * ratio
        tpad = lwin

        pile = self.get_pile()
        tmin, tmax = pile.get_tmin() + tpad, pile.get_tmax() - tpad

        if not self.apply_to_all:
            vtmin, vtmax = self.get_viewer().get_time_range()
            tmin = max(vtmin, tmin)
            tmax = min(vtmax, tmax)

        tinc = min(lwin * self.block_factor, tmax-tmin)

        show_level_traces = self.show_level_traces

        if show_level_traces and tmax-tmin > lwin * 150:
            self.error(
                'Processing time window is longer than 50 x LTA window. '
                'Turning off display of level traces.')
            show_level_traces = False

        markers = []
        for traces in pile.chopper(
                tmin=tmin, tmax=tmax, tinc=tinc, tpad=tpad,
                want_incomplete=False):

            sumtrace = None
            isum = 0
            for trace in traces:
                if self.lowpass is not None:
                    trace.lowpass(4, self.lowpass, nyquist_exception=True)

                if self.highpass is not None:
                    trace.highpass(4, self.highpass, nyquist_exception=True)

                if self.variant == 'centered':
                    trace.sta_lta_centered(
                        swin, lwin,
                        scalingmethod=scalingmethod_map[self.scalingmethod])
                elif self.variant == 'right':
                    trace.sta_lta_right(
                        swin, lwin,
                        scalingmethod=scalingmethod_map[self.scalingmethod])

                trace.chop(trace.wmin, min(trace.wmax, tmax))
                trace.set_codes(location='cg')
                trace.meta = {'tabu': True}

                if sumtrace is None:
                    sumtrace = trace.copy()
                    sumtrace.set_codes(
                        network='', station='SUM', location='cg', channel='')
                else:
                    sumtrace.add(trace)
                isum += 1

            if show_level_traces:
                self.add_traces(traces)

            if sumtrace is not None:
                tpeaks, apeaks = sumtrace.peaks(self.level*isum, swin)

                for t, a in zip(tpeaks, apeaks):
                    mark = Marker([], t, t)
                    print mark, a
                    markers.append(mark)

                if show_level_traces:
                    self.add_trace(sumtrace)

        self.add_markers(markers)


def __snufflings__():
    return [DetectorSTALTA()]
